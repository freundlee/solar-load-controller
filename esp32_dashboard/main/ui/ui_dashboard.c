/*
 * UI Dashboard - Main monitoring screen with real-time solar data
 * Layout: Status bar + 2x2 metric cards + PV channels + energy summary + nav
 */

#include "ui_dashboard.h"
#include "ui_common.h"
#include "ui_control.h"
#include "ui_energy.h"
#include "ui_settings.h"
#include "data_model.h"
#include "wifi_manager.h"
#include <stdio.h>

static lv_obj_t *s_screen = NULL;

/* Metric card labels */
static lv_obj_t *s_lbl_solar_val = NULL;
static lv_obj_t *s_lbl_batt_val = NULL;
static lv_obj_t *s_lbl_grid_val = NULL;
static lv_obj_t *s_lbl_load_val = NULL;

/* PV channel labels */
static lv_obj_t *s_lbl_pv1 = NULL;
static lv_obj_t *s_lbl_pv2 = NULL;
static lv_obj_t *s_lbl_mi = NULL;

/* Energy summary */
static lv_obj_t *s_lbl_solar_kwh = NULL;
static lv_obj_t *s_lbl_import_kwh = NULL;
static lv_obj_t *s_lbl_export_kwh = NULL;

/* Status */
static lv_obj_t *s_lbl_status = NULL;
static lv_obj_t *s_lbl_auto = NULL;

/* Battery arc */
static lv_obj_t *s_arc_batt = NULL;

/* Forward declarations */
static void on_data_update_dashboard(const solar_data_t *data);

/* -------------------------------------------------------------------------- */
/* Navigation callbacks                                                        */
/* -------------------------------------------------------------------------- */
static void nav_control_cb(lv_event_t *e) { ui_control_show(); }
static void nav_energy_cb(lv_event_t *e) { ui_energy_show(); }
static void nav_settings_cb(lv_event_t *e) { ui_settings_show(); }

