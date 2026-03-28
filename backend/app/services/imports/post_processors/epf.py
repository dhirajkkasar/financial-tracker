from typing import ClassVar

class EPFPostProcessor:
    asset_types: ClassVar[list[str]] = ["EPF"]

    def process(self, asset, txns: list, uow) -> None:
        """EPF asset is never auto-closed."""
        asset.is_active = True