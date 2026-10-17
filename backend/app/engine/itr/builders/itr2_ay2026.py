"""ITR-2 builder for AY 2026-27 (FY 2025-26), new regime.

Starts from the schema-derived skeleton (all required branches present, zeroed)
and overlays the assembled draft + the per-year input document. See
``common.py`` for why the skeleton is generated rather than hand-written.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.engine.itr.builders.base import ItrBuilder, register_builder
from app.engine.itr.builders.common import build_skeleton, deref, template
from app.engine.itr.schema_loader import load_itr_schema
from app.schemas.itr_models import ReturnInput
from app.services.itr_assembler import ReturnDraft

FORM_KEY = "ITR2"


@register_builder
class Itr2BuilderAY2026(ItrBuilder):
    form = "ITR-2"
    ay_label = "2026-27"
    assessment_year = "2026"
    schema_ver = "Ver1.0"      # literal in the schema ("Ver1.0"), despite the V1.2 file name
    form_ver = "Ver1.0"
    filing_due_date = "2026-07-31"
    sw_created_by = "SW00000000"

    # Optional schedules this builder populates (they are not in ITR2.required).
    EXTRA_SCHEDULES = (
        "ScheduleS",
        "ScheduleOS",
        "ScheduleCGFor23",
        "Schedule112A",
        "ScheduleSI",
        "ScheduleCFL",
    )

    # ── entry point ───────────────────────────────────────────────────────────

    def build(
        self,
        draft: ReturnDraft,
        input_doc: ReturnInput,
        *,
        generated_on: Optional[date] = None,
    ) -> dict:
        self._schema = load_itr_schema(self.ay_label, self.form)
        doc = build_skeleton(self._schema, FORM_KEY, self.EXTRA_SCHEDULES)
        body = doc["ITR"][FORM_KEY]

        self._creation_info(body, generated_on)
        self._form(body)
        self._part_a(body, input_doc)
        self._schedule_s(body, input_doc)
        self._schedule_os(body, input_doc)
        self._verification(body, input_doc)
        return doc

    # ── helpers ───────────────────────────────────────────────────────────────

    def _def(self, name: str) -> dict:
        return deref(self._schema, self._schema["definitions"][name])

    @staticmethod
    def _safe_pan(pan: str) -> str:
        pan = (pan or "").strip().upper()
        return pan if len(pan) == 10 else "AAAAA0000A"

    @staticmethod
    def _state_code(code: str) -> str:
        code = (code or "").strip()
        if code.isdigit() and 1 <= int(code) <= 37:
            return f"{int(code):02d}"
        return "99"

    @staticmethod
    def _mobile(mobile: Optional[str]) -> int:
        digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
        return int(digits[-10:]) if len(digits) >= 5 else 9999999999

    # ── metadata ──────────────────────────────────────────────────────────────

    def _creation_info(self, body: dict, generated_on: Optional[date]) -> None:
        created = generated_on or date.today()
        if created < date(2026, 4, 1):
            created = date(2026, 4, 1)
        body["CreationInfo"] = {
            "SWVersionNo": "1.0",
            "SWCreatedBy": self.sw_created_by,
            "JSONCreatedBy": self.sw_created_by,
            "JSONCreationDate": created.isoformat(),
            "IntermediaryCity": "NA",
            "Digest": "-",
        }

    def _form(self, body: dict) -> None:
        body["Form_ITR2"] = {
            "FormName": "ITR-2",
            "Description": "ITR-2",
            "AssessmentYear": self.assessment_year,
            "SchemaVer": self.schema_ver,
            "FormVer": self.form_ver,
        }

    # ── Part A: identity + filing status ──────────────────────────────────────

    def _part_a(self, body: dict, inp: ReturnInput) -> None:
        addr = inp.address
        personal = body["PartA_GEN1"]["PersonalInfo"]
        personal["AssesseeName"] = {"SurNameOrOrgName": inp.name or "NA"}
        personal["PAN"] = self._safe_pan(inp.pan)
        personal["Address"] = {
            "ResidenceNo": addr.line1 or "NA",
            "LocalityOrArea": addr.line2 or "NA",
            "CityOrTownOrDistrict": addr.city or "NA",
            "StateCode": self._state_code(addr.state_code),
            "CountryCode": addr.country_code or "91",
            "CountryCodeMobile": 91,
            "MobileNo": self._mobile(addr.mobile),
            "EmailAddress": addr.email or "a@b.co",
        }
        personal["SecondaryAdd"] = "N"
        personal["DOB"] = inp.dob or "1990-01-01"
        personal["Status"] = "I"

        filing = body["PartA_GEN1"]["FilingStatus"]
        filing["ReturnFileSec"] = 11
        filing["OptOutNewTaxRegime"] = "Y" if inp.regime == "old" else "N"
        filing["SeventhProvisio139"] = "N"
        filing["ResidentialStatus"] = inp.residential_status
        filing["HeldUnlistedEqShrPrYrFlg"] = "N"
        filing["FiiFpiFlag"] = "N"
        filing["ItrFilingDueDate"] = self.filing_due_date

    # ── Schedule S: salary ────────────────────────────────────────────────────

    def _schedule_s(self, body: dict, inp: ReturnInput) -> None:
        if not inp.salary:
            # ScheduleS.Salaries has minItems 1, so omit the schedule entirely
            # when there is no salary income (it is not a required schedule).
            body.pop("ScheduleS", None)
            return

        items_node = self._def("ScheduleS")["properties"]["Salaries"]["items"]
        rows = []
        for f in inp.salary:
            row = template(self._schema, items_node)
            row["NameOfEmployer"] = f.employer_name or "NA"
            row["NatureOfEmployment"] = "OTH"
            if f.employer_tan:
                row["TANofEmployer"] = f.employer_tan
            row["AddressDetail"] = {
                **row["AddressDetail"],
                "AddrDetail": f.employer_address or "NA",
                "CityOrTownOrDistrict": "NA",
                "StateCode": "99",
            }
            row["Salarys"] = {
                **row["Salarys"],
                "GrossSalary": round(f.gross_salary),
                "Salary": round(f.gross_salary),
                "ValueOfPerquisites": round(f.perquisites),
                "ProfitsinLieuOfSalary": 0,
                "IncomeNotified89A": 0,
                "IncomeNotifiedOther89A": 0,
            }
            rows.append(row)

        gross = sum(f.gross_salary for f in inp.salary)
        exempt_10 = sum(f.exemptions_10 for f in inp.salary)
        std_ded = sum(f.standard_deduction for f in inp.salary)
        prof_tax = sum(f.professional_tax for f in inp.salary)

        schedule = body["ScheduleS"]
        schedule["Salaries"] = rows
        schedule["TotalGrossSalary"] = round(gross)
        schedule["AllwncExtentExemptUs10"] = round(exempt_10)
        schedule["NetSalary"] = round(gross - exempt_10)
        schedule["DeductionUnderSection16ia"] = round(std_ded)
        schedule["ProfessionalTaxUs16iii"] = round(prof_tax)
        schedule["DeductionUS16"] = round(std_ded + prof_tax)
        schedule["TotIncUnderHeadSalaries"] = round(gross - exempt_10 - std_ded - prof_tax)

    # ── Schedule OS: other income ─────────────────────────────────────────────

    def _schedule_os(self, body: dict, inp: ReturnInput) -> None:
        oi = inp.other_income
        os_sched = body["ScheduleOS"]
        if "IncOthThanOwnRaceHorse" not in os_sched:
            os_sched["IncOthThanOwnRaceHorse"] = template(
                self._schema, self._def("ScheduleOS")["properties"]["IncOthThanOwnRaceHorse"]
            )
        other = os_sched["IncOthThanOwnRaceHorse"]

        fd_interest = (
            oi.term_deposit_interest_override
            if oi.term_deposit_interest_override is not None
            else 0.0
        )
        other["IntrstFrmSavingBank"] = round(oi.savings_interest)
        other["IntrstFrmTermDeposit"] = round(fd_interest)
        other["IntrstFrmIncmTaxRefund"] = round(oi.interest_on_it_refund)
        other["IntrstFrmOthers"] = round(oi.other_interest)
        other["InterestGross"] = round(
            oi.savings_interest + fd_interest + oi.interest_on_it_refund + oi.other_interest
        )
        other["DividendGross"] = round(oi.dividends)

        balance = round(
            oi.savings_interest
            + fd_interest
            + oi.interest_on_it_refund
            + oi.other_interest
            + oi.dividends
        )
        other["BalanceNoRaceHorse"] = balance
        os_sched["TotOthSrcNoRaceHorse"] = balance
        os_sched["IncChargeable"] = balance

    # ── Verification ──────────────────────────────────────────────────────────

    def _verification(self, body: dict, inp: ReturnInput) -> None:
        decl = body["Verification"]["Declaration"]
        decl["AssesseeVerName"] = inp.verification.get("name") or inp.name or "NA"
        decl["FatherName"] = inp.verification.get("father_name") or "NA"
        decl["AssesseeVerPAN"] = self._safe_pan(inp.pan)
        body["Verification"]["Capacity"] = inp.verification.get("capacity") or "S"
