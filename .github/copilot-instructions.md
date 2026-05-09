# Solar Load Controller — Copilot Instructions

## Project Overview
A smart home energy controller that automatically manages an **Anker Solarbank 2 E1600 AC** home load (0–800 W) based on real-time **IOMeter** smart meter readings, minimising grid electricity import. A Dash dashboard provides live monitoring, strategy configuration, and energy history.

## Tech Stack
- **Backend**: FastAPI + uvicorn (async)
- **Dashboard**: Dash 2.x + Plotly + dash-bootstrap-components (Bootstrap 5 Darkly theme)
- **Database**: SQLite (no ORM) — helpers in `app/database.py`
- **Anker API**: Custom async client in `app/api/` (reverse-engineered Solix cloud API)
- **ESP32 bridge**: REST endpoints in `app/routes/esp32_routes.py`
- **Python**: 3.12

## Project Structure
```
app/
  main.py              ← FastAPI app factory + lifespan startup/shutdown
  config.py            ← Dataclass config + env loading (AnkerConfig, IOMeterConfig, StrategyDefaults)
  database.py          ← SQLite helpers (get_config, set_config, insert_reading, …)
  api/                 ← Anker Solix cloud API async client
    api.py / apibase.py / session.py / hesapi.py
    poller.py / energy.py / schedule.py
    authcache/         ← Persisted auth tokens (gitignored in prod)
  routes/
    api_routes.py      ← Main REST API (/api/*)
    esp32_routes.py    ← ESP32 push API (/api/esp32/*)
  services/
    strategy_engine.py ← Main async control loop
    strategies.py      ← Strategy plugins (BaseStrategy + concrete strategies)
    anker_service.py   ← Wraps Anker API, caches state
    iometer_service.py ← Polls IOMeter via LAN
    weather_service.py ← OpenWeatherMap integration
  dashboard/
    app.py             ← Dash app factory (mounted as WSGI middleware)
    layouts.py         ← All UI component layouts
    callbacks.py       ← All Dash callbacks (use _api_get / _api_post helpers)
```

## Key Patterns

### Database access — always use helpers
```python
from app import database as db
value = db.get_config("key", default)
db.set_config("key", value)
db.insert_reading(ts, grid_w, solar_w, battery_w, load_w, soc)
```

### Adding a new Strategy
1. Extend `BaseStrategy` in `app/services/strategies.py`
2. Implement `decide(ctx: StrategyContext) -> StrategyDecision`
3. Use `self.snap_load(watts)` to clamp & snap to 10 W steps
4. Register in the `STRATEGIES` dict at the bottom of the file

### Service injection in API routes
```python
# routes/api_routes.py
iometer, anker, strategy = _get_services(request)  # from request.app.state
```

### Dash callbacks
All callbacks live inside `register_callbacks(app)` in `app/dashboard/callbacks.py`.
Use `_api_get(path)` / `_api_post(path, data)` helpers — never call services directly.

### Load control constraints
- Range: **0–800 W** (German Balkonkraftwerk regulation)
- Step size: **10 W** (Anker SB2 hardware resolution)
- Always use `BaseStrategy.snap_load(w)` before sending to Anker
- Respect `cooldown_period_s` except when `|grid| > emergency_threshold_w`

## Environment Variables
Copy `.env.example` → `.env` and fill in:

| Variable | Description |
|---|---|
| `ANKER_EMAIL` | Anker account e-mail |
| `ANKER_PASSWORD` | Anker account password |
| `ANKER_COUNTRY` | Country code (default: `DE`) |
| `IOMETER_HOST` | LAN IP of the IOMeter (default: `192.168.178.96`) |
| `ESP32_API_KEY` | Shared secret for ESP32 bridge auth |

## Running Locally
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in credentials
python run.py          # listens on :8000 by default
```

## Docker
```bash
docker compose up -d --build
```
Data persists in the `solar-data` Docker volume (mounted at `/app/data`).

## Important Notes
- All internal timestamps are **UTC**; convert to local only for display
- The Anker API is **fully async** — never call sync code from an async context
- SQLite `config` table values can be changed at runtime from the dashboard without restarting
- ESP32 routes require `X-API-Key` header or `?key=` query param
- `app/api/authcache/*.json` stores session tokens — do not commit real credentials
