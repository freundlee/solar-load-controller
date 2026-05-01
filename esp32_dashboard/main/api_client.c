/*
 * API Client - HTTP communication with solar_load_controller
 * Polls GET /api/esp32/dashboard every 5s and provides control endpoints
 */

#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_http_client.h"
#include "cJSON.h"
#include "nvs_flash.h"
#include "nvs.h"

#include "api_client.h"
#include "data_model.h"
#include "wifi_manager.h"

static const char *TAG = "api_client";

#define API_POLL_INTERVAL_MS    5000
#define API_TIMEOUT_MS          5000
#define API_MAX_RESPONSE_SIZE   2048
#define NVS_NAMESPACE           "solar_cfg"

static char s_api_base_url[128] = "http://192.168.178.100:8000";
static char s_api_key[64] = "";
static TaskHandle_t s_poll_task = NULL;
static bool s_polling = false;

/* -------------------------------------------------------------------------- */
/* NVS Config                                                                  */
/* -------------------------------------------------------------------------- */
static void load_config(void)
{
    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) == ESP_OK) {
        size_t len = sizeof(s_api_base_url);
        nvs_get_str(nvs, "api_url", s_api_base_url, &len);
        len = sizeof(s_api_key);
        nvs_get_str(nvs, "api_key", s_api_key, &len);
        nvs_close(nvs);
    }
    ESP_LOGI(TAG, "API URL: %s", s_api_base_url);
}

/* -------------------------------------------------------------------------- */
/* HTTP Helpers                                                                 */
/* -------------------------------------------------------------------------- */
typedef struct {
    char *buf;
    int len;
    int capacity;
} http_response_t;

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    http_response_t *resp = (http_response_t *)evt->user_data;
    if (evt->event_id == HTTP_EVENT_ON_DATA && resp) {
        if (resp->len + evt->data_len < resp->capacity) {
            memcpy(resp->buf + resp->len, evt->data, evt->data_len);
            resp->len += evt->data_len;
            resp->buf[resp->len] = '\0';
        }
    }
    return ESP_OK;
}

static esp_err_t http_get(const char *path, char *response, int max_len)
{
    char url[256];
    snprintf(url, sizeof(url), "%s%s", s_api_base_url, path);

    http_response_t resp = { .buf = response, .len = 0, .capacity = max_len };

    esp_http_client_config_t cfg = {
        .url = url,
        .timeout_ms = API_TIMEOUT_MS,
        .event_handler = http_event_handler,
        .user_data = &resp,
    };

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (s_api_key[0]) {
        esp_http_client_set_header(client, "X-API-Key", s_api_key);
    }

    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (err != ESP_OK) return err;
    if (status != 200) return ESP_FAIL;
    return ESP_OK;
}

static esp_err_t http_post_json(const char *path, const char *json_body)
{
    char url[256];
    snprintf(url, sizeof(url), "%s%s", s_api_base_url, path);

    esp_http_client_config_t cfg = {
        .url = url,
        .timeout_ms = API_TIMEOUT_MS,
        .method = HTTP_METHOD_POST,
    };

    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    if (s_api_key[0]) {
        esp_http_client_set_header(client, "X-API-Key", s_api_key);
    }
    esp_http_client_set_post_field(client, json_body, strlen(json_body));

    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (err != ESP_OK) return err;
    if (status < 200 || status >= 300) return ESP_FAIL;
    return ESP_OK;
}

