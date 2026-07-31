"""Causal cross-asset features at the 30-minute decision clock.

The panel from ``core.data.rth_panel`` is a complete (session x 390-minute) grid, so
every feature here is built by reshaping to ``(n_sessions, 390)`` matrices and doing
window arithmetic on them. That shape is the point: a window can never silently span
two sessions, and the first minute of a session has no in-session predecessor, so the
overnight gap is never mixed into an intraday return.

Everything is measured in LOG PRICE space on the roll-adjusted level, so a "return"
is always a difference of two levels and is additive across windows.

Causality (rule 7). At decision minute ``m``:
  * PAST features use bars in ``(m - W, m]`` -- observable when the decision is made.
  * FORWARD features use ``(m, m + H]`` -- targets only, never predictors.
  * The dollar beta is fitted on STRICTLY PRIOR SESSIONS, never on the window whose
    residual it forms. An in-window beta would make the residual mechanically
    orthogonal to the dollar and would be fitted on its own evaluation data.
  * Trailing same-slot statistics come from ``causal_slot_stats``-style windows over
    strictly earlier sessions at the same time of day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D

PERIOD = 30
RTH_MINUTES = D.RTH_MINUTES


def decision_mfos(period: int = PERIOD) -> np.ndarray:
    """Closing minute of each `period`-long RTH block: 29, 59, ..., 389."""
    return np.arange(1, RTH_MINUTES // period + 1) * period - 1


# --------------------------------------------------------------------------- #
# panel -> matrices
# --------------------------------------------------------------------------- #
def to_matrix(panel: pd.DataFrame, col: str) -> np.ndarray:
    """Reshape a panel column to ``(n_sessions, 390)`` in (sdate, mfo) order."""
    n = len(panel) // RTH_MINUTES
    assert len(panel) == n * RTH_MINUTES, "panel is not a complete RTH grid"
    return panel[col].to_numpy(float).reshape(n, RTH_MINUTES)


def sessions_of(panel: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(panel["sdate"].to_numpy()[::RTH_MINUTES])


def minute_returns(lp: np.ndarray) -> np.ndarray:
    """1-minute log returns inside each session; column 0 is NaN by construction."""
    r = np.full_like(lp, np.nan)
    r[:, 1:] = lp[:, 1:] - lp[:, :-1]
    return r


def _nan_cumsum(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative sum treating NaN as absent, plus a cumulative COUNT of valid cells.

    Both arrays get a leading zero column so a window ``(i, j]`` is ``cs[:, j]-cs[:, i]``.
    """
    v = np.isfinite(a)
    z = np.where(v, a, 0.0)
    cs = np.concatenate([np.zeros((a.shape[0], 1)), np.cumsum(z, axis=1)], axis=1)
    cn = np.concatenate([np.zeros((a.shape[0], 1)), np.cumsum(v, axis=1)], axis=1)
    return cs, cn


# --------------------------------------------------------------------------- #
# causal dollar beta from strictly prior sessions
# --------------------------------------------------------------------------- #
def causal_beta(r_inst: np.ndarray, r_dxy: np.ndarray, lookback: int = 20,
                min_obs: int = 2000) -> np.ndarray:
    """Per-session OLS slope of instrument 1-min returns on dollar 1-min returns,
    fitted on the ``lookback`` STRICTLY PRIOR sessions.

    Returns a length-``n_sessions`` vector; NaN until ``min_obs`` paired minutes are
    available. A through-the-origin slope is used because both inputs are 1-minute
    log returns whose intraday mean is indistinguishable from zero, and estimating an
    intercept on ~7,800 near-zero-mean observations only adds variance.

    ``min_obs`` follows the rule-9a fractional policy: 2,000 of a possible ~7,780
    paired minutes (20 sessions x 389), so a few thin FX days never delete a beta
    outright, but a genuinely broken window still does.
    """
    m = np.isfinite(r_inst) & np.isfinite(r_dxy)
    xy = np.where(m, r_inst * r_dxy, 0.0).sum(axis=1)
    xx = np.where(m, r_dxy * r_dxy, 0.0).sum(axis=1)
    cnt = m.sum(axis=1).astype(float)
    # trailing sums over the previous `lookback` sessions (strictly prior: shift 1)
    def _roll(v):
        s = pd.Series(v).shift(1).rolling(lookback, min_periods=1).sum()
        return s.to_numpy(float)
    XY, XX, N = _roll(xy), _roll(xx), _roll(cnt)
    beta = np.where((N >= min_obs) & (XX > 0), XY / np.where(XX > 0, XX, np.nan), np.nan)
    return beta


