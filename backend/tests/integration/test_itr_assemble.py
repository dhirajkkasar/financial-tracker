"""End-to-end: seed portfolio + input, assemble the ITR draft over HTTP."""
from datetime import date

from app.models.asset import Asset, AssetClass, AssetType
from app.models.itr_return import ItrReturn
from app.models.transaction import Transaction, TransactionType
from tests.factories import make_member


def _seed_equity(db, member_id: int, *, isin="INE002A01018", buy="2023-01-01",
                 buy_paise=-5_000_000, sell_paise=8_000_000, suffix=""):
    asset = Asset(
        member_id=member_id, name="Reliance", identifier=isin,
        asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY,
    )
    db.add(asset)
    db.flush()
    db.add(Transaction(
        txn_id=f"buy-{isin}{suffix}", asset_id=asset.id, type=TransactionType.BUY,
        date=date.fromisoformat(buy), units=100.0, price_per_unit=500.0,
        amount_inr=buy_paise,
    ))
    db.add(Transaction(
        txn_id=f"sell-{isin}{suffix}", asset_id=asset.id, type=TransactionType.SELL,
        date=date(2025, 6, 1), units=100.0, price_per_unit=800.0,
        amount_inr=sell_paise,
    ))
    db.flush()
    return asset


def _prepared(client, member_id: int):
    return client.post(
        "/itr/returns", json={"member_id": member_id, "fy": "2025-26"}
    ).json()


def test_assemble_builds_draft_from_portfolio_and_input(client, db):
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    _seed_equity(db, m.id)  # long-term -> Schedule 112A
    r = _prepared(client, m.id)
    client.put(f"/itr/returns/{r['id']}/input", json={
        "salary": [{"total_taxable_income": 1_200_000.0}],
        "other_income": {"savings_interest": 10_000.0},
    })

    resp = client.post(f"/itr/returns/{r['id']}/assemble")
    assert resp.status_code == 200
    body = resp.json()

    # 112A gain is below the Rs 1.25L limit and there is no other trigger -> ITR-1.
    assert body["form"] == "ITR1"
    assert body["salary_taxable"] == 1_200_000.0
    assert body["buckets"]["ltcg_112a"] == 30_000.0     # 100 x (800-500)
    assert body["buckets"]["other_interest"] == 10_000.0
    assert body["schedule_112a"]["balance"] == 30_000
    assert body["schedule_112a"]["rows"][0]["isin"] == "INNOTREQUIRD"
    assert body["tax"]["ltcg_112a_taxable"] == 0.0      # below the 1.25L exemption


def test_assemble_112a_above_exemption_forces_itr2(client, db):
    m = make_member(db)
    # 100 units bought at 500, sold at 2000 -> gain 1.5L (above the 1.25L limit).
    _seed_equity(db, m.id, buy_paise=-5_000_000, sell_paise=20_000_000)
    r = _prepared(client, m.id)

    body = client.post(f"/itr/returns/{r['id']}/assemble").json()
    assert body["form"] == "ITR2"
    assert body["buckets"]["ltcg_112a"] == 150_000.0
    assert body["tax"]["ltcg_112a_taxable"] == 25_000.0  # 1.5L - 1.25L


def test_assemble_persists_the_draft_and_form(client, db):
    m = make_member(db)
    _seed_equity(db, m.id)
    r = _prepared(client, m.id)
    client.post(f"/itr/returns/{r['id']}/assemble")

    record = db.query(ItrReturn).filter(ItrReturn.id == r["id"]).first()
    assert record.draft_json
    assert record.form_type == "ITR1"
    assert record.status == "draft"


def test_assemble_is_idempotent(client, db):
    m = make_member(db)
    _seed_equity(db, m.id)
    r = _prepared(client, m.id)
    first = client.post(f"/itr/returns/{r['id']}/assemble").json()
    second = client.post(f"/itr/returns/{r['id']}/assemble").json()
    assert first == second


def test_assemble_unknown_return_is_404(client):
    assert client.post("/itr/returns/99999/assemble").status_code == 404


def test_assemble_stcg_short_term_goes_to_111a(client, db):
    m = make_member(db)
    # Bought 2025-01-01, sold 2025-06-01 -> short term.
    _seed_equity(db, m.id, buy="2025-01-01", buy_paise=-5_000_000, sell_paise=6_000_000)
    r = _prepared(client, m.id)
    body = client.post(f"/itr/returns/{r['id']}/assemble").json()
    assert body["buckets"]["stcg_111a"] == 10_000.0
    assert body["buckets"]["ltcg_112a"] == 0.0
