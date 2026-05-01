# Solar Dashboard for ESP32-P4
# Based on ESP_Brookesia Phone system with ST7701 display + GT911 touch

cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS
    "components"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(solar_dashboard)
