"""Volatility Expansion Index (VEI) feature family, with SMOOTHING dimensions.

VEI = intraday ATR(short) / ATR(long) on 1-min RTH bars, causal within-session.
Reading (user): VEI == 1 calm; VEI < 1 consolidating after a wider range
(contraction); VEI > 1 volatility expanding.

Dimensions this module exposes:
  * ATR method: 'sma' (rolling mean of TR), 'wilder' (Wilder RMA, alpha=1/n),
    'ema' (exponential, span=n).
  * warm-up `seed`: 'sma' (textbook Wilder, DEFAULT) or 'first' (legacy pandas
    `ewm(adjust=False)`, superseded -- see below).
  * ratio smoothing: an optional causal EMA of the VEI ratio itself (`smooth`
    span), applied WITHIN each session so no cross-session leakage.

CAUTION when comparing methods (reports/FINDINGS.md section A-corrected): equal nominal
`n` is NOT equal memory. SMA(n) has centre-of-mass (n-1)/2; Wilder(n) has n-1. So
wilder(10,50) carries ~2x the memory of sma(10,50) and a bare sma-vs-wilder comparison
confounds estimator form with memory -- which is exactly how EXP-0001 reached a wrong
attribution. Compare at matched centre-of-mass, in both directions. Note also that
Wilder alpha=1/n IS ewm(span=2n-1), so 'wilder' and 'ema' are one recursion at two
alphas, not two estimator families.

WARM-UP: `ewm(adjust=False, min_periods=n)` seeds at the FIRST bar and only masks the
first n-1 outputs; it does not seed with the first n-bar SMA the way textbook Wilder ATR
does. Because this ATR resets every session that bias is paid ~3710 times, not once, and
it measurably degraded the feature (forward-vol IC +0.157 -> +0.202 NQ / +0.195 -> +0.207
ES on repair). `seed='sma'` is therefore the default; `seed='first'` reproduces
EXP-0001..0005.

CALIBRATION: this ratio is NOT centred on 1. The long ATR stays anchored on the volatile
open while the short one walks off it, so mean VEI drifts monotonically up all session
(0.745 -> 1.165 NQ by 30-min slot). A fixed VEI=1 line is a TIME-OF-DAY threshold, not a
volatility threshold -- do not read it as "calm".

Causality (RULES rule 7/8): TR at bar i uses high[i], low[i] and the prior 1-min
close[i-1] within the SAME session (first bar: high-low). Every ATR / smoother is a
past-only rolling/exponential mean. ATR resets each session (intraday), so the long
window is under-populated near the open; strict min_periods nulls VEI there
(reported per rule 9a, conservative -- drops rows, no leak).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(bars: pd.DataFrame) -> pd.Series:
    """Per-bar 1-min True Range within each session. Aligned to bars.index."""
    b = bars.sort_values(["sdate", "mfo"])
    pc = b.groupby("sdate", sort=False)["close"].shift(1)
    hl = b["high"] - b["low"]
    hc = (b["high"] - pc).abs()
    lc = (b["low"] - pc).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    tr = tr.where(pc.notna(), hl)
    return tr.reindex(bars.index)


SEED_SMA = "sma"      # textbook: recursion starts from the first n-bar SMA
SEED_FIRST = "first"  # legacy: pandas ewm(adjust=False) starts at the first bar


def _alpha(n: int, method: str) -> float:
    """Smoothing constant. Wilder RMA alpha=1/n is EXACTLY ewm(span=2n-1), so the two
    methods differ only in alpha -- `wilder` carries centre-of-mass n-1 against `ema`
    span n's (n-1)/2, i.e. twice the effective memory at equal nominal n."""
    if method == "wilder":
        return 1.0 / n
    if method == "ema":
        return 2.0 / (n + 1.0)
    raise ValueError(method)


