import pytest
from datetime import date
from app.engine.tax_engine import (
    parse_fy,
    classify_holding,
    get_tax_rate,
    compute_fy_realised_gains,
    apply_ltcg_exemption,
    estimate_tax,
    find_harvest_opportunities,
    LTCG_EXEMPTION_LIMIT,
)


# ── parse_fy ─────────────────────────────────────────────────────────────────

def test_parse_fy_standard():
    start, end = parse_fy("2024-25")
    assert start == date(2024, 4, 1)
    assert end == date(2025, 3, 31)


def test_parse_fy_earlier_year():
    start, end = parse_fy("2023-24")
    assert start == date(2023, 4, 1)
    assert end == date(2024, 3, 31)


def test_parse_fy_invalid_no_hyphen():
    with pytest.raises(ValueError):
        parse_fy("2024")


def test_parse_fy_invalid_text():
    with pytest.raises(ValueError):
        parse_fy("bad-input")


# ── classify_holding ──────────────────────────────────────────────────────────

def test_classify_holding_equity_short_term():
    # Use 2023 (non-leap): Jan 1 → Dec 31 = 364 days < 365 threshold → ST
    result = classify_holding(date(2023, 1, 1), date(2023, 12, 31), stcg_days=365)
    assert result["holding_days"] == 364
    assert result["is_short_term"] is True


def test_classify_holding_equity_long_term():
    # Jan 1, 2023 → Jan 1, 2024 = 365 days == threshold → LT (threshold is <365)
    result = classify_holding(date(2023, 1, 1), date(2024, 1, 1), stcg_days=365)
    assert result["holding_days"] == 365
    assert result["is_short_term"] is False


def test_classify_holding_mf_same_thresholds_as_equity():
    st = classify_holding(date(2023, 1, 1), date(2023, 12, 31), stcg_days=365)
    assert st["is_short_term"] is True
    lt = classify_holding(date(2023, 1, 1), date(2024, 1, 1), stcg_days=365)
    assert lt["is_short_term"] is False


def test_classify_holding_us_stock_just_under_threshold():
    # Need < 730 days: Jan 1, 2023 → Dec 30, 2024 = 729 days → ST
    result = classify_holding(date(2023, 1, 1), date(2024, 12, 30), stcg_days=730)
    assert result["holding_days"] == 729
    assert result["is_short_term"] is True


def test_classify_holding_us_stock_long_term():
    # Jan 1, 2023 → Jan 2, 2025 = 731 days >= 730 → LT
    result = classify_holding(date(2023, 1, 1), date(2025, 1, 2), stcg_days=730)
    assert result["is_short_term"] is False


def test_classify_holding_gold_short_term():
    # Need < 1095 days: use Jan 1, 2022 → Dec 30, 2024 = 1094 days → ST
    result = classify_holding(date(2022, 1, 1), date(2024, 12, 30), stcg_days=1095)
    assert result["holding_days"] == 1094
    assert result["is_short_term"] is True


def test_classify_holding_gold_long_term():
    # Jan 1, 2022 → Jan 2, 2025 = 1096 days >= 1095 → LT
    result = classify_holding(date(2022, 1, 1), date(2025, 1, 2), stcg_days=1095)
    assert result["is_short_term"] is False


def test_classify_holding_real_estate_threshold():
    st = classify_holding(date(2023, 1, 1), date(2024, 12, 30), stcg_days=730)
    assert st["is_short_term"] is True
    lt = classify_holding(date(2023, 1, 1), date(2025, 1, 2), stcg_days=730)
    assert lt["is_short_term"] is False


# ── get_tax_rate ──────────────────────────────────────────────────────────────

def test_get_tax_rate_stock_in_stcg():
    r = get_tax_rate("STOCK_IN", is_short_term=True)
    assert r["rate_pct"] == 20.0
    assert r["is_slab"] is False
    assert r["is_exempt"] is False


def test_get_tax_rate_stock_in_ltcg():
    r = get_tax_rate("STOCK_IN", is_short_term=False)
    assert r["rate_pct"] == 12.5
    assert r["is_slab"] is False


