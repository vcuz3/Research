"""
Volatility Expansion Index (VEI): intraday short-lookback ATR / long-lookback ATR.

The indicator measures the ACCELERATION of intraday volatility -- how fast the tape
is moving now (short window) relative to its own recent baseline (long window). A
value > 1 means volatility is EXPANDING; < 1 means CONTRACTING. This is distinct
from the RVOL level (EXP-0015/0016) and the daily ATR scale: VEI is a within-session
vol-of-vol / regime-change ratio, dimensionless.

Baseline variant: ATR(10) / ATR(50) on 1-minute RTH bars.

WARM-UP (repaired 2026-07-27): for the exponential methods, pandas
`ewm(adjust=False, min_periods=n)` seeds the recursion at the FIRST observation and
`min_periods` merely MASKS the first n-1 outputs -- it does not seed with the first
n-bar SMA the way textbook Wilder ATR does. On a continuous series that is a one-off
burn-in, but this ATR RESETS EVERY SESSION, so the bias is paid once per session and
never washes out. In the sibling `vei_exploration` project the same defect measurably
degraded the feature (forward-vol IC +0.157 -> +0.202 NQ / +0.195 -> +0.207 ES on
repair), inflated its apparent persistence (AC1 0.549 -> 0.441, because consecutive
bars shared one contaminating seed), and carried a time-of-day gradient that shifted
downstream conclusions. `seed='sma'` (textbook) is therefore the DEFAULT here;
`seed='first'` reproduces the legacy behaviour and exists only for rule-23
reproduction of EXP-0036. See shared LEARNINGS.md 2026-07-26 and
`futures/nq/vei_exploration/reports/FINDINGS.md` section A-corrected.

NOTE on prior runs: EXP-0035 used `method='sma'` and is UNAFFECTED (the SMA path has
no recursion to seed). EXP-0036 (the Wilder RMA revisit) ran the MIS-INITIALISED
feature and must be re-run before its conclusions are cited.

CAUTION when comparing methods: equal nominal `n` is NOT equal memory. SMA(n) has
centre-of-mass (n-1)/2 but Wilder(n) has n-1, so `wilder(10,50)` carries ~2x the
memory of `sma(10,50)`; a bare sma-vs-wilder comparison confounds estimator form with
effective memory. Wilder alpha=1/n is EXACTLY `ewm(span=2n-1)`, so 'wilder' and 'ema'
are one recursion at two alphas, not two estimator families.

Causality (RULES.md rule 7/8): both ATRs are causal within-session means of the
1-minute True Range using only bars at or before the decision bar. True Range at bar i
uses high[i], low[i] and the PRIOR 1-min close (close[i-1]) -- all known at the close
of bar i. The decision is taken at the bar close; the fill is still next-open
everywhere it is used. The ATR resets each session (intraday indicator), so the long
window is under-populated near the open; strict `min_periods=n` nulls VEI there and
that deletion is REPORTED per rule 9a (it is conservative -- it drops signals, it does
not leak).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(bars: pd.DataFrame) -> pd.Series:
    """Per-bar 1-minute True Range, computed strictly within each session.

    TR[i] = max(high-low, |high - prev_close|, |low - prev_close|) where prev_close
    is the prior 1-min close in the SAME session. At the session's first bar there is
    no prior close, so TR = high - low. Returns a Series aligned to `bars.index`.
    """
    b = bars.sort_values(["sdate", "mfo"])
    pc = b.groupby("sdate", sort=False)["close"].shift(1)
    hl = b["high"] - b["low"]
    hc = (b["high"] - pc).abs()
    lc = (b["low"] - pc).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    tr = tr.where(pc.notna(), hl)  # first bar of session: high-low
    return tr.reindex(bars.index)


SEED_SMA = "sma"      # textbook: recursion starts from the first n-bar SMA
SEED_FIRST = "first"  # legacy: pandas ewm(adjust=False) starts at the first bar


def _alpha(n: int, method: str) -> float:
    """Smoothing constant. Wilder RMA alpha=1/n is EXACTLY ewm(span=2n-1)."""
    if method == "wilder":
        return 1.0 / n
    if method == "ema":
        return 2.0 / (n + 1.0)
    raise ValueError(method)


def _ewm_sma_seeded(s: pd.Series, groups: pd.Series, n: int, alpha: float) -> pd.Series:
    """Per-group exponential mean seeded with the first n-bar SMA (textbook Wilder).

    Definition: out[n-1] = mean(x[0:n]); out[i] = (1-a)*out[i-1] + a*x[i] for i >= n;
    NaN for i < n-1.

    Computed in closed form rather than by loop. Pandas `ewm(adjust=False)` runs the
    same recursion from p[0] = x[0], so the difference d = out - p obeys the
    homogeneous recursion d[i] = (1-a)*d[i-1] for i >= n. Hence for i >= n-1

        out[i] = p[i] + (1-a)**(i-(n-1)) * (mean(x[0:n]) - p[n-1]),

    which is exact and vectorises. Pinned to a literal reference loop by
    `tests/test_vei.py::test_wilder_seed_matches_reference_loop`.
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


