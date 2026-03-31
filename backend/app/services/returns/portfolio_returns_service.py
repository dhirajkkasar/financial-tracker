"""
PortfolioReturnsService — Orchestrates portfolio-level aggregations using strategy registry.

Implements portfolio methods (breakdown, allocation, gainers, overview, asset lots)
by delegating individual asset returns to the strategy registry.
"""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.engine.allocation import compute_allocation, find_top_gainers
from app.engine.lot_engine import match_lots_fifo
from app.engine.returns import compute_xirr, compute_absolute_return
from app.middleware.error_handler import NotFoundError
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.services.returns.strategies.market_based import LOT_TYPES, SELL_TYPES, _Lot, _Sell
from app.services.returns.strategies.registry import IReturnsStrategyRegistry

logger = logging.getLogger(__name__)


def _transform_strategy_response_to_api(response: dict) -> dict:
    """
    Transform AssetReturnsResponse (service format) to ReturnResponse (API format).
    
    Maps strategy layer fields to legacy API field names for backward compatibility.
    """
    return {
        "asset_id": response.get("asset_id"),
        "asset_type": response.get("asset_type"),
        "total_invested": response.get("invested"),
        "current_value": response.get("current_value"),
        "xirr": response.get("xirr"),
        "cagr": response.get("cagr"),
        "absolute_return": response.get("current_pnl"),
        "message": response.get("message"),
        # FD/RD specific
        "maturity_amount": response.get("maturity_amount"),
        "accrued_value_today": response.get("accrued_value_today"),
        "days_to_maturity": response.get("days_to_maturity"),
        # Market-based
        "total_units": response.get("total_units"),
        "avg_price": response.get("avg_price"),
        "current_price": response.get("current_price"),
        # Lot-based gains
        "st_unrealised_gain": response.get("st_unrealised_gain"),
        "lt_unrealised_gain": response.get("lt_unrealised_gain"),
        "st_realised_gain": response.get("st_realised_gain"),
        "lt_realised_gain": response.get("lt_realised_gain"),
        # FD/RD tax
        "taxable_interest": response.get("taxable_interest"),
        "potential_tax_30pct": response.get("potential_tax_30pct"),
        # Price cache metadata
        "price_is_stale": response.get("price_is_stale"),
        "price_fetched_at": response.get("price_fetched_at"),
    }



