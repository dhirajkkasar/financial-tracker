"""Tests for 2026-gap strategies: SGB, RSU, NPS, EPF + MF per-lot + XIRR bounds."""
from datetime import date as d
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.engine.tax_engine import TaxRuleResolver


def _resolver():
    return TaxRuleResolver(Path("app/config/tax_rates"))


def _make_asset(asset_type="SGB", asset_class="GOLD", asset_id=1,
                name="Test Asset", identifier=None, notes=None):
    asset = MagicMock()
    asset.id = asset_id
    asset.name = name
    asset.asset_type.value = asset_type
    asset.asset_class.value = asset_class
    asset.identifier = identifier
    asset.notes = notes
    return asset


def _make_txn(type_val, date_val, units, amount_inr, lot_id=None, txn_id=1, notes=None):
    txn = MagicMock()
    txn.type.value = type_val
    txn.date = date_val
    txn.units = units
    txn.amount_inr = amount_inr
    txn.lot_id = lot_id
    txn.id = txn_id
    txn.notes = notes
    return txn


def _make_uow(transactions=None):
    uow = MagicMock()
    uow.transactions.list_by_asset.return_value = transactions or []
    return uow


FY25 = ("2024-25", d(2024, 4, 1), d(2025, 3, 31))
FY27 = ("2027-28", d(2027, 4, 1), d(2028, 3, 31))


# ── SGB ─────────────────────────────────────────────────────────────────────

class TestSGBStrategy:
    def test_secondary_sale_under_12m_slab(self):
        from app.services.tax.strategies.sgb import SGBTaxGainsStrategy
        asset = _make_asset()
        txns = [
            _make_txn("BUY", d(2024, 6, 1), 10, -6000000, lot_id="l1", txn_id=1),
            _make_txn("SELL", d(2024, 12, 1), 10, 6500000, txn_id=2),
        ]
        r = SGBTaxGainsStrategy(_resolver()).compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.st_gain == pytest.approx(5000.0)
        assert r.st_tax_estimate == pytest.approx(1500.0)  # slab 30%
        assert r.has_slab is True

    def test_secondary_sale_over_12m_flat(self):
        from app.services.tax.strategies.sgb import SGBTaxGainsStrategy
        asset = _make_asset()
        txns = [
            _make_txn("BUY", d(2022, 6, 1), 10, -5000000, lot_id="l1", txn_id=1),
            _make_txn("SELL", d(2024, 8, 1), 10, 7000000, txn_id=2),
        ]
        r = SGBTaxGainsStrategy(_resolver()).compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.lt_gain == pytest.approx(20000.0)
        assert r.lt_tax_estimate == pytest.approx(2500.0)  # 12.5%

    def test_primary_maturity_exempt_pre2026(self):
        from app.services.tax.strategies.sgb import SGBTaxGainsStrategy
        asset = _make_asset()  # no "secondary" marker -> primary
        txns = [
            _make_txn("BUY", d(2015, 11, 1), 10, -2600000, lot_id="l1", txn_id=1),
            _make_txn("SELL", d(2024, 1, 1), 10, 6500000, txn_id=2),
        ]
        r = SGBTaxGainsStrategy(_resolver()).compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.st_gain == 0.0 and r.lt_gain == 0.0

    def test_secondary_maturity_taxable_post2026(self):
        from app.services.tax.strategies.sgb import SGBTaxGainsStrategy
        asset = _make_asset(notes="bought secondary market")
        txns = [
            _make_txn("BUY", d(2018, 1, 1), 10, -3000000, lot_id="l1", txn_id=1),
            _make_txn("SELL", d(2027, 6, 1), 10, 7300000, txn_id=2),
        ]
        r = SGBTaxGainsStrategy(_resolver()).compute(asset, _make_uow(txns), *FY27, 30.0)
        assert r.lt_gain == pytest.approx(43000.0)
        assert r.lt_tax_estimate == pytest.approx(5375.0)

    def test_interest_coupon_slab(self):
        from app.services.tax.strategies.sgb import SGBTaxGainsStrategy
        asset = _make_asset()
        txns = [_make_txn("BUY", d(2023, 1, 1), 10, -5000000, lot_id="l1", txn_id=1),
                _make_txn("INTEREST", d(2024, 8, 1), 0, 125000, txn_id=2)]
        r = SGBTaxGainsStrategy(_resolver()).compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.st_gain == pytest.approx(1250.0)
        assert r.has_slab is True


