import json as _json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from app.api.dependencies import get_import_orchestrator
from app.middleware.error_handler import ValidationError
from app.services.imports.orchestrator import ImportOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/import", tags=["import"])


def _parse_exchange_rates(exchange_rates: str) -> dict[str, float]:
    """Parse and validate the exchange_rates JSON field."""
    try:
        parsed = _json.loads(exchange_rates)
    except Exception:
        raise ValidationError('exchange_rates must be valid JSON, e.g. {"2025-03": 86.5}')
    if not isinstance(parsed, dict) or not all(isinstance(v, (int, float)) for v in parsed.values()):
        raise ValidationError('exchange_rates values must be numbers, e.g. {"2025-03": 86.5}')
    return parsed


@router.post("/preview-file")
async def preview_file_import(
    source: str = Query(..., description="Importer source: zerodha/cas/nps/ppf/epf/fidelity_rsu/fidelity_sale"),
    format: str = Query(..., description="File format: csv or pdf"),
    file: UploadFile = File(...),
    exchange_rates: str | None = Form(None, description='JSON object e.g. {"2025-03": 86.5}'),
    orchestrator: ImportOrchestrator = Depends(get_import_orchestrator),
):
    """Preview a file import using ImportOrchestrator.

    For fidelity sources, exchange_rates is required.
    """
    file_bytes = await file.read()

    importer_kwargs = {
        "filename": file.filename or "",
    }
    if source in {"fidelity_rsu", "fidelity_sale"}:
        if not exchange_rates:
            raise ValidationError("exchange_rates is required for fidelity imports")
        importer_kwargs["exchange_rates"] = _parse_exchange_rates(exchange_rates)

    try:
        response = orchestrator.preview(source, format, file_bytes, **importer_kwargs)
    except ValueError as exc:
        # Unknown importer returns 400, validation errors return 422
        error_msg = str(exc)
        if "No importer for" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)
    
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
