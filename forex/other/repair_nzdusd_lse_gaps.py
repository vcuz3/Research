"""Repair the documented NZDUSD IBKR holes from independent LSE 1-minute bars.

This is a staged hybrid-source repair. ``download`` obtains three immutable
London Strategic Edge (LSE) one-minute exports. ``audit`` measures target
coverage and cross-vendor agreement. ``build`` creates a candidate while
asserting that every pre-existing canonical row is byte-for-byte unchanged.
``promote`` archives the original before atomically replacing it.

The canonical file is never changed by download, audit, or build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from forex.repair_fx_ibkr_gaps import (
        BAR_COLUMNS, CLEAN, INVENTORY, RAW, REPAIR, WORKSPACE,
        assert_ohlc, load_clean, save_json, sha256, stamp,
    )
except ModuleNotFoundError:  # Direct execution: sys.path starts at forex/.
    from repair_fx_ibkr_gaps import (
        BAR_COLUMNS, CLEAN, INVENTORY, RAW, REPAIR, WORKSPACE,
        assert_ohlc, load_clean, save_json, sha256, stamp,
    )


SOURCE = REPAIR / "lse_1m_source"
LSE_STATE = REPAIR / "lse_1m_state.json"
LSE_AUDIT = REPAIR / "lse_1m_audit.json"
PATCH = REPAIR / "NZDUSD_1m_lse_gap_patch.parquet"
CANDIDATE = REPAIR / "NZDUSD_1m_clean_hybrid_repaired.parquet"
VALIDATION = REPAIR / "lse_validation.json"
REPORT = REPAIR / "LSE_REPAIR_REPORT.md"
ROW_CAP = 2_500_000
PIP = 0.0001

# Each range is comfortably below the provider's 2.5-million-row export cap at
# one-minute resolution. Slight boundary overlap is removed locally.
CHUNKS = (
    ("LSE-001", "2011-12-01", "2017-01-01"),
    ("LSE-002", "2017-01-01", "2022-01-01"),
    ("LSE-003", "2022-01-01", "2026-08-01"),
)


def source_path(chunk_id: str) -> Path:
    return SOURCE / f"{chunk_id}_NZDUSD_1m.parquet"


def load_inventory() -> dict[str, Any]:
    if not INVENTORY.exists():
        raise SystemExit("Run repair_fx_ibkr_gaps.py inventory first")
    value = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if sha256(CLEAN) != value["canonical_sha256"]:
        raise SystemExit("Canonical NZDUSD changed since inventory; rebuild inventory")
    return value


def expected_index(inventory: dict[str, Any]) -> pd.DatetimeIndex:
    values = [ts for window in inventory["windows"] for ts in window["expected_utc"]]
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True)).sort_values()


def normalize_lse(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.rename(columns={"ts": "ts_utc"})
    missing = set(BAR_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"LSE source missing columns: {sorted(missing)}")
    frame = frame[BAR_COLUMNS].copy()
    frame["ts_utc"] = pd.to_datetime(frame.ts_utc, utc=True)
    frame = frame.drop_duplicates("ts_utc", keep="last")
    return frame.sort_values("ts_utc", kind="stable").reset_index(drop=True)


def parquet_info(path: Path) -> dict[str, Any]:
    frame = normalize_lse(pd.read_parquet(path))
    assert_ohlc(frame, path.name)
    return {
        "file": path.name,
        "rows": len(frame),
        "bytes": path.stat().st_size,
        "first_utc": frame.ts_utc.iloc[0].isoformat(),
        "last_utc": frame.ts_utc.iloc[-1].isoformat(),
        "sha256": sha256(path),
    }


def load_state() -> dict[str, Any]:
    if LSE_STATE.exists():
        return json.loads(LSE_STATE.read_text(encoding="utf-8"))
    return {"schema_version": 1, "created_utc": stamp(), "chunks": {}}


def lse_client():
    from dotenv import dotenv_values
    from lse import LSE

    key = dotenv_values(WORKSPACE / ".env").get("londonstrategicedge_api")
    if not key:
        raise SystemExit("londonstrategicedge_api is missing from workspace .env")
    return LSE(api_key=str(key), timeout=300)


def wait_for_quota(client) -> None:
    while True:
        usage = client._vault_call("/usage")
        used = int(usage["exports_this_hour"])
        cap = int(usage["exports_cap_hour"])
        if used < cap:
            print(f"LSE export allowance {used}/{cap} used", flush=True)
            return
        now = datetime.now(timezone.utc)
        reset = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1, seconds=5)
        seconds = max(1, int((reset - now).total_seconds()))
        print(f"LSE quota exhausted; reset in about {seconds}s", flush=True)
        time.sleep(min(30, seconds))


def command_download(args: argparse.Namespace) -> None:
    load_inventory()
    SOURCE.mkdir(parents=True, exist_ok=True)
    state = load_state()
    client = lse_client()
    completed_this_run = 0
    for chunk_id, start, end in CHUNKS:
        final = source_path(chunk_id)
        prior = state["chunks"].get(chunk_id)
        if prior and final.exists() and sha256(final) == prior.get("sha256"):
            continue
        if args.max_exports is not None and completed_this_run >= args.max_exports:
            break
        wait_for_quota(client)
        print(f"{chunk_id}: exporting NZD/USD 1m {start} to {end}", flush=True)
        job = client._vault_call("/export", {
            "dataset": "fx", "symbol": "NZD/USD", "timeframe": "1m",
            "start": start, "end": end, "format": "parquet",
        })
        info = client._vault_wait(job["job_id"], poll_seconds=1.5, timeout=7200)
        temporary_name = final.name + ".download"
        temporary = Path(client._vault_download(job["job_id"], temporary_name,
                                                str(SOURCE), info))
        details = parquet_info(temporary)
        if details["rows"] >= ROW_CAP:
            temporary.unlink(missing_ok=True)
            raise SystemExit(f"{chunk_id} hit the provider row cap; split the range")
        os.replace(temporary, final)
        details = parquet_info(final)
        details.update({"start": start, "end": end, "job_id": job["job_id"]})
        state["chunks"][chunk_id] = details
        state["updated_utc"] = stamp()
        save_json(LSE_STATE, state)
        completed_this_run += 1
        print(f"{chunk_id}: saved {details['rows']:,} rows through "
              f"{details['last_utc']}", flush=True)
    complete = sum(source_path(cid).exists() for cid, _, _ in CHUNKS)
    print(f"LSE download progress: {complete}/{len(CHUNKS)} chunks", flush=True)


def load_source() -> pd.DataFrame:
    missing = [cid for cid, _, _ in CHUNKS if not source_path(cid).exists()]
    if missing:
        raise SystemExit(f"Missing LSE chunks: {missing}; run download")
    frames = [normalize_lse(pd.read_parquet(source_path(cid))) for cid, _, _ in CHUNKS]
    source = pd.concat(frames, ignore_index=True)
    source = source.drop_duplicates("ts_utc", keep="last")
    source = source.sort_values("ts_utc", kind="stable").reset_index(drop=True)
    assert_ohlc(source, "combined LSE one-minute source")
    return source


def control_index(inventory: dict[str, Any]) -> pd.DatetimeIndex:
    values: list[pd.Timestamp] = []
    for window in inventory["windows"]:
        start = pd.Timestamp(window["start_utc"])
        values.extend(pd.date_range(start - pd.Timedelta(minutes=30),
                                    start - pd.Timedelta(minutes=1), freq="min"))
        values.extend(pd.date_range(start + pd.Timedelta(minutes=15),
                                    start + pd.Timedelta(minutes=44), freq="min"))
    return pd.DatetimeIndex(values).drop_duplicates().sort_values()


def agreement(source: pd.DataFrame, clean: pd.DataFrame,
              timestamps: pd.DatetimeIndex) -> dict[str, Any]:
    left = clean[clean.ts_utc.isin(timestamps)].set_index("ts_utc")
    right = source[source.ts_utc.isin(timestamps)].set_index("ts_utc")
    joined = left.join(right, how="inner", lsuffix="_ibkr", rsuffix="_lse")
    if joined.empty:
        raise ValueError("No LSE/IBKR overlap control rows")
    difference_frame = pd.DataFrame({
        column: np.abs(joined[f"{column}_ibkr"] - joined[f"{column}_lse"]) / PIP
        for column in ("open", "high", "low", "close")
    }, index=joined.index)
    differences = difference_frame.to_numpy().ravel()
    worst = difference_frame.max(axis=1).nlargest(25)
    by_column = {}
    for column in difference_frame.columns:
        values = difference_frame[column].to_numpy()
        by_column[column] = {
            "median_abs_diff_pips": float(np.median(values)),
            "p95_abs_diff_pips": float(np.quantile(values, 0.95)),
            "p99_abs_diff_pips": float(np.quantile(values, 0.99)),
            "max_abs_diff_pips": float(np.max(values)),
        }
    return {
        "control_minutes_requested": len(timestamps),
        "control_minutes_compared": len(joined),
        "price_values_compared": len(differences),
        "median_abs_diff_pips": float(np.median(differences)),
        "p95_abs_diff_pips": float(np.quantile(differences, 0.95)),
        "p99_abs_diff_pips": float(np.quantile(differences, 0.99)),
        "max_abs_diff_pips": float(np.max(differences)),
        "by_column": by_column,
        "worst_control_minutes": [
            {"ts_utc": ts.isoformat(), "max_abs_diff_pips": float(value)}
            for ts, value in worst.items()
        ],
    }


def reconstruct_window(source_indexed: pd.DataFrame, clean_indexed: pd.DataFrame,
                       start: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Level-align one LSE window to nearby observable IBKR bars.

    LSE is a sparse event feed. A minute without an LSE update is represented
    by the last observed LSE close (flat OHLC), which is the standard empty-bin
    construction for a quote/event series. Provider-specific OHLC offsets are
    the median field differences on the ten canonical bars immediately before
    the target; neither target nor future IBKR values are used.
    """
    target = pd.date_range(start, periods=15, freq="min")
    controls = pd.date_range(start - pd.Timedelta(minutes=10), periods=10, freq="min")
    common = controls.intersection(source_indexed.index).intersection(clean_indexed.index)
    if len(common) < 6:
        raise ValueError(f"{start}: fewer than six cross-vendor control minutes")
    offsets = {
        column: float(np.median(
            clean_indexed.loc[common, column].to_numpy()
            - source_indexed.loc[common, column].to_numpy()
        ))
        for column in ("open", "high", "low", "close")
    }
    reconstructed = source_indexed.reindex(target)[["open", "high", "low", "close"]].copy()
    missing = reconstructed.close.isna()
    prior = clean_indexed.loc[
        start - pd.Timedelta(minutes=30):start - pd.Timedelta(minutes=1)
    ]
    typical_range = float(np.median((prior.high - prior.low).to_numpy()))
    outlier_cap = max(20 * PIP, 5 * typical_range)
    filtered_values = 0
    # LSE occasionally contains an isolated bad field at the top of the hour.
    # Use the median of actual LSE opens/closes within +/-5 minutes only as an
    # outlier reference; in-range source values remain untouched.
    previous_source_close = float(
        clean_indexed.loc[start - pd.Timedelta(minutes=1), "close"] - offsets["close"])
    for position, ts in enumerate(target):
        if missing.iloc[position]:
            reconstructed.loc[ts, ["open", "high", "low", "close"]] = previous_source_close
            continue
        context = source_indexed.loc[
            ts - pd.Timedelta(minutes=5):ts + pd.Timedelta(minutes=5),
            ["open", "close"],
        ]
        center = float(np.median(context.to_numpy().ravel()))
        if abs(float(reconstructed.at[ts, "open"]) - previous_source_close) > outlier_cap:
            reconstructed.at[ts, "open"] = previous_source_close
            filtered_values += 1
        if abs(float(reconstructed.at[ts, "close"]) - center) > outlier_cap:
            reconstructed.at[ts, "close"] = center
            filtered_values += 1
        body_high = max(reconstructed.at[ts, "open"], reconstructed.at[ts, "close"])
        body_low = min(reconstructed.at[ts, "open"], reconstructed.at[ts, "close"])
        if (reconstructed.at[ts, "high"] > body_high + outlier_cap
                or reconstructed.at[ts, "high"] < body_high):
            reconstructed.at[ts, "high"] = body_high
            filtered_values += 1
        if (reconstructed.at[ts, "low"] < body_low - outlier_cap
                or reconstructed.at[ts, "low"] > body_low):
            reconstructed.at[ts, "low"] = body_low
            filtered_values += 1
        previous_source_close = float(reconstructed.at[ts, "close"])
    positions = source_indexed.index.searchsorted(target, side="right") - 1
    if (positions < 0).any():
        raise ValueError(f"{start}: no preceding LSE observation")
    for column, offset in offsets.items():
        reconstructed[column] += offset
    # Field offsets differ, so reset sparse bins to the preceding aligned close
    # after applying them to ensure genuinely flat OHLC bars.
    for position, ts in enumerate(target):
        if not missing.iloc[position]:
            continue
        carried_aligned = (
            reconstructed.close.iloc[position - 1] if position
            else clean_indexed.loc[start - pd.Timedelta(minutes=1), "close"]
        )
        reconstructed.loc[ts, ["open", "high", "low", "close"]] = carried_aligned
    reconstructed["high"] = reconstructed[["open", "high", "close"]].max(axis=1)
    reconstructed["low"] = reconstructed[["open", "low", "close"]].min(axis=1)
    previous_ts = source_indexed.index[positions]
    ages = (target - previous_ts).total_seconds() / 60
    result = reconstructed.reset_index(names="ts_utc")
    return result, {
        "offsets_pips": {column: value / PIP for column, value in offsets.items()},
        "carried_minutes": int(missing.sum()),
        "max_source_age_minutes": float(np.max(ages[missing.to_numpy()])) if missing.any() else 0.0,
        "control_minutes": len(common),
        "outlier_cap_pips": outlier_cap / PIP,
        "filtered_source_values": filtered_values,
    }