def test_get_tax_rate_mf_stcg():
    r = get_tax_rate("MF", is_short_term=True)
    assert r["rate_pct"] == 20.0


def test_get_tax_rate_mf_ltcg():
    r = get_tax_rate("MF", is_short_term=False)
    assert r["rate_pct"] == 12.5


def test_get_tax_rate_us_stock_stcg_is_slab():
    r = get_tax_rate("STOCK_US", is_short_term=True)
    assert r["is_slab"] is True
    assert r["rate_pct"] is None


def test_get_tax_rate_us_stock_ltcg():
    r = get_tax_rate("STOCK_US", is_short_term=False)
    assert r["rate_pct"] == 12.5
    assert r["is_slab"] is False


def test_get_tax_rate_rsu_stcg_is_slab():
    r = get_tax_rate("RSU", is_short_term=True)
    assert r["is_slab"] is True


def test_get_tax_rate_gold_stcg_is_slab():
    r = get_tax_rate("GOLD", is_short_term=True)
    assert r["is_slab"] is True


def test_get_tax_rate_gold_ltcg():
    r = get_tax_rate("GOLD", is_short_term=False)
    assert r["rate_pct"] == 12.5


def test_get_tax_rate_fd_is_slab():
    r = get_tax_rate("FD", is_short_term=True)
    assert r["is_slab"] is True


def test_get_tax_rate_rd_is_slab():
    r = get_tax_rate("RD", is_short_term=True)
    assert r["is_slab"] is True


def test_get_tax_rate_ppf_is_exempt():
    r = get_tax_rate("PPF", is_short_term=True)
    assert r["is_exempt"] is True
    assert r["is_slab"] is False


def test_get_tax_rate_real_estate_stcg_is_slab():
    r = get_tax_rate("REAL_ESTATE", is_short_term=True)
    assert r["is_slab"] is True


def test_get_tax_rate_real_estate_ltcg():
    r = get_tax_rate("REAL_ESTATE", is_short_term=False)
    assert r["rate_pct"] == 12.5


# ── compute_fy_realised_gains ─────────────────────────────────────────────────

def _make_match(buy_date, sell_date, gain):
    return {
        "lot_id": "lot1",
        "buy_date": buy_date,
        "sell_date": sell_date,
        "units_sold": 10.0,
        "buy_price_per_unit": 100.0,
        "sell_price_per_unit": 100.0 + gain / 10,
        "realised_gain_inr": gain,
    }


def test_compute_fy_realised_gains_filters_by_fy():
    matches = [
        _make_match(date(2023, 1, 1), date(2024, 6, 1), 10000.0),   # FY2024-25 ✓
        _make_match(date(2023, 1, 1), date(2024, 3, 15), 5000.0),   # FY2023-24 ✗
        _make_match(date(2023, 1, 1), date(2025, 4, 1), 3000.0),    # FY2025-26 ✗
    ]
    result = compute_fy_realised_gains(matches, "STOCK_IN", date(2024, 4, 1), date(2025, 3, 31))
    assert result["total_gain"] == pytest.approx(10000.0)


def test_compute_fy_realised_gains_classifies_st_lt():
    matches = [
        _make_match(date(2024, 6, 1), date(2024, 9, 1), 5000.0),    # 92 days → ST
        _make_match(date(2023, 1, 1), date(2024, 6, 1), 10000.0),   # 517 days → LT
    ]
    result = compute_fy_realised_gains(matches, "STOCK_IN", date(2024, 4, 1), date(2025, 3, 31))
    assert result["st_gain"] == pytest.approx(5000.0)
    assert result["lt_gain"] == pytest.approx(10000.0)


def test_compute_fy_realised_gains_empty():
    result = compute_fy_realised_gains([], "STOCK_IN", date(2024, 4, 1), date(2025, 3, 31))
    assert result["st_gain"] == 0.0
    assert result["lt_gain"] == 0.0
    assert result["total_gain"] == 0.0


def test_compute_fy_realised_gains_losses_included():
    matches = [
        _make_match(date(2023, 1, 1), date(2024, 6, 1), -3000.0),   # LT loss
    ]
    result = compute_fy_realised_gains(matches, "STOCK_IN", date(2024, 4, 1), date(2025, 3, 31))
    assert result["lt_gain"] == pytest.approx(-3000.0)
    assert result["total_gain"] == pytest.approx(-3000.0)


