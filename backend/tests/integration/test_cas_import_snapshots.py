"""Integration tests for CAS snapshot commit behaviour — written RED first."""
import pytest
from datetime import date
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.asset import Asset, AssetType, AssetClass
from app.models.cas_snapshot import CasSnapshot
from app.importers.base import ParsedFundSnapshot, ParsedTransaction
from app.services.import_service import ImportService
from app.repositories.cas_snapshot_repo import CasSnapshotRepository

FIXTURES = Path(__file__).parent.parent / "fixtures"


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
def active_asset(db):
    asset = Asset(
        name="Parag Parikh Flexi Cap Fund",
        identifier="INF879O01027",
        asset_type=AssetType.MF,
        asset_class=AssetClass.MIXED,
        currency="INR",
        is_active=True,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@pytest.fixture
def redeemed_asset(db):
    asset = Asset(
        name="Aditya Birla Sun Life Large Cap Fund",
        identifier="INF209K01BR9",
        asset_type=AssetType.MF,
        asset_class=AssetClass.MIXED,
        currency="INR",
        is_active=True,  # starts active; import should flip to False
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _make_snapshot(isin, asset_name, closing_units, nav=89.3756,
                   market_value=2375687.37, total_cost=1655390.87):
    return ParsedFundSnapshot(
        isin=isin,
        asset_name=asset_name,
        date=date(2026, 3, 18),
        closing_units=closing_units,
        nav_price_inr=nav,
        market_value_inr=market_value,
        total_cost_inr=total_cost,
    )


class TestCasSnapshotCommit:
    def test_commit_creates_cas_snapshot(self, db, active_asset):
        svc = ImportService(db)
        snap = _make_snapshot(
            isin="INF879O01027",
            asset_name="Parag Parikh Flexi Cap Fund",
            closing_units=26580.939,
        )
        preview = svc.preview(transactions=[], preview_snapshots=[snap])
        svc.commit(preview["preview_id"])

        repo = CasSnapshotRepository(db)
        saved = repo.get_latest_by_asset_id(active_asset.id)
        assert saved is not None
        assert abs(saved.closing_units - 26580.939) < 0.001
        assert saved.date == date(2026, 3, 18)
        # values stored in paise
        assert saved.market_value_inr == round(2375687.37 * 100)
        assert saved.total_cost_inr == round(1655390.87 * 100)

    def test_commit_marks_redeemed_fund_inactive(self, db, redeemed_asset):
        svc = ImportService(db)
        snap = _make_snapshot(
            isin="INF209K01BR9",
            asset_name="Aditya Birla Sun Life Large Cap Fund",
            closing_units=0.0,
            nav=495.46,
            market_value=0.0,
            total_cost=0.0,
        )
        preview = svc.preview(transactions=[], preview_snapshots=[snap])
        svc.commit(preview["preview_id"])

        db.refresh(redeemed_asset)
        assert redeemed_asset.is_active is False

    def test_commit_marks_active_fund_active(self, db, active_asset):
        # Asset starts active; re-importing with units > 0 keeps/sets it active
        active_asset.is_active = False  # simulate it was previously marked inactive
        db.commit()

        svc = ImportService(db)
        snap = _make_snapshot(
            isin="INF879O01027",
            asset_name="Parag Parikh Flexi Cap Fund",
            closing_units=26580.939,
        )
        preview = svc.preview(transactions=[], preview_snapshots=[snap])
        svc.commit(preview["preview_id"])

        db.refresh(active_asset)
        assert active_asset.is_active is True

    def test_commit_creates_new_snapshot_on_reimport(self, db, active_asset):
        """Each CAS import creates a new row; latest is used."""
        svc = ImportService(db)

        # First import
        snap1 = _make_snapshot(
            isin="INF879O01027",
            asset_name="Parag Parikh Flexi Cap Fund",
            closing_units=25000.0,
        )
        snap1.date = date(2026, 1, 31)
        p1 = svc.preview(transactions=[], preview_snapshots=[snap1])
        svc.commit(p1["preview_id"])

        # Second import (newer)
        snap2 = _make_snapshot(
            isin="INF879O01027",
            asset_name="Parag Parikh Flexi Cap Fund",
            closing_units=26580.939,
        )
        p2 = svc.preview(transactions=[], preview_snapshots=[snap2])
        svc.commit(p2["preview_id"])

        repo = CasSnapshotRepository(db)
        all_snaps = db.query(CasSnapshot).filter(CasSnapshot.asset_id == active_asset.id).all()
        assert len(all_snaps) == 2  # both stored

        latest = repo.get_latest_by_asset_id(active_asset.id)
        assert abs(latest.closing_units - 26580.939) < 0.001  # newest used

    def test_commit_skips_snapshot_for_unknown_isin(self, db):
        """Snapshots for ISINs not in DB are silently skipped."""
        svc = ImportService(db)
        snap = _make_snapshot(
            isin="INF999Z99ZZ9",  # not in DB
            asset_name="Unknown Fund",
            closing_units=1000.0,
        )
        preview = svc.preview(transactions=[], preview_snapshots=[snap])
        result = svc.commit(preview["preview_id"])
        # Should not raise; snapshot_count may be 0
        assert result is not None

    def test_preview_stores_snapshots_for_commit(self, db, active_asset):
        """Snapshots stored in preview_store survive until commit."""
        svc = ImportService(db)
        snap = _make_snapshot(
            isin="INF879O01027",
            asset_name="Parag Parikh Flexi Cap Fund",
            closing_units=26580.939,
        )
        preview = svc.preview(transactions=[], preview_snapshots=[snap])
        assert "preview_id" in preview

        result = svc.commit(preview["preview_id"])
        assert result["snapshot_count"] == 1
