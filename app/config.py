"""Configuration management for Solar Load Controller.

All strategy parameters and app settings are stored in SQLite
and can be modified at runtime from the dashboard.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (before reading env vars)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "solar_controller.db"
AUTH_CACHE_DIR = Path(__file__).resolve().parent / "api" / "authcache"


@dataclass
class AnkerConfig:
    email: str = os.environ.get("ANKER_EMAIL", "")
    password: str = os.environ.get("ANKER_PASSWORD", "")
    country: str = os.environ.get("ANKER_COUNTRY", "DE")


@dataclass
class IOMeterConfig:
    host: str = os.environ.get("IOMETER_HOST", "192.168.178.96")
    polling_interval_s: float = 5.0
    request_timeout_s: float = 10.0


@dataclass
class StrategyDefaults:
    """Default values – persisted in SQLite config table on first run."""

    # Polling / timing
    polling_interval_s: float = 5.0          # IOMeter read frequency
    reaction_delay_s: float = 15.0           # wait before reacting to sustained change
    spike_observation_period_s: float = 90.0 # observation window for spike classification
    cooldown_period_s: float = 30.0          # mandatory wait after load change
    rolling_window_s: float = 120.0          # meter-readings buffer length

    # Thresholds
    min_change_threshold_w: float = 20.0     # hysteresis – ignore smaller changes
    emergency_threshold_w: float = 500.0     # override cooldown for large spikes
    grid_target_w: float = 0.0             # target meter reading (zero grid)

    # Load limits (Anker SB2 hardware / German regulations)
    max_load_w: int = 800
    min_load_w: int = 0
    load_step_w: int = 10

    # Cost
    electricity_price_eur_kwh: float = 0.28
    feed_in_tariff_eur_kwh: float = 0.082    # Einspeisevergütung

    # Auto-mode
    auto_mode_enabled: bool = True

    # IOMeter data source: 'local' = poll via LAN, 'esp32' = receive via ESP32 API
    iometer_source: str = 'local'
    iometer_host: str = '192.168.178.96'

    # Anker API refresh intervals
    anker_fast_poll_s: float = 30.0          # site data refresh
    anker_slow_poll_s: float = 300.0         # device details / energy refresh


# Singletons – loaded once, updated from DB at runtime
anker_cfg = AnkerConfig()
iometer_cfg = IOMeterConfig()
strategy_defaults = StrategyDefaults()
