"""
Build a clean 1-minute parquet dataset for RTY (E-mini Russell 2000, CME) from the
Databento continuous-futures file in `futures/data/databento/`.

This mirrors the NQ/ES/GC pipeline (`futures/nq/noise_vwap/core/build_clean.py`)
verbatim in method; only the instrument and source path differ.

We use the RAW (unadjusted continuous, RTY.v.0) file, not a back-adjusted one:
  * The strategy's economics are intraday percentage moves (close/open-1) and the
    session VWAP, both computed WITHIN a single RTH session. Rolls happen between
    RTH sessions, so no session/VWAP/trade spans a roll, and the raw within-session
    move is the real contract's true move.
  * Additive back-adjustment shifts every historical price by a constant, which
    distorts intraday ratios (close/open-1) — exactly what the Noise-Area bands
    are built on. Raw is the faithful choice.

Clean schema (one row per 1-min bar, full 24h):
    ts_utc | symbol | open | high | low | close | volume | is_roll
`ts_utc` is tz-aware UTC. `symbol` is the underlying contract id (instrument_id as
string) so roll detection and diagnostics still work. `is_roll` flags the first bar
of a new contract.

Written to futures/rty/data/RTY_1m_clean.parquet
Run:  python -m futures.rty.noise_vwap.core.build_clean
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# parents[3] = futures (DB source); parents[2] = futures/rty (shared instrument data,
# where core/data.py reads from). Write the clean parquet to the shared parent so the
# loader and builder agree.
DB = Path(__file__).resolve().parents[3] / "data" / "databento"
OUT = Path(__file__).resolve().parents[2] / "data"
RAW = {
    "RTY": DB / "RTY_ohlcv-1m_RTYv0_20100606_20260718.parquet",
}
SRC_COLS = ["ts_event", "instrument_id", "open", "high", "low", "close", "volume"]


def build(inst: str) -> pd.DataFrame:
    df = pd.read_parquet(RAW[inst], columns=SRC_COLS)
    df = df.rename(columns={"ts_event": "ts_utc"})
    # ts_utc is tz-aware UTC already; enforce it.
    if df["ts_utc"].dt.tz is None:
        df["ts_utc"] = df["ts_utc"].dt.tz_localize("UTC")

    n0 = len(df)
    # unique, sorted minutes (defensive; databento is already clean)
    df = df.drop_duplicates(subset=["ts_utc"], keep="last")
    df = df.sort_values("ts_utc").reset_index(drop=True)

    # drop any NaN / non-positive OHLC (defensive)
    bad = (df[["open", "high", "low", "close"]].isna().any(axis=1)
           | (df[["open", "high", "low", "close"]] <= 0).any(axis=1))
    if bad.any():
        print(f"[{inst}] dropping {int(bad.sum())} bad OHLC rows")
        df = df[~bad].reset_index(drop=True)

    df["symbol"] = df["instrument_id"].astype("int64").astype(str)
    df["volume"] = df["volume"].astype("int64")
    df["is_roll"] = df["instrument_id"].ne(df["instrument_id"].shift(1))
    df.loc[0, "is_roll"] = True

    print(f"[{inst}] rows {n0} -> {len(df)}  "
          f"{df['ts_utc'].min()} -> {df['ts_utc'].max()}  "
          f"contracts={df['instrument_id'].nunique()} rolls={int(df['is_roll'].sum())}")
    return df[["ts_utc", "symbol", "open", "high", "low", "close", "volume", "is_roll"]]


def validate(inst: str, df: pd.DataFrame) -> None:
    et = df["ts_utc"].dt.tz_convert("America/New_York")
    tod = et.dt.hour * 60 + et.dt.minute
    date = et.dt.normalize()
    rth = (tod >= 570) & (tod < 960)
    nb = date[rth].groupby(date[rth]).size()
    dup = int(df["ts_utc"].duplicated().sum())
    print(f"[{inst}] VALIDATE  dup_minutes={dup}  "
          f"RTH sessions={nb.shape[0]}  median bars/session={int(nb.median())}  "
          f"full(390)={int((nb==390).sum())}  <350={int((nb<350).sum())}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for inst in ("RTY",):
        df = build(inst)
        validate(inst, df)
        out = OUT / f"{inst}_1m_clean.parquet"
        df.to_parquet(out, index=False)
        print(f"[{inst}] wrote {out}\n")


if __name__ == "__main__":
    main()
