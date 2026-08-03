"""
Path-preserving RETURN shuffle (Null C) for the FX Noise-Area study, ported from
the maintained reference `futures/nq/noise_vwap/core/nulls.py` (RULES.md rule 17).

Per session each bar's internal geometry `shape = (h-o, l-o, c-o)` and the
bar-to-bar link `link[t] = open[t] - close[t-1]` are kept as atoms. The opening
bar and its sentinel link are PINNED at index 0 (the 2026-07-18 shared learning:
shuffling the artificial `link[0] = 0` anchor silently drops a real link and
changes the reconstructed session net move). The remaining atoms are permuted and
the path is rebuilt from the session's true first open.

Preserves : bar geometry, the return distribution and its tails, the session NET
            move (a sum is permutation-invariant), and the opening anchor.
Destroys  : the ORDER of moves after the opening bar, hence intraday
            autocorrelation, continuation, mean reversion, volatility clustering
            and intraday seasonality.

The strategy predicts intraday continuation, which the null destroys; the drift
it merely rides is preserved. A real timing edge must beat this null.

The TWAP is recomputed on the shuffled path, exactly as the real pipeline builds
it, and the caller must rebuild the noise bands from the returned frame.
Validate with `diffusivity()` before interpreting any P&L (rule 17-bis).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def null_c_returns(bars: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Return a new long bars frame with each session's bars return-shuffled."""
    rng = np.random.default_rng(seed)
    d = bars.sort_values(["date", "mfo"]).reset_index(drop=True)
    parts = []
    for _, g in d.groupby("date", sort=False):
        n = len(g)
        g = g.copy()
        o = g["open"].to_numpy(dtype=float)
        h = g["high"].to_numpy(dtype=float)
        l = g["low"].to_numpy(dtype=float)
        c = g["close"].to_numpy(dtype=float)
        dh, dl, dc = h - o, l - o, c - o
        link = np.empty(n)
        link[0] = 0.0
        link[1:] = o[1:] - c[:-1]
        # pin the complete opening atom at index 0
        perm = np.concatenate(([0], rng.permutation(np.arange(1, n))))
        dh, dl, dc, link = dh[perm], dl[perm], dc[perm], link[perm]
        o2 = np.empty(n)
        c2 = np.empty(n)
        o2[0] = o[0]
        c2[0] = o2[0] + dc[0]
        for i in range(1, n):
            o2[i] = c2[i - 1] + link[i]
            c2[i] = o2[i] + dc[i]
        g["open"] = o2
        g["close"] = c2
        g["high"] = o2 + dh
        g["low"] = o2 + dl
        # rebuild the causal cumulative session TWAP on the shuffled path
        tp = (g["high"] + g["low"] + g["close"]) / 3.0
        g["twap"] = np.cumsum(tp.to_numpy()) / np.arange(1, n + 1)
        g["bar_i"] = np.arange(n)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def diffusivity(bars: pd.DataFrame) -> float:
    """Median |next_open - this_close| across all within-session bar steps."""
    d = bars.sort_values(["date", "mfo"])
    nxt = d.groupby("date")["open"].shift(-1)
    return float((nxt - d["close"]).abs().dropna().median())


def session_net_move(bars: pd.DataFrame) -> pd.Series:
    d = bars.sort_values(["date", "mfo"])
    g = d.groupby("date")
    return g["close"].last() - g["open"].first()
