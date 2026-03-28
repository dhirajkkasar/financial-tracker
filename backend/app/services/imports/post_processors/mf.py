"""
MFPostProcessor — persists CAS snapshots after an MF import commit.
"""
from typing import ClassVar


class MFPostProcessor:
    asset_types: ClassVar[list[str]] = ["MF"]

    def process(self, asset, txns: list, uow) -> None:
        """
        No-op by default — CAS snapshot persistence is handled
        by ImportOrchestrator.commit() directly using the snapshots
        in the ImportResult. This processor exists as a hook for
        future MF-specific post-import logic.
        """
        pass
