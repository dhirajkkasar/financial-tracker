"""
Service for importing PPF and EPF PDF statements.

Handles:
  - Asset lookup by identifier (account number for PPF, member ID for EPF)
  - Transaction deduplication by txn_id
  - Valuation creation from closing balance (PPF) / net balance (EPF)
  - EPS sub-asset auto-creation (EPF imports)
  - EPF asset inactivation when net balance = 0
"""
import logging
import uuid

from sqlalchemy.orm import Session

from app.importers.ppf_pdf_parser import PPFPDFParser
from app.importers.epf_pdf_parser import EPFPDFParser
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import TransactionType
from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository
from app.repositories.valuation_repo import ValuationRepository

logger = logging.getLogger(__name__)

LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST"}


class PPFEPFImportService:
    """Import service for PPF and EPF PDF statements."""

    def __init__(self, db: Session):
        self.db = db
        self.asset_repo = AssetRepository(db)
        self.txn_repo = TransactionRepository(db)
        self.val_repo = ValuationRepository(db)

    # ------------------------------------------------------------------
    # PPF
    # ------------------------------------------------------------------

    def import_ppf(self, file_bytes: bytes) -> dict:
        """
        Parse a PPF PDF and import transactions into the DB.

        The PPF asset must already exist with identifier = stripped account number.
        Returns:
          {inserted, skipped, valuation_created, valuation_value, valuation_date,
           account_number, errors}
        """
        parser = PPFPDFParser()
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

        # Find asset by identifier (account number)
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
            logger.info("PPF: imported txn %s for asset %s", txn.txn_id, asset.id)

        # Create Valuation from closing balance
        valuation_created = False
        if result.closing_balance_inr is not None and result.closing_balance_date:
            value_paise = round(result.closing_balance_inr * 100)
            self.val_repo.create(
                asset_id=asset.id,
                date=result.closing_balance_date,
                value_inr=value_paise,
                source="ppf_pdf",
                notes=f"Closing balance from PDF import (account {result.account_number})",
            )
            valuation_created = True
            logger.info(
                "PPF: created valuation %.2f INR on %s for asset %s",
                result.closing_balance_inr,
                result.closing_balance_date,
                asset.id,
            )

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
        Auto-creates an EPS sub-asset (type=EPF, identifier=member_id_EPS).
        Creates a Valuation for the EPF asset from the net balance.
        Marks the EPF asset inactive if net balance = 0.

        Returns:
          {epf_inserted, epf_skipped, eps_inserted, eps_skipped,
           eps_asset_id, eps_asset_created, epf_valuation_created,
           epf_valuation_value, errors}
        """
        parser = EPFPDFParser()
        result = parser.parse(file_bytes)

        if result.errors:
            return {
                "epf_inserted": 0,
                "epf_skipped": 0,
                "eps_inserted": 0,
                "eps_skipped": 0,
                "eps_asset_id": None,
                "eps_asset_created": False,
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

        # Find or create EPS sub-asset
        eps_identifier = f"{result.member_id}_EPS"
        eps_asset = self._find_asset_by_identifier(eps_identifier)
        eps_asset_created = False
        if eps_asset is None:
            eps_asset = self.asset_repo.create(
                name=f"EPS — {result.establishment_name}",
                identifier=eps_identifier,
                asset_type=AssetType.EPF,
                asset_class=AssetClass.DEBT,
                currency="INR",
            )
            eps_asset_created = True
            logger.info("EPF: auto-created EPS asset id=%s", eps_asset.id)

        # Import transactions — route to EPF or EPS asset based on identifier
        epf_inserted = 0
        epf_skipped = 0
        eps_inserted = 0
        eps_skipped = 0

        for txn in result.transactions:
            if self.txn_repo.get_by_txn_id(txn.txn_id):
                if txn.asset_identifier == eps_identifier:
                    eps_skipped += 1
                else:
                    epf_skipped += 1
                continue

            if txn.asset_identifier == eps_identifier:
                target_asset = eps_asset
            else:
                target_asset = epf_asset

            amount_paise = round(txn.amount_inr * 100)
            lot_id = str(uuid.uuid4()) if txn.txn_type in LOT_TYPES else None

            self.txn_repo.create(
                txn_id=txn.txn_id,
                asset_id=target_asset.id,
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

            if txn.asset_identifier == eps_identifier:
                eps_inserted += 1
            else:
                epf_inserted += 1
            logger.info("EPF: imported txn %s for asset %s", txn.txn_id, target_asset.id)

        # Create EPF Valuation (net balance)
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

        # Mark EPF asset inactive if balance = 0
        if net_balance == 0:
            epf_asset.is_active = False
            self.db.commit()
            logger.info("EPF: marked asset %s inactive (zero balance)", epf_asset.id)

        return {
            "epf_inserted": epf_inserted,
            "epf_skipped": epf_skipped,
            "eps_inserted": eps_inserted,
            "eps_skipped": eps_skipped,
            "eps_asset_id": eps_asset.id,
            "eps_asset_created": eps_asset_created,
            "epf_valuation_created": epf_valuation_created,
            "epf_valuation_value": net_balance,
            "errors": result.errors,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_asset_by_identifier(self, identifier: str) -> "Asset | None":
        return self.db.query(Asset).filter(Asset.identifier == identifier).first()
