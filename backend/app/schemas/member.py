import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


class MemberCreate(BaseModel):
    pan: str
    name: str

    @field_validator("pan")
    @classmethod
    def validate_pan(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", v):
            raise ValueError("Invalid PAN format. Expected: ABCDE1234F")
        return v


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pan: str
    name: str
    is_default: bool
    created_at: datetime
