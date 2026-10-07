"""Groww Trade API — READ-ONLY (doc 01 §5).

Three layers keep this read-only:
1. The official SDK object is private to GrowwReadOnlyClient, which exposes only read methods.
2. Every order method on that private object is replaced by a function that raises ReadOnlyViolation.
3. tests/test_readonly_guard.py fails if an order-method name appears anywhere else in the codebase.

Groww has two price-history feeds (checked 3-Oct-2026):
- The candle-data feed (`get_historical_candle_data`) is current the same evening, has real opens, and its daily prices
  are already adjusted for splits and bonuses, back to 2019. It keeps 15-minute bars for about 3 months only, and reports
  their volume as the day's running total. The SDK calls this method deprecated, but it is the only feed that is current.
- The backtesting feed (`get_historical_candles`) has 15-minute bars back to 2020, but runs several days behind (and its
  newest days can be incomplete), isn't adjusted, leaves daily opens empty and double-counts daily volume.
So: daily candles and the latest 15-minute bars come from the candle-data feed; old 15-minute history from the other.
"""

import re
import threading
import time
import warnings
from collections import deque
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pyotp
import requests
from growwapi import GrowwAPI
from growwapi.groww import exceptions as gx

from app.connectors.http import SourceUnavailable

# The ONLY place these names may appear (see tests/test_readonly_guard.py).
BLOCKED_METHODS = (
    "place_order",
    "modify_order",
    "cancel_order",
    "create_smart_order",
    "modify_smart_order",
    "cancel_smart_order",
)

DAILY_CHUNK_DAYS = 1000  # candle-data feed: up to 1080 days of daily candles per request
RECENT_INTRADAY_CHUNK_DAYS = 25  # candle-data feed: about 30 days of 15-minute candles per request
INTRADAY_CHUNK_DAYS = 88  # backtesting feed: up to 90 days of 15-minute candles per request (history from 2020)
IST = ZoneInfo("Asia/Kolkata")
warnings.filterwarnings("ignore", message=".*get_historical_candle_data.*", category=DeprecationWarning)
TOKEN_LIFETIME = timedelta(hours=6)  # tokens last until ~6 am; refreshing more often is harmless


class ReadOnlyViolation(RuntimeError):
    pass


class GrowwNotConnected(SourceUnavailable):
    """Keys missing, wrong, or Groww refused the login — the user needs to reconnect."""


class GrowwNoDataAccess(SourceUnavailable):
    """Logged in, but this Groww plan doesn't include market data (prices / candles)."""


class GrowwBusy(SourceUnavailable):
    """Groww kept rate-limiting us even after backing off. Try again later — never treat as 'no data'."""


def _blocked(name: str):
    def refuse(*_a, **_k):
        raise ReadOnlyViolation(f"NiveshMitra never calls {name} — it is decision-only.")

    return refuse


class RateLimiter:
    """Sliding-window limiter: at most `per_second` calls in any second and `per_minute` in any minute."""

    def __init__(self, per_second: int, per_minute: int):
        self.per_second, self.per_minute = per_second, per_minute
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            while True:
                now = time.monotonic()
                while self.calls and now - self.calls[0] > 60:
                    self.calls.popleft()
                last_second = sum(1 for t in self.calls if now - t < 1)
                if len(self.calls) < self.per_minute and last_second < self.per_second:
                    self.calls.append(now)
                    return
                time.sleep(0.05)


# Groww's published limits, with a safety margin. Historical candles' limit isn't documented; 5/s and 200/min
# breached it in practice (30-Sep-2026), so history is paced well below that and backs off when told to.
LIMITS = {
    "auth": RateLimiter(2, 20),
    "live": RateLimiter(8, 250),
    "history": RateLimiter(2, 100),
    "portfolio": RateLimiter(10, 400),
}
BACKOFF_SECONDS = (3, 6, 12, 24, 48)


@dataclass
class Candle:
    day: date
    open: float | None  # stocks always have one; Groww leaves it empty for some index candles
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class IntradayBar:
    ts: datetime  # bar start, exchange time (IST)
    open: float
    high: float
    low: float
    close: float
    volume: int


