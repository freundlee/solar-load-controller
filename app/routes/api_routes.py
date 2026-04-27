"""FastAPI REST API routes."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import database as db

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

    return {
        "anker": anker.get_dashboard_data(),
        "meter": {
            "power_w": meter_power,
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
    """Return recent in-memory readings (not from DB) for real-time charts."""
    iometer, _, _ = _get_services(request)
    window = iometer.get_readings_window(seconds)
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
