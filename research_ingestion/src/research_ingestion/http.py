from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


USER_AGENT = "TradingResearchIngestion/0.1 (contact: vd373094@gmail.com)"


@dataclass
class Download:
    content: bytes
    content_type: str
    final_url: str


class PublicHttpClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        )

    def close(self) -> None:
        self.client.close()

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
            retries: int = 3, max_bytes: int | None = None) -> Download:
        delay = 1.0
        for attempt in range(retries):
            try:
                with self.client.stream("GET", url, params=params, headers=headers) as response:
                    if response.status_code == 429 and attempt + 1 < retries:
                        retry_after = response.headers.get("retry-after", "")
                        wait = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 3.0
                        time.sleep(max(3.0, wait))
                        delay = max(delay * 2, 3.0)
                        continue
                    if response.status_code in {402, 429}:
                        response.raise_for_status()
                    if response.status_code >= 500 and attempt + 1 < retries:
                        time.sleep(delay)
                        delay *= 2
                        continue
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if max_bytes is not None and len(content) > max_bytes:
                            raise ValueError(f"Response exceeds {max_bytes} bytes: {url}")
                    return Download(
                        bytes(content),
                        response.headers.get("content-type", "").lower(),
                        str(response.url),
                    )
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt + 1 == retries:
                    raise
                time.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")
