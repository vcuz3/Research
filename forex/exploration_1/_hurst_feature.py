"""Causal generalized Hurst exponent (order 1) on a fixed trailing window.

Measures the recent path's persistence regime independently of displacement magnitude
(|z|) and, as far as the estimator allows, of the volatility level. Built on a
FIXED-length trailing window (not session-to-date), so its sampling dispersion does not
shrink through the session -- the defect that makes a fixed threshold on a growing-window
persistence estimate a time-of-day selector (LEARNINGS 2026-08-03). The same-slot
z-score removes any residual per-slot drift.

H = OLS slope of  log <|logc(s) - logc(s-tau)|>_window  vs  log(tau)  over TAUS.
  H ~ 0.5 random walk, > 0.5 persistent/trending, < 0.5 anti-persistent/mean-reverting.

Causality: every value at bar t uses only bars <= t; exact-contiguous (defined only when
the trailing HURST_WIN bars are gap-free, exactly like `z` and `rv_30m`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from _rsi_stop_engine import exact_roll, slot_z

HURST_WIN = 120
TAUS = (1, 2, 4, 8, 16)


def _slope_weights(taus):
    """OLS-slope linear weights: slope = sum_k w_k * y_k for y_k = log K1(tau_k)."""
    x = np.log(np.asarray(taus, float))
    xc = x - x.mean()
    return xc / np.sum(xc ** 2)


def generalized_hurst(logc: pd.Series, time: pd.Series,
                      win: int = HURST_WIN, taus=TAUS) -> pd.Series:
    """Causal GHE(1) over a fixed trailing window, exact-contiguous."""
    w = _slope_weights(taus)
    cols = []
    for tau in taus:
        a = (logc - logc.shift(tau)).abs().where(
            time.shift(tau).eq(time - pd.Timedelta(minutes=tau)))
        k1 = exact_roll(a, time, win, "mean")          # trailing-window mean of |increment|
        cols.append(np.log(k1.replace(0, np.nan)).to_numpy())
    log_k = np.column_stack(cols)                       # n x len(taus)
    h = log_k @ w
    return pd.Series(h, index=logc.index)


def add_hurst_features(f: pd.DataFrame) -> pd.DataFrame:
    """Attach hurst and its same-slot z to a build_features frame."""
    time = f.time
    logc = pd.Series(np.log(f.close.astype(float)), index=f.index)
    f["hurst"] = generalized_hurst(logc, time).to_numpy()
    f["hurst_z"] = slot_z(f, "hurst")
    return f