def test_compute_fy_realised_gains_string_dates():
    matches = [
        {**_make_match(date(2023, 1, 1), date(2024, 6, 1), 8000.0),
         "buy_date": "2023-01-01", "sell_date": "2024-06-01"},
    ]
    result = compute_fy_realised_gains(matches, "STOCK_IN", date(2024, 4, 1), date(2025, 3, 31))
    assert result["lt_gain"] == pytest.approx(8000.0)


def test_compute_fy_realised_gains_boundary_dates_included():
    matches = [
        _make_match(date(2023, 1, 1), date(2024, 4, 1), 1000.0),   # exactly fy_start
        _make_match(date(2023, 1, 1), date(2025, 3, 31), 2000.0),  # exactly fy_end
    ]
    result = compute_fy_realised_gains(matches, "STOCK_IN", date(2024, 4, 1), date(2025, 3, 31))
    assert result["total_gain"] == pytest.approx(3000.0)


# ── apply_ltcg_exemption ──────────────────────────────────────────────────────

def test_ltcg_exemption_below_limit():
    result = apply_ltcg_exemption(100_000.0, "STOCK_IN")
    assert result["taxable_lt_gain"] == pytest.approx(0.0)
    assert result["exemption_used"] == pytest.approx(100_000.0)


def test_ltcg_exemption_above_limit():
    result = apply_ltcg_exemption(200_000.0, "STOCK_IN")
    assert result["taxable_lt_gain"] == pytest.approx(75_000.0)
    assert result["exemption_used"] == pytest.approx(LTCG_EXEMPTION_LIMIT)


def test_ltcg_exemption_exact_limit():
    result = apply_ltcg_exemption(125_000.0, "STOCK_IN")
    assert result["taxable_lt_gain"] == pytest.approx(0.0)
    assert result["exemption_used"] == pytest.approx(LTCG_EXEMPTION_LIMIT)


def test_ltcg_exemption_applies_to_mf():
    result = apply_ltcg_exemption(200_000.0, "MF")
    assert result["taxable_lt_gain"] == pytest.approx(75_000.0)


def test_ltcg_no_exemption_for_us_stock():
    result = apply_ltcg_exemption(100_000.0, "STOCK_US")
    assert result["taxable_lt_gain"] == pytest.approx(100_000.0)
    assert result["exemption_used"] == 0.0


def test_ltcg_no_exemption_for_gold():
    result = apply_ltcg_exemption(100_000.0, "GOLD")
    assert result["taxable_lt_gain"] == pytest.approx(100_000.0)


def test_ltcg_no_exemption_for_real_estate():
    result = apply_ltcg_exemption(100_000.0, "REAL_ESTATE")
    assert result["taxable_lt_gain"] == pytest.approx(100_000.0)


def test_ltcg_exemption_only_on_positive_gain():
    result = apply_ltcg_exemption(-5000.0, "STOCK_IN")
    assert result["taxable_lt_gain"] == pytest.approx(-5000.0)
    assert result["exemption_used"] == 0.0


# ── estimate_tax ──────────────────────────────────────────────────────────────

def test_estimate_tax_stock_in():
    result = estimate_tax(50_000.0, 200_000.0, "STOCK_IN")
    assert result["st_tax"] == pytest.approx(10_000.0)      # 50k × 20%
    assert result["lt_tax"] == pytest.approx(9_375.0)       # (200k-125k) × 12.5%
    assert result["total_tax"] == pytest.approx(19_375.0)
    assert result["is_st_slab"] is False
    assert result["is_lt_exempt"] is False
    assert result["ltcg_exemption_used"] == pytest.approx(125_000.0)


def test_estimate_tax_stock_in_lt_below_exemption():
    result = estimate_tax(0.0, 100_000.0, "STOCK_IN")
    assert result["lt_tax"] == pytest.approx(0.0)
    assert result["ltcg_exemption_used"] == pytest.approx(100_000.0)


