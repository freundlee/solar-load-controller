"""Strategy plugins — pluggable algorithms for load control.

Each strategy encapsulates a different approach to deciding the target home load.
The StrategyEngine selects the active strategy based on configuration.

All strategies receive a `StrategyContext` and return a `StrategyDecision`.
"""

import logging
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context & Decision data
# ---------------------------------------------------------------------------

@dataclass
class StrategyContext:
    """All inputs available to a strategy for decision-making."""
    # Meter
    meter_instant_w: float          # current instant reading
    meter_avg_10s: float            # 10-second average
    meter_avg_30s: float | None     # 30-second average
    meter_avg_60s: float | None     # 60-second average
    meter_history: list[float] = field(default_factory=list)  # recent readings (up to 120s)

    # Anker state
    current_load_w: int = 0         # current home load preset
    battery_soc: float = 0.0        # battery state of charge (0-100%)
    solar_power_w: float = 0.0      # current solar production
    battery_power_w: float = 0.0    # battery charge/discharge power

    # Config
    grid_target_w: float = -10.0    # target grid reading (slight export)
    max_load_w: int = 800
    min_load_w: int = 0
    load_step_w: int = 10
    min_change_threshold_w: float = 20.0
    cooldown_period_s: float = 45.0
    emergency_threshold_w: float = 500.0

    # Timing
    seconds_since_last_change: float = 999.0
    time_of_day: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Weather (optional, for weather-aware strategy)
    weather_forecast: dict | None = None  # {tomorrow_solar_hours, cloud_cover_pct, etc.}

    # Historical patterns (optional)
    hour_avg_load: float | None = None   # avg load for this hour historically
    hour_avg_consumption: float | None = None  # avg consumption for this hour


@dataclass
class StrategyDecision:
    """Output from a strategy."""
    target_load_w: int
    reason: str                     # e.g. "auto_increase", "conservative_hold", etc.
    confidence: float = 1.0         # 0-1, how confident the strategy is
    should_act: bool = True         # False means skip this cycle
    notes: str = ""                 # debug/logging info


# ---------------------------------------------------------------------------
# Base Strategy class
# ---------------------------------------------------------------------------

class BaseStrategy(ABC):
    """Base class for all strategies."""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def decide(self, ctx: StrategyContext) -> StrategyDecision:
        """Given the current context, return a load decision."""
        ...

    @staticmethod
    def snap_load(value: float, max_load: int, min_load: int, step: int) -> int:
        """Clamp and round to nearest step."""
        clamped = max(min_load, min(max_load, value))
        return round(clamped / step) * step


# ---------------------------------------------------------------------------
# Strategy: Proportional (original default)
# ---------------------------------------------------------------------------

class ProportionalStrategy(BaseStrategy):
    """Original direct proportional controller.

    target_load = current_load + (meter_avg_10s - grid_target)

    Simple and responsive, but can oscillate when load changes rapidly.
    """

    name = "proportional"
    description = "Direct proportional: adjusts load by the meter delta. Fast response, may oscillate."

    def decide(self, ctx: StrategyContext) -> StrategyDecision:
        # Cooldown check (unless emergency)
        is_emergency = ctx.meter_avg_10s > ctx.emergency_threshold_w
        if not is_emergency and ctx.seconds_since_last_change < ctx.cooldown_period_s:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="cooldown",
                should_act=False,
            )

        delta = ctx.meter_avg_10s - ctx.grid_target_w
        raw_target = ctx.current_load_w + delta
        target = self.snap_load(raw_target, ctx.max_load_w, ctx.min_load_w, ctx.load_step_w)

        if abs(target - ctx.current_load_w) < ctx.min_change_threshold_w:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="within_threshold",
                should_act=False,
            )

        reason = "auto_emergency" if is_emergency else (
            "auto_increase" if delta > 0 else "auto_decrease"
        )
        return StrategyDecision(target_load_w=target, reason=reason)


# ---------------------------------------------------------------------------
# Strategy: Conservative (minimize grid import at all costs)
# ---------------------------------------------------------------------------

