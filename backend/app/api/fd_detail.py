from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.error_handler import NotFoundError, DuplicateError
from app.repositories.asset_repo import AssetRepository
from app.repositories.fd_repo import FDRepository
from app.schemas.fd_detail import FDDetailCreate, FDDetailUpdate, FDDetailResponse

router = APIRouter(prefix="/assets/{asset_id}/fd-detail", tags=["fd-detail"])


@router.get("", response_model=FDDetailResponse)
def get_fd_detail(asset_id: int, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")
    repo = FDRepository(db)
    fd = repo.get_by_asset_id(asset_id)
    if not fd:
        raise NotFoundError(f"FD detail for asset {asset_id} not found")
    return FDDetailResponse.from_orm_convert(fd)


@router.post("", response_model=FDDetailResponse, status_code=status.HTTP_201_CREATED)
def create_fd_detail(asset_id: int, body: FDDetailCreate, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")
    repo = FDRepository(db)
    if repo.get_by_asset_id(asset_id):
        raise DuplicateError(f"FD detail already exists for asset {asset_id}")

    data = body.model_dump()
    data["principal_amount"] = round(data["principal_amount"] * 100)
    if data.get("maturity_amount") is not None:
        data["maturity_amount"] = round(data["maturity_amount"] * 100)
    data["asset_id"] = asset_id

    fd = repo.create(**data)

    if body.is_matured:
        asset = asset_repo.get_by_id(asset_id)
        asset.is_active = False
        db.commit()

    return FDDetailResponse.from_orm_convert(fd)


@router.put("", response_model=FDDetailResponse)
def update_fd_detail(asset_id: int, body: FDDetailUpdate, db: Session = Depends(get_db)):
    asset_repo = AssetRepository(db)
    if not asset_repo.get_by_id(asset_id):
        raise NotFoundError(f"Asset {asset_id} not found")
    repo = FDRepository(db)
    fd = repo.get_by_asset_id(asset_id)
    if not fd:
        raise NotFoundError(f"FD detail for asset {asset_id} not found")

    update_data = body.model_dump(exclude_none=True)
    if "principal_amount" in update_data:
        update_data["principal_amount"] = round(update_data["principal_amount"] * 100)
    if "maturity_amount" in update_data:
        update_data["maturity_amount"] = round(update_data["maturity_amount"] * 100)

    fd = repo.update(fd, **update_data)

    if body.is_matured is not None:
        asset = asset_repo.get_by_id(asset_id)
        asset.is_active = not body.is_matured
        db.commit()

    return FDDetailResponse.from_orm_convert(fd)
