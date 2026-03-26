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


class _MediaInMemoryUploadWithBody(MediaInMemoryUpload):
    """MediaInMemoryUpload subclass that exposes raw bytes via ``_body``."""

    def __init__(self, body: bytes, mimetype: str = "application/octet-stream", **kwargs):
        super().__init__(body, mimetype=mimetype, **kwargs)
        self._body = body


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
    from google.auth.exceptions import RefreshError

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
            try:
                creds.refresh(Request())
            except RefreshError:
                print("  → Stored token is invalid or revoked. Re-authorizing...")
                TOKEN_PATH.unlink(missing_ok=True)
                creds = None
        if not creds or not creds.valid:
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
    media = _MediaInMemoryUploadWithBody(compressed, mimetype="application/gzip")
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
