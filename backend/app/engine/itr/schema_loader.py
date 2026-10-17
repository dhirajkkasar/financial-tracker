"""Locate and load the bundled official ITR JSON schemas.

The CBDT publishes a JSON Schema per assessment year and form. We bundle it once
(offline thereafter) under ``app/config/itr_schemas/AY<ay>/``. A builder must
never emit unvalidated output, so a missing schema raises loudly rather than
falling back to "best effort".
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "config" / "itr_schemas"


class MissingItrSchemaError(FileNotFoundError):
    """The official schema for this AY/form is not bundled."""


def schema_dir(ay_label: str) -> Path:
    return SCHEMA_ROOT / f"AY{ay_label}"


def _version_key(path: Path) -> tuple[int, int]:
    m = re.search(r"_V(\d+)\.(\d+)\.json$", path.name)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def schema_path(ay_label: str, form: str = "ITR-2") -> Path:
    """The newest bundled schema file for ``form`` in this AY. Raises if absent."""
    directory = schema_dir(ay_label)
    if not directory.is_dir():
        raise MissingItrSchemaError(
            f"No ITR schema directory for AY {ay_label}: {directory}"
        )
    matches = list(directory.glob(f"{form}_*.json"))
    if not matches:
        raise MissingItrSchemaError(
            f"No bundled {form} schema for AY {ay_label} in {directory}"
        )
    return max(matches, key=_version_key)


def schema_version(ay_label: str, form: str = "ITR-2") -> str:
    """The pinned schema version, e.g. ``V1.2``, read from the bundled filename."""
    m = re.search(r"_V(\d+\.\d+)\.json$", schema_path(ay_label, form).name)
    return f"V{m.group(1)}" if m else "unknown"


@lru_cache(maxsize=None)
def load_itr_schema(ay_label: str, form: str = "ITR-2") -> dict:
    """Load (and cache) the bundled schema document for this AY/form."""
    path = schema_path(ay_label, form)
    try:
        with path.open() as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:  # pragma: no cover - bundled file is trusted
        raise MissingItrSchemaError(f"Bundled schema {path} is not valid JSON") from exc
