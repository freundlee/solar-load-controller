/*
 * UI Control - Load control slider, auto mode toggle, strategy selection
 */

#include "ui_control.h"
#include "ui_common.h"
#include "ui_dashboard.h"
#include "ui_energy.h"
#include "ui_settings.h"
#include "data_model.h"
#include "api_client.h"
#include <stdio.h>

static lv_obj_t *s_screen = NULL;
static lv_obj_t *s_slider = NULL;
static lv_obj_t *s_lbl_load_val = NULL;
static lv_obj_t *s_sw_auto = NULL;
static lv_obj_t *s_lbl_state = NULL;
static lv_obj_t *s_lbl_avg30 = NULL;
static lv_obj_t *s_lbl_avg60 = NULL;

/* -------------------------------------------------------------------------- */
/* Callbacks                                                                   */
/* -------------------------------------------------------------------------- */
static void slider_cb(lv_event_t *e)
{
    int val = lv_slider_get_value(s_slider);
    char buf[16];
    snprintf(buf, sizeof(buf), "%d W", val);
    lv_label_set_text(s_lbl_load_val, buf);
}

static void slider_release_cb(lv_event_t *e)
{
    int val = lv_slider_get_value(s_slider);
    api_client_set_load(val);
}

static void auto_switch_cb(lv_event_t *e)
{
    bool checked = lv_obj_has_state(s_sw_auto, LV_STATE_CHECKED);
    api_client_set_auto_mode(checked);
}

static void nav_dashboard_cb(lv_event_t *e) { ui_dashboard_show(); }
static void nav_energy_cb(lv_event_t *e) { ui_energy_show(); }
static void nav_settings_cb(lv_event_t *e) { ui_settings_show(); }

/* -------------------------------------------------------------------------- */
/* Data update                                                                 */
/* -------------------------------------------------------------------------- */
static void on_data_update(const solar_data_t *data)
{
    if (!lvgl_lock(50)) return;

    char buf[32];

    /* Update slider position if in auto mode */
    if (data->auto_mode) {
        lv_slider_set_value(s_slider, (int)data->output_w, LV_ANIM_ON);
        snprintf(buf, sizeof(buf), "%d W", (int)data->output_w);
        lv_label_set_text(s_lbl_load_val, buf);
    }

    /* Auto switch */
    if (data->auto_mode) {
        lv_obj_add_state(s_sw_auto, LV_STATE_CHECKED);
    } else {
        lv_obj_remove_state(s_sw_auto, LV_STATE_CHECKED);
    }

    /* State */
    lv_label_set_text(s_lbl_state, data->state);

    /* Averages */
    snprintf(buf, sizeof(buf), "30s avg: %.0f W", data->avg30);
    lv_label_set_text(s_lbl_avg30, buf);
    snprintf(buf, sizeof(buf), "60s avg: %.0f W", data->avg60);
    lv_label_set_text(s_lbl_avg60, buf);

    lvgl_unlock();
}

