/*
 * UI Settings - WiFi, API config, and display brightness
 */

#include "ui_settings.h"
#include "ui_common.h"
#include "ui_dashboard.h"
#include "ui_control.h"
#include "ui_energy.h"
#include "api_client.h"
#include "wifi_manager.h"
#include "esp_log.h"
#include "nvs.h"
#include "driver/ledc.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "ui_settings";

static lv_obj_t *s_screen = NULL;
static lv_obj_t *s_ta_ssid = NULL;
static lv_obj_t *s_ta_pass = NULL;
static lv_obj_t *s_ta_url = NULL;
static lv_obj_t *s_ta_key = NULL;
static lv_obj_t *s_slider_bright = NULL;
static lv_obj_t *s_lbl_ip = NULL;
static lv_obj_t *s_kb = NULL;

#define NVS_NAMESPACE "solar_cfg"

/* -------------------------------------------------------------------------- */
/* Navigation                                                                  */
/* -------------------------------------------------------------------------- */
static void nav_dashboard_cb(lv_event_t *e) { ui_dashboard_show(); }
static void nav_control_cb(lv_event_t *e) { ui_control_show(); }
static void nav_energy_cb(lv_event_t *e) { ui_energy_show(); }

/* -------------------------------------------------------------------------- */
/* Keyboard handling                                                           */
/* -------------------------------------------------------------------------- */
static void ta_focus_cb(lv_event_t *e)
{
    lv_obj_t *ta = lv_event_get_target(e);
    if (s_kb == NULL) {
        s_kb = lv_keyboard_create(s_screen);
        lv_obj_set_size(s_kb, LV_PCT(100), 240);
        lv_obj_align(s_kb, LV_ALIGN_BOTTOM_MID, 0, 0);
    }
    lv_keyboard_set_textarea(s_kb, ta);
    lv_obj_remove_flag(s_kb, LV_OBJ_FLAG_HIDDEN);
}

static void ta_defocus_cb(lv_event_t *e)
{
    if (s_kb) {
        lv_obj_add_flag(s_kb, LV_OBJ_FLAG_HIDDEN);
    }
}

/* -------------------------------------------------------------------------- */
/* Save callbacks                                                              */
/* -------------------------------------------------------------------------- */
static void save_wifi_cb(lv_event_t *e)
{
    const char *ssid = lv_textarea_get_text(s_ta_ssid);
    const char *pass = lv_textarea_get_text(s_ta_pass);

    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs) == ESP_OK) {
        nvs_set_str(nvs, "wifi_ssid", ssid);
        nvs_set_str(nvs, "wifi_pass", pass);
        nvs_commit(nvs);
        nvs_close(nvs);
        ESP_LOGI(TAG, "Wi-Fi config saved, restarting connection");
        wifi_manager_connect();
    }
}

static void save_api_cb(lv_event_t *e)
{
    const char *url = lv_textarea_get_text(s_ta_url);
    const char *key = lv_textarea_get_text(s_ta_key);

    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs) == ESP_OK) {
        nvs_set_str(nvs, "api_url", url);
        nvs_set_str(nvs, "api_key", key);
        nvs_commit(nvs);
        nvs_close(nvs);
        ESP_LOGI(TAG, "API config saved");
        api_client_reconfigure();
    }
}

static void brightness_cb(lv_event_t *e)
{
    int val = lv_slider_get_value(s_slider_bright);
    /* Map 0-100 to LEDC duty (0-8191 for 13-bit) */
    uint32_t duty = (uint32_t)(val * 8191 / 100);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}

