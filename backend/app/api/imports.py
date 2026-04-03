import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from app.api.dependencies import get_import_orchestrator
from app.middleware.error_handler import ValidationError
from app.services.imports.orchestrator import ImportOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/import", tags=["import"])


@router.post("/preview-file")
async def preview_file_import(
    source: str = Query(..., description="Importer source: zerodha/cas/nps/ppf/epf/fidelity_rsu/fidelity_sale"),
    format: str = Query(..., description="File format: csv or pdf"),
    file: UploadFile = File(...),
    user_inputs: str | None = Form(None, description='JSON object e.g. {"2025-03": 86.5} for fidelity sources'),
    orchestrator: ImportOrchestrator = Depends(get_import_orchestrator),
):
    """Preview a file import using ImportOrchestrator.

    For fidelity sources, user_inputs (exchange rates) is required.
    """
    file_bytes = await file.read()

    importer_kwargs = {
        "filename": file.filename or "",
    }
    
    # Pass user_inputs as-is string if provided (will be validated by importer)
    if user_inputs:
        importer_kwargs["user_inputs"] = user_inputs

    print("user_inputs:", user_inputs)
    print("importer_kwargs:", importer_kwargs)
    try:
        response = orchestrator.preview(source, format, file_bytes, **importer_kwargs)
    except ValueError as exc:
        # Unknown importer returns 400, validation errors return 422
        error_msg = str(exc)
        if "No importer for" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)
    except ValidationError as exc:
        # Validation errors from pipeline already mapped to 422
        raise
    
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
