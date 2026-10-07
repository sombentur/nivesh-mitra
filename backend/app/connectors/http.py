"""Shared HTTP client: identifies itself honestly, retries politely, never hammers a source."""

import time

import httpx

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NiveshMitra/0.1 (personal, non-commercial)"


class SourceUnavailable(Exception):
    """The data source couldn't be reached or returned something unusable."""


def get_text(url: str, *, params: dict | None = None, timeout: float = 60, retries: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True) as client:
                r = client.get(url, params=params)
            if r.status_code == 200:
                return r.text
            last = SourceUnavailable(f"{url} returned HTTP {r.status_code}")
            if r.status_code in (400, 401, 403, 404):
                break  # retrying won't help
        except httpx.HTTPError as exc:
            last = exc
        time.sleep(2 * (attempt + 1))
    raise SourceUnavailable(str(last))


def get_bytes(url: str, *, params: dict | None = None, timeout: float = 120, retries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True) as client:
                r = client.get(url, params=params)
            if r.status_code == 200 and r.content:
                return r.content
            last = SourceUnavailable(f"{url} returned HTTP {r.status_code}")
            if r.status_code in (400, 401, 403, 404):
                break
        except httpx.HTTPError as exc:
            last = exc
        time.sleep(2 * (attempt + 1))
    raise SourceUnavailable(str(last))


def get_json(url: str, **kw) -> dict | list:
    import json

    text = get_text(url, **kw)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise SourceUnavailable(f"{url} did not return JSON") from exc
