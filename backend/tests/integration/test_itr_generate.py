"""End-to-end: assemble -> generate -> validate -> download the ITR-2 JSON."""
from datetime import date

from app.engine.itr.schema_validation import ValidationIssue, ValidationReport
from app.models.asset import Asset, AssetClass, AssetType
from app.models.itr_return import ItrReturn
from app.models.transaction import Transaction, TransactionType
from tests.factories import make_member


def _seed_short_term_equity(db, member_id: int):
    """Buy 2025-01-01, sell 2025-06-01 -> Rs 10,000 STCG u/s 111A -> ITR-2."""
    asset = Asset(
        member_id=member_id, name="Reliance", identifier="INE002A01018",
        asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY,
    )
    db.add(asset)
    db.flush()
    db.add(Transaction(
        txn_id="buy-st", asset_id=asset.id, type=TransactionType.BUY,
        date=date(2025, 1, 1), units=100.0, price_per_unit=500.0, amount_inr=-5_000_000,
    ))
    db.add(Transaction(
        txn_id="sell-st", asset_id=asset.id, type=TransactionType.SELL,
        date=date(2025, 6, 1), units=100.0, price_per_unit=600.0, amount_inr=6_000_000,
    ))
    db.flush()


def _prepared(client, member_id: int):
    return client.post(
        "/itr/returns", json={"member_id": member_id, "fy": "2025-26"}
    ).json()


def _assembled(client, db):
    # A valid *individual* PAN (4th char "P") is required by the schema's
    # Verification/Declaration pattern.
    m = make_member(db, pan="ABCPE1234F", name="Test Taxpayer")
    _seed_short_term_equity(db, m.id)
    r = _prepared(client, m.id)
    assert client.post(f"/itr/returns/{r['id']}/assemble").status_code == 200
    return r


def test_generate_validates_and_persists(client, db):
    r = _assembled(client, db)
    resp = client.post(f"/itr/returns/{r['id']}/generate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "generated"
    assert body["form_type"] == "ITR2"
    assert body["schema_version"] == "V1.2"
    assert body["generated_at"]

    record = db.query(ItrReturn).filter(ItrReturn.id == r["id"]).first()
    assert record.output_json
    assert record.status == "generated"


def test_download_returns_the_generated_json(client, db):
    r = _assembled(client, db)
    client.post(f"/itr/returns/{r['id']}/generate")

    resp = client.get(f"/itr/returns/{r['id']}/json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert "attachment" in resp.headers["content-disposition"]

    document = resp.json()
    assert document["ITR"]["ITR2"]["Form_ITR2"]["FormName"] == "ITR-2"


def test_validation_endpoint_reports_ok(client, db):
    r = _assembled(client, db)
    body = client.get(f"/itr/returns/{r['id']}/validation").json()
    assert body["ok"] is True
    assert body["form"] == "ITR-2"
    assert body["schema_version"] == "V1.2"
    assert body["issues"] == []


def test_generate_before_assemble_is_422(client, db):
    m = make_member(db, pan="ABCPE1234F")
    r = _prepared(client, m.id)
    resp = client.post(f"/itr/returns/{r['id']}/generate")
    assert resp.status_code == 422
    assert "assemble" in resp.json()["error"]["message"].lower()


def test_validation_failure_is_422_and_writes_nothing(client, db, monkeypatch):
    r = _assembled(client, db)

    def _failing(*_args, **_kwargs):
        return ValidationReport(issues=[ValidationIssue("PartB-TI.TotalIncome", "boom", "semantic")])

    monkeypatch.setattr("app.services.itr_json_service.validate_itr_json", _failing)
    resp = client.post(f"/itr/returns/{r['id']}/generate")
    assert resp.status_code == 422
    assert "PartB-TI.TotalIncome" in resp.json()["error"]["message"]

    record = db.query(ItrReturn).filter(ItrReturn.id == r["id"]).first()
    assert record.output_json is None
    assert record.status == "draft"


def test_generate_unknown_return_is_404(client):
    assert client.post("/itr/returns/99999/generate").status_code == 404


def test_download_before_generate_is_404(client, db):
    m = make_member(db, pan="ABCPE1234F")
    r = _prepared(client, m.id)
    assert client.get(f"/itr/returns/{r['id']}/json").status_code == 404
