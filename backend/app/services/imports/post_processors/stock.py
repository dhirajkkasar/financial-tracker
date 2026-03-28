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
        Compute net units for the asset by inspecting all transactions in DB.
        If net_units <= 0, mark the asset inactive.
        """
        try:
            all_txns = uow.transactions.list_by_asset(asset.id)
        except Exception:
            # Fall back to per-call txns if repository unavailable
            all_txns = txns or []

        net_units = 0.0
        for t in all_txns:
            t_type = getattr(t, "type", None)
            if t_type is None:
                t_type = getattr(t, "txn_type", None)
            if t_type is None:
                continue
            t_type_val = t_type.value if hasattr(t_type, "value") else str(t_type)
            units = getattr(t, "units", 0.0) or 0.0
            if t_type_val in _UNIT_ADD_TYPES:
                net_units += units
            elif t_type_val in _UNIT_SUB_TYPES:
                net_units -= units

        if net_units <= 0:
            uow.assets.update(asset, is_active=False)
