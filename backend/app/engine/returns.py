from datetime import date
import logging

logger = logging.getLogger(__name__)

OUTFLOW_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST"}
INFLOW_TYPES = {"SELL", "REDEMPTION", "DIVIDEND", "INTEREST", "WITHDRAWAL", "BONUS"}
EXCLUDED_TYPES = {"SWITCH_IN", "SWITCH_OUT", "SPLIT"}

# Types that ADD units to a holding. BONUS is in INFLOW_TYPES for cashflow purposes
# (amount_inr=0 so numerically neutral for XIRR), but must also ADD to unit count.
UNIT_ADD_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST", "BONUS"}


def compute_xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """
    Compute XIRR for irregular cashflows.
    cashflows: list of (date, amount) — negative=outflow, positive=inflow
    Returns annualized rate or None if cannot converge.
    """
    if len(cashflows) < 2:
        return None
    amounts = [cf[1] for cf in cashflows]
    if all(a < 0 for a in amounts) or all(a >= 0 for a in amounts):
        return None

    # Sort by date to ensure t0 is earliest
    cashflows = sorted(cashflows, key=lambda c: c[0])
    dates = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    t0 = dates[0]
    days = [(d - t0).days / 365.0 for d in dates]

    def npv(rate):
        return sum(cf / (1 + rate) ** t for cf, t in zip(amounts, days))

    def npv_deriv(rate):
        return sum(-t * cf / (1 + rate) ** (t + 1) for cf, t in zip(amounts, days))

    # Try scipy brentq first — robust bracketed solver
    try:
        from scipy.optimize import brentq
        result = brentq(npv, -0.9999, 100.0, xtol=1e-8, maxiter=500)
        if -1 < result < 100:
            return round(result, 6)
    except Exception:
        pass

    # Fallback: Newton-Raphson from multiple starting points including deeply negative
    for guess in [0.1, 0.0, 0.5, -0.1, -0.3, -0.5, -0.7, -0.9, 1.0, 2.0]:
        try:
            rate = guess
            for _ in range(200):
                f = npv(rate)
                fp = npv_deriv(rate)
                if abs(fp) < 1e-12:
                    break
                new_rate = rate - f / fp
                if abs(new_rate - rate) < 1e-8:
                    rate = new_rate
                    break
                rate = new_rate
            if isinstance(rate, complex):
                continue
            if -1 < rate < 100 and abs(npv(rate)) < 1.0:
                return round(rate, 6)
        except (ZeroDivisionError, OverflowError, TypeError, ValueError):
            continue
    logger.warning("XIRR convergence failed")
    return None


def compute_cagr(start_value: float, end_value: float, years: float) -> float | None:
    if years <= 0 or start_value <= 0:
        return None
    return (end_value / start_value) ** (1 / years) - 1


def compute_absolute_return(invested: float, current: float) -> float:
    if invested == 0:
        return 0.0
    return (current - invested) / invested
