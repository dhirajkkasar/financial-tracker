# Google Drive Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `python cli.py backup` command that gzip-compresses the local SQLite DB and uploads it to the user's Google Drive under a `financial-tracker-backup` folder.

**Architecture:** A standalone `backend/backup.py` module holds all Google Drive logic (auth, folder lookup, upload). `cli.py` imports it lazily in `cmd_backup()` and wires a new `backup` subcommand. OAuth2 token is cached per-user at `~/.financial-tracker/token.json`; credentials come from `.env`.

**Tech Stack:** `google-auth-oauthlib`, `google-api-python-client`, Python `gzip` (stdlib), `python-dotenv` (already installed)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/pyproject.toml` | Modify | Add `google-auth-oauthlib`, `google-api-python-client` dependencies |
| `backend/.env` | Modify | Add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_DRIVE_BACKUP_FOLDER` |
| `backend/.env.example` | Modify | Same keys with real values (public client creds — safe to commit) |
| `backend/backup.py` | Create | All Drive logic: resolve DB path, compress, OAuth2, folder, upload |
| `backend/tests/unit/test_backup.py` | Create | Unit tests for every function in backup.py |
| `backend/cli.py` | Modify | Add `cmd_backup()` function + `backup` argparse subcommand |

---

### Task 1: Add dependencies and credentials

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/.env`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add Google client libraries to pyproject.toml**

In `backend/pyproject.toml`, add to the `dependencies` list (after `scipy>=1.13.0`):

```toml
    "google-auth-oauthlib>=1.2.0",
    "google-api-python-client>=2.130.0",
```

- [ ] **Step 2: Install dependencies**

```bash
cd backend
pip install -e ".[dev]"
```

Expected: installs `google-auth-oauthlib` and `google-api-python-client` without errors.

- [ ] **Step 3: Add credentials to .env**

Append to `backend/.env`:

```
GOOGLE_CLIENT_ID=213530153682-rm4lnbnbr00qofus2s58im5hfv64a77a.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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
GOOGLE_DRIVE_BACKUP_FOLDER=financial-tracker-backup
```

- [ ] **Step 4: Add credentials to .env.example**

Append to `backend/.env.example` (these are public client creds — safe to commit):

```
GOOGLE_CLIENT_ID=213530153682-rm4lnbnbr00qofus2s58im5hfv64a77a.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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
GOOGLE_DRIVE_BACKUP_FOLDER=financial-tracker-backup
```

- [ ] **Step 5: Commit**

```bash
cd backend
git add pyproject.toml .env.example
git commit -m "feat: add google-auth-oauthlib and google-api-python-client dependencies"
```

(Do NOT stage `.env` — it is gitignored.)

---

### Task 2: Write failing tests for backup.py

**Files:**
- Create: `backend/tests/unit/test_backup.py`

- [ ] **Step 1: Create the test file**

Create `backend/tests/unit/test_backup.py`:

```python
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


def test_resolve_db_path_relative_url(tmp_path, monkeypatch, tmp_path_cwd):
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
# ---------------------------------------------------------------------------

