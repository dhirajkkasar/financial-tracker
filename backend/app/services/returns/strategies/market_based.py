"""
MarketBasedStrategy — current value = units × price_cache NAV.

Subclasses declare stcg_days: ClassVar[int] and override only what's needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Optional

from app.engine.lot_engine import (
    match_lots,
    compute_gains_summary,
    compute_lot_unrealised,
    GRANDFATHERING_CUTOFF,
)
from app.engine.lot_helper import LotHelper, LOT_TYPES, SELL_TYPES, _Lot, _Sell
from app.engine.returns import UNIT_ADD_TYPES, UNIT_SUB_TYPES, EXCLUDED_TYPES, compute_cagr
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.returns import AssetReturnsResponse, LotComputedResponse
from app.services.returns.strategies.base import AssetReturnsStrategy


@dataclass
class _OpenLot:
    """An open (partially or fully remaining) lot after FIFO matching."""
    lot: _Lot
    units_remaining: float
    scale: float          # units_remaining / lot.units
    cost: float           # lot.buy_amount_inr * scale
    holding_days: int
    is_short_term: bool
    unrealised_gain: Optional[float]


def _compute_total_units(txns) -> float:
    """Sum net units across transactions using add/sub type sets."""
    total = 0.0
    for t in txns:
        ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
        units = t.units or 0.0
        if ttype in UNIT_ADD_TYPES:
            total += units
        elif ttype in UNIT_SUB_TYPES:
            total -= units
    return total


def _accumulate_sold_units(matched: list[dict]) -> dict[str, float]:
    """Build a lot_id -> total units sold mapping from FIFO match results."""
    sold: dict[str, float] = {}
    for m in matched:
        sold[m["lot_id"]] = sold.get(m["lot_id"], 0.0) + m["units_sold"]
    return sold


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
        if price_entry is None or price_entry.price_inr is None or price_entry.price_inr <= 0:
            return None

        txns = uow.transactions.list_by_asset(asset.id)
        total_units = _compute_total_units(txns)

        if total_units <= 0:
            return None

        price_inr = price_entry.price_inr / 100  # paise -> INR
        return round(total_units * price_inr, 2)

    def _build_lots_sells(self, txns) -> tuple[list[_Lot], list[_Sell]]:
        """Build _Lot and _Sell lists from transactions (sorted by date)."""
        return LotHelper(stcg_days=self.stcg_days).build_lots_sells(txns)

    def _match_and_get_open_lots(
        self,
        lots: list[_Lot],
        sells: list[_Sell],
        current_price: Optional[float],
        as_of: Optional[date] = None,
    ) -> tuple[list[_OpenLot], list[dict]]:
        """Run FIFO matching and return open lots with unrealised gain data.

        Returns:
            (open_lots, matched) where matched is the raw FIFO match result.
        """
        matched = match_lots(lots, sells, stcg_days=self.stcg_days)
        sold_units = _accumulate_sold_units(matched)

        if as_of is None:
            as_of = date.today()

        open_lots: list[_OpenLot] = []
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

            open_lots.append(_OpenLot(
                lot=lot,
                units_remaining=units_remaining,
                scale=scale,
                cost=cost,
                holding_days=holding_days,
                is_short_term=is_short_term,
                unrealised_gain=unrealised_gain,
            ))

        return open_lots, matched

    def get_invested_value(self, asset, uow: UnitOfWork) -> Optional[float]:
        """
        Active position: cost basis of currently held (open) lots after FIFO matching.
        Fully redeemed: total cost of all lots ever bought (for historical invested/gains display).
        """
        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = self._build_lots_sells(txns)

        if not lots:
            return 0.0

        open_lots, _ = self._match_and_get_open_lots(lots, sells, current_price=None)

        if not open_lots:
            # Fully redeemed — no remaining position; return total historical cost for gains display
            return sum(lot.buy_amount_inr for lot in lots)

        total_cost = sum(ol.cost for ol in open_lots)
        return total_cost if total_cost > 0 else 0.0

    def compute(self, asset, uow: UnitOfWork) -> AssetReturnsResponse:
        """Override to include lot-based gain breakdown, price metadata, units, cagr."""
        base = super().compute(asset, uow)

        txns = uow.transactions.list_by_asset(asset.id)
        total_units = _compute_total_units(txns)

        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        current_price = (price_entry.price_inr / 100) if price_entry else None

        invested = base.invested
        avg_price = (invested / total_units) if (total_units > 0 and invested) else None

        # Build lots once, reuse for both unrealised and realised gains
        lots_list, sells_list = self._build_lots_sells(txns)
        open_lots, matched = self._match_and_get_open_lots(
            lots_list, sells_list, current_price,
        ) if lots_list else ([], [])

        # Unrealised gains from open lots
        st_unrealised = sum(ol.unrealised_gain or 0.0 for ol in open_lots if ol.is_short_term)
        lt_unrealised = sum(ol.unrealised_gain or 0.0 for ol in open_lots if not ol.is_short_term)

        # Realised gains from matched sells
        st_realised: Optional[float] = None
        lt_realised: Optional[float] = None
        if lots_list and sells_list:
            try:
                open_lot_dicts = [
                    {
                        "lot_id": ol.lot.lot_id,
                        "buy_date": ol.lot.buy_date,
                        "units_remaining": ol.units_remaining,
                        "buy_price_per_unit": ol.lot.buy_price_per_unit,
                        "buy_amount_inr": ol.cost,
                        "current_value": (current_price * ol.units_remaining) if current_price else None,
                        "unrealised_gain": None,
                        "holding_days": 0,
                        "is_short_term": True,
                    }
                    for ol in open_lots
                ]
                gains = compute_gains_summary(open_lot_dicts, matched, asset.asset_type.value)
                st_realised = gains.get("st_realised_gain")
                lt_realised = gains.get("lt_realised_gain")
            except Exception:
                pass

        # all-time P&L = current unrealised P&L + realised
        current_pnl = base.current_pnl
        alltime_pnl = (current_pnl or 0.0) + (st_realised or 0.0) + (lt_realised or 0.0)

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
            "st_unrealised_gain": st_unrealised if open_lots else None,
            "lt_unrealised_gain": lt_unrealised if open_lots else None,
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

        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        current_price = (price_entry.price_inr / 100) if price_entry else None

        open_lots, _ = self._match_and_get_open_lots(lots, sells, current_price)

        result = []
        for ol in open_lots:
            current_val = (current_price * ol.units_remaining) if current_price is not None else None
            unrealised_gain = ol.unrealised_gain
            unrealised_gain_pct = (unrealised_gain / ol.cost * 100) if (unrealised_gain and ol.cost > 0) else 0.0

            result.append(LotComputedResponse(
                lot_id=ol.lot.lot_id,
                buy_date=ol.lot.buy_date,
                units=ol.units_remaining,
                buy_price_per_unit=ol.lot.buy_price_per_unit,
                buy_amount_inr=ol.cost,
                current_price=current_price or 0.0,
                current_value=current_val or 0.0,
                holding_days=ol.holding_days,
                is_short_term=ol.is_short_term,
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

        price_entry = uow.price_cache.get_by_asset_id(asset.id)
        current_price = (price_entry.price_inr / 100) if price_entry else None

        open_lots, _ = self._match_and_get_open_lots(lots, sells, current_price)

        return [
            {
                "lot_id": ol.lot.lot_id,
                "buy_date": ol.lot.buy_date,
                "units": ol.units_remaining,
                "buy_price_per_unit": ol.lot.buy_price_per_unit,
                "buy_amount_inr": ol.cost,
                "current_price": current_price or 0.0,
                "current_value": (current_price * ol.units_remaining) if current_price else None,
                "holding_days": ol.holding_days,
                "is_short_term": ol.is_short_term,
                "unrealised_gain": ol.unrealised_gain if ol.unrealised_gain is not None else 0.0,
                "unrealised_gain_pct": (ol.unrealised_gain / ol.cost * 100) if (ol.unrealised_gain and ol.cost > 0) else 0.0,
            }
            for ol in open_lots
        ]
