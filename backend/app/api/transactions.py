import hashlib
import math
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError, DuplicateError, ValidationError
from app.repositories.asset_repo import AssetRepository
from app.repositories.transaction_repo import TransactionRepository
from app.schemas.transaction import TransactionCreate, TransactionUpdate, TransactionResponse

router = APIRouter(prefix="/assets/{asset_id}/transactions", tags=["transactions"])

LOT_TYPES = {"BUY", "SIP", "CONTRIBUTION", "VEST"}
ALLOWED_PAGE_SIZES = {10, 25, 50}


def generate_txn_id(asset_id: int, txn_type: str, date: str, amount_paise: int, units: float | None) -> str:
    raw = f"{asset_id}|{txn_type}|{date}|{amount_paise}|{units or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


@router.get("", response_model=dict)
def list_transactions(
    asset_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10),
    db: Session = Depends(get_db),
):
    if page_size not in ALLOWED_PAGE_SIZES:
        raise ValidationError(f"page_size must be one of {sorted(ALLOWED_PAGE_SIZES)}, got {page_size}")
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")
    repo = TransactionRepository(db)
    total = repo.count_by_asset(asset_id)
    txns = repo.list_by_asset_paginated(asset_id, page, page_size)
    return {
        "items": [TransactionResponse.from_orm_convert(t) for t in txns],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 1,
    }


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(asset_id: int, body: TransactionCreate, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")

    amount_paise = round(body.amount_inr * 100)
    charges_paise = round(body.charges_inr * 100)

    txn_id = body.txn_id or generate_txn_id(
        asset_id, body.type.value, str(body.date), amount_paise, body.units
    )

    repo = TransactionRepository(db)
    if repo.get_by_txn_id(txn_id):
        raise DuplicateError(f"Transaction with txn_id {txn_id} already exists")

    lot_id = body.lot_id
    if lot_id is None and body.type.value in LOT_TYPES:
        lot_id = str(uuid.uuid4())

    txn = repo.create(
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
    return TransactionResponse.from_orm_convert(txn)


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(asset_id: int, transaction_id: int, body: TransactionUpdate, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")

    repo = TransactionRepository(db)
    txn = repo.get_by_id(transaction_id)
    if not txn or txn.asset_id != asset_id:
        raise NotFoundError(f"Transaction {transaction_id} not found")

    update_data = body.model_dump(exclude_none=True)
    if "amount_inr" in update_data:
        update_data["amount_inr"] = round(update_data["amount_inr"] * 100)
    if "charges_inr" in update_data:
        update_data["charges_inr"] = round(update_data["charges_inr"] * 100)

    txn = repo.update(txn, **update_data)
    return TransactionResponse.from_orm_convert(txn)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(asset_id: int, transaction_id: int, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")

    repo = TransactionRepository(db)
    txn = repo.get_by_id(transaction_id)
    if not txn or txn.asset_id != asset_id:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    repo.delete(txn)
