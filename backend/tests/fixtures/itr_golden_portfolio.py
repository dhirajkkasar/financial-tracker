"""Golden AY 2026-27 (FY 2025-26) portfolio for the end-to-end ITR-2 test.

One member, one year, every income kind the first milestone must handle:

* salary from a synthetic Form 16 (a PDF built here — never real taxpayer data)
* an FD whose FY interest the portfolio supplies (Rs 40,000, SIMPLE compounding)
* savings interest declared in the input document (Rs 10,000)
* listed Indian equity: STCG u/s 111A (Rs 15,000) + LTCG u/s 112A (Rs 2,00,000)
* a US-stock LTCG charged at 12.5% (Rs 50,000)

Every figure is hand-derived from the inputs below, so the end-to-end test fails
loudly if any stage (portfolio -> draft -> builder) drifts. The module is pure
data + a ``seed`` helper; the assertions live in the test.
"""
from __future__ import annotations

from datetime import date

from app.models.asset import Asset, AssetClass, AssetType
from app.models.fd_detail import CompoundingType, FDDetail, FDType
from app.models.transaction import Transaction, TransactionType

# ── identity ──────────────────────────────────────────────────────────────────
# A valid *individual* PAN: the 4th character of the 5-char prefix must be "P"
# (the official schema's Verify pattern for a personal return).
PAN = "ABCPE1234F"
NAME = "Test Taxpayer"
FY = "2025-26"

# ── salary (synthetic Form 16) ────────────────────────────────────────────────
GROSS_SALARY = 2_000_000.0
EXEMPTIONS_10 = 50_000.0
STANDARD_DEDUCTION = 75_000.0
TDS = 250_000.0
TAXABLE_SALARY = GROSS_SALARY - EXEMPTIONS_10 - STANDARD_DEDUCTION   # 1,875,000

# ── other income ──────────────────────────────────────────────────────────────
SAVINGS_INTEREST = 10_000.0
FD_PRINCIPAL_INR = 500_000.0
FD_RATE_PCT = 8.0
# SIMPLE interest over one full FY (2025-03-31 -> 2026-03-31 = 365 days) is
# exactly principal x rate, so the golden figure is unambiguous.
FD_INTEREST = FD_PRINCIPAL_INR * FD_RATE_PCT / 100.0                # 40,000
OTHER_INTEREST = SAVINGS_INTEREST + FD_INTEREST                    # 50,000

# ── capital gains ─────────────────────────────────────────────────────────────
# Reliance — bought and sold inside the year => STCG u/s 111A @ 20%.
STCG_111A = 15_000.0            # 100u @ 500 -> 650
# Infosys — held > 12 months => LTCG u/s 112A (gross; exemption in Schedule SI).
LTCG_112A = 200_000.0           # 50u @ 1,000 -> 5,000
LTCG_112A_UNITS = 50.0
LTCG_112A_BUY_PU = 1_000.0
LTCG_112A_SELL_PU = 5_000.0
LTCG_112A_SALE_VALUE = 250_000.0
LTCG_112A_COST = 50_000.0
# Apple — held > 24 months, not 112A-eligible => other LTCG @ 12.5%.
LTCG_OTHER = 50_000.0           # 100u, -100,000 -> +150,000

LTCG_TOTAL = LTCG_112A + LTCG_OTHER                               # 250,000
CG_GROSS = STCG_111A + LTCG_TOTAL                                 # 265,000

# ── tax (new regime, FY 2025-26 slabs) ────────────────────────────────────────
NORMAL_INCOME = TAXABLE_SALARY + OTHER_INTEREST                   # 1,925,000
LTCG_112A_EXEMPTION = 125_000.0
LTCG_112A_TAXABLE = LTCG_112A - LTCG_112A_EXEMPTION               # 75,000
# Slabs on 1,925,000: 4L@0 + 4L@5% + 4L@10% + 4L@15% + 3.25L@20% = 185,000
NORMAL_TAX = 185_000.0
STCG_111A_TAX = STCG_111A * 0.20                                  # 3,000
LTCG_112A_TAX = LTCG_112A_TAXABLE * 0.125                         # 9,375
LTCG_OTHER_TAX = LTCG_OTHER * 0.125                               # 6,250
SPECIAL_TAX = STCG_111A_TAX + LTCG_112A_TAX + LTCG_OTHER_TAX      # 18,625
CESS = (NORMAL_TAX + SPECIAL_TAX) * 0.04                          # 8,145
TOTAL_TAX = NORMAL_TAX + SPECIAL_TAX + CESS                       # 211,770
REFUND = TDS - TOTAL_TAX                                          # 38,230
# Total income is below the Rs 50L surcharge threshold, so surcharge is zero.
TOTAL_INCOME = NORMAL_INCOME + STCG_111A + LTCG_112A + LTCG_OTHER  # 2,190,000


