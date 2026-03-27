import pytest
from app.importers.base import BaseImporter, ImportResult


def test_base_importer_parse_is_abstract():
    """Can't instantiate abstract class directly."""
    with pytest.raises(TypeError):
        BaseImporter()


def test_concrete_importer_with_class_vars():
    class GoodImporter(BaseImporter):
        source = "test_source"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(source=self.source)

    importer = GoodImporter()
    result = importer.parse(b"test")
    assert result.source == "test_source"


def test_validate_default_returns_empty_list():
    class MinimalImporter(BaseImporter):
        source = "minimal"
        asset_type = "STOCK_IN"
        format = "csv"

        def parse(self, file_bytes: bytes) -> ImportResult:
            return ImportResult(source="minimal")

    importer = MinimalImporter()
    result = importer.parse(b"")
    warnings = importer.validate(result)
    assert warnings == []
