import logging
from datetime import date
from pathlib import Path

import app.services.tax.strategies  # noqa: F401 — triggers @register_tax_strategy decorators
from app.engine.income_tax import (
    IncomeTaxConfig,
    TaxComputation,
    compute_capital_gains_tax,
    compute_income_tax,
)
from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS, match_lots_fifo
from app.engine.lot_engine import match_lots, compute_lot_unrealised
from app.engine.tax_engine import (
    TaxRuleResolver,
    parse_fy,
    apply_ltcg_exemption,
    find_harvest_opportunities,
)
from app.models.tax_loss_carryforward import LossType
from app.repositories.unit_of_work import IUnitOfWorkFactory
from app.services.returns.strategies.market_based import LOT_TYPES, SELL_TYPES, _Lot, _Sell
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxStrategyRegistry

logger = logging.getLogger(__name__)

SKIPPED_ASSET_TYPES = {"PPF"}
LOT_ASSET_TYPES = {"STOCK_IN", "STOCK_US", "MF", "GOLD", "SGB", "RSU", "NPS"}
ASSET_CLASS_ORDER = ["EQUITY", "DEBT", "GOLD", "REAL_ESTATE"]

LTCG_NEAR_THRESHOLD = 125_000.0
LTCG_NEAR_PCT = 0.10

# Default total income when no profile exists (conservative: top slab)
DEFAULT_TOTAL_INCOME_INR = 25_000_000.0


