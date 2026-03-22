import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.importers.base import ParsedTransaction, ParsedFundSnapshot
from app.models.asset import Asset, AssetType, AssetClass
from app.models.transaction import TransactionType
from app.repositories.asset_repo import AssetRepository
from app.repositories.cas_snapshot_repo import CasSnapshotRepository
from app.repositories.transaction_repo import TransactionRepository

logger = logging.getLogger(__name__)

# Module-level in-memory preview store: {preview_id: {"transactions": [...], "snapshots": [...], "created_at": datetime}}
_PREVIEW_STORE: dict[str, dict] = {}

PREVIEW_TTL_MINUTES = 15

LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST"}

# Unit-flow types for STOCK_IN/STOCK_US inactive detection.
# SPLIT, DIVIDEND, INTEREST, TRANSFER are intentionally excluded — they do not
# change the number of units held for stock assets.
_STOCK_UNIT_ADD_TYPES = {"BUY", "SIP", "VEST", "BONUS"}
_STOCK_UNIT_SUB_TYPES = {"SELL", "REDEMPTION"}

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

    def preview(
        self,
        parsed_txns: list[ParsedTransaction] | None = None,
        transactions: list[ParsedTransaction] | None = None,
        preview_snapshots: list[ParsedFundSnapshot] | None = None,
    ) -> dict:
        """
        Check parsed transactions against DB and store a preview for later commit.

        Accepts transactions via positional `parsed_txns` (legacy) or keyword
        `transactions`. CAS callers may also pass `preview_snapshots`.
        """
        # Support both call styles: preview(txns) and preview(transactions=txns)
        txn_list: list[ParsedTransaction] = parsed_txns or transactions or []
        snap_list: list[ParsedFundSnapshot] = preview_snapshots or []

        txn_repo = TransactionRepository(self.db)
        new_txns = []
        duplicates = []

        for txn in txn_list:
            if txn_repo.get_by_txn_id(txn.txn_id):
                duplicates.append(txn)
            else:
                new_txns.append(txn)

        preview_id = str(uuid.uuid4())
        _PREVIEW_STORE[preview_id] = {
            "transactions": txn_list,
            "snapshots": snap_list,
            "created_at": datetime.utcnow(),
        }

        return {
            "preview_id": preview_id,
            "new_count": len(new_txns),
            "duplicate_count": len(duplicates),
            "transactions": [self._txn_to_dict(t) for t in txn_list],
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
        snapshots: list[ParsedFundSnapshot] = entry.get("snapshots", [])
        asset_repo = AssetRepository(self.db)
        txn_repo = TransactionRepository(self.db)
        snap_repo = CasSnapshotRepository(self.db)

        created = 0
        skipped = 0
        touched_stock_assets: dict[int, "Asset"] = {}

        for txn in parsed_txns:
            if txn_repo.get_by_txn_id(txn.txn_id):
                skipped += 1
                continue

            asset = self._find_or_create_asset(asset_repo, txn)
            if txn.asset_type in {"STOCK_IN", "STOCK_US"}:
                touched_stock_assets[asset.id] = asset
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

        # Commit CAS snapshots and update is_active
        snapshot_count = 0
        for snap in snapshots:
            asset = self.db.query(Asset).filter(Asset.identifier == snap.isin).first()
            if not asset:
                logger.warning("CAS snapshot: no asset found for ISIN %s — skipping", snap.isin)
                continue

            snap_repo.create(
                asset_id=asset.id,
                date=snap.date,
                closing_units=snap.closing_units,
                nav_price_inr=round(snap.nav_price_inr * 100),
                market_value_inr=round(snap.market_value_inr * 100),
                total_cost_inr=round(snap.total_cost_inr * 100),
            )
            asset.is_active = snap.closing_units > 0
            snapshot_count += 1
            logger.info(
                "CAS snapshot saved for %s (id=%s): units=%.3f active=%s",
                asset.name, asset.id, snap.closing_units, asset.is_active,
            )

        # Auto-mark fully-exited stock assets as inactive
        for asset_id, stock_asset in touched_stock_assets.items():
            all_txns = txn_repo.list_by_asset(asset_id)
            net_units = sum(
                (t.units or 0.0) if t.type.value in _STOCK_UNIT_ADD_TYPES
                else -(t.units or 0.0) if t.type.value in _STOCK_UNIT_SUB_TYPES
                else 0.0
                for t in all_txns
            )
            if net_units < -1e-6:
                logger.warning(
                    "Asset %d '%s' has negative net_units=%.4f — possible data issue; skipping auto-inactive",
                    asset_id, stock_asset.name, net_units,
                )
            elif net_units <= 1e-6 and stock_asset.is_active:
                stock_asset.is_active = False
                logger.info(
                    "Auto-marked asset %d '%s' inactive (net_units=%.4f)",
                    asset_id, stock_asset.name, net_units,
                )

        # Auto-trigger corporate actions for newly imported stock assets (non-blocking).
        # NSE rate-limiting or network failures must not roll back a completed import.
        if touched_stock_assets:
            try:
                from app.services.corp_actions_service import CorpActionsService
                corp_svc = CorpActionsService(self.db)
                for asset_id, stock_asset in touched_stock_assets.items():
                    try:
                        corp_svc.process_asset(stock_asset)
                    except Exception as e:
                        logger.warning(
                            "Corp actions failed for asset %d '%s': %s",
                            asset_id, stock_asset.name, e,
                        )
            except Exception as e:
                logger.warning("CorpActionsService unavailable: %s", e)

        self.db.commit()
        del _PREVIEW_STORE[preview_id]
        return {"created_count": created, "skipped_count": skipped, "snapshot_count": snapshot_count}



    def _find_or_create_asset(self, asset_repo: AssetRepository, txn: ParsedTransaction) -> Asset:
        """Find an existing asset by identifier or create a new one.

        Lookup order:
        1. ISIN match (preferred — stable across ticker renames)
        2. Ticker/name match within the same asset_type (fallback when ISIN is absent,
           e.g. old BSE 2018 tradebooks that exported without ISIN)

        TODO: BSE vs NSE ticker name divergence (e.g. "ASHOK LEYL." vs "ASHOKLEY") means
        the same company can still create separate assets when both ISIN and name differ.
        Fix requires a canonical name/alias table or CDSL demat statement import.

        TODO: ISIN changes due to corporate restructuring (HDFC Bank merger, IRCTC split)
        cause the same company to appear as two assets with different ISINs. These must be
        merged manually or resolved via NSE corporate action data once that feature is built.

        TODO: Missing buys (IPO allotments, off-market transfers) have no CSV record so
        sold shares create assets with only SELL transactions and negative net_units.
        Fix requires importing CDSL/NSDL demat statement as authoritative source.
        """
        asset_type = AssetType(txn.asset_type)
        asset_class = ASSET_CLASS_MAP.get(txn.asset_type, AssetClass.EQUITY)

        if txn.asset_identifier:
            existing = self.db.query(Asset).filter(
                Asset.identifier == txn.asset_identifier
            ).first()
            if existing:
                return existing
        else:
            # No ISIN — fall back to exact ticker/name match within the same asset type.
            # Prevents duplicate assets when the same stock appears across multiple CSV rows
            # with an empty ISIN field (old BSE tradebook format).
            existing = self.db.query(Asset).filter(
                Asset.name == txn.asset_name,
                Asset.asset_type == asset_type,
            ).first()
            if existing:
                return existing

        return asset_repo.create(
            name=txn.asset_name,
            identifier=txn.asset_identifier or None,
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
