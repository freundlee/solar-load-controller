# Solar Load Controller — Features

A smart-home energy controller that automatically manages an **Anker Solarbank 2 E1600 AC** home load (0–800 W) based on real-time **IOMeter** smart meter readings, with the goal of minimising grid electricity import.

## Core Features

### ⚡ Automatic Load Control
Reads the grid meter every 5 seconds and continuously adjusts the Solarbank home load (0–800 W in 10 W steps) to keep the grid import near zero. Prefers slight export over any import.

### 🎯 3-Layer Control Strategy
1. **Spike Detection** — Rolling 120 s window classifies grid spikes against appliance profiles (microwave vs oven), so short bursts don't trigger unnecessary adjustments.
2. **Load Adjustment** — `target_load = current_load + (meter_reading − grid_target)`, hysteresis-filtered.
3. **Cooldown** — 45 s pause between changes prevents oscillation; emergency threshold (500 W) overrides cooldown.

### 🔌 Pluggable Strategy Plugins
Multiple algorithms, switchable from the UI without restart:
- `proportional` — direct meter-based control
- `conservative` — safety buffers, minimises grid import
- `smoothing` — stability score for variable loads (AC, pumps)
- `battery_guard` — SOC-aware + time-of-day + weather-aware
- `predictive` — historical pattern-based pre-positioning

### 🏠 Configurable Appliance Profiles
Define power range, typical duration, and action (`ignore` / `observe` / `adjust`) for each appliance. Defaults include microwave, oven, kettle, induction cooktop, hair dryer, vacuum.

### 🎛️ Manual Control
Slider and quick-buttons to set load directly (0–800 W, 10 W steps). Auto/Manual mode toggle.

## Dashboard

### Operations Page (`/dashboard/`)
- Real-time metrics: solar, battery SOC, grid, load
- Per-channel PV details (PV1 / PV2 / microinverter) with daily energy
- Power-flow visualisation
- Live meter chart and 24 h load history
- Daily energy summary (production, import, export, cost saved)
- Balance and daily-energy charts with self-sufficiency %
- Smart-plug status (collapsible)
- IOMeter device status (signal, battery, meter number)
- Device schedule viewer (Smart Match / Time of Use / Manual modes)

### Admin Page (`/dashboard/admin`)
- Strategy configuration — all parameters editable from UI, no restart needed
- Active-strategy selector
- Appliance profile management (CRUD)
- IOMeter connection settings (LAN poll / remote push / ESP32 push)
- Weather location (city + coordinates)
- Display timezone

### Analytics
- 7-day weather forecast with PV generation estimate (Open-Meteo / WMO codes)
- **Forecast vs Actual** solar chart with navigation, MAE accuracy KPIs and over/under-estimate counts
- Monthly overview: indicators + 12-month stacked area trend
- Weekly balance chart

## Integrations

| Component | Purpose |
|-----------|---------|
| **Anker Solix Cloud API** | Async client (reverse-engineered) — read state, set load |
| **IOMeter** | LAN poll, remote push, or ESP32 push (3 modes) |
| **ESP32 bridge** | REST endpoints for meter push + compact dashboard payload |
| **OpenWeatherMap / Open-Meteo** | Solar-hours forecast and cloud cover |
| **SQLite** | Config, meter readings, load changes, profiles, forecast snapshots |

## REST API (selected)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/data` | Combined dashboard snapshot |
| POST | `/api/set-load` | Manual load `{"load": 400}` |
| POST | `/api/auto-mode?enabled=true` | Toggle auto mode |
| GET/POST | `/api/config` | Read/write strategy parameters |
| GET/POST/DELETE | `/api/profiles` | Appliance profiles |
| GET | `/api/load-history` | Load change log |
| GET | `/api/meter-history` | Recent meter readings |
| GET | `/api/daily-energy` | Daily energy summary |
| GET | `/api/weather` / `/weather/forecast-history` | Forecast data |
| POST | `/api/esp32/meter` | ESP32 push endpoint |
| GET | `/health` | Health check |

## Tech Stack
FastAPI · Dash 2.x + Plotly · Bootstrap 5 (Darkly) · SQLite · Python 3.12 · Docker

## Deployment
Single `docker compose up -d` on a local Mac mini / Raspberry Pi. Uses `network_mode: host` to reach the IOMeter on the LAN. Persistent volume for SQLite + auth cache.
