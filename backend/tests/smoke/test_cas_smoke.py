import pytest
from pathlib import Path
from app.importers.cas_parser import CASImporter

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_cas_parser_real_pdf():
    result = CASImporter().parse((FIXTURES / "test_cas.pdf").read_bytes())
    assert result.source == "cas"
    assert len(result.transactions) > 0
    assert len(result.errors) == 0