class TaxService:
    def __init__(
        self,
        uow_factory: IUnitOfWorkFactory,
        resolver: TaxRuleResolver | None = None,
    ):
        self._uow_factory = uow_factory
        self._registry = TaxStrategyRegistry()
        self._resolver = resolver

    # ── Member tax profile ──────────────────────────────────────────────────────

    def _get_member_total_income(self, uow, member_id: int | None, fy_label: str) -> float:
        """Get total income for slab/surcharge/rebate computation."""
        if member_id is not None:
            profile = uow.member_tax_profiles.get(member_id, fy_label)
            if profile is not None:
                return profile.total_income_inr
        # Default: assume top slab if no profile
        return DEFAULT_TOTAL_INCOME_INR

    def _get_income_tax_config(self, fy_label: str) -> IncomeTaxConfig:
        """Load income tax config for FY."""
        if self._resolver is not None:
            return self._resolver.get_income_tax_config(fy_label)
        # Fallback: no resolver — zero tax
        from app.engine.income_tax import IncomeTaxConfig
        return IncomeTaxConfig(
            slabs=[],
            surcharge_bands=[],
            cess_pct=0.0,
            rebate_87a=None,
        )

    # ── Carry-forward tracking ──────────────────────────────────────────────────

    def _get_carryforwards(self, uow, member_id: int | None) -> dict[LossType, list[dict]]:
        """Get carry-forward losses grouped by type."""
        if member_id is None:
            return {LossType.STCL: [], LossType.LTCL: []}
        records = uow.tax_loss_carryforwards.list_by_member(member_id)
        result = {LossType.STCL: [], LossType.LTCL: []}
        for r in records:
            result[r.loss_type].append({
                "fy_label": r.fy_label,
                "amount_inr": r.amount_inr,
                "remaining_inr": r.remaining_inr,
                "expires_fy_label": r.expires_fy_label,
            })
        # Sort by FY (oldest first — FIFO absorption)
        for lt in result:
            result[lt].sort(key=lambda x: x["fy_label"])
        return result

    def _record_carryforward(self, uow, member_id: int, fy_label: str,
                             loss_type: LossType, amount: float) -> None:
        """Record a new carry-forward loss."""
        if member_id is None or amount <= 0:
            return
        # 8-year carry-forward: expires 8 FYs after the loss FY
        fy_start_year = int(fy_label.split("-")[0])
        expires_fy = f"{fy_start_year + 8}-{str(fy_start_year + 9)[-2:]}"
        uow.tax_loss_carryforwards.upsert(
            member_id=member_id,
            fy_label=fy_label,
            loss_type=loss_type,
            amount_inr=amount,
            expires_fy_label=expires_fy,
        )

    def _absorb_carryforward(self, uow, member_id: int | None, fy_label: str,
                             carryforwards: dict, loss_type: LossType,
                             gains: float) -> tuple[float, float]:
        """
        Absorb carry-forward losses of given type against gains.
        Returns (absorbed_amount, remaining_gains).
        """
        if gains <= 0:
            return 0.0, gains
        absorbed = 0.0
        remaining = gains
        for cf in carryforwards.get(loss_type, []):
            if remaining <= 0:
                break
            take = min(cf["remaining_inr"], remaining)
            cf["remaining_inr"] -= take
            absorbed += take
            remaining -= take
        return absorbed, remaining

    # ── Realised gains ────────────────────────────────────────────────────────

    def get_tax_summary(self, fy_label: str, member_id: int | None = None) -> dict:
        fy_start, fy_end = parse_fy(fy_label)
        income_tax_config = self._get_income_tax_config(fy_label)

        all_results: list[AssetTaxGainsResult] = []
        member_ids = [member_id] if member_id else None

        with self._uow_factory() as uow:
            total_income = self._get_member_total_income(uow, member_id, fy_label)
            carryforwards = self._get_carryforwards(uow, member_id)

            for asset in uow.assets.list(active=None, member_ids=member_ids):
                atype = asset.asset_type.value
                if atype in SKIPPED_ASSET_TYPES:
                    continue
                strategy = self._registry.get(atype, asset.asset_class.value)
                if strategy is None:
                    continue
                try:
                    result = strategy.compute(asset, uow, fy_label, fy_start, fy_end)
                except Exception as e:
                    logger.warning("Tax gains error for asset %d: %s", asset.id, str(e))
                    continue
                all_results.append(result)

        # Separate FD/RD (interest income) from capital gains assets
        interest_results = [r for r in all_results if r.asset_type in {"FD", "RD"}]
        cg_results = [r for r in all_results if r.asset_type not in {"FD", "RD"}
                      and (r.st_gain != 0.0 or r.lt_gain != 0.0)]

        # ── Aggregate raw gains/losses ───────────────────────────────────────────
        total_st_gain = sum(r.st_gain for r in cg_results)
        total_lt_gain = sum(r.lt_gain for r in cg_results)
        total_interest = sum(r.st_gain for r in interest_results if r.st_gain != 0.0)

        # ── Loss set-off ────────────────────────────────────────────────────────
        # STCL offsets STCG first, then LTCG. LTCL offsets LTCG only.
        st_loss = -min(0.0, total_st_gain)  # positive number if net ST loss
        lt_loss = -min(0.0, total_lt_gain)  # positive number if net LT loss

        # Absorb carry-forward STCL against current STCG, then LTCG
        stcg_after_cf = max(0.0, total_st_gain)
        ltcg_after_cf = max(0.0, total_lt_gain)

        # Current-year STCL absorbs carry-forward STCL? No — current losses
        # absorb carry-forward first (current-year losses are used first).
        # Actually: current-year losses offset current-year gains first,
        # then absorb carry-forward. Unabsorbed current losses → new carry-forward.

        # Step 1: Current-year STCL offsets current STCG
        stcl_used_on_stcg = min(st_loss, stcg_after_cf)
        stcg_after_stcl = stcg_after_cf - stcl_used_on_stcg
        stcl_remaining = st_loss - stcl_used_on_stcg

        # Step 2: Remaining current-year STCL offsets current LTCG
        stcl_used_on_ltcg = min(stcl_remaining, ltcg_after_cf)
        ltcg_after_stcl = ltcg_after_cf - stcl_used_on_ltcg
        stcl_remaining -= stcl_used_on_ltcg

        # Step 3: Current-year LTCL offsets current LTCG
        ltcl_used_on_ltcg = min(lt_loss, ltcg_after_stcl)
        ltcg_after_ltcl = ltcg_after_stcl - ltcl_used_on_ltcg
        ltcl_remaining = lt_loss - ltcl_used_on_ltcg

        # Step 4: Absorb carry-forward STCL against remaining STCG, then LTCG
        cf_stcl_absorbed_stcg, stcg_final = self._absorb_carryforward_in_memory(
            carryforwards, LossType.STCL, stcg_after_stcl
        )
        cf_stcl_absorbed_ltcg, ltcg_final = self._absorb_carryforward_in_memory(
            carryforwards, LossType.STCL, stcg_final
        )

        # Step 5: Absorb carry-forward LTCL against remaining LTCG
        cf_ltgl_absorbed, ltcg_final = self._absorb_carryforward_in_memory(
            carryforwards, LossType.LTCL, ltcg_final
        )

        # Step 6: Record new carry-forwards for unabsorbed current losses
        if member_id is not None:
            with self._uow_factory() as uow:
                if stcl_remaining > 0:
                    self._record_carryforward(uow, member_id, fy_label, LossType.STCL, stcl_remaining)
                if ltcl_remaining > 0:
                    self._record_carryforward(uow, member_id, fy_label, LossType.LTCL, ltcl_remaining)

        # ── Compute tax on net gains ────────────────────────────────────────────

        # Interest income taxed at slab
        interest_tax = 0.0
        if total_interest > 0:
            interest_tax = self._compute_slab_tax_on_amount(
                total_interest, total_income, income_tax_config
            )

        # STCG: slab-rated items use slab, fixed-rate items use their rate
        stcg_tax = self._compute_cg_tax(cg_results, "st", stcg_final, total_income, income_tax_config)

        # LTCG: apply 112A exemption on exempt-eligible gains, then tax
        ltcg_tax, exemption_used = self._compute_ltcg_tax(
            cg_results, ltcg_final, total_income, income_tax_config
        )

        # ── Surcharge + cess on capital gains ───────────────────────────────────
        cg_tax = stcg_tax + ltcg_tax
        cg_surcharge, cg_cess, cg_tax_total = compute_capital_gains_tax(
            cg_tax, total_income, income_tax_config
        )

        # ── Surcharge + cess on interest/slab income ────────────────────────────
        slab_surcharge, slab_cess, slab_tax_total = self._compute_slab_tax_with_cess(
            interest_tax, total_income, income_tax_config
        )

        # ── 87A rebate (applies to total tax including capital gains) ──────────
        total_tax_before_rebate = cg_tax_total + slab_tax_total
        rebate = 0.0
        if income_tax_config.rebate_87a is not None:
            if total_income <= income_tax_config.rebate_87a.income_threshold_inr:
                rebate = min(total_tax_before_rebate, income_tax_config.rebate_87a.max_rebate_inr)

        total_tax = total_tax_before_rebate - rebate

        # ── Build per-asset breakdown ───────────────────────────────────────────
        stcg_assets = []
        for r in cg_results:
            if r.st_gain == 0:
                continue
            is_slab = r.has_slab and r.st_gain != 0
            if is_slab:
                rate = self._get_marginal_slab_rate(total_income, income_tax_config)
            else:
                rate = 20.0  # Equity STCG fixed rate
            tax = max(0.0, r.st_gain) * rate / 100.0
            stcg_assets.append({
                "asset_id": r.asset_id,
                "asset_name": r.asset_name,
                "asset_type": r.asset_type,
                "gain": r.st_gain,
                "tax_estimate": tax,
                "is_slab": is_slab,
                "tax_rate_pct": rate,
            })

        # LTCG per-asset: pro-rate exemption across exempt-eligible assets
        exempt_eligible_lt = sum(
            max(0.0, r.lt_gain) for r in cg_results if r.ltcg_exempt_eligible
        )
        ltcg_assets = []
        for r in cg_results:
            if r.lt_gain == 0:
                continue
            tax = 0.0
            if r.ltcg_exempt_eligible and exemption_used > 0 and exempt_eligible_lt > 0:
                share = exemption_used * (max(0.0, r.lt_gain) / exempt_eligible_lt)
                tax = max(0.0, r.lt_gain - share) * 12.5 / 100.0
            elif r.ltcg_slab:
                rate = self._get_marginal_slab_rate(total_income, income_tax_config)
                tax = max(0.0, r.lt_gain) * rate / 100.0
            else:
                tax = max(0.0, r.lt_gain) * 12.5 / 100.0
            ltcg_assets.append({
                "asset_id": r.asset_id,
                "asset_name": r.asset_name,
                "asset_type": r.asset_type,
                "gain": r.lt_gain,
                "tax_estimate": tax,
                "is_slab": r.ltcg_slab,
                "tax_rate_pct": None if r.ltcg_slab else (tax / r.lt_gain * 100 if r.lt_gain > 0 else None),
                "ltcg_exempt_eligible": r.ltcg_exempt_eligible,
            })

        interest_assets = [
            {
                "asset_id": r.asset_id,
                "asset_name": r.asset_name,
                "asset_type": r.asset_type,
                "interest": r.st_gain,
                "tax_estimate": interest_tax / len(interest_results) if interest_results else 0.0,
            }
            for r in interest_results if r.st_gain > 0
        ]

        # Carry-forward summary
        cf_summary = {
            "stcl": [
                {"fy_label": cf["fy_label"], "remaining_inr": cf["remaining_inr"],
                 "expires_fy_label": cf["expires_fy_label"]}
                for cf in carryforwards.get(LossType.STCL, []) if cf["remaining_inr"] > 0
            ],
            "ltcl": [
                {"fy_label": cf["fy_label"], "remaining_inr": cf["remaining_inr"],
                 "expires_fy_label": cf["expires_fy_label"]}
                for cf in carryforwards.get(LossType.LTCL, []) if cf["remaining_inr"] > 0
            ],
        }

        return {
            "fy": fy_label,
            "member_id": member_id,
            "total_income_inr": total_income,
            "stcg": {
                "total_gain": total_st_gain,
                "net_gain_after_setoff": stcg_final,
                "total_tax": stcg_tax,
                "assets": stcg_assets,
            },
            "ltcg": {
                "total_gain": total_lt_gain,
                "net_gain_after_setoff": ltcg_final,
                "total_tax": ltcg_tax,
                "ltcg_exemption_used": exemption_used,
                "assets": ltcg_assets,
            },
            "interest": {
                "total_interest": total_interest,
                "total_tax": interest_tax,
                "assets": interest_assets,
            },
            "capital_gains_tax": {
                "tax_before_surcharge_cess": cg_tax,
                "surcharge": cg_surcharge,
                "cess": cg_cess,
                "total": cg_tax_total,
            },
            "slab_income_tax": {
                "tax_before_surcharge_cess": interest_tax,
                "surcharge": slab_surcharge,
                "cess": slab_cess,
                "total": slab_tax_total,
            },
            "rebate_87a": rebate,
            "total_tax": total_tax,
            "setoff_summary": {
                "stcl_applied": stcl_used_on_stcg + stcl_used_on_ltcg,
                "ltcl_applied": ltcl_used_on_ltcg,
                "stcl_carryforward_remaining": stcl_remaining,
                "ltcl_carryforward_remaining": ltcl_remaining,
            },
            "carryforward_balances": cf_summary,
        }

    # ── Helper methods ───────────────────────────────────────────────────────────

    def _absorb_carryforward_in_memory(
        self, carryforwards: dict, loss_type: LossType, gains: float
    ) -> tuple[float, float]:
        """Absorb carry-forward losses in memory. Returns (absorbed, remaining_gains)."""
        if gains <= 0:
            return 0.0, gains
        absorbed = 0.0
        remaining = gains
        for cf in carryforwards.get(loss_type, []):
            if remaining <= 0:
                break
            take = min(cf["remaining_inr"], remaining)
            cf["remaining_inr"] -= take
            absorbed += take
            remaining -= take
        return absorbed, remaining

    def _compute_slab_tax_on_amount(
        self, amount: float, total_income: float, config: IncomeTaxConfig
    ) -> float:
        """Compute incremental slab tax on an additional amount of income."""
        from app.engine.income_tax import compute_slab_tax
        tax_before, _ = compute_slab_tax(total_income, config)
        tax_after, _ = compute_slab_tax(total_income + amount, config)
        return tax_after - tax_before

    def _get_marginal_slab_rate(self, total_income: float, config: IncomeTaxConfig) -> float:
        """Get the marginal slab rate for a given total income."""
        from app.engine.income_tax import compute_slab_tax
        _, rate = compute_slab_tax(total_income, config)
        return rate

    def _compute_slab_tax_with_cess(
        self, tax: float, total_income: float, config: IncomeTaxConfig
    ) -> tuple[float, float, float]:
        """Compute surcharge + cess on slab income tax. Returns (surcharge, cess, total)."""
        if tax <= 0:
            return 0.0, 0.0, 0.0
        surcharge = self._compute_surcharge(tax, total_income, config)
        cess = (tax + surcharge) * config.cess_pct / 100.0
        return surcharge, cess, tax + surcharge + cess

    def _compute_surcharge(
        self, tax: float, total_income: float, config: IncomeTaxConfig
    ) -> float:
        """Compute surcharge on tax (non-capital-gains)."""
        applicable_rate = 0.0
        for band in config.surcharge_bands:
            if total_income > band.income_above_inr:
                applicable_rate = band.rate_pct
            else:
                break
        return tax * applicable_rate / 100.0

    def _compute_cg_tax(
        self, results: list[AssetTaxGainsResult], gain_type: str,
        net_gain: float, total_income: float, config: IncomeTaxConfig
    ) -> float:
        """
        Compute tax on capital gains.
        gain_type: 'st' or 'lt'.
        Uses marginal slab rate for slab-rated items, fixed rate for others.
        """
        if net_gain <= 0:
            return 0.0

        tax = 0.0
        marginal_rate = self._get_marginal_slab_rate(total_income, config)

        for r in results:
            gain = r.st_gain if gain_type == "st" else r.lt_gain
            if gain <= 0:
                continue
            if gain_type == "st":
                if r.has_slab:
                    tax += gain * marginal_rate / 100.0
                else:
                    tax += gain * 20.0 / 100.0
            else:
                if r.ltcg_slab:
                    tax += gain * marginal_rate / 100.0
                else:
                    tax += gain * 12.5 / 100.0

        return tax

    def _compute_ltcg_tax(
        self, results: list[AssetTaxGainsResult], net_ltcg: float,
        total_income: float, config: IncomeTaxConfig
    ) -> tuple[float, float]:
        """
        Compute LTCG tax with 112A exemption.
        Returns (tax, exemption_used).
        """
        # Always compute exemption if there are exempt-eligible gains,
        # even if net_ltcg is zero or negative (e.g., after set-off).
        exempt_eligible = sum(
            max(0.0, r.lt_gain) for r in results if r.ltcg_exempt_eligible
        )
        exemption_result = apply_ltcg_exemption(exempt_eligible, "STOCK_IN")
        exemption_used = exemption_result["exemption_used"]
        taxable_exempt = exemption_result["taxable_lt_gain"]

        tax = taxable_exempt * 12.5 / 100.0
        marginal_rate = self._get_marginal_slab_rate(total_income, config)

        for r in results:
            if r.ltcg_exempt_eligible:
                continue
            if r.ltcg_slab:
                tax += max(0.0, r.lt_gain) * marginal_rate / 100.0
            else:
                tax += max(0.0, r.lt_gain) * 12.5 / 100.0

        return tax, exemption_used

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

        # Resolve per-lot: use buy_date to get correct stcg_days for each lot
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

            # Resolve per-lot rule using buy_date for correct stcg_days
            if self._resolver is not None:
                fy_label = self._current_fy_label()
                lot_rule = self._resolver.resolve(
                    fy_label, asset_type,
                    asset_class=asset.asset_class.value,
                    isin=asset.identifier,
                    buy_date=lot.buy_date,
                )
                lot_stcg_days = lot_rule.stcg_days
            else:
                lot_stcg_days = stcg_days

            entry = {
                "lot_id": lot.lot_id,
                "buy_date": lot.buy_date,
                "units": units_remaining,
                "buy_price_per_unit": lot.buy_price_per_unit,
                "buy_amount_inr": lot.buy_amount_inr,
            }
            if current_price is not None:
                unrealised = compute_lot_unrealised(lot, current_price, stcg_days=lot_stcg_days)
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
                    "is_short_term": holding_days < lot_stcg_days,
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
                not is_st
                and 0 < gain <= LTCG_NEAR_THRESHOLD
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

    # ── Harvest opportunities ─────────────────────────────────────────────────

    def get_harvest_opportunities(self, member_id: int | None = None) -> dict:
        summary = self.get_unrealised_summary(member_id=member_id)
        for lot in summary["lots"]:
            if not isinstance(lot.get("buy_date"), str):
                lot["buy_date"] = str(lot["buy_date"])

        opportunities = find_harvest_opportunities(summary["lots"])
        return {"opportunities": opportunities}
