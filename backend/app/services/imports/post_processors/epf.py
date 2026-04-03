from typing import ClassVar

class EPFPostProcessor:
    asset_types: ClassVar[list[str]] = ["EPF"]

    def process(self, asset, import_result, uow) -> None:
        """EPF asset is never auto-closed."""
        asset.is_active = True