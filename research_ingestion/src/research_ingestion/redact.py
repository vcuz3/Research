from __future__ import annotations

import re


_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:api[-_]?key|access[-_]?token|client[-_]?secret|token|key)=)[^&\s'\"]+"
)
_BEARER_SECRET = re.compile(r"(?i)(authorization:\s*bearer\s+|bearer\s+)[A-Za-z0-9._~+/=-]+")


def redact_sensitive(value: object) -> str:
    """Remove credentials commonly embedded in exception text and URLs."""
    text = str(value)
    text = _QUERY_SECRET.sub(r"\1<redacted>", text)
    return _BEARER_SECRET.sub(r"\1<redacted>", text)