class ConservativeStrategy(BaseStrategy):
    """Conservative strategy — absolute priority: never use grid power.

    Key differences from proportional:
    - Uses the HIGHER of avg_10s and avg_30s to avoid lagging
    - Adds a safety buffer (extra watts above meter reading) when increasing
    - Reduces load aggressively on ANY grid import
    - Never reduces load below a minimum floor when battery is healthy
    - Slower to decrease load (avoids the scenario where load drops then
      consumption rises again causing grid import)
    """

    name = "conservative"
    description = "Minimize grid import. Adds safety buffer, slower to decrease. Best when grid avoidance is priority."

    def decide(self, ctx: StrategyContext) -> StrategyDecision:
        is_emergency = ctx.meter_avg_10s > ctx.emergency_threshold_w

        if not is_emergency and ctx.seconds_since_last_change < ctx.cooldown_period_s:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="cooldown",
                should_act=False,
            )

        # Use the highest average to be more responsive to imports
        avg = max(ctx.meter_avg_10s, ctx.meter_avg_30s or ctx.meter_avg_10s)

        # Safety buffer: when grid is importing, add extra to compensate for lag
        safety_buffer = 50 if avg > 20 else 20 if avg > 0 else 0

        # When battery is healthy (>30%), keep a minimum floor to avoid
        # the "drop load → consumption rises → grid import" cycle
        min_floor = 0
        if ctx.battery_soc > 30:
            min_floor = min(ctx.current_load_w, 100)  # don't drop below current-100 or 100W

        delta = avg - ctx.grid_target_w
        raw_target = ctx.current_load_w + delta + safety_buffer

        # For decreasing load: be more cautious (only decrease by 70% of delta)
        if raw_target < ctx.current_load_w:
            decrease_amount = ctx.current_load_w - raw_target
            cautious_decrease = decrease_amount * 0.7
            raw_target = ctx.current_load_w - cautious_decrease
            # Don't go below the minimum floor
            raw_target = max(raw_target, min_floor)

        target = self.snap_load(raw_target, ctx.max_load_w, ctx.min_load_w, ctx.load_step_w)

        if abs(target - ctx.current_load_w) < ctx.min_change_threshold_w:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="within_threshold",
                should_act=False,
            )

        reason = "conservative_emergency" if is_emergency else (
            "conservative_increase" if target > ctx.current_load_w else "conservative_decrease"
        )
        return StrategyDecision(
            target_load_w=target,
            reason=reason,
            notes=f"avg={avg:.0f} buffer={safety_buffer} floor={min_floor}",
        )


# ---------------------------------------------------------------------------
# Strategy: Smoothing (handles rapid fluctuations)
# ---------------------------------------------------------------------------

