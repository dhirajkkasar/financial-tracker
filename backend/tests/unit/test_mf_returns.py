"""Tests for MF returns using CAS snapshot — written RED first."""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.asset import Asset, AssetType, AssetClass
from app.models.cas_snapshot import CasSnapshot
from app.models.transaction import Transaction, TransactionType
from app.models.price_cache import PriceCache
from app.repositories.cas_snapshot_repo import CasSnapshotRepository
from app.services.returns_service import ReturnsService


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
        is_active=True,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@pytest.fixture
def redeemed_asset(db):
    asset = Asset(
        name="Aditya Birla Large Cap",
        identifier="INF209K01BR9",
        asset_type=AssetType.MF,
        asset_class=AssetClass.MIXED,
        currency="INR",
        is_active=False,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _add_sip_transaction(db, asset_id, txn_date, amount_inr, units):
    import uuid
    txn = Transaction(
        txn_id=str(uuid.uuid4()),
        asset_id=asset_id,
        type=TransactionType.SIP,
        date=txn_date,
        units=units,
        price_per_unit=abs(amount_inr) / units,   # INR per unit (Float column)
        amount_inr=round(amount_inr * 100),        # paise (Integer column)
        lot_id=str(uuid.uuid4()),
    )
    db.add(txn)
    db.commit()
    return txn


def _add_snapshot(db, asset_id, snap_date, closing_units, market_value_inr, total_cost_inr, nav_price_inr=89.37):
    snap = CasSnapshot(
        asset_id=asset_id,
        date=snap_date,
        closing_units=closing_units,
        nav_price_inr=round(nav_price_inr * 100),
        market_value_inr=round(market_value_inr * 100),
        total_cost_inr=round(total_cost_inr * 100),
    )
    db.add(snap)
    db.commit()
    return snap


def _add_price_cache(db, asset_id, price_inr):
    from datetime import datetime
    pc = PriceCache(
        asset_id=asset_id,
        price_inr=round(price_inr * 100),
        source="mfapi",
        fetched_at=datetime.utcnow(),
    )
    db.add(pc)
    db.commit()
    return pc


class TestMFReturnsNoSnapshot:
    def test_raises_validation_error_when_no_snapshot(self, db, mf_asset):
        from app.middleware.error_handler import ValidationError
        _add_sip_transaction(db, mf_asset.id, date(2024, 1, 1), -10000.0, 100.0)
        svc = ReturnsService(db)
        with pytest.raises(ValidationError, match="CAS"):
            svc.get_asset_returns(mf_asset.id)


class TestMFReturnsFreshSnapshot:
    """Snapshot < 30 days old → use market_value from snapshot directly."""

    def test_current_value_from_fresh_snapshot(self, db, mf_asset):
        _add_sip_transaction(db, mf_asset.id, date(2024, 1, 1), -100000.0, 1000.0)
        snap_date = date.today() - timedelta(days=5)
        _add_snapshot(db, mf_asset.id, snap_date,
                      closing_units=1000.0, market_value_inr=120000.0, total_cost_inr=100000.0)

        svc = ReturnsService(db)
        result = svc.get_asset_returns(mf_asset.id)

        assert abs(result["current_value"] - 120000.0) < 0.01

    def test_current_pl_from_snapshot(self, db, mf_asset):
        _add_sip_transaction(db, mf_asset.id, date(2024, 1, 1), -100000.0, 1000.0)
        snap_date = date.today() - timedelta(days=5)
        _add_snapshot(db, mf_asset.id, snap_date,
                      closing_units=1000.0, market_value_inr=120000.0, total_cost_inr=100000.0)

        svc = ReturnsService(db)
        result = svc.get_asset_returns(mf_asset.id)

        assert abs(result["current_p_l"] - 20000.0) < 0.01  # 120k - 100k

    def test_all_time_pl_includes_realised_gains(self, db, mf_asset):
        """all_time_p_l = current_p_l + realised gains from lot engine."""
        import uuid
        # Buy 1000 units at ₹100
        _add_sip_transaction(db, mf_asset.id, date(2022, 1, 1), -100000.0, 1000.0)
        # Sell 200 units at ₹150 → realised gain = 200 × (150-100) = ₹10,000
        sell = Transaction(
            txn_id=str(uuid.uuid4()),
            asset_id=mf_asset.id,
            type=TransactionType.REDEMPTION,
            date=date(2023, 6, 1),
            units=200.0,
            price_per_unit=150.0,   # INR per unit (Float column)
            amount_inr=3000000,     # +30,000 INR in paise (Integer column)
        )
        db.add(sell)
        db.commit()

        # CAS snapshot: 800 units remaining at ₹120 = ₹96,000 market value; cost = ₹80,000
        snap_date = date.today() - timedelta(days=5)
        _add_snapshot(db, mf_asset.id, snap_date,
                      closing_units=800.0, market_value_inr=96000.0, total_cost_inr=80000.0)

        svc = ReturnsService(db)
        result = svc.get_asset_returns(mf_asset.id)

        # current_p_l = 96000 - 80000 = 16000
        assert abs(result["current_p_l"] - 16000.0) < 1.0
        # all_time_p_l = 16000 + 10000 realised = 26000
        assert abs(result["all_time_p_l"] - 26000.0) < 1.0


class TestMFReturnsStaleSnapshot:
    """Snapshot ≥ 30 days old → use closing_units × latest NAV from price_cache."""

    def test_current_value_uses_units_times_latest_nav(self, db, mf_asset):
        _add_sip_transaction(db, mf_asset.id, date(2024, 1, 1), -100000.0, 1000.0)
        snap_date = date.today() - timedelta(days=45)
        _add_snapshot(db, mf_asset.id, snap_date,
                      closing_units=1000.0, market_value_inr=110000.0, total_cost_inr=100000.0,
                      nav_price_inr=110.0)
        _add_price_cache(db, mf_asset.id, price_inr=130.0)  # fresher NAV

        svc = ReturnsService(db)
        result = svc.get_asset_returns(mf_asset.id)

        # Should use 1000 units × ₹130 = ₹130,000
        assert abs(result["current_value"] - 130000.0) < 0.01

    def test_stale_snapshot_falls_back_to_snapshot_if_no_price_cache(self, db, mf_asset):
        _add_sip_transaction(db, mf_asset.id, date(2024, 1, 1), -100000.0, 1000.0)
        snap_date = date.today() - timedelta(days=45)
        _add_snapshot(db, mf_asset.id, snap_date,
                      closing_units=1000.0, market_value_inr=110000.0, total_cost_inr=100000.0)

        svc = ReturnsService(db)
        result = svc.get_asset_returns(mf_asset.id)

        # Falls back to snapshot market_value since no price_cache
        assert abs(result["current_value"] - 110000.0) < 0.01


class TestMFReturnsRedeemedFund:
    def test_redeemed_fund_current_value_is_zero(self, db, redeemed_asset):
        import uuid
        buy = Transaction(
            txn_id=str(uuid.uuid4()),
            asset_id=redeemed_asset.id,
            type=TransactionType.SIP,
            date=date(2020, 1, 1),
            units=500.0,
            price_per_unit=100.0,    # ₹100 INR per unit
            amount_inr=-5000000,     # -₹50,000 in paise
            lot_id=str(uuid.uuid4()),
        )
        sell = Transaction(
            txn_id=str(uuid.uuid4()),
            asset_id=redeemed_asset.id,
            type=TransactionType.REDEMPTION,
            date=date(2022, 1, 1),
            units=500.0,
            price_per_unit=150.0,   # ₹150 INR per unit
            amount_inr=7500000,     # +₹75,000 in paise
        )
        db.add_all([buy, sell])
        db.commit()

        snap_date = date.today() - timedelta(days=5)
        _add_snapshot(db, redeemed_asset.id, snap_date,
                      closing_units=0.0, market_value_inr=0.0, total_cost_inr=0.0)

        svc = ReturnsService(db)
        result = svc.get_asset_returns(redeemed_asset.id)

        assert result["current_value"] == 0
        assert result["current_p_l"] is None

    def test_redeemed_fund_shows_all_time_pl(self, db, redeemed_asset):
        import uuid
        buy = Transaction(
            txn_id=str(uuid.uuid4()),
            asset_id=redeemed_asset.id,
            type=TransactionType.SIP,
            date=date(2020, 1, 1),
            units=500.0,
            price_per_unit=100.0,    # ₹100 INR per unit
            amount_inr=-5000000,     # -₹50,000 in paise
            lot_id=str(uuid.uuid4()),
        )
        sell = Transaction(
            txn_id=str(uuid.uuid4()),
            asset_id=redeemed_asset.id,
            type=TransactionType.REDEMPTION,
            date=date(2022, 1, 1),
            units=500.0,
            price_per_unit=150.0,   # ₹150 INR per unit
            amount_inr=7500000,     # +₹75,000 in paise
        )
        db.add_all([buy, sell])
        db.commit()

        snap_date = date.today() - timedelta(days=5)
        _add_snapshot(db, redeemed_asset.id, snap_date,
                      closing_units=0.0, market_value_inr=0.0, total_cost_inr=0.0)

        svc = ReturnsService(db)
        result = svc.get_asset_returns(redeemed_asset.id)

        # Realised gain: 500 units × (₹150 - ₹100) = ₹25,000
        assert result["all_time_p_l"] is not None
        assert result["all_time_p_l"] > 0


def test_total_invested_uses_open_lots_cost_basis():
    """
    total_invested should = cost basis of currently HELD shares only.
    Buy 100 @ 1500 = ₹1,50,000. Sell 40 → 60 remain.
    Open lot cost basis = 60 × 1500 = ₹90,000 (not ₹1,50,000).
    """
    from datetime import datetime

    asset = MagicMock()
    asset.id = 1
    asset.asset_type = MagicMock()
    asset.asset_type.value = "STOCK_IN"

    buy_txn = MagicMock()
    buy_txn.type.value = "BUY"
    buy_txn.date = date(2023, 1, 1)
    buy_txn.units = 100.0
    buy_txn.price_per_unit = 1500.0
    buy_txn.amount_inr = -15_000_000   # -₹1,50,000 in paise
    buy_txn.lot_id = "lot-1"
    buy_txn.id = 1

    sell_txn = MagicMock()
    sell_txn.type.value = "SELL"
    sell_txn.date = date(2024, 1, 1)
    sell_txn.units = 40.0
    sell_txn.price_per_unit = 1800.0
    sell_txn.amount_inr = 7_200_000    # +₹72,000 in paise
    sell_txn.lot_id = None
    sell_txn.id = 2

    svc = ReturnsService.__new__(ReturnsService)
    svc.db = MagicMock()
    svc.txn_repo = MagicMock()
    svc.txn_repo.list_by_asset.return_value = [buy_txn, sell_txn]
    svc.price_repo = MagicMock()
    price_mock = MagicMock()
    price_mock.price_inr = 200_000   # ₹2000 per share in paise
    price_mock.fetched_at = datetime.utcnow()
    svc.price_repo.get_by_asset_id.return_value = price_mock

    result = svc._compute_market_based_returns(asset)

    # 60 remaining shares × ₹1500 = ₹90,000 cost basis
    assert abs(result["total_invested"] - 90_000.0) < 1.0, (
        f"Expected ₹90,000, got {result['total_invested']}"
    )
