from datetime import date, timedelta
import pytest

from app.models.asset import Asset, AssetType, AssetClass
from app.models.fd_detail import FDDetail, FDType, CompoundingType
from app.services.deposits_service import DepositsService


def _add_fd_asset(db, name, maturity_date, is_matured=False, is_active=True, fd_type=FDType.FD):
    asset = Asset(
        name=name,
        asset_type=AssetType.FD if fd_type == FDType.FD else AssetType.RD,
        asset_class=AssetClass.DEBT,
        currency="INR",
        is_active=is_active,
    )
    db.add(asset)
    db.flush()
    fd = FDDetail(
        asset_id=asset.id,
        bank="SBI",
        fd_type=fd_type,
        principal_amount=10_000_00,  # ₹10,000 in paise
        interest_rate_pct=6.5,
        compounding=CompoundingType.QUARTERLY,
        start_date=maturity_date - timedelta(days=365),
        maturity_date=maturity_date,
        is_matured=is_matured,
    )
    db.add(fd)
    db.commit()
    return asset, fd


class TestDepositsServiceMarkMaturedFds:
    def test_marks_past_maturity_fd_as_matured(self, db):
        past_date = date.today() - timedelta(days=10)
        asset, fd = _add_fd_asset(db, "Old FD", maturity_date=past_date)

        count = DepositsService(db).mark_matured_fds()

        db.refresh(asset)
        db.refresh(fd)
        assert count == 1
        assert fd.is_matured is True
        assert asset.is_active is False

    def test_computes_maturity_amount_when_missing(self, db):
        past_date = date.today() - timedelta(days=10)
        asset, fd = _add_fd_asset(db, "Old FD no amt", maturity_date=past_date)
        assert fd.maturity_amount is None

        DepositsService(db).mark_matured_fds()

        db.refresh(fd)
        assert fd.maturity_amount is not None
        assert fd.maturity_amount > fd.principal_amount

    def test_preserves_existing_maturity_amount(self, db):
        past_date = date.today() - timedelta(days=10)
        asset, fd = _add_fd_asset(db, "FD with amt", maturity_date=past_date)
        fd.maturity_amount = 10_500_00  # manually set
        db.commit()

        DepositsService(db).mark_matured_fds()

        db.refresh(fd)
        assert fd.maturity_amount == 10_500_00

    def test_skips_already_matured_fd(self, db):
        past_date = date.today() - timedelta(days=10)
        asset, fd = _add_fd_asset(db, "Already matured", maturity_date=past_date, is_matured=True, is_active=False)

        count = DepositsService(db).mark_matured_fds()

        assert count == 0

    def test_skips_fd_not_yet_matured(self, db):
        future_date = date.today() + timedelta(days=30)
        asset, fd = _add_fd_asset(db, "Future FD", maturity_date=future_date)

        count = DepositsService(db).mark_matured_fds()

        db.refresh(fd)
        assert count == 0
        assert fd.is_matured is False
        assert asset.is_active is True

    def test_marks_past_maturity_rd_as_matured(self, db):
        past_date = date.today() - timedelta(days=5)
        asset, fd = _add_fd_asset(db, "Old RD", maturity_date=past_date, fd_type=FDType.RD)

        count = DepositsService(db).mark_matured_fds()

        db.refresh(asset)
        db.refresh(fd)
        assert count == 1
        assert fd.is_matured is True
        assert asset.is_active is False

    def test_handles_multiple_fds(self, db):
        past = date.today() - timedelta(days=10)
        future = date.today() + timedelta(days=10)
        asset1, fd1 = _add_fd_asset(db, "Past FD 1", maturity_date=past)
        asset2, fd2 = _add_fd_asset(db, "Past FD 2", maturity_date=past)
        asset3, fd3 = _add_fd_asset(db, "Future FD", maturity_date=future)

        count = DepositsService(db).mark_matured_fds()

        assert count == 2
        db.refresh(fd1); db.refresh(fd2); db.refresh(fd3)
        assert fd1.is_matured is True
        assert fd2.is_matured is True
        assert fd3.is_matured is False

    def test_returns_zero_when_nothing_to_update(self, db):
        count = DepositsService(db).mark_matured_fds()
        assert count == 0
