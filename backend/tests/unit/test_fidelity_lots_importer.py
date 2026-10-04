"""Unit tests for the Fidelity lots importers (open + closed, USD exports).

Fixtures use fake tickers/numbers in the exact shape of the real NetBenefits
exports (HTML-span header in closed, footer lines, both date formats).
"""
import json
from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"

RATES = {"2025-03": 86.5, "2025-06": 84.0, "2025-10": 85.0}


def _inputs(**overrides):
    payload = {"ticker": "FAKE", "exchange_rates": dict(RATES)}
    payload.update(overrides)
    return json.dumps(payload)


def _open_bytes():
    return (FIXTURES / "fidelity_open_lots_sample.csv").read_bytes()


def _closed_bytes():
    return (FIXTURES / "fidelity_closed_lots_sample.csv").read_bytes()


# ---------------------------------------------------------------------------
# open lots
# ---------------------------------------------------------------------------

class TestFidelityOpenLotsImporter:
    def _importer(self, user_inputs=None):
        from app.importers.fidelity_lots_importer import FidelityOpenLotsImporter
        return FidelityOpenLotsImporter(user_inputs=user_inputs if user_inputs is not None else _inputs())

    def test_parses_two_remainder_lots(self):
        result = self._importer().parse(_open_bytes())
        assert result.errors == []
        assert len(result.transactions) == 2

    def test_rs_row_is_vest_with_inr_cost(self):
        (vest,) = [t for t in self._importer().parse(_open_bytes()).transactions
                   if t.date == date(2025, 3, 10)]
        assert vest.txn_type == "VEST"
        assert vest.units == pytest.approx(40.0)
        assert vest.price_per_unit == pytest.approx(127.0)
        assert vest.forex_rate == pytest.approx(86.5)
        assert vest.amount_inr == pytest.approx(-5080.0 * 86.5)
        assert vest.asset_identifier == "FAKE"

    def test_sp_row_is_buy_not_vest(self):
        (buy,) = [t for t in self._importer().parse(_open_bytes()).transactions
                  if t.date == date(2025, 6, 20)]
        assert buy.txn_type == "BUY"
        assert buy.units == pytest.approx(25.0)
        assert buy.amount_inr == pytest.approx(-3125.0 * 84.0)

    def test_txn_ids_and_lot_ids_are_stable(self):
        first = self._importer().parse(_open_bytes()).transactions
        second = self._importer().parse(_open_bytes()).transactions
        assert [t.txn_id for t in first] == [t.txn_id for t in second]
        assert [t.lot_id for t in first] == [t.lot_id for t in second]
        assert all(t.txn_id.startswith("fidelity_open_") for t in first)
        assert all(t.lot_id for t in first)

    def test_distinct_lots_get_distinct_lot_ids(self):
        txns = self._importer().parse(_open_bytes()).transactions
        assert txns[0].lot_id != txns[1].lot_id

    def test_extract_required_month_years(self):
        from app.importers.fidelity_lots_importer import FidelityOpenLotsImporter
        assert FidelityOpenLotsImporter.extract_required_month_years(_open_bytes()) == ["2025-03", "2025-06"]

    def test_missing_ticker_fails_validation(self):
        imp = self._importer(json.dumps({"exchange_rates": RATES}))
        result = imp.parse(_open_bytes())
        assert imp.validate(result).is_valid is False

    def test_missing_rate_fails_validation(self):
        imp = self._importer(_inputs(exchange_rates={"2025-03": 86.5}))
        result = imp.parse(_open_bytes())  # 2025-06 row errors at parse
        assert result.errors, "expected a row parse error for the missing month"
        assert imp.validate(result).is_valid is False


# ---------------------------------------------------------------------------
# closed lots
# ---------------------------------------------------------------------------

