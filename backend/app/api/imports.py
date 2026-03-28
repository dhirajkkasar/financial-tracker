import json as _json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_import_orchestrator
from app.database import get_db
from app.importers.zerodha_importer import ZerodhaImporter
from app.importers.cas_importer import CASImporter
from app.services.imports.orchestrator import ImportOrchestrator
from app.importers.fidelity_pdf_importer import FidelityPDFImporter
from app.importers.fidelity_rsu_csv_importer import FidelityRSUImporter
from app.importers.nps_csv_importer import NPSImporter
from app.middleware.error_handler import NotFoundError, ValidationError
from app.models.asset import AssetType
from app.services.import_service import ImportService
from app.services.ppf_epf_import_service import PPFEPFImportService
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)

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
    db: Session = Depends(get_db),
    svc: ImportService = Depends(get_import_service),
):
    result = svc.commit(body.preview_id)
    if result is None:
        raise NotFoundError(f"Preview '{body.preview_id}' not found or expired")

    # Trigger NPS price refresh after import
    if "NPS" in result.get("asset_types", []):
        try:
            nps_refresh = PriceService(db).refresh_by_type(AssetType.NPS)
            result["nps_refresh"] = nps_refresh
        except Exception as e:
            logger.warning("NPS price refresh failed after import: %s", e)

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


def _parse_exchange_rates(exchange_rates: str) -> dict[str, float]:
    """Parse and validate the exchange_rates JSON form field."""
    try:
        parsed = _json.loads(exchange_rates)
    except Exception:
        raise ValidationError('exchange_rates must be valid JSON, e.g. {"2025-03": 86.5}')
    if not all(isinstance(v, (int, float)) for v in parsed.values()):
        raise ValidationError('exchange_rates values must be numbers, e.g. {"2025-03": 86.5}')
    return parsed


def _fidelity_preview(
    parser_cls,
    file_bytes: bytes,
    filename: str,
    rates: dict[str, float],
    svc: ImportService,
):
    """Shared preview logic for Fidelity RSU CSV and sale PDF endpoints.

    Steps:
    1. Validate that all required month-years are covered by rates.
    2. Parse the file via parser_cls(exchange_rates=rates).
    3. Raise ValidationError if parsing failed entirely; otherwise return preview.
    """
    required = parser_cls.extract_required_month_years(file_bytes)
    missing = [m for m in required if m not in rates]
    if missing:
        raise ValidationError(
            f"Missing exchange rates for month(s): {', '.join(missing)}. "
            f"Provide USD/INR rate for each."
        )

    result = parser_cls(exchange_rates=rates).parse(file_bytes, filename)
    if result.errors and not result.transactions:
        raise ValidationError(f"Parse failed: {'; '.join(result.errors)}")
    return svc.preview(transactions=result.transactions)


@router.post("/fidelity-rsu-csv")
async def import_fidelity_rsu_csv(
    file: UploadFile = File(...),
    exchange_rates: str = Form(..., description='JSON object e.g. {"2025-03": 86.5}'),
    svc: ImportService = Depends(get_import_service),
):
    """Import Fidelity RSU holding CSV. Filename must be MARKET_TICKER.csv.
    exchange_rates: JSON string mapping 'YYYY-MM' to USD/INR float.
    Returns 422 if any vest month-year is missing from exchange_rates.
    Returns preview_id for use with POST /import/commit.
    """
    rates = _parse_exchange_rates(exchange_rates)
    file_bytes = await file.read()
    return _fidelity_preview(FidelityRSUImporter, file_bytes, file.filename or "", rates, svc)


@router.post("/fidelity-sale-pdf")
async def import_fidelity_sale_pdf(
    file: UploadFile = File(...),
    exchange_rates: str = Form(..., description='JSON object e.g. {"2025-03": 86.0}'),
    svc: ImportService = Depends(get_import_service),
):
    """Import Fidelity tax-cover SELL transactions from a transaction summary PDF.
    exchange_rates: JSON string mapping 'YYYY-MM' to USD/INR float (use RBI monthly average).
    Returns 422 if any sale month-year is missing from exchange_rates.
    Returns preview_id for use with POST /import/commit.
    SELL transactions are tagged 'Tax cover sale' in notes for tax-page visibility.
    """
    rates = _parse_exchange_rates(exchange_rates)
    file_bytes = await file.read()
    return _fidelity_preview(FidelityPDFImporter, file_bytes, file.filename or "", rates, svc)


# ---------------------------------------------------------------------------
# New orchestrator-based endpoints (Plan 3)
# ---------------------------------------------------------------------------

@router.post("/preview-file")
async def preview_file_import(
    source: str,
    format: str,
    file: UploadFile = File(...),
    orchestrator: ImportOrchestrator = Depends(get_import_orchestrator),
):
    """Preview a file import using the new ImportOrchestrator pipeline.

    source: e.g. 'zerodha', 'cas', 'nps', 'ppf', 'epf', 'fidelity_sale', 'fidelity_rsu'
    format: 'csv' or 'pdf'
    """
    file_bytes = await file.read()
    try:
        response = orchestrator.preview(source, format, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return response


@router.post("/commit-file/{preview_id}")
def commit_file_import(
    preview_id: str,
    orchestrator: ImportOrchestrator = Depends(get_import_orchestrator),
):
    """Commit a previously previewed file import."""
    response = orchestrator.commit(preview_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Preview not found or expired")
    return response
