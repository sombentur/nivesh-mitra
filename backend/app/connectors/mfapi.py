"""mfapi.in — free NAV history built on AMFI data. Used once per fund to download its full history."""

from datetime import date, datetime

from app.connectors.http import SourceUnavailable, get_json

BASE = "https://api.mfapi.in/mf"


def parse_history(payload: dict) -> list[tuple[date, float]]:
    if payload.get("status") != "SUCCESS" or "data" not in payload:
        raise SourceUnavailable("mfapi.in returned no data for this scheme")
    out = []
    for p in payload["data"]:
        try:
            nav = float(p["nav"])
            d = datetime.strptime(p["date"], "%d-%m-%Y").date()
        except (KeyError, ValueError):
            continue
        if nav > 0:
            out.append((d, nav))
    out.sort()
    return out


def fetch_history(scheme_code: int, start: date | None = None) -> list[tuple[date, float]]:
    params = {"startDate": start.isoformat(), "endDate": date.today().isoformat()} if start else None
    payload = get_json(f"{BASE}/{scheme_code}", params=params, timeout=60)
    if not isinstance(payload, dict):
        raise SourceUnavailable("mfapi.in returned an unexpected response")
    return parse_history(payload)
