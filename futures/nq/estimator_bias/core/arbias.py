"""Finite-sample bias in persistence estimators, and the diagnostics that read it.

Three families live here, all in service of HYP-0001:

1. **AR(1) estimation and bias correction.** ``ols_ar1`` is the naive estimator;
   ``kendall_correct`` is the analytic repair; ``bootstrap_ar1_correct`` is the
   independent one. Two correctors that must agree, so a bug in one cannot
   masquerade as a finding.

2. **The pooled lag-1 estimator actually used in this workspace.**
   ``futures/nq/vei_exploration/scripts/s1_smoothing.py::persistence_and_whipsaw``
   stacks every within-session consecutive pair across all sessions and takes one
   ``corrcoef``. ``pooled_lag1`` reproduces it exactly. ``pooled_lag1_slot_demeaned``
   removes the per-slot mean first, which separates genuine persistence from a
   shared deterministic time-of-day profile -- these push the statistic in
   OPPOSITE directions and only one of them is small-sample bias.

3. **The expanding-window Hurst gate and the selection-rate diagnostic.** ``ghe1``
   is copied verbatim from ``noise_vwap/scripts/hyp_0017_hurst_filter.py`` (pinned
   by a test that re-reads that file) so the audit measures the deployed estimator,
   not a lookalike. ``per_slot_selection_rate`` / ``selection_rate_cv`` are the
   one-line "is this threshold a clock?" diagnostic that finding I1 of
   ``futures/forex/vwap_exploration`` established, and ``causal_slot_stats`` is the
   same-slot z-score it is measured against.

Nothing here trades. Every function is a measurement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# constants copied from the audited script (pinned by tests/test_core.py)
# --------------------------------------------------------------------------- #
GHE_LAGS = np.array([1, 2, 3, 4, 5, 7, 10, 15, 20])
H_GRID = np.array([0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65])


# --------------------------------------------------------------------------- #
# 1. AR(1): naive estimator and two independent bias correctors
# --------------------------------------------------------------------------- #
def ols_ar1(x: np.ndarray) -> float:
    """OLS slope of x_t on x_{t-1} WITH an intercept (the textbook estimator).

    Biased toward zero for both signs of phi because the lagged regressor shares
    shock history with the target -- the defect this project exists to size.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.nan
    y, l = x[1:], x[:-1]
    ly = l - l.mean()
    den = float(ly @ ly)
    if den <= 0:
        return np.nan
    return float((ly @ (y - y.mean())) / den)


def kendall_bias(phi: float, T: int) -> float:
    """Kendall's leading-order bias of `ols_ar1`: E[phi_hat] - phi ~= -(1+3phi)/T.

    Note it is negative for every phi > -1/3 and, crucially, is a DETERMINISTIC
    function of the sample length. That is what lets a varying window length
    manufacture a gradient in a feature.
    """
    if T <= 0:
        return np.nan
    return -(1.0 + 3.0 * float(phi)) / float(T)


def kendall_correct(phi_hat: float, T: int) -> float:
    """Invert `kendall_bias`: solve phi_c - (1+3*phi_c)/T = phi_hat.

    Closed form ``(phi_hat + 1/T) / (1 - 3/T)``. Clipped to the stationary region.
    """
    if not np.isfinite(phi_hat) or T <= 3:
        return np.nan
    return float(np.clip((phi_hat + 1.0 / T) / (1.0 - 3.0 / T), -0.9999, 0.9999))


def simulate_ar1(phi: float, T: int, rng: np.random.Generator,
                 sigma: float = 1.0, burn: int = 400,
                 draws: int | None = None) -> np.ndarray:
    """Zero-mean stationary AR(1) path(s) of length T (burn-in discarded).

    `draws=None` returns one 1-D path; an integer returns a ``(draws, T)`` batch.
    Built with `scipy.signal.lfilter` so a calibration table over long T stays cheap;
    the burn-in makes the zero initial state irrelevant (0.9**400 ~ 1e-19).
    """
    from scipy.signal import lfilter
    n = T + burn
    k = 1 if draws is None else int(draws)
    e = rng.normal(0.0, sigma, size=(k, n))
    x = lfilter([1.0], [1.0, -float(phi)], e, axis=1)[:, burn:]
    return x[0] if draws is None else x


def ols_ar1_batch(x: np.ndarray) -> np.ndarray:
    """`ols_ar1` applied row-wise to a ``(draws, T)`` batch, without NaN handling."""
    x = np.asarray(x, dtype=float)
    y, l = x[:, 1:], x[:, :-1]
    yc = y - y.mean(axis=1, keepdims=True)
    lc = l - l.mean(axis=1, keepdims=True)
    den = (lc * lc).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, (lc * yc).sum(axis=1) / den, np.nan)