/* -------------------------------------------------------------------------- */
/* Create                                                                      */
/* -------------------------------------------------------------------------- */
void ui_settings_create(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, UI_COLOR_BG, 0);
    lv_obj_set_flex_flow(s_screen, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(s_screen, 12, 0);
    lv_obj_set_style_pad_gap(s_screen, 8, 0);
    lv_obj_set_scrollbar_mode(s_screen, LV_SCROLLBAR_MODE_OFF);

    /* Title */
    lv_obj_t *title = lv_label_create(s_screen);
    lv_label_set_text(title, "Settings");
    lv_obj_set_style_text_font(title, UI_FONT_MEDIUM, 0);
    lv_obj_set_style_text_color(title, UI_COLOR_TEXT, 0);

    /* ---- WiFi Section ---- */
    lv_obj_t *wifi_card = lv_obj_create(s_screen);
    lv_obj_set_size(wifi_card, LV_PCT(100), LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(wifi_card, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(wifi_card, 10, 0);
    lv_obj_set_style_pad_all(wifi_card, 12, 0);
    lv_obj_set_flex_flow(wifi_card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(wifi_card, 6, 0);
    lv_obj_clear_flag(wifi_card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *lbl = lv_label_create(wifi_card);
    lv_label_set_text(lbl, LV_SYMBOL_WIFI " Wi-Fi");
    lv_obj_set_style_text_font(lbl, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(lbl, UI_COLOR_TEXT, 0);

    s_ta_ssid = lv_textarea_create(wifi_card);
    lv_textarea_set_one_line(s_ta_ssid, true);
    lv_textarea_set_placeholder_text(s_ta_ssid, "SSID");
    lv_obj_set_width(s_ta_ssid, LV_PCT(100));
    lv_obj_add_event_cb(s_ta_ssid, ta_focus_cb, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(s_ta_ssid, ta_defocus_cb, LV_EVENT_DEFOCUSED, NULL);

    s_ta_pass = lv_textarea_create(wifi_card);
    lv_textarea_set_one_line(s_ta_pass, true);
    lv_textarea_set_placeholder_text(s_ta_pass, "Password");
    lv_textarea_set_password_mode(s_ta_pass, true);
    lv_obj_set_width(s_ta_pass, LV_PCT(100));
    lv_obj_add_event_cb(s_ta_pass, ta_focus_cb, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(s_ta_pass, ta_defocus_cb, LV_EVENT_DEFOCUSED, NULL);

    lv_obj_t *btn_wifi = lv_btn_create(wifi_card);
    lv_obj_set_size(btn_wifi, 120, 36);
    lv_obj_set_style_bg_color(btn_wifi, UI_COLOR_BLUE, 0);
    lbl = lv_label_create(btn_wifi);
    lv_label_set_text(lbl, "Save WiFi");
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn_wifi, save_wifi_cb, LV_EVENT_CLICKED, NULL);

    s_lbl_ip = lv_label_create(wifi_card);
    lv_label_set_text(s_lbl_ip, "IP: not connected");
    lv_obj_set_style_text_font(s_lbl_ip, UI_FONT_TINY, 0);
    lv_obj_set_style_text_color(s_lbl_ip, UI_COLOR_TEXT_DIM, 0);

    /* ---- API Section ---- */
    lv_obj_t *api_card = lv_obj_create(s_screen);
    lv_obj_set_size(api_card, LV_PCT(100), LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(api_card, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(api_card, 10, 0);
    lv_obj_set_style_pad_all(api_card, 12, 0);
    lv_obj_set_flex_flow(api_card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(api_card, 6, 0);
    lv_obj_clear_flag(api_card, LV_OBJ_FLAG_SCROLLABLE);

    lbl = lv_label_create(api_card);
    lv_label_set_text(lbl, LV_SYMBOL_DOWNLOAD " API Server");
    lv_obj_set_style_text_font(lbl, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(lbl, UI_COLOR_TEXT, 0);

    s_ta_url = lv_textarea_create(api_card);
    lv_textarea_set_one_line(s_ta_url, true);
    lv_textarea_set_placeholder_text(s_ta_url, "http://192.168.1.x:5000");
    lv_obj_set_width(s_ta_url, LV_PCT(100));
    lv_obj_add_event_cb(s_ta_url, ta_focus_cb, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(s_ta_url, ta_defocus_cb, LV_EVENT_DEFOCUSED, NULL);

    s_ta_key = lv_textarea_create(api_card);
    lv_textarea_set_one_line(s_ta_key, true);
    lv_textarea_set_placeholder_text(s_ta_key, "API Key (optional)");
    lv_obj_set_width(s_ta_key, LV_PCT(100));
    lv_obj_add_event_cb(s_ta_key, ta_focus_cb, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(s_ta_key, ta_defocus_cb, LV_EVENT_DEFOCUSED, NULL);

    lv_obj_t *btn_api = lv_btn_create(api_card);
    lv_obj_set_size(btn_api, 120, 36);
    lv_obj_set_style_bg_color(btn_api, UI_COLOR_BLUE, 0);
    lbl = lv_label_create(btn_api);
    lv_label_set_text(lbl, "Save API");
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn_api, save_api_cb, LV_EVENT_CLICKED, NULL);

    /* ---- Brightness ---- */
    lv_obj_t *bright_card = lv_obj_create(s_screen);
    lv_obj_set_size(bright_card, LV_PCT(100), 80);
    lv_obj_set_style_bg_color(bright_card, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(bright_card, 10, 0);
    lv_obj_set_style_pad_all(bright_card, 12, 0);
    lv_obj_set_flex_flow(bright_card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(bright_card, 8, 0);
    lv_obj_clear_flag(bright_card, LV_OBJ_FLAG_SCROLLABLE);

    lbl = lv_label_create(bright_card);
    lv_label_set_text(lbl, LV_SYMBOL_IMAGE " Brightness");
    lv_obj_set_style_text_font(lbl, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(lbl, UI_COLOR_TEXT, 0);

    s_slider_bright = lv_slider_create(bright_card);
    lv_obj_set_width(s_slider_bright, LV_PCT(90));
    lv_slider_set_range(s_slider_bright, 5, 100);
    lv_slider_set_value(s_slider_bright, 80, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(s_slider_bright, UI_COLOR_PRIMARY, LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_slider_bright, UI_COLOR_YELLOW, LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(s_slider_bright, UI_COLOR_YELLOW, LV_PART_KNOB);
    lv_obj_add_event_cb(s_slider_bright, brightness_cb, LV_EVENT_VALUE_CHANGED, NULL);

    /* ---- Navigation Bar ---- */
    lv_obj_t *nav = lv_obj_create(s_screen);
    lv_obj_set_size(nav, LV_PCT(100), UI_NAV_HEIGHT);
    lv_obj_set_style_bg_color(nav, UI_COLOR_PRIMARY, 0);
    lv_obj_set_style_radius(nav, 12, 0);
    lv_obj_set_style_pad_all(nav, 4, 0);
    lv_obj_set_flex_flow(nav, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(nav, LV_FLEX_ALIGN_SPACE_AROUND,
                          LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_clear_flag(nav, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *btn;

    btn = lv_btn_create(nav);
    lv_obj_set_size(btn, 90, 44);
    lv_obj_set_style_bg_color(btn, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(btn, 8, 0);
    lbl = lv_label_create(btn);
    lv_label_set_text(lbl, LV_SYMBOL_HOME);
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn, nav_dashboard_cb, LV_EVENT_CLICKED, NULL);

    btn = lv_btn_create(nav);
    lv_obj_set_size(btn, 90, 44);
    lv_obj_set_style_bg_color(btn, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(btn, 8, 0);
    lbl = lv_label_create(btn);
    lv_label_set_text(lbl, LV_SYMBOL_SETTINGS);
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn, nav_control_cb, LV_EVENT_CLICKED, NULL);

    btn = lv_btn_create(nav);
    lv_obj_set_size(btn, 90, 44);
    lv_obj_set_style_bg_color(btn, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(btn, 8, 0);
    lbl = lv_label_create(btn);
    lv_label_set_text(lbl, LV_SYMBOL_BAR_CHART);
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn, nav_energy_cb, LV_EVENT_CLICKED, NULL);

    btn = lv_btn_create(nav);
    lv_obj_set_size(btn, 90, 44);
    lv_obj_set_style_bg_color(btn, UI_COLOR_ACCENT, 0);
    lv_obj_set_style_radius(btn, 8, 0);
    lbl = lv_label_create(btn);
    lv_label_set_text(lbl, LV_SYMBOL_LIST);
    lv_obj_center(lbl);

    /* Load saved values into text areas */
    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) == ESP_OK) {
        char tmp[128];
        size_t len;

        len = sizeof(tmp);
        if (nvs_get_str(nvs, "wifi_ssid", tmp, &len) == ESP_OK) {
            lv_textarea_set_text(s_ta_ssid, tmp);
        }
        len = sizeof(tmp);
        if (nvs_get_str(nvs, "api_url", tmp, &len) == ESP_OK) {
            lv_textarea_set_text(s_ta_url, tmp);
        }
        len = sizeof(tmp);
        if (nvs_get_str(nvs, "api_key", tmp, &len) == ESP_OK) {
            lv_textarea_set_text(s_ta_key, tmp);
        }
        nvs_close(nvs);
    }
}

void ui_settings_show(void)
{
    /* Update IP display */
    if (wifi_manager_is_connected()) {
        char buf[32];
        snprintf(buf, sizeof(buf), "IP: %s", wifi_manager_get_ip());
        lv_label_set_text(s_lbl_ip, buf);
    } else {
        lv_label_set_text(s_lbl_ip, "IP: not connected");
    }

    lv_screen_load(s_screen);
}