class GrowwReadOnlyClient:
    def __init__(self, totp_token: str, totp_secret: str):
        self._totp_token = totp_token
        self._totp_secret = totp_secret
        self.__sdk: GrowwAPI | None = None
        self._token_at: datetime | None = None

    # -- connection -------------------------------------------------------------------------
    def _sdk(self) -> GrowwAPI:
        if self.__sdk is None or self._token_at is None or datetime.now() - self._token_at > TOKEN_LIFETIME:
            self._login()
        return self.__sdk

    @property
    def auth_method(self) -> str:
        """"totp" (no daily approval needed) or "secret" (Groww's API key + secret, approved daily on groww.in)."""
        return "totp" if is_totp_secret(self._totp_secret) else "secret"

    def _login(self) -> None:
        LIMITS["auth"].wait()
        try:
            if self.auth_method == "totp":
                code = pyotp.TOTP(self._totp_secret.replace(" ", "").upper()).now()
                token = GrowwAPI.get_access_token(api_key=self._totp_token, totp=code)
            else:
                token = GrowwAPI.get_access_token(api_key=self._totp_token, secret=self._totp_secret.strip())
        except (gx.GrowwAPIAuthenticationException, gx.GrowwAPIAuthorisationException, gx.GrowwAPIException) as exc:
            hint = (
                "Check the TOTP token and secret in Settings."
                if self.auth_method == "totp"
                else "With an API key + secret, Groww needs you to approve the key each day at groww.in/trade-api/api-keys — "
                "or switch to a TOTP key, which needs no daily approval."
            )
            raise GrowwNotConnected(f"Groww refused the login ({_msg(exc)}). {hint}") from exc
        except Exception as exc:  # network errors, bad secret format
            raise GrowwNotConnected(f"Couldn't log in to Groww: {exc}") from exc
        sdk = GrowwAPI(token)
        for name in BLOCKED_METHODS:
            setattr(sdk, name, _blocked(name))
        self.__sdk, self._token_at = sdk, datetime.now()

    def _call(self, limiter: str, fn_name: str, **kwargs):
        relogged = network = False
        for wait in (*BACKOFF_SECONDS, None):
            LIMITS[limiter].wait()
            try:
                return getattr(self._sdk(), fn_name)(**kwargs)
            except gx.GrowwAPIAuthenticationException:
                if relogged:
                    raise GrowwNotConnected("Groww session expired and re-login failed. Reconnect in Settings.")
                self.__sdk, relogged = None, True  # token expired → log in again once
                continue
            except gx.GrowwAPIRateLimitException:
                pass
            except gx.GrowwAPITimeoutException:
                pass
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                network = True  # a dropped connection (Wi-Fi blip, Groww restarting): wait and try again
            except gx.GrowwAPINotFoundException as exc:
                raise SourceUnavailable(f"Groww has no data for this request ({_msg(exc)})") from exc
            except (gx.GrowwAPIAuthorisationException, gx.BaseGrowwException) as exc:
                text = _msg(exc).lower()
                if "rate limit" not in text:  # Groww reports rate limits as a plain API error
                    if limiter in ("live", "history") and "forbidden" in text:
                        raise GrowwNoDataAccess(
                            "Your Groww API plan doesn't include market data (live prices and price history). "
                            "Groww's free trial excludes it; the paid Trade API plan includes it."
                        ) from exc
                    raise SourceUnavailable(f"Groww error: {_msg(exc)}") from exc
            if wait is None:
                break
            time.sleep(wait)  # rate-limited or timed out: back off, then try again
        if network:
            raise GrowwBusy(f"Couldn't reach Groww for {fn_name} after several tries (network)")
        raise GrowwBusy(f"Groww kept refusing {fn_name} (rate limit) after several retries")

    # -- read-only API ----------------------------------------------------------------------
    def profile(self) -> dict:
        return self._call("portfolio", "get_user_profile")

    def holdings(self) -> list[dict]:
        data = self._call("portfolio", "get_holdings_for_user")
        return data.get("holdings", []) if isinstance(data, dict) else []

    def daily_candles(self, groww_symbol: str, start: date, end: date) -> list[Candle]:
        """Daily candles between two dates (inclusive), from the candle-data feed: current to the latest session, with
        real opens, and already adjusted for splits and bonuses. A stock or index: 'NSE-RELIANCE', 'BSE-SENSEX'."""
        exchange, symbol = split_symbol(groww_symbol)
        out: dict[date, Candle] = {}
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=DAILY_CHUNK_DAYS))
            data = self._call(
                "history",
                "get_historical_candle_data",
                trading_symbol=symbol,
                exchange=exchange,
                segment=GrowwAPI.SEGMENT_CASH,
                start_time=f"{cursor:%Y-%m-%d} 00:00:00",
                end_time=f"{chunk_end:%Y-%m-%d} 23:59:59",
                interval_in_minutes=1440,
            )
            for c in (data or {}).get("candles") or []:
                parsed = parse_candle(c)
                if parsed:
                    out[parsed.day] = parsed
            cursor = chunk_end + timedelta(days=1)
        return [out[d] for d in sorted(out)]

    def recent_intraday_candles(self, groww_symbol: str, start: date, end: date) -> list[IntradayBar]:
        """15-minute bars (09:15 to the 15:15 bar) from the candle-data feed: complete and current, but only for about
        the last 3 months. Its volume column is the day's running total, so it is turned into each bar's own volume."""
        exchange, symbol = split_symbol(groww_symbol)
        out: dict[datetime, IntradayBar] = {}
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=RECENT_INTRADAY_CHUNK_DAYS))
            data = self._call(
                "history",
                "get_historical_candle_data",
                trading_symbol=symbol,
                exchange=exchange,
                segment=GrowwAPI.SEGMENT_CASH,
                start_time=f"{cursor:%Y-%m-%d} 09:15:00",
                end_time=f"{chunk_end:%Y-%m-%d} 15:30:00",
                interval_in_minutes=15,
            )
            for c in (data or {}).get("candles") or []:
                bar = parse_intraday(c)
                if bar:
                    out[bar.ts] = bar
            cursor = chunk_end + timedelta(days=1)
        return per_bar_volume([out[t] for t in sorted(out)])

    def intraday_candles(self, groww_symbol: str, start: date, end: date) -> list[IntradayBar]:
        """15-minute bars back to 2020 from the backtesting feed (88-day chunks; its extra 15:30 closing tick is dropped).
        It runs days behind and its newest sessions can be incomplete — recent_intraday_candles() fills those in."""
        out: dict[datetime, IntradayBar] = {}
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=INTRADAY_CHUNK_DAYS))
            data = self._call(
                "history",
                "get_historical_candles",
                exchange=GrowwAPI.EXCHANGE_NSE,
                segment=GrowwAPI.SEGMENT_CASH,
                groww_symbol=groww_symbol,
                start_time=f"{cursor:%Y-%m-%d} 09:15:00",
                end_time=f"{chunk_end:%Y-%m-%d} 15:30:00",
                candle_interval=GrowwAPI.CANDLE_INTERVAL_MIN_15,
            )
            for c in (data or {}).get("candles") or []:
                bar = parse_intraday(c)
                if bar:
                    out[bar.ts] = bar
            cursor = chunk_end + timedelta(days=1)
        return [out[t] for t in sorted(out)]

    def ltp(self, symbols: list[str]) -> dict[str, float]:
        """Last traded prices, 50 keys per call. Keys are 'NSE_SYMBOL' or 'BSE_SYMBOL' (e.g. BSE_SENSEX)."""
        prices: dict[str, float] = {}
        for i in range(0, len(symbols), 50):
            data = self._call("live", "get_ltp", exchange_trading_symbols=tuple(symbols[i : i + 50]), segment=GrowwAPI.SEGMENT_CASH)
            prices.update({k: float(v) for k, v in (data or {}).items() if v is not None})
        return prices


