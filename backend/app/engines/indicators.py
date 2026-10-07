"""Technical indicators on daily bars (a DataFrame with open, high, low, close, volume, indexed by date).

Standard definitions (Wilder smoothing for RSI and ATR), written out so every number can be checked by hand.
"""

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    return line, ema(line, signal)


def add_indicators(df: pd.DataFrame, touch_days: int = 3, breakout_days: int = 20, swing_days: int = 5) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["sma20"], out["sma50"], out["sma200"] = sma(c, 20), sma(c, 50), sma(c, 200)
    out["rsi14"] = rsi(c, 14)
    out["atr14"] = atr(out, 14)
    out["macd"], out["macd_signal"] = macd(c)
    out["vol20_prev"] = out["volume"].shift(1).rolling(20, min_periods=20).mean()
    out["high_prev_n"] = out["high"].shift(1).rolling(breakout_days, min_periods=breakout_days).max()
    out["low_swing"] = out["low"].rolling(swing_days, min_periods=swing_days).min()
    out["low_to_sma20_min"] = (out["low"] / out["sma20"]).rolling(touch_days, min_periods=1).min()
    rng = (out["high"] - out["low"]).replace(0, np.nan)
    out["close_in_range"] = (c - out["low"]) / rng
    # "Green day": closed above its open — or, where the open is missing, above yesterday's close
    out["green"] = np.where(out["open"].notna(), c > out["open"], c > c.shift(1))
    return out
