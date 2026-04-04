"""
LotHelper — shared lot-building and FIFO matching logic.

Defines the shared _Lot, _Sell dataclasses and LOT_TYPES/SELL_TYPES constants
so that market_based.py and fifo_base.py can both import from here without
a circular dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.engine.lot_engine import match_lots_fifo


@dataclass
class _Lot:
    lot_id: str
    buy_date: date
    units: float
    buy_price_per_unit: float
    buy_amount_inr: float
    jan31_2018_price: Optional[float] = None


@dataclass
class _Sell:
    date: date
    units: float
    amount_inr: float


LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST", "BONUS", "SWITCH_IN", "BILLING"}
SELL_TYPES = {"SELL", "REDEMPTION", "WITHDRAWAL", "SWITCH_OUT"}


class LotHelper:
    """
    Wraps lot-building and FIFO matching for a given stcg_days threshold.

    Usage:
        helper = LotHelper(stcg_days=365)
        lots, sells = helper.build_lots_sells(transactions)
        matched = helper.match(lots, sells)
    """

    def __init__(self, stcg_days: int):
        self.stcg_days = stcg_days

    def build_lots_sells(self, txns) -> tuple[list[_Lot], list[_Sell]]:
        """Build sorted _Lot and _Sell lists from transaction records."""
        lots: list[_Lot] = []
        sells: list[_Sell] = []
        for t in sorted(txns, key=lambda x: x.date):
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype in LOT_TYPES and t.units:
                is_bonus = ttype == "BONUS"
                price_pu = 0.0 if is_bonus else (
                    abs(t.amount_inr / 100.0) / t.units if t.units else 0.0
                )
                lots.append(_Lot(
                    lot_id=t.lot_id or str(t.id),
                    buy_date=t.date,
                    units=t.units,
                    buy_price_per_unit=price_pu,
                    buy_amount_inr=0.0 if is_bonus else abs(t.amount_inr / 100.0),
                ))
            elif ttype in SELL_TYPES and t.units:
                sells.append(_Sell(date=t.date, units=t.units, amount_inr=abs(t.amount_inr / 100.0)))
        return lots, sells

    def match(self, lots: list[_Lot], sells: list[_Sell]) -> list[dict]:
        """Run FIFO matching; return raw match dicts from match_lots_fifo."""
        return match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
