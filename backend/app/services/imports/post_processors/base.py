"""
IPostProcessor protocol — one class per asset type needing post-import logic.

Adding new post-import behavior: create a new class implementing IPostProcessor,
register it in api/dependencies.py. ImportOrchestrator picks it up automatically.
"""
from typing import ClassVar, Protocol


class IPostProcessor(Protocol):
    asset_types: ClassVar[list[str]]

    def process(self, asset, import_result, uow) -> None:
        """Called after transactions are persisted for asset. May update asset state."""
        ...
