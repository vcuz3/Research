"""
Load GC (COMEX Gold) 1-minute bars, place the RTH cash session, and build the
per-session RTH VWAP and the same-time-of-day "Noise Area" bands used by the
Zarattini / Quantitativo intraday-momentum strategy.

This is a faithful port of `futures/nq/noise_vwap/core/data.py`; the ONLY
instrument-specific changes are the data path and the contract economics.

Session-hours note (modeling assumption, revisit in research phase):
  The NQ/ES replication uses the equity cash session 09:30..16:00 ET. Gold's
  most-liquid COMEX floor hours are 08:20..13:30 ET, and the Globex electronic
  session runs nearly 24h. For a like-for-like METHOD replication we keep the
  identical 09:30..16:00 ET window and the identical clock/bands/engine, and swap
  only the data and contract economics. Whether that window (versus a gold-native
  session) is the right one for gold is a research question, NOT part of this
  baseline replication.

Conventions (Databento source; see core/build_clean.py):
  * `ts_utc` in the source parquet is tz-aware UTC. We convert straight to
    America/New_York — DST-correct, no lossy round-trip.
  * RTH cash session = 09:30..16:00 ET.
  * VWAP is cumulative WITHIN the RTH session, reset each day, from typical price
    (H+L+C)/3 weighted by bar volume. Causal: bar t uses only bars 0..t.
  * Noise-area sigma[date, tod] = mean over the PRIOR `lookback` sessions of
    |close[d-i, tod] / open[d-i, 09:30] - 1|. Strictly prior sessions (shift 1),
    so no lookahead (CLAUDE.md rule 7/18).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

# Shared instrument data lives at the common GC parent (futures/gc/data), per
# RESEARCH_WORKFLOW: reusable market data is stored once at the instrument parent,
# not duplicated per project. parents[2] = futures/gc.
DATA = Path(__file__).resolve().parents[2] / "data"
# ES lives at the shared NQ instrument parent (Databento clean, same UTC ts + ET
# convention as GC). It is loaded ONLY to derive the ES noise-VWAP *state* for the
# cross-asset conditioning study (HYP-0005); GC contract economics below are unused
# for ES because the study never books ES P&L, only ES direction.
ES_DATA = Path(__file__).resolve().parents[3] / "nq" / "data"
PATHS = {
    "GC": DATA / "GC_1m_clean.parquet",
    "ES": ES_DATA / "ES_1m_clean.parquet",
}

RTH_START = 9 * 60 + 30   # 09:30 ET
RTH_END = 16 * 60         # 16:00 ET

# COMEX Gold (GC): 100 troy oz contract, min tick 0.10 = $10, 1 point = $100.
TICK = {"GC": 0.10}
TICK_VALUE = {"GC": 10.0}       # $ / tick / contract
POINT_VALUE = {"GC": 100.0}     # $ / point / contract

MIN_BARS = 350   # a session must be near-complete to be usable

# Noise-band coverage tolerance (rule 9a). The same-time-of-day sigma averages the
# prior `lookback` sessions' excursion at a given minute. Requiring ALL `lookback`
# of them (min_periods == lookback) means a SINGLE missing minute anywhere in the
# trailing window nulls the band for that (date, tod) -- a no-op on liquid NQ but on
# GC's thinner post-floor-close afternoon it silently deleted ~12% of 14:59 and ~28%
# of 15:29 decisions. Require only this FRACTION of the window populated; the mean is
# taken over whichever prior sessions are present. See reports/DATA_QUALITY.md.
BAND_MIN_FRAC = 0.9


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
    # sigma = mean of the prior `lookback` sessions' move, strictly prior. Tolerate up
    # to (1 - BAND_MIN_FRAC) of the window missing at this minute (rule 9a): rolling
    # .mean() already averages over only the non-NaN prior sessions, so relaxing
    # min_periods simply excludes a missing day from the mean instead of nulling it.
    min_obs = max(1, int(np.ceil(BAND_MIN_FRAC * lookback)))
    sigma = move.shift(1).rolling(lookback, min_periods=min_obs).mean()

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
    for inst in ("GC",):
        d = load_rth(inst)
        b = noise_bands(d, 90)
        print(inst, "bars", len(d), "sessions", d["date"].nunique(),
              d["date"].min().date(), "->", d["date"].max().date(),
              "| band rows", len(b))
