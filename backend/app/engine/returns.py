from datetime import date
import logging

from pyxirr import xirr as _pyxirr, InvalidPaymentsError

from app.models.asset import Asset

logger = logging.getLogger(__name__)

OUTFLOW_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST", "BILLING", "SWITCH_IN"}
INFLOW_TYPES = {"SELL", "REDEMPTION", "DIVIDEND", "INTEREST", "WITHDRAWAL", "BONUS", "SWITCH_OUT"}
EXCLUDED_TYPES = {"SPLIT"}

# Types that ADD units to a holding. BONUS is in INFLOW_TYPES for cashflow purposes
# (amount_inr=0 so numerically neutral for XIRR), but must also ADD to unit count.
# SWITCH_IN transfers units from another scheme (e.g. NPS rebalancing/scheme preference change)
# — excluded from XIRR cashflows but must increase unit count.
UNIT_ADD_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST", "BONUS", "SWITCH_IN"}

# Types that REMOVE units from a holding.
# SWITCH_OUT transfers units to another scheme — excluded from XIRR but must decrease unit count.
# BILLING deducts units from NPS account as intermediary fee payment.
UNIT_SUB_TYPES = {"SELL", "REDEMPTION", "SWITCH_OUT", "BILLING"}


def compute_xirr(cashflows: list[tuple[date, float]], asset_name="unknown") -> float | None:
    """
    Compute XIRR for irregular cashflows.
    cashflows: list of (date, amount) — negative=outflow, positive=inflow
    Returns annualized rate or None if cannot converge.
    """
    if len(cashflows) < 2:
        return None
    amounts = [cf[1] for cf in cashflows]
    if not any(a < 0 for a in amounts) or not any(a > 0 for a in amounts):
        return None

    try:
        dates = [cf[0] for cf in cashflows]
        result = _pyxirr(dates, amounts)
        if result is None or not (-1 < result < 100):
            logger.warning(f"XIRR out of range for {asset_name}: {result}")
            return None
        return round(result, 6)
    except InvalidPaymentsError as e:
        logger.warning(f"Invalid payments for XIRR ({asset_name}): {e}")
        return None
    except Exception as e:
        logger.error(f"XIRR computation failed for {asset_name}: {e}")
        return None


def compute_cagr(start_value: float, end_value: float, years: float) -> float | None:
    if years <= 0 or start_value <= 0:
        logger.warning("Invalid input for CAGR: start_value=%s, end_value=%s, years=%s",
                       start_value, end_value, years)
        return None
    return (end_value / start_value) ** (1 / years) - 1


def compute_absolute_return(invested: float, current: float) -> float:
    if invested == 0:
        return 0.0
    return (current - invested) / invested
