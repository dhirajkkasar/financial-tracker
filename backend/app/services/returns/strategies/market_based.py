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
from app.engine.returns import UNIT_ADD_TYPES, UNIT_SUB_TYPES, EXCLUDED_TYPES, compute_cagr
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


LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST", "BONUS", "SWITCH_IN", "BILLING"}
SELL_TYPES = {"SELL", "REDEMPTION", "WITHDRAWAL", "SWITCH_OUT"}


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

    def _build_lots_sells(self, txns) -> tuple[list[_Lot], list[_Sell]]:
        """Build _Lot and _Sell lists from transactions (sorted by date)."""
        lots: list[_Lot] = []
        sells: list[_Sell] = []
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
                sells.append(_Sell(date=t.date, units=t.units, amount_inr=abs(t.amount_inr / 100.0)))
        return lots, sells

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """Invested amount = cost basis of currently held lots (open lots only)."""
        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = self._build_lots_sells(txns)

        if not lots:
            return 0.0

        matched = match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
        sold_units: dict[str, float] = {}
        for m in matched:
            sold_units[m["lot_id"]] = sold_units.get(m["lot_id"], 0.0) + m["units_sold"]
        
        # Sum cost basis of remaining units in open lots
        total_cost = 0.0
        for lot in lots:
            units_remaining = lot.units - sold_units.get(lot.lot_id, 0.0)
            if units_remaining > 0:
                scale = units_remaining / lot.units if lot.units else 0.0
                total_cost += lot.buy_amount_inr * scale
        
        return total_cost if total_cost > 0 else 0.0

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        """Override to include lot-based gain breakdown, price metadata, units, cagr."""
        base = super().compute(asset, uow)

        txns = uow.transactions.list_by_asset(asset.id)

        # Total net units
        total_units = 0.0
        for t in txns:
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype in UNIT_ADD_TYPES:
                total_units += (t.units or 0.0)
            elif ttype in UNIT_SUB_TYPES:
                total_units -= (t.units or 0.0)

        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        current_price = (price_entry.price_inr / 100) if price_entry else None

        invested = base.invested
        avg_price = (invested / total_units) if (total_units > 0 and invested) else None

        # Unrealised gains from open lots
        lots_data = self._compute_lots_data(asset, uow)
        st_unrealised = sum(l["unrealised_gain"] for l in lots_data if l.get("is_short_term"))
        lt_unrealised = sum(l["unrealised_gain"] for l in lots_data if not l.get("is_short_term"))

        # Realised gains from matched sells
        lots_list, sells_list = self._build_lots_sells(txns)
        st_realised: Optional[float] = None
        lt_realised: Optional[float] = None
        if lots_list and sells_list:
            try:
                matched = match_lots_fifo(lots_list, sells_list, stcg_days=self.stcg_days)
                sold_units_map: dict[str, float] = {}
                for m in matched:
                    sold_units_map[m["lot_id"]] = sold_units_map.get(m["lot_id"], 0.0) + m["units_sold"]
                open_lot_dicts = []
                for lot in lots_list:
                    remaining = lot.units - sold_units_map.get(lot.lot_id, 0.0)
                    if remaining <= 0:
                        continue
                    scale = remaining / lot.units if lot.units else 0.0
                    open_lot_dicts.append({
                        "lot_id": lot.lot_id,
                        "buy_date": lot.buy_date,
                        "units_remaining": remaining,
                        "buy_price_per_unit": lot.buy_price_per_unit,
                        "buy_amount_inr": lot.buy_amount_inr * scale,
                        "current_value": (current_price * remaining) if current_price else None,
                        "unrealised_gain": None,
                        "holding_days": 0,
                        "is_short_term": True,
                    })
                gains = compute_gains_summary(open_lot_dicts, matched, asset.asset_type.value)
                st_realised = gains.get("st_realised_gain")
                lt_realised = gains.get("lt_realised_gain")
            except Exception:
                pass

        # all-time P&L = current unrealised P&L + realised
        current_pnl = base.current_pnl
        if current_pnl is not None or st_realised is not None or lt_realised is not None:
            alltime_pnl = (current_pnl or 0.0) + (st_realised or 0.0) + (lt_realised or 0.0)
        else:
            alltime_pnl = None

        # CAGR
        cagr = None
        non_excl = [t for t in txns if t.type.value not in EXCLUDED_TYPES]
        if non_excl and invested and invested > 0 and base.current_value:
            oldest = min(non_excl, key=lambda t: t.date)
            years = (date.today() - oldest.date).days / 365.0
            cagr = compute_cagr(invested, base.current_value, years)

        return base.model_copy(update={
            "total_units": total_units if total_units > 0 else None,
            "avg_price": avg_price,
            "current_price": current_price,
            "st_unrealised_gain": st_unrealised if lots_data else None,
            "lt_unrealised_gain": lt_unrealised if lots_data else None,
            "st_realised_gain": st_realised,
            "lt_realised_gain": lt_realised,
            "alltime_pnl": alltime_pnl,
            "cagr": cagr,
            "price_is_stale": price_entry.is_stale if price_entry else None,
            "price_fetched_at": price_entry.fetched_at.isoformat() if price_entry and price_entry.fetched_at else None,
        })

    def compute_lots(self, asset, uow: UnitOfWork) -> list[LotComputedResponse]:
        """Compute FIFO lots, with optional current value and unrealised gain when price available."""
        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = self._build_lots_sells(txns)

        if not lots:
            return []

        matched = match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
        sold_units: dict[str, float] = {}
        for m in matched:
            sold_units[m["lot_id"]] = sold_units.get(m["lot_id"], 0.0) + m["units_sold"]
        
        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        current_price = (price_entry.price_inr / 100) if price_entry else None
        
        result = []
        as_of = date.today()
        for lot in lots:
            units_remaining = lot.units - sold_units.get(lot.lot_id, 0.0)
            if units_remaining <= 0:
                continue
            
            scale = units_remaining / lot.units if lot.units else 0.0
            cost = lot.buy_amount_inr * scale
            
            # Compute unrealised gain only if price is available
            current_val = None
            holding_days = (as_of - lot.buy_date).days
            is_short_term = holding_days < self.stcg_days
            unrealised_gain = None
            unrealised_gain_pct = 0.0
            
            if current_price is not None:
                current_val = current_price * units_remaining
                lot_data = compute_lot_unrealised(
                    lot=lot,
                    current_price=current_price,
                    stcg_days=self.stcg_days,
                    grandfathering_cutoff=GRANDFATHERING_CUTOFF,
                    as_of=as_of,
                )
                unrealised_gain = lot_data["unrealised_gain"] * scale
                unrealised_gain_pct = (unrealised_gain / cost * 100) if cost > 0 else 0.0
                is_short_term = lot_data["is_short_term"]
            
            result.append(LotComputedResponse(
                lot_id=lot.lot_id,
                buy_date=lot.buy_date,
                units=units_remaining,
                buy_price_per_unit=lot.buy_price_per_unit,
                buy_amount_inr=cost,
                current_price=current_price or 0.0,
                current_value=current_val or 0.0,
                holding_days=holding_days,
                is_short_term=is_short_term,
                unrealised_gain=unrealised_gain or 0.0,
                unrealised_gain_pct=unrealised_gain_pct,
            ))
        
        return result

    def _compute_lots_data(self, asset, uow: UnitOfWork) -> list[dict]:
        """Build open lot dicts with unrealised gain data for this asset.
        
        Returns lot data even without a price (unrealised_gain will be None).
        """
        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = self._build_lots_sells(txns)

        if not lots:
            return []

        matched = match_lots_fifo(lots, sells, stcg_days=self.stcg_days)
        sold_units: dict[str, float] = {}
        for m in matched:
            sold_units[m["lot_id"]] = sold_units.get(m["lot_id"], 0.0) + m["units_sold"]

        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        current_price = (price_entry.price_inr / 100) if price_entry else None

        as_of = date.today()
        result = []
        for lot in lots:
            units_remaining = lot.units - sold_units.get(lot.lot_id, 0.0)
            if units_remaining <= 0:
                continue
            
            scale = units_remaining / lot.units if lot.units else 0.0
            cost = lot.buy_amount_inr * scale
            holding_days = (as_of - lot.buy_date).days
            is_short_term = holding_days < self.stcg_days
            unrealised_gain = None
            
            if current_price is not None:
                lot_data = compute_lot_unrealised(
                    lot=lot,
                    current_price=current_price,
                    stcg_days=self.stcg_days,
                    grandfathering_cutoff=GRANDFATHERING_CUTOFF,
                    as_of=as_of,
                )
                unrealised_gain = lot_data["unrealised_gain"] * scale
                is_short_term = lot_data["is_short_term"]
            
            result.append({
                "lot_id": lot.lot_id,
                "buy_date": lot.buy_date,
                "units": units_remaining,
                "buy_price_per_unit": lot.buy_price_per_unit,
                "buy_amount_inr": cost,
                "current_price": current_price or 0.0,
                "current_value": (current_price * units_remaining) if current_price else None,
                "holding_days": holding_days,
                "is_short_term": is_short_term,
                "unrealised_gain": unrealised_gain if unrealised_gain is not None else 0.0,
                "unrealised_gain_pct": (unrealised_gain / cost * 100) if (unrealised_gain and cost > 0) else 0.0,
            })
        return result
