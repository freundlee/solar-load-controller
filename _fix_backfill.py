"""One-time script: reset and recalculate import/export from meter readings."""
import sqlite3
from app.database import backfill_daily_energy_from_readings, init_db

conn = sqlite3.connect("data/solar_controller.db")
conn.execute("UPDATE daily_energy SET grid_import_wh = 0, grid_export_wh = 0 WHERE date < date('now')")
conn.commit()
conn.close()
print("Reset historical import/export to 0")

init_db()
n = backfill_daily_energy_from_readings()
print(f"Backfilled {n} dates")

# Verify
conn = sqlite3.connect("data/solar_controller.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT date, grid_import_wh, grid_export_wh FROM daily_energy ORDER BY date").fetchall()
for r in rows:
    print(dict(r))
conn.close()
