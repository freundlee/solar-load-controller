"""SQLite database setup and access helpers."""

import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DB_PATH, StrategyDefaults

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meter_readings (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             TIMESTAMP NOT NULL,
    power_w               REAL NOT NULL,
    total_consumption_wh  REAL,
    total_production_wh   REAL,
    UNIQUE(timestamp)
);

CREATE TABLE IF NOT EXISTS load_changes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TIMESTAMP NOT NULL,
    old_load_w        INTEGER NOT NULL,
    new_load_w        INTEGER NOT NULL,
    reason            TEXT NOT NULL,
    meter_reading_w   REAL,
    solar_production_w REAL,
    battery_soc       REAL
);

CREATE TABLE IF NOT EXISTS appliance_profiles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    power_min_w       REAL NOT NULL,
    power_max_w       REAL NOT NULL,
    typical_duration_s INTEGER,
    max_duration_s    INTEGER,
    action            TEXT NOT NULL DEFAULT 'observe',
    occurrences       INTEGER DEFAULT 0,
    last_seen         TIMESTAMP,
    created_at        TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS power_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time     TIMESTAMP NOT NULL,
    end_time       TIMESTAMP,
    peak_power_w   REAL NOT NULL,
    avg_power_w    REAL,
    duration_s     INTEGER,
    profile_id     INTEGER REFERENCES appliance_profiles(id),
    action_taken   TEXT,
    created_at     TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_energy (
    date                TEXT PRIMARY KEY,
    solar_production_wh REAL DEFAULT 0,
    battery_charge_wh   REAL DEFAULT 0,
    battery_discharge_wh REAL DEFAULT 0,
    grid_import_wh      REAL DEFAULT 0,
    grid_export_wh      REAL DEFAULT 0,
    home_consumption_wh REAL DEFAULT 0,
    cost_saved_eur      REAL DEFAULT 0,
    avg_load_w          REAL DEFAULT 0,
    load_changes_count  INTEGER DEFAULT 0,
    updated_at          TIMESTAMP DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_meter_readings_ts ON meter_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_load_changes_ts   ON load_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_power_events_ts   ON power_events(start_time);
"""

# ---------------------------------------------------------------------------
# Default appliance profiles
# ---------------------------------------------------------------------------

_DEFAULT_PROFILES = [
    ("Microwave",         1400, 2000,  90, 180, "ignore"),
    ("Oven",              1800, 3500, 600, 7200, "adjust"),
    ("Induction Cooktop", 1200, 3500, 300, 5400, "adjust"),
    ("Kettle",            1800, 2400,  90, 180, "ignore"),
    ("Hair Dryer",        1500, 2200,  60, 300, "ignore"),
    ("Vacuum Cleaner",    800,  2000, 120, 600, "observe"),
]

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Init / seed
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create tables and seed defaults if missing."""
    with get_db() as conn:
        conn.executescript(_SCHEMA_SQL)

        # Seed strategy defaults
        defaults = StrategyDefaults()
        for key, value in defaults.__dict__.items():
            conn.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )

        # Seed appliance profiles
        existing = conn.execute("SELECT COUNT(*) FROM appliance_profiles").fetchone()[0]
        if existing == 0:
            for name, pmin, pmax, tdur, mdur, action in _DEFAULT_PROFILES:
                conn.execute(
                    """INSERT INTO appliance_profiles
                       (name, power_min_w, power_max_w, typical_duration_s, max_duration_s, action)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (name, pmin, pmax, tdur, mdur, action),
                )

    logger.info("Database initialized at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def get_config(key: str, default: Any = None) -> Any:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])


def set_config(key: str, value: Any) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO config (key, value, updated_at) VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, json.dumps(value)),
        )


def get_all_config() -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM config").fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}


# ---------------------------------------------------------------------------
# Meter readings
# ---------------------------------------------------------------------------


def insert_meter_reading(power_w: float, total_consumption_wh: float | None = None,
                         total_production_wh: float | None = None) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO meter_readings (timestamp, power_w, total_consumption_wh, total_production_wh)
               VALUES (?, ?, ?, ?)""",
            (ts, power_w, total_consumption_wh, total_production_wh),
        )


