"""Normalise AMFI's scheme descriptions: category, plan (direct/regular), option (growth/IDCW), Direct↔Regular twins.

Pure functions driven by rules/mf_categories.yaml.
"""

import re
from dataclasses import dataclass

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'"})


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.translate(_APOSTROPHES)).strip()


@dataclass(frozen=True)
class Category:
    asset_class: str
    category: str


def categorise(raw: str, fund_name: str, scheme_type: str, rules: dict) -> Category:
    raw = _clean(raw)
    if scheme_type and scheme_type != rules["open_ended_type"]:
        return Category("Closed/Interval", raw or "Closed-ended")
    pair = rules["pairs"].get(raw)
    if pair is None:
        pair = next((v for k, v in rules["pairs"].items() if _clean(k) == raw), None)
    if pair:
        cat = Category(pair["asset_class"], pair["category"])
        if raw == "Other Scheme - Index Funds" and re.search(rules["debt_index_name_pattern"], fund_name):
            cat = Category("Index", "Index Fund – Debt")
        return cat
    if " - " not in raw:
        return Category("Legacy", raw or "Unknown")
    group, name = (p.strip() for p in raw.split(" - ", 1))
    asset_class = rules["groups"].get(group, "Other")
    return Category(asset_class, rules["names"].get(name, name))


def plan_of(plan_raw: str, *names: str) -> str:
    p = plan_raw.lower()
    if "direct" in p:
        return "direct"
    if "regular" in p:
        return "regular"
    for n in names:
        n = (n or "").lower()
        if re.search(r"\bdirect\b|\bdir\b", n):
            return "direct"
        if re.search(r"\bregular\b|\breg\b", n):
            return "regular"
    return "unknown"


def option_of(option_raw: str, *names: str) -> tuple[str, str]:
    """Returns (option, detail) — e.g. ("idcw", "Monthly IDCW")."""
    for text in (option_raw, *names):
        t = (text or "").lower()
        if not t:
            continue
        if re.search(r"idcw|dividend|income distribution|payout|reinvest", t):
            return "idcw", _clean(option_raw) or "IDCW"
        if "bonus" in t:
            return "bonus", "Bonus"
        if "growth" in t:
            return "growth", "Growth"
    return "unknown", _clean(option_raw)


_PLAN_WORDS = re.compile(
    r"\b(direct|regular|plan|option|growth|idcw|dividend|payout|reinvestment|reinvest|dir|reg|gr|opt)\b", re.I
)


def variant_key(amc: str, name: str) -> str:
    """Same fund + same variant, ignoring the plan/option words: links a Direct plan to its Regular twin."""
    base = _PLAN_WORDS.sub(" ", _clean(name).lower())
    base = re.sub(r"[^a-z0-9']+", " ", base)
    return f"{_clean(amc).lower()}|{re.sub(r'\s+', ' ', base).strip()}"


def display_name(nav_name: str | None, fund_name: str, plan: str, option_detail: str) -> str:
    if nav_name:
        return _clean(nav_name)
    parts = [fund_name]
    if plan in ("direct", "regular"):
        parts.append(f"{plan.title()} Plan")
    if option_detail:
        parts.append(option_detail)
    return " - ".join(parts)
