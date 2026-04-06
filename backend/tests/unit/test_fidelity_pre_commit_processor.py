"""
Unit tests for FidelityPreCommitProcessor.

Uses a fake UoW with in-memory transaction/asset repos — no DB needed.
"""
import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.importers.base import ImportResult, ParsedTransaction


# ---------------------------------------------------------------------------
# Helpers to build ParsedTransaction (SELL with acquisition fields)
# ---------------------------------------------------------------------------

def _make_sell(
    ticker: str,
    date_sold: date,
    date_acquired: date,
    units: float,
    proceeds_inr: float,
    cost_inr: float,
    acq_forex: float = 85.0,
    lot_id: Optional[str] = None,
) -> ParsedTransaction:
    raw = f"fidelity_sale|{ticker}|{date_sold.isoformat()}|{date_acquired.isoformat()}|{round(units * 10000)}"
    txn_id = "fidelity_sale_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    return ParsedTransaction(
        source="fidelity_sale",
        asset_name=ticker,
        asset_identifier=ticker,
        asset_type="STOCK_US",
        txn_type="SELL",
        date=date_sold,
        units=units,
        amount_inr=proceeds_inr,
        acquisition_date=date_acquired,
        acquisition_cost=cost_inr,
        acquisition_forex_rate=acq_forex,
        txn_id=txn_id,
        lot_id=lot_id,
    )


# ---------------------------------------------------------------------------
# Fake UoW / repos
# ---------------------------------------------------------------------------

@dataclass
class FakeTransaction:
    id: int
    type: object           # string or enum-like with .value
    date: date
    units: float
    amount_inr: int        # paise
    lot_id: Optional[str]
    txn_id: str = ""


@dataclass
class FakeAsset:
    id: int
    identifier: str


class FakeTransactionRepo:
    def __init__(self, txns: list[FakeTransaction]):
        self._txns = txns

    def list_by_asset(self, asset_id: int) -> list[FakeTransaction]:
        return self._txns

    def get_by_txn_id(self, txn_id: str):
        return None


class FakeAssetRepo:
    def __init__(self, assets: list[FakeAsset]):
        self._assets = assets

    def get_by_identifier(self, identifier: str) -> Optional[FakeAsset]:
        return next((a for a in self._assets if a.identifier == identifier), None)


class FakeUoW:
    def __init__(self, assets=None, txns=None):
        self.assets = FakeAssetRepo(assets or [])
        self.transactions = FakeTransactionRepo(txns or [])


