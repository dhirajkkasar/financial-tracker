"""ItrReturnRepository — create/read/save behaviour."""
from app.repositories.itr_return_repo import ItrReturnRepository


def test_get_by_member_ay_returns_none_when_absent(db):
    repo = ItrReturnRepository(db)
    assert repo.get_by_member_ay(member_id=1, ay_label="2026-27") is None


def test_get_or_create_creates_once(db):
    repo = ItrReturnRepository(db)
    a = repo.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    b = repo.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    assert a.id == b.id
    assert a.form_type == "ITR2"
    assert a.status == "draft"


def test_get_or_create_is_per_member(db):
    repo = ItrReturnRepository(db)
    a = repo.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    b = repo.get_or_create(member_id=2, fy_label="2025-26", ay_label="2026-27")
    assert a.id != b.id


def test_save_and_get_input_json(db):
    repo = ItrReturnRepository(db)
    r = repo.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    repo.save_input(r.id, '{"regime": "new"}')
    assert repo.get(r.id).input_json == '{"regime": "new"}'


def test_list_by_member_ordered_by_ay(db):
    repo = ItrReturnRepository(db)
    repo.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    repo.get_or_create(member_id=1, fy_label="2024-25", ay_label="2025-26")
    repo.get_or_create(member_id=2, fy_label="2024-25", ay_label="2025-26")
    ays = [r.ay_label for r in repo.list_by_member(1)]
    assert ays == ["2025-26", "2026-27"]


def test_uow_exposes_itr_returns(db):
    from app.repositories.unit_of_work import UnitOfWork

    uow = UnitOfWork(db)
    r = uow.itr_returns.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    assert r.id is not None
