import pytest
from pathlib import Path
from app.importers.epf_pdf_parser import EPFPDFParser

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_epf_parser_real_pdf():
    result = EPFPDFParser().parse((FIXTURES / "PYKRP00192140000152747.pdf").read_bytes())
    assert result.member_id == "PYKRP00192140000152747"
    assert len(result.transactions) > 0
    assert len(result.errors) == 0
