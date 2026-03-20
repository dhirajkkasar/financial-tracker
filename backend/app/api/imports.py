from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.importers.broker_csv_parser import ZerodhaImporter
from app.importers.cas_parser import CASImporter
from app.importers.nps_csv_parser import NPSImporter
from app.middleware.error_handler import NotFoundError, ValidationError
from app.services.import_service import ImportService

router = APIRouter(prefix="/import", tags=["import"])

BROKER_IMPORTERS = {
    "zerodha": ZerodhaImporter,
}


def get_import_service(db: Session = Depends(get_db)) -> ImportService:
    return ImportService(db)


class CommitRequest(BaseModel):
    preview_id: str


@router.post("/broker-csv")
async def import_broker_csv(
    broker: str = Query(..., description="Broker: zerodha"),
    file: UploadFile = File(...),
    svc: ImportService = Depends(get_import_service),
):
    if broker not in BROKER_IMPORTERS:
        raise ValidationError(f"Unknown broker '{broker}'. Supported: {sorted(BROKER_IMPORTERS)}")

    file_bytes = await file.read()
    importer = BROKER_IMPORTERS[broker]()
    result = importer.parse(file_bytes, file.filename or "")
    return svc.preview(result.transactions)


@router.post("/nps-csv")
async def import_nps_csv(
    file: UploadFile = File(...),
    svc: ImportService = Depends(get_import_service),
):
    file_bytes = await file.read()
    result = NPSImporter().parse(file_bytes, file.filename or "")
    return svc.preview(result.transactions)


@router.post("/cas-pdf")
async def import_cas_pdf(
    file: UploadFile = File(...),
    svc: ImportService = Depends(get_import_service),
):
    file_bytes = await file.read()
    result = CASImporter().parse(file_bytes, file.filename or "")
    return svc.preview(result.transactions)


@router.post("/commit")
def commit_import(
    body: CommitRequest,
    svc: ImportService = Depends(get_import_service),
):
    result = svc.commit(body.preview_id)
    if result is None:
        raise NotFoundError(f"Preview '{body.preview_id}' not found or expired")
    return result
