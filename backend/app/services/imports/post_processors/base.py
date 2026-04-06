"""
IPostProcessor protocol — one class per asset type needing post-import logic.

Adding new post-import behavior: create a new class implementing IPostProcessor,
register it in api/dependencies.py. ImportOrchestrator picks it up automatically.
"""
from typing import ClassVar, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from app.importers.base import ImportResult
    from app.repositories.unit_of_work import UnitOfWork


class IPostProcessor(Protocol):
    asset_types: ClassVar[list[str]]

    def process(self, asset, import_result, uow) -> None:
        """Called after transactions are persisted for asset. May update asset state."""
        ...


class IPreCommitProcessor(Protocol):
    """
    Runs inside commit() BEFORE the transaction loop.
    Receives the in-memory ImportResult, may add/replace ParsedTransactions.
    Keyed by result.source (not asset_type).
    """
    source: ClassVar[str]

    def process(self, result: "ImportResult", uow: "UnitOfWork") -> "ImportResult":
        """Return modified ImportResult. May expand, replace, or annotate transactions."""
        ...
