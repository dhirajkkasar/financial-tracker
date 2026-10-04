"""
ImportOrchestrator — coordinates preview/commit for any file import.

preview(): parse file → deduplicate → store in PreviewStore → return ImportPreviewResponse
commit():  load from store → persist transactions → run post-processors → publish event

Snapshot sources (e.g. fidelity_open holdings): commit replaces stale snapshot
rows — previously imported rows for the ticker that are absent from the new
file are pruned, so a shrunken remainder updates instead of duplicating.

Adding new post-processing: create an IPostProcessor subclass, register it in
api/dependencies.py. No changes to this file.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.importers.base import ImportResult, ParsedTransaction
from app.importers.pipeline import ImportPipeline
from app.engine.mf_classifier import classify_mf
from app.engine.mf_scheme_lookup import lookup_by_isin
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.unit_of_work import UnitOfWork
from app.schemas.responses.imports import (
    ImportPreviewResponse,
    ImportCommitResponse,
    ParsedTransactionPreview,
)
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
        pre_commit_processors: list | None = None,  # optional for backwards compat
    ):
        self._uow_factory = uow_factory
        self._pipeline = pipeline
        self._store = preview_store
        self._processors: dict[str, IPostProcessor] = {
            at: p for p in post_processors for at in p.asset_types
        }
        self._pre_commit_processors: dict[str, object] = {
            p.source: p for p in (pre_commit_processors or [])
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
        member_id: int | None = None,
        **importer_kwargs,
    ) -> ImportPreviewResponse:
        result = self._pipeline.run(source, fmt, file_bytes, **importer_kwargs)
        result.member_id = member_id  # attach for commit phase
        logger.info("ImportOrchestrator.preview: result.transactions=%d, duplicate_count=%s", len(result.transactions), getattr(result, 'duplicate_count', None))
        if result.source == "fidelity_open":
            self._warn_stale_open_lots(result, member_id, importer_kwargs)
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
        skipped = getattr(result, "duplicate_count", 0)
        errors: list[str] = []
        pruned = 0
        assets_created: dict[int, Asset] = {}
        member_id = getattr(result, "member_id", None)

        with self._uow_factory() as uow:
            # Run pre-commit processor (keyed by result.source) before any DB writes
            pre_processor = self._pre_commit_processors.get(result.source)
            if pre_processor:
                result = pre_processor.process(result, uow)

            for parsed_txn in result.transactions:
                try:
                    # Find or create the asset
                    asset = self._find_or_create_asset(parsed_txn, uow, member_id=member_id)

                    # Track created asssetsfor post-commit processing
                    assets_created[asset.id] = asset

                    # Check for duplicate (second-pass safety)
                    if uow.transactions.get_by_txn_id(parsed_txn.txn_id):
                        skipped += 1
                        continue

                    # Persist transaction
                    uow.transactions.create(
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
                except Exception as exc:
                    logger.warning("Failed to import txn %s: %s", parsed_txn.txn_id, exc)
                    errors.append(str(exc))

            # Snapshot replace (fidelity_open holdings): prune previously imported
            # remainder rows for the ticker that are absent from this snapshot.
            # Skipped when any row errored — a partial snapshot must not delete.
            if result.source == "fidelity_open" and not errors and result.transactions:
                try:
                    # Keep every row the file contained (dedup-skipped rows are
                    # unchanged holdings, not stale ones).
                    keep_ids = set(result.all_txn_ids) or {t.txn_id for t in result.transactions}
                    for stale in self._stale_open_lots(
                        uow, result.transactions[0].asset_identifier, member_id, keep_ids
                    ):
                        uow.transactions.delete(stale)
                        pruned += 1
                    if pruned:
                        logger.info("ImportOrchestrator.commit: pruned %d stale fidelity_open lot(s)", pruned)
                except Exception as exc:
                    logger.warning("Failed to prune stale fidelity_open lots: %s", exc)
                    errors.append(f"prune failed: {exc}")

            # Run post-processor for each asset type
            for _, asset in assets_created.items():
                processor = self._processors.get(asset.asset_type.value)
                if processor:
                    processor.process(asset, result, uow)

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
        return ImportCommitResponse(inserted=inserted, skipped=skipped, errors=errors, pruned=pruned)

    # ------------------------------------------------------------------
    # fidelity_open snapshot helpers
    # ------------------------------------------------------------------

    def _stale_open_lots(self, uow, ticker: str, member_id: int | None, keep_ids: set[str]) -> list:
        """Previously imported fidelity_open rows for ticker absent from keep_ids."""
        candidates: list = []
        if member_id is not None:
            candidates = [a for a in uow.assets.list(active=None, member_ids=[member_id])
                          if a.identifier == ticker]
        if not candidates:
            candidates = [a for a in uow.assets.list(active=None) if a.identifier == ticker]
        stale = []
        for asset in candidates:
            for txn in uow.transactions.list_by_asset(asset.id):
                if txn.txn_id.startswith("fidelity_open_") and txn.txn_id not in keep_ids:
                    stale.append(txn)
        return stale

    def _warn_stale_open_lots(self, result, member_id: int | None, importer_kwargs: dict) -> None:
        """Preview-time notice of snapshot rows commit would prune. Never fails."""
        try:
            import json as _json
            raw = (importer_kwargs or {}).get("user_inputs") or "{}"
            ticker = str(_json.loads(raw).get("ticker") or "").upper()
            if not ticker or not result.transactions:
                return
            with self._uow_factory() as uow:
                keep_ids = set(result.all_txn_ids) or {t.txn_id for t in result.transactions}
                stale = self._stale_open_lots(uow, ticker, member_id, keep_ids)
            if stale:
                result.warnings.append(
                    f"{len(stale)} previously imported holding lot(s) for {ticker} are absent "
                    "from this snapshot and will be removed at commit."
                )
        except Exception as exc:
            logger.warning("Stale-lot preview check failed: %s", exc)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _find_or_create_asset(self, parsed_txn: ParsedTransaction, uow: UnitOfWork, member_id: int | None = None) -> Asset:
        """Find asset by identifier or name; create if not found.

        For MF assets the scheme_code and scheme_category are resolved from the
        bundled CSV only when the asset is new or its mfapi_scheme_code is empty.

        Scoped by member_id when available: member assets are searched first,
        falling back to the global list only if no member match is found.
        """
        if parsed_txn is None:
            return None

        effective_member_id = member_id if member_id is not None else getattr(parsed_txn, "member_id", None)

        def _match(candidates: list[Asset]) -> Asset | None:
            # Match by identifier (ISIN / scheme code)
            if parsed_txn.asset_identifier:
                for a in candidates:
                    if a.identifier == parsed_txn.asset_identifier:
                        # Backfill scheme_code/category if missing on existing MF asset
                        if parsed_txn.asset_type == "MF" and not a.mfapi_scheme_code:
                            self._apply_mf_scheme(a, parsed_txn.asset_identifier)
                        return a

            # Match by name
            for a in candidates:
                if a.name == parsed_txn.asset_name:
                    if parsed_txn.asset_type == "MF" and not a.mfapi_scheme_code:
                        self._apply_mf_scheme(a, parsed_txn.asset_identifier)
                    return a
            return None

        if effective_member_id is not None:
            member_assets = uow.assets.list(active=None, member_ids=[effective_member_id])
            found = _match(member_assets)
            if found is not None:
                return found

        assets = uow.assets.list(active=None)
        found = _match(assets)
        if found is not None:
            return found

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
            member_id=effective_member_id,
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
