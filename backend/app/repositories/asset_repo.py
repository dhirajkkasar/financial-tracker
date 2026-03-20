from typing import Optional
from sqlalchemy.orm import Session
from app.models.asset import Asset, AssetType, AssetClass


class AssetRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Asset:
        asset = Asset(**kwargs)
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def get_by_id(self, asset_id: int) -> Optional[Asset]:
        return self.db.query(Asset).filter(Asset.id == asset_id).first()

    def list(
        self,
        asset_type: Optional[AssetType] = None,
        asset_class: Optional[AssetClass] = None,
        active: Optional[bool] = None,
    ) -> list[Asset]:
        q = self.db.query(Asset)
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
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def soft_delete(self, asset: Asset) -> Asset:
        asset.is_active = False
        self.db.commit()
        self.db.refresh(asset)
        return asset
