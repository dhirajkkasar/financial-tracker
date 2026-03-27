from app.repositories.interfaces import (
    IAssetRepository,
    ITransactionRepository,
    IValuationRepository,
    IPriceCacheRepository,
    IFDRepository,
    ICasSnapshotRepository,
    IGoalRepository,
)
from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.repositories.unit_of_work import UnitOfWork


@pytest.fixture
def uow_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_uow_exposes_all_repos(uow_session):
    uow = UnitOfWork(uow_session)
    assert hasattr(uow, "assets")
    assert hasattr(uow, "transactions")
    assert hasattr(uow, "valuations")
    assert hasattr(uow, "price_cache")
    assert hasattr(uow, "fd")
    assert hasattr(uow, "cas_snapshots")
    assert hasattr(uow, "goals")
    assert hasattr(uow, "snapshots")


def test_uow_context_manager_commits_on_success(uow_session):
    with UnitOfWork(uow_session) as uow:
        uow.assets.create(
            name="Test Asset",
            identifier="TEST",
            asset_type="STOCK_IN",
            asset_class="EQUITY",
            is_active=True,
        )
    # After context exits cleanly, the record should be queryable
    from app.models.asset import Asset
    result = uow_session.query(Asset).filter_by(name="Test Asset").first()
    assert result is not None


@pytest.mark.xfail(
    reason="Repos call db.commit() immediately; rollback isolation requires Plan 4 to remove those commits"
)
def test_uow_context_manager_rolls_back_on_exception(uow_session):
    try:
        with UnitOfWork(uow_session) as uow:
            uow.assets.create(
                name="Should Rollback",
                identifier="ROLLBACK",
                asset_type="STOCK_IN",
                asset_class="EQUITY",
                is_active=True,
            )
            raise ValueError("Simulated failure")
    except ValueError:
        pass

    from app.models.asset import Asset
    result = uow_session.query(Asset).filter_by(name="Should Rollback").first()
    assert result is None


def test_asset_repo_satisfies_interface():
    """AssetRepository satisfies IAssetRepository via duck-typing."""
    assert hasattr(AssetRepository, "get_by_id")
    assert hasattr(AssetRepository, "list")
    assert hasattr(AssetRepository, "create")
    assert hasattr(AssetRepository, "update")


def test_transaction_repo_satisfies_interface():
    assert hasattr(TransactionRepository, "get_by_txn_id")
    assert hasattr(TransactionRepository, "create")
    assert hasattr(TransactionRepository, "list_by_asset")
