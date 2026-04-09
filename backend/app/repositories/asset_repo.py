from __future__ import annotations

from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from app.models.asset import Asset, AssetType, AssetClass
from app.models.fd_detail import FDDetail


class AssetRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Asset:
        print(f"Creating asset with kwargs: {kwargs}")
        asset = Asset(**kwargs)
        self.db.add(asset)
        self.db.flush()
        self.db.refresh(asset)
        return asset

    def get_by_id(self, asset_id: int) -> Optional[Asset]:
        return self.db.query(Asset).filter(Asset.id == asset_id).first()
    
    def get_by_identifier(self, identifier: str) -> Optional[Asset]:
        return self.db.query(Asset).filter(Asset.identifier == identifier).first()

    def list(
        self,
        asset_type: Optional[AssetType] = None,
        asset_class: Optional[AssetClass] = None,
        active: Optional[bool] = None,
        member_ids: Optional[list[int]] = None,
    ) -> list[Asset]:
        q = self.db.query(Asset)
        if member_ids is not None:
            q = q.filter(Asset.member_id.in_(member_ids))
        if asset_type is not None:
            q = q.filter(Asset.asset_type == asset_type)
        if asset_class is not None:
            q = q.filter(Asset.asset_class == asset_class)
        if active is not None:
            q = q.filter(Asset.is_active == active)
        return q.order_by(Asset.id).all()

    def update(self, asset: Asset, **kwargs) -> Asset:
        for key, value in kwargs.items():
            if value is not None:
                setattr(asset, key, value)
        self.db.flush()
        self.db.refresh(asset)
        return asset

    def list_unmatured_past_maturity(self) -> list[Asset]:
        """Return active FD/RD assets whose maturity_date has passed but is_matured is still False."""
        today = date.today()
        return (
            self.db.query(Asset)
            .join(FDDetail, FDDetail.asset_id == Asset.id)
            .filter(
                Asset.asset_type.in_([AssetType.FD, AssetType.RD]),
                Asset.is_active == True,
                FDDetail.is_matured == False,
                FDDetail.maturity_date <= today,
            )
            .all()
        )

    def soft_delete(self, asset: Asset) -> Asset:
        asset.is_active = False
        self.db.flush()
        self.db.refresh(asset)
        return asset
