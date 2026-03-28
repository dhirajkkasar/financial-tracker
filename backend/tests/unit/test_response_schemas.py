from app.schemas.responses.common import PaginatedResponse
from app.schemas.responses.returns import (
    AssetReturnsResponse,
    LotComputedResponse,
    LotsPageResponse,
)
from app.schemas.responses.tax import (
    TaxGainEntry,
    TaxSummaryResponse,
    HarvestOpportunityEntry,
    UnrealisedGainEntry,
)
from app.schemas.responses.imports import (
    ImportPreviewResponse,
    ImportCommitResponse,
    ParsedTransactionPreview,
)
from app.schemas.responses.prices import PriceRefreshResponse, AssetPriceEntry


def test_paginated_response_instantiation():
    r = PaginatedResponse[str](items=["a", "b"], total=10, page=1, size=2)
    assert r.items == ["a", "b"]
    assert r.total == 10
    assert r.page == 1
    assert r.size == 2


def test_paginated_response_empty():
    r = PaginatedResponse[int](items=[], total=0, page=1, size=20)
    assert r.items == []
    assert r.total == 0


def test_asset_returns_response_defaults():
    r = AssetReturnsResponse(
        asset_id=1,
        asset_name="HDFC MF",
        asset_type="MF",
        is_active=True,
    )
    assert r.asset_id == 1
    assert r.invested is None
    assert r.xirr is None


def test_lots_page_response():
    lot = LotComputedResponse(
        lot_id="lot_001",
        buy_date="2023-01-15",
        units=10.0,
        buy_price_per_unit=100.0,
        buy_amount_inr=1000.0,
        current_price=120.0,
        current_value=1200.0,
        holding_days=365,
        is_short_term=False,
        unrealised_gain=200.0,
        unrealised_gain_pct=20.0,
    )
    page = LotsPageResponse(items=[lot], total=1, page=1, size=20)
    assert page.total == 1
    assert page.items[0].lot_id == "lot_001"


def test_tax_summary_response():
    entry = TaxGainEntry(
        category="Equity",
        asset_types=["STOCK_IN", "MF"],
        st_gain=5000.0,
        lt_gain=20000.0,
        st_tax=1000.0,
        lt_tax=None,
        is_st_slab=False,
        is_lt_slab=False,
        ltcg_exemption_used=12500.0,
    )
    resp = TaxSummaryResponse(fy="2024-25", entries=[entry], total_estimated_tax=1000.0)
    assert resp.fy == "2024-25"
    assert len(resp.entries) == 1


def test_harvest_opportunity_entry():
    e = HarvestOpportunityEntry(
        asset_id=1,
        asset_name="Test Stock",
        asset_type="STOCK_IN",
        lot_id="lot_001",
        buy_date="2023-01-01",
        units=10.0,
        unrealised_loss=500.0,
        is_short_term=True,
    )
    assert e.unrealised_loss == 500.0


def test_import_preview_response():
    r = ImportPreviewResponse(
        preview_id="abc-123",
        new_count=5,
        duplicate_count=2,
        transactions=[],
    )
    assert r.preview_id == "abc-123"
    assert r.new_count == 5


def test_import_commit_response():
    r = ImportCommitResponse(inserted=5, skipped=2, errors=[])
    assert r.inserted == 5


def test_price_refresh_response():
    r = PriceRefreshResponse(refreshed=10, failed=1, stale=2)
    assert r.refreshed == 10
