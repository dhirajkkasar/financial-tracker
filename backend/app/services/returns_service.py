from datetime import date
import logging
from sqlalchemy.orm import Session

from app.repositories.asset_repo import AssetRepository
from app.repositories.cas_snapshot_repo import CasSnapshotRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.valuation_repo import ValuationRepository
from app.repositories.fd_repo import FDRepository
from app.repositories.price_cache_repo import PriceCacheRepository
from app.engine.returns import (
    compute_xirr, compute_cagr, compute_absolute_return,
    OUTFLOW_TYPES, INFLOW_TYPES, EXCLUDED_TYPES, UNIT_ADD_TYPES, UNIT_SUB_TYPES,
)
from app.services.price_feed import STALE_MINUTES
from app.engine.fd_engine import compute_fd_maturity, compute_fd_current_value, compute_rd_maturity
from app.engine.ppf_epf_engine import get_latest_valuation
from app.engine.lot_engine import match_lots_fifo, compute_lot_unrealised, compute_gains_summary
from app.engine.allocation import compute_allocation, find_top_gainers

logger = logging.getLogger(__name__)

# Asset types that use market price / transaction-based returns
MARKET_BASED_TYPES = {"STOCK_IN", "STOCK_US", "MF", "RSU", "GOLD", "SGB", "NPS"}
# Asset types that use FD/RD formula
FD_BASED_TYPES = {"FD", "RD"}
# Asset types that use valuation entries (manual passbook / property estimate)
VALUATION_BASED_TYPES = {"PPF", "REAL_ESTATE"}


