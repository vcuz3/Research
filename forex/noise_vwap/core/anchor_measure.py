"""
HYP-0003 / EXP-0003 — measurement layer for the anchor sweep.

Signal construction, the exit-neutral forward-return diagnostic, fire-rate
matching and cluster-robust inference. Deliberately mirrors
`scripts/entry_information.py` (EXP-0002) so the anchor sweep and the frozen
result are produced by the same measurement, with two protocol upgrades that
prior workspace failures require:

MATCHED FIRE RATE (LEARNINGS section 1)
    Different anchors produce different sigma and therefore different selection
    rates, and any threshold whose rate varies is a selector for whatever drives
    the rate. The band multiplier `k` is chosen off a FINE GRID as the grid point
    whose fire rate is closest to a common target. It is never interpolated:
    `np.interp` clamps outside its range and silently turns a rate-match into an
    extrapolation against the shallowest cell.

PAIRED 1-BAR EMBARGO (LEARNINGS section 6, CONFIRMED on this exact archive)
    `open[t+1] == close[t]` on 99.99998% of contiguous minutes here, so filling
    at the next bar's open does NOT separate the decision window from the forward
    window and manufactures reversion. The primary arm fills at `open[t+2]`. The
    two arms run on the IDENTICAL signal set (paired), not on two separately
    filtered samples.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import anchors as A

K_GRID = np.round(np.arange(0.40, 3.0001, 0.02), 4)


def dense_by_minute(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, int]:
    """Minute-indexed open/close arrays for O(1) forward lookups (NaN where absent)."""
    lo = int(df["utc_min"].min())
    hi = int(df["utc_min"].max())
    n = hi - lo + 1
    o = np.full(n, np.nan)
    c = np.full(n, np.nan)
    idx = df["utc_min"].to_numpy() - lo
    o[idx] = df["open"].to_numpy()
    c[idx] = df["close"].to_numpy()
    return o, c, lo


def signal_ratios(dec: pd.DataFrame, ref: pd.DataFrame, sigma: pd.DataFrame,
                  gate: bool = True) -> pd.DataFrame:
    """Per-decision scale-free break depth on each side, plus the TWAP gate.

        long  iff close > max(anchor_open, prior_close) * (1 + k*sigma)  [and gate]
        short iff close < min(anchor_open, prior_close) * (1 - k*sigma)  [and gate]

    Rearranged so the threshold `k` is isolated:
        r_long  = (close/ref_hi - 1) / sigma      -> long  iff r_long  > k
        r_short = (1 - close/ref_lo) / sigma      -> short iff r_short > k

    This makes the whole k-grid a comparison against two precomputed columns, so
    fire-rate matching costs one vectorised pass instead of a re-run per k.
    `bw` is the k=1 band half-width in price units and is the unit-free
    normaliser; it does NOT depend on k, so rate-matching cannot move the scale
    the effect size is reported in.
    """
    m = dec.merge(sigma, on=["date", "mfo"], how="inner")
    m = m.merge(ref[["anchor_open", "prior_close"]], left_on="date",
                right_index=True, how="left")
    m = m.dropna(subset=["sigma", "anchor_open", "prior_close"])
    m = m[m["sigma"] > 0]

    ref_hi = np.maximum(m["anchor_open"].to_numpy(), m["prior_close"].to_numpy())
    ref_lo = np.minimum(m["anchor_open"].to_numpy(), m["prior_close"].to_numpy())
    close = m["close"].to_numpy()
    sig = m["sigma"].to_numpy()

    m = m.assign(
        r_long=(close / ref_hi - 1.0) / sig,
        r_short=(1.0 - close / ref_lo) / sig,
        gate_long=(close > m["twap"].to_numpy()) if gate else True,
        gate_short=(close < m["twap"].to_numpy()) if gate else True,
        bw=sig * m["anchor_open"].to_numpy(),
    )
    return m.reset_index(drop=True)


def fire_rates(rat: pd.DataFrame, k_grid: np.ndarray = K_GRID) -> np.ndarray:
    """Fraction of decisions producing a signal, for every k on the grid."""
    rl = rat["r_long"].to_numpy()[:, None]
    rs = rat["r_short"].to_numpy()[:, None]
    gl = np.asarray(rat["gate_long"], dtype=bool)[:, None]
    gs = np.asarray(rat["gate_short"], dtype=bool)[:, None]
    k = k_grid[None, :]
    fires = ((rl > k) & gl) | ((rs > k) & gs)
    return fires.mean(axis=0)


def pick_k(rat: pd.DataFrame, target_rate: float,
           k_grid: np.ndarray = K_GRID) -> tuple[float, float]:
    """Grid point whose fire rate is closest to `target_rate`. Never interpolated."""
    rates = fire_rates(rat, k_grid)
    j = int(np.argmin(np.abs(rates - target_rate)))
    return float(k_grid[j]), float(rates[j])


def take_signals(rat: pd.DataFrame, k: float) -> pd.DataFrame:
    """Apply the threshold. Long takes precedence if both sides somehow fire
    (impossible while ref_lo <= ref_hi and sigma > 0, asserted in tests)."""
    long_hit = (rat["r_long"].to_numpy() > k) & np.asarray(rat["gate_long"], dtype=bool)
    short_hit = (rat["r_short"].to_numpy() > k) & np.asarray(rat["gate_short"], dtype=bool)
    side = np.where(long_hit, 1, np.where(short_hit, -1, 0))
    out = rat.assign(side=side)
    return out[out["side"] != 0].reset_index(drop=True)


def forward(sig: pd.DataFrame, o: np.ndarray, c: np.ndarray, lo: int,
            horizons, embargo: int,
            length: int = A.SESSION_LENGTH) -> pd.DataFrame:  # noqa: E501
    """Signed forward return, EXIT-NEUTRAL: no stop, no target, no exit rule.

    decision on the close of bar m -> fill at open[m + 1 + embargo]
                                   -> exit at close[m + h + embargo]

    `embargo=0` reproduces the EXP-0002 next-bar-open fill. `embargo=1` is the
    primary arm and is what breaks the shared-close identity. The mfo guard keeps
    the exit inside the same session, so no forward return spans a session break.
    """
    m = sig["utc_min"].to_numpy() - lo
    mfo = sig["mfo"].to_numpy()
    side = sig["side"].to_numpy()

    fill_i = m + 1 + embargo
    ok_fill = (fill_i >= 0) & (fill_i < len(o))
    fill = np.where(ok_fill, o[np.clip(fill_i, 0, len(o) - 1)], np.nan)

    out = sig.copy()
    out["fill"] = fill
    for h in horizons:
        exit_i = m + h + embargo
        ok = (exit_i >= 0) & (exit_i < len(c)) & (mfo + h + embargo < length - 1)
        tgt = np.where(ok, c[np.clip(exit_i, 0, len(c) - 1)], np.nan)
        out[f"fwd_{h}"] = (tgt - fill) * side
    return out


MIN_SIGNALS = 100      # per-cell floor before a t is reported at all
MIN_CLUSTERS = 30      # distinct session dates required for a cluster-robust SE


def cluster_t(x: np.ndarray, groups: np.ndarray,
              min_signals: int = MIN_SIGNALS,
              min_clusters: int = MIN_CLUSTERS) -> float:
    """t of the PER-SIGNAL mean with a cluster-robust SE (rule 12).

    Clustering is on the session date, which is shared across pairs in the pooled
    statistic, so cross-pair correlation on the same day is absorbed too. NOT the
    session-averaged estimand: signal count is endogenous here and the two
    disagree in SIGN on this exact data (EXP-0002 finding D, LEARNINGS section 4).

    SMALL-CLUSTER GUARD. The clustered variance is a sum over clusters of squared
    within-cluster deviation sums. With only a handful of clusters that sum can
    collapse toward zero and the t explodes -- the first execution of this sweep
    produced a placebo |t| of 1.4e16 from a degenerate anchor whose sessions had
    almost no usable data. A t computed from a handful of clusters is not a
    conservative estimate, it is meaningless, so it is returned as NaN.

    NaN here means "this cell has no usable statistic" and MUST be treated as a
    FAILURE by every caller, never silently as a non-event: `NaN >= x` is False
    in numpy, so a NaN placebo would otherwise count as "did not beat the real
    anchor" and make the test easier to pass (LEARNINGS section 5).
    """
    n = len(x)
    if n < max(2, min_signals):
        return np.nan
    s = pd.Series(x - x.mean()).groupby(groups).sum()
    if s.size < min_clusters:
        return np.nan
    var = float((s.to_numpy() ** 2).sum()) / (n ** 2)
    if not np.isfinite(var) or var <= 0:
        return np.nan
    t = float(x.mean() / np.sqrt(var))
    return t if np.isfinite(t) else np.nan
