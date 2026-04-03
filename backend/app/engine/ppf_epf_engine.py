from datetime import date
from typing import Optional
import logging

from app.middleware.error_handler import NotFoundError

logger = logging.getLogger(__name__)


def get_applicable_rate(instrument: str, on_date: date, rates: list) -> float:
    applicable = [
        r for r in rates
        if r.instrument == instrument
        and r.effective_from <= on_date
        and (r.effective_to is None or r.effective_to >= on_date)
    ]
    if not applicable:
        raise NotFoundError(f"No {instrument} rate found for {on_date}")
    # Return the most recent applicable rate
    return max(applicable, key=lambda r: r.effective_from).rate_pct


def get_latest_valuation(valuations: list) -> Optional[object]:
    if not valuations:
        return None
    return max(valuations, key=lambda v: v.date)