def test_get_credentials_missing_client_id_exits(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")

    from backup import _get_credentials
    with pytest.raises(SystemExit, match="GOOGLE_CLIENT_ID"):
        _get_credentials()


def test_get_credentials_missing_client_secret_exits(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "my_id")
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    from backup import _get_credentials
    with pytest.raises(SystemExit, match="GOOGLE_CLIENT_ID"):
        _get_credentials()


def test_get_credentials_uses_cached_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "my_id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "my_secret")

    token_dir = tmp_path / ".financial-tracker"
    token_dir.mkdir()
    token_file = token_dir / "token.json"

    mock_creds = MagicMock()
    mock_creds.valid = True

    with patch("backup.TOKEN_PATH", token_file), \
         patch("backup.Credentials") as mock_creds_cls:
        token_file.write_text(json.dumps({"token": "fake"}))
        mock_creds_cls.from_authorized_user_info.return_value = mock_creds

        from backup import _get_credentials
        result = _get_credentials()

    assert result is mock_creds
    mock_creds_cls.from_authorized_user_info.assert_called_once()


def test_get_credentials_refreshes_expired_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "my_id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "my_secret")

    token_dir = tmp_path / ".financial-tracker"
    token_dir.mkdir()
    token_file = token_dir / "token.json"
    token_file.write_text(json.dumps({"token": "old"}))

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh_tok"

    with patch("backup.TOKEN_PATH", token_file), \
         patch("backup.Credentials") as mock_creds_cls, \
         patch("backup.Request") as mock_request:
        mock_creds_cls.from_authorized_user_info.return_value = mock_creds
        mock_creds.to_json.return_value = json.dumps({"token": "refreshed"})

        from backup import _get_credentials
        result = _get_credentials()

    mock_creds.refresh.assert_called_once()
    assert result is mock_creds


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
```

- [ ] **Step 2: Add `tmp_path_cwd` fixture to `tests/unit/conftest.py` (or create it)**

Check if `backend/tests/unit/conftest.py` exists. If not, create it:

```python
import pytest


@pytest.fixture
def tmp_path_cwd(tmp_path, monkeypatch):
    """Fixture that changes cwd to tmp_path for relative path tests."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
```

If it already exists, just append the fixture.

- [ ] **Step 3: Run tests to confirm they all fail (RED)**

```bash
cd backend
uv run pytest tests/unit/test_backup.py -v 2>&1 | head -40
```

Expected: `ModuleNotFoundError: No module named 'backup'` or similar — confirms tests are wired correctly before any implementation.

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/unit/test_backup.py tests/unit/conftest.py
git commit -m "test: add failing unit tests for backup module"
```

---

### Task 3: Implement backup.py

**Files:**
- Create: `backend/backup.py`

- [ ] **Step 1: Create backup.py**

Create `backend/backup.py`:

```python
"""Google Drive backup for the local SQLite portfolio database."""
import gzip
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

TOKEN_PATH = Path.home() / ".financial-tracker" / "token.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _resolve_db_path() -> Path:
    """Parse DATABASE_URL and return absolute path to the SQLite file."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        sys.exit("DATABASE_URL not set. Add it to backend/.env")
    if not db_url.startswith("sqlite:///"):
        sys.exit(f"DATABASE_URL must be a sqlite:/// URL, got: {db_url!r}")
    path_str = db_url[len("sqlite:///"):]
    path = Path(path_str).resolve()
    if not path.exists():
        sys.exit(f"DB file not found at {path}. Check DATABASE_URL in .env")
    return path


def _get_credentials() -> Credentials:
    """Load or obtain OAuth2 credentials, refreshing or re-authorizing as needed."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env\n"
            "  Copy backend/.env.example to backend/.env to get started."
        )

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_info(
            json.loads(TOKEN_PATH.read_text()), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("  → First run: opening browser for Google authorization...")
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost"],
                    }
                },
                SCOPES,
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def _get_or_create_folder(service, folder_name: str) -> str:
    """Return Drive folder ID for folder_name, creating it if absent."""
    results = (
        service.files()
        .list(
            q=(
                f"name='{folder_name}' "
                "and mimeType='application/vnd.google-apps.folder' "
                "and trashed=false"
            ),
            spaces="drive",
            fields="files(id, name)",
        )
        .execute()
    )
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    folder = (
        service.files()
        .create(
            body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
            fields="id",
        )
        .execute()
    )
    return folder["id"]


def backup_to_drive(folder_name: str | None = None) -> str:
    """Compress the SQLite DB and upload to Google Drive. Returns Drive file ID."""
    load_dotenv()

    folder_name = folder_name or os.getenv(
        "GOOGLE_DRIVE_BACKUP_FOLDER", "financial-tracker-backup"
    )

    db_path = _resolve_db_path()
    print(f"  → Compressing {db_path.name}...")
    compressed = gzip.compress(db_path.read_bytes())

    print("  → Authenticating with Google Drive...")
    creds = _get_credentials()
    service = build("drive", "v3", credentials=creds)

    folder_id = _get_or_create_folder(service, folder_name)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"portfolio_backup_{timestamp}.db.gz"

    print(f"  → Uploading {filename} to {folder_name}...")
    media = MediaInMemoryUpload(compressed, mimetype="application/gzip")
    result = (
        service.files()
        .create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id",
        )
        .execute()
    )

    file_id = result["id"]
    print(f"  → Done. File ID: {file_id}")
    return file_id
```

- [ ] **Step 2: Run tests — expect GREEN**

```bash
cd backend
uv run pytest tests/unit/test_backup.py -v
```

Expected: all tests pass. If any fail, fix before proceeding.

- [ ] **Step 3: Commit**

```bash
git add backup.py
git commit -m "feat: add backup.py — Google Drive DB backup module"
```

---

### Task 4: Wire backup command into cli.py

**Files:**
- Modify: `backend/cli.py`

- [ ] **Step 1: Add `cmd_backup()` function**

Find the `cmd_snapshot` function in `cli.py` (search for `def cmd_snapshot`). Add `cmd_backup` immediately after it:

```python
def cmd_backup(folder: str | None = None):
    import backup as _backup
    _backup.backup_to_drive(folder_name=folder)
```

The lazy import keeps CLI startup fast and avoids import errors if google libraries aren't installed on a machine that only uses other commands.

- [ ] **Step 2: Add `backup` to the argparse subcommands**

Find the block in `cli.py` where subparsers are defined (search for `sub = parser.add_subparsers`). Add the `backup` subparser alongside the others:

```python
p_backup = sub.add_parser("backup", help="Backup DB to Google Drive")
p_backup.add_argument(
    "--folder",
    default=None,
    help="Drive folder name (overrides GOOGLE_DRIVE_BACKUP_FOLDER env var)",
)
```

- [ ] **Step 3: Add backup dispatch in `main()`**

In the `main()` function, find the block `elif args.command == "snapshot":` and add immediately after it:

```python
    elif args.command == "backup":
        cmd_backup(folder=getattr(args, "folder", None))
```

- [ ] **Step 4: Run the full test suite to check nothing is broken**

```bash
cd backend
uv run pytest tests/ -v --ignore=tests/unit/test_backup.py 2>&1 | tail -20
```

Expected: same pass/fail count as before this task. No regressions.

- [ ] **Step 5: Commit**

```bash
git add cli.py
git commit -m "feat: add 'backup' CLI command wired to backup.py"
```

---

### Task 5: Update CLAUDE.md CLI reference

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add backup to the CLI commands list**

In `CLAUDE.md`, find the `python cli.py snapshot` line under the `### Backend` commands section. Add immediately after it:

```
python cli.py backup                     # Backup SQLite DB to Google Drive (gzip-compressed)
python cli.py backup --folder my-folder  # Override Drive folder name
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add backup CLI command to CLAUDE.md"
```

---

### Task 6: Smoke test (manual, real network)

- [ ] **Step 1: Verify `.env` has all three new variables**

```bash
cd backend
grep GOOGLE .env
```

Expected output (values may differ):
```
GOOGLE_CLIENT_ID=213530153682-...
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_DRIVE_BACKUP_FOLDER=financial-tracker-backup
```

- [ ] **Step 2: Run the backup command**

```bash
cd backend
python cli.py backup
```

First run: browser opens at Google OAuth consent screen. Authorize. Then:

```
  → Compressing dhiraj_financial_portfolio.db...
  → Authenticating with Google Drive...
  → First run: opening browser for Google authorization...
  → Uploading portfolio_backup_2026-03-26T14-30-00.db.gz to financial-tracker-backup...
  → Done. File ID: 1abc...xyz
```

- [ ] **Step 3: Verify token was cached**

```bash
ls ~/.financial-tracker/token.json
```

Expected: file exists.

- [ ] **Step 4: Run backup a second time (should be headless)**

```bash
cd backend
python cli.py backup
```

Expected: no browser, completes silently to "Done."

- [ ] **Step 5: Verify file on Google Drive**

Open [drive.google.com](https://drive.google.com) → check for `financial-tracker-backup` folder → confirm two `.db.gz` files are present with timestamps.
