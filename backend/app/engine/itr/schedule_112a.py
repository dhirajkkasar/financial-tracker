"""Schedule 112A scrip-wise builder — pure, no DB.

Column meanings and relations from the official ITR-2 (AY 2026-27) schema
definition ``Schedule112A`` / ``Schedule112A115ADType`` and CBDT Validation
Rules v1.0 (rules 84-90):

  col4  NumSharesUnits
  col5  SalePricePerShareUnit
  col6  TotSaleValue        = round(col4 x col5)
  col7  AcquisitionCost     = higher(col8, col9)
  col8  CostAcqWithoutIndx  = round(col4 x actual cost/unit)
  col9  LTCGBeforelowerB1B2 = lower(col6, col11)   -- only when bought <= 31-Jan-2018
  col10 FairMktValuePerShareunit (FMV on 31-Jan-2018)
  col11 TotFairMktValueCapAst = round(col4 x col10)
  col12 ExpExclCnctTransfer (transfer expenses)
  col13 TotalDeductions     = round(col7 + col12)
  col14 Balance             = col6 - col13

Rows are split by ``ShareOnOrBefore``:
  * "BE" (bought on/before 31-Jan-2018): one row per scrip, ISIN + real name,
    grandfathering applied.
  * "AE" (bought after): ALL such sales collapse into a single row with
    ISIN "INNOTREQUIRD" and name "CONSOLIDATED" (schema pattern/maxLength), and
    cols 9/10/11 are zero.

The Rs 1.25L exemption is deliberately NOT applied here: Schedule 112A carries
the gross gain and the exemption is claimed in Schedule SI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

GRANDFATHERING_CUTOFF = date(2018, 1, 31)
_AE_ISIN = "INNOTREQUIRD"
_AE_NAME = "CONSOLIDATED"


def _inr(x: float) -> int:
    """Round to the nearest rupee, half-up (the utility's convention)."""
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _q4(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


@dataclass
class Schedule112ALot:
    """One FIFO-matched sale of a listed equity share / equity MF unit."""

    isin: str
    name: str
    units: float
    buy_date: date
    cost_per_unit: float
    sale_price_per_unit: float
    fmv_31jan2018_per_unit: float = 0.0
    transfer_expenses: float = 0.0


@dataclass
class Schedule112ARow:
    share_on_or_before: str
    isin: str
    name: str
    units: float
    sale_price_per_unit: float
    tot_sale_value: int
    cost_acq_without_indx: int
    acquisition_cost: float
    ltcg_before_lower: int
    fmv_per_unit: float
    tot_fmv: int
    exp_transfer: float
    total_deductions: int
    balance: int


@dataclass
class Schedule112A:
    rows: list[Schedule112ARow] = field(default_factory=list)
    sale_value: int = 0
    cost_acq_without_indx: int = 0
    acquisition_cost: int = 0
    ltcg_before_lower: int = 0
    tot_fmv: int = 0
    exp_transfer: int = 0
    deductions: int = 0
    balance: int = 0
    total_balance: int = 0


def _be_row(lot: Schedule112ALot) -> Schedule112ARow:
    tot_sale = _inr(lot.units * lot.sale_price_per_unit)
    cost_acq = _inr(lot.units * lot.cost_per_unit)
    tot_fmv = _inr(lot.units * lot.fmv_31jan2018_per_unit)
    lower = min(tot_sale, tot_fmv)
    acquisition_cost = float(max(cost_acq, lower))
    deductions = _inr(acquisition_cost + lot.transfer_expenses)
    return Schedule112ARow(
        share_on_or_before="BE",
        isin=lot.isin,
        name=lot.name,
        units=_q4(lot.units),
        sale_price_per_unit=_q4(lot.sale_price_per_unit),
        tot_sale_value=tot_sale,
        cost_acq_without_indx=cost_acq,
        acquisition_cost=acquisition_cost,
        ltcg_before_lower=lower,
        fmv_per_unit=_q4(lot.fmv_31jan2018_per_unit),
        tot_fmv=tot_fmv,
        exp_transfer=_q4(lot.transfer_expenses),
        total_deductions=deductions,
        balance=tot_sale - deductions,
    )


def _ae_row(lots: list[Schedule112ALot]) -> Schedule112ARow:
    units = sum(l.units for l in lots)
    tot_sale = sum(_inr(l.units * l.sale_price_per_unit) for l in lots)
    cost_acq = sum(_inr(l.units * l.cost_per_unit) for l in lots)
    expenses = sum(l.transfer_expenses for l in lots)
    deductions = _inr(cost_acq + expenses)
    price = _q4(tot_sale / units) if units else 0.0
    return Schedule112ARow(
        share_on_or_before="AE",
        isin=_AE_ISIN,
        name=_AE_NAME,
        units=_q4(units),
        sale_price_per_unit=price,
        tot_sale_value=tot_sale,
        cost_acq_without_indx=cost_acq,
        acquisition_cost=float(cost_acq),
        ltcg_before_lower=0,
        fmv_per_unit=0.0,
        tot_fmv=0,
        exp_transfer=_q4(expenses),
        total_deductions=deductions,
        balance=tot_sale - deductions,
    )


def build_schedule_112a(lots: list[Schedule112ALot]) -> Schedule112A:
    be_lots = sorted(
        (l for l in lots if l.buy_date <= GRANDFATHERING_CUTOFF),
        key=lambda l: (l.buy_date, l.isin),
    )
    ae_lots = [l for l in lots if l.buy_date > GRANDFATHERING_CUTOFF]

    rows = [_be_row(l) for l in be_lots]
    if ae_lots:
        rows.append(_ae_row(ae_lots))

    schedule = Schedule112A(rows=rows)
    schedule.sale_value = sum(r.tot_sale_value for r in rows)
    schedule.cost_acq_without_indx = sum(r.cost_acq_without_indx for r in rows)
    schedule.acquisition_cost = _inr(sum(r.acquisition_cost for r in rows))
    schedule.ltcg_before_lower = sum(r.ltcg_before_lower for r in rows)
    schedule.tot_fmv = sum(r.tot_fmv for r in rows)
    schedule.exp_transfer = _inr(sum(r.exp_transfer for r in rows))
    schedule.deductions = sum(r.total_deductions for r in rows)
    schedule.balance = sum(r.balance for r in rows)
    schedule.total_balance = schedule.balance
    return schedule
