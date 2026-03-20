from typing import Optional
from sqlalchemy.orm import Session
from app.models.transaction import Transaction, TransactionType


class TransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Transaction:
        txn = Transaction(**kwargs)
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)
        return txn

    def get_by_txn_id(self, txn_id: str) -> Optional[Transaction]:
        return self.db.query(Transaction).filter(Transaction.txn_id == txn_id).first()

    def get_by_id(self, transaction_id: int) -> Optional[Transaction]:
        return self.db.query(Transaction).filter(Transaction.id == transaction_id).first()

    def list_by_asset(self, asset_id: int) -> list[Transaction]:
        return (
            self.db.query(Transaction)
            .filter(Transaction.asset_id == asset_id)
            .order_by(Transaction.date.desc())
            .all()
        )

    def count_by_asset(self, asset_id: int) -> int:
        return self.db.query(Transaction).filter(Transaction.asset_id == asset_id).count()

    def list_by_asset_paginated(self, asset_id: int, page: int, page_size: int) -> list[Transaction]:
        offset = (page - 1) * page_size
        return (
            self.db.query(Transaction)
            .filter(Transaction.asset_id == asset_id)
            .order_by(Transaction.date.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

    def list_all(self) -> list[Transaction]:
        return self.db.query(Transaction).order_by(Transaction.date.desc()).all()

    def update(self, txn: Transaction, **kwargs) -> Transaction:
        for key, value in kwargs.items():
            if value is not None:
                setattr(txn, key, value)
        self.db.commit()
        self.db.refresh(txn)
        return txn

    def delete(self, txn: Transaction) -> None:
        self.db.delete(txn)
        self.db.commit()
