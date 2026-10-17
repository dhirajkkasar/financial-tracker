"""Schedule 112A row maths and grandfathering (hand-derived)."""
from datetime import date

from app.engine.itr.schedule_112a import Schedule112ALot, build_schedule_112a


def _lot(**kw):
    base = dict(
        isin="INE002A01018", name="Reliance", units=100.0,
        buy_date=date(2024, 5, 1), cost_per_unit=50.0, sale_price_per_unit=80.0,
    )
    base.update(kw)
    return Schedule112ALot(**base)


# ── Post-2018 (AE) rows ───────────────────────────────────────────────────────

def test_single_post_2018_lot_is_consolidated_row():
    s = build_schedule_112a([_lot()])
    assert len(s.rows) == 1
    r = s.rows[0]
    assert r.share_on_or_before == "AE"
    assert r.isin == "INNOTREQUIRD"
    assert r.name == "CONSOLIDATED"
    assert r.tot_sale_value == 8000
    assert r.cost_acq_without_indx == 5000
    assert r.acquisition_cost == 5000
    assert r.ltcg_before_lower == 0
    assert r.fmv_per_unit == 0.0
    assert r.tot_fmv == 0
    assert r.total_deductions == 5000
    assert r.balance == 3000


def test_post_2018_rows_consolidate_into_one():
    s = build_schedule_112a([
        _lot(isin="INE002A01018", units=100.0, cost_per_unit=50.0, sale_price_per_unit=80.0),
        _lot(isin="INE009A01021", units=50.0, cost_per_unit=10.0, sale_price_per_unit=20.0),
    ])
    assert len(s.rows) == 1
    r = s.rows[0]
    assert r.units == 150.0
    assert r.tot_sale_value == 8000 + 1000
    assert r.cost_acq_without_indx == 5000 + 500
    assert r.balance == 3000 + 500


def test_transfer_expenses_reduce_the_gain():
    s = build_schedule_112a([_lot(transfer_expenses=100.0)])
    r = s.rows[0]
    assert r.exp_transfer == 100.0
    assert r.total_deductions == 5100
    assert r.balance == 2900


# ── Pre-2018 (BE) grandfathering ─────────────────────────────────────────────

def test_be_row_grandfathering_uses_fmv_when_higher_than_cost():
    s = build_schedule_112a([
        _lot(buy_date=date(2017, 6, 1), cost_per_unit=40.0,
             fmv_31jan2018_per_unit=70.0, sale_price_per_unit=100.0),
    ])
    r = s.rows[0]
    assert r.share_on_or_before == "BE"
    assert r.isin == "INE002A01018"      # real ISIN kept for BE rows
    assert r.name == "Reliance"
    assert r.tot_sale_value == 10000
    assert r.cost_acq_without_indx == 4000
    assert r.tot_fmv == 7000
    assert r.ltcg_before_lower == 7000       # lower(sale, fmv)
    assert r.acquisition_cost == 7000        # higher(cost, lower)
    assert r.balance == 3000


def test_be_row_grandfathering_caps_cost_at_sale_value():
    # FMV above the sale price: deemed cost is capped at the sale value -> nil gain.
    s = build_schedule_112a([
        _lot(buy_date=date(2017, 6, 1), cost_per_unit=40.0,
             fmv_31jan2018_per_unit=150.0, sale_price_per_unit=100.0),
    ])
    r = s.rows[0]
    assert r.tot_fmv == 15000
    assert r.ltcg_before_lower == 10000       # lower(10000, 15000)
    assert r.acquisition_cost == 10000
    assert r.balance == 0


def test_be_row_uses_actual_cost_when_higher_than_fmv():
    s = build_schedule_112a([
        _lot(buy_date=date(2017, 6, 1), cost_per_unit=120.0,
             fmv_31jan2018_per_unit=70.0, sale_price_per_unit=100.0),
    ])
    r = s.rows[0]
    assert r.cost_acq_without_indx == 12000
    assert r.ltcg_before_lower == 7000
    assert r.acquisition_cost == 12000
    assert r.balance == -2000                 # a capital loss


def test_be_lot_without_fmv_falls_back_to_actual_cost():
    s = build_schedule_112a([
        _lot(buy_date=date(2017, 6, 1), cost_per_unit=40.0, sale_price_per_unit=100.0),
    ])
    r = s.rows[0]
    assert r.tot_fmv == 0
    assert r.ltcg_before_lower == 0
    assert r.acquisition_cost == 4000
    assert r.balance == 6000


# ── Mixed / totals / ordering ─────────────────────────────────────────────────

def test_mixed_be_and_ae_produce_be_rows_then_one_ae_row():
    s = build_schedule_112a([
        _lot(buy_date=date(2016, 1, 1), isin="INE002A01018", name="Reliance"),
        _lot(buy_date=date(2015, 1, 1), isin="INE009A01021", name="Infosys"),
        _lot(buy_date=date(2024, 1, 1)),
    ])
    assert [r.share_on_or_before for r in s.rows] == ["BE", "BE", "AE"]


def test_be_rows_ordered_by_buy_date_then_isin():
    s = build_schedule_112a([
        _lot(buy_date=date(2017, 1, 1), isin="INE999A01099"),
        _lot(buy_date=date(2016, 1, 1), isin="INE002A01018"),
    ])
    assert [r.isin for r in s.rows] == ["INE002A01018", "INE999A01099"]


def test_totals_are_sum_of_rows():
    s = build_schedule_112a([
        _lot(buy_date=date(2016, 1, 1), cost_per_unit=40.0, fmv_31jan2018_per_unit=70.0,
             sale_price_per_unit=100.0),
        _lot(buy_date=date(2024, 1, 1), cost_per_unit=50.0, sale_price_per_unit=80.0),
    ])
    assert s.sale_value == sum(r.tot_sale_value for r in s.rows)
    assert s.deductions == sum(r.total_deductions for r in s.rows)
    assert s.balance == sum(r.balance for r in s.rows)
    assert s.total_balance == s.balance
    assert s.balance == 3000 + 3000


def test_empty_lots_yield_empty_schedule():
    s = build_schedule_112a([])
    assert s.rows == []
    assert s.balance == 0
    assert s.total_balance == 0


def test_exemption_is_not_applied_here():
    # Gain below Rs 1.25L is still reported gross in Schedule 112A.
    s = build_schedule_112a([_lot(units=100.0, cost_per_unit=10.0, sale_price_per_unit=20.0)])
    assert s.balance == 1000  # not zeroed by the 112A exemption


def test_build_is_deterministic():
    lots = [
        _lot(buy_date=date(2016, 1, 1)),
        _lot(buy_date=date(2024, 1, 1), isin="INE009A01021"),
    ]
    a = build_schedule_112a(lots)
    b = build_schedule_112a(lots)
    assert [r.__dict__ for r in a.rows] == [r.__dict__ for r in b.rows]
