"""
Build a clean 1-SECOND RTH parquet for GC from the Databento ohlcv-1s continuous
archive, for accurate intrabar fill/path resolution in the VWAP-band fade.

Rationale: at 1-minute resolution the stop-vs-target ordering inside a bar is
unknowable and must be resolved adversely (rule 3). 1-second bars make the path
essentially observable, so fills and the stop/target sequence are real rather than
assumed. We keep only the RTH window (09:30..16:00 ET) the strategy trades — the
VWAP resets at the 09:30 open, so no earlier bars are needed.

Method mirrors noise_vwap/core/build_clean.py (raw unadjusted GC.v.0; roll flag on
instrument_id change; no session spans a roll because rolls fall between RTH
sessions). Output schema:  ts_utc | symbol | open | high | low | close | volume | is_roll
Written to futures/gc/data/GC_1s_rth.parquet
Run:  python -m futures.gc.vwap_reversion.core.build_clean_1s
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

DB = Path(__file__).resolve().parents[3] / "data" / "databento"
OUT = Path(__file__).resolve().parents[2] / "data"
RAW = DB / "GC_ohlcv-1s_GCv0_20100606_20260718.parquet"
SRC = ["ts_event", "instrument_id", "open", "high", "low", "close", "volume"]

RTH_START = 9 * 60 + 30
RTH_END = 16 * 60


def build() -> pd.DataFrame:
    df = pd.read_parquet(RAW, columns=SRC).rename(columns={"ts_event": "ts_utc"})
    if df["ts_utc"].dt.tz is None:
        df["ts_utc"] = df["ts_utc"].dt.tz_localize("UTC")
    n0 = len(df)

    # RTH filter in ET (before the expensive dedup/sort to shrink the frame)
    et = df["ts_utc"].dt.tz_convert("America/New_York")
    tod = (et.dt.hour * 60 + et.dt.minute).to_numpy()
    keep = (tod >= RTH_START) & (tod < RTH_END)
    df = df[keep].copy()

    df = df.drop_duplicates(subset=["ts_utc"], keep="last")
    df = df.sort_values("ts_utc").reset_index(drop=True)

    ohlc = df[["open", "high", "low", "close"]]
    bad = ohlc.isna().any(axis=1) | (ohlc <= 0).any(axis=1)
    if bad.any():
        print(f"dropping {int(bad.sum())} bad OHLC rows")
        df = df[~bad].reset_index(drop=True)

    df["symbol"] = df["instrument_id"].astype("int64").astype(str)
    df["volume"] = df["volume"].astype("int64")
    df["is_roll"] = df["instrument_id"].ne(df["instrument_id"].shift(1))
    df.loc[0, "is_roll"] = True

    print(f"rows {n0} -> {len(df)} (RTH 1s)  {df['ts_utc'].min()} -> {df['ts_utc'].max()}  "
          f"contracts={df['instrument_id'].nunique()} rolls={int(df['is_roll'].sum())}")
    return df[["ts_utc", "symbol", "open", "high", "low", "close", "volume", "is_roll"]]


def validate(df: pd.DataFrame) -> None:
    et = df["ts_utc"].dt.tz_convert("America/New_York")
    date = et.dt.normalize()
    nb = date.groupby(date).size()
    # any RTH session that internally spans a roll? (should be zero)
    roll_in_sess = df.loc[df["is_roll"], "ts_utc"].dt.tz_convert("America/New_York")
    roll_tod = roll_in_sess.dt.hour * 60 + roll_in_sess.dt.minute
    intra = int(((roll_tod > RTH_START) & (roll_tod < RTH_END - 1)).sum())
    print(f"VALIDATE dup={int(df['ts_utc'].duplicated().sum())} "
          f"sessions={nb.shape[0]} median_bars/sess={int(nb.median())} "
          f"min={int(nb.min())} max={int(nb.max())} intra_session_rolls={intra}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = build()
    validate(df)
    out = OUT / "GC_1s_rth.parquet"
    df.to_parquet(out, index=False)
    print(f"wrote {out}  ({out.stat().st_size/1e6:.0f} MB)")


if __name__ == "__main__":
    main()
