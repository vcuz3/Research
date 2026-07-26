"""
Volatility Expansion Index (VEI): intraday short-lookback ATR / long-lookback ATR.

The indicator measures the ACCELERATION of intraday volatility -- how fast the tape
is moving now (short window) relative to its own recent baseline (long window). A
value > 1 means volatility is EXPANDING; < 1 means CONTRACTING. This is distinct
from the RVOL level (EXP-0015/0016) and the daily ATR scale: VEI is a within-session
vol-of-vol / regime-change ratio, dimensionless.

Baseline variant: ATR(10) / ATR(50) on 1-minute RTH bars.

Causality (RULES.md rule 7/8): both ATRs are simple rolling means of the 1-minute
True Range computed strictly within the session and using only bars at or before the
decision bar. True Range at bar i uses high[i], low[i] and the PRIOR 1-min close
(close[i-1]) -- all known at the close of bar i. The decision is taken at the bar
close; the fill is still next-open everywhere it is used. The ATR resets each session
(intraday indicator), so the long window is under-populated near the open; strict
`min_periods=n` nulls VEI there and that deletion is REPORTED per rule 9a (it is
conservative -- it drops signals, it does not leak).
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


def intraday_atr(bars: pd.DataFrame, n: int, method: str = "sma") -> pd.Series:
    """Causal within-session ATR(n) of True Range, aligned to `bars.index`.

    method: 'sma' = rolling mean (strict min_periods=n; undefined until n bars in);
            'wilder' = Wilder RMA (EMA with alpha=1/n, min_periods=n) -- the textbook
            ATR, far more persistent (see vei_exploration Study A);
            'ema' = exponential (span=n, min_periods=n).
    """
    b = bars.sort_values(["sdate", "mfo"])
    tr = true_range(b)
    g = tr.groupby(b["sdate"], sort=False)
    if method == "sma":
        atr = g.transform(lambda s: s.rolling(n, min_periods=n).mean())
    elif method == "wilder":
        atr = g.transform(lambda s: s.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean())
    elif method == "ema":
        atr = g.transform(lambda s: s.ewm(span=n, min_periods=n, adjust=False).mean())
    else:
        raise ValueError(method)
    return atr.reindex(bars.index)


def vei_series(bars: pd.DataFrame, short: int, long: int,
               method: str = "sma") -> pd.Series:
    """Per-bar VEI = ATR(short) / ATR(long), causal, aligned to `bars.index`."""
    atr_s = intraday_atr(bars, short, method)
    atr_l = intraday_atr(bars, long, method)
    vei = atr_s / atr_l
    vei = vei.where(np.isfinite(vei))
    return vei


def vei_features(bars: pd.DataFrame, dm, short: int = 10, long: int = 50,
                 method: str = "sma") -> pd.DataFrame:
    """Per (date, decision-mfo) causal VEI value.

    Returns a long frame [date, mfo, vei, atr_s, atr_l] restricted to the decision
    clock `dm`. `date` matches the engine's trade-date key (bars['sdate']).
    """
    dmset = {int(m) for m in dm}
    b = bars.sort_values(["sdate", "mfo"]).copy()
    b["atr_s"] = intraday_atr(b, short, method).to_numpy()
    b["atr_l"] = intraday_atr(b, long, method).to_numpy()
    b["vei"] = (b["atr_s"] / b["atr_l"]).to_numpy()
    dec = b[b["mfo"].isin(dmset)][["sdate", "mfo", "atr_s", "atr_l", "vei"]].copy()
    dec = dec.rename(columns={"sdate": "date"})
    dec["mfo"] = dec["mfo"].astype(int)
    return dec.reset_index(drop=True)
