"""
Generalized session-window loader for the GC session-hours study (HYP-0001).

The baseline `core/data.py` hardcodes the equity RTH window 09:30..16:00 ET. This
module parameterizes the window so we can test a gold-native COMEX session against
the inherited equity window with IDENTICAL machinery (same Concretum :59/:29 clock
measured from the window open, same noise bands, same VWAP, same engine, same
fills). Only the [start_tod, end_tod) window changes.

Everything is the same construction as `core/data.py`, generalized:
  * VWAP: cumulative within the window, reset daily, causal.
  * noise sigma[date, tod] = mean over prior `lookback` sessions of
    |close[d, tod] / open[d, start] - 1|, strictly prior (shift 1).
  * decision clock: Concretum 30-min from the window open (open counted as
    minute 1) -> decisions at start + (30j - 1), exposure from the next bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from .data import PATHS  # reuse GC clean-data path

MIN_BARS_FRAC = 0.90     # a session must have >= 90% of the window's minutes


def load_window(inst: str, start_tod: int, end_tod: int) -> pd.DataFrame:
    """RTH-style loader for an arbitrary [start_tod, end_tod) ET window (minutes
    from midnight). Returns one row per bar with et, date, tod, bar_i, o/h/l/c/
    volume, vwap. Near-complete sessions only."""
    df = pd.read_parquet(PATHS[inst])
    ts = pd.to_datetime(df["ts_utc"], utc=True)
    et = ts.dt.tz_convert("America/New_York")
    df = df.copy()
    df["et"] = et.values
    df["tod"] = (et.dt.hour * 60 + et.dt.minute).values
    df["date"] = et.dt.normalize().dt.tz_localize(None).values
    df = df[(df["tod"] >= start_tod) & (df["tod"] < end_tod)]
    df = df.sort_values("et").reset_index(drop=True)

    min_bars = int((end_tod - start_tod) * MIN_BARS_FRAC)
    nb = df.groupby("date")["et"].transform("size")
    df = df[nb >= min_bars].reset_index(drop=True)

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


def noise_bands_window(df: pd.DataFrame, lookback: int, start_tod: int) -> pd.DataFrame:
    """Same-time-of-day Noise-Area bands keyed to a window opening at start_tod.
    Identical construction to core.data.noise_bands with open = bar at start_tod."""
    opens = df[df["tod"] == start_tod].set_index("date")["open"]
    if opens.empty:
        raise ValueError(f"no window-open bars at tod={start_tod}")
    last = df.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
    dates = df["date"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)

    cm = df.pivot_table(index="date", columns="tod", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    o0 = opens.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()
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


def decision_tods(start_tod: int, end_tod: int, period: int = 30) -> list[int]:
    """Concretum clock: decisions at start + (period*j - 1), exposure next bar.
    For 09:30..16:00 (570..960) this returns 599,629,...,959 exactly matching the
    baseline DECISION_TODS."""
    out = []
    j = 1
    while start_tod + period * j - 1 < end_tod:
        out.append(start_tod + period * j - 1)
        j += 1
    return out
