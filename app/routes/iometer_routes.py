"""IOMeter Remote Push API — receives meter readings pushed from the home LAN.

This endpoint is used when the Solar Dashboard runs on a VPS and the IOMeter
is only accessible on the home LAN.  A lightweight pusher service (e.g. running
on a Mac mini in Docker) polls the local IOMeter and POSTs readings here every
minute.

Endpoint:
  POST /api/iometer/push   — Push a meter reading (power + cumulative total)
  GET  /api/iometer/status — Check last received reading + staleness

Authentication: API key via X-API-Key header or ?key= query param.
Uses the same ESP32_API_KEY environment variable (or IOMETER_PUSH_KEY if set).
"""

import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery
from pydantic import BaseModel, Field

from app import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/iometer", tags=["iometer"])

# ---------------------------------------------------------------------------
# API Key authentication
# Reuse IOMETER_PUSH_KEY if set, otherwise fall back to ESP32_API_KEY.
# ---------------------------------------------------------------------------

_API_KEY = os.environ.get("IOMETER_PUSH_KEY") or os.environ.get("ESP32_API_KEY", "")

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
_query_scheme = APIKeyQuery(name="key", auto_error=False)


async def _verify_api_key(
    header_key: str | None = Security(_header_scheme),
    query_key: str | None = Security(_query_scheme),
) -> str:
    if not _API_KEY:
        return "dev"  # no key configured → dev mode
    key = header_key or query_key
    if key and key == _API_KEY:
        return key
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class MeterPushRequest(BaseModel):
    """Meter reading pushed from the home LAN pusher service."""

    power_w: float = Field(
        ...,
        description="Current grid power in watts (positive = import, negative = export)",
    )
    total_consumption_wh: float | None = Field(
        None,
        description="Cumulative grid import in Wh as read from the meter (OBIS 1-0:1.8.0)",
    )
    total_production_wh: float | None = Field(
        None,
        description="Cumulative grid export/feed-in in Wh (OBIS 1-0:2.8.0)",
    )
    source_ts: str | None = Field(
        None,
        description="ISO timestamp from pusher (UTC). Used for latency monitoring.",
    )


# ---------------------------------------------------------------------------
# Push endpoint
# ---------------------------------------------------------------------------

@router.post("/push")
async def push_meter_reading(
    req: MeterPushRequest,
    request: Request,
    _key: str = Depends(_verify_api_key),
):
    """Receive a meter reading from the home LAN pusher service.

    The iometer_source config key must be set to 'remote' for this data to be
    used by the strategy engine.  In any other mode the data is still accepted
    and stored in the buffer (useful for monitoring), but the strategy engine
    will continue using its configured source.
    """
    iometer = request.app.state.iometer
    reading = iometer.push_reading(
        power_w=req.power_w,
        total_consumption_wh=req.total_consumption_wh,
        total_production_wh=req.total_production_wh,
    )

    # Calculate push latency if source timestamp was provided
    latency_ms = None
    if req.source_ts:
        try:
            src_dt = datetime.fromisoformat(req.source_ts.replace("Z", "+00:00"))
            latency_ms = round(
                (datetime.now(timezone.utc) - src_dt).total_seconds() * 1000
            )
        except Exception:
            pass

    return {
        "ok": True,
        "received_at": reading.timestamp.isoformat(),
        "power_w": reading.power_w,
        "total_consumption_wh": reading.total_consumption_wh,
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_push_status(
    request: Request,
    _key: str = Depends(_verify_api_key),
):
    """Return the last received reading and how fresh it is."""
    iometer = request.app.state.iometer
    latest = iometer.latest
    stale_s = None
    if iometer._last_push_time > 0:
        stale_s = round(time.monotonic() - iometer._last_push_time)

    source = db.get_config("iometer_source", "local")

    return {
        "source": source,
        "connected": iometer.status.connected,
        "stale_seconds": stale_s,
        "latest": {
            "power_w": latest.power_w if latest else None,
            "total_consumption_wh": latest.total_consumption_wh if latest else None,
            "total_production_wh": latest.total_production_wh if latest else None,
            "timestamp": latest.timestamp.isoformat() if latest else None,
        },
    }
