"""NiveshMitra must never place, modify or cancel orders (principle 1). These tests enforce it."""

import re
from pathlib import Path

import pytest

from app.connectors import groww
from app.connectors.groww import BLOCKED_METHODS, GrowwReadOnlyClient, ReadOnlyViolation

APP_DIR = Path(__file__).resolve().parents[1] / "app"
GUARD_FILE = APP_DIR / "connectors" / "groww.py"


def test_no_order_method_names_outside_the_guard():
    pattern = re.compile("|".join(BLOCKED_METHODS))
    offenders = [
        str(p.relative_to(APP_DIR))
        for p in APP_DIR.rglob("*.py")
        if p != GUARD_FILE and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"order-method names found in: {offenders}"


def test_guard_lists_every_order_method_the_sdk_has():
    from growwapi import GrowwAPI

    sdk_writers = {m for m in dir(GrowwAPI) if re.match(r"(place|modify|cancel|create)_", m)}
    assert sdk_writers <= set(BLOCKED_METHODS), f"new SDK write methods not blocked: {sdk_writers - set(BLOCKED_METHODS)}"


def test_order_methods_are_disabled_on_the_private_sdk(monkeypatch):
    monkeypatch.setattr(groww.GrowwAPI, "get_access_token", staticmethod(lambda **kw: "fake-token"))
    monkeypatch.setattr(groww.GrowwAPI, "__init__", lambda self, token: None)
    client = GrowwReadOnlyClient("JWT-ish-token", "JBSWY3DPEHPK3PXP")
    sdk = client._sdk()
    for name in BLOCKED_METHODS:
        with pytest.raises(ReadOnlyViolation):
            getattr(sdk, name)(symbol="RELIANCE", quantity=1)


def test_client_exposes_no_order_methods():
    public = {m for m in dir(GrowwReadOnlyClient) if not m.startswith("_")}
    assert public == {"auth_method", "profile", "holdings", "daily_candles", "intraday_candles", "recent_intraday_candles", "ltp"}


@pytest.mark.parametrize(
    "value,expected",
    [("JBSWY3DPEHPK3PXP", True), ("jbsw y3dp ehpk 3pxp", True), ("a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6", False), ("short", False)],
)
def test_detects_totp_secret(value, expected):
    assert groww.is_totp_secret(value) is expected


class _FlakySdk:
    """Answers with Groww's rate-limit error `fails` times, then returns candles."""

    def __init__(self, fails):
        self.fails, self.calls = fails, 0

    def get_historical_candle_data(self, **kw):
        self.calls += 1
        if self.calls <= self.fails:
            from growwapi.groww.exceptions import GrowwAPIException

            raise GrowwAPIException(code="429", msg="Rate limit has breached for your request. Please try again later.")
        return {"candles": [["2026-09-29T00:00:00", 100, 101, 99, 100, 1000, None]]}


def _client_with(sdk, monkeypatch):
    monkeypatch.setattr(groww, "BACKOFF_SECONDS", (0, 0, 0))
    c = GrowwReadOnlyClient("tok", "JBSWY3DPEHPK3PXP")
    monkeypatch.setattr(c, "_sdk", lambda: sdk)
    return c


def test_rate_limit_is_retried_not_skipped(monkeypatch):
    from datetime import date

    sdk = _FlakySdk(fails=2)
    candles = _client_with(sdk, monkeypatch).daily_candles("NSE-X", date(2026, 9, 20), date(2026, 9, 30))
    assert len(candles) == 1 and sdk.calls == 3


def test_persistent_rate_limit_raises_busy(monkeypatch):
    from datetime import date

    with pytest.raises(groww.GrowwBusy):
        _client_with(_FlakySdk(fails=99), monkeypatch).daily_candles("NSE-X", date(2026, 9, 20), date(2026, 9, 30))


def test_parse_candle_formats():
    assert groww.parse_candle(["2026-09-29T00:00:00", 100, 105, 99, 104, 12345, None]).close == 104
    assert groww.parse_candle([1790640000, 100, 105, 99, 104, 12345, None]).volume == 12345
    assert groww.parse_candle(["bad"]) is None
    no_open = groww.parse_candle(["2026-06-29T00:00:00", None, 1402.0, 1383.2, 1387.6, 13249405, None])
    assert no_open.open is None and no_open.close == 1387.6  # Groww omits recent opens — keep the day
    assert groww.parse_candle(["2026-09-29T00:00:00", 0, 0, 0, 0, 0, None]) is None


def test_dropped_connections_are_retried(monkeypatch):
    import requests

    from app.connectors import groww

    monkeypatch.setattr(groww, "BACKOFF_SECONDS", (0, 0))
    client = groww.GrowwReadOnlyClient("token", "JBSWY3DPEHPK3PXP")
    attempts = []

    class Sdk:
        def get_ltp(self, **kw):
            attempts.append(1)
            if len(attempts) < 3:
                raise requests.exceptions.ConnectionError("Connection aborted.")
            return {"NSE_X": 1.0}

    monkeypatch.setattr(client, "_sdk", lambda: Sdk())
    assert client.ltp(["NSE_X"]) == {"NSE_X": 1.0} and len(attempts) == 3
    attempts.clear()

    class Down:
        def get_ltp(self, **kw):
            raise requests.exceptions.ConnectionError("down")

    monkeypatch.setattr(client, "_sdk", lambda: Down())
    with pytest.raises(groww.GrowwBusy, match="network"):
        client.ltp(["NSE_X"])
