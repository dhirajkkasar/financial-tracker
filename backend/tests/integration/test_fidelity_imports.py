import json
from pathlib import Path

import pytest
from app.importers.base import ParsedTransaction
from datetime import date

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parsed_transaction_has_forex_rate_field():
    txn = ParsedTransaction(
        source="test", asset_name="AMZN", asset_identifier="AMZN",
        asset_type="STOCK_US", txn_type="VEST", date=date(2025, 3, 17),
        units=68.0, price_per_unit=196.40, amount_inr=-1_380_605.0,
        txn_id="test_001", forex_rate=84.5,
    )
    assert txn.forex_rate == 84.5


def test_commit_persists_forex_rate(db):
    """Committed VEST transaction stores forex_rate in DB."""
    from app.importers.base import ParsedTransaction
    from app.services.import_service import ImportService
    from app.repositories.transaction_repo import TransactionRepository
    from datetime import date

    svc = ImportService(db)
    txn = ParsedTransaction(
        source="fidelity_rsu", asset_name="AMZN", asset_identifier="AMZN",
        asset_type="STOCK_US", txn_type="VEST", date=date(2025, 3, 17),
        units=68.0, price_per_unit=196.40, amount_inr=-1_380_000.0,
        txn_id="fidelity_rsu_test_001", forex_rate=84.5,
    )
    preview = svc.preview(transactions=[txn])
    svc.commit(preview["preview_id"])

    repo = TransactionRepository(db)
    saved = repo.get_by_txn_id("fidelity_rsu_test_001")
    assert saved is not None
    assert saved.forex_rate == pytest.approx(84.5)


def test_stock_us_asset_created_with_usd_currency(db):
    from app.importers.base import ParsedTransaction
    from app.services.import_service import ImportService
    from app.models.asset import Asset
    from datetime import date

    svc = ImportService(db)
    txn = ParsedTransaction(
        source="fidelity_rsu", asset_name="AMZN2", asset_identifier="AMZN2",
        asset_type="STOCK_US", txn_type="VEST", date=date(2025, 3, 17),
        units=10.0, price_per_unit=200.0, amount_inr=-170_000.0,
        txn_id="fidelity_rsu_currency_test", forex_rate=85.0,
    )
    preview = svc.preview(transactions=[txn])
    svc.commit(preview["preview_id"])

    asset = db.query(Asset).filter(Asset.identifier == "AMZN2").first()
    assert asset is not None
    assert asset.currency == "USD"


def test_fidelity_rsu_csv_endpoint_preview(client):
    """POST /import/fidelity-rsu-csv returns a valid preview."""
    csv_bytes = (FIXTURES / "fidelity_rsu_sample.csv").read_bytes()
    rates = {"2025-03": 86.5, "2024-09": 83.8}
    resp = client.post(
        "/import/preview-file?source=fidelity_rsu&format=csv",
        data={"exchange_rates": json.dumps(rates)},
        files={"file": ("NASDAQ_AMZN.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "preview_id" in body
    assert body["new_count"] == 2
    assert body["duplicate_count"] == 0


def test_fidelity_rsu_csv_endpoint_missing_rate_returns_422(client):
    """POST /import/preview-file?source=fidelity_rsu&format=csv with incomplete rates returns 422."""
    csv_bytes = (FIXTURES / "fidelity_rsu_sample.csv").read_bytes()
    resp = client.post(
        "/import/preview-file?source=fidelity_rsu&format=csv",
        data={"exchange_rates": json.dumps({"2025-03": 86.5})},  # missing 2024-09
        files={"file": ("NASDAQ_AMZN.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 422
    assert "2024-09" in resp.text


def test_fidelity_rsu_csv_endpoint_idempotent(client):
    """Importing the same CSV twice skips duplicates."""
    csv_bytes = (FIXTURES / "fidelity_rsu_sample.csv").read_bytes()
    rates = {"2025-03": 86.5, "2024-09": 83.8}

    def do_import():
        resp = client.post(
            "/import/preview-file?source=fidelity_rsu&format=csv",
            data={"exchange_rates": json.dumps(rates)},
            files={"file": ("NASDAQ_AMZN.csv", csv_bytes, "text/csv")},
        )
        preview_id = resp.json()["preview_id"]
        return client.post(f"/import/commit-file/{preview_id}").json()

    first = do_import()
    second = do_import()
    assert first["inserted"] == 2
    assert second["inserted"] == 0
    assert second["skipped"] == 2


def test_fidelity_sale_pdf_endpoint_preview(client):
    """POST /import/fidelity-sale-pdf returns preview with 2 SELL transactions."""
    path = FIXTURES / "fidelity_sale_sample.pdf"
    if not path.exists():
        pytest.skip("fidelity_sale_sample.pdf fixture not available")
    pdf_bytes = path.read_bytes()
    rates = {"2025-03": 86.0, "2025-09": 84.5}
    resp = client.post(
        "/import/preview-file?source=fidelity_sale&format=pdf",
        data={"exchange_rates": json.dumps(rates)},
        files={"file": ("sale.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "preview_id" in body
    assert body["new_count"] == 2
    txns = body["transactions"]
    assert all(t["txn_type"] == "SELL" for t in txns)
    assert all("Tax cover sale" in (t["notes"] or "") for t in txns)


def test_fidelity_sale_pdf_endpoint_missing_rate_returns_422(client):
    """POST /import/preview-file?source=fidelity_sale&format=pdf with incomplete rates returns 422."""
    path = FIXTURES / "fidelity_sale_sample.pdf"
    if not path.exists():
        pytest.skip("fidelity_sale_sample.pdf fixture not available")
    pdf_bytes = path.read_bytes()
    resp = client.post(
        "/import/preview-file?source=fidelity_sale&format=pdf",
        data={"exchange_rates": json.dumps({"2025-03": 86.0})},  # missing 2025-09
        files={"file": ("sale.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 422
    assert "2025-09" in resp.text


def test_fidelity_sale_pdf_endpoint_idempotent(client):
    """Importing the same PDF twice skips duplicates."""
    path = FIXTURES / "fidelity_sale_sample.pdf"
    if not path.exists():
        pytest.skip("fidelity_sale_sample.pdf fixture not available")
    pdf_bytes = path.read_bytes()
    rates = {"2025-03": 86.0, "2025-09": 84.5}

    def do_import():
        resp = client.post(
            "/import/preview-file?source=fidelity_sale&format=pdf",
            data={"exchange_rates": json.dumps(rates)},
            files={"file": ("sale.pdf", pdf_bytes, "application/pdf")},
        )
        preview_id = resp.json()["preview_id"]
        return client.post(f"/import/commit-file/{preview_id}").json()

    first = do_import()
    second = do_import()
    assert first["created_count"] == 2
    assert second["created_count"] == 0
    assert second["skipped_count"] == 2
