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

        def parse(self, file_bytes: bytes, filename: str = "") -> ImportResult:
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


def _make_context_manager_uow(existing_assets=None, existing_txn=None):
    """Build a fake UoW that works as a context manager."""
    class FakeAssetRepo:
        def __init__(self, assets):
            self._assets = assets or []
            self.created = []

        def list(self, active=None):
            return self._assets

        def create(self, **kwargs):
            from unittest.mock import MagicMock
            a = MagicMock()
            a.id = 99
            for k, v in kwargs.items():
                setattr(a, k, v)
            self.created.append(a)
            return a

    class FakeTxnRepo:
        def __init__(self, existing_txn=None):
            self._existing = existing_txn
            self.created = []

        def get_by_txn_id(self, txn_id):
            return self._existing

        def create(self, **kwargs):
            from unittest.mock import MagicMock
            t = MagicMock()
            t.id = 1
            for k, v in kwargs.items():
                setattr(t, k, v)
            self.created.append(t)
            return t

    class FakeUoW:
        def __init__(self, assets=None, existing_txn=None):
            self.assets = FakeAssetRepo(assets or [])
            self.transactions = FakeTxnRepo(existing_txn)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    return FakeUoW(assets=existing_assets, existing_txn=existing_txn)


def test_commit_returns_none_for_unknown_preview_id():
    from app.services.imports.preview_store import PreviewStore
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.event_bus import SyncEventBus

    store = PreviewStore()
    bus = SyncEventBus()
    orch = ImportOrchestrator(
        uow_factory=lambda: _make_context_manager_uow(),
        pipeline=None,
        preview_store=store,
        post_processors=[],
        event_bus=bus,
    )
    result = orch.commit("nonexistent-preview-id")
    assert result is None


def test_commit_inserts_transactions():
    from app.importers.base import ParsedTransaction, ImportResult
    from app.services.imports.preview_store import PreviewStore
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.event_bus import SyncEventBus

    txn = ParsedTransaction(
        source="zerodha",
        asset_name="Test Stock",
        asset_identifier="TEST",
        asset_type="STOCK_IN",
        txn_type="BUY",
        date=date(2024, 1, 1),
        units=10.0,
        amount_inr=-10000.0,
        txn_id="commit_test_001",
    )
    result = ImportResult(source="zerodha", transactions=[txn])

    store = PreviewStore()
    pid = store.put(result)
    bus = SyncEventBus()
    orch = ImportOrchestrator(
        uow_factory=lambda: _make_context_manager_uow(),
        pipeline=None,
        preview_store=store,
        post_processors=[],
        event_bus=bus,
    )
    response = orch.commit(pid)
    assert response is not None
    assert response.inserted == 1
    assert response.skipped == 0
    assert response.errors == []


def test_commit_skips_duplicate_transaction():
    from unittest.mock import MagicMock
    from app.importers.base import ParsedTransaction, ImportResult
    from app.services.imports.preview_store import PreviewStore
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.event_bus import SyncEventBus

    txn = ParsedTransaction(
        source="zerodha",
        asset_name="Test Stock",
        asset_identifier="TEST",
        asset_type="STOCK_IN",
        txn_type="BUY",
        date=date(2024, 1, 1),
        units=10.0,
        amount_inr=-10000.0,
        txn_id="dup_txn_001",
    )
    result = ImportResult(source="zerodha", transactions=[txn])

    store = PreviewStore()
    pid = store.put(result)
    bus = SyncEventBus()

    # Simulate existing transaction (duplicate)
    existing = MagicMock()
    orch = ImportOrchestrator(
        uow_factory=lambda: _make_context_manager_uow(existing_txn=existing),
        pipeline=None,
        preview_store=store,
        post_processors=[],
        event_bus=bus,
    )
    response = orch.commit(pid)
    assert response.inserted == 0
    assert response.skipped == 1


