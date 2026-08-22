"""
Load NQ / ES 1-minute clean bars, place the RTH cash session (09:30-16:00 ET),
and resample to 5-minute RTH bars for the ATR counter-bar breakout study.

Conventions (shared Databento source, same as futures/nq/noise_vwap/core/data.py):
  * `ts_utc` is tz-aware UTC -> convert directly to America/New_York (DST correct).
  * RTH cash session = 09:30 <= tod < 16:00 ET.
  * 5-min bars are left-labelled: the 09:30 bar aggregates the 1-min bars in
    [09:30, 09:35). open=first, high=max, low=min, close=last, volume=sum.
  * No RTH session spans a contract roll on either instrument (checked: 0 sessions
    with >1 symbol in RTH), so no bar or trade crosses a roll.

The loader caches the 5-min RTH frame as a parquet next to this file so repeated
runs are fast; delete the cache to rebuild.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"          # futures/nq/data
CACHE = Path(__file__).resolve().parent / "_cache"
CACHE.mkdir(exist_ok=True)

PATHS = {"NQ": DATA / "NQ_1m_clean.parquet", "ES": DATA / "ES_1m_clean.parquet"}

RTH_START = 9 * 60 + 30   # 09:30 ET
RTH_END = 16 * 60         # 16:00 ET

TICK = {"NQ": 0.25, "ES": 0.25}          # index-tick size (points)
# Execution assumed in the MICRO contract (user spec): MNQ / MES.
MICRO_POINT_VALUE = {"NQ": 2.0, "ES": 5.0}   # $ / point / micro contract

MIN_5M_BARS = 12   # a session must have >=1 hour of 5-min bars to be usable


def _resample_5m(inst: str) -> pd.DataFrame:
    df = pd.read_parquet(PATHS[inst])
    et = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    # Drop the tz keeping the LOCAL (ET) wall clock. `.values`/`.to_numpy()` would
    # strip the tz keeping the UTC instant instead, which silently shifts the whole
    # session window by the UTC offset (09:30 ET would become 09:30 UTC = 05:30 ET).
    df = df.assign(et=et.dt.tz_localize(None).values)
    tod = df["et"].dt.hour * 60 + df["et"].dt.minute
    df = df[(tod >= RTH_START) & (tod < RTH_END)].copy()
    df["date"] = df["et"].dt.normalize().dt.tz_localize(None)
    df = df.set_index("et").sort_index()

    g = df.groupby("date").resample("5min")
    out = g.agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum")).dropna(subset=["open"]).reset_index()
    # keep near-complete sessions (half days are fine; drop tiny fragments)
    nb = out.groupby("date")["open"].transform("size")
    out = out[nb >= MIN_5M_BARS].reset_index(drop=True)
    out["bar_i"] = out.groupby("date").cumcount()
    out["inst"] = inst
    return out[["et", "date", "bar_i", "inst", "open", "high", "low", "close", "volume"]]


def load_5m_rth(inst: str, rebuild: bool = False) -> pd.DataFrame:
    cache = CACHE / f"{inst}_5m_rth.parquet"
    if cache.exists() and not rebuild:
        return pd.read_parquet(cache)
    out = _resample_5m(inst)
    out.to_parquet(cache)
    return out


def daily_atr(bars: pd.DataFrame, n: int = 14) -> pd.Series:
    """
    Daily ATR(14) from RTH daily true range, LAGGED one session.

    Daily OHLC = per-session RTH aggregate. TR = max(H-L, |H-Cprev|, |L-Cprev|).
    ATR = Wilder RMA(14) of TR seeded with the 14-bar SMA (avoids the ewm
    first-observation seeding bias, LEARNINGS #11).  Returned series is indexed by
    session date and SHIFTED one session, so the value on date D uses only sessions
    <= D-1 -- the lookahead guard the spec requires.
    """
    g = bars.groupby("date")
    daily = pd.DataFrame({
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
    }).sort_index()
    prev_close = daily["close"].shift(1)
    tr = pd.concat([
        daily["high"] - daily["low"],
        (daily["high"] - prev_close).abs(),
        (daily["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder RMA seeded with SMA(n)
    atr = tr.copy() * np.nan
    tr_v = tr.to_numpy()
    out = np.full(len(tr_v), np.nan)
    if len(tr_v) >= n:
        out[n - 1] = np.nanmean(tr_v[:n])
        for i in range(n, len(tr_v)):
            out[i] = (out[i - 1] * (n - 1) + tr_v[i]) / n
    atr = pd.Series(out, index=daily.index, name="atr")
    return atr.shift(1)   # lookahead guard: day D uses ATR through D-1
