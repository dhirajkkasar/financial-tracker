import pytest
from pathlib import Path
from app.importers.epf_pdf_parser import EPFPDFParser

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_epf_parser_real_pdf():
    result = EPFPDFParser().parse((FIXTURES / "BGBNG00268580000306940_2025.pdf").read_bytes())
    assert result.member_id == "BGBNG00268580000306940"
    assert result.establishment_name == "AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED"
    assert result.print_date is not None
    assert len(result.errors) == 0

    # 2025-2026 passbook: 12 months × 3 contribution types = 36 transactions
    # No interest (Interest details N/A for FY 2025-2026)
    assert len(result.transactions) == 36

    contribution_txns = [t for t in result.transactions if t.txn_type == "CONTRIBUTION"]
    assert len(contribution_txns) == 36

    # All 3 contribution types present
    notes_set = {t.notes for t in contribution_txns}
    assert "Employee Share" in notes_set
    assert "Employer Share" in notes_set
    assert "Pension Contribution (EPS)" in notes_set

    # No interest rows for FY 2025-2026 (N/A)
    interest_txns = [t for t in result.transactions if t.txn_type == "INTEREST"]
    assert len(interest_txns) == 0

    # All txn_ids unique
    ids = [t.txn_id for t in result.transactions]
    assert len(ids) == len(set(ids))

    # All transactions belong to the EPF asset
    for t in result.transactions:
        assert t.asset_identifier == "BGBNG00268580000306940"
        assert t.asset_type == "EPF"