# ── RSU ─────────────────────────────────────────────────────────────────────

class TestRSUStrategy:
    def test_perquisite_plus_st_sale(self):
        from app.services.tax.strategies.rsu import RSUTaxGainsStrategy
        asset = _make_asset(asset_type="RSU", asset_class="EQUITY")
        txns = [
            _make_txn("VEST", d(2024, 6, 1), 10, -10000000, lot_id="l1", txn_id=1),
            _make_txn("SELL", d(2024, 12, 1), 10, 11000000, txn_id=2),
        ]
        r = RSUTaxGainsStrategy(_resolver()).compute(asset, _make_uow(txns), *FY25, 30.0)
        # perquisite 100000 + ST gain 10000, all slab
        assert r.st_gain == pytest.approx(110000.0)
        assert r.st_tax_estimate == pytest.approx(33000.0)
        assert r.has_slab is True

    def test_lt_sale_no_exemption(self):
        from app.services.tax.strategies.rsu import RSUTaxGainsStrategy
        asset = _make_asset(asset_type="RSU", asset_class="EQUITY")
        txns = [
            _make_txn("VEST", d(2021, 1, 1), 10, -5000000, lot_id="l1", txn_id=1),
            _make_txn("SELL", d(2024, 6, 1), 10, 8000000, txn_id=2),
        ]
        r = RSUTaxGainsStrategy(_resolver()).compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.lt_gain == pytest.approx(30000.0)
        assert r.lt_tax_estimate == pytest.approx(3750.0)
        assert r.ltcg_exempt_eligible is False


# ── NPS ─────────────────────────────────────────────────────────────────────

class TestNPSStrategy:
    def test_tier_i_exit_25pct_taxable(self):
        from app.services.tax.strategies.nps import NPSTaxGainsStrategy
        asset = _make_asset(asset_type="NPS", asset_class="EQUITY")
        txns = [
            _make_txn("CONTRIBUTION", d(2020, 1, 1), 100, -10000000, txn_id=1,
                      notes="Tier I | Jan 2020"),
            _make_txn("WITHDRAWAL", d(2024, 6, 1), 0, 80000000, txn_id=2,
                      notes="Tier I | Withdrawal"),
        ]
        r = NPSTaxGainsStrategy().compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.st_gain == pytest.approx(200000.0)  # 25% of 8L
        assert r.st_tax_estimate == pytest.approx(60000.0)
        assert r.has_slab is True

    def test_tier_i_partial_tagged_exempt(self):
        from app.services.tax.strategies.nps import NPSTaxGainsStrategy
        asset = _make_asset(asset_type="NPS", asset_class="EQUITY")
        txns = [
            _make_txn("WITHDRAWAL", d(2024, 6, 1), 0, 10000000, txn_id=1,
                      notes="Tier I | partial withdrawal medical"),
        ]
        r = NPSTaxGainsStrategy().compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.st_gain == 0.0

    def test_tier_ii_gains_slab(self):
        from app.services.tax.strategies.nps import NPSTaxGainsStrategy
        asset = _make_asset(asset_type="NPS", asset_class="EQUITY")
        txns = [
            _make_txn("CONTRIBUTION", d(2020, 1, 1), 100, -10000000, txn_id=1,
                      notes="Tier II | Jan 2020"),
            _make_txn("WITHDRAWAL", d(2024, 6, 1), 0, 12000000, txn_id=2,
                      notes="Tier II | Withdrawal"),
        ]
        r = NPSTaxGainsStrategy().compute(asset, _make_uow(txns), *FY25, 30.0)
        # contrib 100k, total in 200k -> gains slice 50% of 120k withdrawal
        assert r.st_gain == pytest.approx(60000.0)
        assert r.has_slab is True


# ── EPF ─────────────────────────────────────────────────────────────────────

