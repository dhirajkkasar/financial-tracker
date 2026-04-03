from typing import ClassVar


class PPFPostProcessor:
    asset_types: ClassVar[list[str]] = ["PPF"]

    def process(self, asset, import_result, uow) -> None:
        """
        Create closing valuation if provided in import_result.
        """
        if (
            import_result.closing_valuation_inr is not None
            and import_result.closing_valuation_date is not None
        ):
            if asset is None:
                return
            uow.valuations.create(
                asset_id=asset.id,
                date=import_result.closing_valuation_date,
                value_inr=int(import_result.closing_valuation_inr * 100),
                source=import_result.closing_valuation_source or "import",
                notes=import_result.closing_valuation_notes,
            )