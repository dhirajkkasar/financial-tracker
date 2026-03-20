"""
Integration tests for the import flow (T2.2.4).

TDD order: tests written first — they must be RED before implementation exists.
"""

import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def zerodha_csv_bytes():
    return (FIXTURES / "tradebook-EQ-2023.csv").read_bytes()


@pytest.fixture
def nps_csv_bytes():
    return (FIXTURES / "nps_tier_1.csv").read_bytes()


@pytest.fixture
def cas_pdf_bytes():
    return (FIXTURES / "test_cas.pdf").read_bytes()


@pytest.fixture
def ppf_pdf_bytes():
    return (FIXTURES / "PPF_account_statement.pdf").read_bytes()


@pytest.fixture
def epf_pdf_bytes():
    return (FIXTURES / "PYKRP00192140000152747.pdf").read_bytes()


class TestBrokerCSVPreview:
    def test_preview_returns_new_and_duplicate_counts(self, client, zerodha_csv_bytes):
        resp = client.post(
            "/import/broker-csv?broker=zerodha",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "preview_id" in data
        assert isinstance(data["new_count"], int)
        assert isinstance(data["duplicate_count"], int)
        assert data["new_count"] > 0
        assert data["duplicate_count"] == 0
        assert len(data["transactions"]) == data["new_count"] + data["duplicate_count"]

    def test_preview_unknown_broker_returns_422(self, client, zerodha_csv_bytes):
        resp = client.post(
            "/import/broker-csv?broker=unknown_broker",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 422

    def test_commit_writes_new_transactions(self, client, zerodha_csv_bytes):
        # Step 1: Preview
        resp = client.post(
            "/import/broker-csv?broker=zerodha",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        preview_data = resp.json()
        preview_id = preview_data["preview_id"]
        new_count = preview_data["new_count"]

        # Step 2: Commit
        resp = client.post("/import/commit", json={"preview_id": preview_id})
        assert resp.status_code == 200
        commit_data = resp.json()
        assert commit_data["created_count"] == new_count
        assert commit_data["skipped_count"] == 0

    def test_commit_skips_duplicates(self, client, zerodha_csv_bytes):
        # First import: preview + commit
        resp = client.post(
            "/import/broker-csv?broker=zerodha",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        client.post("/import/commit", json={"preview_id": resp.json()["preview_id"]})

        # Second preview of the same file — all should be duplicates now
        resp = client.post(
            "/import/broker-csv?broker=zerodha",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_count"] == 0
        assert data["duplicate_count"] > 0

    def test_reimport_same_file_zero_new(self, client, zerodha_csv_bytes):
        # First full import
        resp = client.post(
            "/import/broker-csv?broker=zerodha",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        client.post("/import/commit", json={"preview_id": resp.json()["preview_id"]})

        # Second import: preview then commit
        resp = client.post(
            "/import/broker-csv?broker=zerodha",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        preview_id = resp.json()["preview_id"]

        resp = client.post("/import/commit", json={"preview_id": preview_id})
        assert resp.status_code == 200
        assert resp.json()["created_count"] == 0

    def test_commit_expired_preview_id_returns_404(self, client):
        resp = client.post("/import/commit", json={"preview_id": str(uuid.uuid4())})
        assert resp.status_code == 404

    def test_commit_missing_preview_id_returns_422(self, client):
        resp = client.post("/import/commit", json={})
        assert resp.status_code == 422


class TestNPSCSVPreview:
    def test_nps_preview_returns_preview_id(self, client, nps_csv_bytes):
        resp = client.post(
            "/import/nps-csv",
            files={"file": ("nps.csv", nps_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "preview_id" in data
        assert "new_count" in data
        assert "duplicate_count" in data

    def test_nps_commit_writes_contributions(self, client, nps_csv_bytes):
        resp = client.post(
            "/import/nps-csv",
            files={"file": ("nps.csv", nps_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        preview_id = resp.json()["preview_id"]
        new_count = resp.json()["new_count"]

        resp = client.post("/import/commit", json={"preview_id": preview_id})
        assert resp.status_code == 200
        assert resp.json()["created_count"] == new_count

    def test_nps_reimport_is_idempotent(self, client, nps_csv_bytes):
        # First import
        resp = client.post(
            "/import/nps-csv",
            files={"file": ("nps.csv", nps_csv_bytes, "text/csv")},
        )
        client.post("/import/commit", json={"preview_id": resp.json()["preview_id"]})

        # Second import — all duplicates
        resp = client.post(
            "/import/nps-csv",
            files={"file": ("nps.csv", nps_csv_bytes, "text/csv")},
        )
        assert resp.json()["new_count"] == 0


class TestCASPDFPreview:
    def test_cas_preview_returns_preview_id(self, client, cas_pdf_bytes):
        resp = client.post(
            "/import/cas-pdf",
            files={"file": ("cas.pdf", cas_pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "preview_id" in data
        assert "new_count" in data
        assert "duplicate_count" in data

    def test_cas_commit_writes_transactions(self, client, cas_pdf_bytes):
        resp = client.post(
            "/import/cas-pdf",
            files={"file": ("cas.pdf", cas_pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200
        preview_id = resp.json()["preview_id"]
        new_count = resp.json()["new_count"]

        resp = client.post("/import/commit", json={"preview_id": preview_id})
        assert resp.status_code == 200
        assert resp.json()["created_count"] == new_count

    def test_cas_reimport_is_idempotent(self, client, cas_pdf_bytes):
        # First import
        resp = client.post(
            "/import/cas-pdf",
            files={"file": ("cas.pdf", cas_pdf_bytes, "application/pdf")},
        )
        client.post("/import/commit", json={"preview_id": resp.json()["preview_id"]})

        # Second import — all duplicates
        resp = client.post(
            "/import/cas-pdf",
            files={"file": ("cas.pdf", cas_pdf_bytes, "application/pdf")},
        )
        assert resp.json()["new_count"] == 0


class TestPPFImport:
    def test_ppf_import_returns_200(self, client, ppf_pdf_bytes, db):
        # Pre-create the PPF asset so the import can match it
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="PPF — SBI",
            identifier="32256576916",
            asset_type=AssetType.PPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        resp = client.post(
            "/import/ppf-pdf",
            files={"file": ("ppf.pdf", ppf_pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200

    def test_ppf_import_writes_two_transactions(self, client, ppf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="PPF — SBI",
            identifier="32256576916",
            asset_type=AssetType.PPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        resp = client.post(
            "/import/ppf-pdf",
            files={"file": ("ppf.pdf", ppf_pdf_bytes, "application/pdf")},
        )
        data = resp.json()
        assert data["inserted"] == 2
        assert data["skipped"] == 0

    def test_ppf_import_creates_valuation(self, client, ppf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="PPF — SBI",
            identifier="32256576916",
            asset_type=AssetType.PPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        resp = client.post(
            "/import/ppf-pdf",
            files={"file": ("ppf.pdf", ppf_pdf_bytes, "application/pdf")},
        )
        data = resp.json()
        assert data["valuation_created"] is True
        # Closing balance = 42947.00 INR
        assert data["valuation_value"] == 42947.0

    def test_ppf_reimport_is_idempotent(self, client, ppf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="PPF — SBI",
            identifier="32256576916",
            asset_type=AssetType.PPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        # First import
        client.post(
            "/import/ppf-pdf",
            files={"file": ("ppf.pdf", ppf_pdf_bytes, "application/pdf")},
        )
        # Second import — should skip duplicates
        resp = client.post(
            "/import/ppf-pdf",
            files={"file": ("ppf.pdf", ppf_pdf_bytes, "application/pdf")},
        )
        data = resp.json()
        assert data["inserted"] == 0
        assert data["skipped"] == 2

    def test_ppf_import_no_asset_returns_404(self, client, ppf_pdf_bytes):
        resp = client.post(
            "/import/ppf-pdf",
            files={"file": ("ppf.pdf", ppf_pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 404


class TestEPFImport:
    def test_epf_import_returns_200(self, client, epf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="EPF — IBM INDIA PVT LTD",
            identifier="PYKRP00192140000152747",
            asset_type=AssetType.EPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        resp = client.post(
            "/import/epf-pdf",
            files={"file": ("epf.pdf", epf_pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200

    def test_epf_import_writes_transactions(self, client, epf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="EPF — IBM INDIA PVT LTD",
            identifier="PYKRP00192140000152747",
            asset_type=AssetType.EPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        resp = client.post(
            "/import/epf-pdf",
            files={"file": ("epf.pdf", epf_pdf_bytes, "application/pdf")},
        )
        data = resp.json()
        assert data["epf_inserted"] > 0
        assert data["epf_skipped"] == 0

    def test_epf_import_creates_eps_asset(self, client, epf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="EPF — IBM INDIA PVT LTD",
            identifier="PYKRP00192140000152747",
            asset_type=AssetType.EPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        resp = client.post(
            "/import/epf-pdf",
            files={"file": ("epf.pdf", epf_pdf_bytes, "application/pdf")},
        )
        data = resp.json()
        assert data["eps_asset_created"] is True
        assert data["eps_asset_id"] is not None

    def test_epf_import_creates_epf_valuation(self, client, epf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="EPF — IBM INDIA PVT LTD",
            identifier="PYKRP00192140000152747",
            asset_type=AssetType.EPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        resp = client.post(
            "/import/epf-pdf",
            files={"file": ("epf.pdf", epf_pdf_bytes, "application/pdf")},
        )
        data = resp.json()
        assert data["epf_valuation_created"] is True
        # Net balance = 0 (fully transferred)
        assert data["epf_valuation_value"] == 0.0

    def test_epf_import_marks_asset_inactive_when_zero_balance(self, client, epf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="EPF — IBM INDIA PVT LTD",
            identifier="PYKRP00192140000152747",
            asset_type=AssetType.EPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()
        asset_id = asset.id

        client.post(
            "/import/epf-pdf",
            files={"file": ("epf.pdf", epf_pdf_bytes, "application/pdf")},
        )

        db.expire_all()
        updated_asset = db.query(Asset).filter(Asset.id == asset_id).first()
        assert updated_asset.is_active is False

    def test_epf_reimport_is_idempotent(self, client, epf_pdf_bytes, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="EPF — IBM INDIA PVT LTD",
            identifier="PYKRP00192140000152747",
            asset_type=AssetType.EPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()

        # First import
        client.post(
            "/import/epf-pdf",
            files={"file": ("epf.pdf", epf_pdf_bytes, "application/pdf")},
        )
        # Second import — all duplicates
        resp = client.post(
            "/import/epf-pdf",
            files={"file": ("epf.pdf", epf_pdf_bytes, "application/pdf")},
        )
        data = resp.json()
        assert data["epf_inserted"] == 0
        assert data["epf_skipped"] > 0

    def test_epf_import_no_asset_returns_404(self, client, epf_pdf_bytes):
        resp = client.post(
            "/import/epf-pdf",
            files={"file": ("epf.pdf", epf_pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 404
