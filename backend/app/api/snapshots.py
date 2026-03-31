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
    svc: SnapshotService = Depends(get_snapshot_service),
):
    return svc.list(from_date, to_date)
