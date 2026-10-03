"""API token authentication dependency.

Reads Authorization: Bearer <token> or X-API-Token header and compares
via hmac.compare_digest to API_TOKEN env var.

If API_TOKEN is empty or "changeme" (dev default), all requests are allowed
with a one-time warning log.
"""
import hmac
import logging
import os

from fastapi import Request
from fastapi.exceptions import HTTPException

logger = logging.getLogger(__name__)

_warned_once = False


def verify_token(request: Request):
    """FastAPI dependency: enforce API_TOKEN auth, except when unconfigured in dev."""
    global _warned_once
    expected = os.getenv("API_TOKEN", "")
    if not expected or expected == "changeme":
        if not _warned_once:
            logger.warning("API_TOKEN not configured — allowing all requests (dev mode)")
            _warned_once = True
        return None

    auth_header = request.headers.get("authorization", "")
    provided = ""
    if auth_header.lower().startswith("bearer "):
        provided = auth_header[7:].strip()
    if not provided:
        provided = request.headers.get("x-api-token", "")

    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return None
