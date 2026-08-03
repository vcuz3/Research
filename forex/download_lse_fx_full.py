"""Resumable full-history 1-second FX downloader for London Strategic Edge.

The provider caps every bulk export at 2,500,000 rows and permits five export
jobs per hour. This process writes immutable Parquet parts, persists progress,
waits for quota resets, and resumes from the timestamp after the last saved row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from dotenv import dotenv_values
from lse import LSE, LSEError


ROOT = Path(__file__).resolve().parents[1]
FX_DIR = ROOT / "forex" / "data" / "lse" / "fx"
STATE_PATH = FX_DIR / "full_history_state.json"
MANIFEST_PATH = FX_DIR / "full_history_manifest.json"
LOCK_PATH = FX_DIR / ".full_history_download.lock"
SYMBOLS = ("EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD")
ROW_CAP = 2_500_000


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def say(message: str) -> None:
    print(f"{stamp()} {message}", flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parquet_info(path: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    ts = pq.read_table(path, columns=["ts"])["ts"]
    if len(ts) == 0:
        raise RuntimeError(f"empty FX part: {path}")
    return {
        "file": path.name,
        "rows": parquet.metadata.num_rows,
        "bytes": path.stat().st_size,
        "first_utc": pd.Timestamp(ts[0].as_py()).isoformat(),
        "last_utc": pd.Timestamp(ts[-1].as_py()).isoformat(),
        "sha256": sha256(path),
    }


def save_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def api_client() -> LSE:
    key = dotenv_values(ROOT / ".env").get("londonstrategicedge_api")
    if not key:
        raise RuntimeError(f"londonstrategicedge_api is missing from {ROOT / '.env'}")
    return LSE(api_key=str(key), timeout=300)


def initial_state(client: LSE) -> dict[str, Any]:
    catalog = {row["symbol"]: row for row in client.catalog("forex")}
    pairs: dict[str, Any] = {}
    for symbol in SYMBOLS:
        token = symbol.replace("/", "_")
        base = FX_DIR / f"fx_{token}_1s.parquet"
        if not base.exists():
            raise RuntimeError(f"missing initial FX export: {base}")
        paths = [base, *sorted(FX_DIR.glob(f"fx_{token}_1s_part_*.parquet"))]
        parts = [parquet_info(path) for path in paths]
        for previous, current in zip(parts, parts[1:]):
            if pd.Timestamp(current["first_utc"]) <= pd.Timestamp(previous["last_utc"]):
                raise RuntimeError(f"overlapping/out-of-order parts for {symbol}")
        advertised_last = pd.to_datetime(catalog[symbol]["last"], utc=True).floor("s")
        pairs[symbol] = {
            "advertised_first_utc": pd.to_datetime(catalog[symbol]["first"], utc=True).isoformat(),
            "advertised_last_utc": advertised_last.isoformat(),
            "parts": parts,
            "complete": pd.Timestamp(parts[-1]["last_utc"]) >= advertised_last,
        }
    return {
        "created_utc": stamp(),
        "updated_utc": stamp(),
        "row_cap_per_export": ROW_CAP,
        "exports_cap_per_hour": 5,
        "next_symbol_index": 0,
        "pairs": pairs,
    }


def load_state(client: LSE) -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state = initial_state(client)
    save_json(STATE_PATH, state)
    return state


def wait_for_quota(client: LSE, stop_at: datetime | None) -> bool:
    while True:
        usage = client._vault_call("/usage")
        used = int(usage["exports_this_hour"])
        cap = int(usage["exports_cap_hour"])
        if used < cap:
            say(f"export allowance {used}/{cap} used")
            return True
        now = datetime.now(timezone.utc)
        reset = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1, seconds=5))
        if stop_at and reset >= stop_at:
            return False
        remaining = max(1, int((reset - now).total_seconds()))
        say(f"hourly export allowance exhausted; next reset in about {remaining}s")
        while datetime.now(timezone.utc) < reset:
            if stop_at and datetime.now(timezone.utc) >= stop_at:
                return False
            time.sleep(min(30, max(1, (reset - datetime.now(timezone.utc)).total_seconds())))


def next_incomplete(state: dict[str, Any]) -> str | None:
    start = int(state.get("next_symbol_index", 0))
    for offset in range(len(SYMBOLS)):
        index = (start + offset) % len(SYMBOLS)
        symbol = SYMBOLS[index]
        if not state["pairs"][symbol]["complete"]:
            state["next_symbol_index"] = (index + 1) % len(SYMBOLS)
            return symbol
    return None


def export_next_part(client: LSE, state: dict[str, Any], symbol: str) -> None:
    pair = state["pairs"][symbol]
    previous = pair["parts"][-1]
    previous_last = pd.to_datetime(previous["last_utc"], utc=True)
    start_date = previous_last.date()
    archive_end = pd.to_datetime(pair["advertised_last_utc"], utc=True).date() + timedelta(days=1)
    # The API's date parser requires YYYY-MM-DD. Re-request the boundary day,
    # then remove rows through the prior exact timestamp locally.
    end_date = min(archive_end, start_date + timedelta(days=366))
    part_number = len(pair["parts"])
    token = symbol.replace("/", "_")
    filename = f"fx_{token}_1s_part_{part_number:03d}.parquet"
    say(f"{symbol}: starting part {part_number:03d} after {previous_last.isoformat()}")
    job = client._vault_call(
        "/export",
        {
            "dataset": "fx",
            "symbol": symbol,
            "timeframe": "1s",
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "format": "parquet",
        },
    )
    info = client._vault_wait(job["job_id"], poll_seconds=1.5, timeout=7200)
    raw_name = filename.removesuffix(".parquet") + ".raw.parquet"
    raw_path = Path(
        client._vault_download(job["job_id"], raw_name, str(FX_DIR), info)
    )
    raw = pq.read_table(raw_path)
    boundary = pa.scalar(previous_last.to_pydatetime(), type=raw["ts"].type)
    filtered = raw.filter(pc.greater(raw["ts"], boundary))
    if len(filtered) == 0:
        raise RuntimeError(f"{symbol}: provider returned no rows after the prior boundary")
    downloaded = FX_DIR / filename
    pq.write_table(filtered, downloaded, compression="zstd")
    raw_path.unlink()
    current = parquet_info(downloaded)
    current_first = pd.to_datetime(current["first_utc"], utc=True)
    current_last = pd.to_datetime(current["last_utc"], utc=True)
    if current_first <= previous_last:
        raise RuntimeError(f"{symbol}: new part overlaps the prior part")
    advertised_last = pd.to_datetime(pair["advertised_last_utc"], utc=True)
    pair["parts"].append(current)
    pair["complete"] = bool(current_last >= advertised_last)
    state["updated_utc"] = stamp()
    save_json(STATE_PATH, state)
    say(
        f"{symbol}: saved {filename}, {current['rows']:,} rows through "
        f"{current_last.isoformat()} (complete={pair['complete']})"
    )


def save_final_manifest(state: dict[str, Any]) -> None:
    manifest = {
        "created_utc": stamp(),
        "source": "London Strategic Edge vault API",
        "timeframe": "1s",
        "partitioned": True,
        "complete": all(pair["complete"] for pair in state["pairs"].values()),
        "pairs": state["pairs"],
    }
    save_json(MANIFEST_PATH, manifest)


def acquire_lock() -> int:
    FX_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            prior_pid = int(LOCK_PATH.read_text(encoding="utf-8").strip())
            os.kill(prior_pid, 0)
        except (OSError, ValueError):
            LOCK_PATH.unlink(missing_ok=True)
    try:
        descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"download lock already exists: {LOCK_PATH}") from exc
    os.write(descriptor, str(os.getpid()).encode())
    return descriptor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-exports", type=int)
    parser.add_argument("--max-hours", type=float)
    args = parser.parse_args()
    lock_descriptor = acquire_lock()
    try:
        client = api_client()
        state = load_state(client)
        stop_at = (
            datetime.now(timezone.utc) + timedelta(hours=args.max_hours)
            if args.max_hours
            else None
        )
        exports = 0
        consecutive_errors = 0
        while True:
            symbol = next_incomplete(state)
            if symbol is None:
                save_final_manifest(state)
                say(f"all four FX histories complete; manifest at {MANIFEST_PATH}")
                return
            if args.max_exports is not None and exports >= args.max_exports:
                say(f"stopped after requested maximum of {exports} exports")
                return
            if stop_at and datetime.now(timezone.utc) >= stop_at:
                say("stopped at requested time limit")
                return
            if not wait_for_quota(client, stop_at):
                say("stopped before the next quota reset at requested time limit")
                return
            try:
                export_next_part(client, state, symbol)
                exports += 1
                consecutive_errors = 0
            except LSEError as exc:
                consecutive_errors += 1
                say(f"provider error for {symbol}: status={exc.status} {exc.message}")
                if consecutive_errors >= 10:
                    raise
                time.sleep(30)
            except Exception:
                say(f"fatal error for {symbol}; see traceback")
                raise
    finally:
        os.close(lock_descriptor)
        LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        say(f"download stopped: {exc}")
        raise
