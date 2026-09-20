from __future__ import annotations

import base64
import html
import os
import smtplib
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


def _digest_message(
    day: str,
    items: list[AcceptedItem],
    recipients: list[str] | str,
    top_n: int,
    warnings: list[str] | None,
    sender: str,
) -> tuple[EmailMessage, list[str]]:
    ranked = sorted(items, key=lambda x: x.relevance_score, reverse=True)[:top_n]
    lines = [f"Trading research for {day}: {len(items)} accepted; showing top {len(ranked)}.", ""]
    html_lines = [
        f"<p>Trading research for {html.escape(day)}: {len(items)} accepted; "
        f"showing top {len(ranked)}.</p>"
    ]
    if warnings:
        lines.append("Pipeline warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
        html_lines.append("<p><strong>Pipeline warnings:</strong></p><ul>")
        html_lines.extend(f"<li>{html.escape(warning)}</li>" for warning in warnings)
        html_lines.append("</ul>")
    for index, item in enumerate(ranked, 1):
        lines.append(f"{index}. {item.title}")
        abstract = (getattr(item, "abstract_or_title", "") or "").strip()
        if abstract and abstract.casefold() != item.title.strip().casefold():
            lines.append(f"abstract: {abstract}")
        pdf_status = "saved to Google Drive" if getattr(item, "local_pdf_path", None) else "no verified public copy available"
        lines.append(f"pdf: {pdf_status}")
        lines.extend([f"link: {item.canonical_url}", ""])
        html_entry = [f"<p>{index}. <strong>{html.escape(item.title)}</strong><br>"]
        if abstract and abstract.casefold() != item.title.strip().casefold():
            html_entry.append(f"abstract: {html.escape(abstract)}<br>")
        html_entry.append(f"pdf: {html.escape(pdf_status)}<br>")
        safe_url = html.escape(item.canonical_url, quote=True)
        html_entry.append(f'link: <a href="{safe_url}">{html.escape(item.canonical_url)}</a></p>')
        html_lines.extend(html_entry)
    message = EmailMessage()
    if isinstance(recipients, str):
        recipients = [recipients]
    message["To"] = ", ".join(recipients)
    message["From"] = sender
    message["Subject"] = f"Trading research digest - {day}"
    message.set_content("\n".join(lines))
    message.add_alternative("\n".join(html_lines), subtype="html")
    return message, recipients


def send_digest(day: str, items: list[AcceptedItem], recipients: list[str] | str, top_n: int,
                warnings: list[str] | None = None, config: dict | None = None) -> str:
    config = config or {}
    transport = config.get("transport", "gmail_oauth")
    sender = os.getenv("GMAIL_SENDER") or "me"
    message, recipients = _digest_message(day, items, recipients, top_n, warnings, sender)

    if transport == "smtp_app_password":
        if sender == "me" or "@" not in sender:
            raise RuntimeError("GMAIL_SENDER must be the full Gmail address for SMTP delivery")
        password_env = config.get("app_password_env", "GMAIL_APP_PASSWORD")
        password = (os.getenv(password_env) or "").replace(" ", "")
        if not password:
            raise RuntimeError(f"Missing Gmail SMTP app password environment variable: {password_env}")
        host = config.get("smtp_host", "smtp.gmail.com")
        port = int(config.get("smtp_port", 465))
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(sender, password)
            smtp.send_message(message, from_addr=sender, to_addrs=recipients)
        return "smtp_sent"

    if transport != "gmail_oauth":
        raise RuntimeError(f"Unsupported email transport: {transport}")
    client_file = os.getenv("GMAIL_CLIENT_SECRET_FILE", "secrets/gmail_client_secret.json")
    token_file = os.getenv("GMAIL_TOKEN_FILE", "secrets/gmail_token.json")
    if not Path(client_file).exists():
        raise RuntimeError(f"Gmail OAuth client file not found: {client_file}")
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    result = gmail_service(client_file, token_file).users().messages().send(userId="me", body={"raw": encoded}).execute()
    return str(result.get("id", "sent"))
