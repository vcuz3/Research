"""Causal triangular-pricing features and entry signals."""

from __future__ import annotations

import math
from datetime import time

import numpy as np
import pandas as pd


def apply_signal_blackout(
    features: pd.DataFrame,
    timezone: str,
    start_time: str,
    end_time: str,
) -> tuple[pd.DataFrame, pd.Series]:
    """Suppress signals whose decision timestamps fall in a local-time window.

    Endpoints are inclusive. Naive indexes are interpreted as UTC, matching the
    project's normalized timestamp convention. Overnight windows are supported.
    """
    if "direction" not in features:
        raise ValueError("features must contain direction")
    if not isinstance(features.index, pd.DatetimeIndex):
        raise ValueError("features must have a DatetimeIndex")

    try:
        start = time.fromisoformat(start_time)
        end = time.fromisoformat(end_time)
    except ValueError as exc:
        raise ValueError("blackout times must use HH:MM or HH:MM:SS") from exc

    utc_index = features.index.tz_localize("UTC") if features.index.tz is None else features.index.tz_convert("UTC")
    local_times = pd.Series(utc_index.tz_convert(timezone).time, index=features.index)
    if start <= end:
        mask = local_times.ge(start) & local_times.le(end)
    else:
        mask = local_times.ge(start) | local_times.le(end)

    filtered = features.copy()
    filtered.loc[mask, "direction"] = 0
    return filtered, mask.rename("signal_blackout")


def build_triangle_features(
    panel: pd.DataFrame,
    zscore_lookback_bars: int,
    entry_z: float,
    basis_mode: str = "log",
    signal_mode: str = "cross",
    min_history_fraction: float = 0.9,
) -> pd.DataFrame:
    """Construct actual/synthetic prices, a causal Z-score, and trade direction.

    Rolling location and scale are shifted by one bar, so the completed decision
    bar is never included in its own normalizer. ``direction`` is +1 for a long
    residual (long AUDUSD, short AUDJPY, long USDJPY) and -1 for the reverse.
    """
    if zscore_lookback_bars < 20:
        raise ValueError("zscore_lookback_bars must be at least 20")
    if entry_z <= 0:
        raise ValueError("entry_z must be positive")
    if basis_mode not in {"log", "raw"}:
        raise ValueError("basis_mode must be 'log' or 'raw'")
    if signal_mode not in {"cross", "state"}:
        raise ValueError("signal_mode must be 'cross' or 'state'")
    if not 0 < min_history_fraction <= 1:
        raise ValueError("min_history_fraction must be in (0, 1]")

    actual = panel["audusd_close"]
    synthetic = panel["audjpy_close"] / panel["usdjpy_close"]
    raw_spread = actual - synthetic
    log_basis = np.log(actual) - np.log(panel["audjpy_close"]) + np.log(panel["usdjpy_close"])
    basis = log_basis if basis_mode == "log" else raw_spread

    min_periods = math.ceil(zscore_lookback_bars * min_history_fraction)
    history = basis.shift(1)
    mean = history.rolling(zscore_lookback_bars, min_periods=min_periods).mean()
    std = history.rolling(zscore_lookback_bars, min_periods=min_periods).std(ddof=1)
    zscore = (basis - mean) / std.replace(0, np.nan)
    state = pd.Series(np.where(zscore <= -entry_z, 1, np.where(zscore >= entry_z, -1, 0)), index=panel.index)
    if signal_mode == "cross":
        previous = zscore.shift(1)
        long_cross = zscore.le(-entry_z) & previous.gt(-entry_z)
        short_cross = zscore.ge(entry_z) & previous.lt(entry_z)
        direction = pd.Series(np.where(long_cross, 1, np.where(short_cross, -1, 0)), index=panel.index)
    else:
        direction = state

    return pd.DataFrame(
        {
            "actual_audusd": actual,
            "synthetic_audusd": synthetic,
            "spread": raw_spread,
            "spread_pips": raw_spread * 10_000,
            "log_basis": log_basis,
            "normalizer_mean": mean,
            "normalizer_std": std,
            "zscore": zscore,
            "direction": direction.astype("int8"),
            "history_count": history.rolling(zscore_lookback_bars, min_periods=1).count(),
        },
        index=panel.index,
    )
