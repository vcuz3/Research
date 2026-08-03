"""Causal absolute realised volatility on the decision grid.

Why this exists
---------------
Every result in this project is stratified by `block`, which is a *time-of-day*
window.  LEARNINGS 2026-07-31c showed that a split matched exactly on time of day
can still inherit a volatility gradient, and that the gradient — not the label —
was doing the work.  Testing that here needs a measure of the ABSOLUTE volatility
level at the decision, which is precisely what `core/vwap.py::causal_slot_scale`
deliberately removes: the same-slot z-score normalises each slot's own dispersion
away, so `dev_z` carries no information about whether this hour is a loud one.

Construction
------------
    rv_w(m)      = mean |close(k) - close(k-1)| for k in (m-w, m],   in pips
    rv_lag_w(m)  = the same over k in (m-w-lag, m-lag]

Both use only bars at or before `close(m)`, and the target's entry price is
`open(m+1)`, so no print is shared with the return being explained.

`rv_lag` exists because `rv_60` overlaps the 30 minutes that define the `past_30`
signal.  Conditioning a `past_30` bet on a quantity built from the same minutes
could attenuate it mechanically; `rv_lag_60` (minutes `(m-90, m-30]`) shares none
of them.

Missing minutes are averaged over rather than nulling the window (rule 9a: the
fractional floor, not `min_periods = w`), and the per-block coverage of the result
is reported by the caller before any contrast is read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D
from . import frame as F

WINDOW = 60
LAG = 30
MIN_FRAC = 0.5


def _close_grid(bars: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    piv = bars.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
    piv = piv.reindex(columns=np.arange(D.SESSION_MINUTES))
    return piv.to_numpy(float), piv.index.to_numpy()


def _window_mean(absd: np.ndarray, lo: int, hi: int, min_frac: float) -> np.ndarray:
    """Row-wise nanmean of `absd[:, lo:hi]`, NaN when under-populated."""
    if lo < 0 or hi <= lo:
        return np.full(absd.shape[0], np.nan)
    w = absd[:, lo:hi]
    cnt = np.isfinite(w).sum(axis=1)
    m = np.full(w.shape[0], np.nan)
    any_ok = cnt > 0
    if any_ok.any():
        with np.errstate(invalid="ignore"):
            m[any_ok] = np.nanmean(w[any_ok], axis=1)
    need = int(np.ceil(min_frac * (hi - lo)))
    return np.where(cnt >= need, m, np.nan)


def realized_vol(product: str, scope: str = "explore", *,
                 period: int = F.PERIOD, window: int = WINDOW,
                 lag: int = LAG, min_frac: float = MIN_FRAC) -> pd.DataFrame:
    """One row per decision with `rv_<window>` and `rv_lag_<window>` in pips.

    Merge onto a panel on `["sdate", "mfo"]`.
    """
    bars, _rep = D.load_bars(product, scope=scope)
    close_m, sdates = _close_grid(bars)
    # absd[:, j] = |close(j+1) - close(j)|, so the change ARRIVING at minute j+1.
    absd = np.abs(np.diff(close_m, axis=1)) / D.pip_size(product)

    dm = F.decision_mfos(period)
    dm = dm[dm < D.SESSION_MINUTES]
    rv = np.full((len(sdates), len(dm)), np.nan)
    rvl = np.full((len(sdates), len(dm)), np.nan)
    for j, m in enumerate(dm):
        # minutes (m-window, m]  ->  diff columns [m-window, m)
        rv[:, j] = _window_mean(absd, m - window, m, min_frac)
        # minutes (m-window-lag, m-lag]  ->  diff columns [m-window-lag, m-lag)
        rvl[:, j] = _window_mean(absd, m - window - lag, m - lag, min_frac)

    idx = pd.MultiIndex.from_product([sdates, dm], names=["sdate", "mfo"])
    out = pd.DataFrame(index=idx).reset_index()
    out[f"rv_{window}"] = rv.ravel()
    out[f"rv_lag_{window}"] = rvl.ravel()
    return out
