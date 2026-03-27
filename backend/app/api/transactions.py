import math
from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_transaction_service
from app.schemas.transaction import TransactionCreate, TransactionUpdate, TransactionResponse
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/assets/{asset_id}/transactions", tags=["transactions"])


@router.get("", response_model=dict)
def list_transactions(
    asset_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10),
    service: TransactionService = Depends(get_transaction_service),
):
    txns, total = service.list_paginated(asset_id, page, page_size)
    return {
        "items": [TransactionResponse.from_orm_convert(t) for t in txns],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 1,
    }


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    asset_id: int,
    body: TransactionCreate,
    service: TransactionService = Depends(get_transaction_service),
):
    txn = service.create(asset_id, body)
    return TransactionResponse.from_orm_convert(txn)


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    asset_id: int,
    transaction_id: int,
    body: TransactionUpdate,
    service: TransactionService = Depends(get_transaction_service),
):
    txn = service.update(asset_id, transaction_id, body)
    return TransactionResponse.from_orm_convert(txn)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    asset_id: int,
    transaction_id: int,
    service: TransactionService = Depends(get_transaction_service),
):
    service.delete(asset_id, transaction_id)
