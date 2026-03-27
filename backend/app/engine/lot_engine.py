"""
FIFO lot matching engine — pure functions, no DB access.

Terminology:
  lot    = a BUY/SIP/CONTRIBUTION/VEST transaction (one purchase event)
  sell   = a SELL/REDEMPTION transaction
  match  = pairing of sell units against the earliest available lot units
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol


# ---------------------------------------------------------------------------
# ST/LT holding thresholds (days) — FY2024-25 rules
# ---------------------------------------------------------------------------
EQUITY_STCG_DAYS = 365          # STOCK_IN, MF equity
STOCK_US_STCG_DAYS = 730        # STOCK_US, RSU (2 years)
GOLD_STCG_DAYS = 1095           # GOLD, SGB (3 years)
REAL_ESTATE_STCG_DAYS = 730     # REAL_ESTATE (2 years)

GRANDFATHERING_CUTOFF = date(2018, 1, 31)

_STCG_DAYS: dict[str, int] = {
    "STOCK_IN": EQUITY_STCG_DAYS,
    "MF":       EQUITY_STCG_DAYS,
    "RSU":      STOCK_US_STCG_DAYS,
    "STOCK_US": STOCK_US_STCG_DAYS,
    "GOLD":     GOLD_STCG_DAYS,
    "SGB":      GOLD_STCG_DAYS,
    "REAL_ESTATE": REAL_ESTATE_STCG_DAYS,
}


# ---------------------------------------------------------------------------
# Protocol — lot_engine accepts any object with these attributes
# ---------------------------------------------------------------------------
class LotLike(Protocol):
    lot_id: str
    buy_date: date
    units: float
    buy_price_per_unit: float
    buy_amount_inr: float
    jan31_2018_price: Optional[float]


class SellLike(Protocol):
    date: date
    units: float
    amount_inr: float


# ---------------------------------------------------------------------------
# match_lots_fifo
# ---------------------------------------------------------------------------

def match_lots_fifo(lots: list, sells: list, stcg_days: int = 365) -> list[dict]:
    """
    Match sell events against buy lots using FIFO (earliest lot first).

    Args:
        lots:      List of lot-like objects sorted by buy_date ascending.
        sells:     List of sell-like objects in chronological order.
        stcg_days: Short-term holding threshold in days (caller-supplied).

    Returns:
        List of match dicts:
          {lot_id, sell_date, buy_date, units_sold, units_remaining,
           buy_price_per_unit, sell_price_per_unit, realised_gain_inr, is_short_term}
    """
    # Work with mutable remaining units per lot
    remaining = {lot.lot_id: lot.units for lot in lots}
    lot_index = {lot.lot_id: lot for lot in lots}
    # Preserve FIFO order
    ordered_ids = [lot.lot_id for lot in sorted(lots, key=lambda l: l.buy_date)]

    matches: list[dict] = []

    for sell in sells:
        units_to_sell = sell.units
        sell_price = sell.amount_inr / sell.units if sell.units > 0 else 0.0

        for lot_id in ordered_ids:
            if units_to_sell <= 0:
                break
            avail = remaining.get(lot_id, 0.0)
            if avail <= 0:
                continue

            lot = lot_index[lot_id]
            consumed = min(avail, units_to_sell)
            remaining[lot_id] = avail - consumed
            units_to_sell -= consumed

            cost_basis = lot.buy_price_per_unit * consumed
            proceeds = sell_price * consumed
            realised_gain = proceeds - cost_basis
            holding_days = (sell.date - lot.buy_date).days

            matches.append({
                "lot_id": lot_id,
                "sell_date": sell.date,
                "buy_date": lot.buy_date,
                "units_sold": consumed,
                "units_remaining": remaining[lot_id],
                "buy_price_per_unit": lot.buy_price_per_unit,
                "sell_price_per_unit": sell_price,
                "realised_gain_inr": realised_gain,
                "is_short_term": holding_days < stcg_days,
            })

    return matches


# ---------------------------------------------------------------------------
# compute_lot_unrealised
# ---------------------------------------------------------------------------

def compute_lot_unrealised(
    lot,
    current_price: float,
    asset_type: str,
    as_of: Optional[date] = None,
) -> dict:
    """
    Compute unrealised P&L for a single open lot.

    Returns:
      {current_value, unrealised_gain, holding_days, is_short_term}
    """
    if as_of is None:
        as_of = date.today()

    holding_days = (as_of - lot.buy_date).days
    current_value = lot.units * current_price
    cost = lot.buy_amount_inr
    unrealised_gain = current_value - cost

    stcg_threshold = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
    is_short_term = holding_days < stcg_threshold

    return {
        "current_value": current_value,
        "unrealised_gain": unrealised_gain,
        "holding_days": holding_days,
        "is_short_term": is_short_term,
    }


# ---------------------------------------------------------------------------
# get_tax_cost_basis  (pre-2018 grandfathering for equity/MF)
# ---------------------------------------------------------------------------

def get_tax_cost_basis(lot, jan31_2018_price: Optional[float]) -> float:
    """
    Return the effective cost basis per unit for tax purposes.

    For assets bought on or before 2018-01-31 (grandfathering):
      cost_basis = max(actual_buy_price, jan31_2018_price)
    For assets bought after 2018-01-31:
      cost_basis = actual_buy_price
    """
    if lot.buy_date <= GRANDFATHERING_CUTOFF and jan31_2018_price is not None:
        return max(lot.buy_price_per_unit, jan31_2018_price)
    return lot.buy_price_per_unit


# ---------------------------------------------------------------------------
# compute_gains_summary
# ---------------------------------------------------------------------------

def compute_gains_summary(open_lots: list[dict], matched_sells: list[dict], asset_type: str) -> dict:
    """
    Aggregate ST/LT unrealized (from open_lots) and realized (from matched_sells) gains.

    open_lots items must have: is_short_term (bool), unrealised_gain (float|None)
    matched_sells items must have: buy_date (date), sell_date (date), realised_gain_inr (float)

    Returns: {st_unrealised_gain, lt_unrealised_gain, st_realised_gain, lt_realised_gain}
    """
    st_unr = sum(
        l["unrealised_gain"] for l in open_lots
        if l.get("is_short_term") and l.get("unrealised_gain") is not None
    )
    lt_unr = sum(
        l["unrealised_gain"] for l in open_lots
        if not l.get("is_short_term") and l.get("unrealised_gain") is not None
    )

    threshold = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
    st_real = 0.0
    lt_real = 0.0
    for m in matched_sells:
        buy_date = m["buy_date"]
        sell_date = m["sell_date"]
        # buy_date and sell_date may be date objects or strings
        if isinstance(buy_date, str):
            from datetime import date as _date
            buy_date = _date.fromisoformat(buy_date)
        if isinstance(sell_date, str):
            from datetime import date as _date
            sell_date = _date.fromisoformat(sell_date)
        holding = (sell_date - buy_date).days
        if holding < threshold:
            st_real += m["realised_gain_inr"]
        else:
            lt_real += m["realised_gain_inr"]

    return {
        "st_unrealised_gain": st_unr,
        "lt_unrealised_gain": lt_unr,
        "st_realised_gain": st_real,
        "lt_realised_gain": lt_real,
    }
