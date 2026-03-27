"""
Tax engine — pure functions, no DB access.

FY2024-25 rates:
  STOCK_IN / equity MF : STCG 20%, LTCG 12.5%, ₹1.25L Section-112A exemption
  STOCK_US / RSU       : STCG slab, LTCG 12.5%
  GOLD / SGB           : STCG slab, LTCG 12.5%
  REAL_ESTATE          : STCG slab, LTCG 12.5%
  FD / RD / EPF        : slab rate regardless of holding
  PPF                  : EEE — fully exempt
"""
import yaml
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

# ₹1.25L LTCG exemption — Section 112A (equity and equity MF only)
LTCG_EXEMPTION_LIMIT = 125_000.0

# Asset types eligible for the ₹1.25L LTCG exemption
EXEMPTION_ELIGIBLE = {"STOCK_IN", "MF"}

# Fully exempt (PPF = EEE)
FULLY_EXEMPT = {"PPF"}

# Always taxed at slab rate
SLAB_RATE_ALL = {"FD", "RD", "EPF"}

# STCG at slab, LTCG at 12.5% flat
LTCG_FLAT_ST_SLAB = {"STOCK_US", "RSU", "GOLD", "SGB", "REAL_ESTATE"}


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

def classify_holding(asset_type: str, buy_date: date, sell_date: date) -> dict:
    """
    Return holding_days and is_short_term based on asset-type thresholds.
    """
    from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS
    holding_days = (sell_date - buy_date).days
    threshold = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
    return {
        "holding_days": holding_days,
        "is_short_term": holding_days < threshold,
    }


# ── Tax rate lookup ───────────────────────────────────────────────────────────

def get_tax_rate(asset_type: str, is_short_term: bool) -> dict:
    """
    Return the applicable FY2024-25 tax rate descriptor.

    Keys: rate_pct (float|None), is_slab (bool), is_exempt (bool)
    """
    base: dict = {"rate_pct": None, "is_slab": False, "is_exempt": False}

    if asset_type in FULLY_EXEMPT:
        return {**base, "is_exempt": True}

    if asset_type in SLAB_RATE_ALL:
        return {**base, "is_slab": True}

    if asset_type in {"STOCK_IN", "MF"}:
        return {**base, "rate_pct": 20.0 if is_short_term else 12.5}

    if asset_type in LTCG_FLAT_ST_SLAB:
        if is_short_term:
            return {**base, "is_slab": True}
        return {**base, "rate_pct": 12.5}

    # Unknown asset type — treat conservatively as slab
    return {**base, "is_slab": True}


# ── Realised gains for a fiscal year ─────────────────────────────────────────

