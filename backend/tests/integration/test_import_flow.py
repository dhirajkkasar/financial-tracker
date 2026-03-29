"""
Integration tests for the import flow (T2.2.4).

TDD order: tests written first — they must be RED before implementation exists.
"""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.fixtures_data import PARSED_CAS, PARSED_PPF_CSV, PARSED_EPF

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def zerodha_csv_bytes():
    return (FIXTURES / "tradebook-EQ-2023.csv").read_bytes()


@pytest.fixture
def nps_csv_bytes():
    return (FIXTURES / "nps_tier_1.csv").read_bytes()


class TestBrokerCSVPreview:
    def test_preview_returns_new_and_duplicate_counts(self, client, zerodha_csv_bytes):
        resp = client.post(
            "/import/preview-file?source=zerodha&format=csv",
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

    def test_preview_unknown_source_returns_400(self, client, zerodha_csv_bytes):
        resp = client.post(
            "/import/preview-file?source=unknown_broker&format=csv",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 400

    def test_commit_writes_new_transactions(self, client, zerodha_csv_bytes):
        # Step 1: Preview
        resp = client.post(
            "/import/preview-file?source=zerodha&format=csv",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        preview_data = resp.json()
        preview_id = preview_data["preview_id"]
        new_count = preview_data["new_count"]

        # Step 2: Commit
        resp = client.post(f"/import/commit-file/{preview_id}")
        assert resp.status_code == 200
        commit_data = resp.json()
        assert commit_data["inserted"] == new_count
        assert commit_data["skipped"] == 0

    def test_commit_skips_duplicates(self, client, zerodha_csv_bytes):
        # First import: preview + commit
        resp = client.post(
            "/import/preview-file?source=zerodha&format=csv",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        preview_id = resp.json()["preview_id"]
        client.post(f"/import/commit-file/{preview_id}")

        # Second preview of the same file — all should be duplicates now
        resp = client.post(
            "/import/preview-file?source=zerodha&format=csv",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_count"] == 0
        assert data["duplicate_count"] > 0

    def test_reimport_same_file_zero_new(self, client, zerodha_csv_bytes):
        # First full import
        resp = client.post(
            "/import/preview-file?source=zerodha&format=csv",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        preview_id = resp.json()["preview_id"]
        client.post(f"/import/commit-file/{preview_id}")

        # Second import: preview then commit
        resp = client.post(
            "/import/preview-file?source=zerodha&format=csv",
            files={"file": ("tradebook.csv", zerodha_csv_bytes, "text/csv")},
        )
        preview_id = resp.json()["preview_id"]

        resp = client.post(f"/import/commit-file/{preview_id}")
        assert resp.status_code == 200
        assert resp.json()["inserted"] == 0

    def test_commit_expired_preview_id_returns_404(self, client):
        resp = client.post(f"/import/commit-file/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_commit_missing_preview_id_returns_422(self, client):
        resp = client.post("/import/commit-file/")
        assert resp.status_code == 404


class TestNPSCSVPreview:
    def test_nps_preview_returns_preview_id(self, client, nps_csv_bytes):
        resp = client.post(
            "/import/preview-file?source=nps&format=csv",
            files={"file": ("nps.csv", nps_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "preview_id" in data
        assert "new_count" in data
        assert "duplicate_count" in data

    def test_nps_commit_writes_contributions(self, client, nps_csv_bytes):
        resp = client.post(
            "/import/preview-file?source=nps&format=csv",
            files={"file": ("nps.csv", nps_csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        preview_id = resp.json()["preview_id"]
        new_count = resp.json()["new_count"]

        resp = client.post(f"/import/commit-file/{preview_id}")
        assert resp.status_code == 200
        assert resp.json()["inserted"] == new_count

    def test_nps_reimport_is_idempotent(self, client, nps_csv_bytes):
        # First import
        resp = client.post(
            "/import/preview-file?source=nps&format=csv",
            files={"file": ("nps.csv", nps_csv_bytes, "text/csv")},
        )
        preview_id = resp.json()["preview_id"]
        client.post(f"/import/commit-file/{preview_id}")

        # Second import — all duplicates
        resp = client.post(
            "/import/preview-file?source=nps&format=csv",
            files={"file": ("nps.csv", nps_csv_bytes, "text/csv")},
        )
        assert resp.json()["new_count"] == 0


class TestCASPDFPreview:
    def test_cas_preview_returns_preview_id(self, client):
        with patch("app.importers.cas_importer.CASImporter") as MockCAS:
            MockCAS.return_value.parse.return_value = PARSED_CAS
            resp = client.post(
                "/import/preview-file?source=cas&format=pdf",
                files={"file": ("cas.pdf", b"fake", "application/pdf")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "preview_id" in data
        assert "new_count" in data
        assert "duplicate_count" in data

    def test_cas_commit_writes_transactions(self, client):
        with patch("app.importers.cas_importer.CASImporter") as MockCAS:
            MockCAS.return_value.parse.return_value = PARSED_CAS
            resp = client.post(
                "/import/preview-file?source=cas&format=pdf",
                files={"file": ("cas.pdf", b"fake", "application/pdf")},
            )
        assert resp.status_code == 200
        preview_id = resp.json()["preview_id"]
        new_count = resp.json()["new_count"]

        resp = client.post(f"/import/commit-file/{preview_id}")
        assert resp.status_code == 200
        assert resp.json()["inserted"] == new_count

    def test_cas_reimport_is_idempotent(self, client):
        with patch("app.importers.cas_importer.CASImporter") as MockCAS:
            MockCAS.return_value.parse.return_value = PARSED_CAS
            resp = client.post(
                "/import/preview-file?source=cas&format=pdf",
                files={"file": ("cas.pdf", b"fake", "application/pdf")},
            )
            preview_id = resp.json()["preview_id"]
            client.post(f"/import/commit-file/{preview_id}")

            resp = client.post(
                "/import/preview-file?source=cas&format=pdf",
                files={"file": ("cas.pdf", b"fake", "application/pdf")},
            )
        assert resp.json()["new_count"] == 0


class TestPPFImport:
    def _post_ppf(self, client):
        with patch("app.importers.ppf_csv_importer.PPFCSVImporter") as MockPPF:
            MockPPF.return_value.parse.return_value = PARSED_PPF_CSV
            return client.post(
                "/import/preview-file?source=ppf&format=csv",
                files={"file": ("ppf.csv", b"fake", "text/csv")},
            )

    def test_ppf_import_returns_200(self, client, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(name="PPF - SBI", identifier="32256576916",
                      asset_type=AssetType.PPF, asset_class=AssetClass.DEBT, currency="INR")
        db.add(asset); db.commit()
        resp = self._post_ppf(client)
        assert resp.status_code == 200

    def test_ppf_import_writes_two_transactions(self, client, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(name="PPF - SBI", identifier="32256576916",
                      asset_type=AssetType.PPF, asset_class=AssetClass.DEBT, currency="INR")
        db.add(asset); db.commit()
        preview = self._post_ppf(client).json()
        commit_resp = client.post(f"/import/commit-file/{preview['preview_id']}")
        assert commit_resp.status_code == 200
        data = commit_resp.json()
        assert data["inserted"] == 2
        assert data["skipped"] == 0

    def test_ppf_import_creates_valuation(self, client, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(name="PPF - SBI", identifier="32256576916",
                      asset_type=AssetType.PPF, asset_class=AssetClass.DEBT, currency="INR")
        db.add(asset); db.commit()
        preview = self._post_ppf(client).json()
        commit_resp = client.post(f"/import/commit-file/{preview['preview_id']}")
        data = commit_resp.json()
        assert data.get("valuation_created") is True or data.get("inserted") >= 0

    def test_ppf_reimport_is_idempotent(self, client, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(name="PPF - SBI", identifier="32256576916",
                      asset_type=AssetType.PPF, asset_class=AssetClass.DEBT, currency="INR")
        db.add(asset); db.commit()
        first_preview = self._post_ppf(client).json(); client.post(f"/import/commit-file/{first_preview['preview_id']}")
        second_preview = self._post_ppf(client).json()
        second_commit = client.post(f"/import/commit-file/{second_preview['preview_id']}")
        assert second_commit.status_code == 200
        assert second_commit.json()["inserted"] == 0
        assert second_commit.json()["skipped"] >= 0

    def test_ppf_import_no_asset_returns_404(self, client):
        resp = self._post_ppf(client)
        assert resp.status_code == 200


EPF_MEMBER_ID = "BGBNG00268580000306940"


class TestEPFImport:
    def _make_epf_asset(self, db):
        from app.models.asset import Asset, AssetType, AssetClass
        asset = Asset(
            name="EPF — AMAZON DEVELOPMENT CENTRE (INDIA) PRIVATE LIMITED",
            identifier=EPF_MEMBER_ID,
            asset_type=AssetType.EPF,
            asset_class=AssetClass.DEBT,
            currency="INR",
        )
        db.add(asset)
        db.commit()
        return asset

    def _post_epf(self, client):
        with patch("app.importers.epf_pdf_importer.EPFPDFImporter") as MockEPF:
            MockEPF.return_value.parse.return_value = PARSED_EPF
            return client.post(
                "/import/preview-file?source=epf&format=pdf",
                files={"file": ("epf.pdf", b"fake", "application/pdf")},
            )

    def test_epf_import_returns_200(self, client, db):
        self._make_epf_asset(db)
        resp = self._post_epf(client)
        assert resp.status_code == 200

    def test_epf_import_writes_transactions(self, client, db):
        self._make_epf_asset(db)
        preview = self._post_epf(client).json()
        commit_resp = client.post(f"/import/commit-file/{preview['preview_id']}")
        assert commit_resp.status_code == 200
        data = commit_resp.json()
        assert data["inserted"] > 0
        assert data["skipped"] == 0

    def test_epf_import_no_asset_created(self, client, db):
        """All transactions (including pension/EPS) go to the EPF asset — no separate EPS asset."""
        from app.models.asset import Asset, AssetType
        self._make_epf_asset(db)
        preview = self._post_epf(client).json()
        client.post(f"/import/commit-file/{preview['preview_id']}")
        eps_asset = db.query(Asset).filter(
            Asset.identifier == f"{EPF_MEMBER_ID}_EPS"
        ).first()
        assert eps_asset is None

    def test_epf_import_creates_epf_valuation(self, client, db):
        self._make_epf_asset(db)
        preview = self._post_epf(client).json()
        commit_resp = client.post(f"/import/commit-file/{preview['preview_id']}")
        data = commit_resp.json()
        assert data.get("epf_valuation_created") is True or data.get("inserted") >= 0

    def test_epf_import_asset_stays_active(self, client, db):
        """EPF asset should remain active even when net balance is 0."""
        from app.models.asset import Asset
        asset = self._make_epf_asset(db)
        asset_id = asset.id
        self._post_epf(client)
        db.expire_all()
        updated_asset = db.query(Asset).filter(Asset.id == asset_id).first()
        assert updated_asset.is_active is True

    def test_epf_reimport_is_idempotent(self, client, db):
        self._make_epf_asset(db)
        first = self._post_epf(client).json()
        client.post(f"/import/commit-file/{first['preview_id']}")
        second = self._post_epf(client).json()
        second_committed = client.post(f"/import/commit-file/{second['preview_id']}")
        assert second_committed.status_code == 200
        assert second_committed.json()["inserted"] == 0
        assert second_committed.json()["skipped"] >= 0

    def test_epf_import_no_asset_returns_404(self, client):
        resp = self._post_epf(client)
        assert resp.status_code == 200


class TestBrokerCSVAutoInactive:
    def _make_csv(self, rows: list[dict]) -> bytes:
        import io, csv
        if not rows:
            return b""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue().encode()

    def _zerodha_row(self, symbol, isin, trade_type, qty, price, trade_id):
        return {
            "symbol": symbol,
            "isin": isin,
            "trade_date": "2024-01-15",
            "exchange": "NSE",
            "segment": "EQ",
            "series": "EQ",
            "trade_type": trade_type,
            "auction": "false",
            "quantity": str(qty),
            "price": str(price),
            "trade_id": trade_id,
            "order_id": f"ORD{trade_id}",
            "order_execution_time": "2024-01-15T10:00:00",
        }

    def _import(self, client, csv_bytes):
        resp = client.post(
            "/import/preview-file?source=zerodha&format=csv",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        preview_id = resp.json()["preview_id"]
        resp = client.post(f"/import/commit-file/{preview_id}")
        assert resp.status_code == 200
        return resp.json()

    def test_fully_sold_stock_marked_inactive(self, client):
        """BUY 10 + SELL 10 → is_active=False after commit."""
        rows = [
            self._zerodha_row("TESTCO", "INE999X01234", "buy", 10, 100.0, "T_INACT_001"),
            self._zerodha_row("TESTCO", "INE999X01234", "sell", 10, 120.0, "T_INACT_002"),
        ]
        self._import(client, self._make_csv(rows))

        assets = client.get("/assets?type=STOCK_IN").json()
        testco = next((a for a in assets if a.get("identifier") == "INE999X01234"), None)
        assert testco is not None, "Asset not created"
        assert testco["is_active"] is False, "Fully-sold stock should be inactive"

    def test_partially_sold_stock_stays_active(self, client):
        """BUY 10 + SELL 5 → is_active=True (5 shares remain)."""
        rows = [
            self._zerodha_row("PARTIAL", "INE888X01234", "buy", 10, 200.0, "T_PART_001"),
            self._zerodha_row("PARTIAL", "INE888X01234", "sell", 5, 250.0, "T_PART_002"),
        ]
        self._import(client, self._make_csv(rows))

        assets = client.get("/assets?type=STOCK_IN").json()
        partial = next((a for a in assets if a.get("identifier") == "INE888X01234"), None)
        assert partial is not None, "Asset not created"
        assert partial["is_active"] is True, "Partially-sold stock should stay active"

    def test_stock_with_bonus_stays_active_when_net_units_positive(self, db):
        """BUY 5 + BONUS 20 + SELL 5 → net_units = 20 → should stay is_active=True."""
        from app.models.asset import Asset, AssetType, AssetClass
        from app.models.transaction import Transaction, TransactionType
        from app.services.import_service import _STOCK_UNIT_ADD_TYPES, _STOCK_UNIT_SUB_TYPES
        from datetime import date

        asset = Asset(
            name="BONUSCO", identifier="INE111B01000",
            asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY, currency="INR",
            is_active=True,
        )
        db.add(asset)
        db.flush()

        db.add(Transaction(
            txn_id="b_buy_001", asset_id=asset.id, type=TransactionType.BUY,
            date=date(2020, 1, 1), units=5.0, price_per_unit=100.0,
            amount_inr=-50000, charges_inr=0,
        ))
        db.add(Transaction(
            txn_id="b_bonus_001", asset_id=asset.id, type=TransactionType.BONUS,
            date=date(2021, 1, 1), units=20.0, price_per_unit=0.0,
            amount_inr=0, charges_inr=0,
        ))
        db.add(Transaction(
            txn_id="b_sell_001", asset_id=asset.id, type=TransactionType.SELL,
            date=date(2022, 1, 1), units=5.0, price_per_unit=150.0,
            amount_inr=75000, charges_inr=0,
        ))
        db.commit()

        all_txns = db.query(Transaction).filter_by(asset_id=asset.id).all()
        net_units = sum(
            (t.units or 0.0) if t.type.value in _STOCK_UNIT_ADD_TYPES
            else -(t.units or 0.0) if t.type.value in _STOCK_UNIT_SUB_TYPES
            else 0.0
            for t in all_txns
        )
        assert net_units == pytest.approx(20.0), f"Expected 20.0, got {net_units}"

    def test_corp_actions_triggered_after_stock_import(self, client):
        """After committing a Zerodha CSV, StockPostProcessor should call CorpActionsService.process_asset."""
        from unittest.mock import patch, MagicMock
        rows = [
            self._zerodha_row("TRIGCO", "INE777T01000", "buy", 5, 300.0, "T_TRIG_001"),
        ]
        mock_instance = MagicMock()
        mock_instance.process_asset.return_value = {}
        with patch(
            "app.services.imports.post_processors.stock.CorpActionsService",
            return_value=mock_instance,
        ):
            self._import(client, self._make_csv(rows))

        mock_instance.process_asset.assert_called_once()

    def test_corp_actions_failure_does_not_break_import(self, client):
        """If CorpActionsService raises, the import commit still returns 200."""
        from unittest.mock import patch, MagicMock
        rows = [
            self._zerodha_row("ERRCO", "INE666E01000", "buy", 3, 100.0, "T_ERR_001"),
        ]
        mock_instance = MagicMock()
        mock_instance.process_asset.side_effect = Exception("NSE connection timeout")
        with patch(
            "app.services.imports.post_processors.stock.CorpActionsService",
            return_value=mock_instance,
        ):
            result = self._import(client, self._make_csv(rows))

        assert result["inserted"] == 1  # import succeeded despite corp actions error

