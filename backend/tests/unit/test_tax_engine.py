import pytest
from datetime import date
from app.engine.tax_engine import (
    parse_fy,
    classify_holding,
    apply_ltcg_exemption,
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
