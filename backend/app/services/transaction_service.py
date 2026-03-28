"""
TransactionService — thin wrapper over TransactionRepository.
"""
from __future__ import annotations

import hashlib
import math
import uuid

from app.middleware.error_handler import DuplicateError, NotFoundError, ValidationError
from app.models.transaction import Transaction
from app.repositories.unit_of_work import UnitOfWork, IUnitOfWorkFactory
from app.schemas.transaction import TransactionCreate, TransactionUpdate

LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST"}
ALLOWED_PAGE_SIZES = {10, 25, 50}


def _generate_txn_id(asset_id: int, txn_type: str, date: str, amount_paise: int, units) -> str:
    raw = f"{asset_id}|{txn_type}|{date}|{amount_paise}|{units or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


class TransactionService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def create(self, asset_id: int, body: TransactionCreate) -> Transaction:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")

            amount_paise = round(body.amount_inr * 100)
            charges_paise = round(body.charges_inr * 100)

            txn_id = body.txn_id or _generate_txn_id(
                asset_id, body.type.value, str(body.date), amount_paise, body.units
            )

            if uow.transactions.get_by_txn_id(txn_id):
                raise DuplicateError(f"Transaction with txn_id {txn_id} already exists")

            lot_id = body.lot_id
            if lot_id is None and body.type.value in LOT_TYPES:
                lot_id = str(uuid.uuid4())

            return uow.transactions.create(
                txn_id=txn_id,
                asset_id=asset_id,
                type=body.type,
                date=body.date,
                units=body.units,
                price_per_unit=body.price_per_unit,
                forex_rate=body.forex_rate,
                amount_inr=amount_paise,
                charges_inr=charges_paise,
                lot_id=lot_id,
                notes=body.notes,
            )

    def list_paginated(self, asset_id: int, page: int, page_size: int):
        if page_size not in ALLOWED_PAGE_SIZES:
            raise ValidationError(f"page_size must be one of {sorted(ALLOWED_PAGE_SIZES)}, got {page_size}")
        with self._uow_factory() as uow:
            total = uow.transactions.count_by_asset(asset_id)
            txns = uow.transactions.list_by_asset_paginated(asset_id, page, page_size)
            return txns, total

    def update(self, asset_id: int, txn_id_int: int, body: TransactionUpdate) -> Transaction:
        with self._uow_factory() as uow:
            txn = uow.transactions.get_by_id(txn_id_int)
            if not txn or txn.asset_id != asset_id:
                raise NotFoundError(f"Transaction {txn_id_int} not found for asset {asset_id}")
            update_data = body.model_dump(exclude_none=True)
            if "amount_inr" in update_data:
                update_data["amount_inr"] = round(update_data["amount_inr"] * 100)
            if "charges_inr" in update_data:
                update_data["charges_inr"] = round(update_data["charges_inr"] * 100)
            return uow.transactions.update(txn, **update_data)

    def delete(self, asset_id: int, txn_id_int: int) -> None:
        with self._uow_factory() as uow:
            txn = uow.transactions.get_by_id(txn_id_int)
            if not txn or txn.asset_id != asset_id:
                raise NotFoundError(f"Transaction {txn_id_int} not found for asset {asset_id}")
            uow.transactions.delete(txn)
