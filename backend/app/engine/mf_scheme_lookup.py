"""
Lazy lookup table from the bundled mf_schemes.csv.

lookup_by_isin(isin) -> (scheme_code, scheme_category) | None

CSV is read once on first call and cached for the process lifetime.
The last column contains up to two 12-char ISINs concatenated without a separator.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CSV_PATH = Path(__file__).parent.parent / "config" / "mf_scheme_codes" / "mf_schemes.csv"

_CACHE: dict[str, tuple[str, str]] | None = None


def _load() -> dict[str, tuple[str, str]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    _CACHE = {}
    try:
        with open(_CSV_PATH, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for row in reader:
                if len(row) < 10:
                    continue
                scheme_code = row[1].strip()
                scheme_category = row[4].strip()
                isin_field = row[9].strip()
                # Each ISIN is exactly 12 characters; up to 2 may be concatenated
                for i in range(0, len(isin_field), 12):
                    isin = isin_field[i:i + 12]
                    if len(isin) == 12:
                        _CACHE[isin] = (scheme_code, scheme_category)
    except Exception as e:
        logger.warning("MFSchemeLookup: failed to load %s: %s", _CSV_PATH, e)

    logger.info("MFSchemeLookup: loaded %d ISIN entries", len(_CACHE))
    return _CACHE


def lookup_by_isin(isin: str) -> Optional[tuple[str, str]]:
    """Return (scheme_code, scheme_category) for the given ISIN, or None if not found."""
    if not isin:
        return None
    return _load().get(isin)