/* -------------------------------------------------------------------------- */
/* Dashboard Fetch & Parse                                                     */
/* -------------------------------------------------------------------------- */
esp_err_t api_client_fetch_dashboard(void)
{
    char *response = heap_caps_malloc(API_MAX_RESPONSE_SIZE, MALLOC_CAP_SPIRAM);
    if (!response) return ESP_ERR_NO_MEM;

    esp_err_t err = http_get("/api/esp32/dashboard", response, API_MAX_RESPONSE_SIZE);
    if (err != ESP_OK) {
        free(response);
        /* Mark disconnected */
        solar_data_t data = *data_model_get();
        data.connected = false;
        data_model_update(&data);
        return err;
    }

    cJSON *root = cJSON_Parse(response);
    free(response);
    if (!root) return ESP_ERR_INVALID_RESPONSE;

    solar_data_t data = {0};
    data.connected = true;
    data.solar_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "solar_w"));
    data.battery_soc = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "battery_soc"));
    data.battery_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "battery_w"));
    data.output_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "output_w"));
    data.load_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "load_w"));
    data.pv1_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "pv1_w"));
    data.pv2_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "pv2_w"));
    data.mi_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "mi_w"));
    data.meter_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "meter_w"));
    data.meter_ok = cJSON_IsTrue(cJSON_GetObjectItem(root, "meter_ok"));
    data.auto_mode = cJSON_IsTrue(cJSON_GetObjectItem(root, "auto"));
    data.avg30 = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "avg30"));
    data.avg60 = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "avg60"));
    data.baseline_w = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "baseline_w"));
    data.solar_kwh = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "solar_kwh"));
    data.pv1_kwh = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "pv1_kwh"));
    data.pv2_kwh = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "pv2_kwh"));
    data.mi_kwh = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "mi_kwh"));
    data.charge_kwh = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "charge_kwh"));
    data.discharge_kwh = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "discharge_kwh"));
    data.import_kwh = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "import_kwh"));
    data.export_kwh = (float)cJSON_GetNumberValue(cJSON_GetObjectItem(root, "export_kwh"));

    cJSON *state_item = cJSON_GetObjectItem(root, "state");
    if (cJSON_IsString(state_item) && state_item->valuestring) {
        strncpy(data.state, state_item->valuestring, sizeof(data.state) - 1);
    }

    cJSON *ts_item = cJSON_GetObjectItem(root, "ts");
    if (cJSON_IsString(ts_item) && ts_item->valuestring) {
        strncpy(data.timestamp, ts_item->valuestring, sizeof(data.timestamp) - 1);
    }

    cJSON_Delete(root);
    data_model_update(&data);
    return ESP_OK;
}

/* -------------------------------------------------------------------------- */
/* Control Actions                                                             */
/* -------------------------------------------------------------------------- */
esp_err_t api_client_set_load(int watts)
{
    char body[64];
    snprintf(body, sizeof(body), "{\"load\":%d}", watts);
    return http_post_json("/api/esp32/set-load", body);
}

esp_err_t api_client_set_auto_mode(bool enabled)
{
    char url[128];
    snprintf(url, sizeof(url), "/api/esp32/auto-mode?enabled=%s", enabled ? "true" : "false");

    char response[128] = {0};
    /* Use POST with query param */
    char full_url[256];
    snprintf(full_url, sizeof(full_url), "%s%s", s_api_base_url, url);

    esp_http_client_config_t cfg = {
        .url = full_url,
        .timeout_ms = API_TIMEOUT_MS,
        .method = HTTP_METHOD_POST,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (s_api_key[0]) {
        esp_http_client_set_header(client, "X-API-Key", s_api_key);
    }
    esp_err_t err = esp_http_client_perform(client);
    esp_http_client_cleanup(client);
    return err;
}

esp_err_t api_client_set_config(const char *key, const char *value)
{
    char body[128];
    snprintf(body, sizeof(body), "{\"key\":\"%s\",\"value\":\"%s\"}", key, value);
    return http_post_json("/api/esp32/config", body);
}

/* -------------------------------------------------------------------------- */
/* Polling Task                                                                */
/* -------------------------------------------------------------------------- */
static void poll_task(void *arg)
{
    ESP_LOGI(TAG, "Polling task started (interval: %dms)", API_POLL_INTERVAL_MS);
    while (s_polling) {
        if (wifi_manager_is_connected()) {
            esp_err_t err = api_client_fetch_dashboard();
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "Dashboard fetch failed: %s", esp_err_to_name(err));
            }
        }
        vTaskDelay(pdMS_TO_TICKS(API_POLL_INTERVAL_MS));
    }
    s_poll_task = NULL;
    vTaskDelete(NULL);
}

esp_err_t api_client_init(void)
{
    load_config();
    return ESP_OK;
}

esp_err_t api_client_start_polling(void)
{
    if (s_polling) return ESP_OK;
    s_polling = true;
    xTaskCreatePinnedToCore(poll_task, "api_poll", 4096, NULL, 3, &s_poll_task, 1);
    return ESP_OK;
}

esp_err_t api_client_stop_polling(void)
{
    s_polling = false;
    return ESP_OK;
}

esp_err_t api_client_reconfigure(void)
{
    load_config();
    return ESP_OK;
}
