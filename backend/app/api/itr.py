import json
import logging

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.api.dependencies import get_itr_json_service, get_itr_service
from app.engine.itr.schema_loader import schema_version
from app.engine.itr.schema_validation import validate_itr_json
from app.middleware.error_handler import NotFoundError
from app.models.itr_return import ItrReturn
from app.schemas.itr import (
    ItrDraftResponse,
    ItrFiscalYearsResponse,
    ItrForm16UploadResponse,
    ItrPrepareRequest,
    ItrReturnDetail,
    ItrReturnListResponse,
    ItrReturnSummary,
    ItrValidationResponse,
)
from app.services.itr_json_service import ItrJsonService
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


@router.post("/returns/{return_id}/form16", response_model=ItrForm16UploadResponse)
async def upload_form16(
    return_id: int,
    file: UploadFile = File(...),
    svc: ItrService = Depends(get_itr_service),
):
    """Parse a Form 16 PDF and merge it into this return's salary entries."""
    data = await file.read()
    inp, warnings = svc.attach_form16(return_id, data)
    return ItrForm16UploadResponse(input=inp, warnings=warnings)


@router.post("/returns/{return_id}/assemble", response_model=ItrDraftResponse)
def assemble_return(return_id: int, svc: ItrService = Depends(get_itr_service)):
    """Assemble the ITR draft (gains + input) and persist it on the return."""
    return svc.assemble(return_id).to_json_dict()


@router.get("/returns/{return_id}/validation", response_model=ItrValidationResponse)
def validate_return(return_id: int, svc: ItrJsonService = Depends(get_itr_json_service)):
    """Validate the current draft against the official schema + tie-out rules."""
    doc, form, ay = svc.build_document(return_id)
    report = validate_itr_json(doc, ay, form)
    return ItrValidationResponse(
        ok=report.ok,
        form=form,
        schema_version=schema_version(ay, form),
        issues=[i.__dict__ for i in report.issues],
    )


@router.post("/returns/{return_id}/generate", response_model=ItrReturnSummary)
def generate_return(
    return_id: int,
    svc: ItrJsonService = Depends(get_itr_json_service),
    itr: ItrService = Depends(get_itr_service),
):
    """Build + validate the ITR JSON and persist it. 422 (with paths) if invalid."""
    svc.generate(return_id)
    return itr.get(return_id)


@router.get("/returns/{return_id}/json")
def download_json(return_id: int, svc: ItrJsonService = Depends(get_itr_json_service)):
    """Download the generated ITR JSON — import it into the Common Offline Utility."""
    record = svc.get_record(return_id)
    document = svc.get_output(return_id)
    filename = f"ITR-{record.ay_label}-{return_id}.json"
    return Response(
        content=json.dumps(document, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Import-With": "Common Offline Utility (offline import; not a portal upload)",
        },
    )
