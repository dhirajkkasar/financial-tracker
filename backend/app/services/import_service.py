import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.importers.base import ParsedTransaction
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import TransactionType
from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository

logger = logging.getLogger(__name__)

# Module-level in-memory preview store: {preview_id: {"transactions": [...], "created_at": datetime}}
_PREVIEW_STORE: dict[str, dict] = {}

PREVIEW_TTL_MINUTES = 15

LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST"}

ASSET_CLASS_MAP: dict[str, AssetClass] = {
    "STOCK_IN": AssetClass.EQUITY,
    "STOCK_US": AssetClass.EQUITY,
    "RSU": AssetClass.EQUITY,
    "MF": AssetClass.MIXED,
    "NPS": AssetClass.MIXED,
    "GOLD": AssetClass.GOLD,
    "SGB": AssetClass.GOLD,
    "REAL_ESTATE": AssetClass.REAL_ESTATE,
    "FD": AssetClass.DEBT,
    "RD": AssetClass.DEBT,
    "PPF": AssetClass.DEBT,
    "EPF": AssetClass.DEBT,
}


class ImportService:
    def __init__(self, db: Session):
        self.db = db

    def preview(self, parsed_txns: list[ParsedTransaction]) -> dict:
        """Check parsed transactions against DB and store a preview for later commit."""
        txn_repo = TransactionRepository(self.db)
        new_txns = []
        duplicates = []

        for txn in parsed_txns:
            if txn_repo.get_by_txn_id(txn.txn_id):
                duplicates.append(txn)
            else:
                new_txns.append(txn)

        preview_id = str(uuid.uuid4())
        _PREVIEW_STORE[preview_id] = {
            "transactions": parsed_txns,
            "created_at": datetime.utcnow(),
        }

        return {
            "preview_id": preview_id,
            "new_count": len(new_txns),
            "duplicate_count": len(duplicates),
            "transactions": [self._txn_to_dict(t) for t in parsed_txns],
        }

    def commit(self, preview_id: str) -> dict | None:
        """Commit a previewed import. Returns None if preview not found or expired."""
        entry = _PREVIEW_STORE.get(preview_id)
        if entry is None:
            return None

        age = datetime.utcnow() - entry["created_at"]
        if age > timedelta(minutes=PREVIEW_TTL_MINUTES):
            del _PREVIEW_STORE[preview_id]
            return None

        parsed_txns: list[ParsedTransaction] = entry["transactions"]
        asset_repo = AssetRepository(self.db)
        txn_repo = TransactionRepository(self.db)

        created = 0
        skipped = 0

        for txn in parsed_txns:
            if txn_repo.get_by_txn_id(txn.txn_id):
                skipped += 1
                continue

            asset = self._find_or_create_asset(asset_repo, txn)
            amount_paise = round(txn.amount_inr * 100)
            charges_paise = round(txn.charges_inr * 100)

            lot_id = str(uuid.uuid4()) if txn.txn_type in LOT_TYPES else None

            txn_repo.create(
                txn_id=txn.txn_id,
                asset_id=asset.id,
                type=TransactionType(txn.txn_type),
                date=txn.date,
                units=txn.units,
                price_per_unit=txn.price_per_unit,
                forex_rate=None,
                amount_inr=amount_paise,
                charges_inr=charges_paise,
                lot_id=lot_id,
                notes=txn.notes,
            )
            created += 1
            logger.info("Imported txn %s for asset %s (id=%s)", txn.txn_id, txn.asset_name, asset.id)

        del _PREVIEW_STORE[preview_id]
        return {"created_count": created, "skipped_count": skipped}

    def _find_or_create_asset(self, asset_repo: AssetRepository, txn: ParsedTransaction) -> Asset:
        """Find an existing asset by identifier or create a new one."""
        if txn.asset_identifier:
            existing = self.db.query(Asset).filter(
                Asset.identifier == txn.asset_identifier
            ).first()
            if existing:
                return existing

        asset_type = AssetType(txn.asset_type)
        asset_class = ASSET_CLASS_MAP.get(txn.asset_type, AssetClass.EQUITY)

        return asset_repo.create(
            name=txn.asset_name,
            identifier=txn.asset_identifier,
            asset_type=asset_type,
            asset_class=asset_class,
            currency="INR",
        )

    def _txn_to_dict(self, txn: ParsedTransaction) -> dict:
        return {
            "source": txn.source,
            "asset_name": txn.asset_name,
            "asset_identifier": txn.asset_identifier,
            "asset_type": txn.asset_type,
            "txn_type": txn.txn_type,
            "date": str(txn.date),
            "units": txn.units,
            "price_per_unit": txn.price_per_unit,
            "amount_inr": txn.amount_inr,
            "charges_inr": txn.charges_inr,
            "txn_id": txn.txn_id,
            "notes": txn.notes,
        }


def get_import_service(db: Session) -> ImportService:
    return ImportService(db)
