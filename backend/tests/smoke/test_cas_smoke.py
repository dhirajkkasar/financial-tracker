import pytest
from pathlib import Path
from app.importers.cas_importer import CASImporter

pytestmark = pytest.mark.smoke
FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_cas_parser_real_pdf():
    path = FIXTURES / "test_cas.pdf"
    if not path.exists():
        pytest.skip("test_cas.pdf fixture not available — place your real CAS PDF here to run this smoke test")
    result = CASImporter().parse(path.read_bytes())
    assert result.source == "cas"
    assert len(result.transactions) > 0
    assert len(result.errors) == 0
