"""FastAPI application entry point.

Wires up: IOMeter service, Anker service, Strategy engine, Dash dashboard.
Background tasks are started/stopped via the FastAPI lifespan context.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

from app import database as db
from app.config import anker_cfg, iometer_cfg
from app.services.iometer_service import IOMeterService
from app.services.anker_service import AnkerService
from app.services.strategy_engine import StrategyEngine
from app.services.weather_service import WeatherService
from app.routes.api_routes import router as api_router
from app.routes.esp32_routes import router as esp32_router
from app.routes.iometer_routes import router as iometer_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _anker_poller(anker: AnkerService, fast_interval: float = 30.0,
                        slow_interval: float = 600.0) -> None:
    """Periodically refresh Anker cloud data. Auto-retries init on failure."""
    cycle = 0
    slow_every = max(1, int(slow_interval / fast_interval))
    while True:
        try:
            if not anker._initialized:
                logger.info("Anker not initialized, attempting (re-)init…")
                await anker.initialize()
                if not anker._initialized:
                    logger.warning("Anker init failed, retrying in 60s")
                    await asyncio.sleep(60)
                    continue
            await anker.refresh_data()
            cycle += 1
            # Run on first cycle (cycle==1) and then every slow_every cycles
            if cycle == 1 or cycle % slow_every == 0:
                await anker.refresh_details()
                # Persist daily energy to DB for historical chart
                _persist_daily_energy(anker)
        except Exception as exc:
            logger.exception("Anker poller error: %s", exc)
        await asyncio.sleep(fast_interval)


def _persist_daily_energy(anker: AnkerService) -> None:
    """Save today's energy totals from Anker cloud to the daily_energy table.

    Grid import/export from the Anker cloud API is often 0 (Anker doesn't
    read the smart meter directly).  Preserve any meter-derived values that
    the EnergyTracker already wrote so they don't get overwritten with 0.
    """
    from datetime import date
    today_str = date.today().isoformat()

    # Read existing row so we can preserve meter-based import/export
    existing = db.get_daily_energy_for_date(today_str) or {}

    anker_import = anker.today_grid_import_kwh * 1000
    anker_export = anker.today_grid_export_kwh * 1000

    data = {
        "solar_production_wh": anker.today_solar_kwh * 1000,
        "battery_charge_wh": anker.today_charge_kwh * 1000,
        "battery_discharge_wh": anker.today_discharge_kwh * 1000,
        # Keep the larger of Anker cloud value vs existing meter-derived value
        "grid_import_wh": max(anker_import, existing.get("grid_import_wh", 0)),
        "grid_export_wh": max(anker_export, existing.get("grid_export_wh", 0)),
        "home_consumption_wh": max(
            anker.today_usage_kwh * 1000,
            existing.get("home_consumption_wh", 0),
        ),
    }
    # Only persist if we have any data
    if any(v > 0 for v in data.values()):
        try:
            db.upsert_daily_energy(today_str, data)
        except Exception as exc:
            logger.error("Failed to persist daily energy: %s", exc)


async def _weather_poller(weather: WeatherService, strategy: StrategyEngine) -> None:
    """Refresh weather forecast every hour and feed to strategy engine."""
    while True:
        try:
            forecast = await weather.get_forecast()
            if forecast:
                strategy.weather_forecast = forecast
                logger.debug("Weather forecast updated: %s", forecast)
        except Exception as exc:
            logger.warning("Weather poller error: %s", exc)
        await asyncio.sleep(3600)  # once per hour


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # --- Startup ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting Solar Load Controller …")

    # Database
    db.init_db()
    db.backfill_daily_energy_from_readings()

    # Services
    iometer = IOMeterService()
    anker = AnkerService()
    strategy = StrategyEngine(iometer, anker)
    weather = WeatherService()

    # Attach to app.state so routes can access them
    app.state.iometer = iometer
    app.state.anker = anker
    app.state.strategy = strategy
    app.state.weather = weather

    # Initialize Anker API (non-blocking — will retry if fails)
    try:
        await anker.initialize()
    except Exception as exc:
        logger.error("Anker init failed (will retry in poller): %s", exc)

    # Launch background tasks
    tasks = [
        asyncio.create_task(iometer.start_polling(), name="iometer_poller"),
        asyncio.create_task(_anker_poller(anker), name="anker_poller"),
        asyncio.create_task(strategy.start(), name="strategy_engine"),
        asyncio.create_task(_weather_poller(weather, strategy), name="weather_poller"),
    ]

    # Also fetch IOMeter status once on startup
    asyncio.create_task(iometer.fetch_status())

    logger.info("All background tasks started")

    yield  # ---- app is running ----

    # --- Shutdown ---
    logger.info("Shutting down …")
    strategy.stop()
    iometer.stop_polling()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await iometer.close()
    await anker.close()
    await weather.close()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Solar Load Controller",
        version="1.0.0",
        lifespan=lifespan,
    )

    # REST API
    app.include_router(api_router)
    app.include_router(esp32_router)
    app.include_router(iometer_router)

    # Mount Dash dashboard
    try:
        from app.dashboard.app import create_dash_app
        dash_app = create_dash_app()
        app.mount("/dashboard", WSGIMiddleware(dash_app.server))
        logger.info("Dash dashboard mounted at /dashboard")
    except Exception as exc:
        logger.error("Failed to mount Dash dashboard: %s", exc)

    # Root redirect → dashboard
    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/dashboard/")

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# For running directly: python -m app.main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    application = create_app()
    uvicorn.run(application, host="0.0.0.0", port=8000)
