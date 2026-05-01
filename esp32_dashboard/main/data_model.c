/*
 * Data Model - Central data store for solar system state
 */

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "data_model.h"

#define MAX_CALLBACKS 4

static const char *TAG = "data_model";
static solar_data_t s_data = {0};
static SemaphoreHandle_t s_mutex = NULL;
static data_update_cb_t s_callbacks[MAX_CALLBACKS] = {NULL};
static int s_cb_count = 0;

void data_model_init(void)
{
    s_mutex = xSemaphoreCreateMutex();
    memset(&s_data, 0, sizeof(s_data));
    s_data.connected = false;
    ESP_LOGI(TAG, "Data model initialized");
}

const solar_data_t *data_model_get(void)
{
    return &s_data;
}

void data_model_update(const solar_data_t *new_data)
{
    if (xSemaphoreTake(s_mutex, pdMS_TO_TICKS(100))) {
        memcpy(&s_data, new_data, sizeof(solar_data_t));
        s_data.last_update_ms = (uint32_t)(esp_timer_get_time() / 1000);
        xSemaphoreGive(s_mutex);

        /* Notify observers */
        for (int i = 0; i < s_cb_count; i++) {
            if (s_callbacks[i]) {
                s_callbacks[i](&s_data);
            }
        }
    }
}

void data_model_register_callback(data_update_cb_t cb)
{
    if (s_cb_count < MAX_CALLBACKS) {
        s_callbacks[s_cb_count++] = cb;
    }
}
