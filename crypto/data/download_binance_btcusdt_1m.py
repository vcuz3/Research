#!/usr/bin/env python3
"""Download and validate Binance Spot BTCUSDT kline history.

Raw official archives and their checksums are retained; a typed Parquet file
and a data-quality report are then built from them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover - depends on the local environment
    raise SystemExit("pyarrow is required; install it with: python -m pip install pyarrow") from exc


BASE_URL = "https://data.binance.vision/data/spot"
SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "1m"
DEFAULT_STARTS = {"1m": date(2017, 8, 17), "1s": date(2020, 1, 1)}
INTERVAL_MS = {"1m": 60_000, "1s": 1_000}
HEADER = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
]
PARQUET_SCHEMA = pa.schema([
    pa.field("open_time", pa.timestamp("ms", tz="UTC"), nullable=False),
    pa.field("open", pa.float64(), nullable=False),
    pa.field("high", pa.float64(), nullable=False),
    pa.field("low", pa.float64(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("volume", pa.float64(), nullable=False),
    pa.field("close_time", pa.timestamp("ms", tz="UTC"), nullable=False),
    pa.field("quote_asset_volume", pa.float64(), nullable=False),
    pa.field("number_of_trades", pa.int64(), nullable=False),
    pa.field("taker_buy_base_asset_volume", pa.float64(), nullable=False),
    pa.field("taker_buy_quote_asset_volume", pa.float64(), nullable=False),
    pa.field("ignore", pa.string(), nullable=False),
])
PARQUET_BATCH_ROWS = 100_000


@dataclass(frozen=True)
class Archive:
    period: str
    name: str
    url: str


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from exc


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def monthly_archive(day: date, interval: str = DEFAULT_INTERVAL) -> Archive:
    stem = f"{SYMBOL}-{interval}-{day:%Y-%m}"
    return Archive("monthly", f"{stem}.zip", f"{BASE_URL}/monthly/klines/{SYMBOL}/{interval}/{stem}.zip")


def daily_archive(day: date, interval: str = DEFAULT_INTERVAL) -> Archive:
    stem = f"{SYMBOL}-{interval}-{day:%Y-%m-%d}"
    return Archive("daily", f"{stem}.zip", f"{BASE_URL}/daily/klines/{SYMBOL}/{interval}/{stem}.zip")


def requested_months(start: date, end: date) -> list[date]:
    result = []
    cursor = month_start(start)
    while cursor <= month_start(end):
        result.append(cursor)
        cursor = next_month(cursor)
    return result


def days_in_month_slice(month: date, start: date, end: date) -> list[date]:
    first = max(month, start)
    last = min(next_month(month) - timedelta(days=1), end)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, target: Path, retries: int, allow_missing: bool = False) -> bool:
    temp = target.with_suffix(target.suffix + ".part")
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "btc-kline-downloader/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            os.replace(temp, target)
            return True
        except urllib.error.HTTPError as exc:
            temp.unlink(missing_ok=True)
            if exc.code == 404 and allow_missing:
                return False
            error = exc
        except (OSError, urllib.error.URLError) as exc:
            temp.unlink(missing_ok=True)
            error = exc
        if attempt < retries:
            time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"download failed: {url}: {error}")


def expected_digest(checksum_path: Path) -> str:
    fields = checksum_path.read_text(encoding="utf-8").strip().split()
    if not fields or len(fields[0]) != 64:
        raise ValueError(f"invalid checksum file: {checksum_path}")
    return fields[0].lower()


def obtain_archive(archive: Archive, raw_dir: Path, retries: int, allow_missing: bool) -> Path | None:
    period_dir = raw_dir / archive.period
    period_dir.mkdir(parents=True, exist_ok=True)
    target = period_dir / archive.name
    checksum = period_dir / f"{archive.name}.CHECKSUM"

    if not checksum.exists() and not fetch(f"{archive.url}.CHECKSUM", checksum, retries, allow_missing):
        return None
    expected = expected_digest(checksum)
    if target.exists() and sha256(target) == expected:
        print(f"verified (cached): {archive.name}")
        return target
    target.unlink(missing_ok=True)
    if not fetch(archive.url, target, retries, allow_missing):
        checksum.unlink(missing_ok=True)
        return None
    actual = sha256(target)
    if actual != expected:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch for {archive.name}: {actual} != {expected}")
    print(f"downloaded + verified: {archive.name}")
    return target


def download(start: date, end: date, output_dir: Path, retries: int, interval: str = DEFAULT_INTERVAL) -> list[Path]:
    raw_dir = output_dir / "raw"
    archives: list[Path] = []
    for month in requested_months(start, end):
        monthly = obtain_archive(monthly_archive(month, interval), raw_dir, retries, allow_missing=True)
        if monthly is not None:
            archives.append(monthly)
            continue
        print(f"monthly archive unavailable for {month:%Y-%m}; trying daily archives")
        for day in days_in_month_slice(month, start, end):
            daily = obtain_archive(daily_archive(day, interval), raw_dir, retries, allow_missing=True)
            if daily is not None:
                archives.append(daily)
            elif day >= DEFAULT_STARTS[interval]:
                print(f"warning: no archive published for {day}", file=sys.stderr)
    if not archives:
        raise RuntimeError("no archives were found for the requested date range")
    return archives


def milliseconds(raw: str) -> tuple[int, str]:
    value = int(raw)
    if value >= 100_000_000_000_000:
        return value // 1000, "microseconds"
    return value, "milliseconds"


def archive_sort_key(path: Path) -> str:
    return path.name


def empty_columns() -> dict[str, list]:
    return {name: [] for name in HEADER}


def write_batch(writer: pq.ParquetWriter, columns: dict[str, list]) -> None:
    if not columns[HEADER[0]]:
        return
    writer.write_table(pa.Table.from_pydict(columns, schema=PARQUET_SCHEMA))
    for values in columns.values():
        values.clear()


def build_dataset(
    archives: list[Path], start: date, end: date, output_dir: Path, interval: str = DEFAULT_INTERVAL
) -> dict:
    start_ms = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    parquet_path = output_dir / f"{SYMBOL}-{interval}-{start}-to-{end}.parquet"
    temp_path = parquet_path.with_suffix(parquet_path.suffix + ".part")
    yearly = Counter()
    hourly = Counter()
    units = Counter()
    rows = duplicates = out_of_order = gaps = missing_bars = invalid_rows = 0
    first_ms = last_ms = previous_ms = None
    interval_ms = INTERVAL_MS[interval]

    columns = empty_columns()
    with pq.ParquetWriter(
        temp_path,
        PARQUET_SCHEMA,
        compression="zstd",
        compression_level=6,
        use_dictionary=True,
        write_statistics=True,
    ) as writer:
        for archive in sorted(archives, key=archive_sort_key):
            with zipfile.ZipFile(archive) as zipped:
                members = [name for name in zipped.namelist() if name.lower().endswith(".csv")]
                if len(members) != 1:
                    raise RuntimeError(f"expected one CSV in {archive}, found {len(members)}")
                with zipped.open(members[0]) as binary, io.TextIOWrapper(binary, encoding="utf-8", newline="") as text:
                    for row in csv.reader(text):
                        if not row or not row[0].isdigit():  # tolerate a header if Binance adds one
                            continue
                        if len(row) != 12:
                            invalid_rows += 1
                            continue
                        open_ms, unit = milliseconds(row[0])
                        if not start_ms <= open_ms < end_ms:
                            continue
                        close_ms, close_unit = milliseconds(row[6])
                        units[unit] += 1
                        if close_unit != unit or close_ms < open_ms:
                            invalid_rows += 1
                            continue
                        if previous_ms is not None:
                            delta = open_ms - previous_ms
                            if delta == 0:
                                duplicates += 1
                                continue
                            if delta < 0:
                                out_of_order += 1
                                continue
                            if delta > interval_ms:
                                gaps += 1
                                missing_bars += delta // interval_ms - 1
                        stamp = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
                        columns["open_time"].append(stamp)
                        columns["open"].append(float(row[1]))
                        columns["high"].append(float(row[2]))
                        columns["low"].append(float(row[3]))
                        columns["close"].append(float(row[4]))
                        columns["volume"].append(float(row[5]))
                        columns["close_time"].append(datetime.fromtimestamp(close_ms / 1000, tz=timezone.utc))
                        columns["quote_asset_volume"].append(float(row[7]))
                        columns["number_of_trades"].append(int(row[8]))
                        columns["taker_buy_base_asset_volume"].append(float(row[9]))
                        columns["taker_buy_quote_asset_volume"].append(float(row[10]))
                        columns["ignore"].append(row[11])
                        if len(columns["open_time"]) >= PARQUET_BATCH_ROWS:
                            write_batch(writer, columns)
                        yearly[str(stamp.year)] += 1
                        hourly[f"{stamp.hour:02d}:00"] += 1
                        rows += 1
                        first_ms = open_ms if first_ms is None else first_ms
                        last_ms = previous_ms = open_ms
        write_batch(writer, columns)
    os.replace(temp_path, parquet_path)

    expected_rows = (end_ms - start_ms) // interval_ms
    leading_missing = (first_ms - start_ms) // interval_ms if first_ms is not None else expected_rows
    trailing_missing = (end_ms - interval_ms - last_ms) // interval_ms if last_ms is not None else 0

    report = {
        "source": "Binance Spot public data archives",
        "symbol": SYMBOL,
        "interval": interval,
        "requested_start_utc": str(start),
        "requested_end_utc_inclusive": str(end),
        "first_bar_utc": datetime.fromtimestamp(first_ms / 1000, tz=timezone.utc).isoformat() if first_ms else None,
        "last_bar_utc": datetime.fromtimestamp(last_ms / 1000, tz=timezone.utc).isoformat() if last_ms else None,
        "rows": rows,
        "requested_calendar_bars": expected_rows,
        "coverage_fraction": rows / expected_rows if expected_rows else None,
        "leading_bars_before_first_bar": leading_missing,
        "trailing_bars_after_last_bar": trailing_missing,
        "duplicate_timestamps_dropped": duplicates,
        "out_of_order_rows_dropped": out_of_order,
        "invalid_rows_dropped": invalid_rows,
        "gap_events": gaps,
        "missing_bars_inside_coverage": missing_bars,
        "rows_by_year": dict(sorted(yearly.items())),
        "rows_by_utc_hour": dict(sorted(hourly.items())),
        "source_timestamp_units_seen": dict(units),
        "output_timestamp_type": "timestamp[ms, tz=UTC]",
        "output_format": "Parquet with Zstandard compression",
        "output_schema": str(PARQUET_SCHEMA),
        "archive_count": len(archives),
        "output_file": parquet_path.name,
        "output_sha256": sha256(parquet_path),
        "notes": [
            "UTC continuous-market coverage; no session calendar or roll boundaries apply.",
            "Gaps are reported, not filled. Never silently forward-fill OHLCV data.",
            "Raw archives and official CHECKSUM files are retained under raw/.",
        ],
    }
    report_path = output_dir / f"BTCUSDT-{interval}-data-quality.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {parquet_path}")
    print(f"wrote {report_path}")
    return report


def main(default_interval: str = DEFAULT_INTERVAL) -> int:
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", choices=sorted(INTERVAL_MS), default=default_interval)
    parser.add_argument("--start", type=parse_date, help="UTC date, inclusive (defaults: 2017-08-17 for 1m; 2020-01-01 for 1s)")
    parser.add_argument("--end", type=parse_date, default=yesterday, help="UTC date, inclusive (default: yesterday)")
    parser.add_argument("--output-dir", type=Path, help="default: crypto/data/binance_spot_btcusdt_<interval>")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--download-only", action="store_true", help="verify archives but skip Parquet/report generation")
    args = parser.parse_args()
    if args.start is None:
        args.start = DEFAULT_STARTS[args.interval]
    if args.output_dir is None:
        args.output_dir = Path(__file__).resolve().parent / f"binance_spot_btcusdt_{args.interval}"
    if args.start > args.end:
        parser.error("--start must be on or before --end")
    if args.end >= datetime.now(timezone.utc).date():
        parser.error("--end must be before the current UTC date (only complete days are downloaded)")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    archives = download(args.start, args.end, args.output_dir, args.retries, args.interval)
    manifest = {"symbol": SYMBOL, "interval": args.interval, "archives": [str(path.relative_to(args.output_dir)) for path in archives]}
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if not args.download_only:
        report = build_dataset(archives, args.start, args.end, args.output_dir, args.interval)
        print(json.dumps({key: report[key] for key in ("rows", "gap_events", "missing_bars_inside_coverage")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
