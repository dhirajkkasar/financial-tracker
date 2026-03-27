from typing import Optional
from sqlalchemy.orm import Session
from app.models.fd_detail import FDDetail


class FDRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> FDDetail:
        fd = FDDetail(**kwargs)
        self.db.add(fd)
        self.db.flush()
        self.db.refresh(fd)
        return fd

    def get_by_asset_id(self, asset_id: int) -> Optional[FDDetail]:
        return self.db.query(FDDetail).filter(FDDetail.asset_id == asset_id).first()

    def update(self, fd: FDDetail, **kwargs) -> FDDetail:
        for key, value in kwargs.items():
            if value is not None:
                setattr(fd, key, value)
        self.db.flush()
        self.db.refresh(fd)
        return fd
