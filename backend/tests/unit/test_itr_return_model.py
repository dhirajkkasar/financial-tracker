"""The itr_returns table shape."""
from app.models.itr_return import ItrReturn


def test_itr_return_tablename_and_columns():
    assert ItrReturn.__tablename__ == "itr_returns"
    cols = {c.name for c in ItrReturn.__table__.columns}
    assert {
        "id", "member_id", "fy_label", "ay_label", "form_type", "status",
        "input_json", "draft_json", "output_json", "schema_version",
        "generated_at", "created_at", "updated_at",
    } <= cols


def test_itr_return_unique_member_ay():
    names = {c.name for c in ItrReturn.__table__.constraints if c.name}
    assert "uq_itr_return_member_ay" in names


def test_itr_return_defaults(db):
    r = ItrReturn(member_id=1, fy_label="2025-26", ay_label="2026-27")
    db.add(r)
    db.flush()
    assert r.form_type == "ITR2"
    assert r.status == "draft"
