"""
Range-expansion signal and per-signal forward-return scoring.

Signal (per session, on the compacted within-session 5-min bar series):
    R_t   = high_t - low_t
    M_t   = mean(R over the N bars ending at t-1)        # causal, EXCLUDES bar t
    fire  = R_t >= k * M_t                                # k = 1.5 primary
    dir   = sign(close_t - open_t)                        # continuation; 0 -> skip

Execution (the article's own convention, and workspace Rule A2):
    entry = open[t+1]                                     # next bar's open
    exit  = open[t+1+H]  if that bar exists in the session, else close[last bar]

`M_t` uses `min_periods = ceil(2N/3)` rather than a strict `N`, per LEARNINGS #2: a
strict `min_periods == window` on a session-reset rolling feature is a hidden,
time-of-day-dependent filter that silently deletes early-session decisions. Rows where
the window is under-populated are reported, not silently dropped.

Everything is vectorised over the whole archive; the session reset is handled by
clamping each row's window start to its own session's first bar, so no window and no
trade ever crosses a session boundary. `test_engine.py` pins this behaviour.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _session_geometry(bars: pd.DataFrame):
    """Return (sorted frame, within-session index, global session start, session end)."""
    b = bars.sort_values(["trade_date", "bar_i"]).reset_index(drop=True)
    bi = b["bar_i"].to_numpy()
    i = np.arange(len(b))
    start = i - bi                              # global index of this session's bar 0
    length = b.groupby("trade_date")["bar_i"].transform("size").to_numpy()
    end = start + length - 1                    # global index of this session's last bar
    return b, bi, start, end


def _trailing_mean(r: np.ndarray, start: np.ndarray, n: int, min_periods: int):
    """Mean of the up-to-`n` values ending at t-1, clamped to the session start."""
    i = np.arange(len(r))
    cum = np.concatenate([[0.0], np.cumsum(r)])
    ws = np.maximum(start, i - n)               # window start (inclusive), never before bar 0
    cnt = i - ws                                # values in [ws, t-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(cnt > 0, (cum[i] - cum[ws]) / np.maximum(cnt, 1), np.nan)
    m = np.where(cnt >= min_periods, m, np.nan)
    return m, cnt


def _fire_mask(bars: pd.DataFrame, k: float, n: int):
    b, bi, start, end = _session_geometry(bars)
    mp = int(np.ceil(2 * n / 3))
    r = b["range"].to_numpy(float)
    m, cnt = _trailing_mean(r, start, n, mp)
    with np.errstate(invalid="ignore"):
        fire = np.isfinite(m) & (m > 0) & (r >= k * m)
    return b, bi, start, end, m, fire, np.isfinite(m)


def signals(bars: pd.DataFrame, k: float = 1.5, n: int = 20, hold: int = 3,
            direction: str = "continuation") -> pd.DataFrame:
    """Score every firing bar. One row per signal (overlaps allowed)."""
    sign_mult = 1.0 if direction == "continuation" else -1.0
    b, bi, start, end, m, fire, _ = _fire_mask(bars, k, n)
    o = b["open"].to_numpy(float); c = b["close"].to_numpy(float)
    r = b["range"].to_numpy(float)

    idx = np.flatnonzero(fire)
    idx = idx[idx + 1 <= end[idx]]                       # entry bar must exist in-session
    if not len(idx):
        return pd.DataFrame()
    d = np.sign(c[idx] - o[idx]) * sign_mult
    idx = idx[d != 0]
    d = d[d != 0]
    if not len(idx):
        return pd.DataFrame()

    e_i = idx + 1
    want = idx + 1 + hold
    truncated = want > end[idx]
    x_i = np.minimum(want, end[idx])
    entry = o[e_i]
    exit_p = np.where(truncated, c[end[idx]], o[x_i])

    return pd.DataFrame(dict(
        trade_date=b["trade_date"].to_numpy()[idx], bar_i=bi[idx],
        slot=b["slot"].to_numpy()[idx], dir=d,
        bar_range=r[idx], roll_mean=m[idx], expansion=r[idx] / m[idx],
        bar_volume=b["volume"].to_numpy()[idx],
        entry=entry, exit=exit_p, truncated=truncated, held=(x_i - e_i),
        gross_pts=d * (exit_p - entry),
    ))


def fire_rate_by_slot(bars: pd.DataFrame, k: float = 1.5, n: int = 20) -> pd.DataFrame:
    """LEARNINGS #1 diagnostic: does a fixed multiple of a trailing mean fire at a
    uniform rate across the session, or is it a time-of-day selector?"""
    b, bi, start, end, m, fire, defined = _fire_mask(bars, k, n)
    df = pd.DataFrame({"slot": b["slot"].to_numpy(), "fire": fire, "defined": defined})
    out = df.groupby("slot").agg(bars=("fire", "size"), defined_frac=("defined", "mean"))
    out["fire_rate"] = df.groupby("slot")["fire"].mean()
    out["fire_rate_defined"] = df[df["defined"]].groupby("slot")["fire"].mean()
    return out