class PortfolioReturnsService:
    """Aggregates portfolio-level returns and metrics using strategy registry."""

    def __init__(
        self,
        db: Session,
        strategy_registry: IReturnsStrategyRegistry,
    ):
        self.db = db
        self.strategy_registry = strategy_registry
        self.uow_factory = lambda: UnitOfWork(db)

    def get_asset_returns(self, asset_id: int) -> dict:
        """Compute returns for a single asset using its strategy."""
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")

            asset_type = asset.asset_type.value
            strategy = self.strategy_registry.get(asset_type)
            response = strategy.compute(asset, uow)

            response_dict = response.model_dump(exclude_none=True)
            return _transform_strategy_response_to_api(response_dict)

    def get_asset_lots(self, asset_id: int) -> dict:
        """Compute FIFO lots and matched sells for a single asset using its strategy."""
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")

            asset_type = asset.asset_type.value
            strategy = self.strategy_registry.get(asset_type)
            lots = strategy.compute_lots(asset, uow)

            # Convert LotComputedResponse objects to dicts and rename 'units' to 'units_remaining'
            lot_dicts = []
            for lot in lots:
                lot_dict = lot.model_dump(exclude_none=True) if hasattr(lot, 'model_dump') else lot
                # Map 'units' to 'units_remaining' for API compatibility
                if 'units' in lot_dict:
                    lot_dict['units_remaining'] = lot_dict.pop('units')
                lot_dicts.append(lot_dict)

            # For lot-based assets, compute matched sells
            matched_sells = []
            if hasattr(strategy, 'stcg_days'):
                # This is a market-based strategy; compute matched sells
                txns = uow.transactions.list_by_asset(asset_id)
                lots_objs = []
                sells_objs = []
                
                for t in sorted(txns, key=lambda x: x.date):
                    ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
                    if ttype in LOT_TYPES and t.units:
                        is_bonus = ttype == "BONUS"
                        price_pu = 0.0 if is_bonus else (
                            t.price_per_unit or (abs(t.amount_inr / 100.0) / t.units if t.units else 0.0)
                        )
                        lots_objs.append(_Lot(
                            lot_id=t.lot_id or str(t.id),
                            buy_date=t.date,
                            units=t.units,
                            buy_price_per_unit=price_pu,
                            buy_amount_inr=0.0 if is_bonus else abs(t.amount_inr / 100.0),
                        ))
                    elif ttype in SELL_TYPES and t.units:
                        sells_objs.append(_Sell(
                            date=t.date,
                            units=t.units,
                            amount_inr=abs(t.amount_inr / 100.0),
                        ))
                
                if lots_objs and sells_objs:
                    matched = match_lots_fifo(lots_objs, sells_objs, stcg_days=strategy.stcg_days)
                    for m in matched:
                        matched_sells.append({
                            "lot_id": m["lot_id"],
                            "buy_date": m["buy_date"],
                            "buy_price_per_unit": m["buy_price_per_unit"],
                            "sell_date": m["sell_date"],
                            "sell_price_per_unit": m["sell_price_per_unit"],
                            "units_sold": m["units_sold"],
                            "is_short_term": m["is_short_term"],
                            "realised_gain_inr": m["realised_gain_inr"],
                        })

            return {
                "open_lots": lot_dicts,
                "matched_sells": matched_sells,
            }

    def get_breakdown(self) -> dict:
        """Portfolio breakdown by asset type with aggregate metrics.

        Includes inactive assets (matured FDs, fully-redeemed stocks, etc.) so that
        alltime_pnl reflects realized gains from closed positions.
        """
        with self.uow_factory() as uow:
            assets = uow.assets.list(active=None)
            breakdown = []

            for asset in assets:
                try:
                    asset_type = asset.asset_type.value
                    strategy = self.strategy_registry.get(asset_type)
                    response = strategy.compute(asset, uow)

                    total_invested = response.invested or 0.0
                    if total_invested <= 0 or response.current_value is None or response.current_value <= 0:
                        continue

                    breakdown.append({
                        "asset_type": asset_type,
                        "total_invested": total_invested,
                        "total_current_value": response.current_value,
                        "xirr": response.xirr,
                        "current_pnl": response.current_pnl,
                        "alltime_pnl": response.alltime_pnl,
                    })
                except Exception as e:
                    logger.warning("Error computing breakdown for asset %d: %s", asset.id, str(e))

            breakdown.sort(key=lambda x: x["total_current_value"] or 0, reverse=True)
            return {"breakdown": breakdown}

    def get_allocation(self) -> dict:
        """Portfolio allocation by asset class with percentages.

        Only contains the 4 canonical classes: EQUITY, DEBT, GOLD, REAL_ESTATE.
        """
        with self.uow_factory() as uow:
            assets = uow.assets.list(active=True)
            entries = []

            for asset in assets:
                try:
                    asset_type = asset.asset_type.value
                    strategy = self.strategy_registry.get(asset_type)
                    response = strategy.compute(asset, uow)

                    current_value = response.current_value
                    if current_value and current_value > 0:
                        asset_class = asset.asset_class.value
                        entries.append({
                            "asset_class": asset_class,
                            "current_value": current_value,
                        })
                except Exception as e:
                    logger.warning("Error computing allocation for asset %d: %s", asset.id, str(e))

            return compute_allocation(entries)

    def get_gainers(self, n: int = 5) -> dict:
        """Return top N gainers and top N losers by absolute return %."""
        with self.uow_factory() as uow:
            assets = uow.assets.list(active=True)
            entries = []

            for asset in assets:
                try:
                    asset_type = asset.asset_type.value
                    strategy = self.strategy_registry.get(asset_type)
                    response = strategy.compute(asset, uow)

                    total_invested = response.invested or 0.0
                    current_value = response.current_value or 0.0
                    abs_return_pct = None
                    if total_invested > 0 and current_value is not None:
                        abs_return_pct = (current_value - total_invested) / total_invested * 100

                    entries.append({
                        "asset_id": asset.id,
                        "name": asset.name,
                        "asset_type": asset_type,
                        "total_invested": total_invested,
                        "current_value": current_value,
                        "absolute_return_pct": abs_return_pct,
                        "xirr": response.xirr,
                    })
                except Exception as e:
                    logger.warning("Error computing gainers for asset %d: %s", asset.id, str(e))

            gainers = find_top_gainers(entries, n=n, gainers=True)
            losers = find_top_gainers(entries, n=n, gainers=False)
            
            return {
                "gainers": gainers,
                "losers": losers,
            }

    def get_overview(self, asset_types: Optional[list[str]] = None) -> dict:
        """High-level portfolio metrics across optionally filtered asset types."""
        with self.uow_factory() as uow:
            assets = uow.assets.list(active=None)

            if asset_types:
                assets = [a for a in assets if a.asset_type.value in asset_types]

            total_invested = 0.0
            total_current = 0.0
            all_cashflows: list[tuple] = []
            results_by_type: dict = {}

            gain_totals = {
                "st_unrealised_gain": 0.0,
                "lt_unrealised_gain": 0.0,
                "st_realised_gain": 0.0,
                "lt_realised_gain": 0.0,
                "total_taxable_interest": 0.0,
                "total_potential_tax": 0.0,
            }
            has_unrealised = False
            has_realised = False
            has_interest = False

            for asset in assets:
                try:
                    asset_type = asset.asset_type.value
                    strategy = self.strategy_registry.get(asset_type)
                    response = strategy.compute(asset, uow)

                    if asset.is_active:
                        # Active assets contribute to portfolio totals, cashflows, and unrealised gains
                        invested = response.invested or 0.0
                        current = response.current_value or 0.0

                        total_invested += invested
                        total_current += current

                        if asset_type not in results_by_type:
                            results_by_type[asset_type] = {
                                "invested": 0.0,
                                "current_value": 0.0,
                                "pnl": 0.0,
                                "pnl_pct": None,
                            }
                        results_by_type[asset_type]["invested"] += invested
                        results_by_type[asset_type]["current_value"] += current

                        # Collect cashflows for portfolio XIRR via strategy hook.
                        # Each strategy decides which transactions to include — market-based
                        # strategies include all non-excluded txns; valuation-based strategies
                        # return outflows only to avoid double-counting embedded interest.
                        all_cashflows.extend(strategy.get_portfolio_cashflows(asset, uow))

                        for key in ("st_unrealised_gain", "lt_unrealised_gain"):
                            v = getattr(response, key, None)
                            if v is not None:
                                gain_totals[key] += v
                                has_unrealised = True

                        if response.taxable_interest is not None:
                            gain_totals["total_taxable_interest"] += response.taxable_interest
                            has_interest = True
                        if response.potential_tax_30pct is not None:
                            gain_totals["total_potential_tax"] += response.potential_tax_30pct

                    # Realised gains: accumulate from all assets (active partial-sells + inactive closed positions)
                    for key in ("st_realised_gain", "lt_realised_gain"):
                        v = getattr(response, key, None)
                        if v is not None:
                            gain_totals[key] += v
                            has_realised = True

                    # Inactive valuation-based assets (FD, RD, PPF, etc.): compute() doesn't set
                    # realised gains; use the hook which returns terminal_value − invested instead.
                    if not asset.is_active and not hasattr(strategy, 'stcg_days'):
                        gain = strategy.get_inactive_realized_gain(asset, uow)
                        if gain is not None:
                            gain_totals["st_realised_gain"] += gain
                            has_realised = True

                except Exception as e:
                    logger.warning("Error computing overview for asset %d: %s", asset.id, str(e))

            # Add total current value as terminal inflow for portfolio XIRR
            all_cashflows.append((date.today(), total_current))

            portfolio_xirr = compute_xirr(all_cashflows) if len(all_cashflows) >= 2 else None
            total_pnl = total_current - total_invested
            total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else None
            abs_return = compute_absolute_return(total_invested, total_current) if total_invested > 0 else 0.0

            # Compute P&L % for each asset type
            for asset_type in results_by_type:
                type_data = results_by_type[asset_type]
                type_pnl = type_data["current_value"] - type_data["invested"]
                type_invested = type_data["invested"]
                if type_invested > 0:
                    type_data["pnl_pct"] = (type_pnl / type_invested * 100)
                type_data["pnl"] = type_pnl

            return {
                "total_invested": total_invested,
                "total_current_value": total_current,
                "total_pnl": total_pnl,
                "total_pnl_pct": total_pnl_pct,
                "absolute_return": abs_return,
                "xirr": portfolio_xirr,
                "st_unrealised_gain": gain_totals["st_unrealised_gain"] if has_unrealised else None,
                "lt_unrealised_gain": gain_totals["lt_unrealised_gain"] if has_unrealised else None,
                "st_realised_gain": gain_totals["st_realised_gain"] if has_realised else None,
                "lt_realised_gain": gain_totals["lt_realised_gain"] if has_realised else None,
                "total_taxable_interest": gain_totals["total_taxable_interest"] if has_interest else None,
                "total_potential_tax": gain_totals["total_potential_tax"] if has_interest else None,
                "by_asset_type": results_by_type,
            }