def bootstrap_ar1_correct(x: np.ndarray, rng: np.random.Generator,
                          nboot: int = 400) -> float:
    """Parametric-bootstrap bias correction, independent of Kendall's algebra.

    Fit phi_hat, resimulate `nboot` AR(1) paths of the SAME length at phi_hat,
    measure the estimator's mean displacement there, and subtract it. Deliberately
    a different route to the same repair so the two can be cross-checked.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    T = len(x)
    phi_hat = ols_ar1(x)
    if not np.isfinite(phi_hat) or T < 8:
        return np.nan
    resid = x[1:] - phi_hat * x[:-1]
    sigma = float(resid.std(ddof=1)) or 1.0
    boots = np.array([ols_ar1(simulate_ar1(phi_hat, T, rng, sigma))
                      for _ in range(nboot)], dtype=float)
    bias = float(np.nanmean(boots)) - phi_hat
    return float(np.clip(phi_hat - bias, -0.9999, 0.9999))


# --------------------------------------------------------------------------- #
# 2. the pooled lag-1 estimator this workspace actually ships
# --------------------------------------------------------------------------- #
def _within_group_pairs(df: pd.DataFrame, col: str, group_col: str,
                        order_col: str) -> tuple[np.ndarray, np.ndarray]:
    """Stack (x_k, x_{k+1}) over consecutive in-group readings, groups never joined."""
    a, b = [], []
    for _, g in df.groupby(group_col, sort=False):
        v = g.sort_values(order_col)[col].to_numpy(float)
        if len(v) < 2:
            continue
        x0, x1 = v[:-1], v[1:]
        m = np.isfinite(x0) & np.isfinite(x1)
        a.append(x0[m])
        b.append(x1[m])
    if not a:
        return np.array([]), np.array([])
    return np.concatenate(a), np.concatenate(b)


def pooled_lag1(df: pd.DataFrame, col: str, *, group_col: str = "date",
                order_col: str = "mfo") -> tuple[float, int]:
    """Reproduce ``persistence_and_whipsaw``'s AC1: one corrcoef over pooled pairs.

    Returns ``(ac1, n_pairs)``. The pair count is the effective T for the
    small-sample bias, and it is large here -- which is the point of Cell B.
    """
    x0, x1 = _within_group_pairs(df, col, group_col, order_col)
    if len(x0) < 3:
        return np.nan, len(x0)
    return float(np.corrcoef(x0, x1)[0, 1]), len(x0)


def pooled_lag1_slot_demeaned(df: pd.DataFrame, col: str, *,
                              group_col: str = "date", order_col: str = "mfo",
                              slot_col: str = "mfo") -> tuple[float, int]:
    """`pooled_lag1` after removing each slot's full-sample mean.

    A feature with a deterministic intraday profile makes consecutive readings
    covary for reasons that have nothing to do with memory: both are high simply
    because it is late in the session. Subtracting the per-slot mean removes that
    shared clock and leaves the persistence.

    This is a DIAGNOSTIC DECOMPOSITION, not a causal feature -- it uses the
    full-sample slot mean on purpose, because the question is how much of an
    already-published descriptive statistic is clock.
    """
    d = df.copy()
    d[col] = d[col].astype(float) - d.groupby(slot_col)[col].transform("mean")
    return pooled_lag1(d, col, group_col=group_col, order_col=order_col)


def whipsaw_rate(df: pd.DataFrame, col: str, level: float = 1.0, *,
                 group_col: str = "date", order_col: str = "mfo") -> float:
    """Fraction of consecutive in-group pairs that cross `level` (the VEI metric)."""
    x0, x1 = _within_group_pairs(df, col, group_col, order_col)
    if not len(x0):
        return np.nan
    return float(np.mean((x0 - level) * (x1 - level) < 0))


# --------------------------------------------------------------------------- #
# 3. the expanding-window Hurst gate
# --------------------------------------------------------------------------- #
def ghe1(logp: np.ndarray) -> float:
    """Generalized Hurst exponent, order 1, of a log-price path.

    VERBATIM from ``noise_vwap/scripts/hyp_0017_hurst_filter.py::ghe1`` -- including
    the ``LAGS <= n // 2`` cap, which silently changes the estimator's own lag set
    at short windows (8 of 9 lags at n=30, all 9 from n=40). Pinned by
    ``tests/test_core.py::test_ghe1_constants_still_match_the_audited_script``.
    """
    logp = np.asarray(logp, dtype=float)
    n = len(logp)
    lags = GHE_LAGS[GHE_LAGS <= n // 2]
    if len(lags) < 3:
        return np.nan
    xs, ys = [], []
    for tau in lags:
        d = np.abs(logp[tau:] - logp[:-tau])
        m = d.mean()
        if m > 0:
            xs.append(np.log(tau))
            ys.append(np.log(m))
    if len(xs) < 3:
        return np.nan
    return float(np.polyfit(xs, ys, 1)[0])


def expanding_ghe1(logp: np.ndarray, ends: np.ndarray) -> np.ndarray:
    """`ghe1` of ``logp[:e+1]`` for each end index e -- the deployed gate's feature.

    This is the session-to-date expanding window of
    ``hyp_0017_hurst_filter.py::hurst_features``: at the first 30-minute decision
    the estimator sees 30 bars, at the last it sees 390.
    """
    return np.array([ghe1(logp[: int(e) + 1]) for e in ends], dtype=float)


# --------------------------------------------------------------------------- #
# 4. same-slot normalisation and the selection-rate diagnostic
# --------------------------------------------------------------------------- #
def causal_slot_stats(df: pd.DataFrame, col: str, *, slot_col: str = "mfo",
                      date_col: str = "date", lookback: int = 90,
                      min_obs: int = 45) -> tuple[pd.Series, pd.Series]:
    """Trailing same-slot mean and sd from STRICTLY PRIOR sessions.

    Same semantics as ``vei_exploration/core/analysis.py::causal_slot_stats``; the
    fractional ``min_obs`` is the rule-9a policy (requiring the full lookback
    deletes decisions wherever same-slot history is thin, and that deletion tracks
    time-of-day liquidity). ``sd`` uses ddof=1.
    """
    mu = pd.Series(np.nan, index=df.index, dtype=float)
    sd = pd.Series(np.nan, index=df.index, dtype=float)
    for _, g in df.groupby(slot_col, sort=False):
        g = g.sort_values(date_col)
        v = g[col].to_numpy(float)
        m = np.full(len(v), np.nan)
        s = np.full(len(v), np.nan)
        for i in range(len(v)):
            w = v[max(0, i - lookback):i]
            w = w[np.isfinite(w)]
            if len(w) >= min_obs:
                m[i] = w.mean()
                s[i] = w.std(ddof=1)
        mu.loc[g.index] = m
        sd.loc[g.index] = s
    return mu, sd


def causal_slot_z(df: pd.DataFrame, col: str, **kw) -> pd.Series:
    """``(x - mu) / sd`` against the trailing same-slot distribution."""
    mu, sd = causal_slot_stats(df, col, **kw)
    z = (df[col].astype(float) - mu) / sd.replace(0.0, np.nan)
    return z


def threshold_at_rate(values: np.ndarray, rate: float, *,
                      upper: bool = True) -> float:
    """Global threshold selecting `rate` of finite `values`.

    ``upper=True`` returns t such that ``mean(values >= t) ~= rate``. Matching the
    GLOBAL selection rate before comparing two gates is mandatory here: otherwise
    the comparison is a selectivity dial, not a calibration test.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if not len(v):
        return np.nan
    q = 1.0 - rate if upper else rate
    return float(np.quantile(v, np.clip(q, 0.0, 1.0)))


