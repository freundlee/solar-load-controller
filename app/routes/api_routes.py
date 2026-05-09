"""FastAPI REST API routes."""

import logging
import zoneinfo
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import database as db
from app.services.strategies import list_strategies

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SetLoadRequest(BaseModel):
    load: int = Field(ge=0, le=800, description="Load in watts (0-800, multiple of 10)")

class ConfigUpdateRequest(BaseModel):
    key: str
    value: float | int | bool | str

class ApplianceProfileRequest(BaseModel):
    id: int | None = None
    name: str
    power_min_w: float
    power_max_w: float
    typical_duration_s: int | None = None
    max_duration_s: int | None = None
    action: str = "observe"


# ---------------------------------------------------------------------------
# Dependency: services are injected from main.py via app.state
# ---------------------------------------------------------------------------

def _get_services(request: Request):
    """Extract services from the FastAPI app state."""
    return (
        request.app.state.iometer,
        request.app.state.anker,
        request.app.state.strategy,
    )


# ---------------------------------------------------------------------------
# Dashboard data (combines all sources)
# ---------------------------------------------------------------------------

@router.get("/data")
async def get_dashboard_data(request: Request):
    """Combined snapshot of all live data for the dashboard."""
    iometer, anker, strategy = _get_services(request)

    meter_reading = iometer.latest
    meter_power = meter_reading.power_w if meter_reading else None
    meter_consumption_wh = meter_reading.total_consumption_wh if meter_reading else None

    return {
        "anker": anker.get_dashboard_data(),
        "meter": {
            "power_w": meter_power,
            "total_consumption_wh": meter_consumption_wh,
            "connected": iometer.status.connected,
            "bridge_rssi": iometer.status.bridge_rssi,
            "battery_level": iometer.status.battery_level,
            "meter_number": iometer.status.meter_number,
        },
        "strategy": strategy.get_status(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status")
async def get_status(request: Request):
    iometer, anker, strategy = _get_services(request)
    return {
        "status": "running",
        "anker_initialized": anker._initialized,
        "iometer_connected": iometer.status.connected,
        "auto_mode": strategy.auto_enabled,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Manual load control
# ---------------------------------------------------------------------------

@router.post("/set-load")
async def set_load(req: SetLoadRequest, request: Request):
    _, anker, strategy = _get_services(request)

    if req.load % 10 != 0:
        raise HTTPException(400, "Load must be a multiple of 10W")

    old_load = anker.current_load_w
    success, message = await anker.set_home_load(req.load)

    if success:
        # Record manual change
        meter_power = None
        iometer = request.app.state.iometer
        if iometer.latest:
            meter_power = iometer.latest.power_w

        db.insert_load_change(
            old_load=old_load,
            new_load=req.load,
            reason="manual",
            meter_reading=meter_power,
            solar_production=anker.solar_power_w,
            battery_soc=anker.battery_soc,
        )
        return {"success": True, "message": message}
    else:
        raise HTTPException(500, message)


# ---------------------------------------------------------------------------
# Auto mode toggle
# ---------------------------------------------------------------------------

@router.post("/auto-mode")
async def toggle_auto_mode(request: Request, enabled: bool = True):
    _, _, strategy = _get_services(request)
    strategy.auto_enabled = enabled
    return {"success": True, "auto_enabled": strategy.auto_enabled}


# ---------------------------------------------------------------------------
# Meter history (in-memory ring buffer — recent readings)
# ---------------------------------------------------------------------------

@router.get("/meter-live")
async def get_live_meter(request: Request, seconds: int = 300):
    """Return recent readings for real-time charts.

    Uses in-memory buffer for short windows; falls back to DB for longer ones.
    """
    iometer, _, _ = _get_services(request)
    window = iometer.get_readings_window(seconds)

    # In-memory buffer only holds ~16 min; for longer requests use DB
    if seconds > 900 and len(window) < seconds / 10:
        db_data = db.get_recent_meter_readings(seconds=seconds)
        return [
            {
                "timestamp": r["timestamp"],
                "power_w": round(r["power_w"], 1),
            }
            for r in db_data
        ]

    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "power_w": round(r.power_w, 1),
        }
        for r in window
    ]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_config():
    return db.get_all_config()


@router.post("/config")
async def update_config(req: ConfigUpdateRequest):
    db.set_config(req.key, req.value)
    return {"success": True, "key": req.key, "value": req.value}


# ---------------------------------------------------------------------------
# Timezone configuration
# ---------------------------------------------------------------------------

# Curated list of common IANA timezones for the UI dropdown
_COMMON_TIMEZONES = [
    "UTC",
    "Europe/Berlin", "Europe/London", "Europe/Paris", "Europe/Rome",
    "Europe/Madrid", "Europe/Amsterdam", "Europe/Brussels", "Europe/Zurich",
    "Europe/Vienna", "Europe/Warsaw", "Europe/Prague", "Europe/Stockholm",
    "Europe/Helsinki", "Europe/Athens", "Europe/Bucharest", "Europe/Istanbul",
    "Europe/Moscow",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "America/Phoenix", "America/Anchorage", "America/Honolulu",
    "America/Toronto", "America/Vancouver", "America/Sao_Paulo",
    "America/Mexico_City", "America/Bogota", "America/Lima",
    "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Tokyo", "Asia/Seoul",
    "Asia/Singapore", "Asia/Kolkata", "Asia/Dubai", "Asia/Bangkok",
    "Asia/Jakarta", "Asia/Taipei", "Asia/Karachi", "Asia/Dhaka",
    "Australia/Sydney", "Australia/Melbourne", "Australia/Brisbane",
    "Australia/Perth", "Pacific/Auckland", "Pacific/Auckland",
    "Africa/Cairo", "Africa/Nairobi", "Africa/Johannesburg",
]


@router.get("/timezone")
async def get_timezone():
    """Return current display timezone and available timezone list."""
    current = db.get_config("display_timezone", "Europe/Berlin")
    # Validate stored value; fall back if invalid
    try:
        zoneinfo.ZoneInfo(current)
    except Exception:
        current = "Europe/Berlin"

    # Deduplicate and ensure current is in the list
    tz_set = dict.fromkeys(_COMMON_TIMEZONES)
    if current not in tz_set:
        tz_set[current] = None
    available = list(tz_set.keys())

    return {
        "current": current,
        "available": available,
        "server_utc": datetime.now(timezone.utc).isoformat(),
        "server_local": datetime.now(zoneinfo.ZoneInfo(current)).strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/timezone")
async def set_timezone(tz: str):
    """Persist a new display timezone. Validates the IANA name first."""
    try:
        zoneinfo.ZoneInfo(tz)
    except zoneinfo.ZoneInfoNotFoundError:
        raise HTTPException(400, f"Unknown timezone: {tz!r}")
    db.set_config("display_timezone", tz)
    return {"success": True, "timezone": tz}


# ---------------------------------------------------------------------------
# Appliance profiles
# ---------------------------------------------------------------------------

@router.get("/profiles")
async def get_profiles():
    return db.get_appliance_profiles()


@router.post("/profiles")
async def upsert_profile(req: ApplianceProfileRequest):
    profile_id = db.upsert_appliance_profile(req.model_dump())
    return {"success": True, "id": profile_id}


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: int):
    db.delete_appliance_profile(profile_id)
    return {"success": True}


# ---------------------------------------------------------------------------
# History data
# ---------------------------------------------------------------------------

@router.get("/load-history")
async def get_load_history(hours: int = 24):
    return db.get_load_changes(hours=hours)


@router.get("/meter-history")
async def get_meter_history(seconds: int = 3600):
    return db.get_recent_meter_readings(seconds=seconds)


@router.get("/power-events")
async def get_power_events(hours: int = 24):
    return db.get_recent_power_events(hours=hours)


@router.get("/daily-energy")
async def get_daily_energy(days: int = 30):
    return db.get_daily_energy(days=days)


@router.get("/schedule")
async def get_schedule(request: Request):
    """Return the cached SB2 schedule (time-based load presets)."""
    anker = request.app.state.anker
    schedule = anker.schedule
    if schedule is None:
        return {"schedule": None, "message": "Schedule not loaded yet"}
    return {"schedule": schedule}


# ---------------------------------------------------------------------------
# Strategy management
# ---------------------------------------------------------------------------

class StrategyChangeRequest(BaseModel):
    strategy: str = Field(description="Strategy name to activate")


@router.get("/strategies")
async def get_strategies(request: Request):
    """List all available strategies and the currently active one."""
    _, _, strategy = _get_services(request)
    return {
        "active": strategy.active_strategy_name,
        "available": list_strategies(),
    }


@router.post("/strategies")
async def set_strategy(req: StrategyChangeRequest, request: Request):
    """Switch the active strategy."""
    _, _, strategy = _get_services(request)
    if strategy.set_strategy(req.strategy):
        return {"success": True, "active": strategy.active_strategy_name}
    raise HTTPException(400, f"Unknown strategy: {req.strategy}")


# ---------------------------------------------------------------------------
# Historical analytics
# ---------------------------------------------------------------------------

@router.get("/analytics/hourly")
async def get_hourly_analytics(days: int = 7):
    """Per-hour average meter power and load over recent days."""
    return db.get_hourly_stats(days_back=days)


@router.get("/analytics/daily")
async def get_daily_analytics(days: int = 30):
    """Daily energy comparison data."""
    return db.get_daily_comparison(days=days)


@router.get("/analytics/weekly")
async def get_weekly_analytics(weeks: int = 12):
    """Weekly aggregated energy summary."""
    return db.get_weekly_summary(weeks=weeks)


@router.get("/analytics/monthly")
async def get_monthly_analytics(months: int = 12):
    """Monthly aggregated energy summary."""
    return db.get_monthly_summary(months=months)


@router.get("/analytics/period")
async def get_period_analytics(start: str, end: str):
    """Meter stats for a custom date range (ISO dates: YYYY-MM-DD)."""
    stats = db.get_meter_stats_for_period(start, end)
    if stats is None:
        return {"message": "No data for this period"}
    return stats


# ---------------------------------------------------------------------------
# Weather forecast
# ---------------------------------------------------------------------------

@router.get("/weather")
async def get_weather(request: Request):
    """Get cached weather forecast for solar optimization."""
    weather = getattr(request.app.state, "weather", None)
    if weather is None:
        return {"forecast": None, "message": "Weather service not available"}
    forecast = await weather.get_forecast()
    return {"forecast": forecast}


# ---------------------------------------------------------------------------
# Energy tracking (calculated from meter readings)
# ---------------------------------------------------------------------------

@router.get("/energy/today")
async def get_energy_today(request: Request):
    """Get today's calculated import/export energy from meter readings."""
    _, _, strategy = _get_services(request)
    return strategy.get_status().get("energy", {})
