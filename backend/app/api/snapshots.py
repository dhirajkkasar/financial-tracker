from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.post("/take")
def take_snapshot(db: Session = Depends(get_db)):
    return SnapshotService(db).take_snapshot()


@router.get("")
def list_snapshots(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    return SnapshotService(db).list(from_date, to_date)
