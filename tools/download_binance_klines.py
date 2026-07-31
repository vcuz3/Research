"""Download and validate Binance public kline history.

The bulk history comes from https://data.binance.vision.  The final tail comes
from the public market-data REST API so the result reaches the latest completed
candle.  Downloads are resumable and official archive checksums are verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


ARCHIVE_ROOT = "https://data.binance.vision/data/spot"
API_ROOT = "https://data-api.binance.vision"
COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]
FLOAT_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]


@dataclass(frozen=True)
class ArchiveItem:
    frequency: str
    period: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--start", default="2017-06-01", help="UTC date, inclusive")
    parser.add_argument(
        "--end",
        default=None,
        help="UTC timestamp/date, exclusive; default is the current open minute",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/binance/spot"),
        help="Root containing SYMBOL/INTERVAL",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--request-sleep", type=float, default=0.05)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def utc_timestamp(value: str | None, *, default_now: bool = False) -> pd.Timestamp:
    if value is None and default_now:
        return pd.Timestamp.now(tz="UTC").floor("min")
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp


def month_starts(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    first = pd.Timestamp(start.year, start.month, 1, tz="UTC")
    end_inclusive = end - pd.Timedelta(microseconds=1)
    last = pd.Timestamp(end_inclusive.year, end_inclusive.month, 1, tz="UTC")
    return list(pd.date_range(first, last, freq="MS", tz="UTC"))


def archive_url(symbol: str, interval: str, item: ArchiveItem) -> str:
    name = f"{symbol}-{interval}-{item.period}.zip"
    return f"{ARCHIVE_ROOT}/{item.frequency}/klines/{symbol}/{interval}/{name}"


def download_archive(
    session: requests.Session,
    url: str,
    destination: Path,
    timeout: float,
    force: bool,
) -> bool:
    checksum_path = destination.with_suffix(destination.suffix + ".CHECKSUM")
    checksum_url = url + ".CHECKSUM"
    if destination.exists() and checksum_path.exists() and not force:
        expected = checksum_path.read_text(encoding="utf-8").split()[0].lower()
        actual = sha256_file(destination)
        if actual == expected:
            return True

    checksum_response = session.get(checksum_url, timeout=timeout)
    if checksum_response.status_code == 404:
        return False
    checksum_response.raise_for_status()
    checksum_text = checksum_response.text.strip()
    expected = checksum_text.split()[0].lower()

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with session.get(url, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    actual = sha256_file(temporary)
    if actual != expected:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"Checksum mismatch for {url}: expected {expected}, got {actual}")
    temporary.replace(destination)
    checksum_path.write_text(checksum_text + "\n", encoding="utf-8")
    return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_timestamp_ms(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="raise").astype("int64")
    # Binance Spot archives switched from milliseconds to microseconds in 2025.
    microseconds = values.abs() >= 100_000_000_000_000
    values.loc[microseconds] = values.loc[microseconds] // 1000
    return values


def parse_archive(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"Expected one CSV in {path}, found {csv_names}")
        with archive.open(csv_names[0]) as handle:
            frame = pd.read_csv(handle, header=None, names=COLUMNS)
    return normalize_frame(frame)


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["open_time"] = normalize_timestamp_ms(frame["open_time"])
    frame["close_time"] = normalize_timestamp_ms(frame["close_time"])
    for column in FLOAT_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("float64")
    frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="raise").astype("int64")
    frame = frame.drop(columns=["ignore"])
    return frame.sort_values("open_time").drop_duplicates("open_time", keep="last")


def convert_archive(zip_path: Path, parquet_path: Path, force: bool) -> pd.DataFrame:
    if parquet_path.exists() and not force:
        return pd.read_parquet(parquet_path)
    frame = parse_archive(zip_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(parquet_path, compression="zstd", index=False)
    return frame


def fetch_rest_tail(
    session: requests.Session,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    timeout: float,
    request_sleep: float,
) -> pd.DataFrame:
    rows: list[list[object]] = []
    cursor = start_ms
    while cursor < end_ms:
        response = session.get(
            f"{API_ROOT}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": 1000,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1][0]) + 60_000
        if next_cursor <= cursor:
            raise RuntimeError("Binance REST pagination did not advance")
        cursor = next_cursor
        time.sleep(request_sleep)
    if not rows:
        return pd.DataFrame(columns=COLUMNS[:-1])
    return normalize_frame(pd.DataFrame(rows, columns=COLUMNS))


def write_quality_report(
    parts: list[Path],
    requested_start: pd.Timestamp,
    requested_end: pd.Timestamp,
    output_path: Path,
) -> dict[str, object]:
    frames = [pd.read_parquet(path, columns=["open_time", "open", "high", "low", "close", "volume"])
              for path in sorted(parts)]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if combined.empty:
        raise RuntimeError("No Binance candles were downloaded")
    combined = combined.sort_values("open_time", kind="stable")
    duplicate_count = int(combined["open_time"].duplicated().sum())
    unique = combined.drop_duplicates("open_time", keep="last")
    diffs = unique["open_time"].diff()
    gap_rows = unique.loc[diffs.gt(60_000), ["open_time"]].copy()
    gap_rows["missing_minutes"] = ((diffs[diffs.gt(60_000)] // 60_000) - 1).astype("int64")
    invalid_ohlc = int(
        (
            (unique["high"] < unique[["open", "close", "low"]].max(axis=1))
            | (unique["low"] > unique[["open", "close", "high"]].min(axis=1))
            | (unique["volume"] < 0)
        ).sum()
    )
    first_ms = int(unique["open_time"].iloc[0])
    last_ms = int(unique["open_time"].iloc[-1])
    off_grid = unique.loc[unique["open_time"].mod(60_000).ne(0), "open_time"]
    report = {
        "requested_start_utc": requested_start.isoformat(),
        "requested_end_exclusive_utc": requested_end.isoformat(),
        "first_candle_utc": pd.to_datetime(first_ms, unit="ms", utc=True).isoformat(),
        "last_candle_utc": pd.to_datetime(last_ms, unit="ms", utc=True).isoformat(),
        "rows": int(len(unique)),
        "duplicate_rows_across_parts": duplicate_count,
        "out_of_order_rows_within_sorted_dataset": 0,
        "gap_count": int(len(gap_rows)),
        "missing_minutes": int(gap_rows["missing_minutes"].sum()) if len(gap_rows) else 0,
        "off_grid_timestamp_rows": int(len(off_grid)),
        "first_off_grid_candle_utc": (
            pd.to_datetime(int(off_grid.iloc[0]), unit="ms", utc=True).isoformat()
            if len(off_grid)
            else None
        ),
        "invalid_ohlcv_rows": invalid_ohlc,
        "parts": len(parts),
        "gaps": [
            {
                "next_candle_utc": pd.to_datetime(int(row.open_time), unit="ms", utc=True).isoformat(),
                "missing_minutes": int(row.missing_minutes),
            }
            for row in gap_rows.itertuples(index=False)
        ],
    }
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    args = parse_args()
    symbol = args.symbol.upper()
    if args.interval != "1m":
        raise ValueError("This downloader currently validates pagination for interval=1m only")
    start = utc_timestamp(args.start)
    end = utc_timestamp(args.end, default_now=True)
    if end <= start:
        raise ValueError("--end must be later than --start")

    dataset_root = args.output_root / symbol / args.interval
    archive_dir = dataset_root / "archives"
    parts_dir = dataset_root / "parts"
    dataset_root.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "research-binance-history-downloader/1.0"

    parts: list[Path] = []
    latest_archive_end = start
    found_month = False
    now = pd.Timestamp.now(tz="UTC")
    current_month = pd.Timestamp(now.year, now.month, 1, tz="UTC")
    for month in month_starts(start, min(end, current_month)):
        item = ArchiveItem("monthly", month.strftime("%Y-%m"))
        zip_path = archive_dir / "monthly" / f"{symbol}-{args.interval}-{item.period}.zip"
        exists = download_archive(
            session, archive_url(symbol, args.interval, item), zip_path, args.timeout, args.force
        )
        if not exists:
            if found_month:
                print(f"Monthly archive unavailable, switching to daily files after {latest_archive_end.date()}")
                break
            print(f"No archive for {item.period} (market not yet listed)")
            continue
        found_month = True
        parquet_path = parts_dir / "monthly" / f"year={month.year}" / f"{item.period}.parquet"
        convert_archive(zip_path, parquet_path, args.force)
        parts.append(parquet_path)
        latest_archive_end = month + pd.offsets.MonthBegin(1)
        print(f"Ready monthly {item.period}")

    daily_start = max(start.floor("D"), latest_archive_end.floor("D"))
    yesterday_end = pd.Timestamp.now(tz="UTC").floor("D")
    daily_end = min(end, yesterday_end)
    day = daily_start
    while day < daily_end:
        item = ArchiveItem("daily", day.strftime("%Y-%m-%d"))
        zip_path = archive_dir / "daily" / f"{symbol}-{args.interval}-{item.period}.zip"
        if download_archive(
            session, archive_url(symbol, args.interval, item), zip_path, args.timeout, args.force
        ):
            parquet_path = parts_dir / "daily" / f"year={day.year}" / f"month={day.month:02d}" / f"{item.period}.parquet"
            convert_archive(zip_path, parquet_path, args.force)
            parts.append(parquet_path)
            latest_archive_end = day + pd.Timedelta(days=1)
            print(f"Ready daily {item.period}")
        else:
            print(f"Daily archive unavailable for {item.period}; REST will cover the tail")
            break
        day += pd.Timedelta(days=1)

    rest_start = max(start, latest_archive_end)
    if rest_start < end:
        tail = fetch_rest_tail(
            session,
            symbol,
            args.interval,
            int(rest_start.timestamp() * 1000),
            int(end.timestamp() * 1000),
            args.timeout,
            args.request_sleep,
        )
        if not tail.empty:
            tail_path = parts_dir / "rest_tail.parquet"
            tail.to_parquet(tail_path, compression="zstd", index=False)
            parts.append(tail_path)
            print(f"Ready REST tail ({len(tail):,} rows)")

    # Include already-created parts when a resumed run does not touch every file.
    parts = sorted(set(parts) | set(parts_dir.rglob("*.parquet")))
    report = write_quality_report(parts, start, end, dataset_root / "quality_report.json")
    manifest = {
        "source": "Binance Spot public data",
        "symbol": symbol,
        "interval": args.interval,
        "timezone": "UTC",
        "timestamp_unit": "milliseconds",
        "columns": COLUMNS[:-1],
        "quality_report": "quality_report.json",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (dataset_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Dataset ready: {dataset_root.resolve()}")


if __name__ == "__main__":
    main()
