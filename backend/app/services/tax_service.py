import logging
from datetime import date

from sqlalchemy.orm import Session

from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.price_cache_repo import PriceCacheRepository
from app.engine.tax_engine import (
    parse_fy,
    compute_fy_realised_gains,
    apply_ltcg_exemption,
    estimate_tax,
    find_harvest_opportunities,
    get_tax_rate,
)
from app.engine.returns import EXCLUDED_TYPES

logger = logging.getLogger(__name__)

# Asset types that use FIFO lot matching (exclude SGB — tax-exempt at maturity)
LOT_ASSET_TYPES = {"STOCK_IN", "STOCK_US", "MF", "GOLD", "RSU", "REAL_ESTATE"}

# How close to ₹1.25L before we flag "near threshold" (within 10%)
LTCG_NEAR_THRESHOLD = 125_000.0
LTCG_NEAR_PCT = 0.10


class TaxService:
    def __init__(self, db: Session):
        self.db = db
        self.asset_repo = AssetRepository(db)
        self.txn_repo = TransactionRepository(db)
        self.price_repo = PriceCacheRepository(db)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_lots_for_asset(self, asset_id: int, asset_type: str):
        """Delegate lot building to ReturnsService to avoid duplication."""
        from app.services.returns_service import ReturnsService
        svc = ReturnsService(self.db)
        transactions = self.txn_repo.list_by_asset(asset_id)
        return svc._build_lots_and_sells(asset_id, asset_type, transactions)

    def _get_all_open_lots(self) -> list[dict]:
        """Return enriched open lots for all active lot-based assets."""
        all_lots: list[dict] = []
        for asset in self.asset_repo.list(active=True):
            atype = asset.asset_type.value
            if atype not in LOT_ASSET_TYPES:
                continue
            try:
                open_lots, _ = self._build_lots_for_asset(asset.id, atype)
                for lot in open_lots:
                    all_lots.append({
                        **lot,
                        "asset_id": asset.id,
                        "asset_name": asset.name,
                        "asset_type": atype,
                    })
            except Exception as e:
                logger.warning("Error building lots for asset %d: %s", asset.id, str(e))
        return all_lots

    def _get_matched_sells_by_type(self) -> dict[str, list[dict]]:
        """Return all FIFO-matched sells grouped by asset type (active + inactive)."""
        by_type: dict[str, list[dict]] = {}
        for asset in self.asset_repo.list(active=None):
            atype = asset.asset_type.value
            if atype not in LOT_ASSET_TYPES:
                continue
            try:
                _, matched_sells = self._build_lots_for_asset(asset.id, atype)
                by_type.setdefault(atype, []).extend(matched_sells)
            except Exception as e:
                logger.warning("Error building sells for asset %d: %s", asset.id, str(e))
        return by_type

    # ── Public API ────────────────────────────────────────────────────────────

    def get_tax_summary(self, fy_label: str) -> dict:
        """Return realised gains, tax estimates, and exemptions per asset type."""
        fy_start, fy_end = parse_fy(fy_label)
        matched_by_type = self._get_matched_sells_by_type()

        entries: list[dict] = []
        total_st_gain = 0.0
        total_lt_gain = 0.0
        total_st_tax = 0.0
        total_lt_tax = 0.0
        has_slab = False

        for asset_type, matches in matched_by_type.items():
            gains = compute_fy_realised_gains(matches, asset_type, fy_start, fy_end)
            if gains["st_gain"] == 0.0 and gains["lt_gain"] == 0.0:
                continue

            tax = estimate_tax(gains["st_gain"], gains["lt_gain"], asset_type)
            exemption = apply_ltcg_exemption(gains["lt_gain"], asset_type)
            st_rate = get_tax_rate(asset_type, is_short_term=True)
            lt_rate = get_tax_rate(asset_type, is_short_term=False)

            entries.append({
                "asset_type": asset_type,
                "st_gain": gains["st_gain"],
                "lt_gain": gains["lt_gain"],
                "total_gain": gains["total_gain"],
                "st_tax_rate_pct": st_rate.get("rate_pct"),
                "lt_tax_rate_pct": lt_rate.get("rate_pct"),
                "is_st_slab": st_rate["is_slab"],
                "is_lt_slab": lt_rate["is_slab"],
                "is_lt_exempt": lt_rate["is_exempt"],
                "ltcg_exemption_used": exemption["exemption_used"],
                "taxable_lt_gain": exemption["taxable_lt_gain"],
                "st_tax_estimate": tax["st_tax"],
                "lt_tax_estimate": tax["lt_tax"],
                "total_tax_estimate": tax["total_tax"],
            })

            total_st_gain += gains["st_gain"]
            total_lt_gain += gains["lt_gain"]
            if tax["st_tax"] is not None:
                total_st_tax += tax["st_tax"]
            if tax["is_st_slab"]:
                has_slab = True
            if tax["lt_tax"] is not None:
                total_lt_tax += tax["lt_tax"]
            if tax.get("is_lt_slab"):
                has_slab = True

        entries.sort(key=lambda e: abs(e["total_gain"]), reverse=True)

        return {
            "fy": fy_label,
            "entries": entries,
            "totals": {
                "total_st_gain": total_st_gain,
                "total_lt_gain": total_lt_gain,
                "total_gain": total_st_gain + total_lt_gain,
                "total_st_tax": total_st_tax,
                "total_lt_tax": total_lt_tax,
                "total_tax": total_st_tax + total_lt_tax,
                "has_slab_rate_items": has_slab,
            },
        }

    def get_unrealised_summary(self) -> dict:
        """Return all open lots with ST/LT classification and near-threshold flags."""
        open_lots = self._get_all_open_lots()
        total_st = 0.0
        total_lt = 0.0
        enriched: list[dict] = []

        for lot in open_lots:
            gain = lot.get("unrealised_gain") or 0.0
            is_st = lot.get("is_short_term", True)
            atype = lot["asset_type"]

            # Flag LT equity/MF lots approaching ₹1.25L threshold
            near_threshold = (
                not is_st
                and gain > 0
                and atype in {"STOCK_IN", "MF"}
                and (LTCG_NEAR_THRESHOLD - gain) <= LTCG_NEAR_THRESHOLD * LTCG_NEAR_PCT
            )

            if is_st:
                total_st += gain
            else:
                total_lt += gain

            # Ensure buy_date is a string for JSON serialisation
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

    def get_harvest_opportunities(self) -> dict:
        """Return open lots with unrealised losses, sorted by largest loss first."""
        open_lots = self._get_all_open_lots()
        # Ensure buy_date is serialisable
        for lot in open_lots:
            if not isinstance(lot.get("buy_date"), str):
                lot["buy_date"] = str(lot["buy_date"])
        opportunities = find_harvest_opportunities(open_lots)
        return {"opportunities": opportunities}
