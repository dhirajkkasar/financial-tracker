from typing import ClassVar


class PPFPostProcessor:
    asset_types: ClassVar[list[str]] = ["PPF"]

    def process(self, asset, txns: list, uow) -> None:
        """
        No-op by default — PPF-specific post-import logic can be added here.
        """
        pass