def is_totp_secret(value: str) -> bool:
    """Authenticator secrets are base32: letters A–Z and digits 2–7 only."""
    v = value.replace(" ", "").upper().rstrip("=")
    return len(v) >= 16 and bool(re.fullmatch(r"[A-Z2-7]+", v))


def split_symbol(groww_symbol: str) -> tuple[str, str]:
    """'NSE-BAJAJ-AUTO' → ('NSE', 'BAJAJ-AUTO'); 'BSE-SENSEX' → ('BSE', 'SENSEX')."""
    exchange, _, symbol = groww_symbol.partition("-")
    return (GrowwAPI.EXCHANGE_BSE if exchange == "BSE" else GrowwAPI.EXCHANGE_NSE), symbol


def per_bar_volume(bars: list[IntradayBar]) -> list[IntradayBar]:
    """Running-total volumes → each bar's own volume, day by day. A day whose numbers aren't a running total is left alone."""
    out: list[IntradayBar] = []
    i = 0
    while i < len(bars):
        j = i
        while j < len(bars) and bars[j].ts.date() == bars[i].ts.date():
            j += 1
        day = bars[i:j]
        totals = [b.volume for b in day]
        if len(day) >= 2 and all(b >= a for a, b in zip(totals, totals[1:])):
            own = [totals[0]] + [b - a for a, b in zip(totals, totals[1:])]
            day = [replace(b, volume=v) for b, v in zip(day, own)]
        out += day
        i = j
    return out


def _exchange_time(ts) -> datetime:
    """Groww timestamps are ISO text in exchange time, or epoch seconds → a naive datetime in exchange time (IST)."""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, IST).replace(tzinfo=None)
    return datetime.fromisoformat(str(ts)[:19])


def parse_candle(c) -> Candle | None:
    """Groww candles are [timestamp, open, high, low, close, volume, open_interest]; timestamp is ISO text or epoch seconds."""
    try:
        day = _exchange_time(c[0]).date()
        h, lo, cl = (float(x) for x in c[2:5])
        o = float(c[1]) if c[1] is not None else None
        vol = int(c[5] or 0)
    except (TypeError, ValueError, IndexError):
        return None
    if min(h, lo, cl) <= 0 or (o is not None and o <= 0):
        return None
    return Candle(day, o, h, lo, cl, vol)


def parse_intraday(c) -> IntradayBar | None:
    """[timestamp, open, high, low, close, volume, oi] → a regular-session bar (09:15 ≤ start ≤ 15:15), else None."""
    try:
        t = _exchange_time(c[0])
        o, h, lo, cl = (float(x) for x in c[1:5])
        vol = int(c[5] or 0)
    except (TypeError, ValueError, IndexError):
        return None
    if min(o, h, lo, cl) <= 0 or not ((9, 15) <= (t.hour, t.minute) <= (15, 15)):
        return None
    return IntradayBar(t, o, h, lo, cl, vol)


def _msg(exc: Exception) -> str:
    return getattr(exc, "msg", None) or str(exc) or type(exc).__name__
