"""AMFI (amfiindia.com) — official daily NAVs, scheme master and NAV history report.

Formats verified on 30-Sep-2026:
- NAVAll.txt: 8 columns since 19-Aug-2026, ';'-separated, with section headers like
  "Open Ended Schemes(Equity Schemes - Flexi Cap Fund)" followed by an AMC name line.
- Scheme master CSV: 10 columns; the two ISINs are joined without a separator in the last column.
- NAV history report: same idea as NAVAll, columns reordered, headers like "Open Ended Schemes ( Money Market )".
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

from app.connectors.http import SourceUnavailable, get_text

NAV_ALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
SCHEME_MASTER_URL = "https://portal.amfiindia.com/DownloadSchemeData_Po.aspx"
NAV_HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"

_HEADER_RE = re.compile(r"^(?P<type>(Open Ended|Close Ended|Interval Fund) Schemes?)\s*\(\s*(?P<cat>.*?)\s*\)\s*$")


@dataclass
class NavRow:
    scheme_code: int
    isin_growth: str | None
    isin_reinvest: str | None
    fund_name: str
    plan_raw: str
    option_raw: str
    nav: float | None
    nav_date: date
    scheme_type: str
    raw_category: str


@dataclass
class MasterRow:
    scheme_code: int
    amc: str
    fund_name: str
    scheme_type: str
    raw_category: str
    nav_name: str
    launch_date: date | None
    isin_growth: str | None
    isin_reinvest: str | None


def _date(s: str) -> date | None:
    s = s.strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _isin(s: str) -> str | None:
    s = s.strip()
    return s if re.fullmatch(r"IN[A-Z0-9]{10}", s) else None


def _nav(s: str) -> float | None:
    try:
        v = float(s.strip())
    except ValueError:
        return None
    return v if v > 0 else None


def _parse_sections(text: str, columns: dict[str, int]) -> list[NavRow]:
    rows: list[NavRow] = []
    scheme_type, raw_category = "", ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Scheme Code"):
            continue
        parts = line.split(";")
        if len(parts) == 8 and parts[0].strip().isdigit():
            d = _date(parts[columns["date"]])
            if d is None:
                continue
            rows.append(
                NavRow(
                    scheme_code=int(parts[0]),
                    isin_growth=_isin(parts[columns["isin1"]]),
                    isin_reinvest=_isin(parts[columns["isin2"]]),
                    fund_name=parts[columns["name"]].strip(),
                    plan_raw=parts[columns["plan"]].strip(),
                    option_raw=parts[columns["option"]].strip(),
                    nav=_nav(parts[columns["nav"]]),
                    nav_date=d,
                    scheme_type=scheme_type,
                    raw_category=raw_category,
                )
            )
            continue
        m = _HEADER_RE.match(line)
        if m:
            scheme_type = "Open Ended Schemes" if m["type"].startswith("Open") else m["type"]
            raw_category = m["cat"]
        # anything else is an AMC name line — the AMC comes from the scheme master
    return rows


def parse_nav_all(text: str) -> list[NavRow]:
    header = text.lstrip("﻿").splitlines()[0] if text else ""
    if not header.startswith("Scheme Code;ISIN") or header.count(";") != 7:
        raise SourceUnavailable("AMFI NAVAll.txt format changed — NiveshMitra needs an update to read it")
    return _parse_sections(text, dict(isin1=1, isin2=2, name=3, plan=4, option=5, nav=6, date=7))


def parse_nav_history(text: str) -> list[NavRow]:
    header = text.lstrip("﻿").splitlines()[0] if text else ""
    if not header.startswith("Scheme Code;NAV Name;Plan;Option"):
        raise SourceUnavailable("AMFI NAV history format changed — NiveshMitra needs an update to read it")
    return _parse_sections(text, dict(name=1, plan=2, option=3, isin1=4, isin2=5, nav=6, date=7))


def parse_scheme_master(text: str) -> list[MasterRow]:
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(reader, None)
    if not header or header[0].strip() != "AMC" or len(header) != 10:
        raise SourceUnavailable("AMFI scheme master format changed — NiveshMitra needs an update to read it")
    out = []
    for r in reader:
        if len(r) != 10 or not r[1].strip().isdigit():
            continue
        isins = re.findall(r"IN[A-Z0-9]{10}", r[9])
        out.append(
            MasterRow(
                scheme_code=int(r[1]),
                amc=r[0].strip(),
                fund_name=r[2].strip(),
                scheme_type=r[3].strip(),
                raw_category=r[4].strip(),
                nav_name=r[5].strip(),
                launch_date=_date(r[7]),
                isin_growth=isins[0] if isins else None,
                isin_reinvest=isins[1] if len(isins) > 1 else None,
            )
        )
    return out


def fetch_nav_all() -> list[NavRow]:
    return parse_nav_all(get_text(NAV_ALL_URL))


def fetch_scheme_master() -> list[MasterRow]:
    return parse_scheme_master(get_text(SCHEME_MASTER_URL, params={"mf": "0"}, timeout=120))


def fetch_nav_history(start: date, end: date) -> list[NavRow]:
    """All schemes' NAVs between two dates (keep ranges short — the file is large)."""
    params = {"frmdt": start.strftime("%d-%b-%Y"), "todt": end.strftime("%d-%b-%Y")}
    return parse_nav_history(get_text(NAV_HISTORY_URL, params=params, timeout=180))
