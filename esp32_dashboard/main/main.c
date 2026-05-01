/*
 * Solar Dashboard for ESP32-P4
 * Main application entry - initializes hardware BSP, Wi-Fi, and UI
 */

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "esp_psram.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_mipi_dsi.h"
#include "esp_lcd_st7701.h"
#include "esp_lcd_touch_gt911.h"
#include "esp_ldo_regulator.h"
#include "driver/ledc.h"
#include "driver/i2c_master.h"
#include "lvgl.h"

#include "data_model.h"
#include "api_client.h"
#include "wifi_manager.h"
#include "ui/ui_dashboard.h"
#include "ui/ui_control.h"
#include "ui/ui_energy.h"
#include "ui/ui_settings.h"

static const char *TAG = "solar_dash";

/* Display parameters (ST7701 480x800) */
#define LCD_H_RES           480
#define LCD_V_RES           800
#define LCD_BIT_PER_PIXEL   16
#define LCD_BL_GPIO         23
#define LCD_DSI_LANE_NUM    2
#define LCD_DSI_LANE_BITRATE_MBPS  500

/* Touch I2C */
#define TOUCH_I2C_PORT      I2C_NUM_0
#define TOUCH_I2C_SDA       7
#define TOUCH_I2C_SCL       8
#define TOUCH_I2C_FREQ      400000
#define TOUCH_RST_GPIO      -1
#define TOUCH_INT_GPIO      -1

/* LVGL */
#define LVGL_TASK_STACK_SIZE    (8 * 1024)
#define LVGL_TASK_PRIORITY      5
#define LVGL_TICK_MS            2
#define LVGL_BUF_LINES          50

static lv_display_t *s_display = NULL;
static lv_indev_t *s_touch_indev = NULL;
static esp_lcd_touch_handle_t s_touch_handle = NULL;
static SemaphoreHandle_t s_lvgl_mutex = NULL;

/* -------------------------------------------------------------------------- */
/* Backlight                                                                   */
/* -------------------------------------------------------------------------- */
static void backlight_init(void)
{
    ledc_timer_config_t timer_cfg = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&timer_cfg);

    ledc_channel_config_t ch_cfg = {
        .gpio_num = LCD_BL_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0,
    };
    ledc_channel_config(&ch_cfg);
}

static void backlight_set(uint8_t percent)
{
    uint32_t duty = (1023 * percent) / 100;
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}

/* -------------------------------------------------------------------------- */
/* MIPI-DSI Display (ST7701)                                                  */
/* -------------------------------------------------------------------------- */
static esp_lcd_panel_handle_t s_panel = NULL;

static void display_init(void)
{
    ESP_LOGI(TAG, "Initializing MIPI-DSI display (ST7701 %dx%d)", LCD_H_RES, LCD_V_RES);

    /* MIPI DSI bus */
    esp_lcd_dsi_bus_handle_t dsi_bus = NULL;
    esp_lcd_dsi_bus_config_t bus_cfg = {
        .bus_id = 0,
        .num_data_lanes = LCD_DSI_LANE_NUM,
        .phy_clk_src = MIPI_DSI_PHY_CLK_SRC_DEFAULT,
        .lane_bit_rate_mbps = LCD_DSI_LANE_BITRATE_MBPS,
    };
    ESP_ERROR_CHECK(esp_lcd_new_dsi_bus(&bus_cfg, &dsi_bus));

    /* DPI panel (video mode) */
    esp_lcd_dpi_panel_config_t dpi_cfg = {
        .dpi_clk_src = MIPI_DSI_DPI_CLK_SRC_DEFAULT,
        .dpi_clock_freq_mhz = 52,
        .virtual_channel = 0,
        .pixel_format = LCD_COLOR_PIXEL_FORMAT_RGB565,
        .video_timing = {
            .h_size = LCD_H_RES,
            .v_size = LCD_V_RES,
            .hsync_back_porch = 30,
            .hsync_pulse_width = 4,
            .hsync_front_porch = 30,
            .vsync_back_porch = 16,
            .vsync_pulse_width = 2,
            .vsync_front_porch = 16,
        },
    };

    /* ST7701 panel config */
    st7701_vendor_config_t vendor_cfg = {
        .mipi_config = {
            .dsi_bus = dsi_bus,
            .dpi_config = &dpi_cfg,
            .lane_num = LCD_DSI_LANE_NUM,
        },
    };

    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = -1,
        .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB,
        .bits_per_pixel = LCD_BIT_PER_PIXEL,
        .vendor_config = &vendor_cfg,
    };

    ESP_ERROR_CHECK(esp_lcd_new_panel_st7701(NULL, &panel_cfg, &s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_init(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(s_panel, true));

    ESP_LOGI(TAG, "Display initialized");
}

/* -------------------------------------------------------------------------- */
/* Touch (GT911)                                                               */
/* -------------------------------------------------------------------------- */
static i2c_master_bus_handle_t s_i2c_bus = NULL;

static void touch_init(void)
{
    ESP_LOGI(TAG, "Initializing GT911 touch");

    /* I2C master bus */
    i2c_master_bus_config_t i2c_bus_cfg = {
        .i2c_port = TOUCH_I2C_PORT,
        .sda_io_num = TOUCH_I2C_SDA,
        .scl_io_num = TOUCH_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_cfg, &s_i2c_bus));

    /* Touch panel config */
    esp_lcd_panel_io_handle_t tp_io = NULL;
    esp_lcd_panel_io_i2c_config_t tp_io_cfg = ESP_LCD_TOUCH_IO_I2C_GT911_CONFIG();

    esp_lcd_panel_io_i2c_config_t io_cfg = tp_io_cfg;
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(s_i2c_bus, &io_cfg, &tp_io));

    esp_lcd_touch_config_t tp_cfg = {
        .x_max = LCD_H_RES,
        .y_max = LCD_V_RES,
        .rst_gpio_num = TOUCH_RST_GPIO,
        .int_gpio_num = TOUCH_INT_GPIO,
    };

    ESP_ERROR_CHECK(esp_lcd_touch_new_i2c_gt911(tp_io, &tp_cfg, &s_touch_handle));
    ESP_LOGI(TAG, "Touch initialized");
}

