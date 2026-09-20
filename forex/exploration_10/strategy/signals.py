"""Causal decision-bar features for low-volatility false-breakout reversion."""
from __future__ import annotations

import numpy as np
import pandas as pd


OHLC = ["open", "high", "low", "close"]


def timeframe_minutes(timeframe: str) -> int:
    """Return an integer minute duration, rejecting non-fixed/non-minute bars."""
    delta = pd.Timedelta(timeframe)
    minute = pd.Timedelta(minutes=1)
    if delta <= pd.Timedelta(0) or delta % minute:
        raise ValueError(f"timeframe must be a positive whole number of minutes: {timeframe}")
    return int(delta / minute)


def build_decision_bars(
    minute_bars: pd.DataFrame,
    timeframe: str,
    require_complete: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate UTC minute bars and return valid bars plus all bucket diagnostics."""
    missing = set(OHLC) - set(minute_bars.columns)
    if missing:
        raise ValueError(f"missing OHLC columns: {sorted(missing)}")
    if not isinstance(minute_bars.index, pd.DatetimeIndex):
        raise TypeError("minute_bars must have a DatetimeIndex")
    if minute_bars.index.has_duplicates or not minute_bars.index.is_monotonic_increasing:
        raise ValueError("minute timestamps must be unique and sorted")

    minutes = timeframe_minutes(timeframe)
    rule = f"{minutes}min"
    grouped = minute_bars.resample(rule, label="left", closed="left")
    bars = grouped.agg(open=("open", "first"), high=("high", "max"),
                       low=("low", "min"), close=("close", "last"),
                       minute_count=("close", "count"))
    bars = bars[bars["minute_count"] > 0].copy()
    bars["complete"] = bars["minute_count"].eq(minutes)
    diagnostics = bars[["minute_count", "complete"]].copy()
    if require_complete:
        bars = bars[bars["complete"]].copy()
    return bars, diagnostics


def wilder_atr(bars: pd.DataFrame, period: int) -> pd.Series:
    """Textbook Wilder ATR seeded by the first period-length simple mean."""
    if period < 1:
        raise ValueError("atr_period must be >= 1")
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [bars["high"] - bars["low"],
         (bars["high"] - prev_close).abs(),
         (bars["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    values = tr.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) >= period:
        out[period - 1] = np.mean(values[:period])
        for i in range(period, len(values)):
            out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return pd.Series(out, index=bars.index, name="atr")


def build_signals(
    bars: pd.DataFrame,
    timeframe: str,
    atr_period: int = 14,
    atr_percentile: float = 0.15,
    percentile_lookback: int = 100,
    breakout_lookback: int = 10,
) -> pd.DataFrame:
    """Add causal features and a contrarian signal (-1 sell, +1 buy)."""
    if not 0.0 <= atr_percentile <= 1.0:
        raise ValueError("atr_percentile must be in [0, 1]")
    if percentile_lookback < 1 or breakout_lookback < 1:
        raise ValueError("lookbacks must be >= 1")
    result = bars.copy()
    result["atr"] = wilder_atr(result, atr_period)
    result["atr_threshold"] = (
        result["atr"].shift(1).rolling(percentile_lookback, min_periods=percentile_lookback)
        .quantile(atr_percentile)
    )
    result["prior_high"] = (
        result["high"].shift(1).rolling(breakout_lookback, min_periods=breakout_lookback).max()
    )
    result["prior_low"] = (
        result["low"].shift(1).rolling(breakout_lookback, min_periods=breakout_lookback).min()
    )
    result["low_vol"] = result["atr"].lt(result["atr_threshold"])
    sell = result["low_vol"] & result["close"].gt(result["prior_high"])
    buy = result["low_vol"] & result["close"].lt(result["prior_low"])
    result["signal"] = np.select([buy, sell], [1, -1], default=0).astype(np.int8)
    result["decision_time"] = result.index + pd.Timedelta(minutes=timeframe_minutes(timeframe))
    return result