class TestFidelityClosedLotsImporter:
    def _importer(self, user_inputs=None):
        from app.importers.fidelity_lots_importer import FidelityClosedLotsImporter
        return FidelityClosedLotsImporter(user_inputs=user_inputs if user_inputs is not None else _inputs())

    def test_three_rows_emit_six_transactions(self):
        result = self._importer().parse(_closed_bytes())
        assert result.errors == []
        assert len(result.transactions) == 6

    def test_acquisition_leg_and_sell_share_lot_id(self):
        txns = self._importer().parse(_closed_bytes()).transactions
        for vest_leg, sell in zip(txns[::2], txns[1::2]):
            assert vest_leg.lot_id == sell.lot_id
            assert vest_leg.date <= sell.date

    def test_stc_pair_nets_to_zero_gain(self):
        txns = self._importer().parse(_closed_bytes()).transactions
        vest_leg, sell = txns[0], txns[1]  # MAR/10/2025 10u same-day
        assert vest_leg.date == sell.date == date(2025, 3, 10)
        assert vest_leg.amount_inr + sell.amount_inr == pytest.approx(0.0)

    def test_specific_lot_sale_math(self):
        txns = self._importer().parse(_closed_bytes()).transactions
        vest_leg, sell = txns[2], txns[3]  # 5u acquired Mar, sold Oct
        assert vest_leg.date == date(2025, 3, 10)
        assert sell.date == date(2025, 10, 2)
        assert vest_leg.txn_type == "VEST"  # defaulted to RS
        assert vest_leg.amount_inr == pytest.approx(-635.0 * 86.5)
        assert sell.amount_inr == pytest.approx(775.0 * 85.0)
        assert sell.price_per_unit == pytest.approx(155.0)

    def test_default_source_warns(self):
        result = self._importer().parse(_closed_bytes())
        assert any("2025-03-10" in w for w in result.warnings)

    def test_sources_override_to_buy(self):
        imp = self._importer(_inputs(sources={"2025-06-20": "SP"}))
        result = imp.parse(_closed_bytes())
        jun_legs = [t for t in result.transactions if t.date == date(2025, 6, 20)]
        assert {t.txn_type for t in jun_legs} == {"BUY", "SELL"}
        assert not any("2025-06-20" in w for w in result.warnings)
        # Other lots still default with warnings
        assert any("2025-03-10" in w for w in result.warnings)

    def test_ids_stable_across_parses(self):
        first = self._importer().parse(_closed_bytes()).transactions
        second = self._importer().parse(_closed_bytes()).transactions
        assert [t.txn_id for t in first] == [t.txn_id for t in second]
        assert [t.lot_id for t in first] == [t.lot_id for t in second]
        prefixes = {t.txn_id.split("_")[1] for t in first}
        assert prefixes == {"closed", "sold"}

    def test_extract_required_month_years_includes_sold_month(self):
        from app.importers.fidelity_lots_importer import FidelityClosedLotsImporter
        assert FidelityClosedLotsImporter.extract_required_month_years(_closed_bytes()) == [
            "2025-03", "2025-06", "2025-10"]

    def test_missing_sold_month_rate_blocks_row(self):
        imp = self._importer(_inputs(exchange_rates={"2025-03": 86.5, "2025-06": 84.0}))
        result = imp.parse(_closed_bytes())
        assert result.errors, "expected a row parse error for missing 2025-10"


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

class TestFidelityDateParsing:
    @pytest.mark.parametrize("raw,expected", [
        ("Sep-15-2026", date(2026, 9, 15)),
        ("SEP/15/2026", date(2026, 9, 15)),
        ("mar-10-2025", date(2025, 3, 10)),
        ("MAR/10/2025", date(2025, 3, 10)),
    ])
    def test_both_formats_and_cases(self, raw, expected):
        from app.importers.fidelity_lots_importer import _parse_fidelity_date
        assert _parse_fidelity_date(raw) == expected

    def test_bom_and_footers_tolerated(self):
        from app.importers.fidelity_lots_importer import _read_rows
        rows = _read_rows(b"\xef\xbb\xbfDate acquired,Quantity\nJan-05-2025,3\n,\nThe values are displayed in USD\n")
        assert len(rows) == 1
        assert rows[0]["quantity"] == "3"
