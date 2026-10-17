"""Validate a built ITR JSON document before it is written out.

Two layers, both must pass:

1. **Structural** — ``jsonschema.Draft4Validator`` against the bundled official
   schema (draft-04). The schema already rejects camelCase keys, missing required
   branches and bad enums/patterns.
2. **Semantic** — the tie-outs the schema cannot express (CBDT Validation Rules
   v1.0). We encode the ones the builder can violate today; more can be added as
   later phases populate more schedules.

A builder must never emit a document that fails here — the generator refuses to
write output when :attr:`ValidationReport.ok` is false.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft4Validator

from app.engine.itr.schema_loader import load_itr_schema

# (schedule, total key, row containers) — a non-zero total must have rows.
_ITEMISED = (
    ("ScheduleS", "TotIncUnderHeadSalaries", ("Salaries",)),
    ("Schedule112A", "Balance112A", ("Schedule112ADtls",)),
    ("ScheduleSI", "TotSplRateInc", ("SplCodeRateTax",)),
)

_CG_ROW_CONTAINERS = (
    ("ShortTermCapGainFor23", ("EquityMFonSTT", "SaleOnOtherAssets", "SaleofLandBuild")),
    ("LongTermCapGain23", ("SaleOfEquityShareUs112A", "SaleofAssetNADtls", "SaleofLandBuild")),
)


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str
    rule: str = "schema"


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, path: str, message: str, rule: str = "semantic") -> None:
        self.issues.append(ValidationIssue(path=path, message=message, rule=rule))

    def render(self) -> str:
        return "\n".join(f"[{i.rule}] {i.path}: {i.message}" for i in self.issues)


def validate_itr_json(doc: dict, ay_label: str, form: str = "ITR-2") -> ValidationReport:
    """Validate ``doc`` against the bundled schema + the semantic tie-out rules."""
    report = ValidationReport()
    schema = load_itr_schema(ay_label, form)
    for error in sorted(Draft4Validator(schema).iter_errors(doc), key=lambda e: list(e.path)):
        report.add(
            path="/".join(str(p) for p in error.absolute_path),
            message=error.message,
            rule="schema",
        )

    body = (doc.get("ITR") or {}).get("ITR2")
    if isinstance(body, dict):
        _audit_itemisation(body, report)
        _check_cg_112a_tie(body, report)          # rule 134
        _check_cfl_bfla_tie(body, report)         # rules 234/235
        _check_schedule_fa(body, report)          # rule 746
    return report


# ── Semantic checks ───────────────────────────────────────────────────────────

def _num(node: dict, *keys: str) -> float:
    value: Any = node
    for key in keys:
        if not isinstance(value, dict):
            return 0.0
        value = value.get(key, 0)
    return float(value or 0)


def _audit_itemisation(body: dict, report: ValidationReport) -> None:
    """A schedule must not carry a total without its itemised rows."""
    for schedule_name, total_key, row_keys in _ITEMISED:
        schedule = body.get(schedule_name)
        if not isinstance(schedule, dict):
            continue
        total = _num(schedule, total_key)
        if total and not any(schedule.get(k) for k in row_keys):
            report.add(
                f"{schedule_name}.{total_key}",
                f"total {total:g} but no itemised rows ({', '.join(row_keys)})",
            )

    cg = body.get("ScheduleCGFor23")
    if isinstance(cg, dict) and _num(cg, "SumOfCGIncm"):
        for sub, row_keys in _CG_ROW_CONTAINERS:
            if any(cg.get(sub, {}).get(k) for k in row_keys):
                return
        report.add(
            "ScheduleCGFor23.SumOfCGIncm",
            f"total {_num(cg, 'SumOfCGIncm'):g} but no itemised capital-gain rows",
        )


def _check_cg_112a_tie(body: dict, report: ValidationReport) -> None:
    """Rule 134: CG B3a must equal the Schedule 112A column-14 total."""
    s112a = body.get("Schedule112A")
    if not isinstance(s112a, dict):
        return
    b3a = _num(body, "ScheduleCGFor23", "LongTermCapGain23", "SaleOfEquityShareUs112A", "BalanceCG")
    total = _num(s112a, "TotalBalance112A") or _num(s112a, "Balance112A")
    if b3a != total:
        report.add(
            "ScheduleCGFor23.LongTermCapGain23.SaleOfEquityShareUs112A.BalanceCG",
            f"CG B3a {b3a:g} does not tie to Schedule 112A total {total:g} (rule 134)",
        )


def _check_cfl_bfla_tie(body: dict, report: ValidationReport) -> None:
    """Rules 234/235: brought-forward losses in CFL must tie to Schedule BFLA."""
    cfl = body.get("ScheduleCFL")
    if not isinstance(cfl, dict):
        return
    cfl_bf = _sum_losses(cfl.get("TotalOfBFLossesEarlierYrs"))
    bfla = body.get("ScheduleBFLA")
    bfla_setoff = _sum_losses(bfla.get("TotalBFLossSetOff")) if isinstance(bfla, dict) else 0
    if cfl_bf != bfla_setoff:
        report.add(
            "ScheduleCFL.TotalOfBFLossesEarlierYrs",
            f"brought-forward losses {cfl_bf:g} do not tie to Schedule BFLA set-off "
            f"{bfla_setoff:g} (rules 234/235)",
        )


def _sum_losses(node: Any) -> float:
    detail = node.get("LossSummaryDetail") if isinstance(node, dict) else None
    if not isinstance(detail, dict):
        return 0.0
    return sum(float(v or 0) for v in detail.values())


def _check_schedule_fa(body: dict, report: ValidationReport) -> None:
    """Rule 746: Schedule FA is required when any asset is held outside India."""
    flag_value = (body.get("PartB_TTI") or {}).get("AssetOutIndiaFlag")
    if flag_value == "YES" and "ScheduleFA" not in body:
        report.add("PartB_TTI.AssetOutIndiaFlag", "AssetOutIndiaFlag=YES but ScheduleFA is absent")