def compute_fy_realised_gains(
    matches: list[dict],
    asset_type: str,
    fy_start: date,
    fy_end: date,
) -> dict:
    """
    Filter FIFO matches whose sell_date falls within [fy_start, fy_end] and
    aggregate into short-term and long-term realised gains.
    """
    st_gain = 0.0
    lt_gain = 0.0
    matches_in_fy: list[dict] = []

    for m in matches:
        sell_date = m["sell_date"]
        buy_date = m["buy_date"]
        if isinstance(sell_date, str):
            sell_date = date.fromisoformat(sell_date)
        if isinstance(buy_date, str):
            buy_date = date.fromisoformat(buy_date)

        if not (fy_start <= sell_date <= fy_end):
            continue

        classification = classify_holding(asset_type, buy_date, sell_date)
        gain = m["realised_gain_inr"]
        if classification["is_short_term"]:
            st_gain += gain
        else:
            lt_gain += gain

        matches_in_fy.append({**m, **classification})

    return {
        "st_gain": st_gain,
        "lt_gain": lt_gain,
        "total_gain": st_gain + lt_gain,
        "matches_in_fy": matches_in_fy,
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


# ── Tax estimation ────────────────────────────────────────────────────────────

def estimate_tax(st_gain: float, lt_gain: float, asset_type: str) -> dict:
    """
    Estimate FY2024-25 tax on realised gains.

    st_tax / lt_tax are None when slab rate applies (tax bracket unknown).
    Losses (negative gains) produce zero tax, not negative tax.
    """
    if asset_type in FULLY_EXEMPT:
        return {
            "st_tax": None, "lt_tax": None, "total_tax": None,
            "is_st_slab": False, "is_lt_slab": False, "is_lt_exempt": True,
            "ltcg_exemption_used": 0.0,
        }

    if asset_type in SLAB_RATE_ALL:
        return {
            "st_tax": None, "lt_tax": None, "total_tax": None,
            "is_st_slab": True, "is_lt_slab": True, "is_lt_exempt": False,
            "ltcg_exemption_used": 0.0,
        }

    st_rate = get_tax_rate(asset_type, is_short_term=True)
    lt_rate = get_tax_rate(asset_type, is_short_term=False)

    # Short-term tax
    if st_rate["is_slab"] or st_rate["is_exempt"]:
        st_tax: Optional[float] = None
        is_st_slab = st_rate["is_slab"]
    else:
        st_tax = max(0.0, st_gain) * (st_rate["rate_pct"] / 100.0)
        is_st_slab = False

    # Long-term tax — apply exemption first
    exemption_result = apply_ltcg_exemption(lt_gain, asset_type)
    taxable_lt = exemption_result["taxable_lt_gain"]
    exemption_used = exemption_result["exemption_used"]

    if lt_rate["is_slab"] or lt_rate["is_exempt"]:
        lt_tax: Optional[float] = None
        is_lt_slab = lt_rate["is_slab"]
    else:
        lt_tax = max(0.0, taxable_lt) * (lt_rate["rate_pct"] / 100.0)
        is_lt_slab = False

    total_tax: Optional[float] = None
    if st_tax is not None and lt_tax is not None:
        total_tax = st_tax + lt_tax

    return {
        "st_tax": st_tax,
        "lt_tax": lt_tax,
        "total_tax": total_tax,
        "is_st_slab": is_st_slab,
        "is_lt_slab": is_lt_slab,
        "is_lt_exempt": lt_rate.get("is_exempt", False),
        "ltcg_exemption_used": exemption_used,
    }


# ── Harvest opportunities ─────────────────────────────────────────────────────

# ---------------------------------------------------------------------------
# TaxRate dataclass + TaxRatePolicy — config-driven rate lookup
# ---------------------------------------------------------------------------

@dataclass
class TaxRate:
    """Tax rate descriptor for one asset type in one FY."""
    stcg_rate_pct: float | None      # None = slab rate
    stcg_is_slab: bool
    ltcg_rate_pct: float | None
    ltcg_is_slab: bool
    ltcg_threshold_days: int | None  # None = no LT distinction
    ltcg_exemption_inr: float
    is_exempt: bool                  # EEE (PPF)
    maturity_exempt: bool = False    # SGB held to maturity


class TaxRatePolicy:
    """
    Loads per-FY YAML config files from a directory and returns TaxRate objects.

    Adding a new FY = drop a YYYY-YY.yaml file into config_dir. Zero code changes.

    Usage:
        policy = TaxRatePolicy(Path("app/config/tax_rates"))
        rate = policy.get_rate("2024-25", "STOCK_IN")
    """

    def __init__(self, config_dir: Path):
        self._config_dir = config_dir
        self._cache: dict[str, dict[str, TaxRate]] = {}

    def get_rate(self, fy: str, asset_type: str) -> TaxRate:
        if fy not in self._cache:
            path = self._config_dir / f"{fy}.yaml"
            if not path.exists():
                raise ValueError(
                    f"No tax rate config for FY {fy!r}. "
                    f"Expected file: {path}"
                )
            with open(path) as f:
                raw_data: dict = yaml.safe_load(f)
            self._cache[fy] = {
                at: TaxRate(**fields) for at, fields in raw_data.items()
            }
        rates = self._cache[fy]
        if asset_type not in rates:
            raise ValueError(
                f"No tax rate for asset_type={asset_type!r} in FY {fy!r}. "
                f"Available: {sorted(rates.keys())}"
            )
        return rates[asset_type]


# ── Harvest opportunities ─────────────────────────────────────────────────────

def find_harvest_opportunities(open_lots: list[dict]) -> list[dict]:
    """
    Return lots with negative unrealised_gain (tax-loss harvesting candidates),
    sorted by largest unrealised loss first.

    Adds 'unrealised_loss' field (absolute value) for convenience.
    """
    opportunities = []
    for lot in open_lots:
        gain = lot.get("unrealised_gain")
        if gain is None or gain >= 0:
            continue
        opportunities.append({**lot, "unrealised_loss": abs(gain)})

    opportunities.sort(key=lambda o: o["unrealised_loss"], reverse=True)
    return opportunities
