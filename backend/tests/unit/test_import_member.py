import pytest
from unittest.mock import MagicMock
from app.services.imports.orchestrator import ImportOrchestrator
from app.importers.base import ParsedTransaction
from datetime import date


def test_find_or_create_asset_uses_member_id():
    """New assets created during import should carry the member_id from preview."""
    uow = MagicMock()
    uow.assets.list.return_value = []  # no existing assets

    mock_create = MagicMock()
    mock_create.return_value = MagicMock(id=1, asset_type=MagicMock(value="STOCK_IN"))
    uow.assets.create = mock_create

    orchestrator = ImportOrchestrator(
        uow_factory=MagicMock(),
        pipeline=MagicMock(),
        preview_store=MagicMock(),
        post_processors=[],
        event_bus=MagicMock(),
    )

    parsed_txn = ParsedTransaction(
        source="zerodha",
        txn_id="test-1",
        asset_name="Test Stock",
        asset_type="STOCK_IN",
        txn_type="BUY",
        date=date(2026, 1, 1),
        amount_inr=-10000.0,
        asset_identifier="INE001A01036",
    )

    orchestrator._find_or_create_asset(parsed_txn, uow, member_id=42)
    _, kwargs = mock_create.call_args
    assert kwargs["member_id"] == 42
