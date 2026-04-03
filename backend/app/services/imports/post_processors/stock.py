"""
StockPostProcessor — marks STOCK_IN, STOCK_US, RSU assets inactive
when net units reach zero after an import.
"""
from typing import ClassVar
import logging

from app.services.corp_actions_service import CorpActionsService

_UNIT_ADD_TYPES = {"BUY", "SIP", "VEST", "BONUS"}
_UNIT_SUB_TYPES = {"SELL", "REDEMPTION"}


class StockPostProcessor:
    asset_types: ClassVar[list[str]] = ["STOCK_IN", "STOCK_US", "RSU"]

    def process(self, asset, import_result, uow) -> None:
        """
        Compute net units for the asset by inspecting all transactions in DB.
        If net_units <= 0, mark the asset inactive.
        Then, process corporate actions.
        """
        try:
            all_txns = uow.transactions.list_by_asset(asset.id)
        except Exception:
            # Fall back to per-call txns if repository unavailable
            if hasattr(import_result, "transactions"):
                all_txns = import_result.transactions or []
            elif isinstance(import_result, list):
                all_txns = import_result
            else:
                all_txns = []

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

        # Process corporate actions
        try:
            corp_svc = CorpActionsService(uow.session)
            corp_svc.process_asset(asset)
        except Exception as e:
            # Log but don't fail the import
            logger = logging.getLogger(__name__)
            logger.warning("Corp actions failed for asset %d '%s': %s", asset.id, asset.name, e)