def test_estimate_tax_mf():
    result = estimate_tax(20_000.0, 150_000.0, "MF")
    assert result["st_tax"] == pytest.approx(4_000.0)       # 20k × 20%
    assert result["lt_tax"] == pytest.approx(3_125.0)       # (150k-125k) × 12.5%


def test_estimate_tax_us_stock_st_is_slab():
    result = estimate_tax(50_000.0, 200_000.0, "STOCK_US")
    assert result["st_tax"] is None
    assert result["is_st_slab"] is True
    assert result["lt_tax"] == pytest.approx(25_000.0)      # 200k × 12.5% (no exemption)


def test_estimate_tax_gold_st_is_slab():
    result = estimate_tax(30_000.0, 150_000.0, "GOLD")
    assert result["st_tax"] is None
    assert result["is_st_slab"] is True
    assert result["lt_tax"] == pytest.approx(18_750.0)      # 150k × 12.5%


def test_estimate_tax_ppf_all_exempt():
    result = estimate_tax(50_000.0, 200_000.0, "PPF")
    assert result["st_tax"] is None
    assert result["lt_tax"] is None
    assert result["is_lt_exempt"] is True


def test_estimate_tax_fd_is_slab():
    result = estimate_tax(50_000.0, 0.0, "FD")
    assert result["st_tax"] is None
    assert result["is_st_slab"] is True


def test_estimate_tax_zero_gains():
    result = estimate_tax(0.0, 0.0, "STOCK_IN")
    assert result["st_tax"] == pytest.approx(0.0)
    assert result["lt_tax"] == pytest.approx(0.0)
    assert result["total_tax"] == pytest.approx(0.0)


def test_estimate_tax_losses_produce_zero_tax():
    # Losses should not produce negative tax
    result = estimate_tax(-10_000.0, -20_000.0, "STOCK_IN")
    assert result["st_tax"] == pytest.approx(0.0)
    assert result["lt_tax"] == pytest.approx(0.0)


# ── find_harvest_opportunities ────────────────────────────────────────────────

def _make_open_lot(asset_id, asset_type, unrealised_gain, is_short_term=True):
    return {
        "asset_id": asset_id,
        "asset_name": f"Asset {asset_id}",
        "asset_type": asset_type,
        "lot_id": f"lot_{asset_id}",
        "buy_date": date(2024, 1, 1),
        "units_remaining": 10.0,
        "buy_price_per_unit": 100.0,
        "current_value": 1000.0 + unrealised_gain,
        "unrealised_gain": unrealised_gain,
        "holding_days": 200,
        "is_short_term": is_short_term,
    }


def test_harvest_only_includes_losses():
    lots = [
        _make_open_lot(1, "STOCK_IN", -5000.0),
        _make_open_lot(2, "STOCK_IN", +3000.0),   # gain — not a harvest candidate
        _make_open_lot(3, "MF", -2000.0),
    ]
    result = find_harvest_opportunities(lots)
    ids = [o["asset_id"] for o in result]
    assert 1 in ids
    assert 3 in ids
    assert 2 not in ids


def test_harvest_sorted_by_loss_magnitude():
    lots = [
        _make_open_lot(1, "STOCK_IN", -2000.0),
        _make_open_lot(2, "STOCK_IN", -8000.0),
        _make_open_lot(3, "STOCK_IN", -500.0),
    ]
    result = find_harvest_opportunities(lots)
    losses = [o["unrealised_loss"] for o in result]
    assert losses == sorted(losses, reverse=True)
    assert losses[0] == pytest.approx(8000.0)


def test_harvest_empty_when_no_losses():
    lots = [
        _make_open_lot(1, "STOCK_IN", +3000.0),
        _make_open_lot(2, "MF", +1000.0),
    ]
    assert find_harvest_opportunities(lots) == []


def test_harvest_includes_st_lt_flag():
    lots = [
        _make_open_lot(1, "STOCK_IN", -3000.0, is_short_term=True),
        _make_open_lot(2, "MF", -1000.0, is_short_term=False),
    ]
    result = find_harvest_opportunities(lots)
    by_id = {o["asset_id"]: o for o in result}
    assert by_id[1]["is_short_term"] is True
    assert by_id[2]["is_short_term"] is False


