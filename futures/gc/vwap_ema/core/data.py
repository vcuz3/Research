"""
Data layer for the VWAP-EMA regime-filtered intraday gold strategy (SSRN-6650958).

Builds two aligned views of GC (COMEX Gold) RTH history:

  * a 15-MINUTE bar frame (the signal / indicator clock) with the paper's
    indicators: continuous EMA200/50/20 and ATR14 across the RTH 15m series, a
    20-bar volume MA, and a per-session cumulative volume-weighted VWAP anchored
    at the 09:30 ET session open (reset each session);
  * a 1-SECOND frame (the intrabar-fill clock) indexed by session, so the engine
    can resolve whether the initial 0.5-ATR stop or the 3R target was reached
    first WITHIN a 15m bar (rule 3 -- a coarse 15m/1m gross for a bracket is a
    fill artifact; see ../vwap_reversion/MEMORY.md).

Session convention (matches the paper's NY-anchored VWAP with a 16:00 ET reset):
RTH cash 09:30..16:00 ET, 26 fifteen-minute bars per session.

Provenance: reads the audited Databento clean parquets built by the sibling GC
projects (`../data/GC_1s_rth.parquet`, 1s RTH; `../data/GC_1m_clean.parquet`, 1m).
The UTC->ET DST-correct conversion mirrors ../vwap_reversion/core/data.py.

Indicator conventions (all causal; value at 15m bar i knowable at its close):
  * EMA200/50/20: EMA of the 15m close, computed CONTINUOUSLY across the RTH 15m
    series (adjust=False), NOT reset per session -- EMA200 spans ~8 sessions.
  * ATR14: Wilder's RMA (alpha=1/14) of true range over the continuous 15m series
    (Wilder 1978, ref [20] in the paper). In price points.
  * volma20: 20-bar simple moving average of 15m volume (continuous).
  * VWAP: cumulative volume-weighted typical price tp=(H+L+C)/3 of the 15m bars,
    reset at each 09:30 ET session open. Causal (bar i uses bars 0..i of its day).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
PATH_1M = DATA / "GC_1m_clean.parquet"
PATH_1S = DATA / "GC_1s_rth.parquet"

RTH_START = 9 * 60 + 30      # 09:30 ET, minutes from ET midnight
RTH_END = 16 * 60            # 16:00 ET (exclusive)
RTH_START_SEC = RTH_START * 60
BAR_SEC = 15 * 60            # 15-minute bar
N_BARS = (RTH_END - RTH_START) // 15   # 26 bars per session

# COMEX Gold (GC): 100 troy oz, tick 0.10 = $10, 1 point = $100.
# (Deployed on MGC micro, 1/10 notional; economics scale by 10. Sizing here is by
#  1%-risk R, so POINT_VALUE only sets the $ unit of the fixed-1-contract view.)
TICK = 0.10
TICK_VALUE = 10.0
POINT_VALUE = 100.0

# indicator warmup: require a fully-populated EMA200 window before a signal is
# valid (the longest lookback). Reported as a data-quality drop, not silent.
WARMUP_BARS = 200
MIN_1S_BARS = 1000   # a session's 1s stream must be materially traded to be used


def _to_et(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the DST-correct ET clock (date, tod minutes, tsec seconds) and gate
    to RTH. Mirrors ../vwap_reversion/core/data.py (offset resolved once per UTC
    day, broadcast by integer day -- fast at 1s scale)."""
    utc_ns = df["ts_utc"].array.asi8
    day_ns = 86_400_000_000_000
    utc_day = np.floor_divide(utc_ns, day_ns)
    days, day_code = np.unique(utc_day, return_inverse=True)
    day_ts = pd.to_datetime(days, unit="D", utc=True).as_unit("ns")
    local_day_ts = day_ts.tz_convert("America/New_York").tz_localize(None)
    offsets_ns = local_day_ts.asi8 - day_ts.asi8
    local_ns = utc_ns + offsets_ns[day_code]
    local_sec = np.floor_divide(local_ns, 1_000_000_000)
    tsec = np.mod(local_sec, 86_400).astype(np.int32)
    df = df.copy()
    df["tsec"] = tsec
    df["tod"] = (tsec // 60).astype(np.int32)
    df["date"] = np.floor_divide(local_ns, day_ns).astype(
        "datetime64[D]").astype("datetime64[ns]")
    df = df[(df["tod"] >= RTH_START) & (df["tod"] < RTH_END)]
    return df.sort_values(["date", "tsec"]).reset_index(drop=True)


def _resample_15m(bars1m: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1-minute RTH bars into 26 fifteen-minute bars per session on the
    ET clock. Bucket b in [0,26) covers [09:30+15b, 09:30+15(b+1)) ET."""
    b = bars1m
    bucket = ((b["tod"].to_numpy() - RTH_START) // 15).astype(np.int64)
    b = b.assign(bucket=bucket)
    g = b.groupby(["date", "bucket"], sort=True)
    out = g.agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum"),
                symbol=("symbol", "first")).reset_index()
    out["tsec"] = (RTH_START_SEC + out["bucket"].to_numpy() * BAR_SEC).astype(np.int64)
    out["tod"] = (out["tsec"] // 60).astype(np.int32)
    return out.sort_values(["date", "tsec"]).reset_index(drop=True)


def _session_vwap(df: pd.DataFrame) -> np.ndarray:
    """Per-session cumulative volume-weighted typical price of the 15m bars."""
    tp = (df["high"].to_numpy() + df["low"].to_numpy() + df["close"].to_numpy()) / 3.0
    v = np.where(df["volume"].to_numpy(float) <= 0, 1e-9, df["volume"].to_numpy(float))
    codes, _ = pd.factorize(df["date"], sort=False)
    vwap = np.empty(len(df), np.float64)
    cv = 0.0; cpv = 0.0; prev = -1
    for i in range(len(df)):
        if codes[i] != prev:
            prev = codes[i]; cv = 0.0; cpv = 0.0
        cv += v[i]; cpv += v[i] * tp[i]
        vwap[i] = cpv / cv
    return vwap


def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Attach continuous EMA200/50/20, Wilder ATR14, volma20, session VWAP."""
    c = df["close"]
    df = df.copy()
    df["ema200"] = c.ewm(span=200, adjust=False).mean().to_numpy()
    df["ema50"] = c.ewm(span=50, adjust=False).mean().to_numpy()
    df["ema20"] = c.ewm(span=20, adjust=False).mean().to_numpy()
    # Wilder ATR14 (RMA of true range) on the continuous 15m series
    pc = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]).abs(),
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    df["atr14"] = tr.ewm(alpha=1.0 / 14.0, adjust=False).mean().to_numpy()
    df["volma20"] = df["volume"].rolling(20, min_periods=20).mean().to_numpy()
    df["vwap"] = _session_vwap(df)
    # continuous bar index (for warmup gate) and within-session bar index
    df["bar_ix"] = np.arange(len(df), dtype=np.int64)
    df["sess_bar"] = df.groupby("date").cumcount().to_numpy()
    return df


