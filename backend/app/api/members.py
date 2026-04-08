from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_member_service
from app.middleware.error_handler import DuplicateError
from app.schemas.member import MemberCreate, MemberResponse
from app.services.member_service import MemberService

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=list[MemberResponse])
def list_members(service: MemberService = Depends(get_member_service)):
    return service.list_all()


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(body: MemberCreate, service: MemberService = Depends(get_member_service)):
    try:
        return service.create(pan=body.pan, name=body.name)
    except DuplicateError:
        raise HTTPException(status_code=409, detail=f"Member with PAN {body.pan} already exists")
