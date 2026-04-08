import logging
from datetime import date
from pathlib import Path

import app.services.tax.strategies  # noqa: F401 — triggers @register_tax_strategy decorators
from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS, match_lots_fifo
from app.engine.lot_engine import match_lots, compute_lot_unrealised
from app.engine.tax_engine import (
    TaxRuleResolver,
    parse_fy,
    apply_ltcg_exemption,
    find_harvest_opportunities,
)
from app.repositories.unit_of_work import IUnitOfWorkFactory
from app.services.returns.strategies.market_based import LOT_TYPES, SELL_TYPES, _Lot, _Sell
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxStrategyRegistry

logger = logging.getLogger(__name__)

SKIPPED_ASSET_TYPES = {"EPF", "PPF", "NPS", "SGB", "RSU"}
LOT_ASSET_TYPES = {"STOCK_IN", "STOCK_US", "MF", "GOLD"}   # FIFO-tracked for unrealised
ASSET_CLASS_ORDER = ["EQUITY", "DEBT", "GOLD", "REAL_ESTATE"]

LTCG_NEAR_THRESHOLD = 125_000.0
LTCG_NEAR_PCT = 0.10


class TaxService:
    def __init__(
        self,
        uow_factory: IUnitOfWorkFactory,
        slab_rate_pct: float = 30.0,
        resolver: TaxRuleResolver | None = None,
    ):
        self._uow_factory = uow_factory
        self._slab_rate_pct = slab_rate_pct
        self._registry = TaxStrategyRegistry()
        self._resolver = resolver

    # ── Realised gains ────────────────────────────────────────────────────────

    def _compute_entry_lt_tax(
        self, results: list[AssetTaxGainsResult]
    ) -> tuple[float, float]:
        """
        Compute (total_lt_tax, ltcg_exemption_used) for an asset_class entry.

        ₹1.25L Section-112A exemption is applied once against the combined
        exempt-eligible (STOCK_IN + equity MF) LTCG — not per-asset.
        All other LTCG at 12.5% flat; slab-rate LTCG at configured slab rate.
        """
        exempt_eligible_lt = sum(
            max(0.0, r.lt_gain) for r in results if r.ltcg_exempt_eligible
        )
        exemption_result = apply_ltcg_exemption(exempt_eligible_lt, "STOCK_IN")
        exemption_used = exemption_result["exemption_used"]
        taxable_exempt_lt = exemption_result["taxable_lt_gain"]

        lt_tax = taxable_exempt_lt * 12.5 / 100.0   # Indian equity after exemption

        for r in results:
            if r.ltcg_exempt_eligible:
                continue   # already handled above
            if r.ltcg_slab:
                lt_tax += max(0.0, r.lt_gain) * self._slab_rate_pct / 100.0
            else:
                lt_tax += max(0.0, r.lt_gain) * 12.5 / 100.0   # Gold, ForeignEquity, RealEstate

        return lt_tax, exemption_used

    def get_tax_summary(self, fy_label: str, member_id: int | None = None) -> dict:
        fy_start, fy_end = parse_fy(fy_label)
        all_results: list[AssetTaxGainsResult] = []
        member_ids = [member_id] if member_id else None

        with self._uow_factory() as uow:
            for asset in uow.assets.list(active=None, member_ids=member_ids):
                atype = asset.asset_type.value
                if atype in SKIPPED_ASSET_TYPES:
                    continue
                strategy = self._registry.get(atype, asset.asset_class.value)
                if strategy is None:
                    continue
                try:
                    result = strategy.compute(asset, uow, fy_label, fy_start, fy_end, self._slab_rate_pct)
                except Exception as e:
                    logger.warning("Tax gains error for asset %d: %s", asset.id, str(e))
                    continue
                all_results.append(result)

        # Separate FD/RD (interest income) from capital gains assets
        interest_results = [r for r in all_results if r.asset_type in {"FD", "RD"}]
        cg_results = [r for r in all_results if r.asset_type not in {"FD", "RD"}
                      and (r.st_gain != 0.0 or r.lt_gain != 0.0)]

        # STCG totals
        total_st_gain = sum(r.st_gain for r in cg_results)
        total_st_tax = sum(r.st_tax_estimate for r in cg_results)
        st_has_slab = any(r.has_slab and r.st_gain != 0 for r in cg_results)

        # LTCG totals with Section 112A exemption applied once across all eligible gains
        total_lt_gain = sum(r.lt_gain for r in cg_results)
        exempt_eligible_lt_gain = sum(max(0.0, r.lt_gain) for r in cg_results if r.ltcg_exempt_eligible)
        exemption_result = apply_ltcg_exemption(exempt_eligible_lt_gain, "STOCK_IN")
        exemption_used = exemption_result["exemption_used"]
        exemption_tax_saved = exemption_used * 12.5 / 100.0
        total_lt_tax_post_exemption = sum(r.lt_tax_estimate for r in cg_results) - exemption_tax_saved
        total_lt_tax_post_exemption = max(0.0, total_lt_tax_post_exemption)
        lt_has_slab = any(r.ltcg_slab for r in cg_results)

        # Interest totals
        total_interest = sum(r.st_gain for r in interest_results if r.st_gain != 0.0)
        interest_tax = sum(r.st_tax_estimate for r in interest_results)

        return {
            "fy": fy_label,
            "stcg": {
                "total_gain": total_st_gain,
                "total_tax": total_st_tax,
                "has_slab_items": st_has_slab,
                "assets": [
                    {
                        "asset_id": r.asset_id,
                        "asset_name": r.asset_name,
                        "asset_type": r.asset_type,
                        "gain": r.st_gain,
                        "tax_estimate": r.st_tax_estimate,
                        "is_slab": r.has_slab and r.st_gain != 0,
                        "tax_rate_pct": None if (r.has_slab and r.st_gain != 0) else (r.st_tax_estimate / r.st_gain * 100 if r.st_gain > 0 else None),
                    }
                    for r in cg_results if r.st_gain != 0
                ],
            },
            "ltcg": {
                "total_gain": total_lt_gain,
                "total_tax": total_lt_tax_post_exemption,
                "ltcg_exemption_used": exemption_used,
                "has_slab_items": lt_has_slab,
                "assets": [
                    {
                        "asset_id": r.asset_id,
                        "asset_name": r.asset_name,
                        "asset_type": r.asset_type,
                        "gain": r.lt_gain,
                        "tax_estimate": r.lt_tax_estimate,
                        "is_slab": r.ltcg_slab,
                        "tax_rate_pct": None if r.ltcg_slab else (r.lt_tax_estimate / r.lt_gain * 100 if r.lt_gain > 0 else None),
                        "ltcg_exempt_eligible": r.ltcg_exempt_eligible,
                    }
                    for r in cg_results if r.lt_gain != 0
                ],
            },
            "interest": {
                "total_interest": total_interest,
                "total_tax": interest_tax,
                "slab_rate_pct": self._slab_rate_pct,
                "assets": [
                    {
                        "asset_id": r.asset_id,
                        "asset_name": r.asset_name,
                        "asset_type": r.asset_type,
                        "interest": r.st_gain,
                        "tax_estimate": r.st_tax_estimate,
                    }
                    for r in interest_results if r.st_gain > 0
                ],
            },
        }

    # ── Unrealised gains ──────────────────────────────────────────────────────

    def _current_fy_label(self) -> str:
        today = date.today()
        start_yr = today.year if today.month >= 4 else today.year - 1
        return f"{start_yr}-{str(start_yr + 1)[-2:]}"

    def _build_lots_for_asset(self, asset, uow) -> tuple[list, list]:
        """Build open lots and matched sells for a single FIFO-tracked asset."""
        asset_id = asset.id
        asset_type = asset.asset_type.value
        transactions = uow.transactions.list_by_asset(asset_id)
        lots, sells = [], []
        for t in sorted(transactions, key=lambda x: x.date):
            ttype = t.type.value if hasattr(t.type, "value") else str(t.type)
            if ttype in LOT_TYPES and t.units:
                is_bonus = ttype == "BONUS"
                price = 0.0 if is_bonus else (abs(t.amount_inr / 100.0) / t.units if t.units else 0)
                lots.append(_Lot(
                    lot_id=t.lot_id or str(t.id),
                    buy_date=t.date,
                    units=t.units,
                    buy_price_per_unit=0.0 if is_bonus else (price or t.price_per_unit),
                    buy_amount_inr=0.0 if is_bonus else abs(t.amount_inr / 100.0),
                ))
            elif ttype in SELL_TYPES and t.units:
                sells.append(
                    _Sell(
                        date=t.date,
                        units=t.units,
                        amount_inr=abs(t.amount_inr / 100.0),
                        lot_id=t.lot_id or str(t.id),
                    )
                )

        if self._resolver is not None:
            fy_label = self._current_fy_label()
            rule = self._resolver.resolve(
                fy_label, asset_type,
                asset_class=asset.asset_class.value,
                isin=asset.identifier,
            )
            stcg_days = rule.stcg_days
        else:
            stcg_days = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
        matched = match_lots(lots, sells, stcg_days=stcg_days)

        sold_units: dict[str, float] = {}
        for m in matched:
            sold_units[m["lot_id"]] = sold_units.get(m["lot_id"], 0.0) + m["units_sold"]

        price_cache = uow.price_cache.get_by_asset_id(asset_id)
        current_price = (price_cache.price_inr / 100.0) if price_cache else None

        open_lots = []
        for lot in lots:
            units_remaining = lot.units - sold_units.get(lot.lot_id, 0.0)
            if units_remaining <= 0:
                continue
            entry = {
                "lot_id": lot.lot_id,
                "buy_date": lot.buy_date,
                "units": units_remaining,
                "buy_price_per_unit": lot.buy_price_per_unit,
                "buy_amount_inr": lot.buy_amount_inr,
            }
            if current_price is not None:
                unrealised = compute_lot_unrealised(lot, current_price, stcg_days=stcg_days)
                scale = units_remaining / lot.units if lot.units else 0
                entry.update({
                    "current_value": current_price * units_remaining,
                    "unrealised_gain": unrealised["unrealised_gain"] * scale,
                    "holding_days": unrealised["holding_days"],
                    "is_short_term": unrealised["is_short_term"],
                })
            else:
                holding_days = (date.today() - lot.buy_date).days
                entry.update({
                    "current_value": None,
                    "unrealised_gain": None,
                    "holding_days": holding_days,
                    "is_short_term": holding_days < stcg_days,
                })
            open_lots.append(entry)

        return open_lots, matched

    def get_unrealised_summary(self, member_id: int | None = None) -> dict:
        all_lots: list[dict] = []
        member_ids = [member_id] if member_id else None
        with self._uow_factory() as uow:
            for asset in uow.assets.list(active=True, member_ids=member_ids):
                atype = asset.asset_type.value
                if atype not in LOT_ASSET_TYPES:
                    continue
                try:
                    open_lots, _ = self._build_lots_for_asset(asset, uow)
                    for lot in open_lots:
                        all_lots.append({
                            **lot,
                            "asset_id": asset.id,
                            "asset_name": asset.name,
                            "asset_type": atype,
                            "asset_class": asset.asset_class.value,
                        })
                except Exception as e:
                    logger.warning("Error building lots for asset %d: %s", asset.id, str(e))

        total_st = 0.0
        total_lt = 0.0
        enriched = []
        for lot in all_lots:
            gain = lot.get("unrealised_gain") or 0.0
            is_st = lot.get("is_short_term", True)
            atype = lot["asset_type"]
            near_threshold = (
                not is_st and gain > 0
                and atype in {"STOCK_IN", "MF"}
                and (LTCG_NEAR_THRESHOLD - gain) <= LTCG_NEAR_THRESHOLD * LTCG_NEAR_PCT
            )
            if is_st:
                total_st += gain
            else:
                total_lt += gain
            entry = dict(lot)
            if not isinstance(entry.get("buy_date"), str):
                entry["buy_date"] = str(entry["buy_date"])
            entry["near_ltcg_threshold"] = near_threshold
            enriched.append(entry)

        return {
            "lots": enriched,
            "totals": {
                "total_st_unrealised": total_st,
                "total_lt_unrealised": total_lt,
                "total_unrealised": total_st + total_lt,
                "near_threshold_count": sum(1 for l in enriched if l["near_ltcg_threshold"]),
            },
        }

    # ── Available fiscal years ────────────────────────────────────────────────

    def get_available_fys(self) -> list[str]:
        """Return sorted list of fiscal year labels from config/tax_rates/*.yaml filenames."""
        config_dir = Path("app/config/tax_rates")
        fys = sorted(
            p.stem for p in config_dir.glob("*.yaml")
            if p.stem != "__init__"
        )
        return fys

    def get_harvest_opportunities(self, member_id: int | None = None) -> dict:
        summary = self.get_unrealised_summary(member_id=member_id)
        for lot in summary["lots"]:
            if not isinstance(lot.get("buy_date"), str):
                lot["buy_date"] = str(lot["buy_date"])
        opportunities = find_harvest_opportunities(summary["lots"])
        return {"opportunities": opportunities}
