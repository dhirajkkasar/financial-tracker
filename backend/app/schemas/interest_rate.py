from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.interest_rate import InstrumentType


class InterestRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instrument: InstrumentType
    rate_pct: float
    effective_from: date
    effective_to: Optional[date] = None
    fy_label: str
    source: str = "Ministry of Finance / EPFO"
