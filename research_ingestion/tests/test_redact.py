from research_ingestion.redact import redact_sensitive


def test_redacts_query_and_bearer_credentials():
    value = "https://example.test/search?q=x&apiKey=secret123&other=ok Authorization: Bearer token.value"
    redacted = redact_sensitive(value)
    assert "secret123" not in redacted
    assert "token.value" not in redacted
    assert "apiKey=<redacted>" in redacted
    assert "other=ok" in redacted
