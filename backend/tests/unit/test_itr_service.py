"""ItrService — prepare/seed/read/update of a per-member, per-AY return."""
import pytest

from app.repositories.unit_of_work import UnitOfWork
from app.services.itr_service import ItrService
from tests.factories import make_member


@pytest.fixture
def svc(db):
    return ItrService(lambda: UnitOfWork(db))


def test_prepare_creates_return_with_derived_ay(svc, db):
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    r = svc.prepare(member_id=m.id, fy_label="2025-26")
    assert r.ay_label == "2026-27"
    assert r.form_type == "ITR2"
    assert r.status == "draft"


def test_prepare_is_idempotent(svc, db):
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    a = svc.prepare(member_id=m.id, fy_label="2025-26")
    b = svc.prepare(member_id=m.id, fy_label="2025-26")
    assert a.id == b.id


def test_prepare_seeds_identity_from_member(svc, db):
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    r = svc.prepare(member_id=m.id, fy_label="2025-26")
    inp = svc.get_input(r.id)
    assert inp.pan == "ABCDE1234F"
    assert inp.name == "Dhiraj"
    assert inp.member_id == m.id


def test_prepare_does_not_clobber_existing_input(svc, db):
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    r = svc.prepare(member_id=m.id, fy_label="2025-26")
    svc.update_input(r.id, {"other_income": {"savings_interest": 1234.0}})
    svc.prepare(member_id=m.id, fy_label="2025-26")
    assert svc.get_input(r.id).other_income.savings_interest == 1234.0


def test_prepare_rejects_unknown_member(svc, db):
    from app.middleware.error_handler import AppError

    with pytest.raises(AppError):
        svc.prepare(member_id=999, fy_label="2025-26")


def test_prepare_rejects_bad_fy(svc, db):
    from app.middleware.error_handler import ValidationError

    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    with pytest.raises(ValidationError):
        svc.prepare(member_id=m.id, fy_label="2025/26")


def test_prepare_seeds_fixed_blocks_from_previous_ay(svc, db):
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    prior = svc.prepare(member_id=m.id, fy_label="2024-25")
    svc.update_input(prior.id, {
        "address": {"city": "Pune"},
        "bank_accounts": [{"bank_name": "HDFC", "account_number": "123"}],
        "creation": {"sw_provider_id": "SW00000001"},
    })
    nxt = svc.prepare(member_id=m.id, fy_label="2025-26")
    inp = svc.get_input(nxt.id)
    assert inp.address.city == "Pune"
    assert inp.bank_accounts[0].bank_name == "HDFC"
    assert inp.creation["sw_provider_id"] == "SW00000001"


def test_seed_does_not_copy_prior_year_income(svc, db):
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    prior = svc.prepare(member_id=m.id, fy_label="2024-25")
    svc.update_input(prior.id, {
        "other_income": {"savings_interest": 9999.0, "dividends": 500.0},
        "salary": [{"employer_name": "ACME", "gross_salary": 1000000.0}],
    })
    nxt = svc.prepare(member_id=m.id, fy_label="2025-26")
    inp = svc.get_input(nxt.id)
    assert inp.other_income.savings_interest == 0.0
    assert inp.other_income.dividends == 0.0
    assert inp.salary == []


def test_list_for_member(svc, db):
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    svc.prepare(member_id=m.id, fy_label="2024-25")
    svc.prepare(member_id=m.id, fy_label="2025-26")
    ays = [r.ay_label for r in svc.list_for_member(m.id)]
    assert ays == ["2025-26", "2026-27"]


def test_get_unknown_returns_none(svc, db):
    assert svc.get(12345) is None
