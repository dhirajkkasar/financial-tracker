"""ITR-1 vs ITR-2 selection. Pure, no DB.

ITR-1 (Sahaj) is available only to a **resident individual** whose total income
is up to Rs 50L, with salary + at most one house property + other income, LTCG
u/s 112A within the Rs 1.25L exemption, no special-rate gains, no foreign
assets/income, no carry-forward losses and no unlisted shares/VDA. Anything else
needs ITR-2. See spec section 6.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ITR1_LTCG_112A_LIMIT = 125_000.0
ITR1_INCOME_LIMIT = 5_000_000.0


@dataclass
class FormSelectionInput:
    """The draft facts the selector needs."""

    residential_status: str = "RES"
    total_income: float = 0.0
    ltcg_112a: float = 0.0            # gross 112A LTCG (before the exemption)
    stcg_111a: float = 0.0
    other_capital_gains: float = 0.0  # 112 / 112-slab / other CG
    house_property_count: int = 0
    has_foreign_assets: bool = False
    has_foreign_income: bool = False
    has_carry_forward_losses: bool = False
    has_unlisted_shares: bool = False
    has_crypto: bool = False
    is_huf: bool = False


@dataclass
class FormSelection:
    form: str
    reasons: list[str] = field(default_factory=list)


def select_form(inp: FormSelectionInput) -> FormSelection:
    reasons: list[str] = []

    if inp.is_huf:
        reasons.append("ITR-1 is for individuals only (HUF must file ITR-2)")
    if inp.residential_status != "RES":
        reasons.append(f"Residential status {inp.residential_status} requires ITR-2")
    if inp.total_income > ITR1_INCOME_LIMIT:
        reasons.append("Total income exceeds Rs 50L")
    if inp.has_foreign_assets:
        reasons.append("Foreign assets (Schedule FA) require ITR-2")
    if inp.has_foreign_income:
        reasons.append("Foreign income (Schedule FSI/TR) requires ITR-2")
    if inp.ltcg_112a > ITR1_LTCG_112A_LIMIT:
        reasons.append("LTCG u/s 112A exceeds the Rs 1.25L ITR-1 limit")
    if inp.stcg_111a > 0:
        reasons.append("STCG u/s 111A requires ITR-2")
    if inp.other_capital_gains > 0:
        reasons.append("Capital gains other than 112A require ITR-2")
    if inp.has_carry_forward_losses:
        reasons.append("Carry-forward of losses requires ITR-2")
    if inp.house_property_count > 1:
        reasons.append("More than one house property requires ITR-2")
    if inp.has_unlisted_shares:
        reasons.append("Unlisted shares require ITR-2")
    if inp.has_crypto:
        reasons.append("Virtual digital assets (VDA) require ITR-2")

    return FormSelection(form="ITR1" if not reasons else "ITR2", reasons=reasons)
