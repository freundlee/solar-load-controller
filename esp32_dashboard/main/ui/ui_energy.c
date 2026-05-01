/*
 * UI Energy - Daily energy statistics with bar-style indicators
 */

#include "ui_energy.h"
#include "ui_common.h"
#include "ui_dashboard.h"
#include "ui_control.h"
#include "ui_settings.h"
#include "data_model.h"
#include <stdio.h>

static lv_obj_t *s_screen = NULL;

/* Energy stat labels */
static lv_obj_t *s_lbl_solar_kwh = NULL;
static lv_obj_t *s_lbl_pv1_kwh = NULL;
static lv_obj_t *s_lbl_pv2_kwh = NULL;
static lv_obj_t *s_lbl_mi_kwh = NULL;
static lv_obj_t *s_lbl_charge_kwh = NULL;
static lv_obj_t *s_lbl_discharge_kwh = NULL;
static lv_obj_t *s_lbl_import_kwh = NULL;
static lv_obj_t *s_lbl_export_kwh = NULL;

/* Bars */
static lv_obj_t *s_bar_solar = NULL;
static lv_obj_t *s_bar_import = NULL;
static lv_obj_t *s_bar_export = NULL;

/* -------------------------------------------------------------------------- */
/* Navigation                                                                  */
/* -------------------------------------------------------------------------- */
static void nav_dashboard_cb(lv_event_t *e) { ui_dashboard_show(); }
static void nav_control_cb(lv_event_t *e) { ui_control_show(); }
static void nav_settings_cb(lv_event_t *e) { ui_settings_show(); }

