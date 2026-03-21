import pytest
from tests.factories import make_asset


def test_create_asset_returns_201(client):
    resp = client.post("/assets", json=make_asset())
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Asset"
    assert data["asset_type"] == "STOCK_IN"
    assert "id" in data


def test_create_asset_missing_required_field_returns_422(client):
    resp = client.post("/assets", json={"name": "Missing Type"})
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_list_assets_filter_by_type(client):
    client.post("/assets", json=make_asset(asset_type="STOCK_IN"))
    client.post("/assets", json=make_asset(name="MF Asset", asset_type="MF", identifier="INF123"))
    resp = client.get("/assets?type=MF")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["asset_type"] == "MF"


def test_list_assets_filter_by_active_false(client):
    r1 = client.post("/assets", json=make_asset(name="Active"))
    assert r1.status_code == 201
    r2 = client.post("/assets", json=make_asset(name="Inactive"))
    assert r2.status_code == 201
    asset_id = r2.json()["id"]
    client.delete(f"/assets/{asset_id}")
    resp = client.get("/assets?active=false")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_active"] is False


def test_get_asset_not_found_returns_404(client):
    resp = client.get("/assets/99999")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


def test_update_asset(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.put(f"/assets/{asset_id}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


def test_delete_asset_soft_deletes(client, seeded_asset):
    asset_id = seeded_asset["id"]
    resp = client.delete(f"/assets/{asset_id}")
    assert resp.status_code == 200
    # Asset should still exist in DB with is_active=False
    get_resp = client.get(f"/assets/{asset_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False


class TestFixInactiveStocks:
    def test_fix_inactive_stocks_marks_exited_asset(self, client, db):
        """POST /assets/fix-inactive-stocks marks assets with net_units=0 as inactive."""
        from datetime import date
        from app.models.asset import Asset, AssetType, AssetClass
        from app.models.transaction import Transaction, TransactionType
        import uuid

        # Create a stock with BUY 10 + SELL 10 (fully exited) but is_active still True
        asset = Asset(
            name="Exited Stock Fix",
            identifier="INE000EX9998",
            asset_type=AssetType.STOCK_IN,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            is_active=True,
        )
        db.add(asset)
        db.flush()

        buy = Transaction(
            txn_id=f"test_{uuid.uuid4().hex}",
            asset_id=asset.id,
            type=TransactionType.BUY,
            date=date(2023, 1, 1),
            units=10.0,
            price_per_unit=100.0,
            amount_inr=-100_000,
            charges_inr=0,
            lot_id=str(uuid.uuid4()),
        )
        sell = Transaction(
            txn_id=f"test_{uuid.uuid4().hex}",
            asset_id=asset.id,
            type=TransactionType.SELL,
            date=date(2023, 6, 1),
            units=10.0,
            price_per_unit=120.0,
            amount_inr=120_000,
            charges_inr=0,
        )
        db.add_all([buy, sell])
        db.commit()

        resp = client.post("/assets/fix-inactive-stocks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fixed"] == 1
        assert "total_checked" in data

        # Reload and verify
        db.expire_all()
        db.refresh(asset)
        assert asset.is_active is False

    def test_fix_inactive_stocks_idempotent(self, client, db):
        """Running fix-inactive-stocks twice doesn't change already-inactive assets."""
        from datetime import date
        from app.models.asset import Asset, AssetType, AssetClass
        from app.models.transaction import Transaction, TransactionType
        import uuid

        asset = Asset(
            name="Exited Stock Idem",
            identifier="INE000EX9997",
            asset_type=AssetType.STOCK_IN,
            asset_class=AssetClass.EQUITY,
            currency="INR",
            is_active=True,
        )
        db.add(asset)
        db.flush()
        buy = Transaction(
            txn_id=f"test_{uuid.uuid4().hex}",
            asset_id=asset.id,
            type=TransactionType.BUY,
            date=date(2023, 1, 1),
            units=5.0,
            price_per_unit=200.0,
            amount_inr=-100_000,
            charges_inr=0,
            lot_id=str(uuid.uuid4()),
        )
        sell = Transaction(
            txn_id=f"test_{uuid.uuid4().hex}",
            asset_id=asset.id,
            type=TransactionType.SELL,
            date=date(2023, 6, 1),
            units=5.0,
            price_per_unit=240.0,
            amount_inr=120_000,
            charges_inr=0,
        )
        db.add_all([buy, sell])
        db.commit()

        # Run twice
        r1 = client.post("/assets/fix-inactive-stocks")
        r2 = client.post("/assets/fix-inactive-stocks")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Second run should fix 0 (already inactive)
        assert r2.json()["fixed"] == 0
