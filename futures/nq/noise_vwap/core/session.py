"""
Generalized session loader for the Noise-Area + VWAP momentum studies.

Serves BOTH the RTH cash session (09:30..16:00 ET, the published/baseline) and the
full ETH / Globex session (18:00 ET prior evening .. 16:00 ET, flat at the RTH
close). The clock coordinate is `mfo` = integer minutes from the session's open,
which works for the overnight-spanning ETH session where raw ET time-of-day wraps
midnight. For RTH, mfo == tod - 570, so this module reproduces core.data exactly.

Session-date assignment (ETH): a bar's trade-date is (ET + 6h).date(). 18:00 ET
+6h = 00:00 next day, so the evening opens the NEXT session; 16:00 ET +6h = 22:00
same day, so the whole RTH day stays with its trade-date. This is the standard CME
Globex session for a trade date.

Hygiene (CLAUDE.md):
  * VWAP / noise-sigma are cumulative-within-session or strictly-prior-lookback:
    no session total, no lookahead (rule 7).
  * ATR (for the threshold study) is the mean prior-`atr_lb`-session RTH range in
    points, strictly shifted — a causal, one-sided volatility scale (rule 8/18),
    NOT an intrabar quantity that could leak (and NOT ticks, per rule 4/19).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
PATHS = {"NQ": DATA / "NQ_1m_clean.parquet", "ES": DATA / "ES_1m_clean.parquet"}

RTH_START = 9 * 60 + 30   # 09:30 ET  (tod)
RTH_END = 16 * 60         # 16:00 ET  (tod, exclusive)

TICK = {"NQ": 0.25, "ES": 0.25}
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}

MIN_BARS_RTH = 350
MIN_BARS_ETH = 900       # a Globex session should be near-complete (~1300 bars)


def _base(inst: str) -> pd.DataFrame:
    df = pd.read_parquet(PATHS[inst])
    ts = pd.to_datetime(df["ts_utc"], utc=True)
    et = ts.dt.tz_convert("America/New_York")
    df = df.copy()
    df["et"] = et.values
    df["tod"] = (et.dt.hour * 60 + et.dt.minute).values
    df["etdate"] = et.dt.normalize().dt.tz_localize(None).values
    # trade-date: RTH = ET date; ETH = (ET + 6h) date (18:00 ET rolls to next day)
    df["sdate_eth"] = (et + pd.Timedelta(hours=6)).dt.normalize().dt.tz_localize(None).values
    return df.sort_values("et").reset_index(drop=True)


def load_session(inst: str, session: str = "RTH", atr_lb: int = 14) -> pd.DataFrame:
    """
    Return 1-min bars for one instrument, one row per bar, with:
      et, sdate, tod, mfo, is_rth, bar_i, inst, symbol, o/h/l/c/volume, vwap, atr
    `sdate` is the trade-date. `mfo` = minutes from that session's open bar.
    `is_rth` flags the 09:30..16:00 ET bars (used to force the daily flat and to
    define the RTH range that ATR is built from). `atr` is the causal prior-
    `atr_lb`-session mean RTH range in points (constant within a session).
    """
    df = _base(inst)
    if session == "RTH":
        df = df[(df["tod"] >= RTH_START) & (df["tod"] < RTH_END)].copy()
        df["sdate"] = df["etdate"]
        min_bars = MIN_BARS_RTH
    elif session == "ETH":
        df["sdate"] = df["sdate_eth"]
        # drop the daily maintenance break (17:00-17:59 ET = 16:00-16:59 CT halt)
        df = df[df["tod"] != -1].copy()  # placeholder; keep all, break is just sparse
        min_bars = MIN_BARS_ETH
    else:
        raise ValueError(session)

    df["is_rth"] = (df["tod"] >= RTH_START) & (df["tod"] < RTH_END)
    df = df.sort_values("et").reset_index(drop=True)

    # minutes-from-open on a FIXED clock anchor (not the first observed bar), so the
    # same-time-of-day bands align across sessions even when the anchor bar is
    # missing. RTH: anchor 09:30 ET (mfo == tod-570, matches core.data exactly).
    # ETH: anchor 18:00 ET (Globex open); minutes wrap past midnight through to the
    # 16:00 ET RTH close at mfo 1320.
    if session == "RTH":
        df["mfo"] = (df["tod"] - RTH_START).astype(int)
    else:  # ETH
        df["mfo"] = ((df["tod"] - (18 * 60)) % 1440).astype(int)
    g = df.groupby("sdate", sort=False)
    df["bar_i"] = g.cumcount().to_numpy()

    # near-complete sessions only
    nb = g["et"].transform("size")
    df = df[nb >= min_bars].reset_index(drop=True)

    # cumulative session VWAP (causal, resets each session)
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"].astype("float64").to_numpy()
    gg = df.groupby("sdate", sort=False)
    cum_v = gg["volume"].cumsum().astype("float64").to_numpy()
    cum_tpv = pd.Series(tp.to_numpy() * v, index=df.index).groupby(df["sdate"]).cumsum().to_numpy()
    df["vwap"] = cum_tpv / cum_v

    # causal ATR: prior-atr_lb-session mean of RTH (high-low) range, in points
    rth = df[df["is_rth"]]
    rng = (rth.groupby("sdate")["high"].max() - rth.groupby("sdate")["low"].min())
    rng = rng.sort_index()
    atr = rng.shift(1).rolling(atr_lb, min_periods=atr_lb).mean()
    df["atr"] = df["sdate"].map(atr).to_numpy()

    df["inst"] = inst
    return df[["et", "sdate", "tod", "mfo", "is_rth", "bar_i", "inst", "symbol",
               "open", "high", "low", "close", "volume", "vwap", "atr"]]


def noise_bands(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    Same-time-of-day Noise-Area bands, keyed by (sdate, mfo).

    move[d, mfo]  = |close[d, mfo] / open[d, 0] - 1|
    sigma[d, mfo] = mean of move over the prior `lookback` sessions (strictly prior)
    upper[d, mfo] = max(open[d,0], prior_session_close[d]) * (1 + sigma)
    lower[d, mfo] = min(open[d,0], prior_session_close[d]) * (1 - sigma)

    Returns long frame: sdate, mfo, sigma, upper, lower, rth_open, prior_close.
    """
    opens = df[df["mfo"] == 0].set_index("sdate")["open"]
    if opens.empty:
        raise ValueError("no session-open (mfo==0) bars found")
    last = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df["sdate"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)

    cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    o0 = opens.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()
    sigma = move.shift(1).rolling(lookback, min_periods=lookback).mean()

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["sdate", "mfo", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="sdate")
    long = long.merge(prior_close.rename("prior_close"), on="sdate")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    hi_ref = np.maximum(long["rth_open"], long["prior_close"])
    lo_ref = np.minimum(long["rth_open"], long["prior_close"])
    long["upper"] = hi_ref * (1.0 + long["sigma"])
    long["lower"] = lo_ref * (1.0 - long["sigma"])
    return long


def daily_returns(df: pd.DataFrame) -> pd.Series:
    """Session close-to-close return per trade-date (for vol-target sizing)."""
    last = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    return last.sort_index().pct_change()


def decision_mfos(period: int, max_mfo: int) -> list[int]:
    """Concretum-style clock at `period` minutes: decide at mfo = j*period - 1
    (i.e. min_from_open % period == 0 with the open counted as minute 1), exposure
    from the next bar. For period=30, RTH -> [29,59,...,389] == tod [599,...,959]."""
    out = []
    j = 1
    while j * period - 1 <= max_mfo:
        out.append(j * period - 1)
        j += 1
    return out


if __name__ == "__main__":
    for sess in ("RTH", "ETH"):
        d = load_session("NQ", sess)
        b = noise_bands(d, 90)
        nb = d.groupby("sdate").size()
        print(f"NQ {sess}: bars={len(d)} sessions={d['sdate'].nunique()} "
              f"{d['sdate'].min().date()}->{d['sdate'].max().date()} "
              f"med_bars/sess={int(nb.median())} max_mfo={int(d['mfo'].max())} "
              f"band_rows={len(b)}")