/* -------------------------------------------------------------------------- */
/* Helper: Create a metric card                                                */
/* -------------------------------------------------------------------------- */
static lv_obj_t *create_metric_card(lv_obj_t *parent, const char *title,
                                     lv_color_t accent, lv_obj_t **val_label)
{
    lv_obj_t *card = lv_obj_create(parent);
    lv_obj_set_size(card, 215, 130);
    lv_obj_set_style_bg_color(card, UI_COLOR_CARD, 0);
    lv_obj_set_style_border_color(card, accent, 0);
    lv_obj_set_style_border_width(card, 2, 0);
    lv_obj_set_style_border_side(card, LV_BORDER_SIDE_LEFT, 0);
    lv_obj_set_style_radius(card, 12, 0);
    lv_obj_set_style_pad_all(card, 12, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);

    /* Title */
    lv_obj_t *lbl_title = lv_label_create(card);
    lv_label_set_text(lbl_title, title);
    lv_obj_set_style_text_font(lbl_title, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(lbl_title, UI_COLOR_TEXT_DIM, 0);

    /* Value */
    *val_label = lv_label_create(card);
    lv_label_set_text(*val_label, "---");
    lv_obj_set_style_text_font(*val_label, UI_FONT_LARGE, 0);
    lv_obj_set_style_text_color(*val_label, UI_COLOR_TEXT, 0);

    return card;
}

/* -------------------------------------------------------------------------- */
/* Create Dashboard Screen                                                     */
/* -------------------------------------------------------------------------- */
void ui_dashboard_create(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, UI_COLOR_BG, 0);
    lv_obj_set_flex_flow(s_screen, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(s_screen, 8, 0);
    lv_obj_set_style_pad_gap(s_screen, 8, 0);
    lv_obj_clear_flag(s_screen, LV_OBJ_FLAG_SCROLLABLE);

    /* ---- Status Bar ---- */
    lv_obj_t *status_bar = lv_obj_create(s_screen);
    lv_obj_set_size(status_bar, LV_PCT(100), 36);
    lv_obj_set_style_bg_opa(status_bar, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(status_bar, 0, 0);
    lv_obj_set_style_pad_all(status_bar, 4, 0);
    lv_obj_clear_flag(status_bar, LV_OBJ_FLAG_SCROLLABLE);

    s_lbl_status = lv_label_create(status_bar);
    lv_label_set_text(s_lbl_status, LV_SYMBOL_WIFI " Connecting...");
    lv_obj_set_style_text_font(s_lbl_status, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_status, UI_COLOR_TEXT_DIM, 0);
    lv_obj_align(s_lbl_status, LV_ALIGN_LEFT_MID, 0, 0);

    s_lbl_auto = lv_label_create(status_bar);
    lv_label_set_text(s_lbl_auto, "AUTO");
    lv_obj_set_style_text_font(s_lbl_auto, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_auto, UI_COLOR_GREEN, 0);
    lv_obj_align(s_lbl_auto, LV_ALIGN_RIGHT_MID, 0, 0);

    /* ---- Metric Cards (2x2 grid) ---- */
    lv_obj_t *card_grid = lv_obj_create(s_screen);
    lv_obj_set_size(card_grid, LV_PCT(100), 280);
    lv_obj_set_style_bg_opa(card_grid, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(card_grid, 0, 0);
    lv_obj_set_style_pad_all(card_grid, 0, 0);
    lv_obj_set_flex_flow(card_grid, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_flex_align(card_grid, LV_FLEX_ALIGN_SPACE_BETWEEN,
                          LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
    lv_obj_set_style_pad_gap(card_grid, 10, 0);
    lv_obj_clear_flag(card_grid, LV_OBJ_FLAG_SCROLLABLE);

    create_metric_card(card_grid, LV_SYMBOL_IMAGE " Solar", UI_COLOR_SOLAR, &s_lbl_solar_val);
    create_metric_card(card_grid, LV_SYMBOL_BATTERY_FULL " Battery", UI_COLOR_BATTERY, &s_lbl_batt_val);
    create_metric_card(card_grid, LV_SYMBOL_LOOP " Grid", UI_COLOR_BLUE, &s_lbl_grid_val);
    create_metric_card(card_grid, LV_SYMBOL_CHARGE " Load", UI_COLOR_ACCENT, &s_lbl_load_val);

    /* ---- PV Channel Row ---- */
    lv_obj_t *pv_row = lv_obj_create(s_screen);
    lv_obj_set_size(pv_row, LV_PCT(100), 60);
    lv_obj_set_style_bg_color(pv_row, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(pv_row, 10, 0);
    lv_obj_set_style_pad_all(pv_row, 10, 0);
    lv_obj_set_flex_flow(pv_row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(pv_row, LV_FLEX_ALIGN_SPACE_AROUND,
                          LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_clear_flag(pv_row, LV_OBJ_FLAG_SCROLLABLE);

    s_lbl_pv1 = lv_label_create(pv_row);
    lv_label_set_text(s_lbl_pv1, "PV1: ---W");
    lv_obj_set_style_text_font(s_lbl_pv1, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_pv1, UI_COLOR_SOLAR, 0);

    s_lbl_pv2 = lv_label_create(pv_row);
    lv_label_set_text(s_lbl_pv2, "PV2: ---W");
    lv_obj_set_style_text_font(s_lbl_pv2, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_pv2, UI_COLOR_SOLAR, 0);

    s_lbl_mi = lv_label_create(pv_row);
    lv_label_set_text(s_lbl_mi, "MI: ---W");
    lv_obj_set_style_text_font(s_lbl_mi, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_mi, UI_COLOR_TEXT_DIM, 0);

    /* ---- Energy Summary ---- */
    lv_obj_t *energy_row = lv_obj_create(s_screen);
    lv_obj_set_size(energy_row, LV_PCT(100), 80);
    lv_obj_set_style_bg_color(energy_row, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(energy_row, 10, 0);
    lv_obj_set_style_pad_all(energy_row, 12, 0);
    lv_obj_set_flex_flow(energy_row, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(energy_row, 4, 0);
    lv_obj_clear_flag(energy_row, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *energy_title = lv_label_create(energy_row);
    lv_label_set_text(energy_title, "Today's Energy");
    lv_obj_set_style_text_font(energy_title, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(energy_title, UI_COLOR_TEXT_DIM, 0);

    lv_obj_t *energy_vals = lv_obj_create(energy_row);
    lv_obj_set_size(energy_vals, LV_PCT(100), 40);
    lv_obj_set_style_bg_opa(energy_vals, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(energy_vals, 0, 0);
    lv_obj_set_style_pad_all(energy_vals, 0, 0);
    lv_obj_set_flex_flow(energy_vals, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(energy_vals, LV_FLEX_ALIGN_SPACE_AROUND,
                          LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_clear_flag(energy_vals, LV_OBJ_FLAG_SCROLLABLE);

    s_lbl_solar_kwh = lv_label_create(energy_vals);
    lv_label_set_text(s_lbl_solar_kwh, LV_SYMBOL_IMAGE " -.- kWh");
    lv_obj_set_style_text_font(s_lbl_solar_kwh, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_solar_kwh, UI_COLOR_SOLAR, 0);

    s_lbl_import_kwh = lv_label_create(energy_vals);
    lv_label_set_text(s_lbl_import_kwh, LV_SYMBOL_DOWNLOAD " -.- kWh");
    lv_obj_set_style_text_font(s_lbl_import_kwh, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_import_kwh, UI_COLOR_GRID_IMP, 0);

    s_lbl_export_kwh = lv_label_create(energy_vals);
    lv_label_set_text(s_lbl_export_kwh, LV_SYMBOL_UPLOAD " -.- kWh");
    lv_obj_set_style_text_font(s_lbl_export_kwh, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_export_kwh, UI_COLOR_GRID_EXP, 0);

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

    /* Nav: Dashboard (current - highlighted) */
    lv_obj_t *btn_dash = lv_btn_create(nav);
    lv_obj_set_size(btn_dash, 90, 44);
    lv_obj_set_style_bg_color(btn_dash, UI_COLOR_ACCENT, 0);
    lv_obj_set_style_radius(btn_dash, 8, 0);
    lv_obj_t *lbl = lv_label_create(btn_dash);
    lv_label_set_text(lbl, LV_SYMBOL_HOME);
    lv_obj_center(lbl);

    /* Nav: Control */
    lv_obj_t *btn_ctrl = lv_btn_create(nav);
    lv_obj_set_size(btn_ctrl, 90, 44);
    lv_obj_set_style_bg_color(btn_ctrl, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(btn_ctrl, 8, 0);
    lbl = lv_label_create(btn_ctrl);
    lv_label_set_text(lbl, LV_SYMBOL_SETTINGS);
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn_ctrl, nav_control_cb, LV_EVENT_CLICKED, NULL);

    /* Nav: Energy */
    lv_obj_t *btn_energy = lv_btn_create(nav);
    lv_obj_set_size(btn_energy, 90, 44);
    lv_obj_set_style_bg_color(btn_energy, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(btn_energy, 8, 0);
    lbl = lv_label_create(btn_energy);
    lv_label_set_text(lbl, LV_SYMBOL_BAR_CHART);
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn_energy, nav_energy_cb, LV_EVENT_CLICKED, NULL);

    /* Nav: Settings */
    lv_obj_t *btn_set = lv_btn_create(nav);
    lv_obj_set_size(btn_set, 90, 44);
    lv_obj_set_style_bg_color(btn_set, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(btn_set, 8, 0);
    lbl = lv_label_create(btn_set);
    lv_label_set_text(lbl, LV_SYMBOL_LIST);
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn_set, nav_settings_cb, LV_EVENT_CLICKED, NULL);

    /* Register data model callback */
    data_model_register_callback(on_data_update_dashboard);
}

/* -------------------------------------------------------------------------- */
/* Data Update Callback                                                        */
/* -------------------------------------------------------------------------- */
static void on_data_update_dashboard(const solar_data_t *data)
{
    if (!lvgl_lock(50)) return;

    char buf[32];

    /* Solar */
    snprintf(buf, sizeof(buf), "%.0f W", data->solar_w);
    lv_label_set_text(s_lbl_solar_val, buf);

    /* Battery */
    snprintf(buf, sizeof(buf), "%.0f%%", data->battery_soc);
    lv_label_set_text(s_lbl_batt_val, buf);

    /* Grid */
    snprintf(buf, sizeof(buf), "%.0f W", data->meter_w);
    lv_label_set_text(s_lbl_grid_val, buf);
    lv_obj_set_style_text_color(s_lbl_grid_val,
        data->meter_w > 0 ? UI_COLOR_GRID_IMP : UI_COLOR_GRID_EXP, 0);

    /* Load */
    snprintf(buf, sizeof(buf), "%.0f W", data->load_w);
    lv_label_set_text(s_lbl_load_val, buf);

    /* PV channels */
    snprintf(buf, sizeof(buf), "PV1: %.0fW", data->pv1_w);
    lv_label_set_text(s_lbl_pv1, buf);
    snprintf(buf, sizeof(buf), "PV2: %.0fW", data->pv2_w);
    lv_label_set_text(s_lbl_pv2, buf);
    snprintf(buf, sizeof(buf), "MI: %.0fW", data->mi_w);
    lv_label_set_text(s_lbl_mi, buf);

    /* Energy */
    snprintf(buf, sizeof(buf), LV_SYMBOL_IMAGE " %.1f kWh", data->solar_kwh);
    lv_label_set_text(s_lbl_solar_kwh, buf);
    snprintf(buf, sizeof(buf), LV_SYMBOL_DOWNLOAD " %.1f kWh", data->import_kwh);
    lv_label_set_text(s_lbl_import_kwh, buf);
    snprintf(buf, sizeof(buf), LV_SYMBOL_UPLOAD " %.1f kWh", data->export_kwh);
    lv_label_set_text(s_lbl_export_kwh, buf);

    /* Status bar */
    if (data->connected) {
        snprintf(buf, sizeof(buf), LV_SYMBOL_WIFI " %s", wifi_manager_get_ip());
        lv_label_set_text(s_lbl_status, buf);
        lv_obj_set_style_text_color(s_lbl_status, UI_COLOR_GREEN, 0);
    } else {
        lv_label_set_text(s_lbl_status, LV_SYMBOL_WIFI " Disconnected");
        lv_obj_set_style_text_color(s_lbl_status, UI_COLOR_RED, 0);
    }

    /* Auto mode indicator */
    lv_label_set_text(s_lbl_auto, data->auto_mode ? "AUTO" : "MANUAL");
    lv_obj_set_style_text_color(s_lbl_auto,
        data->auto_mode ? UI_COLOR_GREEN : UI_COLOR_YELLOW, 0);

    lvgl_unlock();
}

void ui_dashboard_show(void)
{
    lv_screen_load(s_screen);
}

void ui_dashboard_update(void)
{
    const solar_data_t *data = data_model_get();
    on_data_update_dashboard(data);
}
