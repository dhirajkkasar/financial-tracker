from app.schemas.responses.common import PaginatedResponse
from app.schemas.responses.returns import (
    AssetReturnsResponse,
    LotComputedResponse,
    LotsPageResponse,
)
from app.schemas.responses.tax import (
    TaxSummaryResponse,
    StcgSection,
    LtcgSection,
    InterestSection,
    StcgAssetEntry,
    LtcgAssetEntry,
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
    stcg_asset = StcgAssetEntry(
        asset_id=1,
        asset_name="HDFC Equity Fund",
        asset_type="MF",
        gain=5000.0,
        tax_estimate=1000.0,
        is_slab=False,
        tax_rate_pct=20.0,
    )
    ltcg_asset = LtcgAssetEntry(
        asset_id=1,
        asset_name="HDFC Equity Fund",
        asset_type="MF",
        gain=20000.0,
        tax_estimate=0.0,
        is_slab=False,
        tax_rate_pct=12.5,
        ltcg_exempt_eligible=True,
    )
    resp = TaxSummaryResponse(
        fy="2024-25",
        stcg=StcgSection(total_gain=5000.0, total_tax=1000.0, assets=[stcg_asset]),
        ltcg=LtcgSection(total_gain=20000.0, total_tax=0.0, ltcg_exemption_used=12500.0, assets=[ltcg_asset]),
    )
    assert resp.fy == "2024-25"
    assert len(resp.stcg.assets) == 1
    assert len(resp.ltcg.assets) == 1
    assert resp.ltcg.ltcg_exemption_used == 12500.0


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
