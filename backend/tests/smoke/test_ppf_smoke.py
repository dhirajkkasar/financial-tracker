import pytest
from pathlib import Path
from app.importers.ppf_pdf_parser import PPFPDFParser

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_ppf_parser_real_pdf():
    result = PPFPDFParser().parse((FIXTURES / "PPF_account_statement.pdf").read_bytes())
    assert result.account_number == "32256576916"
    assert result.closing_balance_inr == 42947.0
    assert len(result.transactions) == 2
