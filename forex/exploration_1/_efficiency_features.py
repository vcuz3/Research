"""Causal directional-efficiency features: Kaufman ER, Wilder ADX, HTF slope.

All three measure how DIRECTIONAL the recent path is, independently of the
displacement magnitude (|z|) and of the volatility level. They are added to the
`build_features` frame on the full minute grid so the same-slot z-scores are
estimated on the regular grid and read at the event rows (LEARNINGS 2026-08-04).

Causality: every value at bar t uses only bars <= t. KER and the HTF slope are
exact-contiguous (defined only when the trailing window is gap-free, exactly like
`rv_30m`). ADX resets per session and never smooths across the rollover gap.

The Wilder recursions reuse the project's SMA-seeded estimator (`recursive_wilder`)
so ADX is the same estimator family as `vei_atr`; the ADX smoother tolerates the
per-session warmup NaNs in DX by seeding from the first `length` valid values.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import lfilter

from _rsi_stop_engine import exact_roll, slot_z
from _run_rsi_broad_regime_sweep import recursive_wilder

KER_WIN = 30
ADX_LEN = 14
HTF_WIN = 120


def kaufman_er(logc: pd.Series, time: pd.Series, win: int = KER_WIN) -> pd.Series:
    """Net displacement / gross path over `win` minutes, exact-contiguous, in [0,1]."""
    one = time.diff().eq(pd.Timedelta(minutes=1))
    net = (logc - logc.shift(win)).abs().where(
        time.shift(win).eq(time - pd.Timedelta(minutes=win)))
    absret = logc.diff().where(one).abs()
    gross = exact_roll(absret, time, win, "sum")
    er = net / gross.replace(0, np.nan)
    return er.clip(0.0, 1.0)


def _rma_leading_nan(values, one_minute, length):
    """Wilder RMA per session, seeded from the first `length` FINITE values.

    Identical to `recursive_wilder` when the session has no leading NaNs (TR/DM);
    for DX, whose warmup region is NaN, it skips the leading NaNs and seeds at the
    first defined value. After the seed the segment is contiguous-finite by
    construction, so a single lfilter runs the recursion.
    """
    values = np.asarray(values, float)
    starts = np.flatnonzero(~one_minute)
    ends = np.r_[starts[1:], len(values)]
    out = np.full(len(values), np.nan, float)
    a = 1.0 / length
    for s, e in zip(starts, ends):
        seg = values[s:e]
        finite = np.flatnonzero(np.isfinite(seg))
        if len(finite) < length:
            continue
        off = finite[0]
        x = seg[off:]
        if not np.all(np.isfinite(x)):
            continue                       # a mid-session gap in a smoothed input
        seed = float(np.mean(x[:length]))
        k = s + off + length - 1
        out[k] = seed
        if len(x) > length:
            filtered, _ = lfilter([a], [1.0, -(1.0 - a)], x[length:],
                                  zi=[(1.0 - a) * seed])
            out[k + 1:e] = filtered
    return out


def wilder_adx(high, low, close, one_minute, length: int = ADX_LEN):
    """Wilder ADX(length), intraday, session-reset. High = trending, low = ranging."""
    high = np.asarray(high, float)
    low = np.asarray(low, float)
    close = np.asarray(close, float)
    one = np.asarray(one_minute, bool)
    starts = ~one                                   # first bar of each session

    prev_high = np.r_[np.nan, high[:-1]]
    prev_low = np.r_[np.nan, low[:-1]]
    prev_close = np.r_[np.nan, close[:-1]]

    up = high - prev_high
    dn = prev_low - low
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([high - low,
                            np.abs(high - prev_close),
                            np.abs(low - prev_close)])
    # a session's first bar has no previous bar: no directional move, TR = range
    plus_dm[starts] = 0.0
    minus_dm[starts] = 0.0
    tr[starts] = (high - low)[starts]

    atr = recursive_wilder(tr, one, length)
    plus_s = recursive_wilder(plus_dm, one, length)
    minus_s = recursive_wilder(minus_dm, one, length)
    with np.errstate(invalid="ignore", divide="ignore"):
        di_plus = 100.0 * plus_s / np.where(atr > 0, atr, np.nan)
        di_minus = 100.0 * minus_s / np.where(atr > 0, atr, np.nan)
        denom = di_plus + di_minus
        dx = 100.0 * np.abs(di_plus - di_minus) / np.where(denom > 0, denom, np.nan)
    return _rma_leading_nan(dx, one, length)


def add_efficiency_features(f: pd.DataFrame) -> pd.DataFrame:
    """Attach ker, ker_z, adx, adx_z, htf_slope to a `build_features` frame."""
    time = f.time
    logc = pd.Series(np.log(f.close.astype(float)), index=f.index)
    one = time.diff().eq(pd.Timedelta(minutes=1))

    f["ker"] = kaufman_er(logc, time, KER_WIN).to_numpy()
    f["adx"] = wilder_adx(f.high.astype(float), f.low.astype(float),
                          f.close.astype(float), one.to_numpy(), ADX_LEN)
    f["htf_slope"] = (logc - logc.shift(HTF_WIN)).where(
        time.shift(HTF_WIN).eq(time - pd.Timedelta(minutes=HTF_WIN))).to_numpy()

    f["ker_z"] = slot_z(f, "ker")
    f["adx_z"] = slot_z(f, "adx")
    return f
