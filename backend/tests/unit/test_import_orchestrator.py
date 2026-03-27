import pytest
from datetime import date
from app.importers.base import ParsedTransaction, ImportResult


def _make_txn(txn_id="t1", asset_type="STOCK_IN", txn_type="BUY", units=10.0) -> ParsedTransaction:
    return ParsedTransaction(
        source="zerodha",
        asset_name="Test Stock",
        asset_identifier="TEST",
        asset_type=asset_type,
        txn_type=txn_type,
        date=date(2024, 1, 1),
        units=units,
        amount_inr=-10000.0,
        txn_id=txn_id,
    )


def test_stock_post_processor_marks_asset_inactive_when_zero_units():
    from app.services.imports.post_processors.stock import StockPostProcessor

    class FakeAsset:
        asset_type_value = "STOCK_IN"
        is_active = True
        updates = {}

    class FakeAssetRepo:
        def update(self, asset, **kwargs):
            asset.updates.update(kwargs)

    class FakeUoW:
        def __init__(self):
            self.assets = FakeAssetRepo()

    asset = FakeAsset()
    txns_buy = [_make_txn("b1", units=10.0, txn_type="BUY")]
    txns_sell = [_make_txn("s1", units=10.0, txn_type="SELL")]

    processor = StockPostProcessor()
    processor.process(asset, txns_buy + txns_sell, FakeUoW())

    assert asset.updates.get("is_active") is False


def test_stock_post_processor_keeps_active_when_units_remain():
    from app.services.imports.post_processors.stock import StockPostProcessor

    class FakeAsset:
        asset_type_value = "STOCK_IN"
        is_active = True
        updates = {}

    class FakeAssetRepo:
        def update(self, asset, **kwargs):
            asset.updates.update(kwargs)

    class FakeUoW:
        def __init__(self):
            self.assets = FakeAssetRepo()

    asset = FakeAsset()
    txns = [_make_txn("b1", units=10.0, txn_type="BUY")]

    processor = StockPostProcessor()
    processor.process(asset, txns, FakeUoW())

    assert "is_active" not in asset.updates


def test_orchestrator_preview_returns_preview_id():
    from app.importers.pipeline import ImportPipeline
    from app.importers.registry import ImporterRegistry, register_importer
    from app.importers.base import BaseImporter, ImportResult
    from app.services.imports.deduplicator import InMemoryDeduplicator
    from app.services.imports.preview_store import PreviewStore
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.event_bus import SyncEventBus

    @register_importer
    class OrchestratorTestImporter(BaseImporter):
        source = "orch_test"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(
                source=self.source,
                transactions=[_make_txn("orch_txn_1")],
            )

    pipeline = ImportPipeline(
        registry=ImporterRegistry(),
        deduplicator=InMemoryDeduplicator(set()),
    )
    store = PreviewStore()
    bus = SyncEventBus()
    orchestrator = ImportOrchestrator(
        uow_factory=lambda: None,  # not needed for preview
        pipeline=pipeline,
        preview_store=store,
        post_processors=[],
        event_bus=bus,
    )

    response = orchestrator.preview("orch_test", "csv", b"data")
    assert response.preview_id is not None
    assert response.new_count == 1
    assert response.duplicate_count == 0