class SmoothingStrategy(BaseStrategy):
    """Smoothing strategy — handles rapid load fluctuations.

    When consumption changes rapidly:
    - Uses a longer averaging window (60s) as baseline
    - Detects fluctuation patterns and holds steady at a percentile
    - Only adjusts when the trend is clearly established
    - Calculates a "stability score" — lower score = more fluctuation = less aggressive changes

    Best for: households with frequent on/off appliances (AC, pumps, etc.)
    """

    name = "smoothing"
    description = "Handles rapid fluctuations. Uses longer averages and stability detection. Best for variable loads."

    def decide(self, ctx: StrategyContext) -> StrategyDecision:
        is_emergency = ctx.meter_avg_10s > ctx.emergency_threshold_w

        if not is_emergency and ctx.seconds_since_last_change < ctx.cooldown_period_s * 1.5:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="cooldown",
                should_act=False,
            )

        # Calculate stability: std deviation of recent readings
        history = ctx.meter_history
        if len(history) >= 6:
            stdev = statistics.stdev(history[-12:]) if len(history) >= 12 else statistics.stdev(history[-6:])
            mean = statistics.mean(history[-12:]) if len(history) >= 12 else statistics.mean(history[-6:])
        else:
            stdev = 50.0  # assume moderate fluctuation
            mean = ctx.meter_avg_10s

        # Stability score: 0 = very unstable, 1 = very stable
        stability = max(0.0, min(1.0, 1.0 - (stdev / 300.0)))

        # Choose averaging window based on stability
        if stability > 0.7:
            # Stable: use 10s average, respond normally
            effective_avg = ctx.meter_avg_10s
        elif stability > 0.4:
            # Moderate: use 30s average
            effective_avg = ctx.meter_avg_30s or ctx.meter_avg_10s
        else:
            # Highly unstable: use 60s average + p75 bias toward import handling
            base_avg = ctx.meter_avg_60s or ctx.meter_avg_30s or ctx.meter_avg_10s
            # Bias toward the upper end (more likely to need power)
            if len(history) >= 6:
                p75 = sorted(history[-12:] if len(history) >= 12 else history[-6:])[
                    int(len(history[-12:] if len(history) >= 12 else history[-6:]) * 0.75)
                ]
                effective_avg = (base_avg + p75) / 2
            else:
                effective_avg = base_avg

        # Scale adjustment by stability: less stable = smaller steps
        delta = effective_avg - ctx.grid_target_w
        adjusted_delta = delta * (0.5 + 0.5 * stability)

        raw_target = ctx.current_load_w + adjusted_delta
        target = self.snap_load(raw_target, ctx.max_load_w, ctx.min_load_w, ctx.load_step_w)

        # Higher threshold for unstable conditions
        effective_threshold = ctx.min_change_threshold_w * (1.0 + (1.0 - stability))

        if abs(target - ctx.current_load_w) < effective_threshold:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="smoothing_hold",
                should_act=False,
                notes=f"stability={stability:.2f} stdev={stdev:.0f}",
            )

        reason = "smoothing_emergency" if is_emergency else (
            f"smoothing_adjust"
        )
        return StrategyDecision(
            target_load_w=target,
            reason=reason,
            confidence=stability,
            notes=f"stability={stability:.2f} stdev={stdev:.0f} eff_avg={effective_avg:.0f}",
        )


# ---------------------------------------------------------------------------
# Strategy: Battery Guard (protect battery while maximizing usage)
# ---------------------------------------------------------------------------

class BatteryGuardStrategy(BaseStrategy):
    """Battery Guard — context-aware load control based on battery SOC and time.

    Rules:
    - At night (no solar): scale load based on battery SOC
      - SOC > 80%: full proportional response + buffer
      - SOC 50-80%: proportional response, no buffer
      - SOC 20-50%: conservative, reduce max load proportionally
      - SOC < 20%: minimal load, preserve battery for essentials
    - During day (solar available): standard proportional
    - Weather-aware: if tomorrow is sunny, can be more aggressive at night
    """

    name = "battery_guard"
    description = "SOC-aware load control. Scales aggressiveness with battery level. Best for overnight optimization."

    def decide(self, ctx: StrategyContext) -> StrategyDecision:
        is_emergency = ctx.meter_avg_10s > ctx.emergency_threshold_w

        if not is_emergency and ctx.seconds_since_last_change < ctx.cooldown_period_s:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="cooldown",
                should_act=False,
            )

        # Determine if we're in "night mode" (no meaningful solar production)
        is_night = ctx.solar_power_w < 20
        soc = ctx.battery_soc

        # Weather bonus: if tomorrow has good solar forecast, be more aggressive tonight
        weather_bonus = 0
        if ctx.weather_forecast and is_night:
            tomorrow_hours = ctx.weather_forecast.get("tomorrow_solar_hours", 0)
            if tomorrow_hours >= 6:
                weather_bonus = 10  # can afford to use more battery
            elif tomorrow_hours >= 4:
                weather_bonus = 5

        if is_night:
            # Night mode: scale response by SOC
            if soc > 80:
                # Plenty of battery — full proportional + buffer for responsiveness
                buffer = 30 + weather_bonus
                effective_max = ctx.max_load_w
            elif soc > 50:
                # Moderate — standard proportional, slightly reduced max
                buffer = weather_bonus
                effective_max = int(ctx.max_load_w * 0.85)
            elif soc > 20:
                # Low — conservative, reduced max load
                buffer = 0
                effective_max = int(ctx.max_load_w * (soc / 100.0))
            else:
                # Critical — minimal load
                buffer = 0
                effective_max = min(100, ctx.max_load_w)
        else:
            # Daytime: standard proportional with solar
            buffer = 20
            effective_max = ctx.max_load_w

        avg = ctx.meter_avg_10s
        delta = avg - ctx.grid_target_w + buffer
        raw_target = ctx.current_load_w + delta
        target = self.snap_load(raw_target, effective_max, ctx.min_load_w, ctx.load_step_w)

        if abs(target - ctx.current_load_w) < ctx.min_change_threshold_w:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="battery_guard_hold",
                should_act=False,
            )

        reason = "battery_guard_emergency" if is_emergency else (
            f"battery_guard_{'night' if is_night else 'day'}"
        )
        return StrategyDecision(
            target_load_w=target,
            reason=reason,
            notes=f"soc={soc:.0f}% night={is_night} eff_max={effective_max} bonus={weather_bonus}",
        )


