"""The predicted side: autocorrelations, the drift term, and PHI.

PHI is the article's closed form, generalised from the single exponential filter
to an arbitrary return-weight kernel `w` and stated for an execution lag `L`:

    PHI(w, L) = sum_{m>=1} w_m rho(m + L)  +  SR^2 * sum_{m>=1} w_m

with `rho` the autocorrelation of the risk-unit return series and
`SR = mean(x) / sd(x)` its per-period drift Sharpe.  `L = 0` is the article's own
(unattainable) same-bar version; `L = 1` is the executable one, in which the
signal formed at the close of bar `t` is not booked against a return until bar
`t+2`, so every lag in the sum moves out by one.

The predicted per-period P&L, on the engine's scale, is
``Var(x) * PHI / position_scale(w)``.

Two estimators, and the difference matters
------------------------------------------
`moments` is the ordinary pairwise-complete autocorrelation estimator.  It is
what belongs in a report describing a product's tape.

`booked_moments` is the one the machinery uses.  The engine computes
``mean_t( S_t x_{t+1+L} )`` over the rows it can book, and expanding `S_t` gives
``sum_m w_m * mean_t( x[t+1-m] x[t+1+L] )`` -- raw cross moments **at a specific
alignment, over exactly that row set**.  The ordinary estimator averages each lag
over its own, larger, lag-dependent row set, so the two differ by edge effects and
by wherever a roll removed a row.  Using the ordinary estimator would leave a
residual between predicted and realised that is indistinguishable from a real
discrepancy -- which would destroy the only check (HYP-0001 control 1) that tells
us the implementation is right.  `booked_moments` makes the in-sample idealised
arm an exact identity, so any departure from it is a genuine finding.

The decomposition into an autocorrelation term and a drift term is taken on the
same row set: with ``A_m = mean_t( x[t+1-m] x[t+1+L] )``, ``mu`` and ``var`` the
grand mean and variance over the rows touched,

    rho_eff(m) = (A_m - mu^2) / var
    PHI        = sum_m w_m rho_eff(m)  +  (mu^2/var) * sum_m w_m

which reproduces ``sum_m w_m A_m / var`` identically, so the two terms are a true
partition rather than an approximation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Moments:
    """Second-moment summary of one risk-unit return series."""
    n: int                      # rows used
    mean: float                 # mean(x)
    var: float                  # Var(x) = g(0)
    sr: float                   # mean / sd  (per period)
    rho: np.ndarray             # rho[k] for k = 0..maxlag, rho[0] == 1
    n_pairs: np.ndarray         # overlapping pairs behind each rho[k]


def moments(x: np.ndarray, maxlag: int, valid: np.ndarray | None = None) -> Moments:
    """Ordinary pairwise-complete autocorrelations of `x` up to `maxlag`.

    Descriptive.  A lagged pair contributes only when BOTH members are finite and
    valid, so a dropped roll return removes the pairs that straddle it rather than
    silently zeroing them.
    """
    x = np.asarray(x, dtype=np.float64)
    ok = np.isfinite(x)
    if valid is not None:
        ok &= np.asarray(valid, dtype=bool)
    xz = np.where(ok, x, 0.0)
    n = int(ok.sum())
    if n < 2:
        raise ValueError("fewer than 2 usable observations")
    mu = float(xz.sum() / n)
    var = float((xz ** 2).sum() / n - mu ** 2)
    if not np.isfinite(var) or var <= 0:
        raise ValueError("non-positive variance")

    rho = np.empty(maxlag + 1, dtype=np.float64)
    npairs = np.empty(maxlag + 1, dtype=np.int64)
    for k in range(maxlag + 1):
        if k == 0:
            pair_ok, prod = ok, xz * xz
        else:
            pair_ok, prod = ok[:-k] & ok[k:], xz[:-k] * xz[k:]
        m = int(pair_ok.sum())
        npairs[k] = m
        rho[k] = ((prod[pair_ok].sum() / m) - mu ** 2) / var if m > 0 else np.nan
    return Moments(n=n, mean=mu, var=var, sr=mu / np.sqrt(var), rho=rho, n_pairs=npairs)


@dataclass(frozen=True)
class BookedMoments:
    """Raw cross moments at exactly the alignments and rows the engine books."""
    n: int                      # booked rows
    maxlag: int                 # kernel length M
    lag: int                    # execution lag L
    mean: float                 # grand mean of x over rows touched
    var: float                  # grand variance over rows touched
    sr: float                   # mean / sd
    A: np.ndarray               # A[m-1] = mean_t( x[t+1-m] * x[t+1+L] ), m = 1..M
    rho_eff: np.ndarray         # (A - mean^2) / var


def booked_moments(x: np.ndarray, maxlag: int, lag: int, ok: np.ndarray) -> BookedMoments:
    """Cross moments over the engine's booked rows.

    A roll return (NaN in `x`) is zeroed here exactly as `apply_kernel` zeroes it,
    so the identity with the engine holds through rolls too.
    """
    x = np.asarray(x, dtype=np.float64)
    ok = np.asarray(ok, dtype=bool)
    xz = np.where(np.isfinite(x), x, 0.0)
    n = int(ok.sum())
    if n < 2:
        raise ValueError("fewer than 2 booked rows")
    idx = np.flatnonzero(ok)

    # Rows the statistic actually touches: every x[t+1-m] for m = 1..M and the
    # target x[t+1+L].  The grand mean/variance are taken over that union so the
    # drift term refers to the same sample as the autocorrelation term.
    touched = np.zeros(x.size, dtype=bool)
    touched[np.clip(idx + 1 + lag, 0, x.size - 1)] = True
    for m in range(1, maxlag + 1):
        j = idx + 1 - m
        touched[j[j >= 0]] = True
    touched &= np.isfinite(x)
    mu = float(xz[touched].mean())
    var = float(xz[touched].var(ddof=0))
    if not np.isfinite(var) or var <= 0:
        raise ValueError("non-positive variance")

    tgt = xz[idx + 1 + lag]
    A = np.empty(maxlag, dtype=np.float64)
    for m in range(1, maxlag + 1):
        j = idx + 1 - m
        src = np.where(j >= 0, xz[np.clip(j, 0, x.size - 1)], 0.0)
        A[m - 1] = float((src * tgt).mean())
    return BookedMoments(n=n, maxlag=maxlag, lag=lag, mean=mu, var=var,
                         sr=mu / np.sqrt(var), A=A, rho_eff=(A - mu ** 2) / var)


def phi(w: np.ndarray, mom: BookedMoments,
        include_drift: bool = True, include_autocorr: bool = True) -> float:
    """PHI from booked moments. Set either flag False to score a term alone.

    `include_autocorr=False, include_drift=True` is the drift-screen control:
    what the formula predicts if every autocorrelation were exactly zero.  If
    that alone carries the cross-product ranking, the headline claim ("trend P&L
    is a function of autocorrelation") is withdrawn even when PHI itself passes.
    """
    w = np.asarray(w, dtype=np.float64)
    if w.size != mom.maxlag:
        raise ValueError(f"kernel length {w.size} != moments maxlag {mom.maxlag}")
    total = 0.0
    if include_autocorr:
        total += float(np.dot(w, mom.rho_eff))
    if include_drift:
        total += float(mom.sr ** 2 * w.sum())
    return total


def predicted_pnl(w: np.ndarray, mom: BookedMoments, scale: float | None = None,
                  **kw) -> float:
    """PHI in the engine's units: mean P&L per period per unit risk."""
    from .filters import position_scale
    if scale is None:
        scale = position_scale(w)
    return mom.var * phi(w, mom, **kw) / scale


def phi_from_rho(w: np.ndarray, rho: np.ndarray, sr: float, lag: int = 0) -> float:
    """PHI from an ORDINARY autocorrelation estimate -- the out-of-sample form.

    The booked-moment version is an in-sample identity by construction and so
    cannot be used to predict a different era.  When PHI is estimated on era `k`
    to predict era `k+1`, this is the estimator: the ordinary `rho` of era `k`,
    read at the lags the kernel needs.
    """
    w = np.asarray(w, dtype=np.float64)
    lags = np.arange(1, w.size + 1) + lag
    if rho.size <= lags[-1]:
        raise ValueError(f"need rho up to lag {lags[-1]}, have {rho.size - 1}")
    return float(np.nansum(w * rho[lags]) + sr ** 2 * w.sum())


def turnover_closed_form(span: float) -> float:
    """`E|dp| = (2/sqrt(pi)) * sqrt(1-nu)` per period for a unit-variance position.

    The article's `E[a U_t] = (2a/sqrt(pi)) sigma_target sqrt(1-nu)` at
    `sigma_target = 1`.  It follows from `E|z| = sqrt(2/pi) sd(z)` for a mean-zero
    Gaussian with `Var(p_t - p_{t-1}) = 2(1-nu)` when `corr(p_t,p_{t-1}) = nu` and
    `sd(p) = 1`.

    The point of carrying it: it depends only on the filter span, never on the
    market.  So the entire cross-product cost differential enters through the
    product's own cost-to-volatility ratio, not through its turnover -- a
    falsifiable claim, checked against the engine's measured turnover.
    """
    from .filters import span_to_alpha
    nu = 1.0 - span_to_alpha(span)
    return 2.0 / np.sqrt(np.pi) * np.sqrt(1.0 - nu)
