"""
Service for importing PPF and EPF statements.

Handles:
  - Asset lookup by identifier (account number for PPF, member ID for EPF)
  - Transaction deduplication by txn_id
  - Valuation creation from closing balance (PPF) / net balance (EPF)
"""
import logging
import uuid

from sqlalchemy.orm import Session

from app.importers.ppf_csv_importer import PPFCSVImporter
from app.importers.epf_pdf_importer import EPFPDFImporter
from app.models.asset import Asset
from app.models.transaction import TransactionType
from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.valuation_repo import ValuationRepository

logger = logging.getLogger(__name__)

LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST"}


class PPFEPFImportService:
    """Import service for PPF (CSV) and EPF (PDF) statements."""

    def __init__(self, db: Session):
        self.db = db
        self.asset_repo = AssetRepository(db)
        self.txn_repo = TransactionRepository(db)
        self.val_repo = ValuationRepository(db)

    # ------------------------------------------------------------------
    # PPF CSV
    # ------------------------------------------------------------------

    def import_ppf_csv(self, file_bytes: bytes) -> dict:
        """
        Parse a PPF CSV account statement and import transactions into the DB.

        The PPF asset must already exist with identifier = account number.
        Credits whose details contain "INTEREST" become INTEREST transactions
        (positive inflow); all other credits become CONTRIBUTION transactions
        (negative outflow).

        Returns:
          {inserted, skipped, valuation_created, valuation_value, valuation_date,
           account_number, errors}
        """
        parser = PPFCSVImporter()
        result = parser.parse(file_bytes)

        if result.errors:
            return {
                "inserted": 0,
                "skipped": 0,
                "valuation_created": False,
                "valuation_value": None,
                "valuation_date": None,
                "account_number": result.account_number,
                "errors": result.errors,
            }

        asset = self._find_asset_by_identifier(result.account_number)
        if asset is None:
            from app.middleware.error_handler import NotFoundError
            raise NotFoundError(
                f"No PPF asset found with identifier '{result.account_number}'. "
                "Create the asset first before importing."
            )

        inserted = 0
        skipped = 0

        for txn in result.transactions:
            if self.txn_repo.get_by_txn_id(txn.txn_id):
                skipped += 1
                continue

            amount_paise = round(txn.amount_inr * 100)
            lot_id = str(uuid.uuid4()) if txn.txn_type in LOT_TYPES else None

            self.txn_repo.create(
                txn_id=txn.txn_id,
                asset_id=asset.id,
                type=TransactionType(txn.txn_type),
                date=txn.date,
                units=txn.units,
                price_per_unit=txn.price_per_unit,
                forex_rate=None,
                amount_inr=amount_paise,
                charges_inr=0,
                lot_id=lot_id,
                notes=txn.notes,
            )
            inserted += 1
            logger.info("PPF CSV: imported txn %s for asset %s", txn.txn_id, asset.id)

        # Create Valuation from closing balance
        valuation_created = False
        if result.closing_balance_inr and result.closing_balance_date:
            value_paise = round(result.closing_balance_inr * 100)
            self.val_repo.create(
                asset_id=asset.id,
                date=result.closing_balance_date,
                value_inr=value_paise,
                source="ppf_csv",
                notes=f"Closing balance from CSV import (account {result.account_number})",
            )
            valuation_created = True
            logger.info(
                "PPF CSV: created valuation %.2f INR on %s for asset %s",
                result.closing_balance_inr,
                result.closing_balance_date,
                asset.id,
            )

        self.db.commit()

        return {
            "inserted": inserted,
            "skipped": skipped,
            "valuation_created": valuation_created,
            "valuation_value": result.closing_balance_inr,
            "valuation_date": str(result.closing_balance_date) if result.closing_balance_date else None,
            "account_number": result.account_number,
            "errors": result.errors,
        }

    # ------------------------------------------------------------------
    # EPF
    # ------------------------------------------------------------------

    def import_epf(self, file_bytes: bytes) -> dict:
        """
        Parse an EPF PDF and import transactions.

        The EPF asset must already exist with identifier = member_id.
        All transactions (employee share, employer share, pension/EPS, interest, transfer)
        are imported under the EPF asset. No separate EPS sub-asset is created.

        Returns:
          {inserted, skipped, epf_valuation_created, epf_valuation_value, errors}
        """
        parser = EPFPDFImporter()
        result = parser.parse(file_bytes)

        if result.errors:
            return {
                "inserted": 0,
                "skipped": 0,
                "epf_valuation_created": False,
                "epf_valuation_value": None,
                "errors": result.errors,
            }

        # Find EPF asset by member_id
        epf_asset = self._find_asset_by_identifier(result.member_id)
        if epf_asset is None:
            from app.middleware.error_handler import NotFoundError
            raise NotFoundError(
                f"No EPF asset found with identifier '{result.member_id}'. "
                "Create the asset first before importing."
            )

        inserted = 0
        skipped = 0

        for txn in result.transactions:
            if self.txn_repo.get_by_txn_id(txn.txn_id):
                skipped += 1
                continue

            amount_paise = round(txn.amount_inr * 100)
            lot_id = str(uuid.uuid4()) if txn.txn_type in LOT_TYPES else None

            self.txn_repo.create(
                txn_id=txn.txn_id,
                asset_id=epf_asset.id,
                type=TransactionType(txn.txn_type),
                date=txn.date,
                units=txn.units,
                price_per_unit=txn.price_per_unit,
                forex_rate=None,
                amount_inr=amount_paise,
                charges_inr=0,
                lot_id=lot_id,
                notes=txn.notes,
            )
            inserted += 1
            logger.info("EPF: imported txn %s for asset %s", txn.txn_id, epf_asset.id)

        # Create EPF Valuation (net balance from passbook)
        epf_valuation_created = False
        net_balance = result.net_balance_inr
        use_date = result.print_date
        if use_date is None:
            from datetime import date
            use_date = date.today()

        value_paise = round(net_balance * 100)
        self.val_repo.create(
            asset_id=epf_asset.id,
            date=use_date,
            value_inr=value_paise,
            source="epf_pdf",
            notes=f"Net balance from PDF import (member {result.member_id})",
        )
        epf_valuation_created = True

        self.db.commit()

        return {
            "inserted": inserted,
            "skipped": skipped,
            "epf_valuation_created": epf_valuation_created,
            "epf_valuation_value": net_balance,
            "errors": result.errors,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_asset_by_identifier(self, identifier: str) -> "Asset | None":
        return self.db.query(Asset).filter(Asset.identifier == identifier).first()