# ---------------------------------------------------------------------------
# Strategy: Predictive (uses historical patterns)
# ---------------------------------------------------------------------------

class PredictiveStrategy(BaseStrategy):
    """Predictive strategy — uses historical consumption patterns.

    Looks at what typically happens at this hour/day and pre-positions load
    rather than waiting for meter to show import/export.

    Falls back to proportional for current-cycle adjustment, but biases
    the target toward historical patterns.
    """

    name = "predictive"
    description = "Uses historical patterns to pre-position load. Reduces lag by anticipating demand. Best with 7+ days of data."

    def decide(self, ctx: StrategyContext) -> StrategyDecision:
        is_emergency = ctx.meter_avg_10s > ctx.emergency_threshold_w

        if not is_emergency and ctx.seconds_since_last_change < ctx.cooldown_period_s:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="cooldown",
                should_act=False,
            )

        # Proportional component (react to current state)
        avg = ctx.meter_avg_10s
        delta = avg - ctx.grid_target_w
        reactive_target = ctx.current_load_w + delta

        # Predictive component (historical bias)
        if ctx.hour_avg_load is not None:
            # Blend reactive with historical:
            # weight more toward historical when stability is low
            history_weight = 0.3  # 30% historical, 70% reactive
            predictive_target = (reactive_target * (1 - history_weight) +
                                 ctx.hour_avg_load * history_weight)
        else:
            predictive_target = reactive_target

        target = self.snap_load(predictive_target, ctx.max_load_w, ctx.min_load_w, ctx.load_step_w)

        if abs(target - ctx.current_load_w) < ctx.min_change_threshold_w:
            return StrategyDecision(
                target_load_w=ctx.current_load_w,
                reason="predictive_hold",
                should_act=False,
            )

        reason = "predictive_emergency" if is_emergency else "predictive_adjust"
        return StrategyDecision(
            target_load_w=target,
            reason=reason,
            notes=f"hist_load={ctx.hour_avg_load} reactive={reactive_target:.0f}",
        )


# ---------------------------------------------------------------------------
# Strategy Registry
# ---------------------------------------------------------------------------

STRATEGIES: dict[str, type[BaseStrategy]] = {
    "proportional": ProportionalStrategy,
    "conservative": ConservativeStrategy,
    "smoothing": SmoothingStrategy,
    "battery_guard": BatteryGuardStrategy,
    "predictive": PredictiveStrategy,
}


def get_strategy(name: str) -> BaseStrategy:
    """Get an instantiated strategy by name."""
    cls = STRATEGIES.get(name, ProportionalStrategy)
    return cls()


def list_strategies() -> list[dict]:
    """Return metadata about available strategies."""
    return [
        {"name": cls.name, "description": cls.description}
        for cls in STRATEGIES.values()
    ]
