from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .models import AcceptedItem


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def safe_drive_filename(title: str, suffix: str = ".pdf") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    cleaned = " ".join(cleaned.split()).strip(" .") or "untitled-paper"
    return f"{cleaned[:160].rstrip()}{suffix}"


def drive_service(client_secret_file: str, token_file: str, expected_account: str):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Install Google support with: python -m pip install -e .[email]") from exc

    token_path = Path(token_file)
    credentials = Credentials.from_authorized_user_file(token_path, DRIVE_SCOPES) if token_path.exists() else None
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, DRIVE_SCOPES)
        credentials = flow.run_local_server(port=0, login_hint=expected_account, prompt="consent")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")

    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    actual_account = service.about().get(fields="user(emailAddress)").execute()["user"]["emailAddress"]
    if actual_account.casefold() != expected_account.casefold():
        raise RuntimeError(
            f"Google Drive OAuth account mismatch: expected {expected_account}, authorized {actual_account}. "
            f"Remove {token_file} and authorize again with the expected account."
        )
    return service


def _query_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_folder(service, name: str, parent_id: str | None) -> str | None:
    clauses = [
        f"name = '{_query_literal(name)}'",
        f"mimeType = '{FOLDER_MIME}'",
        "trashed = false",
    ]
    if parent_id:
        clauses.append(f"'{_query_literal(parent_id)}' in parents")
    result = service.files().list(
        q=" and ".join(clauses), spaces="drive", fields="files(id,name)", pageSize=10
    ).execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def _ensure_folder(service, name: str, parent_id: str | None = None) -> str:
    existing = _find_folder(service, name, parent_id)
    if existing:
        return existing
    metadata = {"name": name, "mimeType": FOLDER_MIME}
    if parent_id:
        metadata["parents"] = [parent_id]
    return service.files().create(body=metadata, fields="id").execute()["id"]


def authorize_drive(config: dict) -> dict:
    client_file = os.getenv("GDRIVE_CLIENT_SECRET_FILE") or os.getenv(
        "GMAIL_CLIENT_SECRET_FILE", "secrets/gmail_client_secret.json"
    )
    token_file = os.getenv("GDRIVE_TOKEN_FILE", "secrets/drive_token.json")
    account = config["account"]
    if not Path(client_file).exists():
        raise RuntimeError(f"Google OAuth client file not found: {client_file}")
    drive_service(client_file, token_file, account)
    return {"status": "authorized", "account": account, "token_file": token_file}


def upload_accepted_pdfs(day: str, items: list[AcceptedItem], config: dict) -> dict:
    pdf_items = [item for item in items if item.local_pdf_path and Path(item.local_pdf_path).is_file()]
    if not pdf_items:
        return {"status": "no_pdfs", "uploaded": 0, "already_present": 0}

    client_file = os.getenv("GDRIVE_CLIENT_SECRET_FILE") or os.getenv(
        "GMAIL_CLIENT_SECRET_FILE", "secrets/gmail_client_secret.json"
    )
    token_file = os.getenv("GDRIVE_TOKEN_FILE", "secrets/drive_token.json")
    service = drive_service(client_file, token_file, config["account"])
    root_id = _ensure_folder(service, config.get("root_folder_name", "Trading Research Library"))
    year_id = _ensure_folder(service, day[:4], root_id)
    day_id = _ensure_folder(service, day, year_id)

    existing = service.files().list(
        q=f"'{_query_literal(day_id)}' in parents and trashed = false",
        spaces="drive",
        fields="files(id,name,appProperties)",
        pageSize=1000,
    ).execute().get("files", [])
    existing_hashes = {
        (entry.get("appProperties") or {}).get("sha256") for entry in existing
        if (entry.get("appProperties") or {}).get("sha256")
    }

    from googleapiclient.http import MediaFileUpload

    uploaded = 0
    already_present = 0
    for item in pdf_items:
        path = Path(item.local_pdf_path)
        content_hash = item.content_sha256 or hashlib.sha256(path.read_bytes()).hexdigest()
        if content_hash in existing_hashes:
            already_present += 1
            continue
        metadata = {
            "name": safe_drive_filename(item.title),
            "parents": [day_id],
            "description": item.canonical_url,
            "appProperties": {"sha256": content_hash, "source": item.source[:100]},
        }
        media = MediaFileUpload(str(path), mimetype="application/pdf", resumable=True)
        service.files().create(body=metadata, media_body=media, fields="id").execute()
        existing_hashes.add(content_hash)
        uploaded += 1
    return {
        "status": "completed",
        "uploaded": uploaded,
        "already_present": already_present,
        "folder_path": f"{config.get('root_folder_name', 'Trading Research Library')}/{day[:4]}/{day}",
    }
