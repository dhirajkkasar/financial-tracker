from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base application error."""
    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, code: str = None):
        self.message = message
        if code:
            self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class DuplicateError(AppError):
    status_code = 409
    code = "DUPLICATE"


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("AppError: %s %s", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    message = "; ".join(
        f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors
    )
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )
