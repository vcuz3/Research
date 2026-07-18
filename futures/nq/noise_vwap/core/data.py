"""
Load NQ (and ES) 1-minute bars, place the RTH cash session, and build the
per-session RTH VWAP and the same-time-of-day "Noise Area" bands used by the
Zarattini / Quantitativo intraday-momentum strategy.

Conventions (Databento source; see core/build_clean.py):
  * `ts_utc` in the source parquet is tz-aware UTC. We convert straight to
    America/New_York — DST-correct, no lossy Chicago round-trip, no ambiguous-hour
    NaT drops. (This fixes the old vendor's recent-years hours defect.)
  * RTH cash session = 09:30..16:00 ET.
  * VWAP is cumulative WITHIN the RTH session, reset each day, from typical price
    (H+L+C)/3 weighted by bar volume. Causal: bar t uses only bars 0..t.
  * Noise-area sigma[date, tod] = mean over the PRIOR `lookback` sessions of
    |close[d-i, tod] / open[d-i, 09:30] - 1|. Strictly prior sessions (shift 1),
    so no lookahead (CLAUDE.md rule 7/18).

No RTH session contains a contract roll (checked: 0 sessions with >1 symbol in
RTH on either instrument), so no VWAP or trade spans a roll.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
PATHS = {
    "NQ": DATA / "NQ_1m_clean.parquet",
    "ES": DATA / "ES_1m_clean.parquet",
}

RTH_START = 9 * 60 + 30   # 09:30 ET
RTH_END = 16 * 60         # 16:00 ET

TICK = {"NQ": 0.25, "ES": 0.25}
TICK_VALUE = {"NQ": 5.0, "ES": 12.50}       # $ / tick / contract
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}      # $ / point / contract

MIN_BARS = 350   # a session must be near-complete to be usable


def load_rth(inst: str) -> pd.DataFrame:
    """Return RTH 1-min bars with ET clock + session VWAP. One row per bar."""
    df = pd.read_parquet(PATHS[inst])
    ts = pd.to_datetime(df["ts_utc"], utc=True)
    et = ts.dt.tz_convert("America/New_York")
    df = df.copy()
    df["et"] = et.values
    df["tod"] = (et.dt.hour * 60 + et.dt.minute).values
    df["date"] = et.dt.normalize().dt.tz_localize(None).values
    df = df[(df["tod"] >= RTH_START) & (df["tod"] < RTH_END)]
    df = df.sort_values("et").reset_index(drop=True)

    # keep only near-complete sessions
    nb = df.groupby("date")["et"].transform("size")
    df = df[nb >= MIN_BARS].reset_index(drop=True)

    # cumulative session VWAP (causal)
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"].astype("float64").to_numpy()
    g = df.groupby("date", sort=False)
    cum_v = g["volume"].cumsum().astype("float64").to_numpy()
    cum_tpv = pd.Series(tp.to_numpy() * v, index=df.index).groupby(df["date"]).cumsum().to_numpy()
    df["vwap"] = cum_tpv / cum_v
    df["bar_i"] = g.cumcount().to_numpy()
    df["inst"] = inst
    return df[["et", "date", "tod", "bar_i", "inst", "symbol",
               "open", "high", "low", "close", "volume", "vwap"]]


def noise_bands(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    Per (date, tod) upper/lower Noise-Area bands.

    move[d, tod]  = |close[d, tod] / open[d, 09:30] - 1|
    sigma[d, tod] = mean of move over the prior `lookback` sessions (shift 1)
    upper[d, tod] = max(open[d,09:30], prior_rth_close[d]) * (1 + sigma)
    lower[d, tod] = min(open[d,09:30], prior_rth_close[d]) * (1 - sigma)

    Returns long frame: date, tod, sigma, upper, lower, rth_open, prior_close.
    """
    # per-session RTH open (09:30) and prior RTH close (last bar of prior session)
    opens = df[df["tod"] == RTH_START].set_index("date")["open"]
    if opens.empty:
        raise ValueError("no 09:30 open bars found")
    last = df.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
    dates = df["date"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)

    # close matrix [date x tod]
    cm = df.pivot_table(index="date", columns="tod", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    o0 = opens.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()
    # sigma = mean of the prior `lookback` sessions' move, strictly prior
    sigma = move.shift(1).rolling(lookback, min_periods=lookback).mean()

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["date", "tod", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="date")
    long = long.merge(prior_close.rename("prior_close"), on="date")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    hi_ref = np.maximum(long["rth_open"], long["prior_close"])
    lo_ref = np.minimum(long["rth_open"], long["prior_close"])
    long["upper"] = hi_ref * (1.0 + long["sigma"])
    long["lower"] = lo_ref * (1.0 - long["sigma"])
    return long


def daily_returns(df: pd.DataFrame) -> pd.Series:
    """RTH close-to-close return per session (for vol-target sizing)."""
    last = df.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
    return last.sort_index().pct_change()


if __name__ == "__main__":
    for inst in ("NQ", "ES"):
        d = load_rth(inst)
        b = noise_bands(d, 90)
        print(inst, "bars", len(d), "sessions", d["date"].nunique(),
              d["date"].min().date(), "->", d["date"].max().date(),
              "| band rows", len(b))