/* -------------------------------------------------------------------------- */
/* LVGL Integration                                                            */
/* -------------------------------------------------------------------------- */
static void lvgl_flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map)
{
    esp_lcd_panel_draw_bitmap(s_panel,
        area->x1, area->y1, area->x2 + 1, area->y2 + 1, px_map);
    lv_display_flush_ready(disp);
}

static void lvgl_touch_read_cb(lv_indev_t *indev, lv_indev_data_t *data)
{
    esp_lcd_touch_read_data(s_touch_handle);
    uint16_t x[1], y[1];
    uint16_t strength[1];
    uint8_t count = 0;
    bool pressed = esp_lcd_touch_get_coordinates(s_touch_handle, x, y, strength, &count, 1);
    if (pressed && count > 0) {
        data->point.x = x[0];
        data->point.y = y[0];
        data->state = LV_INDEV_STATE_PRESSED;
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
    }
}

static void lvgl_tick_cb(void *arg)
{
    lv_tick_inc(LVGL_TICK_MS);
}

static void lvgl_task(void *arg)
{
    ESP_LOGI(TAG, "LVGL task started");
    while (1) {
        if (xSemaphoreTake(s_lvgl_mutex, pdMS_TO_TICKS(50))) {
            uint32_t ms = lv_timer_handler();
            xSemaphoreGive(s_lvgl_mutex);
            vTaskDelay(pdMS_TO_TICKS(ms < 5 ? 5 : ms));
        } else {
            vTaskDelay(pdMS_TO_TICKS(5));
        }
    }
}

static void lvgl_init(void)
{
    ESP_LOGI(TAG, "Initializing LVGL");
    lv_init();

    s_lvgl_mutex = xSemaphoreCreateMutex();

    /* Display driver */
    size_t buf_size = LCD_H_RES * LVGL_BUF_LINES * sizeof(lv_color16_t);
    void *buf1 = heap_caps_malloc(buf_size, MALLOC_CAP_SPIRAM);
    void *buf2 = heap_caps_malloc(buf_size, MALLOC_CAP_SPIRAM);

    s_display = lv_display_create(LCD_H_RES, LCD_V_RES);
    lv_display_set_flush_cb(s_display, lvgl_flush_cb);
    lv_display_set_buffers(s_display, buf1, buf2, buf_size, LV_DISPLAY_RENDER_MODE_PARTIAL);

    /* Touch input */
    s_touch_indev = lv_indev_create();
    lv_indev_set_type(s_touch_indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(s_touch_indev, lvgl_touch_read_cb);

    /* Tick timer */
    const esp_timer_create_args_t tick_args = {
        .callback = lvgl_tick_cb,
        .name = "lvgl_tick",
    };
    esp_timer_handle_t tick_timer;
    ESP_ERROR_CHECK(esp_timer_create(&tick_args, &tick_timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(tick_timer, LVGL_TICK_MS * 1000));

    /* LVGL rendering task */
    xTaskCreatePinnedToCore(lvgl_task, "lvgl", LVGL_TASK_STACK_SIZE, NULL,
                            LVGL_TASK_PRIORITY, NULL, 0);
}

/* -------------------------------------------------------------------------- */
/* Application Entry                                                           */
/* -------------------------------------------------------------------------- */
void app_main(void)
{
    ESP_LOGI(TAG, "Solar Dashboard v1.0.0 starting...");

    /* NVS init */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* Hardware init */
    backlight_init();
    display_init();
    touch_init();
    lvgl_init();
    backlight_set(90);

    /* Data model init */
    data_model_init();

    /* Create UI screens */
    if (xSemaphoreTake(s_lvgl_mutex, portMAX_DELAY)) {
        ui_dashboard_create();
        ui_control_create();
        ui_energy_create();
        ui_settings_create();
        ui_dashboard_show();  /* Start with dashboard */
        xSemaphoreGive(s_lvgl_mutex);
    }

    /* Wi-Fi connection */
    wifi_manager_init();
    wifi_manager_connect();

    /* Start API polling (after Wi-Fi) */
    api_client_init();
    api_client_start_polling();

    ESP_LOGI(TAG, "Solar Dashboard started successfully");
}

/* Public: take/give LVGL mutex for UI updates from other tasks */
bool lvgl_lock(uint32_t timeout_ms)
{
    return xSemaphoreTake(s_lvgl_mutex, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}

void lvgl_unlock(void)
{
    xSemaphoreGive(s_lvgl_mutex);
}
