"""AMFI — Total Expense Ratio (TER) of every scheme, Direct and Regular, published monthly with daily rows.

Verified 30-Sep-2026: GET /api/populate-te-rdata-revised?MF_ID=All&Month=MM-YYYY&strCat=-1&strType=-1&excel=true returns one
XLSX (~4 MB). Rows are per scheme per day; Direct and Regular are columns. There is no AMFI scheme code, only the
scheme-level name, which is matched to AMFI's scheme master by normalised name.

The layout changed in April 2026 (new SEBI regulations), so columns are found by their headings, not positions.
Parsed with the standard library (the sheet uses inline strings).
"""

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta

from app.connectors.http import SourceUnavailable, get_bytes

TER_URL = "https://www.amfiindia.com/api/populate-te-rdata-revised"
EXCEL_EPOCH = date(1899, 12, 30)


@dataclass
class TerRow:
    scheme_name: str
    category: str
    ter_date: date
    regular_ter: float | None  # fraction: 0.0219 = 2.19% a year (the fund's full cost, as AMFI totals it)
    direct_ter: float | None
    regular_fee: float | None = None  # the fund house's own fee ("base expense ratio"); the rest is brokerage, taxes, levies
    direct_fee: float | None = None


def normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _cells(row_xml: str) -> dict[str, str]:
    out = {}
    for col, inner in re.findall(r'<c r="([A-Z]+)\d+"[^>]*>(.*?)</c>', row_xml, re.S):
        t = re.search(r"<t[^>]*>(.*?)</t>", inner, re.S)
        v = re.search(r"<v>(.*?)</v>", inner, re.S)
        out[col] = (t.group(1) if t else v.group(1) if v else "").replace("&amp;", "&").strip()
    return out


def _pct(s: str) -> float | None:
    try:
        v = float(s)
    except ValueError:
        return None
    return v / 100 if v > 0 else None


def parse_ter_xlsx(data: bytes) -> list[TerRow]:
    try:
        sheet = zipfile.ZipFile(io.BytesIO(data)).read("xl/worksheets/sheet1.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise SourceUnavailable("AMFI's TER file isn't a readable spreadsheet") from exc
    rows = re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S)
    if not rows:
        raise SourceUnavailable("AMFI's TER file is empty")
    header = _cells(rows[0])

    def find(*needles: str) -> str | None:
        return next((c for c, h in header.items() if all(n in h.lower() for n in needles)), None)

    col = {
        "name": find("scheme name"),
        "category": find("scheme category"),
        "date": find("ter date"),
        "regular": find("regular", "total"),
        "direct": find("direct", "total"),
    }
    fee = {"regular": find("regular", "base"), "direct": find("direct", "base")}  # optional: older files may lack it
    if not all(col.values()):
        raise SourceUnavailable(f"AMFI TER file format changed (columns found: {col})")
    out = []
    for r in rows[1:]:
        c = _cells(r)
        try:
            d = EXCEL_EPOCH + timedelta(days=int(float(c.get(col["date"], ""))))
        except ValueError:
            continue  # disclaimer rows at the end
        out.append(
            TerRow(
                c.get(col["name"], ""),
                c.get(col["category"], ""),
                d,
                _pct(c.get(col["regular"], "")),
                _pct(c.get(col["direct"], "")),
                _pct(c.get(fee["regular"], "")) if fee["regular"] else None,
                _pct(c.get(fee["direct"], "")) if fee["direct"] else None,
            )
        )
    return out


def latest_per_scheme(rows: list[TerRow]) -> dict[str, TerRow]:
    """Newest row for each scheme (keyed by normalised name)."""
    out: dict[str, TerRow] = {}
    for r in rows:
        k = normalise_name(r.scheme_name)
        if k and (k not in out or r.ter_date > out[k].ter_date):
            out[k] = r
    return out


def fetch_month(month: date) -> list[TerRow]:
    params = {"MF_ID": "All", "Month": f"{month:%m-%Y}", "strCat": "-1", "strType": "-1", "excel": "true"}
    return parse_ter_xlsx(get_bytes(TER_URL, params=params, timeout=180))
