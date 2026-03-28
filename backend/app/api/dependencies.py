"""
Central dependency wiring for FastAPI routes.

All concrete service instantiation lives here.
Routes import factory functions from this module and use them with Depends().

Rule: No route file should contain `db: Session = Depends(get_db)` directly
after migration. All data access goes through a service factory from this file.
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.importers.pipeline import ImportPipeline
from app.importers.registry import ImporterRegistry
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.services.event_bus import SyncEventBus
from app.services.imports.deduplicator import DBDeduplicator
from app.services.imports.orchestrator import ImportOrchestrator
from app.services.imports.post_processors.stock import StockPostProcessor
from app.services.imports.post_processors.mf import MFPostProcessor
from app.services.imports.post_processors.ppf import PPFPostProcessor
from app.services.imports.post_processors.epf import EPFPostProcessor
from app.services.imports.preview_store import PreviewStore

# ---------------------------------------------------------------------------
# Core: UnitOfWork factory
# ---------------------------------------------------------------------------

def get_uow_factory(db: Session = Depends(get_db)) -> IUnitOfWorkFactory:
    """Provide a callable that creates a UnitOfWork bound to the request session."""
    return lambda: UnitOfWork(db)


# ---------------------------------------------------------------------------
# Import orchestrator singletons (TTL-based store, stateless bus)
# ---------------------------------------------------------------------------

_preview_store = PreviewStore(ttl_minutes=15)
_event_bus = SyncEventBus()

# Wire corp actions handler when corp_actions_service is available
# (Plan 4 adds: _event_bus.subscribe(ImportCompletedEvent, corp_actions_svc.on_import_completed))


def get_import_orchestrator(db: Session = Depends(get_db)) -> ImportOrchestrator:
    uow_factory = lambda: UnitOfWork(db)
    txn_repo = UnitOfWork(db).transactions  # for deduplication check

    pipeline = ImportPipeline(
        registry=ImporterRegistry(),
        deduplicator=DBDeduplicator(txn_repo),
    )

    return ImportOrchestrator(
        uow_factory=uow_factory,
        pipeline=pipeline,
        preview_store=_preview_store,
        post_processors=[StockPostProcessor(), MFPostProcessor(), PPFPostProcessor(), EPFPostProcessor()],
        event_bus=_event_bus,
    )


# ---------------------------------------------------------------------------
# Service factories — Plan 4
# ---------------------------------------------------------------------------

from app.services.asset_service import AssetService
from app.services.transaction_service import TransactionService
from app.services.returns.returns_service import ReturnsService as StrategyReturnsService
from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry


def get_asset_service(db: Session = Depends(get_db)) -> AssetService:
    return AssetService(uow_factory=lambda: UnitOfWork(db))


def get_transaction_service(db: Session = Depends(get_db)) -> TransactionService:
    return TransactionService(uow_factory=lambda: UnitOfWork(db))


def get_strategy_returns_service(db: Session = Depends(get_db)) -> StrategyReturnsService:
    return StrategyReturnsService(
        uow_factory=lambda: UnitOfWork(db),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )
