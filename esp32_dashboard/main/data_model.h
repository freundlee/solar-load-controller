/*
 * Data Model - Central data store for solar system state
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    /* Solar system */
    float solar_w;
    float battery_soc;
    float battery_w;
    float output_w;
    float load_w;
    /* Per channel */
    float pv1_w;
    float pv2_w;
    float mi_w;
    /* Grid meter */
    float meter_w;
    bool meter_ok;
    /* Strategy */
    bool auto_mode;
    char state[16];
    float avg30;
    float avg60;
    float baseline_w;
    /* Energy today */
    float solar_kwh;
    float pv1_kwh;
    float pv2_kwh;
    float mi_kwh;
    float charge_kwh;
    float discharge_kwh;
    float import_kwh;
    float export_kwh;
    /* Timestamp */
    char timestamp[32];
    /* Connection state */
    bool connected;
    uint32_t last_update_ms;
} solar_data_t;

typedef void (*data_update_cb_t)(const solar_data_t *data);

void data_model_init(void);
const solar_data_t *data_model_get(void);
void data_model_update(const solar_data_t *new_data);
void data_model_register_callback(data_update_cb_t cb);
