"""
Unit tests for FIFO lot engine (Phase 3.1).
TDD: tests written first — RED before implementation.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Minimal data shapes the engine will accept (mirrors what service will pass)
# ---------------------------------------------------------------------------

@dataclass
class FakeLot:
    lot_id: str
    asset_id: int
    buy_date: date
    units: float
    buy_price_per_unit: float   # INR
    buy_amount_inr: float       # absolute (positive)
    jan31_2018_price: Optional[float] = None  # for grandfathering


@dataclass
class FakeSell:
    date: date
    units: float
    amount_inr: float           # positive (inflow)


from app.engine.lot_engine import (
    match_lots_fifo,
    compute_lot_unrealised,
    get_tax_cost_basis,
    EQUITY_STCG_DAYS,
    STOCK_US_STCG_DAYS,
    GOLD_STCG_DAYS,
)


# ---------------------------------------------------------------------------
# match_lots_fifo
# ---------------------------------------------------------------------------

class TestMatchLotsFifo:
    def _lot(self, lot_id, buy_date, units, price):
        return FakeLot(
            lot_id=lot_id, asset_id=1,
            buy_date=buy_date, units=units,
            buy_price_per_unit=price, buy_amount_inr=units * price,
        )

    def test_single_sell_consumes_earliest_lot_first(self):
        lots = [
            self._lot("A", date(2022, 1, 1), 10, 100.0),
            self._lot("B", date(2023, 1, 1), 10, 200.0),
        ]
        sell = FakeSell(date=date(2024, 1, 1), units=10, amount_inr=1500.0)
        matched = match_lots_fifo(lots, [sell])
        # Lot A (earliest) should be consumed first
        assert matched[0]["lot_id"] == "A"
        assert matched[0]["units_sold"] == 10.0
        assert matched[0]["sell_date"] == date(2024, 1, 1)

    def test_partial_lot_consumption(self):
        lots = [self._lot("A", date(2022, 1, 1), 10, 100.0)]
        sell = FakeSell(date=date(2024, 1, 1), units=4, amount_inr=600.0)
        matched = match_lots_fifo(lots, [sell])
        assert len(matched) == 1
        assert matched[0]["units_sold"] == 4.0
        assert matched[0]["units_remaining"] == 6.0

    def test_sell_spans_multiple_lots(self):
        lots = [
            self._lot("A", date(2022, 1, 1), 5, 100.0),
            self._lot("B", date(2023, 1, 1), 5, 200.0),
        ]
        sell = FakeSell(date=date(2024, 1, 1), units=8, amount_inr=1200.0)
        matched = match_lots_fifo(lots, [sell])
        assert len(matched) == 2
        assert matched[0]["lot_id"] == "A"
        assert matched[0]["units_sold"] == 5.0
        assert matched[1]["lot_id"] == "B"
        assert matched[1]["units_sold"] == 3.0

    def test_multiple_sells_deplete_lots_in_order(self):
        lots = [
            self._lot("A", date(2022, 1, 1), 10, 100.0),
            self._lot("B", date(2023, 1, 1), 10, 200.0),
        ]
        sells = [
            FakeSell(date=date(2023, 6, 1), units=10, amount_inr=1000.0),
            FakeSell(date=date(2024, 1, 1), units=5, amount_inr=1500.0),
        ]
        matched = match_lots_fifo(lots, sells)
        lot_ids = [m["lot_id"] for m in matched]
        assert lot_ids[0] == "A"   # first sell takes lot A
        assert lot_ids[1] == "B"   # second sell takes lot B

    def test_no_sells_returns_empty(self):
        lots = [self._lot("A", date(2022, 1, 1), 10, 100.0)]
        assert match_lots_fifo(lots, []) == []

    def test_sell_more_than_available_clips_to_available(self):
        lots = [self._lot("A", date(2022, 1, 1), 5, 100.0)]
        sell = FakeSell(date=date(2024, 1, 1), units=10, amount_inr=1000.0)
        matched = match_lots_fifo(lots, [sell])
        assert matched[0]["units_sold"] == 5.0  # capped at available


# ---------------------------------------------------------------------------
# compute_lot_unrealised
# ---------------------------------------------------------------------------

class TestComputeLotUnrealised:
    def _lot(self, buy_date, units, price, asset_type="STOCK_IN"):
        return FakeLot(
            lot_id="X", asset_id=1,
            buy_date=buy_date, units=units,
            buy_price_per_unit=price, buy_amount_inr=units * price,
        )

    def test_unrealised_gain_positive(self):
        lot = self._lot(date(2022, 1, 1), 10, 100.0)
        result = compute_lot_unrealised(lot, current_price=150.0, asset_type="STOCK_IN", as_of=date(2024, 1, 1))
        assert result["current_value"] == pytest.approx(1500.0)
        assert result["unrealised_gain"] == pytest.approx(500.0)

    def test_unrealised_loss_negative(self):
        lot = self._lot(date(2022, 1, 1), 10, 200.0)
        result = compute_lot_unrealised(lot, current_price=150.0, asset_type="STOCK_IN", as_of=date(2024, 1, 1))
        assert result["unrealised_gain"] == pytest.approx(-500.0)

    def test_equity_short_term_under_1_year(self):
        result = compute_lot_unrealised(
            self._lot(date(2023, 7, 1), 10, 100.0),
            current_price=120.0, asset_type="STOCK_IN", as_of=date(2024, 1, 1)
        )
        assert result["is_short_term"] is True

    def test_equity_long_term_over_1_year(self):
        result = compute_lot_unrealised(
            self._lot(date(2022, 1, 1), 10, 100.0),
            current_price=150.0, asset_type="STOCK_IN", as_of=date(2024, 1, 1)
        )
        assert result["is_short_term"] is False

    def test_us_stock_short_term_under_2_years(self):
        result = compute_lot_unrealised(
            self._lot(date(2023, 1, 1), 10, 100.0),
            current_price=120.0, asset_type="STOCK_US", as_of=date(2024, 6, 1)
        )
        assert result["is_short_term"] is True

    def test_us_stock_long_term_over_2_years(self):
        result = compute_lot_unrealised(
            self._lot(date(2021, 1, 1), 10, 100.0),
            current_price=150.0, asset_type="STOCK_US", as_of=date(2024, 1, 1)
        )
        assert result["is_short_term"] is False

    def test_gold_short_term_under_3_years(self):
        result = compute_lot_unrealised(
            self._lot(date(2022, 1, 1), 10, 100.0),
            current_price=120.0, asset_type="GOLD", as_of=date(2024, 6, 1)
        )
        assert result["is_short_term"] is True

    def test_gold_long_term_over_3_years(self):
        result = compute_lot_unrealised(
            self._lot(date(2020, 1, 1), 10, 100.0),
            current_price=150.0, asset_type="GOLD", as_of=date(2024, 1, 1)
        )
        assert result["is_short_term"] is False

    def test_holding_days_computed(self):
        result = compute_lot_unrealised(
            self._lot(date(2023, 1, 1), 10, 100.0),
            current_price=110.0, asset_type="STOCK_IN", as_of=date(2024, 1, 1)
        )
        assert result["holding_days"] == 365


# ---------------------------------------------------------------------------
# get_tax_cost_basis (pre-2018 grandfathering)
# ---------------------------------------------------------------------------

class TestGetTaxCostBasis:
    def test_post_2018_buy_uses_actual_price(self):
        lot = FakeLot("X", 1, date(2019, 1, 1), 10, 100.0, 1000.0)
        assert get_tax_cost_basis(lot, jan31_2018_price=None) == 100.0

    def test_pre_2018_buy_jan31_higher_uses_jan31(self):
        lot = FakeLot("X", 1, date(2016, 1, 1), 10, 80.0, 800.0)
        assert get_tax_cost_basis(lot, jan31_2018_price=120.0) == 120.0

    def test_pre_2018_buy_actual_higher_uses_actual(self):
        lot = FakeLot("X", 1, date(2016, 1, 1), 10, 150.0, 1500.0)
        assert get_tax_cost_basis(lot, jan31_2018_price=100.0) == 150.0

    def test_pre_2018_buy_no_jan31_price_uses_actual(self):
        lot = FakeLot("X", 1, date(2016, 1, 1), 10, 80.0, 800.0)
        assert get_tax_cost_basis(lot, jan31_2018_price=None) == 80.0

    def test_grandfathering_cutoff_is_jan31_2018(self):
        # Bought on 2018-01-31 itself — still qualifies
        lot = FakeLot("X", 1, date(2018, 1, 31), 10, 80.0, 800.0)
        assert get_tax_cost_basis(lot, jan31_2018_price=120.0) == 120.0

    def test_bought_after_jan31_2018_no_grandfathering(self):
        lot = FakeLot("X", 1, date(2018, 2, 1), 10, 80.0, 800.0)
        # jan31 price irrelevant — bought after cutoff
        assert get_tax_cost_basis(lot, jan31_2018_price=120.0) == 80.0


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------

def test_stcg_thresholds():
    assert EQUITY_STCG_DAYS == 365
    assert STOCK_US_STCG_DAYS == 730
    assert GOLD_STCG_DAYS == 1095


# ---------------------------------------------------------------------------
# Tests for explicit stcg_days parameter in match_lots_fifo
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests for explicit stcg_days parameter in compute_lot_unrealised
# ---------------------------------------------------------------------------

def test_compute_lot_unrealised_with_explicit_stcg_days():
    lot = FakeLot(lot_id="lot1", asset_id=1, buy_date=date(2023, 1, 1), units=10,
                  buy_price_per_unit=100.0, buy_amount_inr=1000.0)
    result = compute_lot_unrealised(
        lot=lot,
        current_price=130.0,
        stcg_days=365,
        grandfathering_cutoff=None,
        as_of=date(2024, 1, 1),
    )
    assert result["unrealised_gain"] == pytest.approx(300.0)
    assert result["is_short_term"] is False  # 365 days exactly is NOT short term
    assert result["holding_days"] == 365


def test_match_lots_fifo_with_explicit_stcg_days_equity():
    """Parameterized stcg_days=365 produces same results as the old asset_type='STOCK_IN' lookup."""
    lots = [
        FakeLot(lot_id="lot1", asset_id=1, buy_date=date(2023, 1, 1), units=10,
                buy_price_per_unit=100.0, buy_amount_inr=1000.0),
    ]
    sells = [
        FakeSell(date=date(2023, 6, 1), units=5, amount_inr=600.0),  # 151 days — short-term at 365
    ]
    matches = match_lots_fifo(lots, sells, stcg_days=365)
    assert len(matches) == 1
    assert matches[0]["is_short_term"] is True


def test_match_lots_fifo_with_explicit_stcg_days_us_stock():
    """stcg_days=730 produces long-term for a 730+ day hold."""
    lots = [
        FakeLot(lot_id="lot1", asset_id=1, buy_date=date(2022, 1, 1), units=10,
                buy_price_per_unit=200.0, buy_amount_inr=2000.0),
    ]
    sells = [
        FakeSell(date=date(2024, 3, 1), units=5, amount_inr=1200.0),  # 791 days — LT at 730
    ]
    matches = match_lots_fifo(lots, sells, stcg_days=730)
    assert len(matches) == 1
    assert matches[0]["is_short_term"] is False


# ---------------------------------------------------------------------------
# compute_gains_summary — string date handling and ST/LT paths
# ---------------------------------------------------------------------------

def test_compute_gains_summary_string_dates():
    """compute_gains_summary accepts ISO string dates and classifies correctly."""
    from app.engine.lot_engine import compute_gains_summary

    # Short-term sell: buy 2023-01-01, sell 2023-06-01 (151 days < 365)
    matched_sells = [
        {
            "buy_date": "2023-01-01",
            "sell_date": "2023-06-01",
            "realised_gain_inr": 500.0,
        }
    ]
    result = compute_gains_summary([], matched_sells, asset_type="STOCK_IN")
    assert result["st_realised_gain"] == pytest.approx(500.0)
    assert result["lt_realised_gain"] == pytest.approx(0.0)


def test_compute_gains_summary_lt_string_dates():
    """Long-term path with string dates."""
    from app.engine.lot_engine import compute_gains_summary

    # Long-term sell: buy 2022-01-01, sell 2024-01-01 (730 days >= 365)
    matched_sells = [
        {
            "buy_date": "2022-01-01",
            "sell_date": "2024-01-01",
            "realised_gain_inr": 1000.0,
        }
    ]
    result = compute_gains_summary([], matched_sells, asset_type="STOCK_IN")
    assert result["st_realised_gain"] == pytest.approx(0.0)
    assert result["lt_realised_gain"] == pytest.approx(1000.0)


# ── LotHelper tests ───────────────────────────────────────────────────────────

def _make_buy(date_val, units, amount_inr, lot_id=None, txn_id=1):
    from unittest.mock import MagicMock
    t = MagicMock()
    t.type.value = "BUY"
    t.date = date_val
    t.units = units
    t.amount_inr = amount_inr
    t.lot_id = lot_id
    t.id = txn_id
    return t


def _make_sell(date_val, units, amount_inr, txn_id=2):
    from unittest.mock import MagicMock
    t = MagicMock()
    t.type.value = "SELL"
    t.date = date_val
    t.units = units
    t.amount_inr = amount_inr
    t.lot_id = None
    t.id = txn_id
    return t


def test_lot_helper_build_lots_sells():
    import pytest
    from datetime import date
    from app.engine.lot_helper import LotHelper
    helper = LotHelper(stcg_days=365)
    txns = [
        _make_buy(date(2023, 1, 1), 10, -10000, lot_id="lot1"),
        _make_sell(date(2024, 6, 1), 10, 15000),
    ]
    lots, sells = helper.build_lots_sells(txns)
    assert len(lots) == 1
    assert lots[0].buy_amount_inr == pytest.approx(100.0)   # 10000 paise / 100 = 100 INR
    assert len(sells) == 1


def test_lot_helper_match_produces_gain():
    import pytest
    from datetime import date
    from app.engine.lot_helper import LotHelper
    helper = LotHelper(stcg_days=365)
    txns = [
        _make_buy(date(2023, 1, 1), 10, -10000, lot_id="lot1"),
        _make_sell(date(2024, 6, 1), 10, 15000),
    ]
    lots, sells = helper.build_lots_sells(txns)
    matched = helper.match(lots, sells)
    assert len(matched) == 1
    assert matched[0]["realised_gain_inr"] == pytest.approx(50.0)  # (150-100) INR
    assert matched[0]["is_short_term"] is False   # 517 days >= 365


from app.engine.lot_helper import LotHelper, _Sell

class TestLotHelperSellLotId:
    """_Sell.lot_id is populated from transaction.lot_id."""

    def _make_txn(self, ttype, units, amount_paise, lot_id=None):
        from dataclasses import make_dataclass
        from datetime import date
        from enum import Enum

        class TType(Enum):
            BUY = "BUY"
            SELL = "SELL"

        T = make_dataclass("T", [
            "type", "date", "units", "amount_inr", "lot_id",
            ("id", int, 1),
        ])
        return T(
            type=TType(ttype),
            date=date(2024, 1, 1),
            units=units,
            amount_inr=amount_paise,
            lot_id=lot_id,
        )

    def test_sell_lot_id_populated_from_transaction(self):
        txns = [
            self._make_txn("BUY", 10, -100000, lot_id="lot-buy-1"),
            self._make_txn("SELL", 5, 60000, lot_id="lot-buy-1"),
        ]
        helper = LotHelper(stcg_days=730)
        lots, sells = helper.build_lots_sells(txns)
        assert len(sells) == 1
        assert sells[0].lot_id == "lot-buy-1"

    def test_sell_without_lot_id_is_none(self):
        txns = [
            self._make_txn("BUY", 10, -100000, lot_id="lot-buy-1"),
            self._make_txn("SELL", 5, 60000, lot_id=None),
        ]
        helper = LotHelper(stcg_days=730)
        _, sells = helper.build_lots_sells(txns)
        assert sells[0].lot_id is None
