"""Wilder RSI on the decision grid, and its exact decomposition.

What RSI actually is
--------------------
With `U = max(dp, 0)`, `D = max(-dp, 0)` and `A_n` the Wilder recursion,

    RSI = 100 * A_n(U) / (A_n(U) + A_n(D))

Because `U - D = dp` and `U + D = |dp|`, and `A_n` is linear, this is EXACTLY

    RSI = 50 + 50 * A_n(dp) / A_n(|dp|)                          (identity, tested)

i.e. **a smoothed trailing return divided by a trailing absolute-return volatility,
rescaled onto [0, 100]**.  RSI is not a new quantity; it is this project's own two
ingredients combined in one particular way.

Why that matters here
---------------------
On the 30-minute decision grid the increments `dp` ARE `past_30`, the series
finding B already fades.  So RSI(14) is a differently-NORMALISED sibling of the
project's best signal, and the interesting question is not "does it work" but
"is its normaliser better or worse than the causal same-slot one".  Two hazards
follow directly:

1. **The degenerate-numerator control is mandatory** (LEARNINGS 2026-07-27).  A
   ratio must beat its own bare numerator, or the denominator is decoration.
2. **RSI's denominator is a TRAILING WINDOW, not a same-slot statistic.**  It
   therefore lags volatility transitions: after a quiet stretch gives way to a
   busy one the denominator is still small, so RSI reaches its extremes more
   easily.  A fixed 70/30 cut can be partly a TIME-OF-DAY selector for exactly
   the reason LEARNINGS 2026-07-27 documents, and the per-slot selection rate
   must be reported rather than assumed uniform.

Initialisation (LEARNINGS 2026-07-26)
-------------------------------------
`ewm(alpha=1/n, adjust=False)` seeds the recursion at the FIRST observation and
`min_periods=n` only MASKS early output; it is NOT textbook Wilder, which seeds
with the n-bar SMA.  On a per-reset feature that bias is paid at every reset.
`wilder_rma` seeds with the SMA and is pinned against the pandas version in the
tests so the difference is visible rather than silent.

Resets
------
The recursion runs CONTINUOUSLY across contiguous trade dates -- resetting every
session would pay the warm-up 3,400 times and delete the first 14 of 46 decisions
each day.  It resets only where the retained session sequence BREAKS (a dropped
roll or short session), because an increment spanning a dropped session can span
a contract change.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_N = 14
NEIGHBOURS = (7, 28)


def wilder_rma(values: np.ndarray, n: int, reset: np.ndarray | None = None
               ) -> np.ndarray:
    """Wilder's running average, seeded with the n-bar SMA (textbook, not `ewm`).

    `reset[i] == True` starts a fresh run at `i`. Output is NaN until a run has
    accumulated `n` observations.
    """
    v = np.asarray(values, float)
    out = np.full(v.shape, np.nan)
    if reset is None:
        reset = np.zeros(v.shape, bool)
        if len(reset):
            reset[0] = True
    acc: list[float] = []
    prev = np.nan
    for i in range(len(v)):
        if reset[i]:
            acc, prev = [], np.nan
        x = v[i]
        if not np.isfinite(x):
            acc, prev = [], np.nan          # a gap invalidates the run
            continue
        if not np.isfinite(prev):
            acc.append(x)
            if len(acc) == n:
                prev = float(np.mean(acc))
                out[i] = prev
        else:
            prev = prev + (x - prev) / n
            out[i] = prev
    return out


def run_breaks(sdates: np.ndarray) -> np.ndarray:
    """True at the first row of each maximally contiguous run of trade dates.

    A retained session whose predecessor was DROPPED (roll or short) starts a new
    run, because the increment into it may span a contract change.
    """
    s = pd.to_datetime(pd.Series(sdates)).dt.normalize()
    uniq = s.drop_duplicates().sort_values()
    # NOTE: `NaT > Timedelta` is False, not NaN, so the first date must be marked
    # explicitly -- a `.fillna(True)` on the comparison silently never fires.
    gap = uniq.diff() > pd.Timedelta(days=4)     # weekend is 3 days; >4 = a hole
    gap.iloc[0] = True
    new_run = set(uniq[gap].to_list())
    first_of_day = s != s.shift(1)
    return (first_of_day & s.isin(new_run)).to_numpy()


def rsi_frame(panel: pd.DataFrame, n: int = DEFAULT_N,
              price_col: str = "close", gap_policy: str = "bridge") -> pd.DataFrame:
    """RSI(n) on the decision grid, plus the two halves of its decomposition.

    Returns `rsi_<n>`, `rsi_num_<n>` (smoothed trailing return -- the bare
    NUMERATOR, i.e. the degenerate control) and `rsi_den_<n>` (smoothed |return|,
    the volatility normaliser).  Strictly causal: every value uses only bars at or
    before that decision's own close.

    `gap_policy` -- what a MISSING decision-minute bar does to the recursion:

    ``"bridge"`` (default)
        Increments are taken between consecutive AVAILABLE closes inside a run, so
        one missing minute yields one longer increment.  The decision itself still
        has no RSI (there is no price to evaluate), but the recursion survives.
    ``"reset"``
        A missing bar breaks the run, which then needs `n` fresh increments.

    The difference is NOT cosmetic and is the reason the policy is a parameter
    rather than a constant.  Under ``"reset"``, a gap costs `n` FURTHER decisions,
    and on a 30-minute grid `n=14` is about seven hours -- so the deletion lands in
    a DIFFERENT BLOCK from the gap that caused it.  On 6E, `asia` holds 5.8% of the
    missing bars and `ldn_am` only 0.25%, yet under ``"reset"`` it is `ldn_am`
    whose RSI coverage collapses (0.73), because Asia's gaps are still rebuilding
    when London opens.  Per-block gap counts therefore do NOT predict per-block
    feature coverage for a recursive feature (rule 9a, finding G with a lag).
    """
    if gap_policy not in {"bridge", "reset"}:
        raise ValueError(gap_policy)
    d = panel.sort_values(["sdate", "mfo"], kind="mergesort").reset_index(drop=True)
    px = d[price_col].to_numpy(float)
    brk = run_breaks(d["sdate"].to_numpy())

    if gap_policy == "bridge":
        have = np.isfinite(px)
        idx = np.flatnonzero(have)
        sub_dp = np.full(len(idx), np.nan)
        sub_dp[1:] = np.diff(px[idx])
        sub_brk = brk[idx]
        sub_dp[sub_brk] = np.nan
        sub_res = np.zeros(len(idx), bool)
        sub_res[np.clip(np.flatnonzero(sub_brk) + 1, 0, max(len(idx) - 1, 0))] = True
        if len(sub_res):
            sub_res[0] = True
        sub_num = wilder_rma(sub_dp, n, sub_res)
        sub_den = wilder_rma(np.abs(sub_dp), n, sub_res)
        num = np.full(len(px), np.nan)
        den = np.full(len(px), np.nan)
        num[idx] = sub_num
        den[idx] = sub_den
    else:
        dp = np.full(len(px), np.nan)
        dp[1:] = np.diff(px)
        dp[brk] = np.nan                          # no increment across a break
        # The recursion consumes increments, so it resets one row AFTER the break:
        # the increment at a break row is itself undefined.
        res = np.zeros(len(px), bool)
        res[np.clip(np.flatnonzero(brk) + 1, 0, len(px) - 1)] = True
        if len(res):
            res[0] = True
        num = wilder_rma(dp, n, res)
        den = wilder_rma(np.abs(dp), n, res)

    with np.errstate(invalid="ignore", divide="ignore"):
        rsi = np.where(den > 0, 50.0 + 50.0 * num / den, np.nan)

    out = d[["sdate", "mfo"]].copy()
    out[f"rsi_{n}"] = rsi
    out[f"rsi_num_{n}"] = num
    out[f"rsi_den_{n}"] = den
    return out


def rsi_from_updown(panel: pd.DataFrame, n: int = DEFAULT_N,
                    price_col: str = "close") -> np.ndarray:
    """The TEXTBOOK up/down formulation, kept only to prove the identity in tests."""
    d = panel.sort_values(["sdate", "mfo"], kind="mergesort").reset_index(drop=True)
    px = d[price_col].to_numpy(float)
    brk = run_breaks(d["sdate"].to_numpy())
    dp = np.full(len(px), np.nan)
    dp[1:] = np.diff(px)
    dp[brk] = np.nan
    res = np.zeros(len(px), bool)
    res[np.clip(np.flatnonzero(brk) + 1, 0, len(px) - 1)] = True
    if len(res):
        res[0] = True
    au = wilder_rma(np.maximum(dp, 0.0), n, res)
    ad = wilder_rma(np.maximum(-dp, 0.0), n, res)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((au + ad) > 0, 100.0 * au / (au + ad), np.nan)
