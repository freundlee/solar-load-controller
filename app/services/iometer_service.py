"""IOMeter smart meter integration service.

Polls the local IOMeter device for real-time grid power readings.
Positive power = grid import; negative power = grid export.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp

from app.config import iometer_cfg
from app import database as db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MeterReading:
    timestamp: datetime
    power_w: float                  # + import, - export
    total_consumption_wh: float | None = None
    total_production_wh: float | None = None


@dataclass
class IOMeterStatus:
    connected: bool = False
    bridge_version: str | None = None
    bridge_rssi: int | None = None
    core_connection: str | None = None
    power_status: str | None = None
    battery_level: int | None = None
    meter_number: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class IOMeterService:
    """Manages communication with the local IOMeter bridge."""

    def __init__(self) -> None:
        self._host = iometer_cfg.host
        self._timeout = aiohttp.ClientTimeout(total=iometer_cfg.request_timeout_s)
        self._session: aiohttp.ClientSession | None = None
        self._running = False

        # In-memory ring buffer for strategy engine (last ~120s at 5s intervals = ~24 entries)
        self.readings: deque[MeterReading] = deque(maxlen=200)

        self.latest: MeterReading | None = None
        self.status: IOMeterStatus = IOMeterStatus()
        self._last_db_write: float = 0.0
        self._db_write_interval = 300.0  # persist to SQLite every 5 min

    @property
    def base_url(self) -> str:
        proto = "http"
        return f"{proto}://{self._host}"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={
                    "User-Agent": "SolarLoadController/1.0",
                    "Accept": "application/json",
                },
            )
        return self._session

    # ---- Public API --------------------------------------------------------

    async def fetch_reading(self) -> MeterReading | None:
        """Fetch a single reading from IOMeter /v1/reading endpoint."""
        try:
            session = await self._ensure_session()
            async with session.get(f"{self.base_url}/v1/reading") as resp:
                if resp.status == 404:
                    logger.warning("IOMeter: no readings available (404)")
                    return None
                resp.raise_for_status()
                data = await resp.json()

            # Parse OBIS registers
            registers = (
                data.get("meter", {})
                .get("reading", {})
                .get("registers", [])
            )

            power_w = None
            total_consumption = None
            total_production = None

            for reg in registers:
                obis = reg.get("obis", "")
                val = reg.get("value")
                if val is None:
                    continue

                # Current power (W)  – OBIS 1-0:16.7.0 (signed net power)
                # or 1-0:1.7.0 (consumption direction)
                if "16.7.0" in obis or "10.07.00" in obis:
                    power_w = float(val)
                elif "1.7.0" in obis and power_w is None:
                    power_w = float(val)
                # Total consumption (Wh) – OBIS 1-0:1.8.0
                elif "1.8.0" in obis or "01.08.00" in obis:
                    total_consumption = float(val)
                # Total production / feed-in (Wh) – OBIS 1-0:2.8.0
                elif "2.8.0" in obis or "02.08.00" in obis:
                    total_production = float(val)

            if power_w is None:
                logger.warning("IOMeter: no power register found in response")
                return None

            reading = MeterReading(
                timestamp=datetime.now(timezone.utc),
                power_w=power_w,
                total_consumption_wh=total_consumption,
                total_production_wh=total_production,
            )
            return reading

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("IOMeter unreachable: %s", exc)
            self.status.connected = False
            return None
        except Exception as exc:
            logger.exception("IOMeter unexpected error: %s", exc)
            return None

    async def fetch_status(self) -> IOMeterStatus:
        """Fetch device status from /v1/status."""
        try:
            session = await self._ensure_session()
            async with session.get(f"{self.base_url}/v1/status") as resp:
                if resp.status == 404:
                    self.status.connected = False
                    return self.status
                resp.raise_for_status()
                data = await resp.json()

            device = data.get("device", {})
            bridge = device.get("bridge", {})
            core = device.get("core", {})
            meter = data.get("meter", {})

            self.status = IOMeterStatus(
                connected=core.get("connectionStatus") == "connected",
                bridge_version=bridge.get("version"),
                bridge_rssi=bridge.get("rssi"),
                core_connection=core.get("connectionStatus"),
                power_status=core.get("powerStatus"),
                battery_level=core.get("batteryLevel"),
                meter_number=meter.get("number"),
            )
            return self.status

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("IOMeter status unreachable: %s", exc)
            self.status.connected = False
            return self.status
        except Exception as exc:
            logger.exception("IOMeter status unexpected error: %s", exc)
            return self.status

    async def poll_once(self) -> MeterReading | None:
        """Single poll: fetch reading, store in buffer, optionally persist."""
        reading = await self.fetch_reading()
        if reading is None:
            return None

        self.latest = reading
        self.readings.append(reading)
        self.status.connected = True

        # Persist to DB periodically (not every poll)
        now = time.monotonic()
        if now - self._last_db_write >= self._db_write_interval:
            try:
                db.insert_meter_reading(
                    power_w=reading.power_w,
                    total_consumption_wh=reading.total_consumption_wh,
                    total_production_wh=reading.total_production_wh,
                )
                self._last_db_write = now
            except Exception as exc:
                logger.error("Failed to persist meter reading: %s", exc)

        return reading

    async def start_polling(self, interval: float | None = None) -> None:
        """Start continuous polling loop (run as asyncio task)."""
        self._running = True
        poll_interval = interval or iometer_cfg.polling_interval_s
        logger.info("IOMeter polling started (interval=%.1fs, host=%s)", poll_interval, self._host)

        while self._running:
            await self.poll_once()
            await asyncio.sleep(poll_interval)

    def stop_polling(self) -> None:
        self._running = False

    async def close(self) -> None:
        self.stop_polling()
        if self._session and not self._session.closed:
            await self._session.close()

    # ---- Convenience for strategy engine -----------------------------------

    def get_readings_window(self, seconds: float) -> list[MeterReading]:
        """Return readings from the last `seconds` seconds."""
        cutoff = datetime.now(timezone.utc).timestamp() - seconds
        return [r for r in self.readings if r.timestamp.timestamp() >= cutoff]

    def get_average_power(self, seconds: float) -> float | None:
        """Average power over last N seconds."""
        window = self.get_readings_window(seconds)
        if not window:
            return None
        return sum(r.power_w for r in window) / len(window)
