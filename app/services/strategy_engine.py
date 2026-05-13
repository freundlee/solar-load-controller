"""Strategy engine — the core brain of solar load control.

Pluggable strategy system with multiple algorithms:
  - proportional:  Direct target_load = current + (meter_avg − grid_target)
  - conservative:  Minimize grid import with safety buffers
  - smoothing:     Handle rapid fluctuations with stability detection
  - battery_guard: SOC-aware + time-of-day + weather-aware
  - predictive:    Historical pattern-based pre-positioning

The active strategy is selected from the config table and can be changed
at runtime from the dashboard or API without restart.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app import database as db
from app.services.iometer_service import IOMeterService
from app.services.anker_service import AnkerService
from app.services.strategies import (
    StrategyContext,
    StrategyDecision,
    BaseStrategy,
    get_strategy,
    list_strategies,
    STRATEGIES,
)

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
        self._active_strategy: BaseStrategy | None = None
        self._active_strategy_name: str = "proportional"

        # Counters (exposed for dashboard)
        self.total_adjustments: int = 0
        self.total_spikes_detected: int = 0
        self.total_spikes_ignored: int = 0
        self.last_action: str = "none"
        self.last_action_time: str = ""
        self._plug_total_w: float = 0.0
        self._last_decision_notes: str = ""

        # Energy tracking (calculated from meter readings)
        self._energy_tracker = EnergyTracker()

        # Weather forecast cache (populated externally)
        self.weather_forecast: dict | None = None

    # ---- Config helpers (read from DB every cycle) -------------------------

    def _cfg(self, key: str, default: float) -> float:
        val = db.get_config(key, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _cfg_int(self, key: str, default: int) -> int:
        return int(self._cfg(key, float(default)))

    def _cfg_str(self, key: str, default: str) -> str:
        val = db.get_config(key, default)
        return str(val) if val is not None else default

    @property
    def auto_enabled(self) -> bool:
        return self._auto_enabled

    @auto_enabled.setter
    def auto_enabled(self, value: bool) -> None:
        self._auto_enabled = value
        db.set_config("auto_mode_enabled", value)
        logger.info("Auto mode %s", "enabled" if value else "disabled")

    @property
    def active_strategy_name(self) -> str:
        return self._active_strategy_name

    def set_strategy(self, name: str) -> bool:
        """Switch the active strategy. Returns True if valid."""
        if name not in STRATEGIES:
            return False
        self._active_strategy_name = name
        self._active_strategy = get_strategy(name)
        db.set_config("active_strategy", name)
        logger.info("Strategy switched to: %s", name)
        return True

    # ---- Main loop ----------------------------------------------------------

    async def start(self) -> None:
        """Start the strategy control loop (run as asyncio task)."""
        self._running = True
        self._auto_enabled = bool(db.get_config("auto_mode_enabled", True))
        self._baseline_load_w = self.anker.current_load_w

        # Load active strategy from config
        strategy_name = self._cfg_str("active_strategy", "proportional")
        self._active_strategy_name = strategy_name
        self._active_strategy = get_strategy(strategy_name)

        logger.info("Strategy engine started (auto=%s, baseline=%dW, strategy=%s)",
                     self._auto_enabled, self._baseline_load_w, strategy_name)

        while self._running:
            interval = self._cfg("polling_interval_s", 5.0)
            try:
                if self._auto_enabled:
                    await self._tick()
                # Always track energy (even in manual mode)
                self._energy_tracker.update(self.iometer, self.anker)
            except Exception as exc:
                logger.exception("Strategy tick error: %s", exc)
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self._running = False
        logger.info("Strategy engine stopped")

    # ---- Core tick ----------------------------------------------------------

    async def _tick(self) -> None:
        """One cycle of the strategy loop — delegates to the active strategy plugin."""
        reading = self.iometer.latest
        if reading is None:
            return

        meter_w = reading.power_w  # + = grid import, - = export
        now_mono = time.monotonic()

        # Reload strategy if changed from UI
        configured_strategy = self._cfg_str("active_strategy", "proportional")
        if configured_strategy != self._active_strategy_name:
            self.set_strategy(configured_strategy)

        # Load config each tick
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

        # Hard guard: once battery reaches reserve/min SOC, stop discharging.
        reserve_soc = self.anker.battery_reserve_soc
        if reserve_soc is not None and self.anker.battery_soc <= (reserve_soc + 0.1):
            self._last_decision_notes = (
                f"reserve_reached soc={self.anker.battery_soc:.1f}% "
                f"reserve={reserve_soc:.1f}%"
            )
            if current_load > 0:
                logger.info(
                    "Reserve reached: soc=%.1f%% reserve=%.1f%%, forcing load to 0W",
                    self.anker.battery_soc,
                    reserve_soc,
                )
                await self._set_load(0, "battery_reserve_reached", meter_w, current_load)
            return

        # Smart plug context
        plug_total_w = sum(p.get("power_w", 0) for p in self.anker.smart_plugs)
        self._plug_total_w = plug_total_w

        # Gather meter history for strategies that need it
        meter_history = [r.power_w for r in self.iometer.readings]

        # Build strategy context
        avg_10 = self.iometer.get_average_power(10) or meter_w
        avg_30 = self.iometer.get_average_power(30)
        avg_60 = self.iometer.get_average_power(60)

        # Get historical patterns for predictive strategy
        hour_avg_load = db.get_hourly_avg_load(datetime.now(db.get_display_tz()).hour)

        ctx = StrategyContext(
            meter_instant_w=meter_w,
            meter_avg_10s=avg_10,
            meter_avg_30s=avg_30,
            meter_avg_60s=avg_60,
            meter_history=meter_history,
            current_load_w=current_load,
            battery_soc=self.anker.battery_soc,
            solar_power_w=self.anker.solar_power_w,
            battery_power_w=self.anker.battery_power_w,
            grid_target_w=grid_target,
            max_load_w=max_load,
            min_load_w=min_load,
            load_step_w=step,
            min_change_threshold_w=min_change,
            cooldown_period_s=cooldown,
            emergency_threshold_w=emergency,
            seconds_since_last_change=now_mono - self._last_load_change_time,
            time_of_day=datetime.now(timezone.utc),
            weather_forecast=self.weather_forecast,
            hour_avg_load=hour_avg_load,
        )

        # Delegate to active strategy
        decision = self._active_strategy.decide(ctx)
        self._last_decision_notes = decision.notes

        if not decision.should_act:
            return

        target = decision.target_load_w
        reason = decision.reason

        logger.info(
            "[%s] Adjust: meter_avg=%.0fW load=%d→%dW (%s) %s",
            self._active_strategy_name, avg_10, current_load, target,
            reason, decision.notes,
        )
        await self._set_load(target, reason, meter_w, current_load)

    # ---- Load adjustment helpers -------------------------------------------

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

    # ---- Status for dashboard ----------------------------------------------

    def get_status(self) -> dict:
        reading = self.iometer.latest
        meter_w = reading.power_w if reading else None
        avg_30 = self.iometer.get_average_power(30)
        avg_60 = self.iometer.get_average_power(60)
        return {
            "auto_enabled": self._auto_enabled,
            "state": self._state,
            "active_strategy": self._active_strategy_name,
            "available_strategies": [s["name"] for s in list_strategies()],
            "total_adjustments": self.total_adjustments,
            "total_spikes_detected": self.total_spikes_detected,
            "total_spikes_ignored": self.total_spikes_ignored,
            "last_action": self.last_action,
            "last_action_time": self.last_action_time,
            "last_decision_notes": self._last_decision_notes,
            "baseline_load_w": self._baseline_load_w,
            "meter_avg_30s": round(avg_30, 1) if avg_30 is not None else None,
            "meter_avg_60s": round(avg_60, 1) if avg_60 is not None else None,
            "meter_instant_w": round(meter_w, 1) if meter_w is not None else None,
            "plug_total_w": round(self._plug_total_w, 1),
            "energy": self._energy_tracker.get_today_stats(),
        }


# ---------------------------------------------------------------------------
# Energy Tracker — calculates import/export from meter readings
# ---------------------------------------------------------------------------

class EnergyTracker:
    """Calculates grid import/export energy from meter readings.

    Import: Uses meter cumulative counter OBIS 1-0:1.8.0 (difference
    between current value and start-of-day value).  This is the most
    accurate method since the meter itself integrates power.

    Export: The meter does not provide OBIS 2.8.0, so export is
    calculated via trapezoidal integration of negative power readings
    (power_w < 0 means feeding into the grid).

    Resets daily. Persists to DB periodically.
    """

    def __init__(self) -> None:
        self._last_reading_time: float | None = None
        self._last_power_w: float | None = None
        self._today_date: str = ""
        self._import_wh: float = 0.0
        self._export_wh: float = 0.0
        self._consumption_wh: float = 0.0
        self._last_persist_time: float = 0.0
        # Meter counter baseline (start-of-day value for OBIS 1.8.0)
        self._day_start_consumption_wh: float | None = None
        self._import_from_counter: bool = False
        # Restore baseline from DB (survives restarts)
        self._load_day_start()

    def _load_day_start(self) -> None:
        """Load start-of-day meter counter value from DB config."""
        today = datetime.now(db.get_display_tz()).strftime("%Y-%m-%d")
        saved_date = db.get_config("meter_day_start_date", "")
        if saved_date == today:
            v = db.get_config("meter_day_start_consumption_wh", "")
            if v:
                self._day_start_consumption_wh = float(v)
                self._today_date = today
                logger.info(
                    "EnergyTracker restored day-start counter for %s: "
                    "consumption=%.1f Wh",
                    today, self._day_start_consumption_wh,
                )
            # Restore accumulated export (trapezoidal, lost on restart)
            v = db.get_config("meter_today_export_wh", "")
            if v:
                self._export_wh = float(v)

    def _save_day_start(self) -> None:
        """Persist start-of-day meter counter value to DB config."""
        db.set_config("meter_day_start_date", self._today_date)
        if self._day_start_consumption_wh is not None:
            db.set_config("meter_day_start_consumption_wh",
                          str(self._day_start_consumption_wh))

    def update(self, iometer: IOMeterService, anker: AnkerService) -> None:
        """Called every tick (~5s). Updates import/export from meter."""
        reading = iometer.latest
        if reading is None:
            return

        now = time.monotonic()
        today = datetime.now(db.get_display_tz()).strftime("%Y-%m-%d")

        # --- Day rollover ---
        if today != self._today_date:
            self._today_date = today
            self._import_wh = 0.0
            self._export_wh = 0.0
            self._consumption_wh = 0.0
            self._day_start_consumption_wh = reading.total_consumption_wh
            self._save_day_start()
            self._last_reading_time = now
            self._last_power_w = reading.power_w
            return

        # --- Capture baseline on first reading with counter ---
        if (self._day_start_consumption_wh is None
                and reading.total_consumption_wh is not None):
            self._day_start_consumption_wh = reading.total_consumption_wh
            self._save_day_start()

        # --- Import from meter counter (OBIS 1.8.0) ---
        if (self._day_start_consumption_wh is not None
                and reading.total_consumption_wh is not None):
            self._import_wh = max(
                0, reading.total_consumption_wh - self._day_start_consumption_wh)
            self._import_from_counter = True
        else:
            self._import_from_counter = False

        # --- Trapezoidal integration for export + home consumption ---
        if self._last_reading_time is not None and self._last_power_w is not None:
            dt_hours = (now - self._last_reading_time) / 3600.0
            if 0 < dt_hours < 0.5:  # max 30min gap
                avg_power = (self._last_power_w + reading.power_w) / 2.0

                # Export: always trapezoidal (no 2.8.0 counter available)
                if avg_power < 0:
                    self._export_wh += abs(avg_power * dt_hours)

                # Import fallback: trapezoidal when no counter
                if not self._import_from_counter and avg_power > 0:
                    self._import_wh += avg_power * dt_hours

                # Estimate home consumption (always trapezoidal)
                load_w = anker.current_load_w
                home_power = load_w + avg_power
                if home_power > 0:
                    self._consumption_wh += home_power * dt_hours

        self._last_reading_time = now
        self._last_power_w = reading.power_w

        # Persist to DB every 5 minutes
        if now - self._last_persist_time > 300:
            self._persist()
            self._last_persist_time = now

    def _persist(self) -> None:
        """Save accumulated energy to daily_energy table."""
        if not self._today_date:
            return
        try:
            existing = db.get_daily_energy_for_date(self._today_date)
            data = existing or {}
            data["grid_import_wh"] = max(data.get("grid_import_wh", 0), self._import_wh)
            data["grid_export_wh"] = max(data.get("grid_export_wh", 0), self._export_wh)
            data["home_consumption_wh"] = max(data.get("home_consumption_wh", 0), self._consumption_wh)
            db.upsert_daily_energy(self._today_date, data)
        except Exception as exc:
            logger.debug("Energy tracker persist error: %s", exc)

    def get_today_stats(self) -> dict:
        return {
            "grid_import_wh": round(self._import_wh, 1),
            "grid_export_wh": round(self._export_wh, 1),
            "home_consumption_wh": round(self._consumption_wh, 1),
            "grid_import_kwh": round(self._import_wh / 1000, 3),
            "grid_export_kwh": round(self._export_wh / 1000, 3),
            "home_consumption_kwh": round(self._consumption_wh / 1000, 3),
            "import_from_counter": self._import_from_counter,
        }
