"""Rebuild the futures-volume-joined FX minute dataset into a working directory.

The canonical files under forex/data/clean/ are currently held by an exclusive
lock from other processes (Jupyter kernels). Their *inputs* — the archived
pre-volume spot parquets and the Databento continuous-futures files — are
readable, so we reproduce the exact same left join here and validate the result
against forex/data/clean/futures_volume_manifest.json before using it.

This is a faithful reproduction of forex/build_clean_futures_volume.py's join.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\VuDoa\Research")
ARCHIVE = ROOT / "forex" / "data" / "archive"
DATABENTO = ROOT / "futures" / "data" / "databento"
MANIFEST = ROOT / "forex" / "data" / "clean" / "futures_volume_manifest.json"
ARCHIVE_TAG = "20260809T101545Z"

PAIR_TO_FUTURE = {"EURUSD": "6E", "GBPUSD": "6B", "AUDUSD": "6A", "NZDUSD": "6N"}
WORK = Path(
    r"C:\Users\VuDoa\AppData\Local\Temp\claude"
    r"\C--Users-VuDoa-Research-forex\471b556d-4c10-4dc8-861c-cd123504e10e"
    r"\scratchpad\joined"
)


def _spot_path(pair: str) -> Path:
    return ARCHIVE / f"{pair}_1m_clean_pre_futures_volume_{ARCHIVE_TAG}.parquet"


def _fut_path(product: str) -> Path:
    hits = sorted(DATABENTO.glob(f"{product}_ohlcv-1m_{product}v0_*.parquet"))
    if len(hits) != 1:
        raise RuntimeError(f"{product}: expected 1 databento file, found {hits}")
    return hits[0]


def build_pair(pair: str, force: bool = False) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"{pair}_joined.parquet"
    if out.exists() and not force:
        return out
    product = PAIR_TO_FUTURE[pair]
    spot = pd.read_parquet(_spot_path(pair), columns=["ts_utc", "open", "high", "low", "close"])
    spot["ts_utc"] = pd.to_datetime(spot["ts_utc"]).astype("datetime64[us]")
    fut = pd.read_parquet(_fut_path(product), columns=["ts_event", "volume", "instrument_id"])
    ts = pd.to_datetime(fut["ts_event"], utc=True).dt.tz_localize(None).astype("datetime64[us]")
    fut = pd.DataFrame({"ts_utc": ts, "volume": pd.array(fut["volume"], dtype="Int64")})
    fut = fut.dropna(subset=["ts_utc"]).drop_duplicates("ts_utc").sort_values("ts_utc")
    merged = spot.merge(fut, on="ts_utc", how="left", validate="one_to_one")
    merged.to_parquet(out, index=False, compression="zstd")
    return out


def validate_pair(pair: str) -> dict:
    out = build_pair(pair)
    df = pd.read_parquet(out)
    man = json.loads(MANIFEST.read_text())["pairs"][pair]["quality"]
    matched = df["volume"].notna().sum()
    res = {
        "pair": pair,
        "rows": len(df),
        "man_rows": man["spot_rows"],
        "rows_ok": len(df) == man["spot_rows"],
        "matched": int(matched),
        "man_matched": man["matched_futures_minutes"],
        "match_ok": int(matched) == man["matched_futures_minutes"],
        "match_rate": float(matched / len(df)),
        "man_match_rate": man["futures_volume_match_rate"],
    }
    return res


def load_pair(pair: str) -> pd.DataFrame:
    """Load a joined pair with a proper DatetimeIndex and float volume."""
    df = pd.read_parquet(build_pair(pair))
    df["ts_utc"] = pd.to_datetime(df["ts_utc"])
    df["volume"] = df["volume"].astype("float64")  # NaN where unmatched
    return df


if __name__ == "__main__":
    import sys

    pairs = sys.argv[1:] or list(PAIR_TO_FUTURE)
    for p in pairs:
        r = validate_pair(p)
        flag = "OK" if (r["rows_ok"] and r["match_ok"]) else "MISMATCH"
        print(
            f"[{flag}] {p}: rows {r['rows']:,} (man {r['man_rows']:,}) "
            f"matched {r['matched']:,} (man {r['man_matched']:,}) "
            f"rate {r['match_rate']:.6f} vs {r['man_match_rate']:.6f}",
            flush=True,
        )