def get_recent_meter_readings(seconds: int = 300) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM meter_readings
               WHERE timestamp >= datetime('now', ?)
               ORDER BY timestamp DESC""",
            (f"-{seconds} seconds",),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Load changes
# ---------------------------------------------------------------------------


def insert_load_change(old_load: int, new_load: int, reason: str,
                       meter_reading: float | None = None,
                       solar_production: float | None = None,
                       battery_soc: float | None = None) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO load_changes
               (timestamp, old_load_w, new_load_w, reason, meter_reading_w, solar_production_w, battery_soc)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts, old_load, new_load, reason, meter_reading, solar_production, battery_soc),
        )


def get_load_changes(hours: int = 24) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM load_changes
               WHERE timestamp >= datetime('now', ?)
               ORDER BY timestamp DESC""",
            (f"-{hours} hours",),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Appliance profiles
# ---------------------------------------------------------------------------


def get_appliance_profiles() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM appliance_profiles ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def upsert_appliance_profile(profile: dict) -> int:
    with get_db() as conn:
        if profile.get("id"):
            conn.execute(
                """UPDATE appliance_profiles SET
                   name=?, power_min_w=?, power_max_w=?, typical_duration_s=?,
                   max_duration_s=?, action=? WHERE id=?""",
                (profile["name"], profile["power_min_w"], profile["power_max_w"],
                 profile.get("typical_duration_s"), profile.get("max_duration_s"),
                 profile.get("action", "observe"), profile["id"]),
            )
            return profile["id"]
        else:
            cur = conn.execute(
                """INSERT INTO appliance_profiles
                   (name, power_min_w, power_max_w, typical_duration_s, max_duration_s, action)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (profile["name"], profile["power_min_w"], profile["power_max_w"],
                 profile.get("typical_duration_s"), profile.get("max_duration_s"),
                 profile.get("action", "observe")),
            )
            return cur.lastrowid


def delete_appliance_profile(profile_id: int) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM appliance_profiles WHERE id = ?", (profile_id,))


# ---------------------------------------------------------------------------
# Power events
# ---------------------------------------------------------------------------


def insert_power_event(start_time: str, peak_power: float, profile_id: int | None = None,
                       action_taken: str | None = None) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO power_events (start_time, peak_power_w, profile_id, action_taken)
               VALUES (?, ?, ?, ?)""",
            (start_time, peak_power, profile_id, action_taken),
        )
        return cur.lastrowid


def update_power_event(event_id: int, end_time: str, avg_power: float,
                       duration_s: int) -> None:
    with get_db() as conn:
        conn.execute(
            """UPDATE power_events SET end_time=?, avg_power_w=?, duration_s=?
               WHERE id=?""",
            (end_time, avg_power, duration_s, event_id),
        )


def get_recent_power_events(hours: int = 24) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT pe.*, ap.name as profile_name FROM power_events pe
               LEFT JOIN appliance_profiles ap ON pe.profile_id = ap.id
               WHERE pe.start_time >= datetime('now', ?)
               ORDER BY pe.start_time DESC""",
            (f"-{hours} hours",),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Daily energy
# ---------------------------------------------------------------------------


def upsert_daily_energy(date_str: str, data: dict) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO daily_energy (date, solar_production_wh, battery_charge_wh,
               battery_discharge_wh, grid_import_wh, grid_export_wh, home_consumption_wh,
               cost_saved_eur, avg_load_w, load_changes_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(date) DO UPDATE SET
               solar_production_wh=excluded.solar_production_wh,
               battery_charge_wh=excluded.battery_charge_wh,
               battery_discharge_wh=excluded.battery_discharge_wh,
               grid_import_wh=excluded.grid_import_wh,
               grid_export_wh=excluded.grid_export_wh,
               home_consumption_wh=excluded.home_consumption_wh,
               cost_saved_eur=excluded.cost_saved_eur,
               avg_load_w=excluded.avg_load_w,
               load_changes_count=excluded.load_changes_count,
               updated_at=datetime('now')""",
            (date_str,
             data.get("solar_production_wh", 0),
             data.get("battery_charge_wh", 0),
             data.get("battery_discharge_wh", 0),
             data.get("grid_import_wh", 0),
             data.get("grid_export_wh", 0),
             data.get("home_consumption_wh", 0),
             data.get("cost_saved_eur", 0),
             data.get("avg_load_w", 0),
             data.get("load_changes_count", 0)),
        )


def get_daily_energy(days: int = 30) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM daily_energy
               WHERE date >= date('now', ?)
               ORDER BY date DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]
