"""
MarketBasedStrategy — current value = units × price_cache NAV.

Subclasses declare stcg_days: ClassVar[int] and override only what's needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Optional

from app.engine.lot_engine import (
    match_lots_fifo,
    compute_gains_summary,
    compute_lot_unrealised,
    GRANDFATHERING_CUTOFF,
)
from app.engine.returns import UNIT_ADD_TYPES, UNIT_SUB_TYPES
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse, LotComputedResponse
from app.services.returns.strategies.base import AssetReturnsStrategy


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


LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST", "BONUS"}
SELL_TYPES = {"SELL", "REDEMPTION"}


class MarketBasedStrategy(AssetReturnsStrategy):
    """
    Intermediate: get_current_value = units × price_cache NAV.

    Subclasses must declare:
        stcg_days: ClassVar[int]
    """
    stcg_days: ClassVar[int]  # must be set by each leaf class

    def get_current_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """units × latest price_cache NAV, converted from paise to INR."""
        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        if price_entry is None or price_entry.price_inr is None:
            return None

        txns = uow.transactions.list_by_asset(asset.id)
        total_units = 0.0
        for t in txns:
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            units = t.units or 0.0
            if ttype in UNIT_ADD_TYPES:
                total_units += units
            elif ttype in UNIT_SUB_TYPES:
                total_units -= units

        price_inr = price_entry.price_inr / 100  # paise → INR
        return round(total_units * price_inr, 2)

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        """Override to include lot-based gain breakdown and price metadata."""
        base = super().compute(asset, uow)

        lots_data = self._compute_lots_data(asset, uow)
        st_unrealised = sum(
            l["unrealised_gain"] for l in lots_data if l.get("is_short_term")
        )
        lt_unrealised = sum(
            l["unrealised_gain"] for l in lots_data if not l.get("is_short_term")
        )

        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        return base.model_copy(update={
            "st_unrealised_gain": st_unrealised if lots_data else None,
            "lt_unrealised_gain": lt_unrealised if lots_data else None,
            "price_is_stale": price_entry.is_stale if price_entry else None,
            "price_fetched_at": price_entry.fetched_at.isoformat() if price_entry and price_entry.fetched_at else None,
        })

    def compute_lots(self, asset, uow: UnitOfWork) -> list[LotComputedResponse]:
        lots_data = self._compute_lots_data(asset, uow)
        return [
            LotComputedResponse(
                lot_id=l["lot_id"],
                buy_date=l["buy_date"],
                units=l["units"],
                buy_price_per_unit=l["buy_price_per_unit"],
                buy_amount_inr=l["buy_amount_inr"],
                current_price=l.get("current_price", 0.0),
                current_value=l.get("current_value", 0.0),
                holding_days=l["holding_days"],
                is_short_term=l["is_short_term"],
                unrealised_gain=l["unrealised_gain"],
                unrealised_gain_pct=l.get("unrealised_gain_pct", 0.0),
            )
            for l in lots_data
        ]

    def _compute_lots_data(self, asset, uow: UnitOfWork) -> list[dict]:
        """Build open lot dicts with unrealised gain data for this asset."""
        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        if price_entry is None:
            return []
        current_price = price_entry.price_inr / 100

        txns = uow.transactions.list_by_asset(asset.id)
        lots = []
        sells = []
        for t in sorted(txns, key=lambda x: x.date):
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype in LOT_TYPES and t.units:
                is_bonus = ttype == "BONUS"
                price_pu = 0.0 if is_bonus else (
                    t.price_per_unit or (abs(t.amount_inr / 100.0) / t.units if t.units else 0.0)
                )
                lots.append(_Lot(
                    lot_id=t.lot_id or str(t.id),
                    buy_date=t.date,
                    units=t.units,
                    buy_price_per_unit=price_pu,
                    buy_amount_inr=0.0 if is_bonus else abs(t.amount_inr / 100.0),
                ))
            elif ttype in SELL_TYPES and t.units:
                sells.append(_Sell(
                    date=t.date,
                    units=t.units,
                    amount_inr=abs(t.amount_inr / 100.0),
                ))

        matched = match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
        sold_units: dict[str, float] = {}
        for m in matched:
            sold_units[m["lot_id"]] = sold_units.get(m["lot_id"], 0.0) + m["units_sold"]

        as_of = date.today()
        result = []
        for lot in lots:
            units_remaining = lot.units - sold_units.get(lot.lot_id, 0.0)
            if units_remaining <= 0:
                continue
            lot_data = compute_lot_unrealised(
                lot=lot,
                current_price=current_price,
                stcg_days=self.stcg_days,
                grandfathering_cutoff=GRANDFATHERING_CUTOFF,
                as_of=as_of,
            )
            scale = units_remaining / lot.units if lot.units else 0.0
            cost = lot.buy_amount_inr * scale
            unrealised = lot_data["unrealised_gain"] * scale
            result.append({
                "lot_id": lot.lot_id,
                "buy_date": lot.buy_date,
                "units": units_remaining,
                "buy_price_per_unit": lot.buy_price_per_unit,
                "buy_amount_inr": cost,
                "current_price": current_price,
                "current_value": current_price * units_remaining,
                "holding_days": lot_data["holding_days"],
                "is_short_term": lot_data["is_short_term"],
                "unrealised_gain": unrealised,
                "unrealised_gain_pct": (unrealised / cost * 100) if cost > 0 else 0.0,
            })
        return result