def placebo_agreement(source: pd.DataFrame, clean: pd.DataFrame,
                      max_windows: int = 3000) -> dict[str, Any]:
    local = clean.ts_utc.dt.tz_convert("America/New_York")
    starts = clean.loc[
        local.dt.hour.isin((13, 14, 15)) & local.dt.minute.eq(0), "ts_utc"
    ].drop_duplicates().sort_values().tolist()
    if len(starts) > max_windows:
        positions = np.linspace(0, len(starts) - 1, max_windows, dtype=int)
        starts = [starts[position] for position in positions]
    clean_indexed = clean.set_index("ts_utc")
    source_indexed = source.set_index("ts_utc")
    errors: dict[str, list[np.ndarray]] = {column: [] for column in ("open", "high", "low", "close")}
    used = 0
    skipped = 0
    carried = 0
    filtered = 0
    worst: list[tuple[float, str]] = []
    for start in starts:
        target = pd.date_range(start, periods=15, freq="min")
        if len(target.intersection(clean_indexed.index)) != 15:
            skipped += 1
            continue
        try:
            reconstructed, meta = reconstruct_window(source_indexed, clean_indexed, start)
        except ValueError:
            skipped += 1
            continue
        truth = clean_indexed.loc[target]
        row_max = 0.0
        for column in errors:
            values = np.abs(
                reconstructed[column].to_numpy() - truth[column].to_numpy()
            ) / PIP
            errors[column].append(values)
            row_max = max(row_max, float(np.max(values)))
        worst.append((row_max, start.isoformat()))
        carried += meta["carried_minutes"]
        filtered += meta["filtered_source_values"]
        used += 1
    if used == 0:
        raise ValueError("No usable placebo windows")
    flattened = {column: np.concatenate(values) for column, values in errors.items()}
    all_values = np.concatenate(list(flattened.values()))
    worst.sort(reverse=True)
    return {
        "candidate_windows": len(starts), "windows_compared": used,
        "windows_skipped": skipped, "minutes_compared": used * 15,
        "carried_source_minutes": carried,
        "filtered_source_values": filtered,
        "median_abs_error_pips": float(np.median(all_values)),
        "p95_abs_error_pips": float(np.quantile(all_values, 0.95)),
        "p99_abs_error_pips": float(np.quantile(all_values, 0.99)),
        "max_abs_error_pips": float(np.max(all_values)),
        "by_column": {
            column: {
                "median_abs_error_pips": float(np.median(values)),
                "p95_abs_error_pips": float(np.quantile(values, 0.95)),
                "p99_abs_error_pips": float(np.quantile(values, 0.99)),
                "max_abs_error_pips": float(np.max(values)),
            }
            for column, values in flattened.items()
        },
        "worst_windows": [
            {"start_utc": start, "max_abs_error_pips": value}
            for value, start in worst[:25]
        ],
    }


