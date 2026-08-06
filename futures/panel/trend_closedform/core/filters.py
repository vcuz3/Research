"""Linear trend filters, expressed as weights on PAST RETURNS.

The closed form in HYP-0001 is a statement about a signal of the form

    S_t = sum_{m>=1} w_m x_{t+1-m}

i.e. a weighted sum of past returns.  A single exponential filter is already in
that form.  An EWMA **crossover** -- the benchmark the source item asks for -- is
naturally written as a filter of past *prices*, so it has to be converted.

The conversion is exact, not an approximation.  If

    S_t = sum_{m>=0} c_m P_{t-m}        with   sum_m c_m = 0

(zero DC gain, which every crossover has), then substituting
``P_{t-m} = P_t - sum_{k=1..m} r_{t-k+1}`` gives

    S_t = -sum_{k>=1} ( sum_{m>=k} c_m ) r_{t-k+1}

so ``w_k = -sum_{m>=k} c_m``: the return-weights are minus the reversed cumulative
sum of the price-weights.  `crossover_kernel` returns that, and
`tests/test_core.py` pins it by applying both forms to the same random price path
and requiring identical output.

Truncation
----------
Every kernel is returned as an explicit finite vector of length `M`.  The SAME
vector is used to build the realised signal and to compute the predicted score,
so the truncation cannot introduce a mismatch between the two sides -- which is
what makes the in-sample construction check in HYP-0001 control 1 a genuine
identity test rather than an approximation test.
"""
from __future__ import annotations

import numpy as np


def span_to_alpha(span: float) -> float:
    """pandas/RiskMetrics convention: alpha = 2/(span+1)."""
    if span <= 0:
        raise ValueError(f"span must be positive, got {span}")
    return 2.0 / (span + 1.0)


def default_length(span: float, cap: int = 512) -> int:
    """Kernel length: 5 spans of memory, capped.

    At 5 spans an exponential filter retains ``(1-alpha)^(5*span)`` ~ e^-10 of its
    weight, and the residual tail multiplies autocorrelation estimates that are
    themselves noise at those lags.  The cap keeps the longest span from reaching
    lags where rho is estimated from too few overlapping pairs.
    """
    return int(min(cap, max(8, round(5 * span))))


def ewma_kernel(span: float, length: int | None = None) -> np.ndarray:
    """`w_m = nu^m` for m = 1..M, with `nu = 1 - alpha`.

    This is the article's own filter.  Note the leading `nu`, not `1`: the
    closed form is written as ``sum_{m>=0} nu^m rho(m) - 1``, whose m-th term for
    m >= 1 is ``nu^m rho(m)``, so the weight on a return `m` periods back is
    `nu^m`.  Any overall scale is absorbed by the position normaliser, so the
    convention only has to be consistent between the two sides -- and it is,
    because both read this vector.
    """
    if length is None:
        length = default_length(span)
    nu = 1.0 - span_to_alpha(span)
    m = np.arange(1, length + 1, dtype=np.float64)
    return nu ** m


def _ema_price_weights(span: float, length: int) -> np.ndarray:
    """`c_m` for a recursive EMA of prices: `alpha (1-alpha)^m`, m = 0..M-1."""
    alpha = span_to_alpha(span)
    m = np.arange(length, dtype=np.float64)
    return alpha * (1.0 - alpha) ** m


def crossover_kernel(fast: float, slow: float, length: int | None = None) -> np.ndarray:
    """Return-weights of `EMA_fast(P) - EMA_slow(P)`.

    The price-weights are renormalised to sum to zero before conversion.  A
    truncated EMA's weights sum to ``1 - (1-alpha)^M`` rather than 1, and the
    slow leg loses more mass than the fast one, so an untruncated-looking
    difference would carry a small spurious DC term -- i.e. a level, not a trend.
    Renormalising each leg to unit mass removes it exactly.
    """
    if slow <= fast:
        raise ValueError(f"slow span must exceed fast span, got {fast}/{slow}")
    if length is None:
        length = default_length(slow)
    cf = _ema_price_weights(fast, length)
    cs = _ema_price_weights(slow, length)
    c = cf / cf.sum() - cs / cs.sum()
    # w_k = -sum_{m>=k} c_m, for k = 1..M-1 (c has index 0..M-1)
    tail = np.cumsum(c[::-1])[::-1]
    return -tail[1:]


def apply_kernel(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """`S_t = sum_{m=1..M} w_m x_{t+1-m}`, i.e. a strictly CAUSAL convolution.

    Indexing, which is the whole point: `w[0]` multiplies `x_t`, the MOST RECENT
    observed return, not `x_{t-1}`.  That is what makes `E[S_t x_{t+1}]` pick up
    `gamma(m)` at lag exactly `m`, as the closed form requires.  `x_t` is
    observable at the close of bar `t` (it is `dp_t` over a scale that ended at
    `t-1`), so a signal formed at the close of bar `t` may use it; the execution
    lag, not the filter, is what keeps the rule attainable.

    `x` may contain NaN (a dropped roll return).  Those are treated as zero
    inside the filter: the return genuinely was not observable, so the filter
    carries no information about it.  The count of such substitutions is reported
    by the caller rather than hidden.

    The first `M-1` outputs are NaN, because the filter is not fully populated
    there and a partially-populated filter is a DIFFERENT filter with a different
    predicted score.
    """
    x = np.asarray(x, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    xz = np.where(np.isfinite(x), x, 0.0)
    M = w.size
    # np.convolve(xz, w)[k] = sum_j xz[j] w[k-j], so with w indexed from 0 this
    # is sum_{i>=0} w[i] x[k-i] = sum_{m>=1} w_m x[k+1-m].
    full = np.convolve(xz, w)[: xz.size]
    full[: M - 1] = np.nan
    return full


def position_scale(w: np.ndarray) -> float:
    """Normaliser making the position unit-variance for white unit-variance `x`.

    `sd(S) = sqrt(sum_m w_m^2)` when `x` is white with unit variance.  Dividing
    by it puts every product and every span on the same risk scale, so a realised
    mean P&L reads directly as a per-period Sharpe-like number.  It is an
    ANALYTIC constant of the kernel, identical across products -- it cannot
    reorder the panel, which is why it is safe to apply before a rank statistic.
    """
    return float(np.sqrt(np.sum(np.asarray(w, dtype=np.float64) ** 2)))
