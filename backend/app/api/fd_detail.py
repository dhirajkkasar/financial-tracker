from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_fd_detail_service
from app.schemas.fd_detail import FDDetailCreate, FDDetailUpdate, FDDetailResponse
from app.services.fd_detail_service import FDDetailService

router = APIRouter(prefix="/assets/{asset_id}/fd-detail", tags=["fd-detail"])


@router.get("", response_model=FDDetailResponse)
def get_fd_detail(asset_id: int, svc: FDDetailService = Depends(get_fd_detail_service)):
    return svc.get(asset_id)


@router.post("", response_model=FDDetailResponse, status_code=status.HTTP_201_CREATED)
def create_fd_detail(asset_id: int, body: FDDetailCreate, svc: FDDetailService = Depends(get_fd_detail_service)):
    return svc.create(asset_id, body)


@router.put("", response_model=FDDetailResponse)
def update_fd_detail(asset_id: int, body: FDDetailUpdate, svc: FDDetailService = Depends(get_fd_detail_service)):
    return svc.update(asset_id, body)
