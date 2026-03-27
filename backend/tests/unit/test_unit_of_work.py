from app.repositories.interfaces import (
    IAssetRepository,
    ITransactionRepository,
    IValuationRepository,
    IPriceCacheRepository,
    IFDRepository,
    ICasSnapshotRepository,
    IGoalRepository,
)
from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository


def test_asset_repo_satisfies_interface():
    """AssetRepository satisfies IAssetRepository via duck-typing."""
    assert hasattr(AssetRepository, "get_by_id")
    assert hasattr(AssetRepository, "list")
    assert hasattr(AssetRepository, "create")
    assert hasattr(AssetRepository, "update")


def test_transaction_repo_satisfies_interface():
    assert hasattr(TransactionRepository, "get_by_txn_id")
    assert hasattr(TransactionRepository, "create")
    assert hasattr(TransactionRepository, "list_by_asset")
