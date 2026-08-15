from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from pathlib import Path

from .models import AcceptedItem


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def gmail_service(client_secret_file: str, token_file: str):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Install Gmail support with: python -m pip install -e .[email]") from exc

    token_path = Path(token_file)
    credentials = Credentials.from_authorized_user_file(token_path, SCOPES) if token_path.exists() else None
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
        credentials = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def send_digest(day: str, items: list[AcceptedItem], recipient: str, top_n: int,
                warnings: list[str] | None = None) -> str:
    client_file = os.getenv("GMAIL_CLIENT_SECRET_FILE", "secrets/gmail_client_secret.json")
    token_file = os.getenv("GMAIL_TOKEN_FILE", "secrets/gmail_token.json")
    sender = os.getenv("GMAIL_SENDER", "me")
    if not Path(client_file).exists():
        raise RuntimeError(f"Gmail OAuth client file not found: {client_file}")
    ranked = sorted(items, key=lambda x: x.relevance_score, reverse=True)[:top_n]
    lines = [f"Trading research for {day}: {len(items)} accepted; showing top {len(ranked)}.", ""]
    if warnings:
        lines.append("Pipeline warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    for index, item in enumerate(ranked, 1):
        lines.extend([f"{index}. {item.title}", item.canonical_url, f"Source: {item.source} | relevance: {item.relevance_score:.2f}", ""])
    message = EmailMessage()
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = f"Trading research digest — {day}"
    message.set_content("\n".join(lines))
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    result = gmail_service(client_file, token_file).users().messages().send(userId="me", body={"raw": encoded}).execute()
    return str(result.get("id", "sent"))