class ReturnsService:
    def __init__(self, db: Session):
        self.db = db
        self.asset_repo = AssetRepository(db)
        self.txn_repo = TransactionRepository(db)
        self.val_repo = ValuationRepository(db)
        self.fd_repo = FDRepository(db)
        self.price_repo = PriceCacheRepository(db)
        self.cas_snap_repo = CasSnapshotRepository(db)

    def get_asset_returns(self, asset_id: int) -> dict:
        from app.middleware.error_handler import NotFoundError
        asset = self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise NotFoundError(f"Asset {asset_id} not found")

        asset_type = asset.asset_type.value

        if asset_type == "MF":
            return self._compute_mf_returns(asset)
        elif asset_type in MARKET_BASED_TYPES:
            return self._compute_market_based_returns(asset)
        elif asset_type in FD_BASED_TYPES:
            return self._compute_fd_returns(asset)
        elif asset_type == "EPF":
            return self._compute_epf_returns(asset)
        elif asset_type in VALUATION_BASED_TYPES:
            return self._compute_valuation_based_returns(asset)
        else:
            # Fallback: try market-based
            return self._compute_market_based_returns(asset)

    def _compute_mf_returns(self, asset) -> dict:
        """
        Compute returns for MF assets using CAS snapshot as authoritative source.

        Current value:
          - snapshot < 30 days old  → use snapshot.market_value directly
          - snapshot ≥ 30 days old  → snapshot.closing_units × latest price_cache NAV
        Current P&L  = current_value − snapshot.total_cost  (from CAS)
        All-time P&L = current_p_l + realised gains (FIFO lot engine)
        """
        from app.middleware.error_handler import ValidationError

        asset_id = asset.id
        asset_type = asset.asset_type.value

        snapshot = self.cas_snap_repo.get_latest_by_asset_id(asset_id)
        if snapshot is None:
            raise ValidationError(
                f"No CAS snapshot found for '{asset.name}'. "
                "Please import your CAS PDF statement first."
            )

        transactions = self.txn_repo.list_by_asset(asset_id)
        filtered_txns = [t for t in transactions if t.type.value not in EXCLUDED_TYPES]

        # Build XIRR cashflows from full transaction history
        cashflows = []
        total_invested_txn = 0.0
        for txn in filtered_txns:
            amount_inr = txn.amount_inr / 100.0
            if txn.type.value in OUTFLOW_TYPES:
                cashflows.append((txn.date, amount_inr))
                total_invested_txn += abs(amount_inr)
            elif txn.type.value in INFLOW_TYPES:
                cashflows.append((txn.date, amount_inr))

        # --- Fully redeemed fund ---
        if snapshot.closing_units == 0:
            gains_summary = self._mf_gains_summary(asset_id, asset_type, transactions)
            realised = self._sum_realised(gains_summary)
            # cashflows already has outflows + inflows; no terminal value since fully redeemed
            xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
            return {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "total_invested": total_invested_txn,
                "current_value": 0,
                "current_p_l": None,
                "all_time_p_l": realised if realised is not None else None,
                "xirr": xirr,
                "cagr": None,
                "absolute_return": None,
                "message": "Fully redeemed",
                "price_is_stale": None,
                "price_fetched_at": None,
                "st_unrealised_gain": None,
                "lt_unrealised_gain": None,
                "st_realised_gain": gains_summary.get("st_realised_gain"),
                "lt_realised_gain": gains_summary.get("lt_realised_gain"),
            }

        # --- Active fund: determine current value ---
        snapshot_age_days = (date.today() - snapshot.date).days

        if snapshot_age_days < 30:
            current_value = snapshot.market_value_inr / 100.0
            price_is_stale = False
            price_fetched_at = snapshot.date.isoformat()
        else:
            price_cache = self.price_repo.get_by_asset_id(asset_id)
            if price_cache:
                current_value = snapshot.closing_units * (price_cache.price_inr / 100.0)
                price_is_stale = (date.today() - snapshot.date).days > 30
                price_fetched_at = price_cache.fetched_at.isoformat()
            else:
                # Best available: stale snapshot market value
                current_value = snapshot.market_value_inr / 100.0
                price_is_stale = True
                price_fetched_at = snapshot.date.isoformat()

        total_cost = snapshot.total_cost_inr / 100.0
        current_p_l = current_value - total_cost

        # Validate against lot engine (log warning only; use CAS value)
        gains_summary = self._mf_gains_summary(asset_id, asset_type, transactions)
        lot_unrealised = self._sum_unrealised(gains_summary)
        if lot_unrealised is not None and abs(total_cost) > 0:
            divergence = abs(current_p_l - lot_unrealised) / max(abs(total_cost), 1)
            if divergence > 0.05:
                logger.warning(
                    "MF asset %d '%s': CAS current P&L %.2f differs %.1f%% from lot engine %.2f",
                    asset_id, asset.name, current_p_l, divergence * 100, lot_unrealised,
                )

        realised = self._sum_realised(gains_summary)
        all_time_p_l = current_p_l + (realised or 0.0)

        # XIRR: add current value as final inflow
        if current_value > 0:
            cashflows.append((date.today(), current_value))
        xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None

        # CAGR
        cagr = None
        if filtered_txns and total_invested_txn > 0 and current_value > 0:
            oldest = min(filtered_txns, key=lambda t: t.date)
            years = (date.today() - oldest.date).days / 365.0
            ratio = current_value / total_invested_txn
            if years > 0 and ratio > 0:
                cagr = round(ratio ** (1 / years) - 1, 6)

        abs_return = compute_absolute_return(total_invested_txn, current_value) if total_invested_txn > 0 else None

        return {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "total_invested": total_cost,   # CAS cost basis, not raw txn sum
            "current_value": current_value,
            "current_p_l": current_p_l,
            "all_time_p_l": all_time_p_l,
            "xirr": xirr,
            "cagr": cagr,
            "absolute_return": abs_return,
            "message": None,
            "price_is_stale": price_is_stale,
            "price_fetched_at": price_fetched_at,
            # Unrealised gains intentionally null — CAS cost basis used for current P&L
            # (lot-engine unrealised uses different cost basis and would disagree)
            "st_unrealised_gain": None,
            "lt_unrealised_gain": None,
            # Realised gains from lot engine are still valid for all-time P&L
            "st_realised_gain": gains_summary.get("st_realised_gain"),
            "lt_realised_gain": gains_summary.get("lt_realised_gain"),
        }

    def _mf_gains_summary(self, asset_id: int, asset_type: str, transactions: list) -> dict:
        """Run lot engine for MF, return gains dict (silently returns nulls on error)."""
        try:
            open_lots, matched_sells = self._build_lots_and_sells(asset_id, asset_type, transactions)
            return compute_gains_summary(open_lots, matched_sells, asset_type)
        except Exception as e:
            logger.warning("Error computing gain summary for MF asset %d: %s", asset_id, str(e))
            return {
                "st_unrealised_gain": None,
                "lt_unrealised_gain": None,
                "st_realised_gain": None,
                "lt_realised_gain": None,
            }

    @staticmethod
    def _sum_unrealised(gains: dict) -> float | None:
        st = gains.get("st_unrealised_gain")
        lt = gains.get("lt_unrealised_gain")
        if st is None and lt is None:
            return None
        return (st or 0.0) + (lt or 0.0)

    @staticmethod
    def _sum_realised(gains: dict) -> float | None:
        st = gains.get("st_realised_gain")
        lt = gains.get("lt_realised_gain")
        if st is None and lt is None:
            return None
        return (st or 0.0) + (lt or 0.0)

    def _build_lots_and_sells(self, asset_id: int, asset_type: str, transactions: list):
        """
        Build open_lots and matched_sells lists for lot-based assets.
        Returns (open_lots: list[dict], matched_sells: list[dict]).
        """
        from dataclasses import dataclass
        from typing import Optional as Opt

        LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST", "BONUS"}
        SELL_TYPES = {"SELL", "REDEMPTION"}

        @dataclass
        class _Lot:
            lot_id: str
            buy_date: object
            units: float
            buy_price_per_unit: float
            buy_amount_inr: float
            jan31_2018_price: Opt[float] = None

        @dataclass
        class _Sell:
            date: object
            units: float
            amount_inr: float

        lots = []
        sells = []
        for txn in sorted(transactions, key=lambda t: t.date):
            txn_type = txn.type.value
            if txn_type in LOT_TYPES and txn.units:
                # BONUS shares have 0 cost basis (amount_inr=0 in DB)
                is_bonus = txn_type == "BONUS"
                price = 0.0 if is_bonus else (abs(txn.amount_inr / 100.0) / txn.units if txn.units else 0)
                lots.append(_Lot(
                    lot_id=txn.lot_id or str(txn.id),
                    buy_date=txn.date,
                    units=txn.units,
                    buy_price_per_unit=0.0 if is_bonus else (txn.price_per_unit or price),
                    buy_amount_inr=0.0 if is_bonus else abs(txn.amount_inr / 100.0),
                ))
            elif txn_type in SELL_TYPES and txn.units:
                sells.append(_Sell(
                    date=txn.date,
                    units=txn.units,
                    amount_inr=abs(txn.amount_inr / 100.0),
                ))

        matched = match_lots_fifo(lots, sells)

        sold_units: dict[str, float] = {}
        for m in matched:
            sold_units[m["lot_id"]] = sold_units.get(m["lot_id"], 0.0) + m["units_sold"]

        price_cache = self.price_repo.get_by_asset_id(asset_id)
        current_price = (price_cache.price_inr / 100.0) if price_cache else None

        open_lots = []
        for lot in lots:
            units_remaining = lot.units - sold_units.get(lot.lot_id, 0.0)
            if units_remaining <= 0:
                continue
            entry = {
                "lot_id": lot.lot_id,
                "buy_date": lot.buy_date,
                "units_remaining": units_remaining,
                "buy_price_per_unit": lot.buy_price_per_unit,
                "buy_amount_inr": lot.buy_price_per_unit * units_remaining,
            }
            if current_price is not None:
                unrealised = compute_lot_unrealised(lot, current_price, asset_type)
                scale = units_remaining / lot.units if lot.units else 0
                entry.update({
                    "current_value": current_price * units_remaining,
                    "unrealised_gain": unrealised["unrealised_gain"] * scale,
                    "holding_days": unrealised["holding_days"],
                    "is_short_term": unrealised["is_short_term"],
                })
            else:
                from datetime import date as _date
                from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS
                holding_days = (_date.today() - lot.buy_date).days
                threshold = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
                entry.update({
                    "current_value": None,
                    "unrealised_gain": None,
                    "holding_days": holding_days,
                    "is_short_term": holding_days < threshold,
                })
            open_lots.append(entry)

        return open_lots, matched

    def _compute_market_based_returns(self, asset) -> dict:
        asset_id = asset.id
        asset_type = asset.asset_type.value
        transactions = self.txn_repo.list_by_asset(asset_id)

        # Filter excluded types
        filtered_txns = [t for t in transactions if t.type.value not in EXCLUDED_TYPES]

        # Build cashflows (convert paise to INR)
        cashflows = []

        for txn in filtered_txns:
            amount_inr = txn.amount_inr / 100.0  # paise to INR
            txn_type = txn.type.value

            if txn_type in OUTFLOW_TYPES:
                # DB stores as negative paise for outflows
                # For XIRR, outflow = negative
                cashflows.append((txn.date, amount_inr))  # already negative in DB
            elif txn_type in INFLOW_TYPES:
                # DB stores as positive paise for inflows
                cashflows.append((txn.date, amount_inr))  # already positive in DB

        # Compute lot gain summary (skip for SGB — tax-exempt on maturity)
        # Must run BEFORE total_invested so open_lots is available.
        gains_summary = {
            "st_unrealised_gain": None,
            "lt_unrealised_gain": None,
            "st_realised_gain": None,
            "lt_realised_gain": None,
        }
        open_lots = []
        if asset_type != "SGB":
            try:
                open_lots, matched_sells = self._build_lots_and_sells(asset_id, asset_type, transactions)
                gains_summary = compute_gains_summary(open_lots, matched_sells, asset_type)
            except Exception as e:
                logger.warning("Error computing gain summary for asset %d: %s", asset_id, str(e))

        # total_invested = cost basis of CURRENTLY HELD shares (open lots only).
        # SGB exception: FIFO lot engine is intentionally not run for SGB (government bonds held to
        # maturity are tax-exempt; granular lot tracking does not apply). Fall back to summing all
        # outflow transactions so the "Invested" column shows the actual purchase cost.
        if asset_type == "SGB":
            total_invested = sum(
                abs(txn.amount_inr / 100.0)
                for txn in filtered_txns
                if txn.type.value in OUTFLOW_TYPES
            )
        else:
            total_invested = sum(lot["buy_amount_inr"] for lot in open_lots)

        # Get current price from cache
        price_cache = self.price_repo.get_by_asset_id(asset_id)
        current_value = None

        total_units = sum(
            t.units or 0 for t in filtered_txns if t.type.value in UNIT_ADD_TYPES
        ) - sum(
            t.units or 0 for t in filtered_txns if t.type.value in UNIT_SUB_TYPES
        )
        avg_price = total_invested / total_units if total_units > 0 else None

        if price_cache:
            current_price_inr = price_cache.price_inr / 100.0
            current_value = total_units * current_price_inr

            if current_value > 0:
                cashflows.append((date.today(), current_value))

        xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None

        # Compute total inflows (SELL, DIVIDEND, etc.) from transactions
        total_inflows = sum(
            txn.amount_inr / 100.0
            for txn in filtered_txns
            if txn.type.value in INFLOW_TYPES
        )

        # Effective current value: price cache if available, else use transaction inflows
        effective_current = current_value if current_value is not None else (total_inflows if total_inflows > 0 else None)

        # CAGR: only if we have a current value and a start date
        cagr = None
        abs_return = None
        if total_invested > 0 and effective_current is not None:
            abs_return = compute_absolute_return(total_invested, effective_current)

            if filtered_txns:
                oldest = min(filtered_txns, key=lambda t: t.date)
                years = (date.today() - oldest.date).days / 365.0
                cagr = compute_cagr(total_invested, effective_current, years)

        # Price staleness metadata
        price_is_stale = None
        price_fetched_at = None
        if price_cache:
            from datetime import datetime, timedelta
            threshold = STALE_MINUTES.get(asset.asset_type)
            if threshold is not None:
                price_is_stale = datetime.utcnow() - price_cache.fetched_at > timedelta(minutes=threshold)
            price_fetched_at = price_cache.fetched_at.isoformat()

        result = {
            "asset_id": asset.id,
            "asset_type": asset_type,
            "xirr": xirr,
            "cagr": cagr,
            "absolute_return": abs_return,
            "total_invested": total_invested,
            "current_value": effective_current,
            "total_units": total_units if total_units > 0 else None,
            "avg_price": avg_price,
            "message": None,
            "price_is_stale": price_is_stale,
            "price_fetched_at": price_fetched_at,
        }
        result.update(gains_summary)
        return result

    def _compute_fd_returns(self, asset) -> dict:
        asset_id = asset.id
        asset_type = asset.asset_type.value

        fd = self.fd_repo.get_by_asset_id(asset_id)
        if not fd:
            return {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "xirr": None,
                "message": "No FD detail found",
            }

        principal_inr = fd.principal_amount / 100.0
        rate = fd.interest_rate_pct
        compounding = fd.compounding.value
        start_date = fd.start_date
        maturity_date = fd.maturity_date

        if asset_type == "FD":
            tenure_years = (maturity_date - start_date).days / 365.0
            maturity_amount = compute_fd_maturity(principal_inr, rate, compounding, tenure_years)
            accrued_today = compute_fd_current_value(principal_inr, rate, compounding, start_date, maturity_date)
        else:  # RD
            months = round((maturity_date - start_date).days / 30.44)
            maturity_amount = compute_rd_maturity(principal_inr, rate, months)
            # For RD current value: compute based on elapsed months
            elapsed_months = round((date.today() - start_date).days / 30.44)
            elapsed_months = max(0, min(elapsed_months, months))
            accrued_today = compute_rd_maturity(principal_inr, rate, elapsed_months)

        days_to_maturity = max(0, (maturity_date - date.today()).days)

        # Build cashflows for XIRR from CONTRIBUTION transactions
        transactions = self.txn_repo.list_by_asset(asset_id)
        cashflows = []
        total_invested = 0.0

        for txn in transactions:
            amount_inr = txn.amount_inr / 100.0
            if txn.type.value in OUTFLOW_TYPES:
                cashflows.append((txn.date, amount_inr))  # negative
                total_invested += abs(amount_inr)

        # Add maturity as final inflow at maturity_date (or today if matured)
        effective_end = maturity_date if maturity_date >= date.today() else date.today()
        cashflows.append((effective_end, maturity_amount))

        xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None

        effective_invested = total_invested if total_invested > 0 else principal_inr
        taxable_interest = max(0.0, accrued_today - effective_invested)
        potential_tax_30pct = taxable_interest * 0.30

        return {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "xirr": xirr,
            "cagr": None,
            "absolute_return": compute_absolute_return(principal_inr, accrued_today) if principal_inr > 0 else None,
            "total_invested": effective_invested,
            "current_value": accrued_today,
            "maturity_amount": maturity_amount,
            "accrued_value_today": accrued_today,
            "days_to_maturity": days_to_maturity,
            "message": None,
            "taxable_interest": taxable_interest,
            "potential_tax_30pct": potential_tax_30pct,
        }

    def _compute_epf_returns(self, asset) -> dict:
        """
        Compute returns for EPF assets from transactions only.

        total_invested = sum of all CONTRIBUTION outflows (employee + employer + pension/EPS)
        current_value  = total_invested + sum of all INTEREST inflows
        XIRR           = cashflows from contributions + (today, current_value)
        """
        asset_id = asset.id
        transactions = self.txn_repo.list_by_asset(asset_id)

        total_invested = 0.0
        total_interest = 0.0
        cashflows = []

        for txn in transactions:
            amount_inr = txn.amount_inr / 100.0
            txn_type = txn.type.value
            if txn_type in OUTFLOW_TYPES:
                cashflows.append((txn.date, amount_inr))  # negative
                total_invested += abs(amount_inr)
            elif txn_type == "INTEREST":
                total_interest += amount_inr

        current_value = total_invested + total_interest

        if current_value > 0:
            cashflows.append((date.today(), current_value))

        xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
        abs_return = compute_absolute_return(total_invested, current_value) if total_invested > 0 else None

        return {
            "asset_id": asset_id,
            "asset_type": "EPF",
            "xirr": xirr,
            "cagr": None,
            "absolute_return": abs_return,
            "total_invested": total_invested,
            "current_value": current_value if total_invested > 0 else None,
            "message": None,
        }

    def _compute_valuation_based_returns(self, asset) -> dict:
        asset_id = asset.id
        asset_type = asset.asset_type.value

        # Build cashflows from CONTRIBUTION transactions (always needed)
        transactions = self.txn_repo.list_by_asset(asset_id)
        cashflows = []
        total_invested = 0.0

        for txn in transactions:
            amount_inr = txn.amount_inr / 100.0
            if txn.type.value in OUTFLOW_TYPES:
                cashflows.append((txn.date, amount_inr))  # negative
                total_invested += abs(amount_inr)

        valuations = self.val_repo.list_by_asset(asset_id)
        latest_val = get_latest_valuation(valuations)

        if not latest_val:
            return {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "xirr": None,
                "cagr": None,
                "absolute_return": None,
                "total_invested": total_invested,
                "current_value": None,
                "message": f"No valuation entries found for {asset_type}. Add a passbook entry to compute returns.",
            }

        current_value_inr = latest_val.value_inr / 100.0

        # Add latest valuation as current value inflow
        cashflows.append((latest_val.date, current_value_inr))

        xirr = compute_xirr(cashflows) if len(cashflows) >= 2 else None
        abs_return = compute_absolute_return(total_invested, current_value_inr) if total_invested > 0 else None

        return {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "xirr": xirr,
            "cagr": None,
            "absolute_return": abs_return,
            "total_invested": total_invested,
            "current_value": current_value_inr,
            "message": None,
        }

    def get_asset_lots(self, asset_id: int) -> dict:
        from app.middleware.error_handler import NotFoundError

        asset = self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise NotFoundError(f"Asset {asset_id} not found")

        asset_type = asset.asset_type.value
        transactions = self.txn_repo.list_by_asset(asset_id)

        open_lots, matched_sells = self._build_lots_and_sells(asset_id, asset_type, transactions)

        # Ensure buy_date is serializable as string in open_lots
        for entry in open_lots:
            if not isinstance(entry["buy_date"], str):
                entry["buy_date"] = str(entry["buy_date"])

        return {"open_lots": open_lots, "matched_sells": matched_sells}

    def get_breakdown(self) -> dict:
        """Return invested/current value/XIRR/P&L per asset type."""
        all_assets = self.asset_repo.list(active=None)
        active_by_type: dict[str, list] = {}
        inactive_by_type: dict[str, list] = {}
        for asset in all_assets:
            key = asset.asset_type.value
            if asset.is_active:
                active_by_type.setdefault(key, []).append(asset)
            else:
                inactive_by_type.setdefault(key, []).append(asset)

        all_types = set(active_by_type.keys()) | set(inactive_by_type.keys())

        breakdown = []
        for asset_type in all_types:
            if asset_type in active_by_type:
                overview = self.get_overview(asset_types=[asset_type])
            else:
                overview = {
                    "total_invested": 0.0, "total_current_value": 0.0, "xirr": None,
                    "st_unrealised_gain": None, "lt_unrealised_gain": None,
                    "st_realised_gain": None, "lt_realised_gain": None,
                }

            # Current P&L: unrealized gains for active positions
            st_unr = overview.get("st_unrealised_gain")
            lt_unr = overview.get("lt_unrealised_gain")
            if st_unr is not None or lt_unr is not None:
                current_pnl = (st_unr or 0.0) + (lt_unr or 0.0)
            else:
                invested = overview.get("total_invested") or 0.0
                cv = overview.get("total_current_value") or 0.0
                current_pnl = cv - invested if invested > 0 else 0.0

            # All-time P&L: unrealized + realized (active) + net from inactive assets
            active_realized = (overview.get("st_realised_gain") or 0.0) + (overview.get("lt_realised_gain") or 0.0)

            inactive_pnl = 0.0
            # For FD/RD types with active assets, get_overview() already included
            # inactive FD gains in st_realised_gain — skip the loop to avoid double-counting.
            skip_inactive_fd = asset_type in FD_BASED_TYPES and asset_type in active_by_type
            for inactive_asset in inactive_by_type.get(asset_type, []):
                if skip_inactive_fd:
                    continue
                try:
                    if asset_type in FD_BASED_TYPES:
                        # For FDs/RDs the raw transaction net gives wrong P&L because
                        # the INTEREST txn holds only the interest portion, not the returned
                        # principal. Use the formula-based returns instead.
                        r = self._compute_fd_returns(inactive_asset)
                        cv = r.get("current_value") or 0.0
                        inv = r.get("total_invested") or 0.0
                        inactive_pnl += cv - inv
                    else:
                        # For lot-based assets (stocks, MFs, gold …) the net of all
                        # non-excluded transactions gives the correct realized P&L:
                        # BUY outflows (negative) + SELL inflows (positive) = profit/loss.
                        txns = self.txn_repo.list_by_asset(inactive_asset.id)
                        # Skip assets with no BUY/outflow transactions — these have no
                        # cost basis (e.g. imported SELL-only due to missing tradebook)
                        # and would falsely inflate all-time P&L.
                        has_outflow = any(t.type.value in OUTFLOW_TYPES for t in txns)
                        if not has_outflow:
                            logger.info(
                                "Skipping inactive asset %d (%s) from all-time P&L: no outflow transactions",
                                inactive_asset.id, inactive_asset.name,
                            )
                            continue
                        inactive_pnl += sum(
                            t.amount_inr for t in txns if t.type.value not in EXCLUDED_TYPES
                        ) / 100.0
                except Exception as e:
                    logger.warning("Error computing inactive P&L for asset %d: %s", inactive_asset.id, str(e))

            alltime_pnl = current_pnl + active_realized + inactive_pnl

            total_invested = overview["total_invested"]
            if total_invested > 0:
                breakdown.append({
                    "asset_type": asset_type,
                    "total_invested": total_invested,
                    "total_current_value": overview["total_current_value"],
                    "xirr": overview["xirr"],
                    "current_pnl": round(current_pnl, 2),
                    "alltime_pnl": round(alltime_pnl, 2),
                })

        breakdown.sort(key=lambda x: x["total_current_value"] or 0, reverse=True)
        return {"breakdown": breakdown}

    # Only 4 allocation classes are used in the donut chart.
    # NPS is always treated as DEBT (has equity portion but classified as fixed income).
    # MIXED class (hybrid MFs) is folded into EQUITY.
    # Debt MFs stored with DEBT class stay as DEBT.
    _ALLOCATION_TYPE_OVERRIDE = {
        "NPS": "DEBT",
    }

    def get_allocation(self) -> dict:
        """Return current value grouped by asset_class with percentages.

        Applies overrides so the response only contains the 4 canonical classes:
        EQUITY, DEBT, GOLD, REAL_ESTATE.  MIXED is folded into EQUITY except
        where an asset_type override applies (NPS → DEBT).
        """
        assets = self.asset_repo.list(active=True)
        entries = []
        for asset in assets:
            try:
                current_value = self._get_current_value(asset)
                if current_value and current_value > 0:
                    asset_class = asset.asset_class.value
                    if asset.asset_type.value in self._ALLOCATION_TYPE_OVERRIDE:
                        asset_class = self._ALLOCATION_TYPE_OVERRIDE[asset.asset_type.value]
                    elif asset_class == "MIXED":
                        asset_class = "EQUITY"
                    entries.append({
                        "asset_class": asset_class,
                        "current_value": current_value,
                    })
            except Exception as e:
                logger.warning("Error computing value for asset %d: %s", asset.id, str(e))
        return compute_allocation(entries)

    def get_gainers(self, n: int = 5) -> dict:
        """Return top N gainers and top N losers by absolute_return_pct."""
        assets = self.asset_repo.list(active=True)
        entries = []
        for asset in assets:
            try:
                result = self.get_asset_returns(asset.id)
                total_invested = result.get("total_invested") or 0.0
                current_value = result.get("current_value") or 0.0
                abs_return_pct = None
                if total_invested > 0 and current_value is not None:
                    abs_return_pct = (current_value - total_invested) / total_invested * 100
                entries.append({
                    "asset_id": asset.id,
                    "name": asset.name,
                    "asset_type": asset.asset_type.value,
                    "total_invested": total_invested,
                    "current_value": current_value,
                    "absolute_return_pct": abs_return_pct,
                    "xirr": result.get("xirr"),
                })
            except Exception as e:
                logger.warning("Error computing returns for asset %d: %s", asset.id, str(e))
        return {
            "gainers": find_top_gainers(entries, n=n, gainers=True),
            "losers": find_top_gainers(entries, n=n, gainers=False),
        }

    def _get_current_value(self, asset) -> float | None:
        """Helper: return current value for an asset (all types).

        MF: CAS snapshot market value (authoritative) → fallback to snapshot.closing_units × NAV
            → fallback to stale snapshot market value. Returns None if no snapshot exists.
        Other market-based: transaction units × price_cache NAV.
        FD/RD: compound interest formula.
        PPF/EPF/Real Estate: latest Valuation entry.
        """
        asset_type = asset.asset_type.value

        if asset_type == "MF":
            snapshot = self.cas_snap_repo.get_latest_by_asset_id(asset.id)
            if snapshot is not None:
                if snapshot.closing_units == 0:
                    return 0.0
                snapshot_age_days = (date.today() - snapshot.date).days
                if snapshot_age_days < 30:
                    return snapshot.market_value_inr / 100.0
                price_cache = self.price_repo.get_by_asset_id(asset.id)
                if price_cache:
                    return snapshot.closing_units * (price_cache.price_inr / 100.0)
                return snapshot.market_value_inr / 100.0
            # No CAS snapshot: fall through to MARKET_BASED_TYPES logic (price_cache × units)

        transactions = self.txn_repo.list_by_asset(asset.id)
        filtered_txns = [t for t in transactions if t.type.value not in EXCLUDED_TYPES]

        if asset_type in MARKET_BASED_TYPES:
            price_cache = self.price_repo.get_by_asset_id(asset.id)
            if price_cache:
                total_units = sum(
                    t.units or 0 for t in filtered_txns if t.type.value in UNIT_ADD_TYPES
                ) - sum(
                    t.units or 0 for t in filtered_txns if t.type.value in UNIT_SUB_TYPES
                )
                return total_units * (price_cache.price_inr / 100.0)
        elif asset_type in FD_BASED_TYPES:
            fd = self.fd_repo.get_by_asset_id(asset.id)
            if fd:
                principal_inr = fd.principal_amount / 100.0
                return compute_fd_current_value(
                    principal_inr, fd.interest_rate_pct, fd.compounding.value,
                    fd.start_date, fd.maturity_date
                )
        elif asset_type == "EPF":
            total_invested = 0.0
            total_interest = 0.0
            for txn in transactions:
                txn_type = txn.type.value
                if txn_type in OUTFLOW_TYPES:
                    total_invested += abs(txn.amount_inr / 100.0)
                elif txn_type == "INTEREST":
                    total_interest += txn.amount_inr / 100.0
            current = total_invested + total_interest
            return current if total_invested > 0 else None
        elif asset_type in VALUATION_BASED_TYPES:
            valuations = self.val_repo.list_by_asset(asset.id)
            latest = get_latest_valuation(valuations)
            if latest:
                return latest.value_inr / 100.0
        return None

    def get_overview(self, asset_types: list[str] | None = None) -> dict:
        assets = self.asset_repo.list(active=True)
        if asset_types:
            assets = [a for a in assets if a.asset_type.value in asset_types]

        all_cashflows = []
        total_invested = 0.0
        total_current_value = 0.0

        # Gain field accumulators
        totals = {
            "st_unrealised_gain": 0.0,
            "lt_unrealised_gain": 0.0,
            "st_realised_gain": 0.0,
            "lt_realised_gain": 0.0,
            "total_taxable_interest": 0.0,
            "total_potential_tax": 0.0,
        }
        has_any_unrealised = False
        has_any_realised = False
        has_any_interest = False

        for asset in assets:
            try:
                result = self.get_asset_returns(asset.id)

                invested = result.get("total_invested") or 0.0
                current = result.get("current_value") or 0.0

                total_invested += invested
                if current > 0:
                    total_current_value += current

                # Reconstruct cashflows for portfolio XIRR
                # Must include both outflows (negative) AND inflows (redemptions, dividends)
                # so that partial redemptions are accounted for before adding terminal value.
                #
                # EPF and VALUATION_BASED (PPF, REAL_ESTATE) use a terminal current_value that
                # already embeds all accumulated interest/passbook balance.  Adding intermediate
                # INTEREST inflows here would double-count those returns, producing a portfolio
                # XIRR inconsistent with per-asset XIRR.  Use only outflows for these types.
                asset_type_val = asset.asset_type.value
                _outflow_only = asset_type_val == "EPF" or asset_type_val in VALUATION_BASED_TYPES
                transactions = self.txn_repo.list_by_asset(asset.id)
                filtered_txns = [t for t in transactions if t.type.value not in EXCLUDED_TYPES]
                for txn in filtered_txns:
                    amount_inr = txn.amount_inr / 100.0
                    txn_type = txn.type.value
                    if txn_type in OUTFLOW_TYPES or (not _outflow_only and txn_type in INFLOW_TYPES):
                        all_cashflows.append((txn.date, amount_inr))

                # Accumulate unrealised and realised separately so a 0-unrealised asset
                # (e.g. MF where we null out unrealised) does not suppress realised totals
                for key in ("st_unrealised_gain", "lt_unrealised_gain"):
                    v = result.get(key)
                    if v is not None:
                        totals[key] += v
                        has_any_unrealised = True

                for key in ("st_realised_gain", "lt_realised_gain"):
                    v = result.get(key)
                    if v is not None:
                        totals[key] += v
                        has_any_realised = True

                ti = result.get("taxable_interest")
                pt = result.get("potential_tax_30pct")
                if ti is not None:
                    totals["total_taxable_interest"] += ti
                    has_any_interest = True
                if pt is not None:
                    totals["total_potential_tax"] += pt

            except Exception as e:
                logger.warning("Error computing returns for asset %d: %s", asset.id, str(e))
                continue

        # Add realized interest from inactive (matured) FD/RD assets.
        # These are excluded from total_invested/total_current_value so that
        # current P&L stays active-only, but their earned interest must appear
        # in all-time P&L via st_realised_gain.
        inactive_fd_assets = self.asset_repo.list(active=False)
        if asset_types:
            inactive_fd_assets = [
                a for a in inactive_fd_assets
                if a.asset_type.value in asset_types and a.asset_type.value in FD_BASED_TYPES
            ]
        else:
            inactive_fd_assets = [
                a for a in inactive_fd_assets if a.asset_type.value in FD_BASED_TYPES
            ]
        for asset in inactive_fd_assets:
            try:
                r = self._compute_fd_returns(asset)
                cv = r.get("current_value") or 0.0
                inv = r.get("total_invested") or 0.0
                realized_interest = cv - inv
                if realized_interest != 0:
                    totals["st_realised_gain"] += realized_interest
                    has_any_realised = True
            except Exception as e:
                logger.warning("Error computing inactive FD returns for asset %d: %s", asset.id, str(e))

        # Add today's total_current_value as final inflow for portfolio XIRR
        if total_current_value > 0:
            all_cashflows.append((date.today(), total_current_value))

        portfolio_xirr = compute_xirr(all_cashflows) if len(all_cashflows) >= 2 else None
        abs_return = compute_absolute_return(total_invested, total_current_value) if total_invested > 0 else 0.0

        return {
            "total_invested": total_invested,
            "total_current_value": total_current_value,
            "absolute_return": abs_return,
            "xirr": portfolio_xirr,
            "st_unrealised_gain": totals["st_unrealised_gain"] if has_any_unrealised else None,
            "lt_unrealised_gain": totals["lt_unrealised_gain"] if has_any_unrealised else None,
            "st_realised_gain": totals["st_realised_gain"] if has_any_realised else None,
            "lt_realised_gain": totals["lt_realised_gain"] if has_any_realised else None,
            "total_taxable_interest": totals["total_taxable_interest"] if has_any_interest else None,
            "total_potential_tax": totals["total_potential_tax"] if has_any_interest else None,
        }
