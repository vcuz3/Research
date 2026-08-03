"""
Build clean 1-minute parquet for the four FX pairs from the IBKR CSV archives in
`forex/data/`.

Source convention (`forex/AUDUSD/download_intraday_ibkr.py`): `time` is tz-aware
UTC, OHLC are IBKR MIDPOINT quotes, and `volume` is **-1 for every row** — IBKR
does not publish size for cash FX. That is the single structural difference from
the NQ/ES noise_vwap project and is why this port has no VWAP (see
`core/session.py`).

What this step does, and nothing more:
  * parse `time` as UTC, drop rows that fail to parse;
  * drop exact duplicate timestamps (keep last) and sort;
  * assert OHLC sanity (low <= min(open,close), high >= max(open,close), > 0);
  * store `ts_utc`, `open`, `high`, `low`, `close` as float64 parquet.

Volume is deliberately NOT carried forward: carrying a constant -1 column would
let a downstream feature silently "weight" by it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[2] / "data"
OUT = Path(__file__).resolve().parents[2] / "data" / "clean"

PAIRS = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")


def src_path(pair: str) -> Path:
    return SRC / f"{pair.lower()}_intraday_1min.csv"


def out_path(pair: str) -> Path:
    return OUT / f"{pair}_1m_clean.parquet"


def build(pair: str) -> dict:
    p = src_path(pair)
    if not p.exists():
        raise FileNotFoundError(p)
    df = pd.read_csv(p, usecols=["time", "open", "high", "low", "close", "volume"])
    n_raw = len(df)

    vol = df["volume"].to_numpy()
    n_real_volume = int((vol != -1.0).sum())

    ts = pd.to_datetime(df["time"], utc=True, errors="coerce")
    n_bad_ts = int(ts.isna().sum())
    df = df.loc[ts.notna()].copy()
    df["ts_utc"] = ts[ts.notna()].values

    n_null_px = int(df[["open", "high", "low", "close"]].isna().any(axis=1).sum())
    df = df.dropna(subset=["open", "high", "low", "close"])

    df = df.sort_values("ts_utc")
    dup = df["ts_utc"].duplicated(keep="last")
    n_dup = int(dup.sum())
    df = df.loc[~dup].reset_index(drop=True)

    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    bad_hl = int((h < l).sum())
    bad_hi = int((h < np.maximum(o, c) - 1e-12).sum())
    bad_lo = int((l > np.minimum(o, c) + 1e-12).sum())
    bad_pos = int(((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).sum())
    if bad_hl or bad_hi or bad_lo or bad_pos:
        raise ValueError(
            f"{pair}: OHLC sanity failed h<l={bad_hl} h<max(o,c)={bad_hi} "
            f"l>min(o,c)={bad_lo} nonpositive={bad_pos}")

    out = df[["ts_utc", "open", "high", "low", "close"]].astype(
        {"open": "float64", "high": "float64", "low": "float64", "close": "float64"})
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path(pair), index=False)

    return dict(pair=pair, rows_raw=n_raw, rows_clean=len(out),
                bad_timestamps=n_bad_ts, null_prices=n_null_px,
                duplicate_timestamps=n_dup, rows_with_real_volume=n_real_volume,
                first=str(out["ts_utc"].iloc[0]), last=str(out["ts_utc"].iloc[-1]))


if __name__ == "__main__":
    pairs = sys.argv[1:] or list(PAIRS)
    for pair in pairs:
        r = build(pair)
        print(" ".join(f"{k}={v}" for k, v in r.items()))
