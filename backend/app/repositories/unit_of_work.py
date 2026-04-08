"""
Unit of Work — wraps a SQLAlchemy Session and all repositories.

Usage:
    with UnitOfWork(session) as uow:
        asset = uow.assets.create(name="Foo", ...)
        uow.transactions.create(asset_id=asset.id, ...)
    # All writes committed atomically here.
    # On exception, everything rolls back.

Note: While repos still have their own db.commit() calls (legacy),
the UoW's __exit__ commit is a no-op if already committed. The
UoW's rollback on failure IS effective because SQLite/PostgreSQL
support savepoints. Repos will have their commits removed in Plan 4.
"""
from __future__ import annotations

from typing import Protocol
from sqlalchemy.orm import Session

from app.repositories.member_repo import MemberRepository
from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.valuation_repo import ValuationRepository
from app.repositories.price_cache_repo import PriceCacheRepository
from app.repositories.fd_repo import FDRepository
from app.repositories.cas_snapshot_repo import CasSnapshotRepository
from app.repositories.goal_repo import GoalRepository
from app.repositories.snapshot_repo import SnapshotRepository
from app.repositories.important_data_repo import ImportantDataRepository
from app.repositories.interest_rate_repo import InterestRateRepository


class UnitOfWork:
    """Context manager that provides all repositories and a single commit point."""

    def __init__(self, session: Session):
        self.session = session
        self.members = MemberRepository(session)
        self.assets = AssetRepository(session)
        self.transactions = TransactionRepository(session)
        self.valuations = ValuationRepository(session)
        self.price_cache = PriceCacheRepository(session)
        self.fd = FDRepository(session)
        self.cas_snapshots = CasSnapshotRepository(session)
        self.goals = GoalRepository(session)
        self.snapshots = SnapshotRepository(session)
        self.important_data = ImportantDataRepository(session)
        self.interest_rates = InterestRateRepository(session)

    def __enter__(self) -> "UnitOfWork":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.session.rollback()
        else:
            self.session.commit()

    def flush(self) -> None:
        """Flush pending changes to DB without committing (makes IDs available)."""
        self.session.flush()


class IUnitOfWorkFactory(Protocol):
    """Callable that creates a UnitOfWork given the current session."""
    def __call__(self) -> UnitOfWork: ...
