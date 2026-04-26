"""Strategy engine — the core brain of solar load control.

Three-layer algorithm:
  1. Spike detection & classification (transient vs sustained)
  2. Load adjustment calculation (target meter ≈ 0 W)
  3. Cooldown & rate limiting (avoid oscillation)

All tuneable parameters are read from the SQLite config table so they
can be changed at runtime from the dashboard without restart.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from app import database as db
from app.services.iometer_service import IOMeterService, MeterReading
from app.services.anker_service import AnkerService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class SpikeState(str, Enum):
    IDLE = "idle"
    OBSERVING = "observing"
    SUSTAINED = "sustained"
    RESTORING = "restoring"


@dataclass
class PowerSpike:
    """Tracks an ongoing power spike event."""
    start_time: float                   # monotonic clock
    start_reading_w: float              # meter reading when spike started
    peak_power_w: float = 0.0
    readings: list[float] = field(default_factory=list)
    db_event_id: int | None = None
    matched_profile_id: int | None = None
    matched_profile_action: str = "observe"


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
        self._state = SpikeState.IDLE
        self._current_spike: PowerSpike | None = None
        self._last_load_change_time: float = 0.0
        self._baseline_load_w: int = 0  # load before any auto-adjustment
        self._last_set_load_w: int | None = None

        # Counters (exposed for dashboard)
        self.total_adjustments: int = 0
        self.total_spikes_detected: int = 0
        self.total_spikes_ignored: int = 0
        self.last_action: str = "none"
        self.last_action_time: str = ""

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
        """One cycle of the strategy loop."""
        reading = self.iometer.latest
        if reading is None:
            return

        meter_w = reading.power_w  # + = grid import, - = export
        now_mono = time.monotonic()

        # Load config each tick (they may have changed from UI)
        grid_target = self._cfg("grid_target_w", -10.0)
        min_change = self._cfg("min_change_threshold_w", 30.0)
        cooldown = self._cfg("cooldown_period_s", 45.0)
        emergency = self._cfg("emergency_threshold_w", 500.0)
        spike_obs = self._cfg("spike_observation_period_s", 90.0)
        reaction_delay = self._cfg("reaction_delay_s", 15.0)
        max_load = self._cfg_int("max_load_w", 800)
        min_load = self._cfg_int("min_load_w", 0)
        step = self._cfg_int("load_step_w", 10)

        current_load = self.anker.current_load_w
        if self._last_set_load_w is not None:
            current_load = self._last_set_load_w

        # ----- Layer 1: Spike detection ------------------------------------

        avg_10s = self.iometer.get_average_power(10) or meter_w
        avg_60s = self.iometer.get_average_power(60) or meter_w

        # Deviation from short-term to longer-term average
        deviation = avg_10s - avg_60s

        if self._state == SpikeState.IDLE:
            # Detect a new spike: sudden grid import increase
            if meter_w > grid_target + min_change:
                # Check if this is a significant deviation
                if deviation > min_change or meter_w > emergency:
                    self._state = SpikeState.OBSERVING
                    self._current_spike = PowerSpike(
                        start_time=now_mono,
                        start_reading_w=meter_w,
                        peak_power_w=meter_w,
                        readings=[meter_w],
                    )
                    self.total_spikes_detected += 1

                    # Try to match an appliance profile
                    self._match_profile(meter_w)

                    # Record event in DB
                    ts = datetime.now(timezone.utc).isoformat()
                    self._current_spike.db_event_id = db.insert_power_event(
                        start_time=ts,
                        peak_power=meter_w,
                        profile_id=self._current_spike.matched_profile_id,
                        action_taken="observing",
                    )

                    logger.info(
                        "Spike detected: %.0fW (profile: %s, action: %s)",
                        meter_w,
                        self._current_spike.matched_profile_id,
                        self._current_spike.matched_profile_action,
                    )

                    # Emergency: override everything for very large spikes
                    if meter_w > emergency:
                        logger.warning("Emergency spike %.0fW — immediate adjustment", meter_w)
                        await self._adjust_load(meter_w, grid_target, current_load,
                                                max_load, min_load, step, "auto_emergency")
                        self._state = SpikeState.SUSTAINED
                        return
                else:
                    # Small sustained positive reading – do gradual adjustment
                    if self._in_cooldown(now_mono, cooldown):
                        return
                    await self._adjust_load(meter_w, grid_target, current_load,
                                            max_load, min_load, step, "auto_adjust")

        elif self._state == SpikeState.OBSERVING:
            spike = self._current_spike
            spike.readings.append(meter_w)
            spike.peak_power_w = max(spike.peak_power_w, meter_w)
            elapsed = now_mono - spike.start_time

            # Emergency override during observation
            if meter_w > emergency and not self._in_cooldown(now_mono, cooldown):
                await self._adjust_load(meter_w, grid_target, current_load,
                                        max_load, min_load, step, "auto_emergency")
                self._state = SpikeState.SUSTAINED
                return

            # Check if spike has subsided
            if meter_w <= grid_target + min_change:
                # Spike ended during observation — classify as transient
                self._finalize_spike("transient_ended")
                self.total_spikes_ignored += 1
                self._state = SpikeState.IDLE
                logger.info("Spike ended after %.0fs — classified as transient", elapsed)
                return

            # Check profile action
            if spike.matched_profile_action == "ignore":
                profile_max_dur = self._get_profile_max_duration(spike.matched_profile_id)
                if elapsed > profile_max_dur:
                    # Exceeded expected duration for "ignore" profile — reclassify
                    logger.info("Spike exceeded ignore profile max duration — adjusting")
                    spike.matched_profile_action = "adjust"
                else:
                    # Still within ignore window
                    return

            # Observation period expired — classify as sustained
            if elapsed >= spike_obs or (elapsed >= reaction_delay and spike.matched_profile_action == "adjust"):
                self._state = SpikeState.SUSTAINED
                if not self._in_cooldown(now_mono, cooldown):
                    avg_spike = sum(spike.readings) / len(spike.readings) if spike.readings else meter_w
                    await self._adjust_load(avg_spike, grid_target, current_load,
                                            max_load, min_load, step, "auto_spike")
                    self._finalize_spike("sustained_adjusted")

        elif self._state == SpikeState.SUSTAINED:
            # Continue monitoring — re-adjust if needed
            if meter_w <= grid_target + min_change:
                # High-power usage ended — begin restoring
                self._state = SpikeState.RESTORING
                logger.info("Sustained usage ended, beginning restore")
                return

            # If still importing significantly, re-adjust
            if abs(meter_w - grid_target) > min_change and not self._in_cooldown(now_mono, cooldown):
                await self._adjust_load(meter_w, grid_target, current_load,
                                        max_load, min_load, step, "auto_readjust")

        elif self._state == SpikeState.RESTORING:
            # Gradually restore toward baseline
            if meter_w > grid_target + min_change:
                # Usage came back — go to sustained
                self._state = SpikeState.SUSTAINED
                return

            if not self._in_cooldown(now_mono, cooldown):
                # Calculate restore target: move toward baseline
                target = self._calc_target(meter_w, grid_target, current_load,
                                           max_load, min_load, step)
                # Move at most halfway toward baseline to avoid oscillation
                restore_target = current_load + (target - current_load) // 2
                restore_target = self._snap_load(restore_target, max_load, min_load, step)

                if abs(restore_target - current_load) >= step:
                    await self._set_load(restore_target, "auto_restore",
                                         meter_w, current_load)
                else:
                    # Close enough — done restoring
                    self._state = SpikeState.IDLE
                    self._baseline_load_w = current_load
                    logger.info("Restore complete, baseline=%dW", current_load)

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

    async def _adjust_load(self, meter_w: float, grid_target: float,
                           current_load: int, max_load: int, min_load: int,
                           step: int, reason: str) -> None:
        target = self._calc_target(meter_w, grid_target, current_load,
                                   max_load, min_load, step)
        min_change = self._cfg("min_change_threshold_w", 30.0)
        if abs(target - current_load) < min_change:
            return
        await self._set_load(target, reason, meter_w, current_load)

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

    # ---- Profile matching --------------------------------------------------

    def _match_profile(self, power_w: float) -> None:
        """Try to match the current power reading against known appliance profiles."""
        spike = self._current_spike
        if spike is None:
            return

        profiles = db.get_appliance_profiles()
        for p in profiles:
            if p["power_min_w"] <= power_w <= p["power_max_w"]:
                spike.matched_profile_id = p["id"]
                spike.matched_profile_action = p["action"]
                logger.debug("Matched profile: %s (action=%s)", p["name"], p["action"])
                return

        # No match — default to observe then adjust
        spike.matched_profile_action = "adjust"

    def _get_profile_max_duration(self, profile_id: int | None) -> float:
        if profile_id is None:
            return 180.0  # default 3 minutes
        profiles = db.get_appliance_profiles()
        for p in profiles:
            if p["id"] == profile_id:
                return float(p.get("max_duration_s") or 180)
        return 180.0

    def _finalize_spike(self, action: str) -> None:
        spike = self._current_spike
        if spike is None:
            return
        if spike.db_event_id:
            now = datetime.now(timezone.utc).isoformat()
            avg = sum(spike.readings) / len(spike.readings) if spike.readings else 0
            duration = int(time.monotonic() - spike.start_time)
            try:
                db.update_power_event(
                    event_id=spike.db_event_id,
                    end_time=now,
                    avg_power=avg,
                    duration_s=duration,
                )
            except Exception as exc:
                logger.error("Failed to finalize spike event: %s", exc)

            # Update profile occurrence count
            if spike.matched_profile_id:
                try:
                    from app.database import get_db
                    with get_db() as conn:
                        conn.execute(
                            """UPDATE appliance_profiles
                               SET occurrences = occurrences + 1, last_seen = ?
                               WHERE id = ?""",
                            (now, spike.matched_profile_id),
                        )
                except Exception:
                    pass

        self._current_spike = None

    # ---- Status for dashboard ----------------------------------------------

    def get_status(self) -> dict:
        return {
            "auto_enabled": self._auto_enabled,
            "state": self._state.value,
            "total_adjustments": self.total_adjustments,
            "total_spikes_detected": self.total_spikes_detected,
            "total_spikes_ignored": self.total_spikes_ignored,
            "last_action": self.last_action,
            "last_action_time": self.last_action_time,
            "baseline_load_w": self._baseline_load_w,
            "current_spike": {
                "peak_power_w": self._current_spike.peak_power_w,
                "duration_s": int(time.monotonic() - self._current_spike.start_time),
                "profile_action": self._current_spike.matched_profile_action,
            } if self._current_spike else None,
        }
