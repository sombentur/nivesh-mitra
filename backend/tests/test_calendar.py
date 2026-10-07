from datetime import date, datetime

import pytest

from app.db.base import SessionLocal
from app.db.models import IndexDaily, Instrument, PaperAccount, PaperTrade, Recommendation
from app.engines import holidays
from app.services import app_settings, market, market_calendar
from app.services.stock_data import IST


def test_trading_days_follow_the_holiday_list():
    assert holidays.is_trading_day(date(2026, 10, 1))  # Thursday
    assert not holidays.is_trading_day(date(2026, 10, 2))  # Friday, Mahatma Gandhi Jayanti
    assert not holidays.is_trading_day(date(2026, 10, 3))  # Saturday
    assert holidays.is_trading_day(date(2026, 2, 1))  # Sunday, but a full Budget-day session
    assert not holidays.is_trading_day(date(2026, 11, 8))  # Sunday: Muhurat trading is only a short evening session
    assert holidays.holiday_name(date(2026, 10, 2)) == "Mahatma Gandhi Jayanti"
    assert holidays.holiday_name(date(2026, 8, 15)) == "Independence Day" and holidays.holiday_name(date(2026, 10, 1)) is None
    assert holidays.special_session(date(2026, 11, 8))["name"] == "Diwali Muhurat trading"
    assert holidays.known_until() == date(2026, 12, 31)


def test_next_trading_day_skips_weekends_and_holidays():
    assert holidays.next_trading_day(date(2026, 10, 1)) == date(2026, 10, 5)  # holiday Friday + weekend
    assert holidays.next_trading_day(date(2026, 11, 6)) == date(2026, 11, 9)  # Muhurat Sunday isn't a normal session
    assert holidays.next_trading_day(date(2026, 11, 9)) == date(2026, 11, 11)  # Diwali Balipratipada on the 10th
    assert holidays.next_trading_day(date(2026, 12, 31)) == date(2027, 1, 1)  # beyond the list: plain weekdays


def _ist(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_market_state_and_open_hours():
    assert market_calendar.market_state(_ist(2026, 10, 1, 8)) == {"state": "pre", "next_open": "2026-10-01"}
    assert market_calendar.market_state(_ist(2026, 10, 1, 10))["state"] == "open"
    assert market_calendar.market_state(_ist(2026, 10, 1, 16)) == {"state": "closed", "next_open": "2026-10-05"}
    assert market_calendar.market_state(_ist(2026, 10, 2, 10)) == {"state": "closed", "next_open": "2026-10-05"}  # holiday
    assert market.market_open(_ist(2026, 10, 1, 10)) and not market.market_open(_ist(2026, 10, 2, 10))


def _index(db, symbol, closes: dict[date, float]):
    db.add_all(IndexDaily(symbol=symbol, date=d, open=c, high=c, low=c, close=c) for d, c in closes.items())


@pytest.fixture
def week(monkeypatch):
    monkeypatch.setattr(market_calendar, "now_ist", lambda: _ist(2026, 10, 3, 12))  # Saturday noon
    with SessionLocal() as db:
        # Sunday 27 Sep traded (a special session); Tuesday 29 Sep didn't (an unlisted holiday)
        _index(db, "NIFTY", {date(2026, 9, 25): 23140.5, date(2026, 9, 27): 23000.0, date(2026, 9, 28): 22770.0, date(2026, 9, 30): 22620.45, date(2026, 10, 1): 22421.95})
        _index(db, "SENSEX", {date(2026, 9, 30): 72480.29, date(2026, 10, 1): 71909.7})
        inst = Instrument(symbol="X", groww_symbol="NSE-X")
        acct = PaperAccount(start_capital=10000)
        db.add_all([inst, acct])
        db.flush()
        for pnl in (120.0, -45.5):
            db.add(PaperTrade(account_id=acct.id, instrument_id=inst.id, status="closed", qty=1, entry_low=1, entry_high=1, stop=0.9, target=2, max_hold_days=10,
                              for_session=date(2026, 9, 28), entry_date=date(2026, 9, 28), entry_price=1, exit_date=date(2026, 9, 30), exit_price=1.1, exit_reason="target", net_pnl=pnl, r_multiple=1.0))
        db.add(Recommendation(engine="swing", action="buy", for_session=date(2026, 10, 5), instrument_id=inst.id))
        app_settings.set_setting(db, "paper_mode_start", "2026-08-10")  # practice ends 60 days later: 9 Oct
        db.commit()
    yield


def test_calendar_days(week, signed_in):
    r = signed_in.get("/api/calendar", params={"start": "2026-09-26", "end": "2026-10-09"})
    assert r.status_code == 200
    c = r.json()
    assert c["today"] == "2026-10-03" and c["latest_session"] == "2026-10-01"
    assert c["market"] == {"state": "closed", "next_open": "2026-10-05"} and c["holidays_known_until"] == "2026-12-31"
    day = {d["date"]: d for d in c["days"]}
    assert len(day) == 14
    assert day["2026-09-26"]["status"] == "weekend" and day["2026-09-26"]["nifty"] is None
    assert day["2026-09-27"]["status"] == "special" and day["2026-09-27"]["name"] == "Special trading session"  # a Sunday that traded
    assert day["2026-09-28"]["status"] == "trading" and day["2026-09-28"]["nifty"] == {"close": 22770.0, "change_pct": -0.01}
    assert day["2026-09-29"]["status"] == "holiday" and day["2026-09-29"]["name"] == "Market holiday"  # a weekday with no trading
    assert day["2026-09-30"]["pnl"] == 74.5 and day["2026-09-30"]["closed_trades"] == 2 and day["2026-09-30"]["sensex"] is None  # no earlier Sensex close
    assert day["2026-10-01"]["nifty"]["change_pct"] == pytest.approx(-0.0088, abs=1e-4) and day["2026-10-01"]["sensex"]["change_pct"] == pytest.approx(-0.0079, abs=1e-4)
    assert day["2026-10-02"]["status"] == "holiday" and day["2026-10-02"]["name"] == "Mahatma Gandhi Jayanti"  # from the list
    assert day["2026-10-03"]["status"] == "weekend"
    assert day["2026-10-05"]["status"] == "trading" and day["2026-10-05"]["nifty"] is None and day["2026-10-05"]["ideas"] == 1
    assert day["2026-10-09"]["events"] == ["Practice period ends: your practice report is ready"]


def test_calendar_shows_muhurat_and_named_weekend_festivals(week, signed_in):
    day = {d["date"]: d for d in signed_in.get("/api/calendar", params={"start": "2026-11-07", "end": "2026-11-10"}).json()["days"]}
    assert day["2026-11-08"]["status"] == "special" and day["2026-11-08"]["name"] == "Diwali Muhurat trading" and "evening" in day["2026-11-08"]["note"]
    assert day["2026-11-10"]["status"] == "holiday" and day["2026-11-10"]["name"] == "Diwali Balipratipada"
    assert day["2026-11-07"]["status"] == "weekend" and day["2026-11-09"]["status"] == "trading"


def test_calendar_needs_login_and_a_sane_range(client, signed_in):
    assert signed_in.get("/api/calendar", params={"start": "2026-10-01", "end": "2026-12-31"}).status_code == 400
    assert signed_in.get("/api/calendar", params={"start": "2026-10-05", "end": "2026-10-01"}).status_code == 400
    assert signed_in.get("/api/calendar").status_code == 422
