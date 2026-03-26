"""Unit tests for backup.py — Google Drive backup module."""
import gzip
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _resolve_db_path
# ---------------------------------------------------------------------------

def test_resolve_db_path_returns_absolute_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    db_file.write_bytes(b"SQLite format 3\x00")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    from backup import _resolve_db_path
    result = _resolve_db_path()
    assert result == db_file
    assert result.is_absolute()


def test_resolve_db_path_relative_url(tmp_path, monkeypatch):
    """sqlite:///./foo.db resolves relative to cwd."""
    db_file = tmp_path / "rel.db"
    db_file.write_bytes(b"SQLite format 3\x00")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./rel.db")

    from backup import _resolve_db_path
    assert _resolve_db_path() == db_file


def test_resolve_db_path_missing_file_exits(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/missing.db")

    from backup import _resolve_db_path
    with pytest.raises(SystemExit, match="not found"):
        _resolve_db_path()


def test_resolve_db_path_non_sqlite_exits(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/mydb")

    from backup import _resolve_db_path
    with pytest.raises(SystemExit, match="sqlite"):
        _resolve_db_path()


def test_resolve_db_path_missing_env_exits(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from backup import _resolve_db_path
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        _resolve_db_path()


# ---------------------------------------------------------------------------
# _get_credentials
# (tests omitted — _get_credentials triggers real OAuth browser flow;
#  covered implicitly via backup_to_drive tests which mock _get_credentials)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _get_or_create_folder
# ---------------------------------------------------------------------------

def test_get_or_create_folder_returns_existing_id():
    mock_service = MagicMock()
    mock_service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "existing_folder_id", "name": "financial-tracker-backup"}]
    }

    from backup import _get_or_create_folder
    result = _get_or_create_folder(mock_service, "financial-tracker-backup")

    assert result == "existing_folder_id"
    mock_service.files.return_value.create.assert_not_called()


def test_get_or_create_folder_creates_when_missing():
    mock_service = MagicMock()
    mock_service.files.return_value.list.return_value.execute.return_value = {"files": []}
    mock_service.files.return_value.create.return_value.execute.return_value = {
        "id": "new_folder_id"
    }

    from backup import _get_or_create_folder
    result = _get_or_create_folder(mock_service, "financial-tracker-backup")

    assert result == "new_folder_id"
    mock_service.files.return_value.create.assert_called_once()


# ---------------------------------------------------------------------------
# backup_to_drive (integration-level, all Drive calls mocked)
# ---------------------------------------------------------------------------

def test_backup_to_drive_uploads_gzipped_file(tmp_path, monkeypatch):
    db_file = tmp_path / "portfolio.db"
    db_file.write_bytes(b"SQLite format 3\x00" * 100)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test_secret")

    mock_creds = MagicMock()
    mock_service = MagicMock()
    # folder search returns existing folder
    mock_service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "folder_123", "name": "test-backup"}]
    }
    # file upload returns file id
    mock_service.files.return_value.create.return_value.execute.return_value = {
        "id": "file_456"
    }

    with patch("backup._get_credentials", return_value=mock_creds), \
         patch("backup.build", return_value=mock_service):
        from backup import backup_to_drive
        file_id = backup_to_drive(folder_name="test-backup")

    assert file_id == "file_456"

    # verify the uploaded media is gzip-compressed
    call_kwargs = mock_service.files.return_value.create.call_args
    media = call_kwargs.kwargs.get("media_body") or call_kwargs[1].get("media_body")
    raw = media._body
    decompressed = gzip.decompress(raw)
    assert decompressed == db_file.read_bytes()


def test_backup_to_drive_filename_has_timestamp(tmp_path, monkeypatch):
    db_file = tmp_path / "portfolio.db"
    db_file.write_bytes(b"SQLite format 3\x00")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test_secret")

    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "folder_123"}]
    }
    mock_service.files.return_value.create.return_value.execute.return_value = {"id": "file_789"}

    with patch("backup._get_credentials", return_value=mock_creds), \
         patch("backup.build", return_value=mock_service):
        from backup import backup_to_drive
        backup_to_drive(folder_name="test-backup")

    call_kwargs = mock_service.files.return_value.create.call_args
    file_metadata = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body") or call_kwargs[0][0]
    filename = file_metadata["name"]
    assert filename.startswith("portfolio_backup_")
    assert filename.endswith(".db.gz")
