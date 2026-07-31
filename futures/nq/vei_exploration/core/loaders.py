"""Data loader for the VEI-exploration study (self-contained, RTH 1-min).

One row per RTH 09:30--16:00 ET 1-min bar for NQ and ES, from the shared clean
Databento files at futures/nq/data/{NQ,ES}_1m_clean.parquet. Keeps full OHLC +
volume (True Range needs high/low and the prior close). `sdate` = ET calendar date;
`mfo` = minutes from 09:30 (0..389). Near-complete sessions only (>=350 bars);
Databento-flagged degraded days dropped (same list as hurst_explore). Nothing here
trades -- this is a measurement project.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NQ_DATA = ROOT.parents[0] / "data"                 # futures/nq/data
ONE_MIN = {"NQ": NQ_DATA / "NQ_1m_clean.parquet",
           "ES": NQ_DATA / "ES_1m_clean.parquet"}

RTH_START = 9 * 60 + 30
RTH_END = 16 * 60
MIN_BARS_1M = 350

DEGRADED = {
    "2014-06-11", "2014-06-12", "2014-06-13", "2017-11-13", "2018-10-21",
    "2019-01-15", "2019-02-22", "2020-02-27", "2020-02-28", "2020-06-30",
    "2020-07-01", "2021-12-05", "2022-01-02", "2025-09-17", "2025-09-24",
    "2025-11-28",
}
_DEGRADED = {pd.Timestamp(d) for d in DEGRADED}


def load_1m_rth(inst: str) -> pd.DataFrame:
    """RTH 1-min OHLCV with sdate, tod, mfo(0..389). Sorted by (sdate, mfo)."""
    # Keep the contract/roll fields in the research frame.  Most feature code does
    # not need them, but every material run must be able to report roll boundaries
    # and prove that a short holding window did not unknowingly span one (rule 9a/11).
    df = pd.read_parquet(
        ONE_MIN[inst],
        columns=["ts_utc", "symbol", "open", "high", "low", "close", "volume",
                 "is_roll"],
    )
    et = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    tod = et.dt.hour * 60 + et.dt.minute
    m = (tod >= RTH_START) & (tod < RTH_END)
    df = df[m].copy()
    df["sdate"] = et[m].dt.normalize().dt.tz_localize(None).values
    df["tod"] = tod[m].values
    df["mfo"] = (df["tod"] - RTH_START).astype(int)
    df = df[~df["sdate"].isin(_DEGRADED)]
    n = df.groupby("sdate")["close"].transform("size")
    df = df[n >= MIN_BARS_1M]
    return df.sort_values(["sdate", "mfo"]).reset_index(drop=True)


def daily_atr(bars: pd.DataFrame, lb: int = 14) -> pd.Series:
    """Causal prior-`lb`-session mean RTH (high-low) range in points, per sdate.

    Strictly prior (shift 1); a one-sided volatility SCALE for normalising forward
    moves into R units (distinct from the intraday VEI ratio). Indexed by sdate.
    """
    rng = bars.groupby("sdate")["high"].max() - bars.groupby("sdate")["low"].min()
    rng = rng.sort_index()
    return rng.shift(1).rolling(lb, min_periods=lb).mean()
