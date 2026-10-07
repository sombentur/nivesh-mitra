"""Split and bonus detection for price series that are NOT adjusted — today, the 15-minute bars.

Daily candles come from Groww's candle-data feed already adjusted, so they never pass through here. The 15-minute history
(Groww's backtesting feed) is raw: Reliance's 1:1 bonus shows as a 50% overnight "crash" on 28-Oct-2024. The intraday
engine uses detect() on per-session opens and closes built from those bars to skip ex-dates.

How: an overnight fall of more than 28% from yesterday's close to today's OPEN whose size matches a common Indian
split/bonus ratio (1:1 bonus = ÷2, 1:2 bonus = ÷1.5, split 10→1 = ÷10 …) within ±12%. Using the open matters: a real
crash usually opens only part of the way down (PB Fintech fell 36% on 24-Sep-2026 but opened far higher), while a split
opens exactly at the ratio. A fall of 40%+ that matches no ratio (a demerger) is treated as an event too.

Not caught: small bonuses (1:3, 1:4 → 25%/20% drops) that look like ordinary bad days.
"""

import math

import pandas as pd

FACTORS = (1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 10.0, 20.0, 25.0, 50.0, 100.0)
CANDIDATE_BELOW = 0.72  # day-over-day price ratio that makes us look closer
MATCH_WITHIN = math.log(1.12)  # after dividing by the factor, the day's move must be within ±12%
UNMATCHED_BELOW = 0.60  # a 40%+ drop at the open matching no ratio: demerger or capital reduction


def detect(bars: pd.DataFrame) -> list[tuple[pd.Timestamp, float]]:
    """(ex-date, factor) for each split/bonus-like event. Uses the open where Groww has it (closest to the pure ratio)."""
    prev = bars["close"].shift(1)
    ratio_open = bars["open"] / prev
    ratio = ratio_open.where(bars["open"].notna(), bars["close"] / prev)
    events = []
    for day, g in ratio[ratio < CANDIDATE_BELOW].items():
        if not g or g <= 0 or pd.isna(g):
            continue
        k = min(FACTORS, key=lambda f: abs(math.log(g * f)))
        if abs(math.log(g * k)) <= MATCH_WITHIN:
            events.append((day, k))
        elif g < UNMATCHED_BELOW:
            events.append((day, 1 / g))
    return events
