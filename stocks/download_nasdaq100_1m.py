"""Build and download a point-in-time Nasdaq-100 1-minute archive.

The downloader deliberately fails closed when London Strategic Edge (LSE) does
not cover every constituent during its index-membership interval.  An explicit
``--allow-provider-gaps`` override can download the available subset, but that
subset must not be described as survivorship-bias-free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import requests
from dotenv import dotenv_values
from lse import LSE, LSEError


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "stocks"
UNIVERSE_DIR = PROJECT_ROOT / "universe"
STATE_PATH = PROJECT_ROOT / "download_state.json"
MANIFEST_PATH = PROJECT_ROOT / "manifest.json"
LOCK_PATH = PROJECT_ROOT / ".download.lock"
LOG_PATH = PROJECT_ROOT / "download.log"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
START = pd.Timestamp("2016-08-11")
END = pd.Timestamp("2026-08-11")
TIMEFRAME = "1m"
USER_AGENT = "Nasdaq100ResearchArchive/1.0 (personal research)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def say(message: str) -> None:
    line = f"{utc_now()} {message}"
    print(line, flush=True)
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def api_client() -> LSE:
    key = dotenv_values(RESEARCH_ROOT / ".env").get("londonstrategicedge_api")
    if not key:
        raise RuntimeError(
            f"londonstrategicedge_api is missing from {RESEARCH_ROOT / '.env'}"
        )
    return LSE(api_key=str(key), timeout=300)


def fetch_membership_tables() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    response = requests.get(
        WIKI_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    response.raise_for_status()
    source_sha256 = hashlib.sha256(response.content).hexdigest()
    tables = pd.read_html(StringIO(response.text))
    current = tables[0].copy()
    changes = tables[1].copy()
    if "Ticker" not in current or not isinstance(changes.columns, pd.MultiIndex):
        raise RuntimeError("Nasdaq-100 source tables changed shape")
    current = current.rename(columns={"Ticker": "ticker", "Company": "company"})
    current["ticker"] = current["ticker"].astype(str).str.strip()
    changes.columns = [
        "date",
        "added",
        "added_name",
        "removed",
        "removed_name",
        "reason",
    ]
    changes["date"] = pd.to_datetime(changes["date"], errors="raise")
    for column in ("added", "removed"):
        changes[column] = (
            changes[column].fillna("").astype(str).str.strip().replace("nan", "")
        )
    return current, changes, source_sha256


def reconstruct_periods(
    current: pd.DataFrame,
    changes: pd.DataFrame,
    start: pd.Timestamp = START,
    end: pd.Timestamp = END,
) -> pd.DataFrame:
    """Reconstruct half-open [member_from, member_to) membership intervals."""
    relevant = changes.loc[(changes["date"] >= start) & (changes["date"] <= end)].copy()
    active = set(current["ticker"])
    # Reverse all in-window events to obtain the membership set at START.
    for row in relevant.sort_values("date", ascending=False).itertuples(index=False):
        if row.added and row.removed and row.added == row.removed:
            continue
        if row.added:
            active.discard(row.added)
        if row.removed:
            active.add(row.removed)

    opened = {ticker: start for ticker in active}
    intervals: list[dict[str, Any]] = []
    for event_date, group in relevant.sort_values("date").groupby("date", sort=True):
        # A same-ticker corporate identity replacement does not alter symbol membership.
        same = {
            row.added
            for row in group.itertuples(index=False)
            if row.added and row.added == row.removed
        }
        for ticker in group["removed"]:
            if not ticker or ticker in same:
                continue
            began = opened.pop(ticker, None)
            if began is not None:
                intervals.append(
                    {"ticker": ticker, "member_from": began, "member_to": event_date}
                )
        for ticker in group["added"]:
            if not ticker or ticker in same:
                continue
            opened.setdefault(ticker, event_date)

    for ticker, began in opened.items():
        intervals.append({"ticker": ticker, "member_from": began, "member_to": end})
    result = pd.DataFrame(intervals).sort_values(["ticker", "member_from"])
    if (result["member_to"] <= result["member_from"]).any():
        raise RuntimeError("non-positive membership interval reconstructed")
    return result.reset_index(drop=True)


def prepare(client: LSE) -> dict[str, Any]:
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current, changes, source_sha256 = fetch_membership_tables()
    periods = reconstruct_periods(current, changes)
    catalog = pd.DataFrame(client.catalog("stocks")).sort_values("symbol")

    current.to_csv(UNIVERSE_DIR / "current_constituents_source.csv", index=False)
    changes.to_csv(UNIVERSE_DIR / "component_changes_source.csv", index=False)
    periods.to_csv(UNIVERSE_DIR / "membership_periods.csv", index=False)
    catalog.to_csv(UNIVERSE_DIR / "lse_stock_catalog.csv", index=False)

    bounds = periods.groupby("ticker").agg(
        required_from=("member_from", "min"), required_to=("member_to", "max")
    )
    by_symbol = catalog.set_index("symbol")
    rows: list[dict[str, Any]] = []
    tolerance = pd.Timedelta(days=7)

    def probe(ticker: str, begin: pd.Timestamp, finish: pd.Timestamp, order: str) -> str | None:
        for attempt in range(6):
            try:
                candles = client.candles(
                    ticker,
                    "1d",
                    start=begin.date().isoformat(),
                    end=finish.date().isoformat(),
                    limit=1,
                    order=order,
                    dataset="stocks",
                )
                return candles[0]["timestamp"] if candles else None
            except LSEError as exc:
                if exc.status != 429 or attempt == 5:
                    raise
                time.sleep(5)
        return None

    for ticker, required in bounds.iterrows():
        found = ticker in by_symbol.index
        required_from = pd.Timestamp(required.required_from)
        required_to = pd.Timestamp(required.required_to)
        row: dict[str, Any] = {
            "ticker": ticker,
            "required_from": required_from.date().isoformat(),
            "required_to": required_to.date().isoformat(),
            "lse_catalog_present": found,
            "lse_first": None,
            "lse_last": None,
            "start_candle_probe": None,
            "end_candle_probe": None,
            "lse_downloadable": False,
            "membership_coverage_complete": False,
            "issue": "",
        }
        covers_start = False
        covers_end = False
        if found:
            item = by_symbol.loc[ticker]
            first = pd.Timestamp(item["first"])
            last = pd.Timestamp(item["last"])
            covers_start = first <= required_from + tolerance
            covers_end = last >= required_to - tolerance
            row.update(
                {
                    "lse_first": first.isoformat(),
                    "lse_last": last.isoformat(),
                }
            )
        # Raw-tape catalog bounds can be newer than the pre-aggregated candle
        # archive, so probe only the bounds not already proven by the catalog.
        if not covers_start:
            stamp = probe(ticker, required_from, required_from + timedelta(days=15), "asc")
            row["start_candle_probe"] = stamp
            covers_start = bool(stamp and pd.Timestamp(stamp).tz_localize(None) <= required_from + tolerance)
        if not covers_end:
            stamp = probe(ticker, required_to - timedelta(days=15), required_to, "desc")
            row["end_candle_probe"] = stamp
            covers_end = bool(stamp and pd.Timestamp(stamp).tz_localize(None) >= required_to - tolerance)
        complete = bool(covers_start and covers_end)
        issues = []
        if not covers_start:
            issues.append("no LSE candle coverage when membership began")
        if not covers_end:
            issues.append("no LSE candle coverage when membership ended")
        row["lse_downloadable"] = bool(found or row["start_candle_probe"] or row["end_candle_probe"])
        row["membership_coverage_complete"] = complete
        row["issue"] = "; ".join(issues)
        rows.append(row)
    audit = pd.DataFrame(rows).sort_values("ticker")
    audit.to_csv(UNIVERSE_DIR / "provider_coverage_audit.csv", index=False)

    complete = bool(audit["membership_coverage_complete"].all())
    manifest = {
        "created_utc": utc_now(),
        "window": {"start": START.date().isoformat(), "end": END.date().isoformat()},
        "timeframe": TIMEFRAME,
        "price_source": "London Strategic Edge vault API",
        "membership_source": WIKI_URL,
        "membership_source_sha256": source_sha256,
        "current_security_count": int(len(current)),
        "historical_ticker_count": int(len(audit)),
        "membership_interval_count": int(len(periods)),
        "lse_catalog_present_count": int(audit["lse_catalog_present"].sum()),
        "lse_downloadable_count": int(audit["lse_downloadable"].sum()),
        "membership_covered_count": int(audit["membership_coverage_complete"].sum()),
        "survivorship_bias_gate": "passed" if complete else "failed",
        "download_complete": False,
        "warning": None
        if complete
        else "LSE does not cover every historical constituent over its membership interval.",
    }
    atomic_json(MANIFEST_PATH, manifest)
    say(
        f"prepared {len(audit)} historical tickers; "
        f"{int(audit['lse_catalog_present'].sum())} in LSE catalog; "
        f"{int(audit['membership_coverage_complete'].sum())} cover membership intervals"
    )
    return manifest


def parquet_record(path: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    frame = pd.read_parquet(path)
    timestamp_column = "ts" if "ts" in frame else "timestamp"
    timestamps = pd.to_datetime(frame[timestamp_column], utc=True)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    prices = [column for column in ("open", "high", "low", "close") if column in frame]
    invalid_ohlc = 0
    if len(prices) == 4:
        invalid_ohlc = int(
            (
                (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
                | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
            ).sum()
        )
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "rows": parquet.metadata.num_rows,
        "columns": parquet.schema_arrow.names,
        "first_utc": timestamps.min().isoformat(),
        "last_utc": timestamps.max().isoformat(),
        "duplicate_timestamps": int(timestamps.duplicated().sum()),
        "out_of_order_timestamps": int((timestamps.diff().dt.total_seconds() < 0).sum()),
        "null_ohlc_cells": int(frame[prices].isna().sum().sum()) if prices else None,
        "invalid_ohlc_envelopes": invalid_ohlc,
    }


def acquire_lock() -> None:
    try:
        descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"download lock already exists: {LOCK_PATH}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))


def wait_for_export_quota(client: LSE) -> None:
    while True:
        usage = client._vault_call("/usage")
        used = int(usage["exports_this_hour"])
        cap = int(usage["exports_cap_hour"])
        if used < cap:
            say(f"LSE export allowance {used}/{cap} used")
            return
        now = datetime.now(timezone.utc)
        reset = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1, seconds=5)
        seconds = max(1, int((reset - now).total_seconds()))
        say(f"hourly export allowance exhausted; waiting about {seconds}s")
        while datetime.now(timezone.utc) < reset:
            time.sleep(min(30, max(1, (reset - datetime.now(timezone.utc)).total_seconds())))


def download(client: LSE, allow_provider_gaps: bool) -> None:
    if not MANIFEST_PATH.exists():
        prepare(client)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["survivorship_bias_gate"] != "passed" and not allow_provider_gaps:
        raise RuntimeError(
            "survivorship-bias gate failed; inspect universe/provider_coverage_audit.csv. "
            "Use --allow-provider-gaps only to fetch a knowingly incomplete subset."
        )
    audit = pd.read_csv(UNIVERSE_DIR / "provider_coverage_audit.csv")
    queue = audit.loc[audit["lse_downloadable"].astype(bool)].copy()
    state = (
        json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if STATE_PATH.exists()
        else {"created_utc": utc_now(), "files": {}, "errors": {}}
    )
    acquire_lock()
    try:
        for number, row in enumerate(queue.itertuples(index=False), start=1):
            ticker = row.ticker
            destination = DATA_DIR / f"stocks_{ticker}_{TIMEFRAME}.parquet"
            if destination.exists():
                if ticker not in state["files"]:
                    state["files"][ticker] = parquet_record(destination)
                    atomic_json(STATE_PATH, state)
                say(f"[{number}/{len(queue)}] {ticker}: existing file verified")
                continue
            wait_for_export_quota(client)
            say(
                f"[{number}/{len(queue)}] {ticker}: requesting "
                f"{row.required_from} to {row.required_to}"
            )
            try:
                result = client.history(
                    ticker,
                    dataset="stocks",
                    timeframe=TIMEFRAME,
                    start=row.required_from,
                    end=row.required_to,
                    dest=str(DATA_DIR),
                    dataframe=False,
                    timeout=7200,
                )
                result_path = Path(result)
                if result_path != destination:
                    os.replace(result_path, destination)
                state["files"][ticker] = parquet_record(destination)
                state["errors"].pop(ticker, None)
                state["updated_utc"] = utc_now()
                atomic_json(STATE_PATH, state)
                say(f"{ticker}: saved {state['files'][ticker]['rows']:,} rows")
            except Exception as exc:
                state["errors"][ticker] = {"at_utc": utc_now(), "error": repr(exc)}
                atomic_json(STATE_PATH, state)
                say(f"{ticker}: ERROR {exc!r}")
    finally:
        LOCK_PATH.unlink(missing_ok=True)
    verify()


def verify() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    audit = pd.read_csv(UNIVERSE_DIR / "provider_coverage_audit.csv")
    records = []
    for path in sorted(DATA_DIR.glob(f"stocks_*_{TIMEFRAME}.parquet")):
        records.append(parquet_record(path))
    downloaded = {record["file"].removeprefix("stocks_").removesuffix(f"_{TIMEFRAME}.parquet") for record in records}
    required = set(audit["ticker"])
    quality_pass = all(
        record["rows"] > 0
        and record["duplicate_timestamps"] == 0
        and record["out_of_order_timestamps"] == 0
        and record["null_ohlc_cells"] == 0
        and record["invalid_ohlc_envelopes"] == 0
        for record in records
    )
    manifest.update(
        {
            "verified_utc": utc_now(),
            "downloaded_ticker_count": len(downloaded),
            "missing_download_tickers": sorted(required - downloaded),
            "data_quality_gate": "passed" if quality_pass else "failed",
            "download_complete": bool(required <= downloaded and quality_pass),
            "files": records,
        }
    )
    atomic_json(MANIFEST_PATH, manifest)
    say(
        f"verified {len(records)} files; quality={manifest['data_quality_gate']}; "
        f"complete={manifest['download_complete']}"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "download", "verify", "status"))
    parser.add_argument(
        "--allow-provider-gaps",
        action="store_true",
        help="Download LSE's available subset even when survivorship coverage fails.",
    )
    args = parser.parse_args()
    if args.command == "status":
        if MANIFEST_PATH.exists():
            print(MANIFEST_PATH.read_text(encoding="utf-8"))
        else:
            print("not prepared")
        return
    if args.command == "verify":
        verify()
        return
    client = api_client()
    if args.command == "prepare":
        prepare(client)
    else:
        download(client, args.allow_provider_gaps)


if __name__ == "__main__":
    main()
