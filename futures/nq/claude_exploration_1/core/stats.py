"""Inference helpers: session-block bootstrap, within-slot statistics, re-pairing null.

Reuses the audited measurement helpers from ``futures.nq.vei_exploration.core.analysis``
rather than reimplementing them (same policy as that project's ``core/nulls.py``, which
reuses ``noise_vwap.null_c_returns``). Everything added here is either (a) a within-slot
form the other project does not have, or (b) the cross-instrument re-pairing null that
rule 18 requires for a cross-market claim.

Two conventions carried over from the workspace, both load-bearing:

* Inference resamples WHOLE SESSIONS (rule 12). Intraday rows are strongly dependent;
  an i.i.d. bootstrap over 40,000 decision rows would produce absurdly tight intervals.
* An intraday panel statistic is reported WITHIN SLOT and count-weighted. A pooled
  correlation on this panel is dominated by getting the time-of-day ordering right,
  which no decision ever requires -- a decision is always made at one slot on one day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from futures.nq.vei_exploration.core.analysis import (   # audited, reused as-is
    _block_boot, _rankcorr, block_boot_corr, block_boot_ic,
    block_boot_within_slot_ic, block_boot_within_slot_ic_delta, partial_spearman,
    session_slices, spearman, within_slot_ic_arrays,
)

__all__ = [
    "spearman", "partial_spearman", "within_slot_ic_arrays", "session_slices",
    "block_boot_ic", "block_boot_corr", "block_boot_within_slot_ic",
    "block_boot_within_slot_ic_delta", "within_slot_partial_ic",
    "block_boot_within_slot_partial_ic", "within_slot_corr", "regime_contrast",
    "block_boot_regime_contrast", "repair_sessions", "fmt_ci",
]


def fmt_ci(v: tuple[float, float, float]) -> str:
    r, lo, hi = v
    star = "*" if np.isfinite(lo) and np.isfinite(hi) and lo * hi > 0 else " "
    return f"{r:+.4f} [{lo:+.4f},{hi:+.4f}]{star}"


# --------------------------------------------------------------------------- #
# within-slot partial IC
# --------------------------------------------------------------------------- #
def within_slot_partial_ic(x: np.ndarray, y: np.ndarray, z: np.ndarray,
                           slot: np.ndarray, min_n: int = 30) -> float:
    """Count-weighted mean of the per-slot partial Spearman IC of x,y given z.

    "What does x say about y that z does not already say", computed at the slot a
    decision is actually made at.
    """
    num = den = 0.0
    for s in np.unique(slot[np.isfinite(slot)]):
        m = slot == s
        if int(m.sum()) < min_n:
            continue
        ic = partial_spearman(x[m], y[m], z[m])
        if np.isfinite(ic):
            num += ic * int(m.sum())
            den += int(m.sum())
    return num / den if den else np.nan


def block_boot_within_slot_partial_ic(df: pd.DataFrame, xcol: str, ycol: str,
                                      zcol: str, rng, nboot: int = 400,
                                      slot_col: str = "mfo", date_col: str = "date"
                                      ) -> tuple[float, float, float]:
    d = df.dropna(subset=[xcol, ycol, zcol, slot_col])
    if len(d) < 200:
        return np.nan, np.nan, np.nan
    cols = [xcol, ycol, zcol, slot_col]
    real = within_slot_partial_ic(*[d[c].to_numpy(float) for c in cols])
    boots = _block_boot(d, cols, within_slot_partial_ic, rng, nboot, date_col=date_col)
    return float(real), *np.nanpercentile(boots, [5, 95])


# --------------------------------------------------------------------------- #
# within-slot Pearson correlation and the regime contrast
# --------------------------------------------------------------------------- #
def within_slot_corr(x: np.ndarray, y: np.ndarray, slot: np.ndarray,
                     min_n: int = 30) -> float:
    """Count-weighted mean of the per-slot PEARSON correlation.

    The momentum statistic of `vei_exploration` Study D -- corr(trailing return, next
    return) -- measured within slot so the answer is not a time-of-day composition.
    """
    num = den = 0.0
    for s in np.unique(slot[np.isfinite(slot)]):
        m = slot == s
        n = int(m.sum())
        if n < min_n:
            continue
        xa, ya = x[m], y[m]
        v = np.isfinite(xa) & np.isfinite(ya)
        if v.sum() < min_n:
            continue
        c = np.corrcoef(xa[v], ya[v])[0, 1]
        if np.isfinite(c):
            num += c * int(v.sum())
            den += int(v.sum())
    return num / den if den else np.nan


def _split_by_rate(sel: np.ndarray, slot: np.ndarray, rate: float
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Top-``rate`` / bottom-``rate`` masks of ``sel``, thresholded WITHIN EACH SLOT.

    Matching the selection rate is mandatory when comparing regime labels: otherwise a
    label wins simply by relabelling more observations (the `vei_exploration` finding
    H/I method note). Thresholding per slot additionally guarantees the two cells have
    identical time-of-day composition, so the contrast cannot be a clock.
    """
    hi = np.zeros(len(sel), bool)
    lo = np.zeros(len(sel), bool)
    for s in np.unique(slot[np.isfinite(slot)]):
        m = (slot == s) & np.isfinite(sel)
        if m.sum() < 40:
            continue
        v = sel[m]
        qh, ql = np.quantile(v, 1 - rate), np.quantile(v, rate)
        idx = np.flatnonzero(m)
        hi[idx[v >= qh]] = True
        lo[idx[v <= ql]] = True
    return hi, lo


