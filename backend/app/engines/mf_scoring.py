"""Category scores (doc 03 §C3–C4): percentile rank within peers, weighted, with plain-language reasons.

Pure functions: metrics in, scores out.
"""

import math
import re
from dataclasses import dataclass, field

ABS_IN_TEXT = {"maxdd_5y", "tracking_diff_1y", "tracking_diff_3y"}


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def percentiles(values: dict[int, float | None], higher_is_better: bool) -> dict[int, float]:
    """0 = worst peer, 100 = best peer; ties share the average position."""
    vals = {k: v for k, v in values.items() if _ok(v)}
    n = len(vals)
    if n == 0:
        return {}
    if n == 1:
        return {k: 50.0 for k in vals}
    out = {}
    for k, v in vals.items():
        worse = sum(1 for o in vals.values() if (o < v if higher_is_better else o > v))
        ties = sum(1 for o in vals.values() if o == v) - 1
        out[k] = 100.0 * (worse + 0.5 * ties) / (n - 1)
    return out


@dataclass
class Scored:
    scheme_code: int
    total: float | None
    rank: int | None
    peers: int
    coverage: float
    confidence: str  # high | medium | low | unranked
    components: dict[str, dict] = field(default_factory=dict)
    reasons_for: list[str] = field(default_factory=list)
    reasons_against: list[str] = field(default_factory=list)
    unranked_reason: str | None = None


def _reason(rules: dict, metric: str, side: str, value: float, pct: float, ctx: dict) -> str | None:
    tpl = rules["reasons"].get(metric, {}).get(side)
    if not tpl:
        return None
    v = abs(value) if metric in ABS_IN_TEXT else value
    cat = re.sub(r"\s+Fund$", "", ctx.get("category", "peer"))  # "Short Duration Fund funds" → "Short Duration funds"
    return tpl.format(v=v, p=pct, cat=cat, bench=ctx.get("bench_label") or "index")


def score_group(funds: dict[int, dict], model: str, rules: dict, ctx: dict, not_applicable: frozenset[str] = frozenset()) -> dict[int, Scored]:
    """Score every fund in one peer group. `funds` maps scheme_code → metrics dict.

    `not_applicable` metrics (e.g. "beat the index" where the category has no index stand-in) are left out entirely,
    so they don't count as missing data and don't lower confidence.
    """
    weights: dict[str, float] = {k: v for k, v in rules["models"][model].items() if k not in not_applicable}
    total_w = sum(weights.values())
    lower = set(rules["lower_is_better"])
    conf = rules["confidence"]
    min_years = rules["min_history_years"]

    eligible = {c: m for c, m in funds.items() if (m.get("history_years") or 0) >= min_years}
    out: dict[int, Scored] = {}
    for c, m in funds.items():
        if c not in eligible:
            out[c] = Scored(c, None, None, len(eligible), 0.0, "unranked", unranked_reason=f"Less than {min_years} years of history")
    if len(eligible) < rules["min_category_size"]:
        for c in eligible:
            out[c] = Scored(c, None, None, len(eligible), 0.0, "unranked", unranked_reason=f"Only {len(eligible)} comparable funds — too few to rank")
        return out

    pct = {metric: percentiles({c: m.get(metric) for c, m in eligible.items()}, metric not in lower) for metric in weights}
    ranked: list[Scored] = []
    for c, m in eligible.items():
        comps, got, pts = {}, 0.0, 0.0
        for metric, w in weights.items():
            if c in pct[metric]:
                p = pct[metric][c]
                comps[metric] = {"value": m[metric], "percentile": round(p, 1), "weight": w}
                got += w
                pts += w * p / 100
        coverage = got / total_w
        if coverage < conf["unscored_below"]:
            out[c] = Scored(c, None, None, len(eligible), round(coverage, 2), "unranked", comps, unranked_reason="Not enough data to rank")
            continue
        total = 100 * pts / got
        if coverage >= conf["high_coverage"] and m["history_years"] >= conf["high_min_history_years"] and len(eligible) >= conf["high_min_peers"]:
            confidence = "high"
        elif coverage >= conf["medium_coverage"]:
            confidence = "medium"
        else:
            confidence = "low"
        impact = sorted(comps.items(), key=lambda kv: (kv[1]["percentile"] - 50) * kv[1]["weight"], reverse=True)
        pros = [_reason(rules, k, "for", v["value"], v["percentile"], ctx) for k, v in impact if v["percentile"] >= 60][:3]
        cons = [_reason(rules, k, "against", v["value"], v["percentile"], ctx) for k, v in reversed(impact) if v["percentile"] <= 40][:3]
        s = Scored(c, round(total, 1), None, len(eligible), round(coverage, 2), confidence, comps, [p for p in pros if p], [x for x in cons if x])
        out[c] = s
        ranked.append(s)
    for i, s in enumerate(sorted(ranked, key=lambda x: x.total, reverse=True), start=1):
        s.rank = i
    return out


def model_for(asset_class: str, category: str, rules: dict) -> str | None:
    return rules["category_models"].get(category) or rules["asset_class_models"].get(asset_class)


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", name.lower().replace("nifty50", "nifty 50"))).strip()


def index_group(name: str, rules: dict) -> dict | None:
    n = _norm(name)
    return next((g for g in rules["index_groups"] if re.search(g["pattern"], n)), None)
