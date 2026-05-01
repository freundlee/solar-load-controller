/*
 * Wi-Fi Manager - Handles ESP-Hosted SDIO Wi-Fi via ESP32-C6
 */
#pragma once

#include "esp_err.h"
#include <stdbool.h>

esp_err_t wifi_manager_init(void);
esp_err_t wifi_manager_connect(void);
bool wifi_manager_is_connected(void);
const char *wifi_manager_get_ip(void);
