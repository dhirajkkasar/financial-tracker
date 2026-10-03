import logging
from sqlalchemy.orm import Session

from app.engine.fd_engine import compute_maturity_paise
from app.repositories.asset_repo import AssetRepository
from app.repositories.fd_repo import FDRepository

logger = logging.getLogger(__name__)


class DepositsService:
    def __init__(self, db: Session):
        self.db = db
        self.asset_repo = AssetRepository(db)
        self.fd_repo = FDRepository(db)

    def mark_matured_fds(self) -> int:
        """Mark FDs/RDs whose maturity date has passed as matured and inactive.

        Computes maturity_amount only when not already set, so a previously
        recorded (e.g. bank-confirmed) maturity value is never overwritten.
        Returns the number of assets updated.
        """
        assets = self.asset_repo.list_unmatured_past_maturity()
        count = 0
        for asset in assets:
            fd = self.fd_repo.get_by_asset_id(asset.id)
            if fd is None:
                continue

            if fd.maturity_amount is None:
                fd.maturity_amount = compute_maturity_paise(fd)
            fd.is_matured = True
            asset.is_active = False
            logger.info(
                "Marked '%s' (id=%d) as matured (maturity_date=%s)",
                asset.name, asset.id, fd.maturity_date,
            )
            count += 1

        if count:
            self.db.commit()

        return count

