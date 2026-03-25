"""
EPF Auto-Contribution Service

On startup, for each active EPF asset, checks whether monthly contribution
transactions are missing and auto-fills them using the same amounts as the
most recent contribution (employee share, employer share, EPS).

Only CONTRIBUTION transactions are auto-filled. INTEREST, TRANSFER, and all
other transaction types must be added manually.

txn_id format matches the EPF PDF parser and CLI convention so that
auto-inserted transactions are deduplicated against PDF-imported or
CLI-inserted ones without conflicts.
"""
import calendar
import hashlib
import logging
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetType
from app.models.transaction import Transaction, TransactionType
from app.repositories.transaction_repo import TransactionRepository

logger = logging.getLogger(__name__)


def _epf_txn_id(*parts) -> str:
    """Stable EPF txn_id — matches EPF PDF parser and CLI convention."""
    raw = "|".join(str(p) for p in parts)
    return "epf_" + hashlib.sha256(raw.encode()).hexdigest()


class EPFAutoContribService:
    """
    Auto-fills missing monthly EPF contribution transactions on startup.

    For each active EPF asset, finds the last Employee Share contribution,
    determines which subsequent months are missing (up to the previous
    completed month), and inserts contributions using the same amounts.
    """

    def __init__(self, db: Session):
        self.db = db
        self.txn_repo = TransactionRepository(db)

    def backfill_missing_contributions(self, today: date | None = None) -> dict:
        """
        Check all active EPF assets and insert missing monthly contributions.

        Args:
            today: Override today's date (used in tests). Defaults to date.today().

        Returns:
            {assets_checked, assets_updated, months_inserted}
        """
        if today is None:
            today = date.today()

        # Auto-fill up to the end of the *previous* month.
        # Current month is not filled — contributions may not have been processed yet.
        if today.month == 1:
            fill_up_to = (today.year - 1, 12)
        else:
            fill_up_to = (today.year, today.month - 1)

        epf_assets = (
            self.db.query(Asset)
            .filter(Asset.asset_type == AssetType.EPF, Asset.is_active == True)
            .all()
        )

        assets_checked = len(epf_assets)
        assets_updated = 0
        months_inserted = 0

        for asset in epf_assets:
            inserted = self._backfill_asset(asset, fill_up_to)
            if inserted > 0:
                assets_updated += 1
                months_inserted += inserted // 3  # 3 txns per month (emp + er + eps)

        return {
            "assets_checked": assets_checked,
            "assets_updated": assets_updated,
            "months_inserted": months_inserted,
        }

    def _backfill_asset(self, asset: Asset, fill_up_to: tuple[int, int]) -> int:
        """
        Back-fill missing contribution months for one EPF asset.
        Returns total number of transactions inserted.
        """
        last_emp = (
            self.db.query(Transaction)
            .filter(
                Transaction.asset_id == asset.id,
                Transaction.type == TransactionType.CONTRIBUTION,
                Transaction.notes == "Employee Share",
            )
            .order_by(Transaction.date.desc())
            .first()
        )

        if last_emp is None:
            return 0

        last_year, last_month = last_emp.date.year, last_emp.date.month

        # Already up to date — last contribution is in the fill_up_to period or later
        if (last_year, last_month) >= fill_up_to:
            return 0

        # Find the matching employer and EPS contributions for the same last month
        month_start = date(last_year, last_month, 1)
        month_end = date(last_year, last_month, calendar.monthrange(last_year, last_month)[1])

        last_er = (
            self.db.query(Transaction)
            .filter(
                Transaction.asset_id == asset.id,
                Transaction.type == TransactionType.CONTRIBUTION,
                Transaction.notes == "Employer Share",
                Transaction.date >= month_start,
                Transaction.date <= month_end,
            )
            .first()
        )

        last_eps = (
            self.db.query(Transaction)
            .filter(
                Transaction.asset_id == asset.id,
                Transaction.type == TransactionType.CONTRIBUTION,
                Transaction.notes == "Pension Contribution (EPS)",
                Transaction.date >= month_start,
                Transaction.date <= month_end,
            )
            .first()
        )

        # amount_inr is stored in paise, negative for outflows
        emp_paise = last_emp.amount_inr
        er_paise = last_er.amount_inr if last_er is not None else emp_paise
        eps_paise = last_eps.amount_inr if last_eps is not None else 0

        member_id = asset.identifier or ""
        inserted = 0

        cur_year, cur_month = last_year, last_month
        while True:
            # Advance one month
            if cur_month == 12:
                cur_month, cur_year = 1, cur_year + 1
            else:
                cur_month += 1

            if (cur_year, cur_month) > fill_up_to:
                break

            mmyyyy = f"{cur_month:02d}{cur_year}"
            last_day = calendar.monthrange(cur_year, cur_month)[1]
            txn_date = date(cur_year, cur_month, last_day)

            inserted += self._insert_if_missing(
                asset_id=asset.id,
                txn_id=_epf_txn_id(member_id, "CONTRIB_EMP", mmyyyy, abs(emp_paise)),
                amount_paise=emp_paise,
                notes="Employee Share",
                txn_date=txn_date,
            )
            inserted += self._insert_if_missing(
                asset_id=asset.id,
                txn_id=_epf_txn_id(member_id, "CONTRIB_ER", mmyyyy, abs(er_paise)),
                amount_paise=er_paise,
                notes="Employer Share",
                txn_date=txn_date,
            )
            if eps_paise != 0:
                inserted += self._insert_if_missing(
                    asset_id=asset.id,
                    txn_id=_epf_txn_id(member_id, "CONTRIB_EPS", mmyyyy, abs(eps_paise)),
                    amount_paise=eps_paise,
                    notes="Pension Contribution (EPS)",
                    txn_date=txn_date,
                )
                if inserted > 0:
                    logger.info(
                        "EPF auto-contrib: inserted contributions for %02d/%d asset_id=%d",
                        cur_month, cur_year, asset.id,
                    )

        return inserted

    def _insert_if_missing(
        self,
        asset_id: int,
        txn_id: str,
        amount_paise: int,
        notes: str,
        txn_date: date,
    ) -> int:
        """Insert a contribution transaction if it doesn't already exist.

        Returns 1 if inserted, 0 if skipped (duplicate).
        """
        if self.txn_repo.get_by_txn_id(txn_id):
            return 0

        self.txn_repo.create(
            txn_id=txn_id,
            asset_id=asset_id,
            type=TransactionType.CONTRIBUTION,
            date=txn_date,
            units=None,
            price_per_unit=None,
            forex_rate=None,
            amount_inr=amount_paise,
            charges_inr=0,
            lot_id=str(uuid.uuid4()),
            notes=notes,
        )
        return 1
