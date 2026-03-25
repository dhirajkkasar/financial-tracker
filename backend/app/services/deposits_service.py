import logging
from sqlalchemy.orm import Session

from app.engine.fd_engine import compute_fd_maturity, compute_rd_maturity
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

        Returns the number of assets updated.
        """
        assets = self.asset_repo.list_unmatured_past_maturity()
        count = 0
        for asset in assets:
            fd = self.fd_repo.get_by_asset_id(asset.id)
            if fd is None:
                continue

            if fd.maturity_amount is None:
                principal_inr = fd.principal_amount / 100.0
                if fd.fd_type.value == "FD":
                    tenure_years = (fd.maturity_date - fd.start_date).days / 365.0
                    maturity_inr = compute_fd_maturity(
                        principal_inr, fd.interest_rate_pct, fd.compounding.value, tenure_years
                    )
                else:  # RD
                    months = round((fd.maturity_date - fd.start_date).days / 30.44)
                    maturity_inr = compute_rd_maturity(principal_inr, fd.interest_rate_pct, months)
                fd.maturity_amount = round(maturity_inr * 100)

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
