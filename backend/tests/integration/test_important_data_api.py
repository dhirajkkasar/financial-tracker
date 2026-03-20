import pytest


def make_important_data(**overrides):
    return {
        "category": "BANK",
        "label": "HDFC Savings",
        "fields": {"account_number": "12345", "ifsc": "HDFC0001234"},
        **overrides,
    }


def test_create_important_data(client):
    resp = client.post("/important-data", json=make_important_data())
    assert resp.status_code == 201
    data = resp.json()
    assert data["label"] == "HDFC Savings"
    assert data["category"] == "BANK"
    assert data["fields"]["account_number"] == "12345"


def test_list_by_category(client):
    client.post("/important-data", json=make_important_data(category="BANK", label="HDFC"))
    client.post("/important-data", json=make_important_data(category="IDENTITY", label="PAN", fields={"pan": "ABCDE1234F"}))

    resp = client.get("/important-data?category=BANK")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["category"] == "BANK"


def test_update_important_data(client):
    create_resp = client.post("/important-data", json=make_important_data())
    item_id = create_resp.json()["id"]

    resp = client.put(f"/important-data/{item_id}", json={"label": "Updated Label"})
    assert resp.status_code == 200
    assert resp.json()["label"] == "Updated Label"


def test_delete_important_data(client):
    create_resp = client.post("/important-data", json=make_important_data())
    item_id = create_resp.json()["id"]

    del_resp = client.delete(f"/important-data/{item_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/important-data/{item_id}")
    assert get_resp.status_code == 404


def test_get_important_data_not_found(client):
    resp = client.get("/important-data/99999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_list_all_without_filter(client):
    client.post("/important-data", json=make_important_data(label="Item 1"))
    client.post("/important-data", json=make_important_data(label="Item 2"))
    resp = client.get("/important-data")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