def audit_value(inventory: dict[str, Any], source: pd.DataFrame,
                clean: pd.DataFrame) -> dict[str, Any]:
    expected = expected_index(inventory)
    have = pd.DatetimeIndex(source.ts_utc)
    missing = expected.difference(have)
    present = expected.intersection(have)
    window_counts = []
    incomplete_windows = []
    for window in inventory["windows"]:
        target = pd.DatetimeIndex(pd.to_datetime(window["expected_utc"], utc=True))
        count = len(target.intersection(have))
        window_counts.append(count)
        absent = target.difference(have)
        if len(absent):
            incomplete_windows.append({
                "window_id": window["window_id"], "et_date": window["et_date"],
                "et_hour": window["et_hour"], "present": count,
                "missing": [x.isoformat() for x in absent],
            })
    counts = pd.Series(window_counts)
    value = {
        "schema_version": 1,
        "created_utc": stamp(),
        "source": "London Strategic Edge NZD/USD 1-minute OHLC",
        "source_chunks": [parquet_info(source_path(cid)) for cid, _, _ in CHUNKS],
        "canonical_sha256": sha256(CLEAN),
        "inventory_sha256": sha256(INVENTORY),
        "target_minutes": len(expected),
        "target_minutes_present": len(present),
        "target_minutes_missing": len(missing),
        "complete_windows": int((counts == 15).sum()),
        "incomplete_windows": int((counts != 15).sum()),
        "windows_by_present_minute_count": {
            str(int(k)): int(v) for k, v in counts.value_counts().sort_index().items()
        },
        "first_missing_target_minutes": [x.isoformat() for x in missing[:100]],
        "incomplete_window_details": incomplete_windows,
        "overlap_agreement": agreement(source, clean, control_index(inventory)),
        "placebo_reconstruction": placebo_agreement(source, clean),
    }
    return value


