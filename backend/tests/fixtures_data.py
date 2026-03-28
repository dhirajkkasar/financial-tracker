"""
Static pre-computed parse results for use in unit and integration tests.

These values are taken from the real parsers run against the fixture PDFs.
To re-verify, run: pytest -m smoke
"""
from datetime import date

from app.importers.base import ImportResult, ParsedTransaction, ParsedFundSnapshot


# ---------------------------------------------------------------------------
# CAS (Mutual Fund Consolidated Account Statement)
# Values verified from tests/fixtures/test_cas.pdf
# ---------------------------------------------------------------------------
PARSED_CAS = ImportResult(
    source="cas",
    transactions=[
        ParsedTransaction(
            source="cas",
            asset_name="HDFC Multi Cap Fund Direct Growth",
            asset_identifier="INF179KC1BS5",
            asset_type="MF",
            txn_type="SIP",
            date=date(2026, 1, 27),
            amount_inr=-9999.5,
            isin="INF179KC1BS5",
            txn_id="cas_cfcc5962779b9ab1c67523fed912bd8af781c37267b82a87c48371c8650fc9ab",
        ),
        ParsedTransaction(
            source="cas",
            asset_name="Kotak Small Cap Fund - Direct Plan - Growth",
            asset_identifier="INF174K01KT2",
            asset_type="MF",
            txn_type="BUY",
            date=date(2026, 3, 9),
            amount_inr=-49997.5,
            isin="INF174K01KT2",
            txn_id="cas_fa001c4d8bb91ec2d1a7f9110fc05432f816dc0472e264bae5f49bd4bee1dac7",
        ),
        ParsedTransaction(
            source="cas",
            asset_name="UTI Nifty 50 Index Fund - Direct Plan",
            asset_identifier="INF789F01XA0",
            asset_type="MF",
            txn_type="BUY",
            date=date(2026, 1, 12),
            amount_inr=-19999.0,
            isin="INF789F01XA0",
            txn_id="cas_08609fe9d37779f37f7fac7c4fde57947821580dde74cfd07a07e836e1079805",
        ),
    ],
    snapshots=[
        ParsedFundSnapshot(
            isin="INF179KC1BS5",
            asset_name="HDFC Multi Cap Fund Direct Growth",
            date=date(2026, 3, 18),
            closing_units=17292.257,
            nav_price_inr=18.505,
            market_value_inr=319993.22,
            total_cost_inr=340000.00,
        ),
        ParsedFundSnapshot(
            isin="INF879O01027",
            asset_name="Parag Parikh Flexi Cap Fund - Direct Plan Growth (formerly Parag Parikh Long Term Value Fund)",
            date=date(2026, 3, 18),
            closing_units=26580.939,
            nav_price_inr=89.3756,
            market_value_inr=2375687.37,
            total_cost_inr=1655390.87,
        ),
        ParsedFundSnapshot(
            isin="INF209K01UU3",
            asset_name="Aditya Birla Sun Life Money Manager Fund - Growth-Direct Plan",
            date=date(2026, 3, 18),
            closing_units=0.0,
            nav_price_inr=391.6409,
            market_value_inr=0.0,
            total_cost_inr=0.0,
        ),
    ],
    errors=[],
)


# ---------------------------------------------------------------------------
# PPF CSV (SBI PPF Account Statement — CSV format)
# 2 transactions from the minimal test CSV used in test_ppf_csv_parser.py
# txn_ids computed via _make_txn_id("32256576916", type, date, paise)
# ---------------------------------------------------------------------------
PARSED_PPF_CSV = ImportResult(
    source="ppf_csv",
    closing_valuation_inr=12543.0,
    closing_valuation_date=date(2026, 3, 25),
    transactions=[
        ParsedTransaction(
            source="ppf_csv",
            asset_name="PPF - SBI",
            asset_identifier="32256576916",
            asset_type="PPF",
            txn_type="CONTRIBUTION",
            date=date(2012, 10, 9),
            amount_inr=-10000.0,
            txn_id="ppf_csv_contrib_oct2012",
        ),
        ParsedTransaction(
            source="ppf_csv",
            asset_name="PPF - SBI",
            asset_identifier="32256576916",
            asset_type="PPF",
            txn_type="INTEREST",
            date=date(2013, 3, 31),
            amount_inr=543.0,
            txn_id="ppf_csv_interest_mar2013",
        ),
    ],
    errors=[],
)


# ---------------------------------------------------------------------------
# EPF (Employees Provident Fund passbook)
# Values verified from tests/fixtures/epf1.pdf (first month)
# plus representative interest txns from the 2024 passbook (31/03/2025).
# The smoke test (tests/smoke/test_epf_smoke.py) validates the full real parse.
# ---------------------------------------------------------------------------
PARSED_EPF = ImportResult(
    source="epf_pdf",
    closing_valuation_inr=0.0,
    closing_valuation_date=date(2026, 3, 24),
    transactions=[
        # Employee Share CONTRIBUTION — Apr-2025 (first row of 2025-2026 passbook)
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED",
            asset_identifier="BGBNG00268580000306940",
            asset_type="EPF",
            txn_type="CONTRIBUTION",
            date=date(2025, 4, 30),
            amount_inr=-27000.0,
            txn_id="epf_3409cb4e1fc84dcf843807af0e186045f5cefdf4ef58a28106fa0258b47ed902",
            notes="Employee Share",
        ),
        # Employer Share CONTRIBUTION — Apr-2025
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED",
            asset_identifier="BGBNG00268580000306940",
            asset_type="EPF",
            txn_type="CONTRIBUTION",
            date=date(2025, 4, 30),
            amount_inr=-25750.0,
            txn_id="epf_4e408707c193883de7b95802a8479023a9891d59df43737b3e0cf74ef7778d6f",
            notes="Employer Share",
        ),
        # Pension CONTRIBUTION — Apr-2025
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED",
            asset_identifier="BGBNG00268580000306940",
            asset_type="EPF",
            txn_type="CONTRIBUTION",
            date=date(2025, 4, 30),
            amount_inr=-1250.0,
            txn_id="epf_8715a251796889da7a96ac2d2bcf52d2c2436d3b994e5a8f5de8b220819472d0",
            notes="Pension Contribution (EPS)",
        ),
        # Employee INTEREST — 31/03/2025 (from 2024-2025 passbook)
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED",
            asset_identifier="BGBNG00268580000306940",
            asset_type="EPF",
            txn_type="INTEREST",
            date=date(2025, 3, 31),
            amount_inr=159741.0,
            txn_id="epf_1bf9d24d75644204f671523d79be6322c6286bc49c78ff2544556b8ed2c57350",
            notes="Employee Interest",
        ),
        # Employer INTEREST — 31/03/2025
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED",
            asset_identifier="BGBNG00268580000306940",
            asset_type="EPF",
            txn_type="INTEREST",
            date=date(2025, 3, 31),
            amount_inr=137317.0,
            txn_id="epf_df566077f9f139fc5efb4c7fb628fae0865015f4446f4830015ce6ea2fe6e570",
            notes="Employer Interest",
        ),
        # EPS INTEREST — 31/03/2025 (always recorded even when 0)
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED",
            asset_identifier="BGBNG00268580000306940",
            asset_type="EPF",
            txn_type="INTEREST",
            date=date(2025, 3, 31),
            amount_inr=0.0,
            txn_id="epf_698aff6560d40c9a36cc75848711562462ff496bcb792191c4c1f7ef3f82297e",
            notes="EPS Interest",
        ),
    ],
    errors=[],
)
