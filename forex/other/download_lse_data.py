"""Download London Strategic Edge FX and economics data.

Reads ``londonstrategicedge_api`` from the workspace-root ``.env`` and writes
only data and non-secret metadata beneath ``forex/data/lse``.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from dotenv import dotenv_values
from lse import LSE, LSEError


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "forex" / "data" / "lse"
FX_SYMBOLS = ("EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD")
ECON_COUNTRIES = {
    "US": "United States",
    "Euro_Area": "Euro Area",
    "Australia": "Australia",
}
CALENDAR_REGIONS = {"US": "US", "Euro_Area": "EU", "Australia": "AU"}
_RATE_LOCK = threading.Lock()
_NEXT_CALL_AT = 0.0


def api_client() -> LSE:
    key = dotenv_values(ROOT / ".env").get("londonstrategicedge_api")
    if not key:
        raise RuntimeError(f"londonstrategicedge_api is missing from {ROOT / '.env'}")
    return LSE(api_key=str(key), timeout=300)


def file_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    parquet = pq.ParquetFile(path)
    record: dict[str, Any] = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "rows": parquet.metadata.num_rows,
        "columns": parquet.schema_arrow.names,
    }
    frame = pd.read_parquet(path)
    if path.parent.name == "fx":
        ts = pd.to_datetime(frame["ts"], utc=True)
        delta = ts.diff().dt.total_seconds()
        record["coverage"] = {
            "first_utc": ts.min().isoformat(),
            "last_utc": ts.max().isoformat(),
            "duplicate_timestamps": int(ts.duplicated().sum()),
            "out_of_order_timestamps": int((delta < 0).sum()),
            "gaps_over_1_second": int((delta > 1).sum()),
            "largest_gap_seconds": float(delta.max()),
        }
        record["ohlc_quality"] = {
            "null_cells": int(frame[["open", "high", "low", "close"]].isna().sum().sum()),
            "invalid_envelopes": int(
                (
                    (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
                    | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
                ).sum()
            ),
            "nonpositive_prices": int((frame[["open", "high", "low", "close"]] <= 0).sum().sum()),
        }
    elif path.parent.name == "economics":
        dates = pd.to_datetime(frame["date"], errors="coerce")
        record["coverage"] = {
            "first_date": dates.min().date().isoformat(),
            "last_date": dates.max().date().isoformat(),
            "series": int(frame["symbol"].nunique()),
            "duplicate_symbol_dates": int(frame.duplicated(["symbol", "date"]).sum()),
            "null_values": int(frame["value"].isna().sum()),
        }
    elif path.parent.name == "economic_calendar":
        timestamps = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
        record["coverage"] = {
            "first_utc": timestamps.min().isoformat(),
            "last_utc": timestamps.max().isoformat(),
            "duplicate_ids": int(frame["id"].duplicated().sum()),
            "missing_actual": int(frame["actual"].isna().sum()),
        }
    return record


def download_fx(client: LSE) -> tuple[list[Path], Path]:
    destination = OUT / "fx"
    destination.mkdir(parents=True, exist_ok=True)
    catalog = pd.DataFrame(client.catalog("forex"))
    catalog = catalog.loc[catalog["symbol"].isin(FX_SYMBOLS)].copy()
    catalog_path = destination / "catalog.csv"
    catalog.to_csv(catalog_path, index=False)
    paths: list[Path] = []
    for symbol in FX_SYMBOLS:
        expected = destination / f"fx_{symbol.replace('/', '_')}_1s.parquet"
        if expected.exists():
            print(f"FX {symbol}: using existing {expected.name}", flush=True)
        else:
            print(f"FX {symbol}: starting full-history 1s export", flush=True)
            result = client.history(
                symbol,
                dataset="fx",
                timeframe="1s",
                dest=str(destination),
                dataframe=False,
                timeout=7200,
            )
            expected = Path(result)
            print(
                f"FX {symbol}: downloaded {expected.stat().st_size / (1 << 30):.2f} GiB",
                flush=True,
            )
        paths.append(expected)
    return paths, catalog_path


def download_economics(client: LSE) -> tuple[list[Path], Path]:
    destination = OUT / "economics"
    destination.mkdir(parents=True, exist_ok=True)
    catalog = pd.DataFrame(client.catalog("economics"))
    catalog_path = destination / "series_catalog.csv"
    catalog.to_csv(catalog_path, index=False)

    paths: list[Path] = []
    for label, country in ECON_COUNTRIES.items():
        path = destination / f"economics_{label}.parquet"
        country_catalog = catalog.loc[catalog["country"].eq(country)].copy()
        # The provider currently returns an empty file for symbol="all" economics
        # exports, so use the complete per-series endpoint with a resumable cache.
        frame = pd.DataFrame()
        expected = int(country_catalog["ticks"].sum())
        if len(frame) != expected:
            print(
                f"Economics {country}: bulk export returned {len(frame):,}/{expected:,}; "
                "using the series endpoint",
                flush=True,
            )
            frame = _economics_from_series(client, country_catalog, country, destination)
        if len(frame) != expected:
            raise RuntimeError(
                f"Economics {country}: expected {expected:,} observations, got {len(frame):,}"
            )
        frame.to_parquet(path, compression="zstd", index=False)
        paths.append(path)
        print(
            f"Economics {country}: {len(country_catalog)} series, {len(frame):,} observations",
            flush=True,
        )
    return paths, catalog_path


def _series_call(client: LSE, symbol: str, start: str | None = None, end: str | None = None):
    global _NEXT_CALL_AT
    while True:
        try:
            with _RATE_LOCK:
                now = time.monotonic()
                wait = max(0.0, _NEXT_CALL_AT - now)
                _NEXT_CALL_AT = max(now, _NEXT_CALL_AT) + 0.32
            if wait:
                time.sleep(wait)
            rows = client.economics(symbol, start=start, end=end, limit=5000)
            return rows
        except LSEError as exc:
            if exc.status != 429:
                raise
            time.sleep(5)


def _economics_from_series(
    client: LSE,
    country_catalog: pd.DataFrame,
    country: str,
    destination: Path,
) -> pd.DataFrame:
    cache = destination / "series_cache"
    cache.mkdir(parents=True, exist_ok=True)
    rows_to_fetch = list(country_catalog.itertuples(index=False))

    def fetch(row) -> pd.DataFrame:
        cached = cache / f"{row.symbol}.parquet"
        if cached.exists():
            frame = pd.read_parquet(cached)
        else:
            expected = int(row.ticks)
            if expected <= 5000:
                rows = _series_call(client, row.symbol)
            else:
                first_year = pd.Timestamp(row.first).year
                last_year = pd.Timestamp(row.last).year
                rows = []
                for year in range(first_year, last_year + 1):
                    rows.extend(
                        _series_call(
                            client,
                            row.symbol,
                            start=f"{year:04d}-01-01",
                            end=f"{year + 1:04d}-01-01",
                        )
                    )
            frame = pd.DataFrame(rows)
            if "symbol" not in frame.columns:
                frame["symbol"] = row.symbol
            frame = frame.drop_duplicates().reset_index(drop=True)
            if len(frame) != expected:
                raise RuntimeError(
                    f"{row.symbol}: catalog says {expected:,} observations, endpoint returned "
                    f"{len(frame):,}"
                )
            frame.to_parquet(cached, compression="zstd", index=False)
        frame["series_name"] = row.name
        frame["country"] = country
        return frame

    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for number, frame in enumerate(pool.map(fetch, rows_to_fetch), start=1):
            frames.append(frame)
        if number % 50 == 0 or number == len(country_catalog):
            print(f"Economics {country}: fetched {number}/{len(country_catalog)} series", flush=True)
    return pd.concat(frames, ignore_index=True)


def download_calendar(client: LSE) -> list[Path]:
    destination = OUT / "economic_calendar"
    destination.mkdir(parents=True, exist_ok=True)
    first_year = 2015
    last_year = datetime.now(timezone.utc).year + 1
    outputs: list[Path] = []
    for label, region in CALENDAR_REGIONS.items():
        rows: list[dict[str, Any]] = []
        for year in range(first_year, last_year + 1):
            start = date(year, 1, 1).isoformat()
            end = date(year + 1, 1, 1).isoformat()
            page = client.economic_calendar(
                region=region,
                start=start,
                end=end,
                order="asc",
                limit=5000,
            )
            if len(page) == 5000:
                raise RuntimeError(f"Calendar page cap reached for {region} in {year}")
            rows.extend(page)
        frame = pd.DataFrame(rows).drop_duplicates()
        path = destination / f"economic_calendar_{label}.parquet"
        frame.to_parquet(path, compression="zstd", index=False)
        outputs.append(path)
        print(f"Calendar {label}: {len(frame):,} events", flush=True)
    return outputs


def verify(paths: list[Path], catalog_path: Path, fx_catalog_path: Path) -> Path:
    records = [file_record(path) for path in paths]
    fx_catalog = pd.read_csv(fx_catalog_path).set_index("symbol")
    for record in records:
        if "/fx/" not in f"/{record['path']}":
            continue
        symbol = Path(record["path"]).stem.removeprefix("fx_").removesuffix("_1s").replace("_", "/")
        advertised_last = pd.to_datetime(fx_catalog.loc[symbol, "last"], utc=True)
        actual_last = pd.to_datetime(record["coverage"]["last_utc"], utc=True)
        record["advertised_last_utc"] = advertised_last.isoformat()
        record["complete_through_advertised_last"] = bool(actual_last >= advertised_last)
        record["limitation"] = (
            None
            if actual_last >= advertised_last
            else "Provider bulk export was silently capped at 2,500,000 rows."
        )
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": "London Strategic Edge vault API",
        "credential_variable": "londonstrategicedge_api",
        "fx_request": {
            "symbols": list(FX_SYMBOLS),
            "timeframe": "1s",
            "range": "full available history",
        },
        "economics_request": {
            "countries": list(ECON_COUNTRIES.values()),
            "series_count_by_country": {
                country: int(count)
                for country, count in pd.read_csv(catalog_path)
                .loc[lambda x: x["country"].isin(ECON_COUNTRIES.values())]
                .groupby("country")["symbol"]
                .nunique()
                .items()
            },
        },
        "files": records,
    }
    path = OUT / "manifest.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Only rebuild the manifest from files already on disk.",
    )
    args = parser.parse_args()
    if args.skip_download:
        paths = [
            *sorted((OUT / "fx").glob("fx_???_USD_1s.parquet")),
            *sorted((OUT / "economics").glob("economics_*.parquet")),
            *sorted((OUT / "economic_calendar").glob("*.parquet")),
        ]
        paths = [p for p in paths if p.name != "economics_all_tick.parquet"]
        catalog_path = OUT / "economics" / "series_catalog.csv"
        fx_catalog_path = OUT / "fx" / "catalog.csv"
    else:
        client = api_client()
        fx_paths, fx_catalog_path = download_fx(client)
        econ_paths, catalog_path = download_economics(client)
        calendar_paths = download_calendar(client)
        paths = fx_paths + econ_paths + calendar_paths
    manifest = verify(paths, catalog_path, fx_catalog_path)
    print(f"Manifest: {manifest}", flush=True)


if __name__ == "__main__":
    main()