def _make_buy_txn(lot_id: str, buy_date: date, units: float, asset_id: int = 1) -> FakeTransaction:
    from enum import Enum
    class TType(Enum):
        BUY = "BUY"
        VEST = "VEST"
    return FakeTransaction(
        id=1, type=TType.BUY,
        date=buy_date, units=units,
        amount_inr=-int(units * 10000 * 100),
        lot_id=lot_id,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFidelityPreCommitProcessor:
    def _processor(self):
        from app.services.imports.post_processors.fidelity import FidelityPreCommitProcessor
        return FidelityPreCommitProcessor()

    def _result(self, txns: list) -> ImportResult:
        return ImportResult(source="fidelity_sale", transactions=txns)

    # --- Asset not found ---

    def test_sell_passed_through_unchanged_when_asset_not_found(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 10, 1000.0, 800.0)
        uow = FakeUoW(assets=[])   # no AMZN asset in DB
        result = self._processor().process(self._result([sell]), uow)
        assert len(result.transactions) == 1
        assert result.transactions[0].lot_id is None

    # --- Lot found: single lot, exact match ---

    def test_single_lot_found_sell_gets_lot_id(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 10, 1000.0, 800.0)
        buy = _make_buy_txn("lot-uuid-1", date(2023, 1, 1), 20)
        uow = FakeUoW(
            assets=[FakeAsset(id=1, identifier="AMZN")],
            txns=[buy],
        )
        result = self._processor().process(self._result([sell]), uow)
        assert len(result.transactions) == 1
        assert result.transactions[0].lot_id == "lot-uuid-1"
        assert result.transactions[0].units == pytest.approx(10.0)

    # --- Two lots on same date: SELL splits into 2 partials ---

    def test_two_same_date_lots_sell_splits_into_partials(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 36, 3600.0, 2800.0)
        lot_a = _make_buy_txn("lot-a", date(2023, 1, 1), 20)
        lot_a.id = 1
        lot_b = _make_buy_txn("lot-b", date(2023, 1, 1), 16)
        lot_b.id = 2
        uow = FakeUoW(
            assets=[FakeAsset(id=1, identifier="AMZN")],
            txns=[lot_a, lot_b],
        )
        result = self._processor().process(self._result([sell]), uow)
        assert len(result.transactions) == 2
        lot_ids = {t.lot_id for t in result.transactions}
        assert lot_ids == {"lot-a", "lot-b"}
        total_units = sum(t.units for t in result.transactions)
        assert total_units == pytest.approx(36.0)

    def test_partial_sells_have_proportional_amounts(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 36, 3600.0, 2800.0)
        lot_a = _make_buy_txn("lot-a", date(2023, 1, 1), 20); lot_a.id = 1
        lot_b = _make_buy_txn("lot-b", date(2023, 1, 1), 16); lot_b.id = 2
        uow = FakeUoW(
            assets=[FakeAsset(id=1, identifier="AMZN")],
            txns=[lot_a, lot_b],
        )
        result = self._processor().process(self._result([sell]), uow)
        price_per_unit = 3600.0 / 36.0
        for t in result.transactions:
            assert t.amount_inr == pytest.approx(price_per_unit * t.units, rel=1e-4)

    def test_partial_sell_txn_ids_are_stable(self):
        """Re-running produces the same txn_ids."""
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2023, 1, 1), 36, 3600.0, 2800.0)
        lot_a = _make_buy_txn("lot-a", date(2023, 1, 1), 20); lot_a.id = 1
        lot_b = _make_buy_txn("lot-b", date(2023, 1, 1), 16); lot_b.id = 2
        uow = FakeUoW(
            assets=[FakeAsset(id=1, identifier="AMZN")],
            txns=[lot_a, lot_b],
        )
        r1 = self._processor().process(self._result([sell]), uow)
        r2 = self._processor().process(self._result([sell]), uow)
        ids1 = sorted(t.txn_id for t in r1.transactions)
        ids2 = sorted(t.txn_id for t in r2.transactions)
        assert ids1 == ids2

    # --- Sell-to-cover: date_acquired == date_sold, no existing lot ---

    def test_sell_to_cover_creates_buy_sell_pair(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2024, 3, 1), 10, 1000.0, 800.0, acq_forex=84.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        types = {t.txn_type for t in result.transactions}
        assert types == {"BUY", "SELL"}

    def test_sell_to_cover_buy_and_sell_share_lot_id(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2024, 3, 1), 10, 1000.0, 800.0, acq_forex=84.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        buy = next(t for t in result.transactions if t.txn_type == "BUY")
        sell_out = next(t for t in result.transactions if t.txn_type == "SELL")
        assert buy.lot_id == sell_out.lot_id
        assert buy.lot_id is not None

    def test_sell_to_cover_buy_price_per_unit_in_usd(self):
        # cost_inr=840.0, units=10, acq_forex=84.0 → price_per_unit = 840/(10*84) = 1.0 USD
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2024, 3, 1), 10, 1000.0, 840.0, acq_forex=84.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        buy = next(t for t in result.transactions if t.txn_type == "BUY")
        assert buy.price_per_unit == pytest.approx(1.0)

    def test_sell_to_cover_buy_amount_inr_is_negative(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2024, 3, 1), 10, 1000.0, 840.0, acq_forex=84.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        buy = next(t for t in result.transactions if t.txn_type == "BUY")
        assert buy.amount_inr < 0

    # --- Orphaned sale (no matching lot, dates differ) ---

    def test_orphaned_sale_creates_buy_sell_pair(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2021, 6, 1), 5, 500.0, 400.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([sell]), uow)
        types = {t.txn_type for t in result.transactions}
        assert types == {"BUY", "SELL"}

    def test_orphaned_sale_buy_txn_id_is_stable(self):
        sell = _make_sell("AMZN", date(2024, 3, 1), date(2021, 6, 1), 5, 500.0, 400.0)
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        r1 = self._processor().process(self._result([sell]), uow)
        r2 = self._processor().process(self._result([sell]), uow)
        buy1 = next(t for t in r1.transactions if t.txn_type == "BUY")
        buy2 = next(t for t in r2.transactions if t.txn_type == "BUY")
        assert buy1.txn_id == buy2.txn_id

    # --- Non-SELL transactions pass through unchanged ---

    def test_non_sell_transactions_pass_through(self):
        other = ParsedTransaction(
            source="fidelity_sale",
            asset_name="AMZN", asset_identifier="AMZN",
            asset_type="STOCK_US", txn_type="DIVIDEND",
            date=date(2024, 1, 1), amount_inr=100.0,
        )
        uow = FakeUoW(assets=[FakeAsset(id=1, identifier="AMZN")], txns=[])
        result = self._processor().process(self._result([other]), uow)
        assert len(result.transactions) == 1
        assert result.transactions[0].txn_type == "DIVIDEND"
