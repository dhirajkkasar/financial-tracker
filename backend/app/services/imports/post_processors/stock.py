"""
StockPostProcessor — marks STOCK_IN, STOCK_US, RSU assets inactive
when net units reach zero after an import.
"""
from typing import ClassVar

_UNIT_ADD_TYPES = {"BUY", "SIP", "VEST", "BONUS"}
_UNIT_SUB_TYPES = {"SELL", "REDEMPTION"}


class StockPostProcessor:
    asset_types: ClassVar[list[str]] = ["STOCK_IN", "STOCK_US", "RSU"]

    def process(self, asset, txns: list, uow) -> None:
        """
        Compute net units from the provided transactions.
        If net_units <= 0, mark the asset inactive.
        """
        net_units = 0.0
        for txn in txns:
            txn_type = getattr(txn, "type", None)
            if txn_type is None:
                txn_type = getattr(txn, "txn_type", None)
            if txn_type is not None:
                txn_type_val = txn_type.value if hasattr(txn_type, "value") else str(txn_type)
                units = getattr(txn, "units", 0.0) or 0.0
                if txn_type_val in _UNIT_ADD_TYPES:
                    net_units += units
                elif txn_type_val in _UNIT_SUB_TYPES:
                    net_units -= units
        if net_units <= 0:
            uow.assets.update(asset, is_active=False)