def regime_contrast(past: np.ndarray, fwd: np.ndarray, sel: np.ndarray,
                    slot: np.ndarray, rate: float = 0.30) -> float:
    """within-slot corr(past, fwd) in the TOP ``rate`` of ``sel`` minus the BOTTOM.

    Positive means the regime label picks out the part of the tape where trailing
    moves continue. Both cells are the same size and have the same slot composition
    by construction.
    """
    hi, lo = _split_by_rate(sel, slot, rate)
    return (within_slot_corr(past[hi], fwd[hi], slot[hi])
            - within_slot_corr(past[lo], fwd[lo], slot[lo]))


def block_boot_regime_contrast(df: pd.DataFrame, past: str, fwd: str, sel: str,
                               rng, nboot: int = 400, rate: float = 0.30,
                               slot_col: str = "mfo", date_col: str = "date"
                               ) -> tuple[float, float, float]:
    d = df.dropna(subset=[past, fwd, sel, slot_col])
    if len(d) < 500:
        return np.nan, np.nan, np.nan
    cols = [past, fwd, sel, slot_col]

    def _stat(p, f, s, sl):
        return regime_contrast(p, f, s, sl, rate=rate)

    real = _stat(*[d[c].to_numpy(float) for c in cols])
    boots = _block_boot(d, cols, _stat, rng, nboot, date_col=date_col)
    return float(real), *np.nanpercentile(boots, [5, 95])


# --------------------------------------------------------------------------- #
# rule-18 cross-instrument re-pairing null
# --------------------------------------------------------------------------- #
def repair_sessions(dates: pd.DatetimeIndex, rng, stratify: str = "year"
                    ) -> np.ndarray:
    """A derangement of session indices, stratified so donors share the era.

    Rule 18: a cross-instrument claim needs a null that destroys CONTEMPORANEOUS
    cross-information while preserving each leg's own dynamics. Re-pairing today's
    equity/gold session with a DIFFERENT session's dollar path does exactly that: the
    dollar path is a real dollar path with real volatility, autocorrelation, calendar
    and roll structure -- it just did not happen on the same day.

    Donors are drawn within calendar year so the null does not accidentally test the
    2011 dollar against the 2025 dollar (an era change, not a pairing change). Fixed
    points are resampled so no session is paired with itself.
    """
    key = pd.Series(dates).dt.year.to_numpy() if stratify == "year" else np.zeros(len(dates))
    out = np.arange(len(dates))
    for k in np.unique(key):
        idx = np.flatnonzero(key == k)
        if len(idx) < 3:
            continue
        perm = rng.permutation(idx)
        # Force a DERANGEMENT: a session paired with itself would leak exactly the
        # contemporaneous information the null exists to destroy. Each remaining fixed
        # point is swapped with a random other position in the same era block, which
        # cannot create a new fixed point (the partner was not fixed).
        for _ in range(50):
            f = np.flatnonzero(perm == idx)
            if f.size == 0:
                break
            for i in f:
                j = i
                while j == i:
                    j = int(rng.integers(0, len(idx)))
                perm[i], perm[j] = perm[j], perm[i]
        out[idx] = perm
    return out
