"""
Static pre-computed parse results for use in unit and integration tests.

These values are taken from the real parsers run against the fixture PDFs.
To re-verify, run: pytest -m smoke
"""
from datetime import date

from app.importers.base import ImportResult, ParsedTransaction, ParsedFundSnapshot
from app.importers.ppf_pdf_parser import PPFImportResult
from app.importers.epf_pdf_parser import EPFImportResult


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
# PPF (Public Provident Fund statement)
# Values verified from tests/fixtures/PPF_account_statement.pdf
# ---------------------------------------------------------------------------
PARSED_PPF = PPFImportResult(
    source="ppf_pdf",
    account_number="32256576916",
    closing_balance_inr=42947.0,
    closing_balance_date=date(2018, 12, 28),
    transactions=[
        ParsedTransaction(
            source="ppf_pdf",
            asset_name="PPF — 32256576916",
            asset_identifier="32256576916",
            asset_type="PPF",
            txn_type="CONTRIBUTION",
            date=date(2018, 5, 29),
            amount_inr=-5000.0,
            txn_id="ppf_3199410044308",
        ),
        ParsedTransaction(
            source="ppf_pdf",
            asset_name="PPF — 32256576916",
            asset_identifier="32256576916",
            asset_type="PPF",
            txn_type="CONTRIBUTION",
            date=date(2018, 12, 28),
            amount_inr=-15000.0,
            txn_id="ppf_IF17658260",
        ),
    ],
    errors=[],
)


# ---------------------------------------------------------------------------
# EPF (Employees Provident Fund passbook)
# Values verified from tests/fixtures/PYKRP00192140000152747.pdf
# ---------------------------------------------------------------------------
PARSED_EPF = EPFImportResult(
    source="epf_pdf",
    member_id="PYKRP00192140000152747",
    establishment_name="IBM INDIA PVT LTD",
    print_date=date(2018, 11, 27),
    grand_total_emp_deposit=198371.0,
    grand_total_er_deposit=140204.0,
    net_balance_inr=0.0,
    transactions=[
        # Employee Share CONTRIBUTION → EPF asset
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — IBM INDIA PVT LTD",
            asset_identifier="PYKRP00192140000152747",
            asset_type="EPF",
            txn_type="CONTRIBUTION",
            date=date(2011, 8, 31),
            amount_inr=-2114.0,
            txn_id="epf_eb6c5d62c1f7f5f140a823f60111b2ac3e7569156034e6cd7d417fd49b6bdb91",
            notes="Employee Share",
        ),
        # Employer Share CONTRIBUTION → EPF asset
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — IBM INDIA PVT LTD",
            asset_identifier="PYKRP00192140000152747",
            asset_type="EPF",
            txn_type="CONTRIBUTION",
            date=date(2011, 8, 31),
            amount_inr=-1573.0,
            txn_id="epf_b7916686c424dff4416b2619ed2f667f000d3ccbf84b13a0596062dd28c2bc7f",
            notes="Employer Share",
        ),
        # Pension CONTRIBUTION → EPS asset
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPS — IBM INDIA PVT LTD",
            asset_identifier="PYKRP00192140000152747_EPS",
            asset_type="EPF",
            txn_type="CONTRIBUTION",
            date=date(2011, 8, 31),
            amount_inr=-541.0,
            txn_id="epf_210f65dd7a640f61178d9b664d9f4c763298d708252163d74e7f2ff7d88ed2cf",
            notes="Pension Contribution",
        ),
        # INTEREST → EPF asset
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — IBM INDIA PVT LTD",
            asset_identifier="PYKRP00192140000152747",
            asset_type="EPF",
            txn_type="INTEREST",
            date=date(2012, 3, 31),
            amount_inr=690.0,
            txn_id="epf_1d26f70cbdd82ef1d265333918f609f81ef73420305e1e2625dc5eb42bc68f98",
        ),
        # TRANSFER (Claim: Against PARA 57(1)) → EPF asset
        ParsedTransaction(
            source="epf_pdf",
            asset_name="EPF — IBM INDIA PVT LTD",
            asset_identifier="PYKRP00192140000152747",
            asset_type="EPF",
            txn_type="TRANSFER",
            date=date(2018, 11, 27),
            amount_inr=338575.0,
            txn_id="epf_f2e088e9df8de39e8bb99fe1b6a9b5b3e26ad3500ba56f997a8e6d28c32ed0e0",
        ),
    ],
    errors=[],
)
