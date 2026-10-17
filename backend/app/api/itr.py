import logging

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_itr_service
from app.middleware.error_handler import NotFoundError
from app.models.itr_return import ItrReturn
from app.schemas.itr import (
    ItrFiscalYearsResponse,
    ItrPrepareRequest,
    ItrReturnDetail,
    ItrReturnListResponse,
    ItrReturnSummary,
)
from app.services.itr_service import ItrService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/itr", tags=["itr"])


def _detail(record: ItrReturn, svc: ItrService) -> ItrReturnDetail:
    return ItrReturnDetail(
        id=record.id,
        member_id=record.member_id,
        fy_label=record.fy_label,
        ay_label=record.ay_label,
        form_type=record.form_type,
        status=record.status,
        schema_version=record.schema_version,
        generated_at=record.generated_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        input=svc.get_input(record.id),
    )


@router.get("/fiscal-years", response_model=ItrFiscalYearsResponse)
def get_fiscal_years(svc: ItrService = Depends(get_itr_service)):
    return ItrFiscalYearsResponse(fiscal_years=svc.get_available_fys())


@router.get("/returns", response_model=ItrReturnListResponse)
def list_returns(
    member_id: int = Query(..., description="Member ID — ITR is per-PAN"),
    svc: ItrService = Depends(get_itr_service),
):
    return ItrReturnListResponse(returns=svc.list_for_member(member_id))


@router.post("/returns", response_model=ItrReturnSummary, status_code=status.HTTP_201_CREATED)
def prepare_return(body: ItrPrepareRequest, svc: ItrService = Depends(get_itr_service)):
    return svc.prepare(member_id=body.member_id, fy_label=body.fy)


@router.get("/returns/{return_id}", response_model=ItrReturnDetail)
def get_return(return_id: int, svc: ItrService = Depends(get_itr_service)):
    record = svc.get(return_id)
    if record is None:
        raise NotFoundError(f"ITR return {return_id} not found")
    return _detail(record, svc)


@router.put("/returns/{return_id}/input", response_model=ItrReturnDetail)
def update_input(
    return_id: int, body: dict, svc: ItrService = Depends(get_itr_service)
):
    svc.update_input(return_id, body)
    record = svc.get(return_id)
    return _detail(record, svc)
