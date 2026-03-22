"""Integration tests for CorpActionsService — uses real DB session, mocks HTTP fetcher."""
import pytest
from datetime import date
from unittest.mock import MagicMock


class TestCorpActionsServiceApply:
    """Tests that use a real DB session (db fixture) but mock NSECorpActionFetcher.fetch."""

    def _setup_asset_with_buy(self, db):
        from app.models.asset import Asset, AssetType, AssetClass
        from app.models.transaction import Transaction, TransactionType
        a = Asset(name="TCS", identifier="INE467B01029",
                  asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY,
                  currency="INR", is_active=True)
        db.add(a)
        db.flush()
        db.add(Transaction(
            txn_id="tcs_buy_001", asset_id=a.id, type=TransactionType.BUY,
            date=date(2020, 1, 1), units=10.0, price_per_unit=2000.0,
            amount_inr=-2000000, charges_inr=0,
        ))
        db.commit()
        db.refresh(a)
        return a

    def test_bonus_creates_transaction(self, db):
        from app.services.corp_actions_service import CorpActionsService
        from app.models.transaction import Transaction, TransactionType
        asset = self._setup_asset_with_buy(db)

        svc = CorpActionsService(db)
        svc.fetcher.fetch = MagicMock(return_value=[{
            "exDate": "01-JUN-2021",
            "subject": "Bonus 1:1",
        }])

        result = svc.process_asset(asset)
        assert result["bonus_created"] == 1

        bonus_txn = db.query(Transaction).filter_by(
            asset_id=asset.id, type=TransactionType.BONUS
        ).first()
        assert bonus_txn is not None
        assert bonus_txn.units == pytest.approx(10.0)  # 10 held × 1:1 ratio
        assert bonus_txn.amount_inr == 0

    def test_bonus_idempotent(self, db):
        from app.services.corp_actions_service import CorpActionsService
        asset = self._setup_asset_with_buy(db)
        mock_data = [{"exDate": "01-JUN-2021", "subject": "Bonus 1:1"}]

        svc = CorpActionsService(db)
        svc.fetcher.fetch = MagicMock(return_value=mock_data)
        r1 = svc.process_asset(asset)

        svc2 = CorpActionsService(db)
        svc2.fetcher.fetch = MagicMock(return_value=mock_data)
        r2 = svc2.process_asset(asset)

        assert r1["bonus_created"] == 1
        assert r2["bonus_skipped"] == 1

    def test_split_updates_buy_transaction(self, db):
        from app.services.corp_actions_service import CorpActionsService
        from app.models.transaction import Transaction, TransactionType
        asset = self._setup_asset_with_buy(db)

        svc = CorpActionsService(db)
        svc.fetcher.fetch = MagicMock(return_value=[{
            "exDate": "01-APR-2021",
            "subject": "Sub-Division / Split From Rs 10/- To Rs 2/-",
        }])

        result = svc.process_asset(asset)
        assert result["split_applied"] == 1

        # Original BUY units should be 10 × 5 = 50
        buy_txn = db.query(Transaction).filter_by(
            asset_id=asset.id, type=TransactionType.BUY
        ).first()
        assert buy_txn.units == pytest.approx(50.0)
        assert buy_txn.price_per_unit == pytest.approx(400.0)  # 2000 / 5

    def test_split_also_rescales_sell_transactions(self, db):
        """SELL before ex_date must be rescaled so unit counts remain consistent."""
        from app.services.corp_actions_service import CorpActionsService
        from app.models.asset import Asset, AssetType, AssetClass
        from app.models.transaction import Transaction, TransactionType
        a = Asset(name="HDFC", identifier="INE001A01036",
                  asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY,
                  currency="INR", is_active=True)
        db.add(a)
        db.flush()
        # Buy 10 then sell 5 (pre-split), then split 2:1
        db.add(Transaction(
            txn_id="hdfc_buy_001", asset_id=a.id, type=TransactionType.BUY,
            date=date(2019, 1, 1), units=10.0, price_per_unit=1000.0,
            amount_inr=-1000000, charges_inr=0,
        ))
        db.add(Transaction(
            txn_id="hdfc_sell_001", asset_id=a.id, type=TransactionType.SELL,
            date=date(2020, 1, 1), units=5.0, price_per_unit=1200.0,
            amount_inr=600000, charges_inr=0,
        ))
        db.commit()
        db.refresh(a)

        svc = CorpActionsService(db)
        svc.fetcher.fetch = MagicMock(return_value=[{
            "exDate": "01-JUL-2021",
            "subject": "Sub-Division / Split From Rs 10/- To Rs 5/-",  # 2:1 split
        }])
        result = svc.process_asset(a)
        assert result["split_applied"] == 1

        sell_txn = db.query(Transaction).filter_by(
            asset_id=a.id, type=TransactionType.SELL
        ).first()
        assert sell_txn.units == pytest.approx(10.0)   # 5 × 2 = 10
        assert sell_txn.price_per_unit == pytest.approx(600.0)  # 1200 / 2

    def test_split_idempotent(self, db):
        from app.services.corp_actions_service import CorpActionsService
        asset = self._setup_asset_with_buy(db)
        mock_data = [{"exDate": "01-APR-2021", "subject": "Sub-Division / Split From Rs 10/- To Rs 2/-"}]

        svc = CorpActionsService(db)
        svc.fetcher.fetch = MagicMock(return_value=mock_data)
        r1 = svc.process_asset(asset)

        svc2 = CorpActionsService(db)
        svc2.fetcher.fetch = MagicMock(return_value=mock_data)
        r2 = svc2.process_asset(asset)

        assert r1["split_applied"] == 1
        assert r2["split_skipped"] == 1

    def test_dividend_creates_transaction(self, db):
        from app.services.corp_actions_service import CorpActionsService
        from app.models.transaction import Transaction, TransactionType
        asset = self._setup_asset_with_buy(db)

        svc = CorpActionsService(db)
        svc.fetcher.fetch = MagicMock(return_value=[{
            "exDate": "15-MAR-2021",
            "subject": "Interim Dividend - Rs 25 Per Share",
        }])

        result = svc.process_asset(asset)
        assert result["dividend_created"] == 1

        div_txn = db.query(Transaction).filter_by(
            asset_id=asset.id, type=TransactionType.DIVIDEND
        ).first()
        assert div_txn is not None
        assert div_txn.amount_inr == 25000  # 10 units × 25 INR × 100 paise

    def test_dividend_re_notation(self, db):
        """NSE uses 'Re.' for sub-₹1 dividends — must be parsed correctly."""
        from app.services.corp_actions_service import CorpActionsService
        from app.models.transaction import Transaction, TransactionType
        asset = self._setup_asset_with_buy(db)

        svc = CorpActionsService(db)
        svc.fetcher.fetch = MagicMock(return_value=[{
            "exDate": "15-MAR-2021",
            "subject": "Interim Dividend Re. 0.50 Per Share",
        }])

        result = svc.process_asset(asset)
        assert result["dividend_created"] == 1

        div_txn = db.query(Transaction).filter_by(
            asset_id=asset.id, type=TransactionType.DIVIDEND
        ).first()
        assert div_txn is not None
        assert div_txn.amount_inr == 500  # 10 units × 0.5 INR × 100 paise

    def test_action_outside_holding_period_skipped(self, db):
        """Corporate action after all shares sold → not applied."""
        from app.models.transaction import Transaction, TransactionType
        from app.services.corp_actions_service import CorpActionsService
        asset = self._setup_asset_with_buy(db)
        # Sell all shares before the corporate action ex_date
        db.add(Transaction(
            txn_id="tcs_sell_001", asset_id=asset.id, type=TransactionType.SELL,
            date=date(2020, 6, 1), units=10.0, price_per_unit=2200.0,
            amount_inr=2200000, charges_inr=0,
        ))
        db.commit()

        svc = CorpActionsService(db)
        svc.fetcher.fetch = MagicMock(return_value=[{
            "exDate": "01-JAN-2022",  # after full sell in June 2020
            "subject": "Bonus 1:1",
        }])

        result = svc.process_asset(asset)
        assert result["bonus_created"] == 0
        assert result["bonus_skipped"] == 0  # not even attempted