def intraday_atr(bars: pd.DataFrame, n: int, method: str = "sma",
                 seed: str = SEED_SMA) -> pd.Series:
    """Causal within-session ATR(n) of True Range, aligned to `bars.index`.

    method: 'sma' = rolling mean (strict min_periods=n; undefined until n bars in);
            'wilder' = Wilder RMA (alpha=1/n) -- the textbook ATR, far more
            persistent (see vei_exploration Study A);
            'ema' = exponential (span=n).

    `seed` selects the exponential warm-up and is IGNORED by 'sma':
      * 'sma' (default, textbook) -- seed the recursion with the first n-bar SMA at
        bar n-1, so the first published value is a genuine n-bar average;
      * 'first' (legacy, superseded) -- pandas `ewm(adjust=False)` seeded at bar 0
        with `min_periods=n` merely masking the first n-1 outputs. Retained only to
        reproduce EXP-0036; see this module's docstring.
    """
    b = bars.sort_values(["sdate", "mfo"])
    tr = true_range(b)
    g = tr.groupby(b["sdate"], sort=False)
    if method == "sma":
        atr = g.transform(lambda s: s.rolling(n, min_periods=n).mean())
    elif method in ("wilder", "ema"):
        a = _alpha(n, method)
        if seed == SEED_SMA:
            atr = _ewm_sma_seeded(tr, b["sdate"], n, a)
        elif seed == SEED_FIRST:
            atr = g.transform(lambda s: s.ewm(alpha=a, min_periods=n,
                                              adjust=False).mean())
        else:
            raise ValueError(seed)
    else:
        raise ValueError(method)
    return atr.reindex(bars.index)


def vei_series(bars: pd.DataFrame, short: int, long: int,
               method: str = "sma", seed: str = SEED_SMA) -> pd.Series:
    """Per-bar VEI = ATR(short) / ATR(long), causal, aligned to `bars.index`."""
    atr_s = intraday_atr(bars, short, method, seed)
    atr_l = intraday_atr(bars, long, method, seed)
    vei = atr_s / atr_l
    vei = vei.where(np.isfinite(vei))
    return vei


def vei_features(bars: pd.DataFrame, dm, short: int = 10, long: int = 50,
                 method: str = "sma", seed: str = SEED_SMA) -> pd.DataFrame:
    """Per (date, decision-mfo) causal VEI value.

    Returns a long frame [date, mfo, vei, atr_s, atr_l] restricted to the decision
    clock `dm`. `date` matches the engine's trade-date key (bars['sdate']).
    """
    dmset = {int(m) for m in dm}
    b = bars.sort_values(["sdate", "mfo"]).copy()
    b["atr_s"] = intraday_atr(b, short, method, seed).to_numpy()
    b["atr_l"] = intraday_atr(b, long, method, seed).to_numpy()
    b["vei"] = (b["atr_s"] / b["atr_l"]).to_numpy()
    dec = b[b["mfo"].isin(dmset)][["sdate", "mfo", "atr_s", "atr_l", "vei"]].copy()
    dec = dec.rename(columns={"sdate": "date"})
    dec["mfo"] = dec["mfo"].astype(int)
    return dec.reset_index(drop=True)
