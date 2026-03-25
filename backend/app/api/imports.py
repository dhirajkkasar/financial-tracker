from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.importers.broker_csv_parser import ZerodhaImporter
from app.importers.cas_parser import CASImporter
from app.importers.nps_csv_parser import NPSImporter
from app.middleware.error_handler import NotFoundError, ValidationError
from app.services.import_service import ImportService
from app.services.ppf_epf_import_service import PPFEPFImportService

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
    return svc.preview(result.transactions, preview_snapshots=result.snapshots)


@router.post("/commit")
def commit_import(
    body: CommitRequest,
    svc: ImportService = Depends(get_import_service),
):
    result = svc.commit(body.preview_id)
    if result is None:
        raise NotFoundError(f"Preview '{body.preview_id}' not found or expired")
    return result


@router.post("/ppf-csv")
async def import_ppf_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Import a PPF account statement CSV (SBI format).

    The PPF asset must already exist with identifier = account number.
    Credits with "INTEREST" in details → INTEREST transactions (positive inflow).
    Other credits → CONTRIBUTION transactions (negative outflow).
    A Valuation entry is created from the closing balance.

    Returns {inserted, skipped, valuation_created, valuation_value, valuation_date,
             account_number, errors}
    """
    file_bytes = await file.read()
    svc = PPFEPFImportService(db)
    return svc.import_ppf_csv(file_bytes)


@router.post("/epf-pdf")
async def import_epf_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Import an EPFO Member Passbook PDF.

    The EPF asset must already exist in the DB with identifier = member_id.
    All transactions (employee share, employer share, pension/EPS, interest, transfer)
    are imported under the single EPF asset.

    Returns {inserted, skipped, epf_valuation_created, epf_valuation_value, errors}
    """
    file_bytes = await file.read()
    svc = PPFEPFImportService(db)
    return svc.import_epf(file_bytes)
