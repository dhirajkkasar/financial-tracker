import pytest
from datetime import date
from unittest.mock import MagicMock, patch


class TestParseCorpActionSubject:
    def test_bonus_1_1(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        r = parse_corp_action_subject("Bonus 1:1")
        assert r["kind"] == "BONUS"
        assert r["ratio"] == pytest.approx(1.0)

    def test_bonus_2_1(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        r = parse_corp_action_subject("Bonus 2:1")
        assert r["ratio"] == pytest.approx(2.0)

    def test_bonus_1_2(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        r = parse_corp_action_subject("Bonus Issue 1:2")
        assert r["ratio"] == pytest.approx(0.5)

    def test_split_10_to_2(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        r = parse_corp_action_subject("Sub-Division / Split From Rs 10/- To Rs 2/-")
        assert r["kind"] == "SPLIT"
        assert r["ratio"] == pytest.approx(5.0)

    def test_split_5_to_1(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        r = parse_corp_action_subject("Split From Rs 5 To Rs 1")
        assert r["kind"] == "SPLIT"
        assert r["ratio"] == pytest.approx(5.0)

    def test_interim_dividend(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        r = parse_corp_action_subject("Interim Dividend - Rs 3 Per Share")
        assert r["kind"] == "DIVIDEND"
        assert r["per_share_inr"] == pytest.approx(3.0)

    def test_final_dividend(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        r = parse_corp_action_subject("Final Dividend - Rs 10 Per Share")
        assert r["kind"] == "DIVIDEND"
        assert r["per_share_inr"] == pytest.approx(10.0)

    def test_dividend_decimal(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        r = parse_corp_action_subject("Dividend Rs. 1.50 Per Share")
        assert r["per_share_inr"] == pytest.approx(1.5)

    def test_buyback_returns_none(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        assert parse_corp_action_subject("Buyback of Shares") is None

    def test_rights_returns_none(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        assert parse_corp_action_subject("Rights Issue 1:5 at Rs 200") is None

    def test_unrecognised_returns_none(self):
        from app.services.corp_actions_service import parse_corp_action_subject
        assert parse_corp_action_subject("Scheme of Amalgamation") is None


class TestIsHeldOnDate:
    def _make_txn(self, txn_type, txn_date, units):
        t = MagicMock()
        t.type.value = txn_type
        t.date = txn_date
        t.units = units
        return t

    def test_held_during_period(self):
        from app.services.corp_actions_service import is_held_on_date
        txns = [
            self._make_txn("BUY", date(2020, 1, 1), 10),
            self._make_txn("SELL", date(2021, 6, 1), 10),
        ]
        assert is_held_on_date(txns, date(2020, 6, 1)) is True

    def test_not_held_before_buy(self):
        from app.services.corp_actions_service import is_held_on_date
        txns = [self._make_txn("BUY", date(2022, 1, 1), 10)]
        assert is_held_on_date(txns, date(2020, 6, 1)) is False

    def test_not_held_after_full_sell(self):
        from app.services.corp_actions_service import is_held_on_date
        txns = [
            self._make_txn("BUY", date(2018, 1, 1), 10),
            self._make_txn("SELL", date(2019, 1, 1), 10),
        ]
        # Ex-date after full sell — not held
        assert is_held_on_date(txns, date(2022, 1, 1)) is False

    def test_held_in_second_cycle(self):
        from app.services.corp_actions_service import is_held_on_date
        txns = [
            self._make_txn("BUY", date(2018, 1, 1), 10),
            self._make_txn("SELL", date(2019, 1, 1), 10),
            self._make_txn("BUY", date(2021, 1, 1), 5),
        ]
        # Ex-date in second buy cycle
        assert is_held_on_date(txns, date(2022, 1, 1)) is True


class TestUnitsHeldAtDate:
    def _make_txn(self, txn_type, txn_date, units):
        t = MagicMock()
        t.type.value = txn_type
        t.date = txn_date
        t.units = units
        return t

    def test_buy_only(self):
        from app.services.corp_actions_service import units_held_at_date
        txns = [self._make_txn("BUY", date(2020, 1, 1), 10)]
        assert units_held_at_date(txns, date(2020, 6, 1)) == pytest.approx(10.0)

    def test_buy_plus_bonus(self):
        from app.services.corp_actions_service import units_held_at_date
        txns = [
            self._make_txn("BUY", date(2020, 1, 1), 10),
            self._make_txn("BONUS", date(2021, 1, 1), 5),
        ]
        assert units_held_at_date(txns, date(2021, 6, 1)) == pytest.approx(15.0)

    def test_before_bonus(self):
        from app.services.corp_actions_service import units_held_at_date
        txns = [
            self._make_txn("BUY", date(2020, 1, 1), 10),
            self._make_txn("BONUS", date(2021, 1, 1), 5),
        ]
        assert units_held_at_date(txns, date(2020, 6, 1)) == pytest.approx(10.0)

    def test_after_partial_sell(self):
        from app.services.corp_actions_service import units_held_at_date
        txns = [
            self._make_txn("BUY", date(2020, 1, 1), 10),
            self._make_txn("BONUS", date(2021, 1, 1), 5),
            self._make_txn("SELL", date(2022, 1, 1), 3),
        ]
        assert units_held_at_date(txns, date(2022, 6, 1)) == pytest.approx(12.0)

    def test_never_negative(self):
        from app.services.corp_actions_service import units_held_at_date
        txns = [self._make_txn("SELL", date(2022, 1, 1), 100)]
        assert units_held_at_date(txns, date(2022, 6, 1)) == 0.0


class TestNSECorpActionFetcherParseExDate:
    def test_valid_date(self):
        from app.services.corp_actions_service import NSECorpActionFetcher
        d = NSECorpActionFetcher.parse_ex_date("09-JAN-2020")
        assert d == date(2020, 1, 9)

    def test_valid_date_dec(self):
        from app.services.corp_actions_service import NSECorpActionFetcher
        d = NSECorpActionFetcher.parse_ex_date("25-DEC-2021")
        assert d == date(2021, 12, 25)

    def test_invalid_returns_none(self):
        from app.services.corp_actions_service import NSECorpActionFetcher
        assert NSECorpActionFetcher.parse_ex_date("not-a-date") is None

    def test_empty_returns_none(self):
        from app.services.corp_actions_service import NSECorpActionFetcher
        assert NSECorpActionFetcher.parse_ex_date("") is None


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
