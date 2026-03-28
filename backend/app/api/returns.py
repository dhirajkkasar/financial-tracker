import math
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import ValidationError
from app.schemas.returns import (
    ReturnResponse, OverviewReturnsResponse, BreakdownResponse,
    AllocationResponse, GainersResponse, BulkReturnResponse,
)
from app.services.returns.strategies.registry import DefaultReturnsStrategyRegistry
from app.services.returns.portfolio_returns_service import PortfolioReturnsService

router = APIRouter(tags=["returns"])

ALLOWED_PAGE_SIZES = {10, 25, 50}


def get_portfolio_returns_service(db: Session = Depends(get_db)) -> PortfolioReturnsService:
    strategy_registry = DefaultReturnsStrategyRegistry()
    return PortfolioReturnsService(db, strategy_registry)


def _paginate(items: list, page: int, page_size: int) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 1,
    }


@router.get("/assets/{asset_id}/returns", response_model=ReturnResponse)
def get_asset_returns(asset_id: int, svc: PortfolioReturnsService = Depends(get_portfolio_returns_service)):
    return svc.get_asset_returns(asset_id)


@router.get("/returns/bulk", response_model=BulkReturnResponse)
def get_bulk_returns(
    asset_ids: str = Query(..., description="Comma-separated asset IDs"),
    svc: PortfolioReturnsService = Depends(get_portfolio_returns_service),
):
    ids = [int(i.strip()) for i in asset_ids.split(",") if i.strip()]
    results = []
    for asset_id in ids:
        try:
            results.append(svc.get_asset_returns(asset_id))
        except Exception:
            pass
    return {"returns": results}


@router.get("/assets/{asset_id}/returns/lots")
def get_asset_lots(
    asset_id: int,
    open_page: int = Query(1, ge=1),
    matched_page: int = Query(1, ge=1),
    page_size: int = Query(10),
    svc: PortfolioReturnsService = Depends(get_portfolio_returns_service),
):
    if page_size not in ALLOWED_PAGE_SIZES:
        raise ValidationError(f"page_size must be one of {sorted(ALLOWED_PAGE_SIZES)}, got {page_size}")
    result = svc.get_asset_lots(asset_id)
    return {
        "open_lots": _paginate(result["open_lots"], open_page, page_size),
        "matched_sells": _paginate(result["matched_sells"], matched_page, page_size),
    }


@router.get("/returns/breakdown", response_model=BreakdownResponse)
def get_returns_breakdown(svc: PortfolioReturnsService = Depends(get_portfolio_returns_service)):
    return svc.get_breakdown()


@router.get("/overview/allocation", response_model=AllocationResponse)
def get_overview_allocation(svc: PortfolioReturnsService = Depends(get_portfolio_returns_service)):
    return svc.get_allocation()


@router.get("/overview/gainers", response_model=GainersResponse)
def get_overview_gainers(
    n: int = Query(5, ge=1, le=20, description="Number of top gainers/losers to return"),
    svc: PortfolioReturnsService = Depends(get_portfolio_returns_service),
):
    return svc.get_gainers(n=n)


@router.get("/returns/overview", response_model=OverviewReturnsResponse)
def get_returns_overview(
    types: Optional[str] = Query(None, description="Comma-separated asset types, e.g. STOCK_IN,MF"),
    svc: PortfolioReturnsService = Depends(get_portfolio_returns_service),
):
    asset_types = [t.strip() for t in types.split(",")] if types else None
    return svc.get_overview(asset_types=asset_types)
