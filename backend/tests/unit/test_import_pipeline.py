import time
import pytest
from datetime import datetime, date
from app.importers.base import ParsedTransaction, ImportResult


def _make_txn(txn_id="txn_001", asset_name="Test", asset_type="STOCK_IN") -> ParsedTransaction:
    return ParsedTransaction(
        source="zerodha",
        asset_name=asset_name,
        asset_identifier="TEST",
        asset_type=asset_type,
        txn_type="BUY",
        date=date(2024, 1, 1),
        amount_inr=-10000.0,
        txn_id=txn_id,
    )


# --- Deduplicator tests ---

def test_deduplicator_filters_known_txn_ids():
    from app.services.imports.deduplicator import InMemoryDeduplicator

    existing_ids = {"txn_001", "txn_002"}
    dedup = InMemoryDeduplicator(existing_ids)

    result = ImportResult(
        source="zerodha",
        transactions=[_make_txn("txn_001"), _make_txn("txn_003")],
    )
    filtered = dedup.filter_duplicates(result)
    assert len(filtered.transactions) == 1
    assert filtered.transactions[0].txn_id == "txn_003"
    assert filtered.duplicate_count == 1


def test_deduplicator_empty_existing_ids():
    from app.services.imports.deduplicator import InMemoryDeduplicator

    dedup = InMemoryDeduplicator(set())
    result = ImportResult(
        source="zerodha",
        transactions=[_make_txn("txn_new")],
    )
    filtered = dedup.filter_duplicates(result)
    assert len(filtered.transactions) == 1
    assert filtered.duplicate_count == 0


# --- PreviewStore tests ---

def test_preview_store_put_and_get():
    from app.services.imports.preview_store import PreviewStore

    store = PreviewStore(ttl_minutes=5)
    result = ImportResult(source="zerodha", transactions=[_make_txn()])
    preview_id = store.put(result)

    retrieved = store.get(preview_id)
    assert retrieved is not None
    assert retrieved.source == "zerodha"


def test_preview_store_get_expired_returns_none():
    from app.services.imports.preview_store import PreviewStore

    store = PreviewStore(ttl_minutes=0)  # immediate expiry
    result = ImportResult(source="zerodha", transactions=[_make_txn()])
    preview_id = store.put(result)

    time.sleep(0.01)  # allow expiry
    retrieved = store.get(preview_id)
    assert retrieved is None


def test_preview_store_get_unknown_id_returns_none():
    from app.services.imports.preview_store import PreviewStore

    store = PreviewStore()
    assert store.get("nonexistent-id") is None


def test_import_pipeline_run():
    from app.importers.pipeline import ImportPipeline
    from app.importers.registry import ImporterRegistry, register_importer
    from app.importers.base import BaseImporter, ImportResult
    from app.services.imports.deduplicator import InMemoryDeduplicator

    @register_importer
    class FakeCSVImporter(BaseImporter):
        source = "fake_pipeline_test"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
            return ImportResult(
                source=self.source,
                transactions=[_make_txn("pipeline_txn_1")],
            )

    registry = ImporterRegistry()
    dedup = InMemoryDeduplicator(set())
    pipeline = ImportPipeline(registry=registry, deduplicator=dedup)

    result = pipeline.run("fake_pipeline_test", "csv", b"data")
    assert len(result.transactions) == 1
    assert result.transactions[0].txn_id == "pipeline_txn_1"


def test_import_pipeline_deduplicates():
    from app.importers.pipeline import ImportPipeline
    from app.importers.registry import ImporterRegistry, register_importer
    from app.importers.base import BaseImporter, ImportResult
    from app.services.imports.deduplicator import InMemoryDeduplicator

    @register_importer
    class FakeCSVImporter2(BaseImporter):
        source = "fake_dedup_test"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
            return ImportResult(
                source=self.source,
                transactions=[
                    _make_txn("existing_id"),
                    _make_txn("new_id"),
                ],
            )

    registry = ImporterRegistry()
    dedup = InMemoryDeduplicator({"existing_id"})
    pipeline = ImportPipeline(registry=registry, deduplicator=dedup)

    result = pipeline.run("fake_dedup_test", "csv", b"data")
    assert len(result.transactions) == 1
    assert result.transactions[0].txn_id == "new_id"
    assert result.duplicate_count == 1