def _ewm_sma_seeded(s: pd.Series, groups: pd.Series, n: int, alpha: float) -> pd.Series:
    """Per-group exponential mean seeded with the first n-bar SMA (textbook Wilder).

    Definition: out[n-1] = mean(x[0:n]); out[i] = (1-a)*out[i-1] + a*x[i] for i >= n.
    NaN for i < n-1.

    Computed in closed form rather than by loop. Pandas `ewm(adjust=False)` runs the
    same recursion from p[0] = x[0], so the difference d = out - p obeys the homogeneous
    recursion d[i] = (1-a)*d[i-1] for i >= n. Hence for i >= n-1

        out[i] = p[i] + (1-a)**(i-(n-1)) * (mean(x[0:n]) - p[n-1]),

    which is exact and vectorises. `test_wilder_seed_matches_reference_loop` pins it to
    a literal loop.
    """
    g = s.groupby(groups, sort=False)
    p = g.transform(lambda x: x.ewm(alpha=alpha, min_periods=1, adjust=False).mean())
    pos = g.cumcount()
    sma = g.transform(lambda x: x.rolling(n, min_periods=n).mean())
    at_seed = pos == (n - 1)
    # broadcast each group's seed-bar values (NaN for sessions shorter than n bars)
    anchor_p = p.where(at_seed).groupby(groups, sort=False).transform("max")
    anchor_s = sma.where(at_seed).groupby(groups, sort=False).transform("max")
    out = p + np.power(1.0 - alpha, pos - (n - 1)) * (anchor_s - anchor_p)
    return out.where(pos >= (n - 1))


def _roll(s: pd.Series, groups: pd.Series, n: int, method: str,
          seed: str = SEED_SMA) -> pd.Series:
    if method == "sma":
        return s.groupby(groups, sort=False).transform(
            lambda x: x.rolling(n, min_periods=n).mean())
    if method in ("wilder", "ema"):
        a = _alpha(n, method)
        if seed == SEED_SMA:
            return _ewm_sma_seeded(s, groups, n, a)
        if seed == SEED_FIRST:
            return s.groupby(groups, sort=False).transform(
                lambda x: x.ewm(alpha=a, min_periods=n, adjust=False).mean())
        raise ValueError(seed)
    raise ValueError(method)


def intraday_atr(bars: pd.DataFrame, n: int, method: str = "sma",
                 seed: str = SEED_SMA) -> pd.Series:
    """Causal within-session ATR(n) by `method` in {sma, wilder, ema}.

    `seed` selects the exponential warm-up and is ignored by `sma`:
      * `'sma'` (default, textbook Wilder) -- seed the recursion with the first n-bar
        SMA at bar n-1, so the first published value is a genuine n-bar average.
      * `'first'` (legacy, superseded) -- pandas `ewm(adjust=False)` seeded at bar 0
        with `min_periods=n` merely masking the first n-1 outputs. Retained only to
        reproduce EXP-0001..0005; see reports/FINDINGS.md section A-corrected.

    The distinction matters here because the ATR resets EVERY session, so a warm-up
    bias is paid ~3710 times rather than once.
    """
    b = bars.sort_values(["sdate", "mfo"])
    tr = true_range(b)
    atr = _roll(tr, b["sdate"], n, method, seed)
    return atr.reindex(bars.index)


def vei_series(bars: pd.DataFrame, short: int, long: int,
               atr_method: str = "sma", smooth: int = 0,
               seed: str = SEED_SMA) -> pd.Series:
    """Per-bar VEI = ATR(short)/ATR(long), optionally EMA-smoothed (span=`smooth`).

    `smooth<=1` returns the raw ratio. `seed` is passed to `intraday_atr`.
    Aligned to bars.index.
    """
    b = bars.sort_values(["sdate", "mfo"])
    atr_s = intraday_atr(b, short, atr_method, seed)
    atr_l = intraday_atr(b, long, atr_method, seed)
    vei = atr_s / atr_l
    vei = vei.where(np.isfinite(vei))
    if smooth and smooth > 1:
        vei = vei.groupby(b["sdate"], sort=False).transform(
            lambda x: x.ewm(span=smooth, min_periods=1, adjust=False).mean())
    return vei.reindex(bars.index)


def add_vei(bars: pd.DataFrame, short: int = 10, long: int = 50,
            atr_method: str = "sma", smooth: int = 0, col: str = "vei",
            seed: str = SEED_SMA) -> pd.DataFrame:
    """Return a copy of bars with a VEI column added."""
    out = bars.copy()
    out[col] = vei_series(bars, short, long, atr_method, smooth, seed).to_numpy()
    return out
