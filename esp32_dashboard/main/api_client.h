/*
 * API Client - HTTP communication with solar_load_controller
 */
#pragma once

#include "esp_err.h"

esp_err_t api_client_init(void);
esp_err_t api_client_start_polling(void);
esp_err_t api_client_stop_polling(void);
esp_err_t api_client_set_load(int watts);
esp_err_t api_client_set_auto_mode(bool enabled);
esp_err_t api_client_set_config(const char *key, const char *value);
esp_err_t api_client_fetch_dashboard(void);
esp_err_t api_client_reconfigure(void);
