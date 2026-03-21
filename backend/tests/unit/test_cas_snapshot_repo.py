"""Tests for CasSnapshot model and repository — written RED first."""
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.asset import Asset, AssetType, AssetClass
from app.models.cas_snapshot import CasSnapshot
from app.repositories.cas_snapshot_repo import CasSnapshotRepository


@pytest.fixture
def db():
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


@pytest.fixture
def mf_asset(db):
    asset = Asset(
        name="Parag Parikh Flexi Cap Fund",
        identifier="INF879O01027",
        asset_type=AssetType.MF,
        asset_class=AssetClass.MIXED,
        currency="INR",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


class TestCasSnapshotRepository:
    def test_create_snapshot(self, db, mf_asset):
        repo = CasSnapshotRepository(db)
        snap = repo.create(
            asset_id=mf_asset.id,
            date=date(2026, 3, 18),
            closing_units=26580.939,
            nav_price_inr=8937,   # 89.37 INR in paise
            market_value_inr=237568737,   # 2,375,687.37 INR in paise
            total_cost_inr=165539087,     # 1,655,390.87 INR in paise
        )
        assert snap.id is not None
        assert snap.asset_id == mf_asset.id
        assert snap.closing_units == 26580.939
        assert snap.nav_price_inr == 8937
        assert snap.market_value_inr == 237568737
        assert snap.total_cost_inr == 165539087
        assert snap.date == date(2026, 3, 18)

    def test_get_latest_returns_most_recent(self, db, mf_asset):
        repo = CasSnapshotRepository(db)
        repo.create(
            asset_id=mf_asset.id,
            date=date(2026, 1, 31),
            closing_units=25000.0,
            nav_price_inr=8500,
            market_value_inr=212500000,
            total_cost_inr=150000000,
        )
        repo.create(
            asset_id=mf_asset.id,
            date=date(2026, 3, 18),
            closing_units=26580.939,
            nav_price_inr=8937,
            market_value_inr=237568737,
            total_cost_inr=165539087,
        )
        latest = repo.get_latest_by_asset_id(mf_asset.id)
        assert latest is not None
        assert latest.date == date(2026, 3, 18)
        assert abs(latest.closing_units - 26580.939) < 0.001

    def test_get_latest_returns_none_when_no_snapshot(self, db, mf_asset):
        repo = CasSnapshotRepository(db)
        result = repo.get_latest_by_asset_id(mf_asset.id)
        assert result is None

    def test_get_latest_is_per_asset(self, db, mf_asset):
        """Snapshots from other assets don't bleed through."""
        other = Asset(
            name="Other Fund",
            identifier="INF999Z01ZZ9",
            asset_type=AssetType.MF,
            asset_class=AssetClass.MIXED,
            currency="INR",
        )
        db.add(other)
        db.commit()

        repo = CasSnapshotRepository(db)
        repo.create(
            asset_id=other.id,
            date=date(2026, 3, 18),
            closing_units=1000.0,
            nav_price_inr=5000,
            market_value_inr=50000000,
            total_cost_inr=40000000,
        )
        assert repo.get_latest_by_asset_id(mf_asset.id) is None