def test_harvest_none_unrealised_gain_excluded():
    lots = [
        {**_make_open_lot(1, "STOCK_IN", -1000.0), "unrealised_gain": None},
        _make_open_lot(2, "STOCK_IN", -500.0),
    ]
    result = find_harvest_opportunities(lots)
    ids = [o["asset_id"] for o in result]
    assert 1 not in ids
    assert 2 in ids


def test_harvest_unrealised_loss_field_is_absolute():
    lots = [_make_open_lot(1, "STOCK_IN", -4000.0)]
    result = find_harvest_opportunities(lots)
    assert result[0]["unrealised_loss"] == pytest.approx(4000.0)


# ── TaxRatePolicy ─────────────────────────────────────────────────────────────

import yaml
from pathlib import Path


@pytest.fixture
def temp_tax_config(tmp_path):
    """Create a minimal tax rate YAML for testing."""
    rates = {
        "STOCK_IN": {
            "stcg_rate_pct": 20.0,
            "stcg_is_slab": False,
            "ltcg_rate_pct": 12.5,
            "ltcg_is_slab": False,
            "ltcg_threshold_days": 365,
            "ltcg_exemption_inr": 125000.0,
            "is_exempt": False,
            "maturity_exempt": False,
        },
        "PPF": {
            "stcg_rate_pct": None,
            "stcg_is_slab": False,
            "ltcg_rate_pct": None,
            "ltcg_is_slab": False,
            "ltcg_threshold_days": None,
            "ltcg_exemption_inr": 0.0,
            "is_exempt": True,
            "maturity_exempt": False,
        },
        "FD": {
            "stcg_rate_pct": None,
            "stcg_is_slab": True,
            "ltcg_rate_pct": None,
            "ltcg_is_slab": True,
            "ltcg_threshold_days": None,
            "ltcg_exemption_inr": 0.0,
            "is_exempt": False,
            "maturity_exempt": False,
        },
    }
    fy_file = tmp_path / "2024-25.yaml"
    fy_file.write_text(yaml.dump(rates))
    return tmp_path


def test_tax_rate_policy_loads_stock_in(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    rate = policy.get_rate("2024-25", "STOCK_IN")
    assert rate.stcg_rate_pct == 20.0
    assert rate.ltcg_rate_pct == 12.5
    assert rate.ltcg_exemption_inr == 125000.0
    assert rate.is_exempt is False


def test_tax_rate_policy_loads_ppf_exempt(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    rate = policy.get_rate("2024-25", "PPF")
    assert rate.is_exempt is True


def test_tax_rate_policy_missing_fy_raises(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    with pytest.raises(ValueError, match="No tax rate config for FY"):
        policy.get_rate("2099-00", "STOCK_IN")


def test_tax_rate_policy_caches_file(temp_tax_config):
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    rate1 = policy.get_rate("2024-25", "STOCK_IN")
    rate2 = policy.get_rate("2024-25", "STOCK_IN")
    assert rate1 is rate2  # same object from cache


def test_tax_rate_policy_missing_asset_type(temp_tax_config):  # noqa: F811 (redefinition ok — different fixture)
    from app.engine.tax_engine import TaxRatePolicy

    policy = TaxRatePolicy(temp_tax_config)
    with pytest.raises(ValueError, match="No tax rate for asset_type"):
        policy.get_rate("2024-25", "UNKNOWN_TYPE")


# ── classify_holding with explicit stcg_days ──────────────────────────────────

def test_classify_holding_with_explicit_stcg_days():
    from app.engine.tax_engine import classify_holding

    result = classify_holding(
        buy_date=date(2023, 1, 1),
        sell_date=date(2023, 6, 1),
        stcg_days=365,
    )
    assert result["is_short_term"] is True
    assert result["holding_days"] == 151


def test_classify_holding_long_term_explicit():
    from app.engine.tax_engine import classify_holding

    result = classify_holding(
        buy_date=date(2022, 1, 1),
        sell_date=date(2023, 6, 1),
        stcg_days=365,
    )
    assert result["is_short_term"] is False
