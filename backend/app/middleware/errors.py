"""Error hierarchy re-exports for consistent import path."""
from app.middleware.error_handler import AppError, NotFoundError, DuplicateError, ValidationError

__all__ = ["AppError", "NotFoundError", "DuplicateError", "ValidationError"]
