from app.schemas.responses.common import PaginatedResponse
from app.schemas.responses.returns import (
    AssetReturnsResponse,
    LotComputedResponse,
    LotsPageResponse,
)


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
