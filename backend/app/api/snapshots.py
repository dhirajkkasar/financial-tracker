from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_snapshot_service
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.post("/take")
def take_snapshot(svc: SnapshotService = Depends(get_snapshot_service)):
    return svc.take_snapshot()


@router.get("")
def list_snapshots(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    member_ids: Optional[str] = Query(None, description="Comma-separated member IDs"),
    svc: SnapshotService = Depends(get_snapshot_service),
):
    parsed = [int(x.strip()) for x in member_ids.split(",") if x.strip()] if member_ids else None
    return svc.list(from_date, to_date, member_ids=parsed)