/* -------------------------------------------------------------------------- */
/* Create Control Screen                                                       */
/* -------------------------------------------------------------------------- */
void ui_control_create(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, UI_COLOR_BG, 0);
    lv_obj_set_flex_flow(s_screen, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(s_screen, 16, 0);
    lv_obj_set_style_pad_gap(s_screen, 16, 0);
    lv_obj_clear_flag(s_screen, LV_OBJ_FLAG_SCROLLABLE);

    /* Title */
    lv_obj_t *title = lv_label_create(s_screen);
    lv_label_set_text(title, "Load Control");
    lv_obj_set_style_text_font(title, UI_FONT_MEDIUM, 0);
    lv_obj_set_style_text_color(title, UI_COLOR_TEXT, 0);

    /* ---- Auto Mode Toggle ---- */
    lv_obj_t *auto_row = lv_obj_create(s_screen);
    lv_obj_set_size(auto_row, LV_PCT(100), 60);
    lv_obj_set_style_bg_color(auto_row, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(auto_row, 10, 0);
    lv_obj_set_style_pad_hor(auto_row, 16, 0);
    lv_obj_clear_flag(auto_row, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *auto_lbl = lv_label_create(auto_row);
    lv_label_set_text(auto_lbl, "Auto Mode");
    lv_obj_set_style_text_font(auto_lbl, UI_FONT_MEDIUM, 0);
    lv_obj_set_style_text_color(auto_lbl, UI_COLOR_TEXT, 0);
    lv_obj_align(auto_lbl, LV_ALIGN_LEFT_MID, 0, 0);

    s_sw_auto = lv_switch_create(auto_row);
    lv_obj_set_size(s_sw_auto, 56, 28);
    lv_obj_align(s_sw_auto, LV_ALIGN_RIGHT_MID, 0, 0);
    lv_obj_set_style_bg_color(s_sw_auto, UI_COLOR_GREEN, LV_PART_INDICATOR | LV_STATE_CHECKED);
    lv_obj_add_event_cb(s_sw_auto, auto_switch_cb, LV_EVENT_VALUE_CHANGED, NULL);

    /* ---- Load Slider ---- */
    lv_obj_t *slider_card = lv_obj_create(s_screen);
    lv_obj_set_size(slider_card, LV_PCT(100), 160);
    lv_obj_set_style_bg_color(slider_card, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(slider_card, 10, 0);
    lv_obj_set_style_pad_all(slider_card, 16, 0);
    lv_obj_set_flex_flow(slider_card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(slider_card, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_gap(slider_card, 12, 0);
    lv_obj_clear_flag(slider_card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slider_title = lv_label_create(slider_card);
    lv_label_set_text(slider_title, "Output Power");
    lv_obj_set_style_text_font(slider_title, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(slider_title, UI_COLOR_TEXT_DIM, 0);

    s_lbl_load_val = lv_label_create(slider_card);
    lv_label_set_text(s_lbl_load_val, "0 W");
    lv_obj_set_style_text_font(s_lbl_load_val, UI_FONT_LARGE, 0);
    lv_obj_set_style_text_color(s_lbl_load_val, UI_COLOR_TEXT, 0);

    s_slider = lv_slider_create(slider_card);
    lv_obj_set_width(s_slider, LV_PCT(90));
    lv_slider_set_range(s_slider, 0, 800);
    lv_slider_set_value(s_slider, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(s_slider, UI_COLOR_PRIMARY, LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_slider, UI_COLOR_ACCENT, LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(s_slider, UI_COLOR_ACCENT, LV_PART_KNOB);
    lv_obj_add_event_cb(s_slider, slider_cb, LV_EVENT_VALUE_CHANGED, NULL);
    lv_obj_add_event_cb(s_slider, slider_release_cb, LV_EVENT_RELEASED, NULL);

    /* ---- State Info ---- */
    lv_obj_t *state_card = lv_obj_create(s_screen);
    lv_obj_set_size(state_card, LV_PCT(100), 120);
    lv_obj_set_style_bg_color(state_card, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(state_card, 10, 0);
    lv_obj_set_style_pad_all(state_card, 16, 0);
    lv_obj_set_flex_flow(state_card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(state_card, 8, 0);
    lv_obj_clear_flag(state_card, LV_OBJ_FLAG_SCROLLABLE);

    s_lbl_state = lv_label_create(state_card);
    lv_label_set_text(s_lbl_state, "State: ---");
    lv_obj_set_style_text_font(s_lbl_state, UI_FONT_MEDIUM, 0);
    lv_obj_set_style_text_color(s_lbl_state, UI_COLOR_TEXT, 0);

    s_lbl_avg30 = lv_label_create(state_card);
    lv_label_set_text(s_lbl_avg30, "30s avg: --- W");
    lv_obj_set_style_text_font(s_lbl_avg30, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_avg30, UI_COLOR_TEXT_DIM, 0);

    s_lbl_avg60 = lv_label_create(state_card);
    lv_label_set_text(s_lbl_avg60, "60s avg: --- W");
    lv_obj_set_style_text_font(s_lbl_avg60, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(s_lbl_avg60, UI_COLOR_TEXT_DIM, 0);

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
    lv_obj_set_style_bg_color(btn, UI_COLOR_ACCENT, 0);
    lv_obj_set_style_radius(btn, 8, 0);
    lbl = lv_label_create(btn);
    lv_label_set_text(lbl, LV_SYMBOL_SETTINGS);
    lv_obj_center(lbl);

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
    lv_obj_set_style_bg_color(btn, UI_COLOR_CARD, 0);
    lv_obj_set_style_radius(btn, 8, 0);
    lbl = lv_label_create(btn);
    lv_label_set_text(lbl, LV_SYMBOL_LIST);
    lv_obj_center(lbl);
    lv_obj_add_event_cb(btn, nav_settings_cb, LV_EVENT_CLICKED, NULL);

    /* Register data callback */
    data_model_register_callback(on_data_update);
}

void ui_control_show(void)
{
    lv_screen_load(s_screen);
}
