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
from app.routes.api_routes import router as api_router

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
        except Exception as exc:
            logger.exception("Anker poller error: %s", exc)
        await asyncio.sleep(fast_interval)


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

    # Services
    iometer = IOMeterService()
    anker = AnkerService()
    strategy = StrategyEngine(iometer, anker)

    # Attach to app.state so routes can access them
    app.state.iometer = iometer
    app.state.anker = anker
    app.state.strategy = strategy

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
