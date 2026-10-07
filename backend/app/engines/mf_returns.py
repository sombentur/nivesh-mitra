"""Point-to-point returns from a NAV series. Rolling returns, risk and scores arrive with the fund engine (step 4)."""

from bisect import bisect_right
from datetime import date

from dateutil.relativedelta import relativedelta

Series = list[tuple[date, float]]
TOLERANCE_DAYS = 7  # a start date may fall on a holiday; accept a NAV up to a week earlier


def nav_on_or_before(series: Series, d: date) -> tuple[date, float] | None:
    i = bisect_right([p[0] for p in series], d)
    return series[i - 1] if i else None


def cagr(start_nav: float, end_nav: float, days: int) -> float:
    years = days / 365.25
    return (end_nav / start_nav) ** (1 / years) - 1 if years >= 1 else end_nav / start_nav - 1


def trailing(series: Series, years: int) -> float | None:
    """Annualised return over the last `years` (absolute return for periods under a year)."""
    if len(series) < 2:
        return None
    end_d, end_nav = series[-1]
    target = end_d - relativedelta(years=years)
    if series[0][0] > target:
        return None  # not enough history
    start = nav_on_or_before(series, target)
    if start is None or (target - start[0]).days > TOLERANCE_DAYS:
        return None
    return cagr(start[1], end_nav, (end_d - start[0]).days)


def since_start(series: Series) -> float | None:
    if len(series) < 2:
        return None
    (d0, n0), (d1, n1) = series[0], series[-1]
    return cagr(n0, n1, (d1 - d0).days)


def summary(series: Series) -> dict:
    return {
        "1y": trailing(series, 1),
        "3y": trailing(series, 3),
        "5y": trailing(series, 5),
        "10y": trailing(series, 10),
        "since_start": since_start(series),
        "history_from": series[0][0].isoformat() if series else None,
    }


def downsample_weekly(series: Series, max_points: int = 700) -> Series:
    """Keep the last NAV of each ISO week once there are too many points for a chart."""
    if len(series) <= max_points:
        return series
    out: dict[tuple[int, int], tuple[date, float]] = {}
    for d, n in series:
        out[d.isocalendar()[:2]] = (d, n)
    return list(out.values())
