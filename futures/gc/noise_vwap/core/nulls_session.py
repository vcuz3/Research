"""
Session-keyed (sdate/mfo) path-preserving RETURN shuffle (Null C) for the GC grid.

Same construction and invariants as `core.nulls.null_c_returns` (CLAUDE.md rule
17 / the 2026-07-18 opening-anchor learning), adapted to the fast-engine schema and
to BOTH VWAP anchors:

  * Each RTH session's bars are return-shuffled: bar geometry (h-o, l-o, c-o), the
    inter-bar link (open[t]-close[t-1]) and volume are kept as atoms; the opening
    atom (index 0, sentinel link 0) is PINNED; the rest are permuted and the path
    is rebuilt from the true first open. Preserves bar shapes, the return/volume
    distribution and the session NET move; destroys the ORDER of intraday moves.
  * `vwap_rth` is recomputed on the reshuffled path (reset at 09:30).
  * `vwap_eth` is recomputed as (fixed overnight anchor ov_tpv/ov_v) + the
    reshuffled RTH cumulative -- the overnight context the strategy may merely ride
    is preserved, the RTH intraday order it predicts is destroyed. Symmetric to the
    RTH anchor's treatment of its own opening bar.

Validate with `diffusivity()` before trusting (rule 17-bis).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def null_c_returns(rth: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Return a reshuffled copy of `rth` (from session.load_rth_both) with vwap_rth
    and vwap_eth recomputed on the shuffled path. Caller rebuilds noise bands."""
    rng = np.random.default_rng(seed)
    d = rth.sort_values(["sdate", "mfo"]).reset_index(drop=True)
    parts = []
    for _, g in d.groupby("sdate", sort=False):
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
        # pin the complete opening atom at index 0 (2026-07-18 learning), permute rest
        perm = np.concatenate(([0], rng.permutation(np.arange(1, n))))
        dh, dl, dc, link = dh[perm], dl[perm], dc[perm], link[perm]
        vol = g["volume"].to_numpy()[perm]
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
        g["volume"] = vol
        tp = (g["high"] + g["low"] + g["close"]) / 3.0
        v = vol.astype("float64")
        cum_v = np.cumsum(v)
        cum_tpv = np.cumsum(tp.to_numpy() * v)
        g["vwap_rth"] = cum_tpv / cum_v
        ov_tpv = float(g["ov_tpv"].iloc[0])
        ov_v = float(g["ov_v"].iloc[0])
        g["vwap_eth"] = (ov_tpv + cum_tpv) / (ov_v + cum_v)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def diffusivity(rth: pd.DataFrame) -> float:
    """Median |next_open - this_close| across within-session bar steps (points)."""
    d = rth.sort_values(["sdate", "mfo"])
    nxt_open = d.groupby("sdate")["open"].shift(-1)
    return float((nxt_open - d["close"]).abs().dropna().median())
