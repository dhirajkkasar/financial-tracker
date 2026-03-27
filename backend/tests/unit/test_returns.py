from datetime import date
from app.engine.returns import (
    compute_xirr, compute_cagr, compute_absolute_return,
    OUTFLOW_TYPES, INFLOW_TYPES, EXCLUDED_TYPES, UNIT_ADD_TYPES,
)


def test_compute_xirr_known_inputs():
    # Invest ₹1L on 2020-01-01, receive ₹1.5L on 2023-01-01
    # Approx 3-year XIRR ~ 14.47%
    cashflows = [(date(2020, 1, 1), -100000.0), (date(2023, 1, 1), 150000.0)]
    result = compute_xirr(cashflows)
    assert result is not None
    assert abs(result - 0.1447) < 0.005  # within 0.5%


def test_compute_xirr_single_cashflow_returns_none():
    cashflows = [(date(2020, 1, 1), -100000.0)]
    assert compute_xirr(cashflows) is None


def test_compute_xirr_all_same_sign_returns_none():
    cashflows = [(date(2020, 1, 1), -100000.0), (date(2021, 1, 1), -50000.0)]
    assert compute_xirr(cashflows) is None


def test_compute_xirr_convergence_failure_returns_none():
    # Degenerate: equal inflow and outflow on same day
    cashflows = [(date(2020, 1, 1), -1.0), (date(2020, 1, 1), 1.0)]
    result = compute_xirr(cashflows)
    # Either None or some value — just ensure it doesn't crash
    assert result is None or isinstance(result, float)


def test_sign_convention_outflow_types():
    assert "BUY" in OUTFLOW_TYPES
    assert "SIP" in OUTFLOW_TYPES
    assert "CONTRIBUTION" in OUTFLOW_TYPES
    assert "VEST" in OUTFLOW_TYPES


def test_sign_convention_inflow_types():
    assert "SELL" in INFLOW_TYPES
    assert "DIVIDEND" in INFLOW_TYPES
    assert "INTEREST" in INFLOW_TYPES
    assert "REDEMPTION" in INFLOW_TYPES


def test_sign_convention_excluded_types():
    assert "SWITCH_IN" in EXCLUDED_TYPES
    assert "SWITCH_OUT" in EXCLUDED_TYPES
    assert "SPLIT" in EXCLUDED_TYPES


def test_compute_cagr_known_values():
    # 1L → 2L in 5 years = 14.87% CAGR
    result = compute_cagr(100000.0, 200000.0, 5.0)
    assert result is not None
    assert abs(result - 0.1487) < 0.001


def test_compute_cagr_zero_duration_returns_none():
    assert compute_cagr(100000.0, 150000.0, 0.0) is None


def test_compute_absolute_return():
    result = compute_absolute_return(100000.0, 125000.0)
    assert abs(result - 0.25) < 0.0001


def test_compute_xirr_convergence_failure_returns_none():
    # All same-sign cashflows — Newton's method cannot converge
    cashflows = [(date(2020, 1, 1), -100000.0), (date(2021, 1, 1), -50000.0)]
    assert compute_xirr(cashflows) is None


def test_compute_cagr_zero_start_value_returns_none():
    assert compute_cagr(0.0, 150000.0, 3.0) is None


def test_unit_add_types_includes_bonus():
    assert "BONUS" in UNIT_ADD_TYPES


def test_unit_add_types_includes_buy_sip_vest():
    assert {"BUY", "SIP", "VEST", "CONTRIBUTION"}.issubset(UNIT_ADD_TYPES)


def test_unit_add_types_excludes_sell_and_redemption():
    assert "SELL" not in UNIT_ADD_TYPES
    assert "REDEMPTION" not in UNIT_ADD_TYPES


def test_compute_absolute_return_zero_invested():
    # invested=0 should return 0.0 without division error
    assert compute_absolute_return(0, 100000.0) == 0.0
