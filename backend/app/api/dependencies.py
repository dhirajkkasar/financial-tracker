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
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory


# ---------------------------------------------------------------------------
# Core: UnitOfWork factory
# ---------------------------------------------------------------------------

def get_uow_factory(db: Session = Depends(get_db)) -> IUnitOfWorkFactory:
    """Provide a callable that creates a UnitOfWork bound to the request session."""
    return lambda: UnitOfWork(db)


# ---------------------------------------------------------------------------
# Placeholder stubs — filled in by Plans 3 and 4
# ---------------------------------------------------------------------------
# Plan 3 will add:
#   get_import_orchestrator(db) -> ImportOrchestrator
#
# Plan 4 will add:
#   get_returns_service(db) -> ReturnsService
#   get_tax_service(db) -> TaxService
#   get_price_service(db) -> PriceService
#   get_asset_service(db) -> AssetService
#   get_transaction_service(db) -> TransactionService
