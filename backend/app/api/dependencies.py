"""
Central dependency wiring for FastAPI routes.

All concrete service instantiation lives here.
Routes import factory functions from this module and use them with Depends().

Rule: No route file should contain `db: Session = Depends(get_db)` directly
after migration. All data access goes through a service factory from this file.
"""
import os

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
from app.services.imports.post_processors.fidelity import FidelityPreCommitProcessor
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
        pre_commit_processors=[FidelityPreCommitProcessor()],
        event_bus=_event_bus,
    )


# ---------------------------------------------------------------------------
# Service factories — Plan 4
# ---------------------------------------------------------------------------

from pathlib import Path

from app.services.asset_service import AssetService
from app.services.transaction_service import TransactionService
from app.services.returns.returns_service import ReturnsService as StrategyReturnsService
from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry
from app.services.returns.portfolio_returns_service import PortfolioReturnsService
from app.services.goal_service import GoalService
from app.services.valuation_service import ValuationService
from app.services.fd_detail_service import FDDetailService
from app.services.interest_rate_service import InterestRateService
from app.services.important_data_service import ImportantDataService
from app.services.price_service import PriceService
from app.services.snapshot_service import SnapshotService
from app.services.tax_service import TaxService
from app.services.corp_actions_service import CorpActionsService
from app.engine.tax_engine import TaxRuleResolver
from app.services.tax.strategies.base import register_tax_strategy_instance
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy
from app.services.tax.strategies.real_estate import RealEstateTaxGainsStrategy
from app.services.tax.strategies.accrued_interest import AccruedInterestTaxGainsStrategy

_tax_resolver = TaxRuleResolver(Path("app/config/tax_rates"))

# Register config-driven FIFO strategy for all lot-tracked capital gains types
_fifo_strategy = FifoTaxGainsStrategy(_tax_resolver)
for _key in [("STOCK_IN", "*"), ("STOCK_US", "*"), ("MF", "*"), ("GOLD", "*")]:
    register_tax_strategy_instance(_key, _fifo_strategy)

# Non-FIFO strategies
register_tax_strategy_instance(("REAL_ESTATE", "*"), RealEstateTaxGainsStrategy(_tax_resolver))
register_tax_strategy_instance(("FD", "*"), AccruedInterestTaxGainsStrategy())
register_tax_strategy_instance(("RD", "*"), AccruedInterestTaxGainsStrategy())


def get_asset_service(db: Session = Depends(get_db)) -> AssetService:
    return AssetService(uow_factory=lambda: UnitOfWork(db))


def get_transaction_service(db: Session = Depends(get_db)) -> TransactionService:
    return TransactionService(uow_factory=lambda: UnitOfWork(db))


def get_strategy_returns_service(db: Session = Depends(get_db)) -> StrategyReturnsService:
    return StrategyReturnsService(
        uow_factory=lambda: UnitOfWork(db),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )


def get_portfolio_returns_service(db: Session = Depends(get_db)) -> PortfolioReturnsService:
    return PortfolioReturnsService(db, DefaultReturnsStrategyRegistry())


def get_goal_service(db: Session = Depends(get_db)) -> GoalService:
    returns_svc = PortfolioReturnsService(db, DefaultReturnsStrategyRegistry())
    return GoalService(uow_factory=lambda: UnitOfWork(db), returns_service=returns_svc)


def get_valuation_service(db: Session = Depends(get_db)) -> ValuationService:
    return ValuationService(uow_factory=lambda: UnitOfWork(db))


def get_fd_detail_service(db: Session = Depends(get_db)) -> FDDetailService:
    return FDDetailService(uow_factory=lambda: UnitOfWork(db))


def get_interest_rate_service(db: Session = Depends(get_db)) -> InterestRateService:
    return InterestRateService(uow_factory=lambda: UnitOfWork(db))


def get_important_data_service(db: Session = Depends(get_db)) -> ImportantDataService:
    return ImportantDataService(uow_factory=lambda: UnitOfWork(db))


def get_price_service(db: Session = Depends(get_db)) -> PriceService:
    return PriceService(db)


def get_snapshot_service(db: Session = Depends(get_db)) -> SnapshotService:
    return SnapshotService(db)


def get_tax_service(db: Session = Depends(get_db)) -> TaxService:
    slab_rate_pct = float(os.environ.get("SLAB_RATE", "30.0"))
    return TaxService(
        uow_factory=lambda: UnitOfWork(db),
        slab_rate_pct=slab_rate_pct,
        resolver=_tax_resolver,
    )


def get_corp_actions_service(db: Session = Depends(get_db)) -> CorpActionsService:
    return CorpActionsService(db)
