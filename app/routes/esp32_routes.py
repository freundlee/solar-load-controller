"""ESP32 Bridge API — bidirectional sync between home ESP32 and VPS.

Endpoints:
  POST /api/esp32/meter          — ESP32 pushes IOMeter readings
  POST /api/esp32/status         — ESP32 pushes IOMeter device status
  GET  /api/esp32/dashboard      — Compact data for ESP32 local display
  POST /api/esp32/set-load       — Manual load control from home console
  GET  /api/esp32/config         — Read strategy config
  POST /api/esp32/config         — Update strategy config
  POST /api/esp32/auto-mode      — Toggle auto mode

Authentication: API key via X-API-Key header or ?key= query param.
"""

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery
from pydantic import BaseModel, Field

from app import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/esp32", tags=["esp32"])

# ---------------------------------------------------------------------------
# API Key authentication
# ---------------------------------------------------------------------------

_API_KEY = os.environ.get("ESP32_API_KEY", "")

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
_query_scheme = APIKeyQuery(name="key", auto_error=False)


async def _verify_api_key(
    header_key: str | None = Security(_header_scheme),
    query_key: str | None = Security(_query_scheme),
) -> str:
    """Validate the API key from header or query parameter."""
    if not _API_KEY:
        # No key configured → allow all (development mode)
        return "dev"
    key = header_key or query_key
    if key and key == _API_KEY:
        return key
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class MeterPushRequest(BaseModel):
    power_w: float = Field(..., description="Grid power in watts (+ import, - export)")
    total_consumption_wh: float | None = Field(None, description="Cumulative import Wh")
    total_production_wh: float | None = Field(None, description="Cumulative export Wh")


class StatusPushRequest(BaseModel):
    connected: bool = True
    bridge_rssi: int | None = None
    battery_level: int | None = None
    meter_number: str | None = None
    bridge_version: str | None = None
    core_connection: str | None = None
    power_status: str | None = None


class SetLoadRequest(BaseModel):
    load: int = Field(ge=0, le=800, description="Load in watts (0-800, multiple of 10)")


class ConfigUpdateRequest(BaseModel):
    key: str
    value: float | int | bool | str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_services(request: Request):
    return (
        request.app.state.iometer,
        request.app.state.anker,
        request.app.state.strategy,
    )


# ---------------------------------------------------------------------------
# ESP32 → VPS: Push meter data
# ---------------------------------------------------------------------------

@router.post("/meter")
async def push_meter_reading(
    req: MeterPushRequest,
    request: Request,
    _key: str = Depends(_verify_api_key),
):
    """ESP32 pushes an IOMeter reading to the server."""
    iometer, _, _ = _get_services(request)
    reading = iometer.push_reading(
        power_w=req.power_w,
        total_consumption_wh=req.total_consumption_wh,
        total_production_wh=req.total_production_wh,
    )
    return {
        "ok": True,
        "timestamp": reading.timestamp.isoformat(),
        "power_w": reading.power_w,
    }


@router.post("/status")
async def push_meter_status(
    req: StatusPushRequest,
    request: Request,
    _key: str = Depends(_verify_api_key),
):
    """ESP32 pushes IOMeter device status."""
    iometer, _, _ = _get_services(request)
    from app.services.iometer_service import IOMeterStatus
    iometer.status = IOMeterStatus(
        connected=req.connected,
        bridge_rssi=req.bridge_rssi,
        battery_level=req.battery_level,
        meter_number=req.meter_number,
        bridge_version=req.bridge_version,
        core_connection=req.core_connection,
        power_status=req.power_status,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# VPS → ESP32: Compact dashboard for local display
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def get_esp32_dashboard(
    request: Request,
    _key: str = Depends(_verify_api_key),
):
    """Compact data payload for ESP32 local display.

    Returns a flat, small JSON optimized for constrained devices.
    """
    iometer, anker, strategy = _get_services(request)

    meter_reading = iometer.latest
    meter_w = meter_reading.power_w if meter_reading else None
    strat = strategy.get_status()

    return {
        # Solar system
        "solar_w": anker.solar_power_w,
        "battery_soc": anker.battery_soc,
        "battery_w": anker.battery_power_w,
        "output_w": anker.output_power_w,
        "load_w": anker.current_load_w,
        # Per-channel
        "pv1_w": anker.pv1_power_w,
        "pv2_w": anker.pv2_power_w,
        "mi_w": anker.micro_inverter_power_w,
        # Grid meter
        "meter_w": meter_w,
        "meter_ok": iometer.status.connected,
        # Strategy
        "auto": strat.get("auto_enabled", False),
        "state": strat.get("state", "IDLE"),
        "avg30": strat.get("meter_avg_30s"),
        "avg60": strat.get("meter_avg_60s"),
        "baseline_w": strat.get("baseline_load_w", 0),
        # Energy today
        "solar_kwh": anker.today_solar_kwh,
        "pv1_kwh": anker.today_pv1_kwh,
        "pv2_kwh": anker.today_pv2_kwh,
        "mi_kwh": anker.today_mi_kwh,
        "charge_kwh": anker.today_charge_kwh,
        "discharge_kwh": anker.today_discharge_kwh,
        "import_kwh": anker.today_grid_import_kwh,
        "export_kwh": anker.today_grid_export_kwh,
        # Timestamp
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# ESP32 → VPS: Manual load control
# ---------------------------------------------------------------------------

@router.post("/set-load")
async def esp32_set_load(
    req: SetLoadRequest,
    request: Request,
    _key: str = Depends(_verify_api_key),
):
    """Set home load from ESP32 console."""
    _, anker, _ = _get_services(request)

    if req.load % 10 != 0:
        raise HTTPException(400, "Load must be a multiple of 10W")

    old_load = anker.current_load_w
    success, message = await anker.set_home_load(req.load)

    if success:
        iometer = request.app.state.iometer
        meter_power = iometer.latest.power_w if iometer.latest else None
        db.insert_load_change(
            old_load=old_load,
            new_load=req.load,
            reason="esp32_manual",
            meter_reading=meter_power,
            solar_production=anker.solar_power_w,
            battery_soc=anker.battery_soc,
        )
        return {"ok": True, "load_w": req.load, "message": message}
    raise HTTPException(500, message)


@router.post("/auto-mode")
async def esp32_auto_mode(
    request: Request,
    enabled: bool = True,
    _key: str = Depends(_verify_api_key),
):
    """Toggle auto mode from ESP32 console."""
    _, _, strategy = _get_services(request)
    strategy.auto_enabled = enabled
    return {"ok": True, "auto": strategy.auto_enabled}


# ---------------------------------------------------------------------------
# ESP32 ↔ VPS: Config read/write
# ---------------------------------------------------------------------------

@router.get("/config")
async def esp32_get_config(_key: str = Depends(_verify_api_key)):
    """Read all strategy config."""
    return db.get_all_config()


@router.post("/config")
async def esp32_set_config(
    req: ConfigUpdateRequest,
    _key: str = Depends(_verify_api_key),
):
    """Update a strategy config parameter."""
    db.set_config(req.key, req.value)
    return {"ok": True, "key": req.key, "value": req.value}


# ---------------------------------------------------------------------------
# ESP32 ↔ VPS: Strategy management (API-key protected proxy)
# ---------------------------------------------------------------------------

class StrategySetRequest(BaseModel):
    name: str = Field(..., description="Strategy name to activate")


@router.get("/strategies")
async def esp32_get_strategies(
    request: Request,
    _key: str = Depends(_verify_api_key),
):
    """Return available strategies and the currently active one.

    Response mirrors GET /api/strategies so the ESP32 uses a single
    authenticated endpoint without needing separate API access.
    """
    _, _, strategy = _get_services(request)
    from app.services.strategies import STRATEGIES
    return {
        "strategies": list(STRATEGIES.keys()),
        "active": strategy.active_strategy_name,
    }


@router.post("/strategies")
async def esp32_set_strategy(
    req: StrategySetRequest,
    request: Request,
    _key: str = Depends(_verify_api_key),
):
    """Switch the active strategy from the ESP32 console."""
    _, _, strategy = _get_services(request)
    from app.services.strategies import STRATEGIES
    if req.name not in STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{req.name}'. "
                   f"Available: {list(STRATEGIES.keys())}",
        )
    strategy.set_strategy(req.name)
    logger.info("ESP32 switched strategy to '%s'", req.name)
    return {"ok": True, "active": req.name}
