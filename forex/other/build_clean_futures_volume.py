"""Join CME FX-futures volume onto the four canonical spot-FX minute files.

Price OHLC remains the existing IBKR/LSE midpoint source. Volume is matched at
the exact UTC minute from Databento's volume-ranked continuous futures:
EURUSD=6E, GBPUSD=6B, AUDUSD=6A, NZDUSD=6N. Unmatched minutes remain null; they
are not silently interpreted as zero trading.

The script stages and validates every output before moving the prior canonical
Parquets to ``forex/data/archive`` and installing replacements under
``forex/data/clean``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "forex" / "data" / "clean"
ARCHIVE = ROOT / "forex" / "data" / "archive"
DATABENTO = ROOT / "futures" / "data" / "databento"
PAIR_TO_FUTURE = {
    "EURUSD": "6E",
    "GBPUSD": "6B",
    "AUDUSD": "6A",
    "NZDUSD": "6N",
}


def enable_parent_acl_inheritance(path: Path) -> None:
    """Ensure a staged Windows file is readable by users of its destination folder.

    ``os.replace`` preserves the staged file's ACL. Files created by a sandboxed
    process can have protected, owner-only ACLs even when their destination folder
    grants the workspace user access, so explicitly re-enable inheritance after
    installation.
    """
    if os.name != "nt":
        return
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:e"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Could not enable inherited ACLs for {path}: {detail}")
OUTPUT_COLUMNS = ["ts_utc", "open", "high", "low", "close", "volume"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def futures_path(product: str) -> Path:
    paths = sorted(DATABENTO.glob(f"{product}_ohlcv-1m_{product}v0_*.parquet"))
    if len(paths) != 1:
        raise RuntimeError(f"expected one Databento 1m file for {product}, found {paths}")
    return paths[0]


def normalize_futures(frame: pd.DataFrame, product: str) -> pd.DataFrame:
    required = {"ts_event", "volume", "instrument_id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{product}: missing futures columns {sorted(missing)}")
    ts = pd.to_datetime(frame["ts_event"], utc=True, errors="coerce")
    if ts.isna().any():
        raise ValueError(f"{product}: {int(ts.isna().sum())} invalid timestamps")
    out = pd.DataFrame(
        {
            "ts_utc": ts.dt.tz_localize(None).astype("datetime64[us]"),
            "volume": pd.array(frame["volume"], dtype="UInt64"),
            "instrument_id": frame["instrument_id"].astype("uint32"),
        }
    )
    if (out["ts_utc"].dt.second != 0).any() or (out["ts_utc"].dt.microsecond != 0).any():
        raise ValueError(f"{product}: source contains non-minute timestamps")
    if out["ts_utc"].duplicated().any():
        raise ValueError(f"{product}: duplicate futures timestamps")
    if not out["ts_utc"].is_monotonic_increasing:
        raise ValueError(f"{product}: out-of-order futures timestamps")
    return out


def join_volume(spot: pd.DataFrame, futures: pd.DataFrame, pair: str) -> pd.DataFrame:
    required = {"ts_utc", "open", "high", "low", "close"}
    missing = required - set(spot.columns)
    if missing:
        raise ValueError(f"{pair}: missing spot columns {sorted(missing)}")
    left = spot[["ts_utc", "open", "high", "low", "close"]].copy()
    left["ts_utc"] = pd.to_datetime(left["ts_utc"], errors="coerce").astype("datetime64[us]")
    if left["ts_utc"].isna().any():
        raise ValueError(f"{pair}: invalid spot timestamps")
    if left["ts_utc"].duplicated().any() or not left["ts_utc"].is_monotonic_increasing:
        raise ValueError(f"{pair}: spot timestamps must be unique and ordered")
    out = left.merge(futures[["ts_utc", "volume"]], on="ts_utc", how="left", validate="one_to_one")
    out["volume"] = pd.array(out["volume"], dtype="UInt64")
    if len(out) != len(left) or not out["ts_utc"].equals(left["ts_utc"]):
        raise AssertionError(f"{pair}: join changed the spot row set or order")
    return out[OUTPUT_COLUMNS]


def data_quality(
    spot: pd.DataFrame,
    futures: pd.DataFrame,
    output: pd.DataFrame,
) -> dict[str, Any]:
    spot_delta = spot["ts_utc"].diff().dt.total_seconds().div(60)
    matched = output["volume"].notna()
    by_year = output.assign(year=output["ts_utc"].dt.year, matched=matched).groupby("year").agg(
        spot_rows=("ts_utc", "size"), matched_rows=("matched", "sum")
    )
    by_hour = output.assign(hour_utc=output["ts_utc"].dt.hour, matched=matched).groupby("hour_utc").agg(
        spot_rows=("ts_utc", "size"), matched_rows=("matched", "sum")
    )

    def records(table: pd.DataFrame, key: str) -> list[dict[str, Any]]:
        table = table.reset_index()
        table["match_rate"] = table["matched_rows"] / table["spot_rows"]
        return [
            {
                key: int(row[key]),
                "spot_rows": int(row["spot_rows"]),
                "matched_rows": int(row["matched_rows"]),
                "match_rate": float(row["match_rate"]),
            }
            for row in table.to_dict("records")
        ]

    return {
        "spot_rows": int(len(spot)),
        "output_rows": int(len(output)),
        "first_utc": output["ts_utc"].min().isoformat(),
        "last_utc": output["ts_utc"].max().isoformat(),
        "duplicate_output_timestamps": int(output["ts_utc"].duplicated().sum()),
        "out_of_order_output_timestamps": int((spot_delta < 0).sum()),
        "spot_gaps_over_1_minute": int((spot_delta > 1).sum()),
        "largest_spot_gap_minutes": float(spot_delta.max()),
        "matched_futures_minutes": int(matched.sum()),
        "unmatched_futures_minutes": int((~matched).sum()),
        "futures_volume_match_rate": float(matched.mean()),
        "matched_zero_volume_minutes": int((output["volume"] == 0).fillna(False).sum()),
        "negative_futures_volume_minutes": 0,
        "futures_source_rows": int(len(futures)),
        "futures_source_first_utc": futures["ts_utc"].min().isoformat(),
        "futures_source_last_utc": futures["ts_utc"].max().isoformat(),
        "futures_roll_boundaries": int(futures["instrument_id"].ne(futures["instrument_id"].shift()).sum() - 1),
        "coverage_by_year": records(by_year, "year"),
        "coverage_by_utc_hour": records(by_hour, "hour_utc"),
        "unmatched_policy": "nullable UInt64; no zero-fill or as-of fill",
    }


def build_all(archive_tag: str) -> dict[str, Any]:
    CLEAN.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "price_source": "existing canonical spot-FX midpoint OHLC",
        "volume_source": "Databento GLBX.MDP3 ohlcv-1m volume-ranked continuous futures",
        "join": "exact UTC minute, left join preserving every spot row",
        "pairs": {},
    }
    staged: dict[str, Path] = {}
    archives: dict[str, Path] = {}

    with tempfile.TemporaryDirectory(prefix="futures_volume_", dir=CLEAN) as temp:
        temp_dir = Path(temp)
        for pair, product in PAIR_TO_FUTURE.items():
            clean_path = CLEAN / f"{pair}_1m_clean.parquet"
            if not clean_path.exists():
                raise FileNotFoundError(clean_path)
            future_path = futures_path(product)
            print(f"{pair}: reading spot prices and {product} futures volume", flush=True)
            spot = pd.read_parquet(clean_path)
            raw_futures = pd.read_parquet(future_path, columns=["ts_event", "volume", "instrument_id"])
            futures = normalize_futures(raw_futures, product)
            output = join_volume(spot, futures, pair)
            staged_path = temp_dir / clean_path.name
            output.to_parquet(staged_path, index=False, compression="zstd")
            check = pd.read_parquet(staged_path)
            if list(check.columns) != OUTPUT_COLUMNS or len(check) != len(spot):
                raise AssertionError(f"{pair}: staged Parquet verification failed")
            quality = data_quality(spot, futures, output)
            archived_path = ARCHIVE / f"{pair}_1m_clean_pre_futures_volume_{archive_tag}.parquet"
            if archived_path.exists():
                raise FileExistsError(archived_path)
            staged[pair] = staged_path
            archives[pair] = archived_path
            manifest["pairs"][pair] = {
                "futures_product": product,
                "spot_input_path": str(clean_path.relative_to(ROOT)).replace("\\", "/"),
                "spot_input_sha256": sha256(clean_path),
                "futures_input_path": str(future_path.relative_to(ROOT)).replace("\\", "/"),
                "futures_input_sha256": sha256(future_path),
                "archive_path": str(archived_path.relative_to(ROOT)).replace("\\", "/"),
                "output_path": str(clean_path.relative_to(ROOT)).replace("\\", "/"),
                "staged_output_sha256": sha256(staged_path),
                "quality": quality,
            }
            print(
                f"{pair}: matched {quality['matched_futures_minutes']:,}/"
                f"{quality['spot_rows']:,} minutes ({quality['futures_volume_match_rate']:.2%})",
                flush=True,
            )

        moved: list[str] = []
        installed: list[str] = []
        try:
            for pair in PAIR_TO_FUTURE:
                clean_path = CLEAN / f"{pair}_1m_clean.parquet"
                os.replace(clean_path, archives[pair])
                moved.append(pair)
            for pair in PAIR_TO_FUTURE:
                clean_path = CLEAN / f"{pair}_1m_clean.parquet"
                os.replace(staged[pair], clean_path)
                enable_parent_acl_inheritance(clean_path)
                installed.append(pair)
                manifest["pairs"][pair]["output_sha256"] = sha256(clean_path)
                manifest["pairs"][pair]["output_bytes"] = clean_path.stat().st_size
                manifest["pairs"][pair]["output_columns"] = pq.ParquetFile(clean_path).schema_arrow.names
        except Exception:
            for pair in reversed(installed):
                (CLEAN / f"{pair}_1m_clean.parquet").unlink(missing_ok=True)
            for pair in reversed(moved):
                clean_path = CLEAN / f"{pair}_1m_clean.parquet"
                if not clean_path.exists() and archives[pair].exists():
                    os.replace(archives[pair], clean_path)
            raise

    manifest_path = CLEAN / "futures_volume_manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(temporary, manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-tag",
        default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        help="Suffix used for the archived pre-volume files.",
    )
    args = parser.parse_args()
    manifest = build_all(args.archive_tag)
    print(f"wrote {CLEAN / 'futures_volume_manifest.json'}", flush=True)
    print(f"completed {len(manifest['pairs'])} pairs", flush=True)


if __name__ == "__main__":
    main()
