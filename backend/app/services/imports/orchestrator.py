"""
ImportOrchestrator — coordinates preview/commit for any file import.

preview(): parse file → deduplicate → store in PreviewStore → return ImportPreviewResponse
commit():  load from store → persist transactions → run post-processors → publish event

Adding new post-processing: create an IPostProcessor subclass, register it in
api/dependencies.py. No changes to this file.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.importers.base import ImportResult, ParsedTransaction
from app.importers.pipeline import ImportPipeline
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.imports import (
    ImportPreviewResponse,
    ImportCommitResponse,
    ParsedTransactionPreview,
)
from app.engine.mf_classifier import classify_mf
from app.engine.mf_scheme_lookup import lookup_by_isin
from app.services.event_bus import ImportCompletedEvent, IEventBus
from app.services.imports.post_processors.base import IPostProcessor
from app.services.imports.preview_store import PreviewStore

logger = logging.getLogger(__name__)

ASSET_CLASS_MAP: dict[str, AssetClass] = {
    "STOCK_IN": AssetClass.EQUITY,
    "STOCK_US": AssetClass.EQUITY,
    "RSU": AssetClass.EQUITY,
    "NPS": AssetClass.DEBT,
    "GOLD": AssetClass.GOLD,
    "SGB": AssetClass.GOLD,
    "REAL_ESTATE": AssetClass.REAL_ESTATE,
    "FD": AssetClass.DEBT,
    "RD": AssetClass.DEBT,
    "PPF": AssetClass.DEBT,
    "EPF": AssetClass.DEBT,
}


class ImportOrchestrator:
    def __init__(
        self,
        uow_factory,
        pipeline: ImportPipeline,
        preview_store: PreviewStore,
        post_processors: list,
        event_bus: IEventBus,
    ):
        self._uow_factory = uow_factory
        self._pipeline = pipeline
        self._store = preview_store
        self._processors: dict[str, IPostProcessor] = {
            at: p for p in post_processors for at in p.asset_types
        }
        self._bus = event_bus

    # ------------------------------------------------------------------
    # preview
    # ------------------------------------------------------------------

    def preview(
        self,
        source: str,
        fmt: str,
        file_bytes: bytes,
    ) -> ImportPreviewResponse:
        result = self._pipeline.run(source, fmt, file_bytes)
        preview_id = self._store.put(result)

        txn_previews = [
            ParsedTransactionPreview(
                txn_id=t.txn_id,
                asset_name=t.asset_name,
                asset_type=t.asset_type,
                txn_type=t.txn_type,
                date=t.date,
                units=t.units,
                amount_inr=t.amount_inr,
                notes=t.notes,
                is_duplicate=False,
            )
            for t in result.transactions
        ]
        return ImportPreviewResponse(
            preview_id=preview_id,
            new_count=len(result.transactions),
            duplicate_count=getattr(result, "duplicate_count", 0),
            transactions=txn_previews,
            warnings=result.warnings,
        )

    # ------------------------------------------------------------------
    # commit
    # ------------------------------------------------------------------

    def commit(self, preview_id: str) -> Optional[ImportCommitResponse]:
        result = self._store.get(preview_id)
        if result is None:
            return None  # expired or not found

        inserted = 0
        skipped = 0
        errors: list[str] = []

        with self._uow_factory() as uow:
            for parsed_txn in result.transactions:
                try:
                    # Find or create the asset
                    asset = self._find_or_create_asset(parsed_txn, uow)

                    # Check for duplicate (second-pass safety)
                    if uow.transactions.get_by_txn_id(parsed_txn.txn_id):
                        skipped += 1
                        continue

                    # Persist transaction
                    txn = uow.transactions.create(
                        asset_id=asset.id,
                        txn_id=parsed_txn.txn_id,
                        type=parsed_txn.txn_type,
                        date=parsed_txn.date,
                        units=parsed_txn.units,
                        price_per_unit=parsed_txn.price_per_unit,
                        forex_rate=parsed_txn.forex_rate,
                        amount_inr=int(parsed_txn.amount_inr * 100),  # INR → paise
                        charges_inr=int(parsed_txn.charges_inr * 100),
                        lot_id=parsed_txn.lot_id,
                        notes=parsed_txn.notes,
                    )
                    inserted += 1

                    # Run post-processor for this asset type
                    processor = self._processors.get(parsed_txn.asset_type)
                    if processor:
                        processor.process(asset, [txn], uow)

                except Exception as exc:
                    logger.warning("Failed to import txn %s: %s", parsed_txn.txn_id, exc)
                    errors.append(str(exc))

            # Create closing valuation if the importer populated one (e.g. PPF CSV)
            print("Post-processing imported transactions...")
            print(f"Closing valuation: INR {result.closing_valuation_inr}, date {result.closing_valuation_date}")
            if (
                result.closing_valuation_inr is not None
                and result.closing_valuation_date is not None
            ):
                first_txn = result.transactions[0] if result.transactions else None
                if first_txn:
                    try:
                        asset = self._find_or_create_asset(first_txn, uow)
                        print(f"Creating closing valuation for asset '{asset})")
                        uow.valuations.create(
                            asset_id=asset.id,
                            date=result.closing_valuation_date,
                            value_inr=int(result.closing_valuation_inr * 100),
                            source=result.closing_valuation_source or "import",
                            notes=result.closing_valuation_notes,
                        )
                    except Exception as exc:
                        logger.warning("Failed to create closing valuation: %s", exc)
                        errors.append(f"Valuation error: {exc}")
                else:
                    logger.warning("No transactions found to associate closing valuation with")
                    errors.append("Valuation error: no transactions found for asset association")

        # Publish event for each unique asset_type inserted
        if inserted > 0:
            self._bus.publish(
                ImportCompletedEvent(
                    asset_id=0,  # batch: no single asset_id
                    asset_type=AssetType[result.transactions[0].asset_type] if result.transactions else AssetType.STOCK_IN,
                    inserted_count=inserted,
                )
            )

        self._store.delete(preview_id)
        return ImportCommitResponse(inserted=inserted, skipped=skipped, errors=errors)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _find_or_create_asset(self, parsed_txn: ParsedTransaction, uow: UnitOfWork) -> Asset:
        """Find asset by identifier or name; create if not found.

        For MF assets the scheme_code and scheme_category are resolved from the
        bundled CSV only when the asset is new or its mfapi_scheme_code is empty.
        """
        assets = uow.assets.list(active=None)

        # Match by identifier (ISIN / scheme code)
        if parsed_txn.asset_identifier:
            for a in assets:
                if a.identifier == parsed_txn.asset_identifier:
                    # Backfill scheme_code/category if missing on existing MF asset
                    if parsed_txn.asset_type == "MF" and not a.mfapi_scheme_code:
                        self._apply_mf_scheme(a, parsed_txn.asset_identifier)
                    return a

        # Match by name
        for a in assets:
            if a.name == parsed_txn.asset_name:
                if parsed_txn.asset_type == "MF" and not a.mfapi_scheme_code:
                    self._apply_mf_scheme(a, parsed_txn.asset_identifier)
                return a

        # Create new asset
        asset_type_enum = AssetType[parsed_txn.asset_type]
        scheme_code = None
        asset_class = ASSET_CLASS_MAP.get(parsed_txn.asset_type, AssetClass.EQUITY)
        scheme_category = None
        if parsed_txn.asset_type == "MF" and parsed_txn.asset_identifier:
            lookup = lookup_by_isin(parsed_txn.asset_identifier)
            if lookup:
                scheme_code, scheme_category = lookup
                asset_class = classify_mf(scheme_category)

        return uow.assets.create(
            name=parsed_txn.asset_name,
            identifier=parsed_txn.asset_identifier or "",
            mfapi_scheme_code=scheme_code,
            scheme_category=scheme_category,
            asset_type=asset_type_enum,
            asset_class=asset_class,
            currency="USD" if parsed_txn.asset_type in ("STOCK_US", "RSU") else "INR",
            is_active=True,
        )

    def _apply_mf_scheme(self, asset: Asset, isin: str | None) -> None:
        """Backfill mfapi_scheme_code and scheme_category on an existing MF asset."""
        if not isin:
            return
        lookup = lookup_by_isin(isin)
        if not lookup:
            return
        scheme_code, scheme_category = lookup
        asset.mfapi_scheme_code = scheme_code
        if not asset.scheme_category:
            asset.scheme_category = scheme_category
            asset.asset_class = classify_mf(scheme_category)
