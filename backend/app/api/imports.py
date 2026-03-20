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


@router.post("/ppf-pdf")
async def import_ppf_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Import a PPF account statement PDF (SBI format).

    The PPF asset must already exist in the DB with identifier = stripped account number
    (leading zeros removed). Transactions are deduplicated by txn_id. A Valuation entry
    is created from the closing balance on the statement date.

    Returns {inserted, skipped, valuation_created, valuation_value, valuation_date,
             account_number, errors}
    """
    file_bytes = await file.read()
    svc = PPFEPFImportService(db)
    return svc.import_ppf(file_bytes)


@router.post("/epf-pdf")
async def import_epf_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Import an EPFO Member Passbook PDF.

    The EPF asset must already exist in the DB with identifier = member_id.
    Auto-creates an EPS sub-asset (type=EPF, identifier=member_id_EPS) if not present.
    Creates a Valuation for the EPF asset from the net balance.
    Marks the EPF asset inactive when net balance = 0.

    Returns {epf_inserted, epf_skipped, eps_inserted, eps_skipped,
             eps_asset_id, eps_asset_created, epf_valuation_created,
             epf_valuation_value, errors}
    """
    file_bytes = await file.read()
    svc = PPFEPFImportService(db)
    return svc.import_epf(file_bytes)
