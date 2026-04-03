import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.database import SessionLocal
from app.middleware.error_handler import AppError, app_error_handler, validation_error_handler
from app.services.deposits_service import DepositsService
from app.services.epf_auto_contrib_service import EPFAutoContribService
from app.services.price_service import PriceService
from app.services.snapshot_service import SnapshotService
from scripts.seed_interest_rates import seed

# Import all importer classes to trigger @register_importer decorators
# This must happen before any ImporterRegistry() is instantiated
import app.importers  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def _background_price_refresh():
    """Non-blocking price refresh + snapshot triggered on startup."""
    try:
        db = SessionLocal()
        try:
            result = PriceService(db).refresh_all()
            logger.info("Startup price refresh: %s", result)
            SnapshotService(db).take_snapshot()
        finally:
            db.close()
    except Exception as e:
        logger.warning("Startup price refresh failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed interest rates (idempotent)
    try:
        db = SessionLocal()
        try:
            seed(db)
        finally:
            db.close()
    except Exception as e:
        logger.warning("Interest rate seed failed: %s", e)

    # Auto-mature FDs/RDs whose maturity date has passed
    try:
        db = SessionLocal()
        try:
            matured = DepositsService(db).mark_matured_fds()
            if matured:
                logger.info("Startup: marked %d FD(s)/RD(s) as matured", matured)
        finally:
            db.close()
    except Exception as e:
        logger.warning("Startup FD maturity check failed: %s", e)

    # Auto-fill missing EPF monthly contributions using the last known amounts
    try:
        db = SessionLocal()
        try:
            result = EPFAutoContribService(db).backfill_missing_contributions()
            if result["months_inserted"]:
                logger.info(
                    "Startup: EPF auto-contrib filled %d month(s) across %d asset(s)",
                    result["months_inserted"],
                    result["assets_updated"],
                )
        finally:
            db.close()
    except Exception as e:
        logger.warning("Startup EPF auto-contrib failed: %s", e)

    # Price refresh is on-demand only (via CLI: python cli.py refresh-prices)
    yield


app = FastAPI(
    title="Financial Portfolio Tracker",
    version="0.1.0",
    description="Personal, local-first, single-user investment portfolio tracker",
    lifespan=lifespan,
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


from app.api.assets import router as assets_router
from app.api.transactions import router as transactions_router
from app.api.fd_detail import router as fd_detail_router
from app.api.valuations import router as valuations_router
from app.api.goals import router as goals_router
from app.api.important_data import router as important_data_router
from app.api.interest_rates import router as interest_rates_router
from app.api.returns import router as returns_router
from app.api.prices import router as prices_router
from app.api.imports import router as imports_router
from app.api.tax import router as tax_router
from app.api.snapshots import router as snapshots_router
from app.api.corp_actions import router as corp_actions_router

app.include_router(assets_router)
app.include_router(transactions_router)
app.include_router(fd_detail_router)
app.include_router(valuations_router)
app.include_router(goals_router)
app.include_router(important_data_router)
app.include_router(interest_rates_router)
app.include_router(returns_router)
app.include_router(prices_router)
app.include_router(imports_router)
app.include_router(tax_router)
app.include_router(snapshots_router)
app.include_router(corp_actions_router)
