from datetime import date, timedelta

import pytest

from app.connectors import amfi, mfapi
from app.connectors.http import SourceUnavailable
from app.db.base import SessionLocal
from app.db.models import MfScheme, NavDaily
from app.services import mf_data
from tests import mf_fixtures as fx


@pytest.fixture
def sources(monkeypatch):
    """Fake AMFI + mfapi.in. Tests change `state` to simulate new days and outages."""
    state = {"nav_all": fx.nav_all(), "history_calls": [], "mfapi_calls": [], "history_fail": False, "mfapi_fail": set()}

    def history(start, end):
        state["history_calls"].append((start, end))
        if state["history_fail"]:
            raise SourceUnavailable("AMFI down")
        entries, d = [], start
        while d <= end:
            if d.weekday() < 5:
                entries.append((122639, d.strftime("%d-%b-%Y"), 90.0))
            d += timedelta(days=1)
        return amfi.parse_nav_history(fx.nav_history(entries))

    def mf_history(code, start=None):
        state["mfapi_calls"].append((code, start))
        if code in state["mfapi_fail"]:
            raise SourceUnavailable("mfapi down")
        first, last = start or date(2016, 1, 1), date(2026, 9, 29)
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        return [(d, 10.0 + i * 0.01) for i, d in enumerate(days) if d.weekday() < 5]

    monkeypatch.setattr(amfi, "fetch_scheme_master", lambda: amfi.parse_scheme_master(fx.MASTER))
    monkeypatch.setattr(amfi, "fetch_nav_all", lambda: amfi.parse_nav_all(state["nav_all"]))
    monkeypatch.setattr(amfi, "fetch_nav_history", history)
    monkeypatch.setattr(mfapi, "fetch_history", mf_history)
    monkeypatch.setattr(mf_data, "MFAPI_PAUSE_SECONDS", 0)
    return state


def _full_sync(db):
    mf_data.sync_scheme_master(db)
    mf_data.update_daily_navs(db)
    mf_data.backfill_history(db)


def test_first_sync_classifies_and_tracks_direct_growth_only(sources):
    with SessionLocal() as db:
        mf_data.sync_scheme_master(db)
        summary = mf_data.update_daily_navs(db)
        assert "29 Sep 2026" in summary
        s = {x.scheme_code: x for x in db.query(MfScheme).all()}
        assert s[122639].tracked and s[122639].category == "Flexi Cap Fund" and s[122639].launch_date == date(2013, 5, 24)
        assert s[122639].display_name == "Parag Parikh Flexi Cap Fund - Direct Plan - Growth"
        assert not s[122640].tracked  # regular plan
        assert not s[120504].tracked  # IDCW option
        assert s[120716].plan == "direct" and s[120716].tracked  # plan column empty → read from the master's full name
        assert not s[130947].is_active and not s[130947].tracked  # stale NAV from 2020
        assert not s[140001].tracked  # closed-ended
        assert s[148001].category == "Index Fund – Debt"
        assert s[122639].twin_scheme_code == 122640 and s[122640].twin_scheme_code == 122639


def test_backfill_downloads_history_once(sources):
    with SessionLocal() as db:
        _full_sync(db)
        counts = mf_data.history_counts(db)
        assert counts == {"tracked": 4, "synced": 4, "failed": 0}
        assert db.query(NavDaily).filter_by(scheme_code=122639).count() > 500
        calls = len(sources["mfapi_calls"])
        mf_data.backfill_history(db)
        assert len(sources["mfapi_calls"]) == calls  # nothing pending → no new downloads


def test_backfill_failure_is_recorded_and_retried(sources):
    sources["mfapi_fail"].add(122639)
    with SessionLocal() as db:
        _full_sync(db)
        s = db.get(MfScheme, 122639)
        assert s.history_synced_at is None and "mfapi down" in s.history_error
        assert mf_data.history_counts(db)["failed"] == 1
        sources["mfapi_fail"].clear()
        mf_data.backfill_history(db)
        db.refresh(s)
        assert s.history_synced_at is not None and s.history_error is None


def test_next_day_appends_nav(sources):
    with SessionLocal() as db:
        _full_sync(db)
        sources["nav_all"] = fx.nav_all(d="30-Sep-2026", ppfas_d="91.0000")
        mf_data.update_daily_navs(db)
        row = db.get(NavDaily, {"scheme_code": 122639, "date": date(2026, 9, 30)})
        assert row.nav == 91.0
        assert db.get(MfScheme, 122639).history_end == date(2026, 9, 30)
        assert sources["history_calls"] == []  # no gap, no history download


def test_missed_days_are_filled_from_amfi_history(sources):
    with SessionLocal() as db:
        _full_sync(db)
        sources["nav_all"] = fx.nav_all(d="09-Oct-2026")  # PC was off for ~10 days
        summary = mf_data.update_daily_navs(db)
        assert "filled missed days" in summary
        assert sources["history_calls"] == [(date(2026, 9, 30), date(2026, 10, 9))]
        assert db.get(NavDaily, {"scheme_code": 122639, "date": date(2026, 10, 5)}) is not None
        assert db.get(MfScheme, 122639).history_end == date(2026, 10, 9)


def test_gap_fill_outage_requeues_without_losing_the_gap(sources):
    with SessionLocal() as db:
        _full_sync(db)
        sources["nav_all"] = fx.nav_all(d="09-Oct-2026")
        sources["history_fail"] = True
        summary = mf_data.update_daily_navs(db)
        assert "queued for re-download" in summary
        s = db.get(MfScheme, 122639)
        assert s.history_synced_at is None and s.history_end == date(2026, 9, 29)  # gap start kept
        sources["mfapi_calls"].clear()
        mf_data.backfill_history(db)
        assert (122639, date(2026, 9, 30)) in sources["mfapi_calls"]  # re-fetched from the day after


def test_very_long_gap_goes_back_to_mfapi(sources):
    with SessionLocal() as db:
        _full_sync(db)
        sources["nav_all"] = fx.nav_all(d="30-Mar-2027")
        summary = mf_data.update_daily_navs(db)
        assert "gap of" in summary and sources["history_calls"] == []
        assert db.get(MfScheme, 122639).history_synced_at is None


def test_source_outage_raises_and_marks_unhealthy(sources, monkeypatch):
    monkeypatch.setattr(amfi, "fetch_nav_all", lambda: (_ for _ in ()).throw(SourceUnavailable("offline")))
    with SessionLocal() as db:
        with pytest.raises(SourceUnavailable):
            mf_data.update_daily_navs(db)
        from app.db.models import DataSourceStatus

        st = db.get(DataSourceStatus, mf_data.SOURCE_NAV)
        assert st.healthy is False and "offline" in st.last_error
