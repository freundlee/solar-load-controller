"""Strategy engine — the core brain of solar load control.

Direct proportional controller:
  target_load = current_load + (meter_avg_10s − grid_target)

Applies adjustment in ONE step with a cooldown to prevent oscillation
while the SB2 ramps to the new preset.  Smart plug power is already
reflected in the meter reading and needs no special handling.

All tuneable parameters are read from the SQLite config table so they
can be changed at runtime from the dashboard without restart.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app import database as db
from app.services.iometer_service import IOMeterService
from app.services.anker_service import AnkerService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy Engine
# ---------------------------------------------------------------------------

class StrategyEngine:
    """Runs the main control loop: poll meter → decide → adjust load."""

    def __init__(self, iometer: IOMeterService, anker: AnkerService) -> None:
        self.iometer = iometer
        self.anker = anker

        # State
        self._running = False
        self._auto_enabled = True
        self._state = "idle"
        self._last_load_change_time: float = 0.0
        self._baseline_load_w: int = 0  # load before any auto-adjustment
        self._last_set_load_w: int | None = None

        # Counters (exposed for dashboard)
        self.total_adjustments: int = 0
        self.total_spikes_detected: int = 0
        self.total_spikes_ignored: int = 0
        self.last_action: str = "none"
        self.last_action_time: str = ""
        self._plug_total_w: float = 0.0

    # ---- Config helpers (read from DB every cycle) -------------------------

    def _cfg(self, key: str, default: float) -> float:
        val = db.get_config(key, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _cfg_int(self, key: str, default: int) -> int:
        return int(self._cfg(key, float(default)))

    @property
    def auto_enabled(self) -> bool:
        return self._auto_enabled

    @auto_enabled.setter
    def auto_enabled(self, value: bool) -> None:
        self._auto_enabled = value
        db.set_config("auto_mode_enabled", value)
        logger.info("Auto mode %s", "enabled" if value else "disabled")

    # ---- Main loop ----------------------------------------------------------

    async def start(self) -> None:
        """Start the strategy control loop (run as asyncio task)."""
        self._running = True
        self._auto_enabled = bool(db.get_config("auto_mode_enabled", True))
        self._baseline_load_w = self.anker.current_load_w
        logger.info("Strategy engine started (auto=%s, baseline=%dW)",
                     self._auto_enabled, self._baseline_load_w)

        while self._running:
            interval = self._cfg("polling_interval_s", 5.0)
            try:
                if self._auto_enabled:
                    await self._tick()
            except Exception as exc:
                logger.exception("Strategy tick error: %s", exc)
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self._running = False
        logger.info("Strategy engine stopped")

    # ---- Core tick ----------------------------------------------------------

    async def _tick(self) -> None:
        """One cycle of the strategy loop.

        Simple proportional controller:
          target_load = current_load + (meter_avg - grid_target)

        Uses a 10s rolling average to filter transient spikes (motor startup
        etc.), then applies the change in ONE step.  The cooldown period
        prevents oscillation while the SB2 ramps to the new preset.

        Smart plug power is already reflected in the meter reading, so it
        is implicitly accounted for.
        """
        reading = self.iometer.latest
        if reading is None:
            return

        meter_w = reading.power_w  # + = grid import, - = export
        now_mono = time.monotonic()

        # Load config each tick (they may have changed from UI)
        grid_target = self._cfg("grid_target_w", 0.0)
        min_change = self._cfg("min_change_threshold_w", 20.0)
        cooldown = self._cfg("cooldown_period_s", 30.0)
        emergency = self._cfg("emergency_threshold_w", 500.0)
        max_load = self._cfg_int("max_load_w", 800)
        min_load = self._cfg_int("min_load_w", 0)
        step = self._cfg_int("load_step_w", 10)

        current_load = self.anker.current_load_w
        if self._last_set_load_w is not None:
            current_load = self._last_set_load_w

        # Smart plug context (for logging / dashboard)
        plug_total_w = sum(p.get("power_w", 0) for p in self.anker.smart_plugs)
        self._plug_total_w = plug_total_w

        # Use 10s average to smooth transient spikes; fall back to instant
        avg = self.iometer.get_average_power(10) or meter_w

        # Emergency: skip cooldown for very large grid import
        is_emergency = avg > emergency
        if not is_emergency and self._in_cooldown(now_mono, cooldown):
            return

        # Direct target calculation
        target = self._calc_target(avg, grid_target, current_load,
                                   max_load, min_load, step)

        # Hysteresis — skip tiny adjustments
        if abs(target - current_load) < min_change:
            return

        # Determine reason for logging
        if is_emergency:
            reason = "auto_emergency"
        elif avg > grid_target:
            reason = "auto_increase"
        else:
            reason = "auto_decrease"

        logger.info(
            "Adjust: meter_avg=%.0fW target_grid=%.0fW load=%d→%dW "
            "plugs=%.0fW (%s)",
            avg, grid_target, current_load, target, plug_total_w, reason,
        )
        await self._set_load(target, reason, meter_w, current_load)

    # ---- Load adjustment helpers -------------------------------------------

    def _calc_target(self, meter_w: float, grid_target: float,
                     current_load: int, max_load: int, min_load: int,
                     step: int) -> int:
        """Calculate target load to bring meter reading toward grid_target."""
        delta = meter_w - grid_target
        raw_target = current_load + delta
        return self._snap_load(raw_target, max_load, min_load, step)

    @staticmethod
    def _snap_load(value: float, max_load: int, min_load: int, step: int) -> int:
        """Clamp and round to nearest step."""
        clamped = max(min_load, min(max_load, value))
        return round(clamped / step) * step

    async def _set_load(self, new_load: int, reason: str,
                        meter_w: float, old_load: int) -> None:
        """Actually call Anker API to change the load."""
        success, msg = await self.anker.set_home_load(new_load)
        now_mono = time.monotonic()

        if success:
            self._last_load_change_time = now_mono
            self._last_set_load_w = new_load
            self.total_adjustments += 1
            self.last_action = f"{reason}: {old_load}W→{new_load}W"
            self.last_action_time = datetime.now(timezone.utc).isoformat()

            db.insert_load_change(
                old_load=old_load,
                new_load=new_load,
                reason=reason,
                meter_reading=meter_w,
                solar_production=self.anker.solar_power_w,
                battery_soc=self.anker.battery_soc,
            )
            logger.info("Load changed: %dW → %dW (reason=%s, meter=%.0fW)",
                        old_load, new_load, reason, meter_w)
        else:
            logger.error("Failed to set load to %dW: %s", new_load, msg)

    def _in_cooldown(self, now_mono: float, cooldown: float) -> bool:
        return (now_mono - self._last_load_change_time) < cooldown

    # ---- Status for dashboard ----------------------------------------------

    def get_status(self) -> dict:
        reading = self.iometer.latest
        meter_w = reading.power_w if reading else None
        avg_30 = self.iometer.get_average_power(30)
        avg_60 = self.iometer.get_average_power(60)
        return {
            "auto_enabled": self._auto_enabled,
            "state": self._state,
            "total_adjustments": self.total_adjustments,
            "total_spikes_detected": self.total_spikes_detected,
            "total_spikes_ignored": self.total_spikes_ignored,
            "last_action": self.last_action,
            "last_action_time": self.last_action_time,
            "baseline_load_w": self._baseline_load_w,
            "meter_avg_30s": round(avg_30, 1) if avg_30 is not None else None,
            "meter_avg_60s": round(avg_60, 1) if avg_60 is not None else None,
            "meter_instant_w": round(meter_w, 1) if meter_w is not None else None,
            "plug_total_w": round(self._plug_total_w, 1),
        }