def command_audit(_: argparse.Namespace) -> None:
    inventory = load_inventory()
    source = load_source()
    clean = load_clean()
    value = audit_value(inventory, source, clean)
    save_json(LSE_AUDIT, value)
    print(json.dumps({k: value[k] for k in (
        "target_minutes", "target_minutes_present", "target_minutes_missing",
        "complete_windows", "incomplete_windows", "overlap_agreement",
        "placebo_reconstruction")}, indent=2))


def command_build(args: argparse.Namespace) -> None:
    inventory = load_inventory()
    source = load_source()
    clean = load_clean()
    audit = audit_value(inventory, source, clean)
    save_json(LSE_AUDIT, audit)
    placebo = audit["placebo_reconstruction"]
    if placebo["p95_abs_error_pips"] > args.max_placebo_p95_pips:
        raise SystemExit("Placebo p95 reconstruction error exceeds the declared build limit")
    if placebo["p99_abs_error_pips"] > args.max_placebo_p99_pips:
        raise SystemExit("Placebo p99 reconstruction error exceeds the declared build limit")
    if placebo["max_abs_error_pips"] > args.max_placebo_error_pips:
        raise SystemExit("Placebo maximum reconstruction error exceeds the declared build limit")
    expected = expected_index(inventory)
    source_indexed = source.set_index("ts_utc")
    clean_indexed = clean.set_index("ts_utc")
    patches = []
    reconstruction = []
    for window in inventory["windows"]:
        rebuilt, meta = reconstruct_window(
            source_indexed, clean_indexed, pd.Timestamp(window["start_utc"]))
        patches.append(rebuilt)
        reconstruction.append({"window_id": window["window_id"], **meta})
    patch = pd.concat(patches, ignore_index=True)[BAR_COLUMNS]
    patch = patch.sort_values("ts_utc", kind="stable").reset_index(drop=True)
    assert_ohlc(patch, "LSE repair patch")
    if len(patch) != len(expected):
        raise SystemExit("Patch cardinality differs from expected target minutes")
    if clean.ts_utc.isin(patch.ts_utc).any():
        raise SystemExit("Patch overlaps canonical timestamps")
    max_source_age = max(value["max_source_age_minutes"] for value in reconstruction)
    if max_source_age > args.max_source_age_minutes:
        raise SystemExit(
            f"Maximum carried LSE observation age {max_source_age} minutes exceeds gate")
    candidate = pd.concat([clean, patch], ignore_index=True)
    candidate = candidate.sort_values("ts_utc", kind="stable").reset_index(drop=True)
    assert_ohlc(candidate, "hybrid repaired candidate")
    existing = candidate[candidate.ts_utc.isin(clean.ts_utc)].reset_index(drop=True)
    if not existing.equals(clean.reset_index(drop=True)):
        raise SystemExit("Existing canonical rows changed in candidate")
    PATCH.parent.mkdir(parents=True, exist_ok=True)
    patch.assign(ts_utc=patch.ts_utc.dt.tz_localize(None)).to_parquet(PATCH, index=False)
    candidate.assign(ts_utc=candidate.ts_utc.dt.tz_localize(None)).to_parquet(CANDIDATE, index=False)
    filtered_windows = [
        {"window_id": value["window_id"],
         "filtered_source_values": value["filtered_source_values"],
         "outlier_cap_pips": value["outlier_cap_pips"]}
        for value in reconstruction if value["filtered_source_values"]
    ]
    validation = {
        "schema_version": 1, "created_utc": stamp(), "passed": True,
        "source": audit["source"], "source_is_independent_vendor": True,
        "reconstruction": "causal per-field median alignment on ten preceding IBKR bars; "
                          "empty LSE minutes carry the last LSE close as flat OHLC; "
                          "gross LSE field outliers use a symmetric +/-5-minute LSE-only "
                          "reference and are recorded for sensitivity exclusion",
        "canonical_rows_before": len(clean), "patch_rows": len(patch),
        "candidate_rows": len(candidate), "existing_rows_unchanged": True,
        "target_minutes_missing_after": 0,
        "raw_lse_target_minutes": audit["target_minutes_present"],
        "carried_target_minutes": int(sum(x["carried_minutes"] for x in reconstruction)),
        "filtered_target_source_values": int(sum(
            x["filtered_source_values"] for x in reconstruction)),
        "filtered_target_windows": filtered_windows,
        "max_source_age_minutes": max_source_age,
        "max_source_age_minutes_gate": args.max_source_age_minutes,
        "placebo_gates_pips": {
            "p95": args.max_placebo_p95_pips,
            "p99": args.max_placebo_p99_pips,
            "maximum": args.max_placebo_error_pips,
        },
        "placebo_reconstruction": placebo,
        "overlap_agreement": audit["overlap_agreement"],
        "original_sha256": sha256(CLEAN), "patch_sha256": sha256(PATCH),
        "candidate_sha256": sha256(CANDIDATE),
        "inventory_sha256": sha256(INVENTORY), "audit_sha256": sha256(LSE_AUDIT),
    }
    save_json(VALIDATION, validation)
    REPORT.write_text(
        "# NZDUSD hybrid-source gap repair\n\n"
        "Status: candidate built and validated; promotion is a separate command.\n\n"
        f"- Existing IBKR rows preserved exactly: yes ({len(clean):,})\n"
        f"- Missing minutes reconstructed from LSE: {len(patch):,}\n"
        f"- Direct LSE minutes: {audit['target_minutes_present']:,}\n"
        f"- Sparse LSE minutes carried as flat OHLC: "
        f"{sum(x['carried_minutes'] for x in reconstruction):,}\n"
        f"- Gross LSE outlier fields replaced: "
        f"{sum(x['filtered_source_values'] for x in reconstruction):,} "
        f"across {len(filtered_windows):,} windows\n"
        f"- Placebo median / p95 / p99 error: "
        f"{placebo['median_abs_error_pips']:.4f} / "
        f"{placebo['p95_abs_error_pips']:.4f} / "
        f"{placebo['p99_abs_error_pips']:.4f} pips\n"
        "- Alignment is causal: per-field median difference on ten preceding known bars.\n"
        "- Gross-field filtering uses a symmetric +/-5-minute LSE-only reference; "
        "affected windows are listed in validation for sensitivity exclusion.\n"
        "- Source caveat: repaired timestamps are adjusted LSE OHLC, not actual IBKR bars.\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, indent=2))


def command_promote(_: argparse.Namespace) -> None:
    inventory = load_inventory()
    if not VALIDATION.exists() or not CANDIDATE.exists():
        raise SystemExit("Run build first")
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    if not validation.get("passed"):
        raise SystemExit("Validation has not passed")
    if sha256(INVENTORY) != validation["inventory_sha256"]:
        raise SystemExit("Inventory changed after validation")
    if sha256(CLEAN) != validation["original_sha256"]:
        raise SystemExit("Canonical changed after validation")
    if sha256(CANDIDATE) != validation["candidate_sha256"]:
        raise SystemExit("Candidate changed after validation")
    date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = RAW.parent / f"NZDUSD_1m_clean_pre_lse_gap_repair_{date}.parquet"
    if backup.exists():
        raise SystemExit(f"Backup already exists: {backup}")
    shutil.copy2(CLEAN, backup)
    if sha256(backup) != validation["original_sha256"]:
        raise SystemExit("Backup verification failed")
    temporary = CLEAN.with_suffix(".parquet.repair.tmp")
    shutil.copy2(CANDIDATE, temporary)
    if sha256(temporary) != validation["candidate_sha256"]:
        temporary.unlink(missing_ok=True)
        raise SystemExit("Promotion temporary-file verification failed")
    os.replace(temporary, CLEAN)
    validation.update({
        "promoted_utc": stamp(), "backup_path": backup.relative_to(WORKSPACE).as_posix(),
        "backup_sha256": sha256(backup), "canonical_sha256_after": sha256(CLEAN),
    })
    save_json(VALIDATION, validation)
    print(f"Promoted hybrid repaired NZDUSD; backup={backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download")
    download.add_argument("--max-exports", type=int)
    download.set_defaults(func=command_download)
    audit = sub.add_parser("audit")
    audit.set_defaults(func=command_audit)
    build = sub.add_parser("build")
    build.add_argument("--max-placebo-p95-pips", type=float, default=1.25)
    build.add_argument("--max-placebo-p99-pips", type=float, default=3.5)
    build.add_argument("--max-placebo-error-pips", type=float, default=50.0)
    build.add_argument("--max-source-age-minutes", type=float, default=15.0)
    build.set_defaults(func=command_build)
    promote = sub.add_parser("promote")
    promote.set_defaults(func=command_promote)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
