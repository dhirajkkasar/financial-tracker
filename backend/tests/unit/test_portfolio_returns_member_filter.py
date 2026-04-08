import pytest
from unittest.mock import MagicMock, patch
from app.services.returns.portfolio_returns_service import PortfolioReturnsService


def test_get_breakdown_passes_member_ids():
    """Verify that member_ids is forwarded to uow.assets.list()."""
    db = MagicMock()
    registry = MagicMock()

    svc = PortfolioReturnsService(db, registry)

    with patch("app.services.returns.portfolio_returns_service.UnitOfWork") as MockUoW:
        mock_uow = MagicMock()
        mock_uow.assets.list.return_value = []
        MockUoW.return_value.__enter__ = MagicMock(return_value=mock_uow)
        MockUoW.return_value.__exit__ = MagicMock(return_value=False)

        svc.get_breakdown(member_ids=[1, 2])
        mock_uow.assets.list.assert_called_once_with(active=None, member_ids=[1, 2])
