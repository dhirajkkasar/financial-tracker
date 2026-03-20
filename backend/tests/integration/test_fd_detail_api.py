import pytest
from tests.factories import make_asset


def make_fd_detail(**overrides):
    return {
        "bank": "SBI",
        "fd_type": "FD",
        "principal_amount": 100000.0,
        "interest_rate_pct": 6.5,
        "compounding": "QUARTERLY",
        "start_date": "2023-01-01",
        "maturity_date": "2025-01-01",
        **overrides,
    }


def test_create_fd_detail(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.post(f"/assets/{asset_id}/fd-detail", json=make_fd_detail())
    assert resp.status_code == 201
    data = resp.json()
    assert data["bank"] == "SBI"
    assert data["principal_amount"] == 100000.0
    assert data["asset_id"] == asset_id


def test_create_fd_detail_duplicate_returns_409(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp1 = client.post(f"/assets/{asset_id}/fd-detail", json=make_fd_detail())
    assert resp1.status_code == 201
    resp2 = client.post(f"/assets/{asset_id}/fd-detail", json=make_fd_detail())
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "DUPLICATE"


def test_create_rd_detail_stores_monthly_installment(client):
    # Create RD asset
    rd_asset_resp = client.post(
        "/assets",
        json=make_asset(name="My RD", asset_type="RD"),
    )
    assert rd_asset_resp.status_code == 201
    asset_id = rd_asset_resp.json()["id"]

    monthly_installment = 5000.0
    resp = client.post(
        f"/assets/{asset_id}/fd-detail",
        json=make_fd_detail(fd_type="RD", principal_amount=monthly_installment),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["fd_type"] == "RD"
    # principal_amount for RD is monthly installment — verify roundtrip
    assert data["principal_amount"] == monthly_installment


def test_get_fd_detail(client, seeded_asset):
    asset_id = seeded_asset["id"]
    client.post(f"/assets/{asset_id}/fd-detail", json=make_fd_detail())
    resp = client.get(f"/assets/{asset_id}/fd-detail")
    assert resp.status_code == 200
    assert resp.json()["bank"] == "SBI"


def test_get_fd_detail_not_found(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.get(f"/assets/{asset_id}/fd-detail")
    assert resp.status_code == 404
