import base64
from email import message_from_bytes
from types import SimpleNamespace

from research_ingestion.emailer import send_digest


def test_digest_supports_multiple_recipients_and_abstract_below_title(monkeypatch, tmp_path):
    client_file = tmp_path / "client.json"
    client_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET_FILE", str(client_file))
    monkeypatch.delenv("GMAIL_SENDER", raising=False)
    sent = {}

    class SendCall:
        def execute(self):
            return {"id": "message-id"}

    class Messages:
        def send(self, **kwargs):
            sent.update(kwargs)
            return SendCall()

    class Users:
        def messages(self):
            return Messages()

    class Service:
        def users(self):
            return Users()

    monkeypatch.setattr("research_ingestion.emailer.gmail_service", lambda *_args: Service())
    item = SimpleNamespace(
        source="test-source",
        title="Useful trading paper",
        abstract_or_title="Evidence on market liquidity and execution quality.",
        canonical_url="https://example.test/paper",
        local_pdf_path=None,
        relevance_score=0.91,
    )

    result = send_digest(
        "2026-08-15",
        [item],
        ["reader1@example.test", "reader2@example.test"],
        25,
    )

    message = message_from_bytes(base64.urlsafe_b64decode(sent["body"]["raw"]))
    parts = {part.get_content_type(): part for part in message.walk() if not part.is_multipart()}
    body = parts["text/plain"].get_payload(decode=True).decode(parts["text/plain"].get_content_charset())
    html_body = parts["text/html"].get_payload(decode=True).decode(parts["text/html"].get_content_charset())
    assert result == "message-id"
    assert message["To"] == "reader1@example.test, reader2@example.test"
    assert message["From"] == "me"
    assert "Useful trading paper" in body
    assert "Useful trading paper\nabstract: Evidence on market liquidity and execution quality.\npdf: no verified public copy available\nlink: https://example.test/paper" in body
    assert "<strong>Useful trading paper</strong>" in html_body
    assert "abstract: Evidence on market liquidity and execution quality." in html_body
    assert "pdf: no verified public copy available" in html_body
    assert 'link: <a href="https://example.test/paper">https://example.test/paper</a>' in html_body
    assert "https://example.test/paper" in body
    assert "test-source" not in body
    assert "0.91" not in body


def test_digest_sends_with_smtp_app_password(monkeypatch):
    sent = {}
    monkeypatch.setenv("GMAIL_SENDER", "sender@example.test")
    monkeypatch.setenv("APP_PASSWORD", "abcd efgh ijkl mnop")

    class SMTP:
        def __init__(self, host, port, timeout):
            sent.update(host=host, port=port, timeout=timeout)
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def login(self, sender, password):
            sent.update(sender=sender, password=password)
        def send_message(self, message, from_addr, to_addrs):
            sent.update(message=message, from_addr=from_addr, to_addrs=to_addrs)

    monkeypatch.setattr("research_ingestion.emailer.smtplib.SMTP_SSL", SMTP)
    item = SimpleNamespace(
        title="Paper", abstract_or_title="Abstract", canonical_url="https://example.test",
        local_pdf_path=None, relevance_score=0.9,
    )
    result = send_digest(
        "2026-08-24", [item], ["reader@example.test"], 25, config={
            "transport": "smtp_app_password", "app_password_env": "APP_PASSWORD",
        },
    )

    assert result == "smtp_sent"
    assert sent["password"] == "abcdefghijklmnop"
    assert sent["to_addrs"] == ["reader@example.test"]
