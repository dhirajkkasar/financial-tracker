import pytest
from unittest.mock import MagicMock
from app.services.tax_service import TaxService


def test_get_tax_summary_filters_by_member_id():
    uow_factory = MagicMock()
    mock_uow = MagicMock()
    mock_uow.assets.list.return_value = []
    uow_factory.return_value.__enter__ = MagicMock(return_value=mock_uow)
    uow_factory.return_value.__exit__ = MagicMock(return_value=False)

    svc = TaxService(uow_factory=uow_factory)
    svc.get_tax_summary("2024-25", member_id=1)
    mock_uow.assets.list.assert_called_once_with(active=None, member_ids=[1])


def test_get_unrealised_filters_by_member_id():
    uow_factory = MagicMock()
    mock_uow = MagicMock()
    mock_uow.assets.list.return_value = []
    uow_factory.return_value.__enter__ = MagicMock(return_value=mock_uow)
    uow_factory.return_value.__exit__ = MagicMock(return_value=False)

    svc = TaxService(uow_factory=uow_factory)
    svc.get_unrealised_summary(member_id=1)
    mock_uow.assets.list.assert_called_once_with(active=True, member_ids=[1])