def per_slot_selection_rate(df: pd.DataFrame, selected: np.ndarray, *,
                            slot_col: str = "mfo",
                            defined: np.ndarray | None = None) -> pd.Series:
    """Fraction of DEFINED decisions selected at each slot.

    `defined` defaults to "the gate returned a finite reading". Dividing by defined
    rather than by all rows keeps a coverage gap from being read as a low
    selection rate.
    """
    d = pd.DataFrame({"slot": df[slot_col].to_numpy(),
                      "sel": np.asarray(selected, dtype=bool)})
    d["ok"] = (np.ones(len(d), dtype=bool) if defined is None
               else np.asarray(defined, dtype=bool))
    d = d[d["ok"]]
    if d.empty:
        return pd.Series(dtype=float)
    return d.groupby("slot")["sel"].mean().sort_index()


def selection_rate_cv(rates: pd.Series) -> float:
    """Coefficient of variation of the per-slot selection rate.

    The workspace's one-line "is this threshold a clock?" number. Calibration from
    ``futures/forex/vwap_exploration`` finding I1: a same-slot z-score scores
    0.060-0.064; RSI's fixed 70/30 cut scored 0.223-0.364 and was ruled a
    time-of-day selector.
    """
    r = pd.Series(rates).astype(float).dropna()
    if len(r) < 2 or r.mean() == 0:
        return np.nan
    return float(r.std(ddof=1) / r.mean())