# ── synthetic Form 16 ─────────────────────────────────────────────────────────

def form16_text() -> str:
    """A complete, parseable Form 16 with the salary figures above."""
    return f"""FORM NO. 16
Certificate under section 203 of the Income-tax Act, 1961 for tax deducted at source on salary

PART A

Name and address of the Employer: Acme Technologies Private Limited, 5 Example Park, Pune 411001
TAN of the Deductor: ZZZZ00000Z
PAN of the Deductor: AAAAA0000A
Name and address of the Employee: {NAME}, 1 Example Road, Pune 411002
PAN of the Employee: {PAN}
Period with the Employer: From 2025-04-01 To 2026-03-31

PART B

Details of salary paid and any other income and tax deducted
1   Gross Salary                                {GROSS_SALARY:.2f}
2   Exemptions under section 10                 {EXEMPTIONS_10:.2f}
3   Perquisites                                 0
4   Standard deduction under section 16(ia)     {STANDARD_DEDUCTION:.2f}
5   Professional tax under section 16(iii)      0
6   Total Taxable Income                        {TAXABLE_SALARY:.2f}
Total amount of tax deducted                    {TDS:.2f}
"""


def form16_pdf_bytes() -> bytes:
    """Render :func:`form16_text` to a one-page PDF (no real data involved)."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in form16_text().splitlines():
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ── portfolio ─────────────────────────────────────────────────────────────────

def _equity(db, member_id: int, *, name, isin, buy_date, sell_date,
            units, buy_pu, sell_pu) -> Asset:
    asset = Asset(
        member_id=member_id, name=name, identifier=isin,
        asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY,
    )
    db.add(asset)
    db.flush()
    db.add(Transaction(
        txn_id=f"buy-{isin}", asset_id=asset.id, type=TransactionType.BUY,
        date=buy_date, units=units, price_per_unit=buy_pu,
        amount_inr=-round(buy_pu * units * 100),          # paise, signed
    ))
    db.add(Transaction(
        txn_id=f"sell-{isin}", asset_id=asset.id, type=TransactionType.SELL,
        date=sell_date, units=units, price_per_unit=sell_pu,
        amount_inr=round(sell_pu * units * 100),
    ))
    db.flush()
    return asset


def seed(db, member_id: int) -> dict:
    """Create the golden portfolio for ``member_id``; return the asset ids."""
    reliance = _equity(
        db, member_id, name="Reliance Industries", isin="INE002A01018",
        buy_date=date(2025, 1, 10), sell_date=date(2025, 6, 1),
        units=100.0, buy_pu=500.0, sell_pu=650.0,
    )
    infosys = _equity(
        db, member_id, name="Infosys", isin="INE009A01021",
        buy_date=date(2022, 6, 1), sell_date=date(2025, 6, 1),
        units=LTCG_112A_UNITS, buy_pu=LTCG_112A_BUY_PU, sell_pu=LTCG_112A_SELL_PU,
    )

    us = Asset(
        member_id=member_id, name="Apple Inc", identifier="AAPL",
        asset_type=AssetType.STOCK_US, asset_class=AssetClass.EQUITY, currency="USD",
    )
    db.add(us)
    db.flush()
    db.add(Transaction(
        txn_id="buy-AAPL", asset_id=us.id, type=TransactionType.BUY,
        date=date(2022, 1, 15), units=100.0, price_per_unit=1_000.0,
        amount_inr=-10_000_000,
    ))
    db.add(Transaction(
        txn_id="sell-AAPL", asset_id=us.id, type=TransactionType.SELL,
        date=date(2025, 8, 1), units=100.0, price_per_unit=1_500.0,
        amount_inr=15_000_000,
    ))
    db.flush()

    fd = Asset(
        member_id=member_id, name="HDFC FD", identifier=None,
        asset_type=AssetType.FD, asset_class=AssetClass.DEBT,
    )
    db.add(fd)
    db.flush()
    # Starts before the FY and matures after it, so the FY window is exactly one
    # year of SIMPLE interest: 500,000 x 8% = 40,000.
    db.add(FDDetail(
        asset_id=fd.id, bank="HDFC Bank", fd_type=FDType.FD,
        principal_amount=int(FD_PRINCIPAL_INR * 100),
        interest_rate_pct=FD_RATE_PCT, compounding=CompoundingType.SIMPLE,
        start_date=date(2024, 4, 1), maturity_date=date(2027, 3, 31),
        tds_applicable=False,
    ))
    db.flush()

    return {"reliance": reliance.id, "infosys": infosys.id, "us": us.id, "fd": fd.id}
