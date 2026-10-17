"""ITR-2 builder for AY 2026-27 (FY 2025-26), new regime.

Starts from the schema-derived skeleton (all required branches present, zeroed)
and overlays the assembled draft + the per-year input document. See
``common.py`` for why the skeleton is generated rather than hand-written.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.engine.itr.builders.base import ItrBuilder, register_builder
from app.engine.itr.builders.common import build_skeleton, deref, template
from app.engine.itr.schema_loader import load_itr_schema
from app.schemas.itr_models import ReturnInput
from app.services.itr_assembler import ReturnDraft

FORM_KEY = "ITR2"


def _r(x: float) -> int:
    """Round to the nearest rupee, half-up (the Common Offline Utility's convention)."""
    return int(Decimal(str(x or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


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
        self._schedule_os(body, draft, input_doc)
        self._schedule_cg(body, draft)
        self._schedule_112a(body, draft)
        self._schedule_si(body, draft)
        self._part_b_ti(body, draft, input_doc)
        self._part_b_tti(body, draft, input_doc)
        self._schedule_cfl(body, draft)
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

    def _schedule_os(self, body: dict, draft: ReturnDraft, inp: ReturnInput) -> None:
        buckets = draft.buckets or {}
        oi = inp.other_income
        total_interest = buckets.get("other_interest", 0.0)
        dividends = buckets.get("dividends", 0.0)
        # Split the assembled interest total across the OS lines; whatever the
        # user did not itemise (portfolio FD/RD interest) lands in term deposits.
        fd_interest = max(
            0.0,
            total_interest
            - oi.savings_interest
            - oi.interest_on_it_refund
            - oi.other_interest,
        )

        os_sched = body["ScheduleOS"]
        if "IncOthThanOwnRaceHorse" not in os_sched:
            os_sched["IncOthThanOwnRaceHorse"] = template(
                self._schema, self._def("ScheduleOS")["properties"]["IncOthThanOwnRaceHorse"]
            )
        other = os_sched["IncOthThanOwnRaceHorse"]
        other["IntrstFrmSavingBank"] = _r(oi.savings_interest)
        other["IntrstFrmTermDeposit"] = _r(fd_interest)
        other["IntrstFrmIncmTaxRefund"] = _r(oi.interest_on_it_refund)
        other["IntrstFrmOthers"] = _r(oi.other_interest)
        other["InterestGross"] = _r(total_interest)
        other["DividendGross"] = _r(dividends)

        balance = _r(total_interest + dividends)
        other["BalanceNoRaceHorse"] = balance
        os_sched["TotOthSrcNoRaceHorse"] = balance
        os_sched["IncChargeable"] = balance

    # ── Schedule CG ───────────────────────────────────────────────────────────

    @staticmethod
    def _deduct_sec48(acquisition_cost: int) -> dict:
        return {
            "AquisitCost": acquisition_cost,
            "ImproveCost": 0,
            "ExpOnTrans": 0,
            "TotalDedn": acquisition_cost,
        }

    def _schedule_cg(self, body: dict, draft: ReturnDraft) -> None:
        g = draft.gross or {}
        stcg_111a = _r(g.get("stcg_111a", 0.0))
        stcg_slab = _r(g.get("stcg_slab", 0.0))
        # The 112A figure must tie to Schedule 112A (rule 134), so take it from
        # the scrip-wise schedule rather than the summary's per-asset gain.
        ltcg_112a = _r((draft.schedule_112a or {}).get("balance", 0))
        ltcg_other = _r(g.get("ltcg_other_12_5", 0.0))

        sched = body["ScheduleCGFor23"]
        stcg = sched["ShortTermCapGainFor23"]
        # 111A: listed equity / equity MF STCG at 20% ("1A" per the schema notes).
        if stcg_111a:
            stcg["EquityMFonSTT"] = [{
                "MFSectionCode": "1A",
                "EquityMFonSTTDtls": {
                    "FullConsideration": stcg_111a,
                    "DeductSec48": self._deduct_sec48(0),
                    "BalanceCG": stcg_111a,
                    "LossSec94of7Or94of8": 0,
                    "CapgainonAssets": stcg_111a,
                },
            }]
        # Slab-rate short-term gains: other assets.
        if stcg_slab:
            stcg["SaleOnOtherAssets"] = {
                "FullValueConsdRecvUnqshr": 0,
                "FairMrktValueUnqshr": 0,
                "FullValueConsdSec50CA": 0,
                "FullValueConsdOthUnqshr": 0,
                "FullConsideration": stcg_slab,
                "DeductSec48": self._deduct_sec48(0),
                "BalanceCG": stcg_slab,
                "LossSec94of7Or94of8": 0,
                "CapgainonAssets": stcg_slab,
            }
        stcg["TotalSTCG"] = stcg_111a + stcg_slab

        ltcg = sched["LongTermCapGain23"]
        # B3a — long-term gains on listed equity / equity MF u/s 112A.
        if ltcg_112a:
            ltcg["SaleOfEquityShareUs112A"] = {
                "BalanceCG": ltcg_112a,
                "DeductionUs54F": 0,
                "CapgainonAssets": ltcg_112a,
            }
        if ltcg_other:
            ltcg["SaleofAssetNADtls"] = {
                "SaleofAssetNA": {
                    "FullValueConsdRecvUnqshr": 0,
                    "FairMrktValueUnqshr": 0,
                    "FullValueConsdSec50CA": 0,
                    "FullValueConsdOthUnqshr": 0,
                    "FullConsideration": ltcg_other,
                    "DeductSec48": self._deduct_sec48(0),
                    "BalanceCG": ltcg_other,
                    "DeductionUs54F": 0,
                    "CapgainonAssets": ltcg_other,
                }
            }
        ltcg["TotalLTCG"] = ltcg_112a + ltcg_other

        total_gross = stcg_111a + stcg_slab + ltcg_112a + ltcg_other
        sched["SumOfCGIncm"] = total_gross
        sched["TotScheduleCGFor23"] = total_gross

        setoff = draft.setoff or {}
        created = (draft.carryforward or {}).get("created_this_year") or {}
        stcl_on_stcg = _r(setoff.get("stcl_on_stcg", 0.0))
        stcl_on_ltcg = _r(setoff.get("stcl_on_ltcg", 0.0))
        ltcl_on_ltcg = _r(setoff.get("ltcl_on_ltcg", 0.0))
        curr = sched["CurrYrLosses"]
        curr["InLossSetOff"] = self._setoff_summary(stcl_on_stcg, stcl_on_ltcg + ltcl_on_ltcg)
        curr["TotLossSetOff"] = self._setoff_summary(stcl_on_stcg, stcl_on_ltcg + ltcl_on_ltcg)
        curr["LossRemainSetOff"] = self._setoff_summary(
            _r(created.get("stcl", 0.0)), _r(created.get("ltcl", 0.0))
        )
        curr["InStcg20Per"]["CurrYearIncome"] = stcg_111a
        curr["InStcg20Per"]["CurrYrCapGain"] = stcg_111a
        curr["InLtcg12_5Per"]["CurrYearIncome"] = ltcg_112a + ltcg_other
        curr["InLtcg12_5Per"]["CurrYrCapGain"] = ltcg_112a + ltcg_other

    @staticmethod
    def _setoff_summary(stcl_20per: int, ltcl_12_5per: int) -> dict:
        return {
            "StclSetoff20Per": stcl_20per,
            "StclSetoff30Per": 0,
            "StclSetoffAppRate": 0,
            "StclSetoffDTAARate": 0,
            "LtclSetOff12_5Per": ltcl_12_5per,
            "LtclSetOffDTAARate": 0,
        }

    # ── Schedule 112A ─────────────────────────────────────────────────────────

    def _schedule_112a(self, body: dict, draft: ReturnDraft) -> None:
        s = draft.schedule_112a or {}
        rows = s.get("rows", [])
        if not rows:
            body.pop("Schedule112A", None)
            return
        node = body["Schedule112A"]
        node["Schedule112ADtls"] = [
            {
                "ShareOnOrBefore": r["share_on_or_before"],
                "ISINCode": r.get("isin") or "INNOTREQUIRD",
                "ShareUnitName": r.get("name") or "CONSOLIDATED",
                "NumSharesUnits": r["units"],
                "SalePricePerShareUnit": r["sale_price_per_unit"],
                "TotSaleValue": _r(r["tot_sale_value"]),
                "CostAcqWithoutIndx": _r(r["cost_acq_without_indx"]),
                "AcquisitionCost": _r(r["acquisition_cost"]),
                "LTCGBeforelowerB1B2": _r(r["ltcg_before_lower"]),
                "FairMktValuePerShareunit": r["fmv_per_unit"],
                "TotFairMktValueCapAst": _r(r["tot_fmv"]),
                "ExpExclCnctTransfer": _r(r["exp_transfer"]),
                "TotalDeductions": _r(r["total_deductions"]),
                "Balance": _r(r["balance"]),
            }
            for r in rows
        ]
        node["SaleValue112A"] = _r(s.get("sale_value", 0))
        node["CostAcqWithoutIndx112A"] = _r(s.get("cost_acq_without_indx", 0))
        node["AcquisitionCost112A"] = _r(s.get("acquisition_cost", 0))
        node["LTCGBeforelowerB1B2112A"] = _r(s.get("ltcg_before_lower", 0))
        node["FairMktValueCapAst112A"] = _r(s.get("tot_fmv", 0))
        node["ExpExclCnctTransfer112A"] = _r(s.get("exp_transfer", 0))
        node["Deductions112A"] = _r(s.get("deductions", 0))
        node["Balance112A"] = _r(s.get("balance", 0))
        node["TotalBalance112A"] = _r(s.get("total_balance", 0))

    # ── Schedule SI — income charged at special rates ─────────────────────────

    def _schedule_si(self, body: dict, draft: ReturnDraft) -> None:
        g = draft.gross or {}
        tax = draft.tax or {}
        ltcg_112a = _r((draft.schedule_112a or {}).get("balance", 0))
        ltcg_112a_taxable = _r(tax.get("ltcg_112a_taxable", 0.0))
        stcg_111a = _r(g.get("stcg_111a", 0.0))
        ltcg_other = _r(g.get("ltcg_other_12_5", 0.0))

        lines = []
        if stcg_111a:
            lines.append({"SecCode": "1A", "SplRatePercent": 20.0,
                          "SplRateInc": stcg_111a,
                          "SplRateIncTax": _r(stcg_111a * 0.20)})
        if ltcg_112a_taxable:
            lines.append({"SecCode": "2A", "SplRatePercent": 12.5,
                          "SplRateInc": ltcg_112a_taxable,
                          "SplRateIncTax": _r(ltcg_112a_taxable * 0.125)})
        if ltcg_other:
            lines.append({"SecCode": "21", "SplRatePercent": 12.5,
                          "SplRateInc": ltcg_other,
                          "SplRateIncTax": _r(ltcg_other * 0.125)})

        si = body["ScheduleSI"]
        if not lines:
            # SplCodeRateTax has minItems 1; omit the schedule when nothing is
            # charged at a special rate (ScheduleSI is not a required schedule).
            body.pop("ScheduleSI", None)
            return
        si["SplCodeRateTax"] = lines
        si["TotSplRateInc"] = sum(l["SplRateInc"] for l in lines)
        si["TotSplRateIncTax"] = sum(l["SplRateIncTax"] for l in lines)

    # ── Part B-TI ─────────────────────────────────────────────────────────────

    def _part_b_ti(self, body: dict, draft: ReturnDraft, inp: ReturnInput) -> None:
        g = draft.gross or {}
        b = draft.buckets or {}
        tax = draft.tax or {}
        setoff = draft.setoff or {}
        cf = draft.carryforward or {}

        salary = _r(b.get("salary", 0.0))
        interest = _r(b.get("other_interest", 0.0))
        dividends = _r(b.get("dividends", 0.0))
        stcg_111a = _r(g.get("stcg_111a", 0.0))
        stcg_slab = _r(g.get("stcg_slab", 0.0))
        ltcg_112a = _r((draft.schedule_112a or {}).get("balance", 0))
        ltcg_other = _r(g.get("ltcg_other_12_5", 0.0))
        ltcg_112a_taxable = _r(tax.get("ltcg_112a_taxable", 0.0))

        cg_total = stcg_111a + stcg_slab + ltcg_112a + ltcg_other
        os_total = interest + dividends

        applied_current = sum(
            _r(setoff.get(k, 0.0))
            for k in ("stcl_on_stcg", "stcl_on_ltcg", "ltcl_on_ltcg")
        )
        applied_brought = _r(setoff.get("cf_stcl_used", 0.0)) + _r(setoff.get("cf_ltcl_used", 0.0))
        created = (cf.get("created_this_year") or {})
        carried_fwd = _r(created.get("stcl", 0.0)) + _r(created.get("ltcl", 0.0))

        total_ti = salary + cg_total + os_total
        balance_after_setoff = total_ti - applied_current
        gross_total_income = balance_after_setoff - applied_brought

        ti = body["PartB-TI"]
        ti["Salaries"] = salary
        ti["IncomeFromHP"] = 0
        cg = ti["CapGain"]
        cg["ShortTerm"]["ShortTerm20Per"] = stcg_111a
        cg["ShortTerm"]["ShortTermAppRate"] = stcg_slab
        cg["ShortTerm"]["TotalShortTerm"] = stcg_111a + stcg_slab
        cg["LongTerm"]["LongTerm12_5Per"] = ltcg_112a + ltcg_other
        cg["LongTerm"]["TotalLongTerm"] = ltcg_112a + ltcg_other
        cg["ShortTermLongTermTotal"] = cg_total
        cg["TotalCapGains"] = cg_total

        ti["IncFromOS"]["OtherSrcThanOwnRaceHorse"] = os_total
        ti["IncFromOS"]["TotIncFromOS"] = os_total

        ti["TotalTI"] = total_ti
        ti["CurrentYearLoss"] = applied_current
        ti["BalanceAfterSetoffLosses"] = balance_after_setoff
        ti["BroughtFwdLossesSetoff"] = applied_brought
        ti["GrossTotalIncome"] = gross_total_income
        ti["IncChargeTaxSplRate111A112"] = stcg_111a + ltcg_112a_taxable
        ti["DeductionsUnderScheduleVIA"] = 0
        ti["TotalIncome"] = gross_total_income
        ti["IncChargeableTaxSplRates"] = stcg_111a + ltcg_112a_taxable + ltcg_other
        ti["NetAgricultureIncomeOrOtherIncomeForRate"] = 0
        ti["AggregateIncome"] = gross_total_income
        ti["LossesOfCurrentYearCarriedFwd"] = carried_fwd
        ti["DeemedIncomeUs115JC"] = 0

    # ── Part B-TTI — computation of tax liability ─────────────────────────────

    def _part_b_tti(self, body: dict, draft: ReturnDraft, inp: ReturnInput) -> None:
        tax = draft.tax or {}
        normal = _r(tax.get("normal_tax_inr", 0.0))
        special = _r(
            tax.get("stcg_111a_tax_inr", 0.0)
            + tax.get("ltcg_112a_tax_inr", 0.0)
            + tax.get("ltcg_other_tax_inr", 0.0)
        )
        rebate = _r(tax.get("rebate_87a_inr", 0.0))
        surcharge = _r(tax.get("surcharge_inr", 0.0))
        cess = _r(tax.get("cess_inr", 0.0))
        total = _r(tax.get("total_tax_inr", 0.0))

        tti = body["PartB_TTI"]
        tti["Surcharge"] = surcharge
        tti["HealthEduCess"] = cess
        tti["TotalTaxPayablDeemedTotInc"] = total
        tti["AssetOutIndiaFlag"] = (
            "YES" if (inp.foreign.fa_asset_overrides or inp.foreign.dividends) else "NO"
        )

        ctl = tti["ComputationOfTaxLiability"]
        tpo = ctl["TaxPayableOnTI"]
        tpo["TaxAtNormalRatesOnAggrInc"] = normal
        tpo["TaxAtSpecialRates"] = special
        tpo["RebateOnAgriInc"] = 0
        tpo["TaxPayableOnTotInc"] = normal + special
        ctl["Rebate87A"] = rebate
        ctl["TaxPayableOnRebate"] = normal + special - rebate
        ctl["TotalSurcharge"] = surcharge
        ctl["EducationCess"] = cess
        ctl["GrossTaxLiability"] = normal + special - rebate + surcharge
        ctl["GrossTaxPayable"] = total
        ctl["CreditUS115JD"] = 0
        ctl["TaxPayAfterCreditUs115JD"] = total
        ctl["NetTaxLiability"] = total
        ctl["AggregateTaxInterestLiability"] = total

        taxes_paid = _r(sum(f.tds for f in inp.salary))
        tti["TaxPaid"]["BalTaxPayable"] = max(0, total - taxes_paid)
        tti["Refund"]["RefundDue"] = max(0, taxes_paid - total)

    # ── Schedule CFL ──────────────────────────────────────────────────────────

    def _schedule_cfl(self, body: dict, draft: ReturnDraft) -> None:
        cf = draft.carryforward or {}
        created = cf.get("created_this_year") or {}
        brought = cf.get("brought_forward") or {}
        cfl = body["ScheduleCFL"]
        summary = cfl["TotalLossCFSummary"]["LossSummaryDetail"]
        summary["TotalSTCGPTILossCF"] = _r(created.get("stcl", 0.0))
        summary["TotalLTCGPTILossCF"] = _r(created.get("ltcl", 0.0))
        earlier = cfl["TotalOfBFLossesEarlierYrs"]["LossSummaryDetail"]
        earlier["TotalSTCGPTILossCF"] = _r(brought.get("stcl", 0.0))
        earlier["TotalLTCGPTILossCF"] = _r(brought.get("ltcl", 0.0))

    # ── Verification ──────────────────────────────────────────────────────────

    def _verification(self, body: dict, inp: ReturnInput) -> None:
        decl = body["Verification"]["Declaration"]
        decl["AssesseeVerName"] = inp.verification.get("name") or inp.name or "NA"
        decl["FatherName"] = inp.verification.get("father_name") or "NA"
        decl["AssesseeVerPAN"] = self._safe_pan(inp.pan)
        body["Verification"]["Capacity"] = inp.verification.get("capacity") or "S"
