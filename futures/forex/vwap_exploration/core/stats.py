"""Estimands and inference.

Two hard rules from this workspace are wired into the API rather than left to the
caller's discipline:

1. **Report the MEAN and the RANK together.**  `ic_and_mean` always returns both a
   Spearman rank IC and a quintile mean spread, because they can give OPPOSITE
   readings on the same rows: on GC a rank IC of -0.036 (CI excluding zero) sat on
   a mean spread of zero, while ES/NQ had rank IC ~0 with real positive mean
   spreads (LEARNINGS 2026-07-31a).  Equity/FX intraday continuation lives in the
   TAILS, which a rank statistic cannot see.

2. **Never session-average a per-signal effect.**  `cluster_t` is the per-signal
   mean with a session cluster-robust SE.  Averaging signals within a session and
   then averaging sessions can INVERT the sign when the signal count is endogenous
   to the outcome, which it always is for a threshold-crossing rule
   (LEARNINGS 2026-08-01).  `mean_count_corr` is the one-line detector for that
   condition and is reported alongside.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# per-signal mean with session-clustered inference
# --------------------------------------------------------------------------- #
def cluster_t(x: np.ndarray, block: np.ndarray) -> tuple[float, float, float, int]:
    """Per-signal mean of `x` with a `block`-cluster-robust SE.

    Var(mean) = (1/N^2) * sum_b ( sum_{i in b} (x_i - xbar) )^2

    Returns (mean, se, t, n).
    """
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    x, block = x[ok], np.asarray(block)[ok]
    n = x.size
    if n < 2:
        return (np.nan, np.nan, np.nan, n)
    xbar = x.mean()
    d = x - xbar
    s = pd.Series(d).groupby(np.asarray(block)).sum().to_numpy()
    var = (s ** 2).sum() / n ** 2
    se = float(np.sqrt(var))
    t = float(xbar / se) if se > 0 else np.nan
    return (float(xbar), se, t, n)


def mean_count_corr(x: np.ndarray, block: np.ndarray) -> float:
    """corr(block mean, block count) -- the endogenous-signal-count detector.

    A materially non-zero value means the per-signal and block-averaged estimands
    are measuring different things and the block-averaged one is not causally
    implementable.
    """
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    g = pd.DataFrame({"x": x[ok], "b": np.asarray(block)[ok]}).groupby("b")["x"]
    m, c = g.mean().to_numpy(), g.size().to_numpy()
    if m.size < 3:
        return np.nan
    return float(np.corrcoef(m, c)[0, 1])


def block_mean_t(x: np.ndarray, block: np.ndarray) -> tuple[float, float, int]:
    """The INVALID-when-count-is-endogenous estimand, reported only for contrast."""
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    g = pd.DataFrame({"x": x[ok], "b": np.asarray(block)[ok]}).groupby("b")["x"].mean()
    m = g.to_numpy()
    if m.size < 3:
        return (np.nan, np.nan, m.size)
    se = m.std(ddof=1) / np.sqrt(m.size)
    return (float(m.mean()), float(m.mean() / se) if se > 0 else np.nan, m.size)


# --------------------------------------------------------------------------- #
# rank and mean views of the same relationship
# --------------------------------------------------------------------------- #
def spearman(x: np.ndarray, y: np.ndarray) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return np.nan
    rx = pd.Series(x[ok]).rank().to_numpy()
    ry = pd.Series(y[ok]).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def quantile_spread(x: np.ndarray, y: np.ndarray, q: int = 5) -> tuple[float, np.ndarray]:
    """Mean of `y` in the top vs bottom `q`-tile of `x`, plus the full profile."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 10 * q:
        return (np.nan, np.full(q, np.nan))
    edges = np.quantile(x, np.linspace(0, 1, q + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    idx = np.clip(np.searchsorted(edges, x, side="right") - 1, 0, q - 1)
    prof = np.array([y[idx == i].mean() if (idx == i).any() else np.nan
                     for i in range(q)])
    return (float(prof[-1] - prof[0]), prof)


def block_bootstrap(df: pd.DataFrame, cols: list[str], stat, rng,
                    nboot: int = 400, block_col: str = "sdate") -> np.ndarray:
    """Resample whole `block_col` groups with replacement; return `nboot` stats."""
    keys, inv = np.unique(df[block_col].to_numpy(), return_inverse=True)
    order = np.argsort(inv, kind="mergesort")
    inv_sorted = inv[order]
    starts = np.r_[0, np.flatnonzero(np.diff(inv_sorted)) + 1, len(inv_sorted)]
    slices = [order[starts[i]:starts[i + 1]] for i in range(len(keys))]
    arrs = [df[c].to_numpy() for c in cols]
    out = np.empty(nboot)
    nb = len(slices)
    for i in range(nboot):
        pick = rng.integers(0, nb, nb)
        idx = np.concatenate([slices[p] for p in pick])
        out[i] = stat(*[a[idx] for a in arrs])
    return out


def ci(samples: np.ndarray, lo: float = 2.5, hi: float = 97.5) -> tuple[float, float]:
    s = np.asarray(samples, float)
    s = s[np.isfinite(s)]
    if s.size < 10:
        return (np.nan, np.nan)
    return (float(np.percentile(s, lo)), float(np.percentile(s, hi)))


# --------------------------------------------------------------------------- #
# stratified (confounder-matched) contrasts
# --------------------------------------------------------------------------- #
def quantile_bins(x: np.ndarray, nbins: int,
                  edges: np.ndarray | None = None
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Assign each finite `x` to one of `nbins` sample-quantile strata.

    Returns `(bin_index, edges)` with `-1` where `x` is not finite.  Pass `edges`
    to reuse a fixed set of cut points (needed so a bootstrap resamples the DATA
    and not the binning).
    """
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    if edges is None:
        edges = np.quantile(x[ok], np.linspace(0, 1, nbins + 1))
        edges[0], edges[-1] = -np.inf, np.inf
    b = np.full(x.shape, -1, dtype=int)
    b[ok] = np.clip(np.searchsorted(edges, x[ok], side="right") - 1, 0, nbins - 1)
    return b, edges


def stratified_contrast(pnl: np.ndarray, group: np.ndarray, bins: np.ndarray,
                        a, b, *, cov: np.ndarray | None = None,
                        min_cell: int = 30) -> dict:
    """Contrast mean(`pnl`) between `group==a` and `group==b`, within strata.

    This is the LEARNINGS 2026-07-31c control.  A split that is matched on one
    label can still inherit a gradient in a confounder; comparing the two cells
    only WITHIN strata of that confounder removes it.

        C_adj = sum_q w_q * (mean[a,q] - mean[b,q]),
        w_q  proportional to  n[a,q]*n[b,q] / (n[a,q]+n[b,q])

    The harmonic weight is deliberate: it is zero when either cell of a stratum
    is empty, so the estimate lives on COMMON SUPPORT and never extrapolates.  It
    also makes `n_eff = sum_q w_q` interpretable — under proportional support it
    equals the pooled harmonic count exactly, so any shortfall measures how
    disjoint the two cells' confounder distributions are.  A collapse in `C_adj`
    is only attributable to the confounder if `n_eff` held up and the cells'
    `cov` ratio moved toward 1; otherwise the split was merely weakened.

    `cov` (optional) is the confounder itself; its per-cell means are returned so
    the caller can report that ratio before and after.
    """
    pnl = np.asarray(pnl, float)
    group = np.asarray(group)
    bins = np.asarray(bins, int)
    ok = np.isfinite(pnl) & (bins >= 0)
    if cov is not None:
        cov = np.asarray(cov, float)
        ok &= np.isfinite(cov)
    pnl, group, bins = pnl[ok], group[ok], bins[ok]
    covv = cov[ok] if cov is not None else None

    ia, ib = (group == a), (group == b)
    raw = (float(pnl[ia].mean()) - float(pnl[ib].mean())
           if ia.any() and ib.any() else np.nan)
    na, nb = int(ia.sum()), int(ib.sum())
    n_harm = na * nb / (na + nb) if (na + nb) else 0.0
    cov_a = float(covv[ia].mean()) if covv is not None and ia.any() else np.nan
    cov_b = float(covv[ib].mean()) if covv is not None and ib.any() else np.nan

    rows, wsum, num, cwa, cwb = [], 0.0, 0.0, 0.0, 0.0
    for q in np.unique(bins):
        qa, qb = ia & (bins == q), ib & (bins == q)
        nqa, nqb = int(qa.sum()), int(qb.sum())
        if nqa < min_cell or nqb < min_cell:
            w = 0.0
        else:
            w = nqa * nqb / (nqa + nqb)
        ma = float(pnl[qa].mean()) if nqa else np.nan
        mb = float(pnl[qb].mean()) if nqb else np.nan
        ca = float(covv[qa].mean()) if covv is not None and nqa else np.nan
        cb = float(covv[qb].mean()) if covv is not None and nqb else np.nan
        rows.append(dict(q=int(q), n_a=nqa, n_b=nqb, mean_a=ma, mean_b=mb,
                         cov_a=ca, cov_b=cb, w=w))
        if w > 0:
            wsum += w
            num += w * (ma - mb)
            if covv is not None:
                cwa += w * ca
                cwb += w * cb
    adj = num / wsum if wsum > 0 else np.nan
    return dict(raw=raw, adj=adj, n_a=na, n_b=nb, n_harm=n_harm, n_eff=wsum,
                retention=(wsum / n_harm if n_harm > 0 else np.nan),
                cov_a=cov_a, cov_b=cov_b,
                cov_ratio_raw=(cov_a / cov_b if cov_b else np.nan),
                cov_ratio_adj=((cwa / wsum) / (cwb / wsum)
                               if (wsum > 0 and cwb > 0) else np.nan),
                rows=rows)


# --------------------------------------------------------------------------- #
# partialling
# --------------------------------------------------------------------------- #
def _resid_on(a: np.ndarray, z: np.ndarray) -> np.ndarray:
    z = np.column_stack([np.ones_like(z), z])
    beta, *_ = np.linalg.lstsq(z, a, rcond=None)
    return a - z @ beta


def partial_spearman(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    """Spearman of x and y after removing the LINEAR-IN-RANKS effect of z."""
    x, y, z = (np.asarray(v, float) for v in (x, y, z))
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if ok.sum() < 20:
        return np.nan
    rx = pd.Series(x[ok]).rank().to_numpy()
    ry = pd.Series(y[ok]).rank().to_numpy()
    rz = pd.Series(z[ok]).rank().to_numpy()
    ex, ey = _resid_on(rx, rz), _resid_on(ry, rz)
    return float(np.corrcoef(ex, ey)[0, 1])