def load_15m() -> pd.DataFrame:
    """RTH 15-minute bars with the paper's indicators. One row per bar, time
    sorted, columns: date, tsec, tod, sess_bar, bar_ix, open, high, low, close,
    volume, symbol, vwap, ema200, ema50, ema20, atr14, volma20."""
    b1 = pd.read_parquet(PATH_1M, columns=["ts_utc", "symbol", "open", "high",
                                           "low", "close", "volume"])
    b1 = _to_et(b1)
    bars = _resample_15m(b1)
    bars = _add_indicators(bars)
    return bars


def load_1s_index() -> dict:
    """Per-session 1-second arrays for intrabar fill resolution.

    Returns {date(np.datetime64): (tsec, open, high, low)} with each array sorted
    by tsec. Sessions with fewer than MIN_1S_BARS traded seconds are omitted; the
    engine falls back to the 15m OHLC (adverse) for those (reported by
    scripts/data_quality.py)."""
    df = pd.read_parquet(PATH_1S, columns=["ts_utc", "open", "high", "low"])
    df = _to_et(df)
    out: dict = {}
    codes, uniq = pd.factorize(df["date"], sort=True)
    tsec = df["tsec"].to_numpy(np.int64)
    op = df["open"].to_numpy(np.float64)
    hi = df["high"].to_numpy(np.float64)
    lo = df["low"].to_numpy(np.float64)
    order = np.argsort(codes, kind="stable")
    codes_s = codes[order]
    bounds = np.searchsorted(codes_s, np.arange(len(uniq)))
    bounds = np.append(bounds, len(codes_s))
    for k in range(len(uniq)):
        sl = order[bounds[k]:bounds[k + 1]]
        if sl.size < MIN_1S_BARS:
            continue
        s = sl[np.argsort(tsec[sl], kind="stable")]
        out[uniq[k].to_datetime64()] = (tsec[s], op[s], hi[s], lo[s])
    return out


if __name__ == "__main__":
    d = load_15m()
    print("15m bars", len(d), "sessions", d["date"].nunique(),
          str(d["date"].min().date()), "->", str(d["date"].max().date()))
    print("bars/session median", int(d.groupby("date").size().median()),
          "(theoretical 26)")
    warm = d[d["bar_ix"] >= WARMUP_BARS]
    print(f"usable after {WARMUP_BARS}-bar EMA200 warmup: {len(warm)} "
          f"({len(warm)/len(d):.1%})")
    print("atr14 median @sess_bar>=4:",
          round(float(d[d.sess_bar >= 4]["atr14"].median()), 3), "pt")
