"""ITR API — prepare, list, detail, input update."""


def _member(client, pan="ABCDE1234F", name="Dhiraj"):
    return client.post("/members", json={"pan": pan, "name": name}).json()


def test_fiscal_years_returns_list(client):
    resp = client.get("/itr/fiscal-years")
    assert resp.status_code == 200
    fys = resp.json()["fiscal_years"]
    assert isinstance(fys, list) and fys == sorted(fys) and len(fys) > 0


def test_list_returns_empty(client):
    m = _member(client)
    resp = client.get(f"/itr/returns?member_id={m['id']}")
    assert resp.status_code == 200
    assert resp.json()["returns"] == []


def test_prepare_creates_and_lists(client):
    m = _member(client)
    resp = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["ay_label"] == "2026-27"
    assert body["form_type"] == "ITR2"
    assert body["status"] == "draft"

    listed = client.get(f"/itr/returns?member_id={m['id']}").json()["returns"]
    assert [r["id"] for r in listed] == [body["id"]]


def test_prepare_is_idempotent(client):
    m = _member(client)
    a = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}).json()
    b = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}).json()
    assert a["id"] == b["id"]


def test_prepare_rejects_bad_fy(client):
    m = _member(client)
    resp = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025/26"})
    assert resp.status_code == 422


def test_prepare_unknown_member_is_404(client):
    resp = client.post("/itr/returns", json={"member_id": 999, "fy": "2025-26"})
    assert resp.status_code == 404


def test_detail_includes_input_document(client):
    m = _member(client)
    r = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}).json()
    resp = client.get(f"/itr/returns/{r['id']}")
    assert resp.status_code == 200
    assert resp.json()["input"]["pan"] == "ABCDE1234F"


def test_detail_unknown_is_404(client):
    resp = client.get("/itr/returns/12345")
    assert resp.status_code == 404


def test_update_input_persists(client):
    m = _member(client)
    r = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"}).json()
    resp = client.put(
        f"/itr/returns/{r['id']}/input",
        json={"other_income": {"savings_interest": 4200.0}},
    )
    assert resp.status_code == 200
    assert resp.json()["input"]["other_income"]["savings_interest"] == 4200.0

    detail = client.get(f"/itr/returns/{r['id']}").json()
    assert detail["input"]["other_income"]["savings_interest"] == 4200.0


def test_returns_are_isolated_per_member(client):
    a = _member(client, pan="ABCDE1234F", name="A")
    b = _member(client, pan="ZYXWV9876Q", name="B")
    client.post("/itr/returns", json={"member_id": a["id"], "fy": "2025-26"})
    assert client.get(f"/itr/returns?member_id={b['id']}").json()["returns"] == []
