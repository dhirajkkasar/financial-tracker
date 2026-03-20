from datetime import date

COMPOUNDING_FREQ = {
    "MONTHLY": 12,
    "QUARTERLY": 4,
    "HALF_YEARLY": 2,
    "YEARLY": 1,
    "SIMPLE": 1,
}


def compute_fd_maturity(principal: float, rate_pct: float, compounding: str, tenure_years: float) -> float:
    """A = P(1 + r/n)^(nt)"""
    n = COMPOUNDING_FREQ[compounding]
    r = rate_pct / 100
    return principal * (1 + r / n) ** (n * tenure_years)


def compute_rd_maturity(monthly_installment: float, rate_pct: float, months: int) -> float:
    """RD maturity = sum of each installment compounded for remaining months."""
    if months == 0:
        return 0.0
    r = rate_pct / 100 / 4  # quarterly rate
    # Compound each monthly installment for the remaining period
    total = 0.0
    for i in range(months):
        # installment i is invested for (months - i) months
        quarters = (months - i) / 3.0
        total += monthly_installment * (1 + r) ** quarters
    return total


def compute_fd_current_value(
    principal: float, rate_pct: float, compounding: str,
    start_date: date, maturity_date: date, as_of: date = None
) -> float:
    if as_of is None:
        as_of = date.today()
    if as_of >= maturity_date:
        tenure_years = (maturity_date - start_date).days / 365.0
        return compute_fd_maturity(principal, rate_pct, compounding, tenure_years)
    tenure_years = (as_of - start_date).days / 365.0
    if tenure_years <= 0:
        return principal
    return compute_fd_maturity(principal, rate_pct, compounding, tenure_years)