def test_commit_publishes_event_when_inserted():
    from app.importers.base import ParsedTransaction, ImportResult
    from app.services.imports.preview_store import PreviewStore
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.event_bus import SyncEventBus, ImportCompletedEvent

    published = []

    class TrackingBus(SyncEventBus):
        def publish(self, event):
            published.append(event)

    txn = ParsedTransaction(
        source="zerodha",
        asset_name="Event Test Stock",
        asset_identifier="EVT",
        asset_type="STOCK_IN",
        txn_type="BUY",
        date=date(2024, 1, 1),
        units=5.0,
        amount_inr=-5000.0,
        txn_id="event_test_001",
    )
    result = ImportResult(source="zerodha", transactions=[txn])

    store = PreviewStore()
    pid = store.put(result)

    orch = ImportOrchestrator(
        uow_factory=lambda: _make_context_manager_uow(),
        pipeline=None,
        preview_store=store,
        post_processors=[],
        event_bus=TrackingBus(),
    )
    response = orch.commit(pid)
    assert response.inserted == 1
    assert len(published) == 1
    assert isinstance(published[0], ImportCompletedEvent)


def test_commit_deletes_preview_after_commit():
    from app.importers.base import ParsedTransaction, ImportResult
    from app.services.imports.preview_store import PreviewStore
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.event_bus import SyncEventBus

    txn = ParsedTransaction(
        source="zerodha",
        asset_name="Del Test",
        asset_identifier="DEL",
        asset_type="STOCK_IN",
        txn_type="BUY",
        date=date(2024, 1, 1),
        units=1.0,
        amount_inr=-1000.0,
        txn_id="del_test_001",
    )
    result = ImportResult(source="zerodha", transactions=[txn])
    store = PreviewStore()
    pid = store.put(result)
    bus = SyncEventBus()
    orch = ImportOrchestrator(
        uow_factory=lambda: _make_context_manager_uow(),
        pipeline=None,
        preview_store=store,
        post_processors=[],
        event_bus=bus,
    )
    orch.commit(pid)
    # After commit, preview should be deleted
    assert store.get(pid) is None


def test_find_or_create_asset_matches_by_identifier():
    from unittest.mock import MagicMock
    from app.importers.base import ParsedTransaction
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.imports.preview_store import PreviewStore
    from app.services.event_bus import SyncEventBus

    # Setup: existing asset with matching identifier
    existing_asset = MagicMock()
    existing_asset.id = 5
    existing_asset.identifier = "ISIN123"
    existing_asset.name = "Existing Fund"

    parsed_txn = ParsedTransaction(
        source="cas",
        asset_name="Existing Fund",
        asset_identifier="ISIN123",
        asset_type="MF",
        txn_type="SIP",
        date=date(2024, 1, 1),
        units=10.0,
        amount_inr=-1000.0,
        txn_id="isin_test_001",
    )

    uow = _make_context_manager_uow(existing_assets=[existing_asset])

    orch = ImportOrchestrator(
        uow_factory=lambda: uow,
        pipeline=None,
        preview_store=PreviewStore(),
        post_processors=[],
        event_bus=SyncEventBus(),
    )
    # Call _find_or_create_asset directly
    with uow as u:
        result = orch._find_or_create_asset(parsed_txn, u)
    assert result.id == 5  # found by identifier, not created


def test_find_or_create_asset_creates_new_when_not_found():
    from app.importers.base import ParsedTransaction
    from app.services.imports.orchestrator import ImportOrchestrator
    from app.services.imports.preview_store import PreviewStore
    from app.services.event_bus import SyncEventBus

    parsed_txn = ParsedTransaction(
        source="zerodha",
        asset_name="Brand New Stock",
        asset_identifier="NEWSTOCK",
        asset_type="STOCK_IN",
        txn_type="BUY",
        date=date(2024, 1, 1),
        units=10.0,
        amount_inr=-10000.0,
        txn_id="new_asset_001",
    )

    uow = _make_context_manager_uow(existing_assets=[])

    orch = ImportOrchestrator(
        uow_factory=lambda: uow,
        pipeline=None,
        preview_store=PreviewStore(),
        post_processors=[],
        event_bus=SyncEventBus(),
    )
    with uow as u:
        result = orch._find_or_create_asset(parsed_txn, u)
    assert result is not None
    assert len(uow.assets.created) == 1
