"""Assemble an ITR draft from portfolio gains + the per-year input document.

Pure: takes the ``ReturnInput`` and the ``TaxService.get_tax_summary`` dict and
returns a serialisable :class:`ReturnDraft`. No DB access — the ``ItrService``
orchestrates persistence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

from app.engine.itr.form_selector import FormSelectionInput, select_form
from app.engine.itr.schedule_112a import Schedule112ALot, build_schedule_112a
from app.engine.itr.tax_compute import IncomeBuckets, compute_return_tax
from app.schemas.itr_models import ReturnInput


@dataclass
class ReturnDraft:
    member_id: int
    fy_label: str
    ay_label: str
    form: str
    form_reasons: list[str]
    salary_taxable: float
    buckets: dict          # net of set-off — drives the tax computation
    gross: dict            # current-year gains/losses *before* set-off (CG schedule)
    tax: dict
    schedule_112a: dict
    setoff: dict
    carryforward: dict
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return asdict(self)


# ── Income composition ────────────────────────────────────────────────────────

def taxable_salary(inp: ReturnInput) -> float:
    """Sum the taxable salary across Form 16s (net of 10/16 deductions)."""
    total = 0.0
    for f in inp.salary:
        if f.total_taxable_income:
            total += f.total_taxable_income
        else:
            total += (
                f.gross_salary
                - f.exemptions_10
                - f.standard_deduction
                - f.professional_tax
            )
    return total


def other_interest_total(inp: ReturnInput, summary: dict) -> tuple[float, dict]:
    """Declared savings/other interest + FD/RD interest from the portfolio."""
    oi = inp.other_income
    fd_interest = 0.0
    for a in summary.get("interest", {}).get("assets", []):
        fd_interest += a.get("interest", 0.0)
    term_deposit = (
        oi.term_deposit_interest_override
        if oi.term_deposit_interest_override is not None
        else fd_interest
    )
    total = oi.savings_interest + oi.other_interest + oi.interest_on_it_refund + term_deposit
    return total, {"fd_interest": fd_interest, "term_deposit_used": term_deposit}


def _gross_gains(summary: dict) -> tuple[dict, dict, float, float]:
    """Split gross gains into rate buckets; also return current-year STCL/LTCL."""
    stcg = {"stcg_111a": 0.0, "stcg_slab": 0.0}
    ltcg = {"ltcg_112a": 0.0, "ltcg_other_12_5": 0.0}
    stcg_loss = 0.0
    ltcg_loss = 0.0

    for a in summary.get("stcg", {}).get("assets", []):
        gain = a.get("gain", 0.0)
        if gain >= 0:
            stcg["stcg_slab" if a.get("is_slab") else "stcg_111a"] += gain
        else:
            stcg_loss += -gain

    for a in summary.get("ltcg", {}).get("assets", []):
        gain = a.get("gain", 0.0)
        if gain >= 0:
            ltcg["ltcg_other_12_5" if not a.get("ltcg_exempt_eligible") else "ltcg_112a"] += gain
        else:
            ltcg_loss += -gain

    return stcg, ltcg, stcg_loss, ltcg_loss


def _absorb(pools: dict, loss: float) -> float:
    """Offset ``loss`` against the pools pro-rata; return the unused remainder."""
    total = sum(max(0.0, v) for v in pools.values())
    used = min(loss, total)
    if total > 0 and used > 0:
        factor = 1.0 - used / total
        for key in pools:
            pools[key] = max(0.0, pools[key]) * factor
    return loss - used


def _apply_setoff(stcg, ltcg, stcg_loss, ltcg_loss, cf_stcl, cf_ltcl):
    """Statutory order: current STCL -> STCG -> LTCG; LTCL -> LTCG; then b/f."""
    applied = {}

    # Current-year STCL: STCG first, then LTCG.
    rem = _absorb(stcg, stcg_loss)
    applied["stcl_on_stcg"] = stcg_loss - rem
    rem = _absorb(ltcg, rem)
    applied["stcl_on_ltcg"] = stcg_loss - applied["stcl_on_stcg"] - rem
    stcl_left = rem

    # Current-year LTCL: LTCG only.
    rem = _absorb(ltcg, ltcg_loss)
    applied["ltcl_on_ltcg"] = ltcg_loss - rem
    ltcl_left = rem

    # Brought-forward STCL: STCG first, then LTCG.
    rem = _absorb(stcg, cf_stcl)
    cf_stcl_used = cf_stcl - rem
    rem2 = _absorb(ltcg, rem)
    applied["cf_stcl_used"] = cf_stcl_used + (rem - rem2)
    cf_stcl_left = rem2

    # Brought-forward LTCL: LTCG only.
    rem = _absorb(ltcg, cf_ltcl)
    applied["cf_ltcl_used"] = cf_ltcl - rem
    cf_ltcl_left = rem

    new_cf = {"stcl": stcl_left + cf_stcl_left, "ltcl": ltcl_left + cf_ltcl_left}
    return stcg, ltcg, applied, new_cf


def _collect_112a_lots(summary: dict, warnings: list[str]) -> list[Schedule112ALot]:
    lots: list[Schedule112ALot] = []
    for a in summary.get("ltcg", {}).get("assets", []):
        if not a.get("ltcg_exempt_eligible"):
            continue
        for l in a.get("ltcg_lots", []):
            buy = date.fromisoformat(l["buy_date"])
            fmv = l.get("jan31_2018_price") or 0.0
            if buy <= date(2018, 1, 31) and not fmv:
                warnings.append(
                    f"No 31-Jan-2018 FMV for {a.get('asset_name')} lot bought {buy}; "
                    "grandfathering falls back to actual cost"
                )
            lots.append(Schedule112ALot(
                isin=a.get("isin") or "",
                name=a.get("asset_name") or "",
                units=l["units"],
                buy_date=buy,
                cost_per_unit=l["buy_price_per_unit"],
                sale_price_per_unit=l["sell_price_per_unit"],
                fmv_31jan2018_per_unit=fmv,
            ))
    return lots


def assemble_draft(inp: ReturnInput, summary: dict) -> ReturnDraft:
    warnings: list[str] = []

    salary = taxable_salary(inp)
    interest, interest_detail = other_interest_total(inp, summary)
    dividends = inp.other_income.dividends

    if not inp.salary:
        warnings.append("No Form 16 attached — salary is taken as zero")

    stcg_gross, ltcg_gross, stcg_loss, ltcg_loss = _gross_gains(summary)
    cf = summary.get("carryforward_balances", {})
    cf_stcl = sum(b["remaining_inr"] for b in cf.get("stcl", []))
    cf_ltcl = sum(b["remaining_inr"] for b in cf.get("ltcl", []))

    stcg_net, ltcg_net, applied, new_cf = _apply_setoff(
        stcg_gross, ltcg_gross, stcg_loss, ltcg_loss, cf_stcl, cf_ltcl
    )

    buckets = IncomeBuckets(
        salary=salary,
        other_interest=interest,
        dividends=dividends,
        stcg_slab=stcg_net["stcg_slab"],
        stcg_111a=stcg_net["stcg_111a"],
        ltcg_112a=ltcg_net["ltcg_112a"],
        ltcg_other_12_5=ltcg_net["ltcg_other_12_5"],
    )

    tax = compute_return_tax(buckets, inp.fy_label, regime=inp.regime)

    lots = _collect_112a_lots(summary, warnings)
    schedule = build_schedule_112a(lots)
    # Schedule 112A covers only listed-equity / equity-MF LTCG, so it must tie to
    # the 112A-eligible gains alone — not to other LTCG (property, US stock, ...).
    if lots and schedule.balance != round(ltcg_gross["ltcg_112a"]):
        warnings.append(
            "Schedule 112A total does not tie to the portfolio's 112A LTCG — review the lots"
        )

    normal_income = salary + interest + dividends + stcg_net["stcg_slab"]
    total_income = normal_income + sum(stcg_net.values()) + sum(ltcg_net.values())
    has_foreign_assets = bool(inp.foreign.fa_asset_overrides)
    has_foreign_income = bool(inp.foreign.dividends)
    sel = select_form(FormSelectionInput(
        residential_status=inp.residential_status,
        total_income=total_income,
        ltcg_112a=sum(a.get("gain", 0.0) for a in summary.get("ltcg", {}).get("assets", [])
                      if a.get("ltcg_exempt_eligible") and a.get("gain", 0.0) > 0),
        stcg_111a=stcg_gross["stcg_111a"],
        other_capital_gains=ltcg_gross["ltcg_other_12_5"] + stcg_gross["stcg_slab"],
        has_foreign_assets=has_foreign_assets,
        has_foreign_income=has_foreign_income,
        has_carry_forward_losses=bool(cf_stcl or cf_ltcl or new_cf["stcl"] or new_cf["ltcl"]),
    ))

    return ReturnDraft(
        member_id=inp.member_id,
        fy_label=inp.fy_label,
        ay_label=inp.ay_label,
        form=sel.form,
        form_reasons=sel.reasons,
        salary_taxable=salary,
        buckets=asdict(buckets),
        gross={
            **stcg_gross,
            **ltcg_gross,
            "stcg_loss": stcg_loss,
            "ltcg_loss": ltcg_loss,
        },
        tax=asdict(tax),
        schedule_112a=asdict(schedule),
        setoff=applied,
        carryforward={"brought_forward": {"stcl": cf_stcl, "ltcl": cf_ltcl},
                      "created_this_year": new_cf},
        warnings=warnings,
    )