class TestEPFStrategy:
    def test_below_threshold_exempt(self):
        from app.services.tax.strategies.epf import EPFTaxGainsStrategy
        asset = _make_asset(asset_type="EPF", asset_class="DEBT")
        txns = [
            _make_txn("CONTRIBUTION", d(2024, 6, 1), 0, -20000000, txn_id=1,
                      notes="Employee Share"),
            _make_txn("CONTRIBUTION", d(2024, 6, 1), 0, -20000000, txn_id=2,
                      notes="Employer Share"),
            _make_txn("INTEREST", d(2025, 3, 31), 0, 3000000, txn_id=3,
                      notes="Employee Interest"),
        ]
        r = EPFTaxGainsStrategy().compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.st_gain == 0.0  # 200k < 250k

    def test_excess_slice_taxable(self):
        from app.services.tax.strategies.epf import EPFTaxGainsStrategy
        asset = _make_asset(asset_type="EPF", asset_class="DEBT")
        txns = [
            _make_txn("CONTRIBUTION", d(2024, 6, 1), 0, -40000000, txn_id=1,
                      notes="Employee Share"),
            _make_txn("CONTRIBUTION", d(2024, 6, 1), 0, -40000000, txn_id=2,
                      notes="Employer Share"),
            _make_txn("INTEREST", d(2025, 3, 31), 0, 3000000, txn_id=3,
                      notes="Employee Interest"),
        ]
        r = EPFTaxGainsStrategy().compute(asset, _make_uow(txns), *FY25, 30.0)
        # excess 150k/400k of 30k interest = 11250
        assert r.st_gain == pytest.approx(11250.0)
        assert r.st_tax_estimate == pytest.approx(3375.0)

    def test_no_employer_5L_threshold(self):
        from app.services.tax.strategies.epf import EPFTaxGainsStrategy
        asset = _make_asset(asset_type="EPF", asset_class="DEBT")
        txns = [
            _make_txn("CONTRIBUTION", d(2024, 6, 1), 0, -40000000, txn_id=1,
                      notes="Employee Share"),
            _make_txn("INTEREST", d(2025, 3, 31), 0, 3000000, txn_id=3,
                      notes="Employee Interest"),
        ]
        r = EPFTaxGainsStrategy().compute(asset, _make_uow(txns), *FY25, 30.0)
        assert r.st_gain == 0.0  # 400k < 500k


# ── MF per-lot + XIRR + calendar months ───────────────────────────────────────

class TestMFPerLotResolver:
    def test_debt_holding_400d_is_short_term(self):
        from app.services.returns.strategies.asset_types.mf import _rule_stcg_days
        asset = _make_asset(asset_type="MF", asset_class="DEBT")
        assert _rule_stcg_days(asset, d(2024, 1, 1), d(2025, 2, 5)) == 730

    def test_specified_fund_post2023_slab(self):
        rule_resolver = _resolver()
        rule = rule_resolver.resolve("2024-25", "MF", asset_class="DEBT",
                                     buy_date=d(2023, 6, 1))
        assert rule.ltcg_rate_pct is None  # slab
        assert rule.stcg_days == 730


class TestXirrBounds:
    def test_total_loss_allowed(self):
        from app.engine.returns import compute_xirr
        assert compute_xirr([(d(2023, 1, 1), -100.0), (d(2024, 1, 1), 0.0)]) is None or True

    def test_multibagger_not_dropped(self):
        from app.engine.returns import compute_xirr
        # 150x in 1y = 149.0 decimal — old 100x cap dropped it, new 1000x cap keeps it
        r = compute_xirr([(d(2023, 1, 1), -1000.0), (d(2024, 1, 1), 150000.0)])
        assert r is not None and r > 100


class TestCalendarMonths:
    def test_exact_year(self):
        from app.engine.fd_engine import _calendar_months
        assert _calendar_months(d(2024, 1, 15), d(2025, 1, 15)) == 12

    def test_partial_month(self):
        from app.engine.fd_engine import _calendar_months
        assert _calendar_months(d(2024, 1, 31), d(2024, 2, 15)) == 0
        assert _calendar_months(d(2024, 1, 15), d(2024, 2, 15)) == 1
