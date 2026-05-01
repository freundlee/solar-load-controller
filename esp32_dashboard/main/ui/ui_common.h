/*
 * UI Common - Shared definitions for all UI screens
 */
#pragma once

#include "lvgl.h"

/* Colors */
#define UI_COLOR_BG         lv_color_hex(0x1A1A2E)
#define UI_COLOR_CARD       lv_color_hex(0x16213E)
#define UI_COLOR_PRIMARY    lv_color_hex(0x0F3460)
#define UI_COLOR_ACCENT     lv_color_hex(0xE94560)
#define UI_COLOR_GREEN      lv_color_hex(0x00C853)
#define UI_COLOR_RED        lv_color_hex(0xFF1744)
#define UI_COLOR_YELLOW     lv_color_hex(0xFFD600)
#define UI_COLOR_BLUE       lv_color_hex(0x2979FF)
#define UI_COLOR_TEXT       lv_color_hex(0xE0E0E0)
#define UI_COLOR_TEXT_DIM   lv_color_hex(0x9E9E9E)
#define UI_COLOR_SOLAR      lv_color_hex(0xFFC107)
#define UI_COLOR_BATTERY    lv_color_hex(0x4CAF50)
#define UI_COLOR_GRID_IMP   lv_color_hex(0xF44336)
#define UI_COLOR_GRID_EXP   lv_color_hex(0x2196F3)

/* Font sizes mapped to available LV fonts */
#define UI_FONT_LARGE       &lv_font_montserrat_28
#define UI_FONT_MEDIUM      &lv_font_montserrat_18
#define UI_FONT_SMALL       &lv_font_montserrat_14
#define UI_FONT_TINY        &lv_font_montserrat_12

/* Screen dimensions */
#define UI_SCREEN_W         480
#define UI_SCREEN_H         800

/* Navigation bar height */
#define UI_NAV_HEIGHT       60

/* External LVGL lock (defined in main.c) */
extern bool lvgl_lock(uint32_t timeout_ms);
extern void lvgl_unlock(void);
