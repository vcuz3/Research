"""Feature translation of the supplied Pine v6 triangular strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd


def wilder_rma(values: pd.Series, period: int) -> pd.Series:
    """TradingView-style Wilder moving average seeded with an n-value SMA."""
    if period < 1:
        raise ValueError("period must be positive")
    x = values.astype(float).to_numpy()
    out = np.full(len(x), np.nan)
    valid = np.flatnonzero(np.isfinite(x))
    if len(valid) < period:
        return pd.Series(out, index=values.index, name=values.name)
    # The price panels are contiguous inside a segment. Restart after any NaN.
    run_start = 0
    while run_start < len(x):
        while run_start < len(x) and not np.isfinite(x[run_start]):
            run_start += 1
        run_end = run_start
        while run_end < len(x) and np.isfinite(x[run_end]):
            run_end += 1
        if run_end - run_start >= period:
            seed_pos = run_start + period - 1
            out[seed_pos] = x[run_start : seed_pos + 1].mean()
            alpha = 1.0 / period
            for i in range(seed_pos + 1, run_end):
                out[i] = out[i - 1] + alpha * (x[i] - out[i - 1])
        run_start = run_end + 1
    return pd.Series(out, index=values.index, name=values.name)


def pine_atr(audusd_bars: pd.DataFrame, period: int) -> pd.Series:
    previous_close = audusd_bars["audusd_close"].shift(1)
    true_range = pd.concat(
        [
            audusd_bars["audusd_high"] - audusd_bars["audusd_low"],
            (audusd_bars["audusd_high"] - previous_close).abs(),
            (audusd_bars["audusd_low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return wilder_rma(true_range, period).rename("atr")


def build_pine_features(
    panel: pd.DataFrame,
    audusd_bars: pd.DataFrame,
    lookback_period: int = 50,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Translate the Pine spread, SMA/stdev Z-score, and ATR calculations.

    Pine's ``ta.sma`` and ``ta.stdev`` include the current completed bar, and
    ``ta.stdev`` is population standard deviation by default (ddof=0). Those
    details are preserved here. Orders based on the result are placed later by
    the engine, so current-bar inclusion is causal at a bar-close decision.
    """
    if lookback_period < 5:
        raise ValueError("lookback_period must be at least 5")
    if atr_period < 1:
        raise ValueError("atr_period must be positive")
    actual = panel["audusd_close"]
    synthetic = panel["audjpy_close"] / panel["usdjpy_close"]
    spread = actual - synthetic
    mean = spread.rolling(lookback_period, min_periods=lookback_period).mean()
    std = spread.rolling(lookback_period, min_periods=lookback_period).std(ddof=0)
    zscore = ((spread - mean) / std.replace(0, np.nan)).fillna(0.0)
    atr = pine_atr(audusd_bars, atr_period).reindex(panel.index)
    z_ready = mean.notna() & std.gt(0)
    atr_ready = atr.notna()
    return pd.DataFrame(
        {
            "actual_audusd": actual,
            "synthetic_audusd": synthetic,
            "spread": spread,
            "spread_pips": spread * 10_000,
            "mean_spread": mean,
            "std_spread": std,
            "zscore": zscore,
            "atr": atr,
            "z_ready": z_ready,
            "atr_ready": atr_ready,
            "feature_ready": z_ready & atr_ready,
        },
        index=panel.index,
    )
