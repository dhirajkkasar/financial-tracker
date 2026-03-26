import pytest
from app.importers.base import ParsedTransaction
from datetime import date


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