/* -------------------------------------------------------------------------- */
/* Helper: energy row with bar                                                 */
/* -------------------------------------------------------------------------- */
static lv_obj_t *create_energy_row(lv_obj_t *parent, const char *label,
                                    lv_color_t color, lv_obj_t **val_lbl,
                                    lv_obj_t **bar)
{
    lv_obj_t *row = lv_obj_create(parent);
    lv_obj_set_size(row, LV_PCT(100), 50);
    lv_obj_set_style_bg_opa(row, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(row, 0, 0);
    lv_obj_set_style_pad_all(row, 4, 0);
    lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *lbl = lv_label_create(row);
    lv_label_set_text(lbl, label);
    lv_obj_set_style_text_font(lbl, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(lbl, UI_COLOR_TEXT_DIM, 0);
    lv_obj_align(lbl, LV_ALIGN_TOP_LEFT, 0, 0);

    *val_lbl = lv_label_create(row);
    lv_label_set_text(*val_lbl, "0.0 kWh");
    lv_obj_set_style_text_font(*val_lbl, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(*val_lbl, color, 0);
    lv_obj_align(*val_lbl, LV_ALIGN_TOP_RIGHT, 0, 0);

    if (bar) {
        *bar = lv_bar_create(row);
        lv_obj_set_size(*bar, LV_PCT(100), 8);
        lv_obj_align(*bar, LV_ALIGN_BOTTOM_MID, 0, 0);
        lv_bar_set_range(*bar, 0, 100);
        lv_bar_set_value(*bar, 0, LV_ANIM_OFF);
        lv_obj_set_style_bg_color(*bar, UI_COLOR_PRIMARY, LV_PART_MAIN);
        lv_obj_set_style_bg_color(*bar, color, LV_PART_INDICATOR);
        lv_obj_set_style_radius(*bar, 4, 0);
        lv_obj_set_style_radius(*bar, 4, LV_PART_INDICATOR);
    }

    return row;
}

/* -------------------------------------------------------------------------- */
/* Data update callback                                                        */
/* -------------------------------------------------------------------------- */
static void on_data_update(const solar_data_t *data)
{
    if (!lvgl_lock(50)) return;

    char buf[32];
    float max_kwh = data->solar_kwh > 0.1f ? data->solar_kwh : 10.0f;

    snprintf(buf, sizeof(buf), "%.1f kWh", data->solar_kwh);
    lv_label_set_text(s_lbl_solar_kwh, buf);
    lv_bar_set_value(s_bar_solar, (int)(data->solar_kwh / max_kwh * 100), LV_ANIM_ON);

    snprintf(buf, sizeof(buf), "%.1f kWh", data->pv1_kwh);
    lv_label_set_text(s_lbl_pv1_kwh, buf);

    snprintf(buf, sizeof(buf), "%.1f kWh", data->pv2_kwh);
    lv_label_set_text(s_lbl_pv2_kwh, buf);

    snprintf(buf, sizeof(buf), "%.1f kWh", data->mi_kwh);
    lv_label_set_text(s_lbl_mi_kwh, buf);

    snprintf(buf, sizeof(buf), "%.1f kWh", data->charge_kwh);
    lv_label_set_text(s_lbl_charge_kwh, buf);

    snprintf(buf, sizeof(buf), "%.1f kWh", data->discharge_kwh);
    lv_label_set_text(s_lbl_discharge_kwh, buf);

    snprintf(buf, sizeof(buf), "%.1f kWh", data->import_kwh);
    lv_label_set_text(s_lbl_import_kwh, buf);
    lv_bar_set_value(s_bar_import, (int)(data->import_kwh / max_kwh * 100), LV_ANIM_ON);

    snprintf(buf, sizeof(buf), "%.1f kWh", data->export_kwh);
    lv_label_set_text(s_lbl_export_kwh, buf);
    lv_bar_set_value(s_bar_export, (int)(data->export_kwh / max_kwh * 100), LV_ANIM_ON);

    lvgl_unlock();
}

/* -------------------------------------------------------------------------- */
/* Create                                                                      */
/* -------------------------------------------------------------------------- */
void ui_energy_create(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, UI_COLOR_BG, 0);
    lv_obj_set_flex_flow(s_screen, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(s_screen, 16, 0);
    lv_obj_set_style_pad_gap(s_screen, 4, 0);
    lv_obj_clear_flag(s_screen, LV_OBJ_FLAG_SCROLLABLE);

    /* Title */
    lv_obj_t *title = lv_label_create(s_screen);
    lv_label_set_text(title, "Today's Energy");
    lv_obj_set_style_text_font(title, UI_FONT_MEDIUM, 0);
    lv_obj_set_style_text_color(title, UI_COLOR_TEXT, 0);

    /* Content card */
    lv_obj_t *card = lv_obj_create(s_screen);
    lv_obj_set_size(card, LV_PCT(100), LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(card, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(card, 10, 0);
    lv_obj_set_style_pad_all(card, 12, 0);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(card, 2, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    create_energy_row(card, "Solar Total", UI_COLOR_SOLAR, &s_lbl_solar_kwh, &s_bar_solar);
    create_energy_row(card, "PV1", UI_COLOR_SOLAR, &s_lbl_pv1_kwh, NULL);
    create_energy_row(card, "PV2", UI_COLOR_SOLAR, &s_lbl_pv2_kwh, NULL);
    create_energy_row(card, "Micro-Inverter", UI_COLOR_TEXT_DIM, &s_lbl_mi_kwh, NULL);
    create_energy_row(card, "Battery Charge", UI_COLOR_BATTERY, &s_lbl_charge_kwh, NULL);
    create_energy_row(card, "Battery Discharge", UI_COLOR_YELLOW, &s_lbl_discharge_kwh, NULL);
    create_energy_row(card, "Grid Import", UI_COLOR_GRID_IMP, &s_lbl_import_kwh, &s_bar_import);
    create_energy_row(card, "Grid Export", UI_COLOR_GRID_EXP, &s_lbl_export_kwh, &s_bar_export);

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

    lv_obj_t *btn, *lbl;

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
    lv_obj_set_style_bg_color(btn, UI_COLOR_ACCENT, 0);
    lv_obj_set_style_radius(btn, 8, 0);
    lbl = lv_label_create(btn);
    lv_label_set_text(lbl, LV_SYMBOL_BAR_CHART);
    lv_obj_center(lbl);

    btn = lv_btn_create(nav);
    lv_obj_set_size(btn, 90, 44);
    lv_obj_set_style_bg_color(btn, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(btn, 8, 0);
    lbl = lv_label_create(btn);
    lv_label_set_text(lbl, LV_SYMBOL_LIST);
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn, nav_settings_cb, LV_EVENT_CLICKED, NULL);

    /* Register callback */
    data_model_register_callback(on_data_update);
}

void ui_energy_show(void)
{
    lv_screen_load(s_screen);
}
