"""Unit tests for TaxService.get_available_fys()."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_service():
    from app.services.tax_service import TaxService
    return TaxService(uow_factory=MagicMock())


# ── get_available_fys ─────────────────────────────────────────────────────────

def test_get_available_fys_returns_sorted_list():
    """Returns FY labels sorted ascending from config yaml filenames."""
    svc = _make_service()
    fake_files = [
        MagicMock(stem="2025-26"),
        MagicMock(stem="2024-25"),
        MagicMock(stem="2026-27"),
    ]
    with patch.object(Path, "glob", return_value=fake_files):
        result = svc.get_available_fys()
    assert result == ["2024-25", "2025-26", "2026-27"]


def test_get_available_fys_excludes_init():
    """__init__ stem from the config dir is not included in results."""
    svc = _make_service()
    fake_files = [
        MagicMock(stem="__init__"),
        MagicMock(stem="2024-25"),
        MagicMock(stem="2025-26"),
    ]
    with patch.object(Path, "glob", return_value=fake_files):
        result = svc.get_available_fys()
    assert "__init__" not in result
    assert result == ["2024-25", "2025-26"]


def test_get_available_fys_empty_config_dir():
    """Returns empty list when no yaml files exist."""
    svc = _make_service()
    with patch.object(Path, "glob", return_value=[]):
        result = svc.get_available_fys()
    assert result == []


def test_get_available_fys_single_year():
    """Works correctly with only one config file."""
    svc = _make_service()
    fake_files = [MagicMock(stem="2024-25")]
    with patch.object(Path, "glob", return_value=fake_files):
        result = svc.get_available_fys()
    assert result == ["2024-25"]
