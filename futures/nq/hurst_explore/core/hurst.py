"""Hurst-exponent estimator panel and synthetic-truth generator.

This module is deliberately estimator-agnostic: it exposes four standard
estimators from three families so that A1 (the measurement-error floor) can ask
whether an *intraday* Hurst estimate is well-determined or whether it is mostly
estimator/sample noise.

Conventions (kept consistent so all four agree on a synthetic fBm of Hurst H):
  * The STRUCTURE-FUNCTION estimator operates on the LEVEL path `logp`
    (log-price).  For fractional Brownian motion,
        E|P(t+tau) - P(t)|^q  ~  tau^(q*H),   so slope(log K_q, log tau) / q = H.
  * R/S and DFA operate on the INCREMENTS `r = diff(logp)` (a fractional
    Gaussian noise).  For fGn, R/S ~ tau^H and the DFA fluctuation F ~ tau^H.
Applying R/S or DFA to the level path instead (an extra integration) would give
H+1; applying the structure function to increments would give H-1.  Keeping the
object explicit per estimator is what makes the panel comparable.

None of the estimators is causal-by-construction here; causality is enforced by
the CALLER (feeding only session-to-date data).  These are pure array ops.

Nothing in this module trades; it is measurement only.
"""
from __future__ import annotations

import numpy as np


# --------------------------------------------------------------------------- #
# lag grids
# --------------------------------------------------------------------------- #
def log_lags(lo: int, hi: int, num: int = 12) -> np.ndarray:
    """Unique, integer, log-spaced lags in [lo, hi] (inclusive)."""
    if hi < lo:
        return np.empty(0, dtype=int)
    raw = np.unique(np.round(np.geomspace(lo, hi, num)).astype(int))
    return raw[(raw >= lo) & (raw <= hi)]


