"""
Single-instrument path-preserving RETURN shuffle (Null C) for the Noise-Area
momentum study. See CLAUDE.md rule 17/17-bis.

Per session we keep each bar's internal geometry  shape=(h-o, l-o, c-o)  and the
bar-to-bar link  link[t]=open[t]-close[t-1]  as atoms. The opening bar and its
sentinel link are pinned at index 0; the remaining atoms are permuted and the
path is rebuilt from the session's true first open. This:
  preserves  bar geometry, the return distribution + fat tails, volumes, and the
             session NET move (a sum is permutation-invariant);
  destroys   the ORDER of moves after the opening bar -> most intraday
             autocorrelation, mean reversion, vol clustering, and seasonality.

Everything the strategy PREDICTS (intraday continuation) is destroyed; the drift
it might merely ride is preserved. So a real timing edge must beat this null; the
excess over the null is the machinery-manufactured P&L.

VALIDATE before trusting (rule 17-bis): the null must reproduce the real tape's
median |next_open - this_close| (diffusivity gate). `diffusivity()` checks it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def null_c_returns(bars: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Return a new long bars frame with each session's bars return-shuffled.
    Recomputes cumulative session VWAP + bar_i on the rebuilt path. Caller must
    rebuild the noise bands from the returned frame (same pipeline, rule 17)."""
    rng = np.random.default_rng(seed)
    d = bars.sort_values(["date", "tod"]).reset_index(drop=True)
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
        # link[0] is an artificial anchor, not an observed inter-bar link.  It
        # must remain at index 0: if it is shuffled, reconstruction re-anchors
        # the first open and silently drops whichever real link lands there.
        # Pinning the complete first atom preserves both net move and the
        # original (link, shape, volume) pairing for every shuffled atom.
        perm = np.concatenate(([0], rng.permutation(np.arange(1, n))))
        dh, dl, dc, link = dh[perm], dl[perm], dc[perm], link[perm]
        o2 = np.empty(n)
        c2 = np.empty(n)
        o2[0] = o[0]
        for i in range(n):
            if i > 0:
                o2[i] = c2[i - 1] + link[i]
            c2[i] = o2[i] + dc[i]
        g["open"] = o2
        g["close"] = c2
        g["high"] = o2 + dh
        g["low"] = o2 + dl
        g["volume"] = g["volume"].to_numpy()[perm]
        # rebuild cumulative session VWAP on the shuffled path
        tp = (g["high"] + g["low"] + g["close"]) / 3.0
        v = g["volume"].astype("float64").to_numpy()
        cum_v = np.cumsum(v)
        cum_tpv = np.cumsum(tp.to_numpy() * v)
        g["vwap"] = cum_tpv / cum_v
        g["bar_i"] = np.arange(n)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def diffusivity(bars: pd.DataFrame) -> float:
    """Median |next_open - this_close| across all within-session bar steps."""
    d = bars.sort_values(["date", "tod"])
    nxt_open = d.groupby("date")["open"].shift(-1)
    step = (nxt_open - d["close"]).abs()
    return float(step.dropna().median())
