from app.engine.fd_engine import compute_fd_maturity, compute_rd_maturity, compute_fd_current_value
from datetime import date


def test_fd_maturity_quarterly_compounding():
    # ₹1L at 8.75% quarterly for 3 years
    # A = P*(1 + r/n)^(nt) = 100000*(1 + 0.0875/4)^12 ≈ 129650
    result = compute_fd_maturity(100000.0, 8.75, "QUARTERLY", 3.0)
    assert abs(result - 129650.0) < 200  # within ₹200


def test_fd_maturity_monthly_compounding():
    # ₹1L at 8% monthly for 1 year
    result = compute_fd_maturity(100000.0, 8.0, "MONTHLY", 1.0)
    assert abs(result - 108300.0) < 200


def test_fd_current_value_active_fd():
    # Started 2023-01-01, matures 2026-01-01, check value at 2024-07-01 (midpoint ~)
    result = compute_fd_current_value(100000.0, 8.0, "QUARTERLY", date(2023, 1, 1), date(2026, 1, 1), as_of=date(2024, 7, 1))
    assert result > 100000.0  # accrued interest
    assert result < compute_fd_maturity(100000.0, 8.0, "QUARTERLY", 3.0)


def test_rd_maturity_known_values():
    # ₹5000/month at 7% for 12 months
    result = compute_rd_maturity(5000.0, 7.0, 12)
    assert abs(result - 62316.0) < 500  # RD maturity formula


def test_rd_maturity_zero_months_returns_zero():
    assert compute_rd_maturity(5000.0, 7.0, 0) == 0.0
