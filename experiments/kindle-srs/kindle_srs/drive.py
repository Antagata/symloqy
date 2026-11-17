"""
Google Drive client.

Responsibilities:
  - Authenticate with a service account
  - Sync new photos from KindleSRS/MyPhotos/ into the DB
  - Download individual photo bytes for Claude Vision
  - Download / upload the SQLite DB file (persistence across GitHub Actions runs)

Setup:
  1. Create a Google Cloud project, enable Drive API
  2. Create a Service Account, download credentials.json
  3. Share the 'KindleSRS' Drive folder with the service account email
  4. Set GOOGLE_CREDENTIALS_FILE=credentials.json  (local)
     or GOOGLE_CREDENTIALS_JSON=<full JSON string>  (GitHub Actions secret)
"""

import io
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    from kindle_srs.config import GOOGLE_CREDENTIALS_JSON, GOOGLE_CREDENTIALS_FILE

    if GOOGLE_CREDENTIALS_JSON:
        info = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    elif GOOGLE_CREDENTIALS_FILE and os.path.exists(GOOGLE_CREDENTIALS_FILE):
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
        )
    else:
        raise RuntimeError(
            "No Google credentials found. "
            "Set GOOGLE_CREDENTIALS_JSON or GOOGLE_CREDENTIALS_FILE."
        )

    return build("drive", "v3", credentials=creds)


# ── Folder navigation ─────────────────────────────────────────────────────────

def _get_or_create_folder(service, name: str, parent_id: Optional[str] = None) -> str:
    """Return existing folder ID or create a new one."""
    q = (
        f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
        f" and trashed=false"
    )
    if parent_id:
        q += f" and '{parent_id}' in parents"

    results = service.files().list(q=q, fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def _resolve_folder_path(service, path: str) -> str:
    """
    Resolve a path like 'KindleSRS/MyPhotos' to a Drive folder ID,
    creating missing folders along the way.
    """
    parts = path.strip("/").split("/")
    parent_id = None
    for part in parts:
        parent_id = _get_or_create_folder(service, part, parent_id)
    return parent_id


# ── Photo sync ────────────────────────────────────────────────────────────────

def list_drive_photos(photos_folder_path: str) -> list[tuple[str, str]]:
    """
    List all image files in the Drive photos folder.
    Returns list of (drive_file_id, filename).
    """
    service = _get_service()
    folder_id = _resolve_folder_path(service, photos_folder_path)

    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false and mimeType contains 'image/'",
        fields="files(id, name)",
        orderBy="createdTime desc",
        pageSize=200,
    ).execute()

    return [(f["id"], f["name"]) for f in results.get("files", [])]


def download_file(file_id: str) -> bytes:
    """Download a file from Drive and return raw bytes."""
    from googleapiclient.http import MediaIoBaseDownload

    service = _get_service()
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


# ── Database persistence ──────────────────────────────────────────────────────

def download_db(root_folder_path: str, db_filename: str, local_path: str) -> bool:
    """
    Download the SQLite DB from Drive to local_path.
    Returns True if the file existed and was downloaded, False if it's a fresh start.
    """
    service = _get_service()
    folder_id = _resolve_folder_path(service, root_folder_path)

    results = service.files().list(
        q=f"'{folder_id}' in parents and name='{db_filename}' and trashed=false",
        fields="files(id)",
    ).execute()
    files = results.get("files", [])

    if not files:
        logger.info(f"No existing DB in Drive — starting fresh: {db_filename}")
        return False

    data = download_file(files[0]["id"])
    with open(local_path, "wb") as f:
        f.write(data)
    logger.info(f"Downloaded DB from Drive: {db_filename} ({len(data):,} bytes)")
    return True


def upload_db(root_folder_path: str, db_filename: str, local_path: str):
    """Upload (create or overwrite) the SQLite DB in Drive."""
    from googleapiclient.http import MediaFileUpload

    service = _get_service()
    folder_id = _resolve_folder_path(service, root_folder_path)

    results = service.files().list(
        q=f"'{folder_id}' in parents and name='{db_filename}' and trashed=false",
        fields="files(id)",
    ).execute()
    existing = results.get("files", [])

    media = MediaFileUpload(local_path, mimetype="application/x-sqlite3", resumable=False)

    if existing:
        service.files().update(fileId=existing[0]["id"], media_body=media).execute()
        logger.info(f"Updated DB in Drive: {db_filename}")
    else:
        meta = {"name": db_filename, "parents": [folder_id]}
        service.files().create(body=meta, media_body=media, fields="id").execute()
        logger.info(f"Created DB in Drive: {db_filename}")
