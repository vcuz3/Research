"""Causal daily volatility/trend regimes with trailing empirical calibration.

The indicator for session t uses close-to-close returns through t-1.  Its
percentile and bucket thresholds use only earlier indicator observations.  The
full-sample ``qcut`` labels in EXP-0038 remain a descriptive control; this module
is the deployable, point-in-time construction introduced by HYP-0029/EXP-0041.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


VOL_LABELS = ("low", "normal", "elevated", "high")
TREND_LABELS = ("chop", "weak", "trend")


def daily_close_from_bars(bars: pd.DataFrame) -> pd.Series:
    """Return the last RTH close per session, sorted by session date."""
    return (bars.sort_values("et").groupby("date").tail(1)
            .set_index("date")["close"].sort_index().astype(float))


def regime_indicators(close: pd.Series, lookback: int) -> pd.DataFrame:
    """RV and absolute trend t-stat known before each session opens."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    close = close.sort_index().astype(float)
    ret = np.log(close / close.shift(1))
    sd = ret.rolling(lookback, min_periods=lookback).std()
    mu = ret.rolling(lookback, min_periods=lookback).mean()
    return pd.DataFrame({
        "rv_ann": (sd * np.sqrt(252.0)).shift(1),
        "abs_tstat": (mu / (sd / np.sqrt(float(lookback)))).shift(1).abs(),
    }, index=close.index)


def trailing_percentile(values: pd.Series, window: int, min_obs: int,
                        quantiles: tuple[float, ...]) -> pd.DataFrame:
    """Mid-rank percentile and prior-only empirical thresholds.

    The value at position i is ranked only against positions [i-window, i).
    Threshold columns are useful audit evidence and never include value i.
    """
    if window < 1 or not 1 <= min_obs <= window:
        raise ValueError("require 1 <= min_obs <= window")
    if any(not 0.0 < q < 1.0 for q in quantiles):
        raise ValueError("quantiles must be strictly between zero and one")

    x = values.astype(float).to_numpy()
    pct = np.full(len(x), np.nan)
    thresholds = np.full((len(x), len(quantiles)), np.nan)
    for i, current in enumerate(x):
        if not np.isfinite(current):
            continue
        hist = x[max(0, i - window):i]
        hist = hist[np.isfinite(hist)]
        if len(hist) < min_obs:
            continue
        pct[i] = ((hist < current).sum() + 0.5 * (hist == current).sum()) / len(hist)
        thresholds[i, :] = np.quantile(hist, quantiles)

    out = pd.DataFrame({"percentile": pct}, index=values.index)
    for j, q in enumerate(quantiles):
        out[f"q{q:.6f}"] = thresholds[:, j]
    return out


def _bucket(percentile: pd.Series, cuts: tuple[float, ...],
            labels: tuple[str, ...]) -> pd.Series:
    bins = (-np.inf, *cuts, np.inf)
    return pd.cut(percentile, bins=bins, labels=labels, right=False).astype("string")


def hysteresis_labels(percentile: pd.Series, cuts: tuple[float, ...],
                      labels: tuple[str, ...], buffer: float) -> pd.Series:
    """Convert a causal score to less jittery causal labels.

    Enter the next state only after crossing ``boundary + buffer`` and leave it
    only after crossing ``boundary - buffer``.  Multiple boundaries may be
    crossed on one observation, so a large move is not artificially delayed.
    ``buffer=0`` exactly reproduces ordinary left-closed percentile buckets.
    """
    if len(labels) != len(cuts) + 1:
        raise ValueError("labels must have one more element than cuts")
    if buffer < 0.0 or any(buffer >= 0.5 * (b - a)
                           for a, b in zip((0.0, *cuts), (*cuts, 1.0))):
        raise ValueError("buffer must be non-negative and smaller than half a bucket")

    x = percentile.astype(float).to_numpy()
    out = pd.Series(pd.NA, index=percentile.index, dtype="string")
    state: int | None = None
    for i, value in enumerate(x):
        if not np.isfinite(value):
            continue
        if state is None:
            state = int(np.searchsorted(np.asarray(cuts), value, side="right"))
        else:
            while state < len(cuts) and value >= cuts[state] + buffer:
                state += 1
            while state > 0 and value < cuts[state - 1] - buffer:
                state -= 1
        out.iloc[i] = labels[state]
    return out


def causal_regimes(close: pd.Series, indicator_lookback: int,
                   calibration_lookback: int,
                   min_fraction: float = 2.0 / 3.0) -> pd.DataFrame:
    """Build point-in-time volatility and trend regimes for every session."""
    if not 0.0 < min_fraction <= 1.0:
        raise ValueError("min_fraction must be in (0, 1]")
    min_obs = int(math.ceil(calibration_lookback * min_fraction))
    ind = regime_indicators(close, indicator_lookback)
    vol = trailing_percentile(ind["rv_ann"], calibration_lookback, min_obs,
                              (0.25, 0.50, 0.75))
    trend = trailing_percentile(ind["abs_tstat"], calibration_lookback, min_obs,
                                (1.0 / 3.0, 2.0 / 3.0))

    out = ind.copy()
    out["vol_percentile"] = vol["percentile"]
    out["trend_percentile"] = trend["percentile"]
    out["vol_q25"] = vol["q0.250000"]
    out["vol_q50"] = vol["q0.500000"]
    out["vol_q75"] = vol["q0.750000"]
    out["trend_q33"] = trend[f"q{1.0 / 3.0:.6f}"]
    out["trend_q67"] = trend[f"q{2.0 / 3.0:.6f}"]
    out["vol_regime"] = _bucket(out["vol_percentile"], (0.25, 0.50, 0.75),
                                 VOL_LABELS)
    out["trend_regime"] = _bucket(out["trend_percentile"], (1.0 / 3.0, 2.0 / 3.0),
                                   TREND_LABELS)
    out["cell"] = out["vol_regime"] + " x " + out["trend_regime"]
    return out
