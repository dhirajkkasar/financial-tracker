"""
Tax engine — pure functions, no DB access.

Tax rates are config-driven: see config/tax_rates/{FY}.yaml
Resolved via TaxRuleResolver with hierarchical override support.
"""
import yaml
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from app.engine.income_tax import IncomeTaxConfig, load_income_tax_config

# ₹1.25L LTCG exemption — Section 112A (equity and equity MF only)
LTCG_EXEMPTION_LIMIT = 125_000.0

# Asset types eligible for the ₹1.25L LTCG exemption
EXEMPTION_ELIGIBLE = {"STOCK_IN", "MF"}


# ── FY helpers ────────────────────────────────────────────────────────────────

def parse_fy(fy_label: str) -> tuple[date, date]:
    """
    Parse a fiscal year label into its start and end dates.

    '2024-25' → (date(2024, 4, 1), date(2025, 3, 31))
    """
    parts = fy_label.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(
            f"Invalid FY label {fy_label!r}. Expected format: '2024-25'"
        )
    start_yr = int(parts[0])
    suffix = int(parts[1])
    # Handle short suffix '25' or full '2025'
    end_yr = (start_yr // 100) * 100 + suffix if suffix < 100 else suffix
    if end_yr != start_yr + 1:
        raise ValueError(
            f"Invalid FY label {fy_label!r}. End year must be start year + 1"
        )
    return date(start_yr, 4, 1), date(end_yr, 3, 31)


# ── Holding period classification ─────────────────────────────────────────────

def classify_holding(
    buy_date: date,
    sell_date: date,
    stcg_days: int,
    asset_type: Optional[str] = None,  # kept for any legacy callers; ignored
) -> dict:
    """
    Return holding_days and is_short_term.

    Pass stcg_days explicitly (from strategy ClassVar).
    asset_type parameter is deprecated and ignored.
    """
    holding_days = (sell_date - buy_date).days
    return {
        "holding_days": holding_days,
        "is_short_term": holding_days < stcg_days,
    }


# ── LTCG exemption ────────────────────────────────────────────────────────────

def apply_ltcg_exemption(lt_gain: float, asset_type: str) -> dict:
    """
    Apply the ₹1.25L Section-112A LTCG exemption for STOCK_IN and equity MF.
    Only applies to positive gains.

    Returns {taxable_lt_gain, exemption_used}.
    """
    if asset_type not in EXEMPTION_ELIGIBLE or lt_gain <= 0:
        return {"taxable_lt_gain": lt_gain, "exemption_used": 0.0}

    exemption = min(lt_gain, LTCG_EXEMPTION_LIMIT)
    return {
        "taxable_lt_gain": lt_gain - exemption,
        "exemption_used": exemption,
    }


# ---------------------------------------------------------------------------
# ResolvedTaxRule + TaxRuleResolver — config-driven rate lookup
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedTaxRule:
    """Resolved tax rule for one asset type + class + ISIN + buy_date combination."""
    stcg_rate_pct: float | None      # None = slab rate
    ltcg_rate_pct: float | None
    stcg_days: int
    ltcg_exemption_inr: float
    ltcg_exempt_eligible: bool


# Keys that are rule fields (not asset_class sub-levels)
_RULE_KEYS = {
    "stcg_rate_pct", "ltcg_rate_pct", "stcg_days",
    "ltcg_exemption_inr", "ltcg_exempt_eligible",
}

_RULE_DEFAULTS: dict[str, object] = {
    "ltcg_exemption_inr": 0.0,
    "ltcg_exempt_eligible": False,
}


class TaxRuleResolver:
    """
    Loads per-FY YAML config and resolves tax rules via hierarchical override chain.

    Resolution order:
      1. asset_type default fields
      2. asset_type overrides (ordered merge)
      3. asset_class fields (if sub-level exists)
      4. asset_class overrides (ordered merge)

    Adding a new FY = drop a YYYY-YY.yaml file into config_dir.
    """

    def __init__(self, config_dir: Path):
        self._config_dir = config_dir
        self._cache: dict[str, dict] = {}
        self._income_tax_cache: dict[str, IncomeTaxConfig] = {}

    def resolve(
        self,
        fy: str,
        asset_type: str,
        asset_class: str | None = None,
        isin: str | None = None,
        buy_date: date | None = None,
    ) -> ResolvedTaxRule:
        raw = self._load(fy)
        type_block = raw[asset_type]

        # 1. Asset type defaults (scalar rule keys only)
        result = {k: v for k, v in type_block.items()
                  if k in _RULE_KEYS}

        # 2. Asset type overrides
        result = self._apply_overrides(
            result, type_block.get("overrides", []), isin, buy_date)

        # 3. Asset class fields (if sub-level exists)
        if asset_class and asset_class in type_block:
            class_block = type_block[asset_class]
            class_fields = {k: v for k, v in class_block.items()
                           if k in _RULE_KEYS}
            result = {**result, **class_fields}

            # 4. Asset class overrides
            result = self._apply_overrides(
                result, class_block.get("overrides", []), isin, buy_date)

        # Fill defaults for optional keys
        for k, default in _RULE_DEFAULTS.items():
            result.setdefault(k, default)

        # Strip 'overrides' if it leaked in
        result.pop("overrides", None)

        return ResolvedTaxRule(**result)

    def get_income_tax_config(self, fy: str) -> IncomeTaxConfig:
        """Load income tax config (slabs, surcharge, cess, 87A) for a FY."""
        if fy not in self._income_tax_cache:
            self._income_tax_cache[fy] = load_income_tax_config(fy, self._config_dir)
        return self._income_tax_cache[fy]

    def _load(self, fy: str) -> dict:
        if fy not in self._cache:
            path = self._config_dir / f"{fy}.yaml"
            if not path.exists():
                raise ValueError(
                    f"No tax rate config for FY {fy!r}. Expected file: {path}"
                )
            with open(path) as f:
                self._cache[fy] = yaml.safe_load(f)
        return self._cache[fy]

    def _apply_overrides(
        self,
        base: dict,
        overrides: list[dict],
        isin: str | None,
        buy_date: date | None,
    ) -> dict:
        result = dict(base)
        for override in overrides:
            match_conds = override["match"]
            if not self._matches(match_conds, isin, buy_date):
                continue
            for k, v in override.items():
                if k != "match" and k in _RULE_KEYS:
                    result[k] = v
        return result

    @staticmethod
    def _matches(
        match: dict,
        isin: str | None,
        buy_date: date | None,
    ) -> bool:
        """Return True if ALL conditions in the match block are satisfied."""
        if "isins" in match:
            if isin is None or isin not in match["isins"]:
                return False
        if "bought_before" in match:
            cutoff = date.fromisoformat(match["bought_before"])
            if buy_date is None or buy_date >= cutoff:
                return False
        if "bought_on_or_after" in match:
            cutoff = date.fromisoformat(match["bought_on_or_after"])
            if buy_date is None or buy_date < cutoff:
                return False
        return True


# ── Harvest opportunities ─────────────────────────────────────────────────────

LTCG_EXEMPTION_LIMIT = 125_000.0  # ₹1.25L Section 112A


def find_harvest_opportunities(
    open_lots: list[dict],
    total_income_inr: float = 25_000_000.0,
    income_tax_config=None,
) -> list[dict]:
    """
    Return lots with negative unrealised_gain (tax-loss harvesting candidates),
    sorted by tax benefit (highest first).

    Adds fields:
      - unrealised_loss: absolute value of loss
      - loss_type: 'STCL' or 'LTCL'
      - tax_benefit: estimated tax saved by realising this loss
      - priority: 'high' | 'medium' | 'low' based on tax benefit per rupee
      - guardrail: warning message if harvest may be suboptimal

    STCL can offset STCG (slab) and LTCG (12.5%/slab) — more flexible.
    LTCL can only offset LTCG — less flexible.
    """
    from app.engine.income_tax import compute_slab_tax

    opportunities = []
    for lot in open_lots:
        gain = lot.get("unrealised_gain")
        if gain is None or gain >= 0:
            continue

        loss = abs(gain)
        is_st = lot.get("is_short_term", True)
        loss_type = "STCL" if is_st else "LTCL"

        # Compute marginal tax rate for slab-rated gains
        if income_tax_config is not None:
            _, marginal_rate = compute_slab_tax(total_income_inr, income_tax_config)
        else:
            marginal_rate = 30.0

        # Tax benefit: STCL offsets STCG at slab rate (or LTCG at 12.5%)
        # LTCL only offsets LTCG at 12.5%
        if is_st:
            # STCL: can offset STCG (slab) or LTCG (12.5%)
            # Benefit = loss * max(slab_rate, 12.5%) — but capped by available gains
            tax_benefit = loss * max(marginal_rate, 12.5) / 100.0
        else:
            # LTCL: only offsets LTCG at 12.5%
            tax_benefit = loss * 12.5 / 100.0

        # Priority based on tax benefit per rupee of loss
        if is_st and marginal_rate > 20.0:
            priority = "high"  # STCL at high slab rate
        elif is_st:
            priority = "medium"  # STCL at lower slab rate
        else:
            priority = "low"  # LTCL only offsets 12.5% LTCG

        # Guardrails
        guardrail = None
        if not is_st and marginal_rate < 15.0:
            guardrail = (
                "LTCL only offsets LTCG at 12.5%. "
                "If your slab rate is low, consider holding for STCL conversion."
            )
        elif is_st and total_income_inr < 500_000:
            guardrail = (
                "Income below ₹5L: STCL may not provide immediate tax benefit "
                "if no STCG/LTCG to offset. Loss will carry forward."
            )

        opportunities.append({
            **lot,
            "unrealised_loss": loss,
            "loss_type": loss_type,
            "tax_benefit": tax_benefit,
            "priority": priority,
            "guardrail": guardrail,
        })

    # Sort by tax benefit (highest first)
    opportunities.sort(key=lambda o: o["tax_benefit"], reverse=True)
    return opportunities


def find_gain_harvesting_opportunities(
    open_lots: list[dict],
    ltcg_exemption_remaining: float = LTCG_EXEMPTION_LIMIT,
) -> list[dict]:
    """
    Return lots where realising LTCG up to the remaining ₹1.25L exemption is tax-free.

    These are lots with positive unrealised_gain that are long-term and
    exemption-eligible (STOCK_IN, equity MF).

    Adds fields:
      - potential_ltcg: gain that can be realised tax-free
      - exemption_remaining: remaining ₹1.25L exemption after this realisation
    """
    opportunities = []
    for lot in open_lots:
        gain = lot.get("unrealised_gain")
        if gain is None or gain <= 0:
            continue
        is_st = lot.get("is_short_term", True)
        if is_st:
            continue  # Only LTCG qualifies for 112A exemption

        atype = lot.get("asset_type", "")
        if atype not in {"STOCK_IN", "MF"}:
            continue  # Only equity + equity MF eligible

        potential_ltcg = min(gain, ltcg_exemption_remaining)
        if potential_ltcg <= 0:
            continue

        opportunities.append({
            **lot,
            "potential_ltcg": potential_ltcg,
            "exemption_remaining": ltcg_exemption_remaining - potential_ltcg,
        })

    # Sort by potential LTCG (highest first)
    opportunities.sort(key=lambda o: o["potential_ltcg"], reverse=True)
    return opportunities
