"""Rank statistics, cluster-aware uncertainty, and the re-pairing null.

Everything here exists because the panel has 30 rows and nothing like 30
independent observations.  `MGC` is `GC` at 1/10 notional on the same tape,
`MCL` is `CL` likewise, the seven FX contracts are seven views of the dollar, and
`ZT ZF ZN ZB UB` are five points on one curve.  A plain 30-observation
confidence interval on a cross-product Spearman would be badly
anti-conservative, so every uncertainty statement in this project is either
clustered by asset class, computed leave-one-class-out, or read against a
re-pairing null.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks, ties shared (the Spearman convention)."""
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(a.size, dtype=np.float64)
    ranks[order] = np.arange(1, a.size + 1, dtype=np.float64)
    # average over tied groups
    s = a[order]
    i = 0
    while i < s.size:
        j = i
        while j + 1 < s.size and s[j + 1] == s[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = ranks[order[i:j + 1]].mean()
        i = j + 1
    return ranks


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rank correlation over the finite-in-both rows."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    ra, rb = rankdata(a[ok]), rankdata(b[ok])
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den > 0 else float("nan")


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    x, y = a[ok] - a[ok].mean(), b[ok] - b[ok].mean()
    den = np.sqrt((x ** 2).sum() * (y ** 2).sum())
    return float((x * y).sum() / den) if den > 0 else float("nan")


@dataclass(frozen=True)
class Interval:
    point: float
    lo: float
    hi: float
    n: int
    n_clusters: int

    def excludes_zero(self) -> bool:
        return np.isfinite(self.lo) and np.isfinite(self.hi) and (self.lo > 0 or self.hi < 0)

    def __str__(self) -> str:
        return f"{self.point:+.4f} [{self.lo:+.4f}, {self.hi:+.4f}] (n={self.n}, k={self.n_clusters})"


def cluster_bootstrap_spearman(a: np.ndarray, b: np.ndarray, clusters: np.ndarray,
                               draws: int = 5000, seed: int = 0,
                               alpha: float = 0.05) -> Interval:
    """Percentile CI resampling WHOLE CLUSTERS with replacement.

    Resampling clusters (not products) is the point: it lets the interval reflect
    the fact that drawing "metals" twice gives you GC and MGC twice, which is one
    piece of evidence, not two.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    clusters = np.asarray(clusters)
    names = np.unique(clusters)
    idx_by = {c: np.flatnonzero(clusters == c) for c in names}
    rng = np.random.default_rng(seed)
    out = np.empty(draws, dtype=np.float64)
    for d in range(draws):
        pick = rng.choice(names, size=names.size, replace=True)
        rows = np.concatenate([idx_by[c] for c in pick])
        out[d] = spearman(a[rows], b[rows])
    out = out[np.isfinite(out)]
    lo, hi = np.quantile(out, [alpha / 2, 1 - alpha / 2]) if out.size else (np.nan, np.nan)
    return Interval(point=spearman(a, b), lo=float(lo), hi=float(hi),
                    n=int(a.size), n_clusters=int(names.size))


def leave_one_cluster_out(a: np.ndarray, b: np.ndarray, clusters: np.ndarray,
                          ) -> dict[str, float]:
    """Spearman with each asset class dropped in turn.

    With five clusters this is more informative than any interval: it says
    directly whether one asset class is carrying the whole result.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    clusters = np.asarray(clusters)
    return {str(c): spearman(a[clusters != c], b[clusters != c])
            for c in np.unique(clusters)}


def repairing_null_spearman(a: np.ndarray, b: np.ndarray, draws: int = 20000,
                            seed: int = 0) -> tuple[np.ndarray, float]:
    """Null distribution of Spearman under a random re-pairing of the two columns.

    Returns the draws and the fraction of them at or above the real statistic.
    This destroys the product-to-product correspondence while preserving each
    column's own marginal distribution -- the rule-18 control for "is the
    predicted number actually about THIS product".
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    real = spearman(a, b)
    rng = np.random.default_rng(seed)
    out = np.empty(draws, dtype=np.float64)
    for d in range(draws):
        out[d] = spearman(a, rng.permutation(b))
    return out, float((out >= real).mean())


def pooled_rank_spearman(pred: np.ndarray, real: np.ndarray, group: np.ndarray) -> float:
    """Spearman after converting both columns to WITHIN-GROUP fractional ranks.

    Pools several cross-sections (one per era transition, or per year) without
    letting a group whose returns were large in absolute terms dominate.  Only
    the within-group ordering carries information about a RANKING screen.
    """
    pred, real, group = (np.asarray(pred, dtype=np.float64),
                         np.asarray(real, dtype=np.float64), np.asarray(group))
    rp, rr = np.full(pred.size, np.nan), np.full(real.size, np.nan)
    for g in np.unique(group):
        m = group == g
        ok = m & np.isfinite(pred) & np.isfinite(real)
        if ok.sum() < 3:
            continue
        rp[ok] = rankdata(pred[ok]) / (ok.sum() + 1)
        rr[ok] = rankdata(real[ok]) / (ok.sum() + 1)
    return spearman(rp, rr)


def cluster_bootstrap_pooled_diff(pred_a: np.ndarray, pred_b: np.ndarray,
                                  real: np.ndarray, group: np.ndarray,
                                  cluster: np.ndarray, unit: np.ndarray,
                                  draws: int = 5000, seed: int = 0,
                                  alpha: float = 0.05) -> tuple[Interval, Interval, Interval]:
    """CIs for pooled Spearman of two predictors and for their DIFFERENCE.

    Bootstrapping the DIFFERENCE rather than comparing two intervals is the
    lesson carried from `futures/forex/vwap_exploration` EXP-0005: two wide,
    overlapping intervals can still have a difference whose interval is tight,
    and "does the theory beat the no-theory benchmark" is a question about the
    difference.

    Resampling is over CLUSTERS of `unit` (products), so a product's several
    group rows move together and the five asset classes are the sampling unit.
    """
    pred_a, pred_b, real = (np.asarray(pred_a, dtype=np.float64),
                            np.asarray(pred_b, dtype=np.float64),
                            np.asarray(real, dtype=np.float64))
    group, cluster, unit = np.asarray(group), np.asarray(cluster), np.asarray(unit)
    names = np.unique(cluster)
    rows_by = {c: np.flatnonzero(cluster == c) for c in names}
    rng = np.random.default_rng(seed)
    a = np.empty(draws)
    b = np.empty(draws)
    for d in range(draws):
        pick = rng.choice(names, size=names.size, replace=True)
        rows = np.concatenate([rows_by[c] for c in pick])
        # Re-label the group so duplicated clusters do not collide within a
        # cross-section: each draw of a cluster is ranked in its own copy.
        rep = np.concatenate([np.full(rows_by[c].size, i) for i, c in enumerate(pick)])
        g2 = np.char.add(group[rows].astype(str), rep.astype(str))
        a[d] = pooled_rank_spearman(pred_a[rows], real[rows], g2)
        b[d] = pooled_rank_spearman(pred_b[rows], real[rows], g2)
    diff = a - b
    n, k = int(pred_a.size), int(names.size)

    def _iv(draws_arr, point):
        f = draws_arr[np.isfinite(draws_arr)]
        lo, hi = (np.quantile(f, [alpha / 2, 1 - alpha / 2]) if f.size
                  else (np.nan, np.nan))
        return Interval(point=point, lo=float(lo), hi=float(hi), n=n, n_clusters=k)

    pa = pooled_rank_spearman(pred_a, real, group)
    pb = pooled_rank_spearman(pred_b, real, group)
    return _iv(a, pa), _iv(b, pb), _iv(diff, pa - pb)


def kendall_tau_pairs(order: list[str], values: dict[str, float]) -> tuple[int, int, list[str]]:
    """How many adjacent pairs of a DECLARED ordering the values reproduce.

    `order` is a list of product names, best first.  Returns
    (pairs satisfied, pairs testable, the pairs that failed).  Used for the K3
    ordering check, where the claim is about a specific published ladder rather
    than about a correlation.
    """
    ok, tot, bad = 0, 0, []
    for i in range(len(order) - 1):
        hi, lo = order[i], order[i + 1]
        if hi not in values or lo not in values:
            continue
        if not (np.isfinite(values[hi]) and np.isfinite(values[lo])):
            continue
        tot += 1
        if values[hi] > values[lo]:
            ok += 1
        else:
            bad.append(f"{hi}<={lo}")
    return ok, tot, bad
