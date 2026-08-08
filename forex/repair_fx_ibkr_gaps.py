"""Audit and repair the documented NZDUSD IBKR 1-minute archive holes.

The repair is deliberately staged and resumable. Nothing overwrites the
canonical clean Parquet until every target minute is fetched, the candidate
passes all invariants, and ``promote`` archives the original first.

Run from the workspace root::

    python forex/repair_fx_ibkr_gaps.py inventory
    .venv/Scripts/python.exe forex/repair_fx_ibkr_gaps.py fetch
    python forex/repair_fx_ibkr_gaps.py build
    python forex/repair_fx_ibkr_gaps.py promote

Only the empirically documented NZDUSD holes at 13:00-13:14, 14:00-14:14,
and 15:00-15:14 America/New_York are targeted. The 17:00 rollover is excluded:
it mixes provider conventions with genuine daily-roll/reopen effects and needs
a separate specification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


FOREX = Path(__file__).resolve().parent
WORKSPACE = FOREX.parent
DATA = FOREX / "data"
CLEAN = DATA / "clean" / "NZDUSD_1m_clean.parquet"
RAW = DATA / "archive" / "nzdusd_intraday_1min.csv"
REPAIR = DATA / "repair" / "ibkr_nzdusd"
REQUESTS = REPAIR / "requests"
INVENTORY = REPAIR / "inventory.json"
STATE = REPAIR / "fetch_state.json"
PATCH = REPAIR / "NZDUSD_1m_ibkr_gap_patch.parquet"
CANDIDATE = REPAIR / "NZDUSD_1m_clean_repaired.parquet"
VALIDATION = REPAIR / "validation.json"
REPORT = REPAIR / "REPORT.md"

PAIR = "NZDUSD"
TARGET_ET_HOURS = (13, 14, 15)
BAR_COLUMNS = ["ts_utc", "open", "high", "low", "close"]
PIP = 0.0001


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_clean(path: Path = CLEAN) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=BAR_COLUMNS)
    frame["ts_utc"] = pd.to_datetime(frame.ts_utc, utc=True)
    return frame.sort_values("ts_utc", kind="stable").reset_index(drop=True)


def assert_ohlc(frame: pd.DataFrame, label: str) -> None:
    if frame.empty:
        raise ValueError(f"{label}: empty frame")
    if frame[BAR_COLUMNS].isna().any().any():
        raise ValueError(f"{label}: null OHLC/timestamp")
    if frame.ts_utc.duplicated().any():
        raise ValueError(f"{label}: duplicate timestamps")
    if not frame.ts_utc.is_monotonic_increasing:
        raise ValueError(f"{label}: timestamps out of order")
    o, h, l, c = (frame[x].to_numpy(float) for x in ["open", "high", "low", "close"])
    if ((h < l) | (h < np.maximum(o, c) - 1e-12) |
            (l > np.minimum(o, c) + 1e-12) | (np.minimum.reduce([o, h, l, c]) <= 0)).any():
        raise ValueError(f"{label}: OHLC sanity failure")


def detect_target_holes(timestamps: pd.Series) -> pd.DataFrame:
    """Return 15-minute acquisition holes with normal trading after minute 15."""
    ts = pd.to_datetime(timestamps, utc=True).dropna().drop_duplicates().sort_values()
    et = ts.dt.tz_convert("America/New_York")
    frame = pd.DataFrame({
        "et_date": et.dt.tz_localize(None).dt.normalize(),
        "et_hour": et.dt.hour,
        "minute": et.dt.minute,
    })
    frame = frame.loc[frame.et_hour.isin(TARGET_ET_HOURS)]
    cells = (frame.groupby(["et_date", "et_hour"], observed=True).minute
             .agg(pre15=lambda s: int((s < 15).sum()),
                  post15=lambda s: int((s >= 15).sum())).reset_index())
    holes = cells.loc[cells.pre15.eq(0) & cells.post15.ge(40)].copy()
    holes = holes.sort_values(["et_date", "et_hour"]).reset_index(drop=True)
    holes["window_id"] = [f"WIN-{i:04d}" for i in range(1, len(holes) + 1)]
    starts = []
    expected = []
    for row in holes.itertuples(index=False):
        local = (pd.Timestamp(row.et_date) + pd.Timedelta(hours=int(row.et_hour)))
        local = local.tz_localize("America/New_York")
        start = local.tz_convert("UTC")
        starts.append(start.isoformat())
        expected.append([(start + pd.Timedelta(minutes=m)).isoformat() for m in range(15)])
    holes["start_utc"] = starts
    holes["expected_utc"] = expected
    return holes


def request_plan(holes: pd.DataFrame) -> list[dict[str, Any]]:
    """Greedily pair consecutive ET dates; each request remains <=2 days."""
    dates = sorted(pd.Timestamp(x) for x in holes.et_date.unique())
    groups: list[list[pd.Timestamp]] = []
    i = 0
    while i < len(dates):
        group = [dates[i]]
        if i + 1 < len(dates) and dates[i + 1] - dates[i] <= pd.Timedelta(days=1):
            group.append(dates[i + 1])
            i += 1
        groups.append(group)
        i += 1

    plan = []
    for number, group in enumerate(groups, 1):
        last = group[-1] + pd.Timedelta(hours=16, minutes=30)
        end_local = last.tz_localize("America/New_York")
        ids = holes.loc[holes.et_date.isin(group), "window_id"].tolist()
        plan.append({
            "request_id": f"REQ-{number:04d}",
            "et_dates": [d.date().isoformat() for d in group],
            "end_utc": end_local.tz_convert("UTC").isoformat(),
            "duration": "2 D" if len(group) == 2 else "1 D",
            "window_ids": ids,
        })
    return plan


def raw_clean_timestamp_parity(clean: pd.DataFrame) -> dict[str, Any]:
    if not RAW.exists():
        return {"checked": False, "reason": f"missing {RAW}"}
    raw = pd.read_csv(RAW, usecols=["time"])
    raw_ts = pd.to_datetime(raw.time, utc=True, errors="coerce").dropna()
    raw_ts = raw_ts.drop_duplicates().sort_values().reset_index(drop=True)
    clean_ts = clean.ts_utc.reset_index(drop=True)
    equal = len(raw_ts) == len(clean_ts) and np.array_equal(
        raw_ts.to_numpy(dtype="datetime64[ns]"), clean_ts.to_numpy(dtype="datetime64[ns]"))
    if not equal:
        raise ValueError("archived raw and clean timestamp sets differ")
    return {"checked": True, "equal": True, "raw_rows": len(raw),
            "raw_unique_valid_timestamps": len(raw_ts), "clean_rows": len(clean_ts)}


def command_inventory(_: argparse.Namespace) -> None:
    clean = load_clean()
    assert_ohlc(clean, "canonical clean")
    parity = raw_clean_timestamp_parity(clean)
    holes = detect_target_holes(clean.ts_utc)
    if len(holes) == 0:
        raise SystemExit("No target holes found; refusing to create an empty repair inventory")
    plan = request_plan(holes)
    value = {
        "schema_version": 1,
        "created_utc": stamp(),
        "pair": PAIR,
        "source": "IBKR CASH MIDPOINT 1-minute",
        "canonical_path": CLEAN.relative_to(WORKSPACE).as_posix(),
        "canonical_sha256": sha256(CLEAN),
        "archived_raw_path": RAW.relative_to(WORKSPACE).as_posix(),
        "archived_raw_sha256": sha256(RAW) if RAW.exists() else None,
        "raw_clean_timestamp_parity": parity,
        "target_et_hours": list(TARGET_ET_HOURS),
        "excluded_window": "17:00 ET rollover/reopen is not part of this repair",
        "windows": holes.to_dict("records"),
        "requests": plan,
        "summary": {
            "target_windows": len(holes),
            "target_minutes": len(holes) * 15,
            "unique_et_dates": int(holes.et_date.nunique()),
            "planned_requests": len(plan),
            "windows_by_hour": {str(k): int(v) for k, v in holes.groupby("et_hour").size().items()},
        },
    }
    # Convert pandas timestamps left by to_dict.
    for window in value["windows"]:
        window["et_date"] = pd.Timestamp(window["et_date"]).date().isoformat()
        for key in ("pre15", "post15", "et_hour"):
            window[key] = int(window[key])
    save_json(INVENTORY, value)
    if not STATE.exists():
        save_json(STATE, {"schema_version": 1, "created_utc": stamp(),
                          "inventory_sha256": sha256(INVENTORY), "requests": {}})
    print(json.dumps(value["summary"], indent=2))
    print(f"inventory={INVENTORY}")


def load_env() -> None:
    # Use the same lightweight loader as the repository's IBKR downloader.
    sys.path.insert(0, str(FOREX))
    import fred_common as fc
    fc.load_env_file(WORKSPACE / ".env")
    fc.load_env_file(FOREX / ".env")


def normalize_ibkr_bars(bars, util) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=BAR_COLUMNS)
    frame = util.df(bars).rename(columns={"date": "ts_utc"})
    frame["ts_utc"] = pd.to_datetime(frame.ts_utc, utc=True)
    frame = frame[BAR_COLUMNS].dropna().drop_duplicates("ts_utc", keep="last")
    frame = frame.sort_values("ts_utc").reset_index(drop=True)
    assert_ohlc(frame, "IBKR response")
    return frame


def expected_index(inventory: dict, window_ids: list[str]) -> pd.DatetimeIndex:
    wanted = set(window_ids)
    values = [ts for w in inventory["windows"] if w["window_id"] in wanted
              for ts in w["expected_utc"]]
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True)).sort_values()


def compare_overlap(fetched: pd.DataFrame, clean_indexed: pd.DataFrame) -> dict[str, Any]:
    overlap = fetched.set_index("ts_utc").join(clean_indexed, how="inner", lsuffix="_new", rsuffix="_old")
    if overlap.empty:
        return {"rows": 0, "max_abs_diff_pips": None, "p99_abs_diff_pips": None}
    diffs = []
    for col in ["open", "high", "low", "close"]:
        diffs.append((overlap[f"{col}_new"] - overlap[f"{col}_old"]).abs().to_numpy() / PIP)
    diff = np.concatenate(diffs)
    return {"rows": len(overlap), "max_abs_diff_pips": float(np.max(diff)),
            "p99_abs_diff_pips": float(np.quantile(diff, 0.99)),
            "exact_fraction": float(np.mean(diff == 0))}


def fetch_one(ib, contract, util, end_utc: str, duration: str) -> pd.DataFrame:
    end = pd.Timestamp(end_utc).to_pydatetime()
    bars = ib.reqHistoricalData(contract, endDateTime=end, durationStr=duration,
                                barSizeSetting="1 min", whatToShow="MIDPOINT",
                                useRTH=False, formatDate=2)
    return normalize_ibkr_bars(bars, util)


def command_fetch(args: argparse.Namespace) -> None:
    if not INVENTORY.exists():
        raise SystemExit("Run inventory first")
    load_env()
    try:
        from ib_async import IB, Forex, util
    except ImportError as exc:
        raise SystemExit("ib_async is required; use .venv\\Scripts\\python.exe") from exc
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if sha256(CLEAN) != inventory["canonical_sha256"]:
        raise SystemExit("Canonical clean file changed since inventory; rebuild inventory")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("inventory_sha256") != sha256(INVENTORY):
        raise SystemExit("Fetch state belongs to a different inventory; archive/reset repair state")
    clean = load_clean().set_index("ts_utc")[["open", "high", "low", "close"]]
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "4001"))
    client_id = int(os.environ.get("IB_CLIENT_ID", str(args.client_id)))
    ib = IB()
    print(f"Connecting read-only to IBKR {host}:{port} clientId={client_id}")
    try:
        ib.connect(host, port, clientId=client_id, readonly=True, timeout=20)
    except Exception as exc:
        raise SystemExit(f"IBKR connection failed: {type(exc).__name__}: {exc}") from exc
    try:
        contract = Forex(PAIR)
        ib.qualifyContracts(contract)
        done = 0
        REQUESTS.mkdir(parents=True, exist_ok=True)
        for request in inventory["requests"]:
            rid = request["request_id"]
            prior = state["requests"].get(rid, {})
            path = REQUESTS / f"{rid}.parquet"
            if prior.get("status") == "complete" and path.exists():
                continue
            if args.max_requests is not None and done >= args.max_requests:
                break
            expected = expected_index(inventory, request["window_ids"])
            print(f"{rid}: {request['duration']} ending {request['end_utc']} for {len(expected)} target minutes")
            try:
                fetched = fetch_one(ib, contract, util, request["end_utc"], request["duration"])
                calls = 1
                have = pd.DatetimeIndex(fetched.ts_utc)
                missing = expected.difference(have)
                # A missing target in a daily request gets a narrow four-hour retry
                # with the target window safely inside, not at a response boundary.
                fallback_frames = []
                if len(missing):
                    windows = [w for w in inventory["windows"]
                               if w["window_id"] in request["window_ids"]]
                    for window in windows:
                        widx = pd.DatetimeIndex(pd.to_datetime(window["expected_utc"], utc=True))
                        if len(widx.difference(have)) == 0:
                            continue
                        fallback_end = pd.Timestamp(window["start_utc"]) + pd.Timedelta(hours=2)
                        time.sleep(args.pacing_sleep)
                        fallback_frames.append(fetch_one(ib, contract, util,
                                                          fallback_end.isoformat(), "4 H"))
                        calls += 1
                    fetched = pd.concat([fetched, *fallback_frames], ignore_index=True)
                    fetched = fetched.drop_duplicates("ts_utc", keep="last").sort_values("ts_utc").reset_index(drop=True)
                    assert_ohlc(fetched, f"{rid} merged response")
                    have = pd.DatetimeIndex(fetched.ts_utc)
                    missing = expected.difference(have)
                temporary = path.with_suffix(".parquet.tmp")
                fetched.assign(ts_utc=fetched.ts_utc.dt.tz_localize(None)).to_parquet(temporary, index=False)
                os.replace(temporary, path)
                overlap = compare_overlap(fetched, clean)
                status = "complete" if len(missing) == 0 else "incomplete"
                state["requests"][rid] = {
                    "status": status, "updated_utc": stamp(), "file": path.name,
                    "calls": calls, "rows": len(fetched), "target_minutes": len(expected),
                    "missing_target_minutes": [x.isoformat() for x in missing],
                    "overlap": overlap,
                }
                save_json(STATE, state)
                print(f"{rid}: {status}; rows={len(fetched):,}; missing={len(missing)}; overlap={overlap}")
                done += 1
                time.sleep(args.pacing_sleep)
            except Exception as exc:
                state["requests"][rid] = {"status": "error", "updated_utc": stamp(),
                                           "error": f"{type(exc).__name__}: {exc}"}
                save_json(STATE, state)
                raise
    finally:
        ib.disconnect()
    complete = sum(x.get("status") == "complete" for x in state["requests"].values())
    print(f"fetch progress: {complete}/{len(inventory['requests'])} requests complete")


def read_request_files() -> pd.DataFrame:
    frames = []
    for path in sorted(REQUESTS.glob("REQ-*.parquet")):
        frame = pd.read_parquet(path, columns=BAR_COLUMNS)
        frame["ts_utc"] = pd.to_datetime(frame.ts_utc, utc=True)
        frames.append(frame)
    if not frames:
        raise SystemExit("No request checkpoints found")
    out = pd.concat(frames, ignore_index=True).drop_duplicates("ts_utc", keep="last")
    return out.sort_values("ts_utc").reset_index(drop=True)


def command_build(_: argparse.Namespace) -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("inventory_sha256") != sha256(INVENTORY):
        raise SystemExit("Fetch state belongs to a different inventory; refusing build")
    pending = [r["request_id"] for r in inventory["requests"]
               if state["requests"].get(r["request_id"], {}).get("status") != "complete"]
    if pending:
        raise SystemExit(f"Cannot build: {len(pending)} requests are not complete; first={pending[:5]}")
    if sha256(CLEAN) != inventory["canonical_sha256"]:
        raise SystemExit("Canonical clean file changed since inventory; rebuild inventory")
    fetched = read_request_files()
    assert_ohlc(fetched, "combined fetched requests")
    expected = expected_index(inventory, [w["window_id"] for w in inventory["windows"]])
    patch = fetched.loc[fetched.ts_utc.isin(expected)].copy()
    patch = patch.drop_duplicates("ts_utc", keep="last").sort_values("ts_utc").reset_index(drop=True)
    missing = expected.difference(pd.DatetimeIndex(patch.ts_utc))
    extra = pd.DatetimeIndex(patch.ts_utc).difference(expected)
    if len(missing) or len(extra) or len(patch) != len(expected):
        raise SystemExit(f"Patch coverage mismatch: rows={len(patch)} expected={len(expected)} missing={len(missing)} extra={len(extra)}")
    assert_ohlc(patch, "target patch")
    clean = load_clean()
    if pd.DatetimeIndex(clean.ts_utc).intersection(pd.DatetimeIndex(patch.ts_utc)).size:
        raise SystemExit("Patch overlaps canonical timestamps; target inventory is stale")
    candidate = pd.concat([clean, patch], ignore_index=True).sort_values("ts_utc").reset_index(drop=True)
    assert_ohlc(candidate, "repaired candidate")
    remaining = detect_target_holes(candidate.ts_utc)
    if len(remaining):
        raise SystemExit(f"Candidate still has {len(remaining)} target holes")
    # Prove all old rows are byte-for-byte equal in value after the merge.
    old = clean.set_index("ts_utc")[["open", "high", "low", "close"]]
    carried = candidate.loc[candidate.ts_utc.isin(clean.ts_utc)].set_index("ts_utc")[["open", "high", "low", "close"]]
    if not old.equals(carried):
        raise SystemExit("Existing canonical rows changed in candidate")
    REPAIR.mkdir(parents=True, exist_ok=True)
    patch.assign(ts_utc=patch.ts_utc.dt.tz_localize(None)).to_parquet(PATCH, index=False)
    candidate.assign(ts_utc=candidate.ts_utc.dt.tz_localize(None)).to_parquet(CANDIDATE, index=False)
    validation = {
        "created_utc": stamp(), "status": "passed", "original_rows": len(clean),
        "patch_rows": len(patch), "candidate_rows": len(candidate),
        "expected_candidate_rows": len(clean) + len(expected),
        "target_holes_before": len(inventory["windows"]), "target_holes_after": 0,
        "original_sha256": sha256(CLEAN), "patch_sha256": sha256(PATCH),
        "candidate_sha256": sha256(CANDIDATE), "existing_rows_unchanged": True,
        "duplicates": int(candidate.ts_utc.duplicated().sum()),
        "out_of_order": int((candidate.ts_utc.diff().dropna() <= pd.Timedelta(0)).sum()),
    }
    save_json(VALIDATION, validation)
    REPORT.write_text(
        "# NZDUSD IBKR Gap Repair\n\n"
        f"Status: **candidate validated, not yet promoted**.\n\n"
        f"- Target windows: {len(inventory['windows']):,}\n"
        f"- Added minutes: {len(patch):,}\n"
        f"- Original rows: {len(clean):,}\n"
        f"- Candidate rows: {len(candidate):,}\n"
        f"- Remaining 13:00-15:14 ET target holes: 0\n"
        f"- Existing rows unchanged: yes\n"
        f"- Candidate SHA-256: `{validation['candidate_sha256']}`\n\n"
        "The 17:00 ET rollover/reopen window was intentionally not patched.\n",
        encoding="utf-8")
    print(json.dumps(validation, indent=2))


def command_promote(_: argparse.Namespace) -> None:
    if not VALIDATION.exists() or not CANDIDATE.exists():
        raise SystemExit("Run build and inspect REPORT.md before promote")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    if validation.get("status") != "passed":
        raise SystemExit("Validation status is not passed")
    current_hash = sha256(CLEAN)
    if current_hash != inventory["canonical_sha256"] or current_hash != validation["original_sha256"]:
        raise SystemExit("Canonical file changed since validation; refusing promotion")
    if sha256(CANDIDATE) != validation["candidate_sha256"]:
        raise SystemExit("Candidate hash changed since validation")
    date = datetime.now(timezone.utc).date().isoformat().replace("-", "")
    backup = DATA / "archive" / f"NZDUSD_1m_clean_pre_ibkr_gap_repair_{date}.parquet"
    if backup.exists():
        if sha256(backup) != current_hash:
            raise SystemExit(f"Existing backup differs: {backup}")
    else:
        shutil.copy2(CLEAN, backup)
        if sha256(backup) != current_hash:
            raise SystemExit("Backup verification failed")
    temporary = CLEAN.with_suffix(".parquet.repair.tmp")
    shutil.copy2(CANDIDATE, temporary)
    if sha256(temporary) != validation["candidate_sha256"]:
        raise SystemExit("Promotion temporary copy failed hash check")
    os.replace(temporary, CLEAN)
    if sha256(CLEAN) != validation["candidate_sha256"]:
        raise SystemExit("Promoted canonical hash mismatch")
    validation["promoted_utc"] = stamp()
    validation["backup_path"] = backup.relative_to(WORKSPACE).as_posix()
    validation["canonical_sha256_after"] = sha256(CLEAN)
    save_json(VALIDATION, validation)
    print(f"Promoted repaired NZDUSD clean data; backup={backup}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory")
    inv.set_defaults(func=command_inventory)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--client-id", type=int, default=27)
    fetch.add_argument("--max-requests", type=int)
    fetch.add_argument("--pacing-sleep", type=float, default=11.0)
    fetch.set_defaults(func=command_fetch)
    build = sub.add_parser("build")
    build.set_defaults(func=command_build)
    promote = sub.add_parser("promote")
    promote.set_defaults(func=command_promote)
    return p


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
