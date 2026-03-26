# Google Drive Backup — Design Spec
Date: 2026-03-26

## Overview

Add a `python cli.py backup` command that compresses the local SQLite database and uploads it to the user's Google Drive under a dedicated folder. No server required — operates directly on the DB file.

## Configuration

### `.env` / `.env.example`
Three new variables added (actual values committed to `.env.example` since OAuth2 desktop client credentials are public by design):

```
GOOGLE_CLIENT_ID=<client_id from GCP>
GOOGLE_CLIENT_SECRET=<client_secret from GCP>
GOOGLE_DRIVE_BACKUP_FOLDER=financial-tracker-backup
```

`GOOGLE_DRIVE_BACKUP_FOLDER` defaults to `financial-tracker-backup` if not set.

### Token storage
Cached OAuth token stored at `~/.financial-tracker/token.json`. Directory created automatically on first run. Never committed.

### Credentials source
The GCP `client_secret_*.json` file at `/Users/dhirajkasar/Downloads/` is the source of truth for `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. The file itself is never committed to the repo.

## Architecture

### New file: `backend/backup.py`

Single public function:
```python
def backup_to_drive() -> str:
    """Compress DB and upload to Google Drive. Returns Drive file ID."""
```

Internal steps:
1. **Resolve DB path** — parse `DATABASE_URL` env var, strip `sqlite:///` prefix, resolve to absolute path. Exit with clear message if not set or file not found.
2. **Validate credentials** — check `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set. Exit with setup instructions if missing.
3. **Gzip compress** — read DB file bytes, compress in-memory with `gzip.compress()`. No temp files written to disk.
4. **OAuth2 flow** — load `~/.financial-tracker/token.json` if exists; refresh if expired; else run `InstalledAppFlow` (opens browser for one-time authorization). Save updated token after each run.
5. **Drive folder** — search for folder named `GOOGLE_DRIVE_BACKUP_FOLDER` owned by user; create it if not found.
6. **Upload** — upload compressed bytes as `portfolio_backup_<YYYY-MM-DDTHH-MM-SS>.db.gz`. Returns Drive file ID.

### CLI integration: `backend/cli.py`

New top-level subcommand `backup`. No required arguments.

```
python cli.py backup [--folder FOLDER_NAME]
```

`--folder` overrides `GOOGLE_DRIVE_BACKUP_FOLDER` env var (falls back to `financial-tracker-backup`).

Output on success:
```
  → Compressing dhiraj_financial_portfolio.db...
  → Authenticating with Google Drive...
  → Uploading portfolio_backup_2026-03-26T14-30-00.db.gz to financial-tracker-backup...
  → Done. File ID: 1abc...xyz
```

First-run note printed before browser opens:
```
  → First run: opening browser for Google authorization...
```

### Dependencies

Added to `backend/pyproject.toml` (or `setup.cfg`/`requirements`):
- `google-auth-oauthlib`
- `google-api-python-client`

## Error Handling

| Condition | Behaviour |
|---|---|
| `DATABASE_URL` not set | `sys.exit("DATABASE_URL not set in .env")` |
| DB file not found at resolved path | `sys.exit("DB file not found at <path>")` |
| `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` missing | `sys.exit` with instructions to copy `.env.example` |
| Drive API error | Print error message, `sys.exit` |
| Token directory doesn't exist | Auto-create `~/.financial-tracker/` |

## Multi-user Story

Other users:
1. `cp .env.example .env` — credentials already present (public client creds, safe to commit to `.env.example`)
2. `python cli.py backup` — browser opens, user authorizes with their own Google account
3. `~/.financial-tracker/token.json` created for their account — subsequent runs are headless

Each user backs up to their own Google Drive. Shared app credentials, separate user tokens.

## Non-goals

- Scheduled / automatic backups (can be added via cron externally)
- Retention / deletion of old backups
- Restore from backup via CLI
- Encryption of backup file
- PostgreSQL backup support (SQLite only)
