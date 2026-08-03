"""Session-anchored average-price anchors and the deviation feature.

Anchors
-------
All anchors are causal cumulative statistics over bars ``0..t`` of the SAME
session.  They are deliberately built as a family so that the volume weighting
can be isolated by comparison rather than assumed:

    vwap    sum(tp*v) / sum(v)          the real thing; needs exchange volume
    twap    mean(tp)                    the EXACT degenerate limit of vwap at
                                        constant volume (this is what every spot-FX
                                        "VWAP" in this workspace actually is)
    open    session open price          no averaging at all
    pclose  prior session's close       no intra-session information at all

`tp` is the bar typical price (h+l+c)/3, the standard VWAP input.

`open` and `pclose` are not candidate indicators.  They are the DEGENERATE LIMITS
that answer "does the averaging do anything?" the way the bare numerator answers
"is this really a ratio?" (LEARNINGS 2026-07-27).  If distance-from-open predicts
as well as distance-from-VWAP, the VWAP machinery is decoration.

Deviation
---------
    dev_price = close - anchor                       (price units)
    dev_pip   = dev_price / 1e-4                     (reporting unit)
    dev_z     = dev_price / scale                    (unit-free)

`scale` is a CAUSAL same-slot dispersion: the trailing mean absolute deviation at
this exact `mfo` over the previous `lookback` sessions, shifted by one session.
This is the noise-area construction applied to the anchor distance, and it exists
because a fixed threshold on a session-reset feature is a TIME-OF-DAY SELECTOR
(LEARNINGS 2026-07-27): |close - vwap| grows mechanically through the session as
the anchor's window lengthens and the walk diffuses, so a fixed cut in pips would
select almost nothing in Asia and everything in the NY afternoon.

`min_periods` is the rule-9a fractional floor (2/3 of the lookback), not the
strict `min_periods=lookback` that silently deleted 28% of GC's late-day
decisions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANCHORS = ("vwap", "twap", "open", "pclose")

# Prior sessions used for the same-slot scale, and the rule-9a fractional floor.
#
# These values are SET BY THE MEASURED COVERAGE, not by convention.  6B is thin in
# Asia (ET 18:00-01:00 minute coverage 0.71-0.84 vs 6E's 0.89-0.96), so the usual
# (60, 2/3) pair deletes 35% of 6B's 18:00 ET decisions while deleting 1% of its
# London decisions -- a time-of-day-selective hidden filter of exactly the kind
# that cost GC 28% of its 15:29 decisions.  (90, 1/2) keeps the same 45-session
# estimator floor while cutting the worst-hour deletion to 4.8% and the
# across-hour spread from 0.342 to 0.035.  See reports/DATA_QUALITY.txt.
SLOT_LOOKBACK = 90
SLOT_MIN_FRAC = 0.5


def typical_price(bars: pd.DataFrame) -> np.ndarray:
    return (bars["high"].to_numpy(float)
            + bars["low"].to_numpy(float)
            + bars["close"].to_numpy(float)) / 3.0


def _cum_by_session(values: np.ndarray, sdate_codes: np.ndarray) -> np.ndarray:
    """Cumulative sum restarting at each session boundary. Input must be sorted."""
    c = np.cumsum(values)
    out = c.copy()
    # subtract the running total as of the last bar of the previous session
    starts = np.flatnonzero(np.r_[True, sdate_codes[1:] != sdate_codes[:-1]])
    base = np.zeros_like(c)
    prev_totals = np.r_[0.0, c[starts[1:] - 1]]
    base = np.repeat(prev_totals, np.diff(np.r_[starts, len(c)]))
    return out - base


def add_anchors(bars: pd.DataFrame) -> pd.DataFrame:
    """Attach `vwap`, `twap`, `open_anchor`, `pclose` (causal, session-anchored)."""
    b = bars.sort_values(["sdate", "mfo"], kind="mergesort").reset_index(drop=True)
    codes = pd.factorize(b["sdate"], sort=False)[0]
    tp = typical_price(b)
    v = b["volume"].to_numpy(float)

    cum_pv = _cum_by_session(tp * v, codes)
    cum_v = _cum_by_session(v, codes)
    cum_tp = _cum_by_session(tp, codes)
    cum_n = _cum_by_session(np.ones(len(b)), codes)

    with np.errstate(invalid="ignore", divide="ignore"):
        vwap = np.where(cum_v > 0, cum_pv / cum_v, np.nan)
    # A zero-volume prefix has no VWAP. Carry the last valid value forward WITHIN
    # the session so the anchor exists from the first traded bar onward.
    b["vwap"] = pd.Series(vwap).groupby(codes).ffill().to_numpy()
    b["twap"] = cum_tp / cum_n

    first = b.groupby("sdate")["open"].transform("first")
    b["open_anchor"] = first.to_numpy(float)
    last_close = b.groupby("sdate")["close"].last()
    b["pclose"] = b["sdate"].map(last_close.shift(1)).to_numpy(float)
    return b


def anchor_column(anchor: str) -> str:
    return {"vwap": "vwap", "twap": "twap",
            "open": "open_anchor", "pclose": "pclose"}[anchor]


def causal_slot_scale(df: pd.DataFrame, col: str, *,
                      lookback: int = SLOT_LOOKBACK,
                      min_frac: float = SLOT_MIN_FRAC) -> np.ndarray:
    """Trailing same-`mfo` mean of |col| over the PRIOR `lookback` sessions.

    Strictly causal: the value at (sdate s, mfo m) uses only sessions < s.  Returns
    NaN where fewer than `ceil(min_frac*lookback)` prior sessions carry that slot.
    """
    min_obs = int(np.ceil(min_frac * lookback))
    d = df[["sdate", "mfo", col]].copy()
    d["_a"] = d[col].abs()
    piv = d.pivot_table(index="sdate", columns="mfo", values="_a", aggfunc="mean")
    roll = piv.shift(1).rolling(lookback, min_periods=min_obs).mean()
    stacked = roll.stack(future_stack=True).rename("scale").reset_index()
    merged = df[["sdate", "mfo"]].merge(stacked, on=["sdate", "mfo"], how="left")
    return merged["scale"].to_numpy(float)


def add_deviations(bars: pd.DataFrame, anchors=ANCHORS, *,
                   lookback: int = SLOT_LOOKBACK) -> pd.DataFrame:
    """Attach `dev_<anchor>_pip` and `dev_<anchor>_z` for each anchor."""
    b = bars
    close = b["close"].to_numpy(float)
    for a in anchors:
        raw = close - b[anchor_column(a)].to_numpy(float)
        b[f"dev_{a}"] = raw
        b[f"dev_{a}_pip"] = raw / 1e-4
        scale = causal_slot_scale(b, f"dev_{a}", lookback=lookback)
        b[f"scale_{a}"] = scale
        with np.errstate(invalid="ignore", divide="ignore"):
            b[f"dev_{a}_z"] = np.where(scale > 0, raw / scale, np.nan)
    return b