def _loglog_slope(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return np.nan
    return float(np.polyfit(x, y, 1)[0])


# --------------------------------------------------------------------------- #
# 1. Generalized Hurst exponent (structure function) on the LEVEL path
# --------------------------------------------------------------------------- #
def ghe(logp: np.ndarray, lags: np.ndarray, q: float = 1.0) -> float:
    """Generalized Hurst exponent of order q via the structure function.

    K_q(tau) = mean(|logp[t+tau]-logp[t]|^q) ~ tau^(q*H(q)).  Returns H(q).
    For q=1 this reduces to the order-1 GHE used in the noise_vwap Hurst work.
    """
    logp = np.asarray(logp, float)
    n = len(logp)
    lags = np.asarray(lags, int)
    lags = lags[(lags >= 1) & (lags <= n // 2)]
    if len(lags) < 3:
        return np.nan
    xs, ys = [], []
    for tau in lags:
        d = np.abs(logp[tau:] - logp[:-tau])
        m = np.mean(d ** q)
        if m > 0:
            xs.append(np.log(tau))
            ys.append(np.log(m))
    return _loglog_slope(np.asarray(xs), np.asarray(ys)) / q


def ghe_spectrum(logp: np.ndarray, lags: np.ndarray,
                 qs: np.ndarray) -> np.ndarray:
    """H(q) for each q in `qs` (multifractality probe; A4 uses this)."""
    return np.array([ghe(logp, lags, float(q)) for q in qs])


# --------------------------------------------------------------------------- #
# 2. Rescaled range (R/S) on INCREMENTS
# --------------------------------------------------------------------------- #
def rs_hurst(r: np.ndarray, lags: np.ndarray) -> float:
    """Classic rescaled-range Hurst on an increments series.  E[R/S] ~ n^H.

    Vectorized: for each block size the truncated series is reshaped to
    (k, n) and R/S computed along the window axis.
    """
    r = np.asarray(r, float)
    N = len(r)
    lags = np.asarray(lags, int)
    lags = lags[(lags >= 8) & (lags <= N // 2)]
    if len(lags) < 3:
        return np.nan
    xs, ys = [], []
    for n in lags:
        k = N // n
        if k < 1:
            continue
        Z = r[:k * n].reshape(k, n)
        dev = Z - Z.mean(axis=1, keepdims=True)
        cum = np.cumsum(dev, axis=1)
        R = cum.max(axis=1) - cum.min(axis=1)
        S = Z.std(axis=1, ddof=0)
        good = (S > 0) & (R > 0)
        if good.any():
            xs.append(np.log(n))
            ys.append(np.log(np.mean(R[good] / S[good])))
    return _loglog_slope(np.asarray(xs), np.asarray(ys))


# --------------------------------------------------------------------------- #
# 3. Detrended fluctuation analysis (DFA) on INCREMENTS
# --------------------------------------------------------------------------- #
def dfa_hurst(r: np.ndarray, lags: np.ndarray, order: int = 1) -> float:
    """DFA fluctuation exponent alpha (~H for fGn).  Linear detrend by default.

    Integrates the mean-removed increments (recovering ~the level), splits into
    non-overlapping windows of size n, removes a polynomial trend of `order`
    within each window, and fits log F(n) ~ alpha log n.  DFA is the estimator
    most robust to slow nonstationary trends, which real price paths carry.
    """
    r = np.asarray(r, float)
    y = np.cumsum(r - r.mean())
    N = len(y)
    lags = np.asarray(lags, int)
    lags = lags[(lags >= order + 2) & (lags <= N // 2)]
    if len(lags) < 3:
        return np.nan
    xs, ys = [], []
    for n in lags:
        k = N // n
        if k < 1:
            continue
        Y = y[:k * n].reshape(k, n)
        if order == 1:
            # vectorized linear detrend with a centered abscissa
            t = np.arange(n) - (n - 1) / 2.0
            slope = (Y * t).sum(axis=1) / (t * t).sum()
            resid = Y - (Y.mean(axis=1, keepdims=True) + slope[:, None] * t[None, :])
        else:
            idx = np.arange(n)
            resid = np.empty_like(Y)
            for i in range(k):
                coef = np.polyfit(idx, Y[i], order)
                resid[i] = Y[i] - np.polyval(coef, idx)
        F = np.sqrt(np.mean(resid ** 2))
        if F > 0:
            xs.append(np.log(n))
            ys.append(np.log(F))
    return _loglog_slope(np.asarray(xs), np.asarray(ys))


# --------------------------------------------------------------------------- #
# A2: LOCAL structure-function slope across the scale axis
# --------------------------------------------------------------------------- #
def struct_fn(logp: np.ndarray, lags: np.ndarray, q: float = 1.0) -> np.ndarray:
    """Return K_q(tau) = mean(|logp[t+tau]-logp[t]|^q) for each requested lag.

    NaN where the lag is too long for the path.  Feeds the term-structure plot:
    the LOCAL slope of log K_q vs log tau over a sliding tau-window is the
    scale-resolved Hurst exponent H(tau).
    """
    logp = np.asarray(logp, float)
    n = len(logp)
    out = np.full(len(lags), np.nan)
    for i, tau in enumerate(np.asarray(lags, int)):
        if 1 <= tau <= n - 1:
            d = np.abs(logp[tau:] - logp[:-tau])
            out[i] = np.mean(d ** q)
    return out


def local_slope(log_tau: np.ndarray, log_k: np.ndarray,
                win: int = 3) -> np.ndarray:
    """Centered local log-log slope over a window of `win` points each side."""
    m = len(log_tau)
    out = np.full(m, np.nan)
    for i in range(m):
        lo, hi = max(0, i - win), min(m, i + win + 1)
        xs, ys = log_tau[lo:hi], log_k[lo:hi]
        good = np.isfinite(xs) & np.isfinite(ys)
        if good.sum() >= 3:
            out[i] = float(np.polyfit(xs[good], ys[good], 1)[0])
    return out


# --------------------------------------------------------------------------- #
# Synthetic truth: fractional Gaussian noise / fBm (Davies-Harte, exact)
# --------------------------------------------------------------------------- #
def fgn(H: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """Exact fractional Gaussian noise via circulant embedding (Davies-Harte).

    Returns `n` samples.  The scale constant is irrelevant to every estimator
    here (all are log-log SLOPES, invariant to a variance rescale), so this is
    used purely to inject a KNOWN Hurst exponent H into the level path
    `fbm = cumsum(fgn)`.
    """
    if n < 2:
        return rng.standard_normal(max(n, 0))
    k = np.arange(n)
    g = 0.5 * (np.abs(k - 1) ** (2 * H) - 2 * np.abs(k) ** (2 * H)
               + np.abs(k + 1) ** (2 * H))
    g[0] = 1.0
    # circulant first row of length 2(n-1), symmetric
    row = np.concatenate([g, g[-2:0:-1]])
    lam = np.fft.fft(row).real
    lam[lam < 0] = 0.0
    m = len(row)
    w = (rng.standard_normal(m) + 1j * rng.standard_normal(m))
    y = np.fft.fft(np.sqrt(lam) * w).real / np.sqrt(2 * m)
    return y[:n]


def fbm(H: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """Fractional Brownian motion level path of length n (fbm[0] = 0)."""
    return np.concatenate([[0.0], np.cumsum(fgn(H, n - 1, rng))])


# --------------------------------------------------------------------------- #
# convenience: run the whole panel on one path
# --------------------------------------------------------------------------- #
def estimate_panel(logp: np.ndarray, lags: np.ndarray) -> dict:
    """All four estimators on one level path.  Keys: ghe1, ghe2, rs, dfa."""
    r = np.diff(logp)
    return {
        "ghe1": ghe(logp, lags, 1.0),
        "ghe2": ghe(logp, lags, 2.0),
        "rs": rs_hurst(r, lags),
        "dfa": dfa_hurst(r, lags),
    }