def rolling_corr(r_a: np.ndarray, r_b: np.ndarray, win: int) -> np.ndarray:
    """Trailing ``win``-minute within-session correlation of two 1-min return series.

    Value at column ``m`` uses minutes ``(m - win, m]`` of the SAME session, so it is
    causal and never spans the overnight gap. Pairs where either series is NaN are
    dropped from that window (this is how dollar staleness is excluded: the caller
    NaNs stale minutes before calling). NaN where fewer than ``win // 2`` valid pairs
    survive -- the fractional-coverage policy of rule 9a rather than a strict count,
    so a normally-thin hour is measured rather than deleted.
    """
    m = np.isfinite(r_a) & np.isfinite(r_b)
    a = np.where(m, r_a, 0.0)
    b = np.where(m, r_b, 0.0)
    csa, cn = _nan_cumsum(np.where(m, r_a, np.nan))
    csb, _ = _nan_cumsum(np.where(m, r_b, np.nan))
    csaa, _ = _nan_cumsum(np.where(m, r_a * r_a, np.nan))
    csbb, _ = _nan_cumsum(np.where(m, r_b * r_b, np.nan))
    csab, _ = _nan_cumsum(np.where(m, a * b, np.nan))
    out = np.full(r_a.shape, np.nan)
    T = r_a.shape[1]
    for mm in range(T):
        lo = max(0, mm + 1 - win)
        n = cn[:, mm + 1] - cn[:, lo]
        sa = csa[:, mm + 1] - csa[:, lo]
        sb = csb[:, mm + 1] - csb[:, lo]
        saa = csaa[:, mm + 1] - csaa[:, lo]
        sbb = csbb[:, mm + 1] - csbb[:, lo]
        sab = csab[:, mm + 1] - csab[:, lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            cov = sab - sa * sb / n
            va = saa - sa * sa / n
            vb = sbb - sb * sb / n
            c = cov / np.sqrt(va * vb)
        out[:, mm] = np.where(n >= max(10, win // 2), c, np.nan)
    return np.clip(out, -1.0, 1.0)


# --------------------------------------------------------------------------- #
# trailing same-slot normalisation (the EXP-0009 canonical construction)
# --------------------------------------------------------------------------- #
def slot_zscore(mat: np.ndarray, lookback: int = 90, min_obs: int = 60) -> np.ndarray:
    """``(x - mu) / sd`` against the trailing same-slot distribution.

    ``mat`` is ``(n_sessions, n_cols)``; each COLUMN is one time-of-day slot and is
    normalised against the ``lookback`` strictly prior sessions at that same slot.
    This is `vei_exploration` finding I: a fixed cut on a feature that has a
    time-of-day profile is a clock, not a regime, and dividing by the trailing mean
    fixes location but not scale -- only the z-score fixes both. Fractional
    ``min_obs`` (2/3 of the lookback) keeps the coverage loss uniform across slots.
    """
    out = np.full(mat.shape, np.nan)
    for j in range(mat.shape[1]):
        v = mat[:, j]
        good = np.isfinite(v)
        z = np.where(good, v, 0.0)
        cs = np.concatenate([[0.0], np.cumsum(z)])
        cq = np.concatenate([[0.0], np.cumsum(z * z)])
        cn = np.concatenate([[0.0], np.cumsum(good)])
        idx = np.arange(len(v))
        lo = np.maximum(0, idx - lookback)
        n = cn[idx] - cn[lo]
        s = cs[idx] - cs[lo]
        q = cq[idx] - cq[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            mu = s / n
            var = (q - n * mu * mu) / (n - 1)
            zz = (v - mu) / np.sqrt(var)
        out[:, j] = np.where((n >= min_obs) & (var > 0), zz, np.nan)
    return out


# --------------------------------------------------------------------------- #
# the decision frame
# --------------------------------------------------------------------------- #
def decision_frame(panel: pd.DataFrame, instruments=("GC", "ES", "NQ"),
                   past_wins=(15, 30, 60), horizons=(10, 30, 60),
                   coh_win: int = 60, beta_lb: int = 20,
                   slot_lb: int = 90, period: int = PERIOD) -> pd.DataFrame:
    """One row per (session, 30-minute decision slot) with every study's inputs.

    Columns
    -------
    ``date``, ``mfo``
    ``past_<I>_<W>``      log return of instrument I over ``(m-W, m]``
    ``past_dxy_<W>``      dollar log return over the same window
    ``resid_<I>_<W>``     ``past_<I>_<W> - beta_<I> * past_dxy_<W>`` (causal beta)
    ``factor_<I>_<W>``    ``beta_<I> * past_dxy_<W>`` -- the dollar-explained part;
                          the DEGENERATE control for the decomposition (finding H's
                          "score the bare numerator" discipline: if the factor leg
                          predicts on its own, the residual split is not what matters)
    ``fwd_<I>_<H>``       forward log return over ``(m, m+H]``  (target)
    ``fwd_dxy_<H>``       forward dollar log return            (target)
    ``rv_<I>``            trailing 30-minute realised vol of I (the volatility LEVEL,
                          used as the degenerate regime control)
    ``beta_<I>``          causal dollar beta in force for that session
    ``coh_<I>``           trailing ``coh_win``-minute |corr| of I with the dollar,
                          computed on DOLLAR-FRESH minutes only
    ``cohz_<I>``          its trailing same-slot z-score (the calibrated regime label)
    ``rvz_<I>``           same-slot z-score of ``rv_<I>`` (matched control label)
    ``dxy_fresh``         True when the dollar is un-stale at both window endpoints
    """
    dm = decision_mfos(period)
    sess = sessions_of(panel)
    ld = to_matrix(panel, "log_dxy")
    stale = to_matrix(panel, "stale_dxy").astype(bool)
    rd = minute_returns(ld)
    # a dollar 1-min return is only trustworthy when NEITHER endpoint was carried
    fresh_r = ~(stale | np.roll(stale, 1, axis=1))
    fresh_r[:, 0] = False
    rd_fresh = np.where(fresh_r, rd, np.nan)

    out = {"date": np.repeat(sess.to_numpy(), len(dm)),
           "mfo": np.tile(dm, len(sess))}

    def _emit(name, mat):
        out[name] = mat[:, dm].reshape(-1)

    for W in past_wins:
        _emit(f"past_dxy_{W}", ld - np.concatenate(
            [np.full((ld.shape[0], W), np.nan), ld[:, :-W]], axis=1))
        lag = np.concatenate([np.full((ld.shape[0], 1), np.nan), ld[:, :-1]], axis=1)
        lagW = np.concatenate([np.full((ld.shape[0], W + 1), np.nan),
                               ld[:, :-(W + 1)]], axis=1)
        _emit(f"pastlag_dxy_{W}", lag - lagW)
    for H in horizons:
        _emit(f"fwd_dxy_{H}", np.concatenate(
            [ld[:, H:], np.full((ld.shape[0], H), np.nan)], axis=1) - ld)
    _emit("dxy_stale_now", stale.astype(float))

    for inst in instruments:
        lp = to_matrix(panel, f"lp_{inst}")
        ri = minute_returns(lp)
        beta = causal_beta(ri, rd, lookback=beta_lb)
        out_beta = np.repeat(beta[:, None], RTH_MINUTES, axis=1)
        _emit(f"beta_{inst}", out_beta)

        for W in past_wins:
            pad = np.full((lp.shape[0], W), np.nan)
            pi = lp - np.concatenate([pad, lp[:, :-W]], axis=1)
            pd_ = ld - np.concatenate([pad, ld[:, :-W]], axis=1)
            _emit(f"past_{inst}_{W}", pi)
            _emit(f"factor_{inst}_{W}", out_beta * pd_)
            _emit(f"resid_{inst}_{W}", pi - out_beta * pd_)
            # Shared-endpoint control. `past` ends and `fwd` starts at the SAME close
            # lp[m]. Any measurement error in that one price (bid-ask bounce, a stale
            # or one-tick print) enters `past` with +1 and `fwd` with -1 and therefore
            # induces MECHANICAL negative correlation between them. `pastlag` ends one
            # bar earlier so the two windows share no price at all; a reversal that
            # survives it is a property of the tape, not of the sampling.
            lag = np.concatenate([np.full((lp.shape[0], 1), np.nan), lp[:, :-1]], axis=1)
            lagW = np.concatenate([np.full((lp.shape[0], W + 1), np.nan),
                                   lp[:, :-(W + 1)]], axis=1)
            _emit(f"pastlag_{inst}_{W}", lag - lagW)
        for H in horizons:
            fwd = np.concatenate(
                [lp[:, H:], np.full((lp.shape[0], H), np.nan)], axis=1) - lp
            _emit(f"fwd_{inst}_{H}", fwd)
            # residualised forward return: the target with the dollar leg removed
            fdx = np.concatenate(
                [ld[:, H:], np.full((ld.shape[0], H), np.nan)], axis=1) - ld
            _emit(f"fwdresid_{inst}_{H}", fwd - out_beta * fdx)

        # volatility level (the degenerate regime control) and factor coherence
        cs, cn = _nan_cumsum(ri * ri)
        rv = np.full(lp.shape, np.nan)
        for mm in range(RTH_MINUTES):
            lo = max(0, mm + 1 - 30)
            n = cn[:, mm + 1] - cn[:, lo]
            s = cs[:, mm + 1] - cs[:, lo]
            rv[:, mm] = np.where(n >= 20, np.sqrt(np.maximum(s, 0.0)), np.nan)
        _emit(f"rv_{inst}", rv)
        _emit(f"rvz_{inst}", _slotz_on_dm(rv, dm, slot_lb))

        coh = np.abs(rolling_corr(np.where(fresh_r, ri, np.nan), rd_fresh, coh_win))
        _emit(f"coh_{inst}", coh)
        _emit(f"cohz_{inst}", _slotz_on_dm(coh, dm, slot_lb))

    df = pd.DataFrame(out)
    # endpoint freshness for the widest window actually emitted
    Wmax = max(past_wins)
    ep = np.full(stale.shape, False)
    ep[:, Wmax:] = stale[:, Wmax:] | stale[:, :-Wmax]
    df["dxy_fresh"] = ~ep[:, dm].reshape(-1)
    return df


def overnight_frame(panel: pd.DataFrame, instruments=("GC", "ES", "NQ"),
                    beta_lb: int = 20) -> pd.DataFrame:
    """One row per session: the overnight move, its dollar decomposition, and the
    RTH move that follows.

    ``on_<I>``  = ``lp_I[d, 0] - lp_I[d-1, 389]`` -- the roll-adjusted log change from
    the previous equity close to today's equity open. Because the level is a
    cumulative sum over ALL 24h bars, this is the true overnight change, not a
    same-session artefact, and the roll adjustment means a contract change inside the
    gap does not appear as a move (rule 11).

    ``short_<I>`` = ``beta_I * on_dxy - on_I`` -- the part of the dollar-implied
    overnight repricing that the instrument has NOT yet absorbed. Positive means the
    instrument is "owed" an up-move relative to where the dollar already went.

    ``rth_<I>`` = ``lp_I[d, 389] - lp_I[d, 0]`` -- the target.

    Sessions that do not follow the immediately preceding calendar session in the
    panel are kept, but ``gap_days`` records the calendar distance so a weekend or
    holiday gap can be excluded or examined separately.
    """
    sess = sessions_of(panel)
    ld = to_matrix(panel, "log_dxy")
    rd = minute_returns(ld)
    on_dxy = np.r_[np.nan, ld[1:, 0] - ld[:-1, -1]]
    out = {"date": sess.to_numpy(), "on_dxy": on_dxy,
           "rth_dxy": ld[:, -1] - ld[:, 0],
           "gap_days": np.r_[np.nan, np.diff(sess.to_numpy()).astype("timedelta64[D]")
                             .astype(float)]}
    for inst in instruments:
        lp = to_matrix(panel, f"lp_{inst}")
        beta = causal_beta(minute_returns(lp), rd, lookback=beta_lb)
        on = np.r_[np.nan, lp[1:, 0] - lp[:-1, -1]]
        out[f"beta_{inst}"] = beta
        out[f"on_{inst}"] = on
        out[f"factor_on_{inst}"] = beta * on_dxy
        out[f"short_{inst}"] = beta * on_dxy - on
        out[f"rth_{inst}"] = lp[:, -1] - lp[:, 0]
        # Split the session so the MECHANISM is testable, not just the direction. If
        # the story is "the repricing completes once New York liquidity arrives", the
        # effect must be concentrated in the first hour and largely spent afterwards.
        # An effect spread evenly across the whole session is a different animal.
        out[f"rth60_{inst}"] = lp[:, 60] - lp[:, 0]
        out[f"rthrest_{inst}"] = lp[:, -1] - lp[:, 60]
    return pd.DataFrame(out)


def _slotz_on_dm(mat: np.ndarray, dm: np.ndarray, lookback: int) -> np.ndarray:
    """Same-slot z-score computed on the DECISION columns, scattered back to full width.

    Normalising at the decision slots only is what the label is used at, and it keeps
    the trailing window a same-time-of-day window rather than a same-minute one.
    """
    z = slot_zscore(mat[:, dm], lookback=lookback, min_obs=(2 * lookback) // 3)
    full = np.full(mat.shape, np.nan)
    full[:, dm] = z
    return full
