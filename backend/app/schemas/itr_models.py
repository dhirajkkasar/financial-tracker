"""Typed per-year ITR input document.

``ReturnInput`` is the reusable artefact persisted on ``itr_returns.input_json``:
everything the portfolio data cannot supply (identity, bank accounts, salary from
Form 16, savings/dividend income, foreign income/overrides, challans). Next
year's return is seeded by copying the fixed blocks from the prior year.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AddressIn(BaseModel):
    line1: str = ""
    line2: str = ""
    city: str = ""
    state_code: str = ""
    pin: Optional[int] = None
    country_code: str = "91"
    mobile: Optional[str] = None
    email: Optional[str] = None


class BankAccountIn(BaseModel):
    bank_name: str = ""
    account_number: str = ""
    ifsc: str = ""
    account_type: Literal["SBA", "CA", "CC", "OD", "NRO", "NRE", "OTH"] = "SBA"
    is_refund_account: bool = False


class Form16SummaryIn(BaseModel):
    """Deterministic parse of one Form 16 (one employer)."""

    employer_name: str = ""
    employer_tan: str = ""
    employer_address: str = ""
    employee_pan: str = ""
    employee_name: str = ""
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    gross_salary: float = 0.0
    exemptions_10: float = 0.0
    standard_deduction: float = 0.0
    professional_tax: float = 0.0
    perquisites: float = 0.0
    total_taxable_income: float = 0.0
    chapter_via: dict[str, float] = Field(default_factory=dict)
    tds: float = 0.0
    opted_out_115bac: bool = False
    warnings: list[str] = Field(default_factory=list)


class OtherIncomeIn(BaseModel):
    savings_interest: float = 0.0
    term_deposit_interest_override: Optional[float] = None
    other_interest: float = 0.0
    interest_on_it_refund: float = 0.0
    dividends: float = 0.0
    dividend_quarters: dict[str, float] = Field(default_factory=dict)


class ForeignIncomeIn(BaseModel):
    dividends: float = 0.0
    tax_paid_abroad: float = 0.0
    fa_asset_overrides: list[dict] = Field(default_factory=list)


class ChallanIn(BaseModel):
    bsr_code: str = ""
    date: str = ""
    serial: str = ""
    amount: float = 0.0


class ReturnInput(BaseModel):
    member_id: int
    fy_label: str
    ay_label: str
    regime: Literal["new", "old"] = "new"
    residential_status: Literal["RES", "NRI", "NOR"] = "RES"
    pan: str = ""
    name: str = ""
    dob: Optional[str] = None
    address: AddressIn = Field(default_factory=AddressIn)
    bank_accounts: list[BankAccountIn] = Field(default_factory=list)
    salary: list[Form16SummaryIn] = Field(default_factory=list)
    other_income: OtherIncomeIn = Field(default_factory=OtherIncomeIn)
    foreign: ForeignIncomeIn = Field(default_factory=ForeignIncomeIn)
    challans: list[ChallanIn] = Field(default_factory=list)
    verification: dict[str, str] = Field(default_factory=dict)
    creation: dict[str, str] = Field(default_factory=dict)
