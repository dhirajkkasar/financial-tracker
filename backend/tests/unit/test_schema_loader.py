"""Schema loader: resolves the bundled official schema, refuses when absent."""
import pytest

from app.engine.itr.schema_loader import (
    MissingItrSchemaError,
    load_itr_schema,
    schema_path,
    schema_version,
)


def test_schema_path_exists_for_ay_2026_27():
    path = schema_path("2026-27")
    assert path.exists()
    assert path.name == "ITR-2_2026_Main_V1.2.json"


def test_schema_version_is_pinned():
    assert schema_version("2026-27") == "V1.2"


def test_loads_draft4_schema_with_itr_root():
    schema = load_itr_schema("2026-27")
    assert schema["$schema"] == "http://json-schema.org/draft-04/schema#"
    assert "ITR" in schema["properties"]
    assert len(schema["definitions"]) > 100


def test_missing_ay_raises():
    with pytest.raises(MissingItrSchemaError):
        schema_path("2099-00")


def test_missing_form_raises():
    with pytest.raises(MissingItrSchemaError):
        schema_path("2026-27", form="ITR-9")
