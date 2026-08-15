"""Download six sovereign 2-year yield histories from London Strategic Edge.

The API credential is read from the workspace-root ``.env``. Outputs and
non-secret provenance are written beneath ``forex/data/lse/bond_yields``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from dotenv import dotenv_values
from lse import LSE


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "forex" / "data" / "lse" / "bond_yields"
SYMBOLS = ("AU2Y", "NZ2Y", "DE2Y", "UK2Y", "US2Y", "JP2Y")
PAGE_SIZE = 5000


def api_client() -> LSE:
    key = dotenv_values(ROOT / ".env").get("londonstrategicedge_api")
    if not key:
        raise RuntimeError(f"londonstrategicedge_api is missing from {ROOT / '.env'}")
    return LSE(api_key=str(key), timeout=300)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_symbol(client: LSE, symbol: str) -> pd.DataFrame:
    """Fetch all rows, advancing by date when the REST response reaches its cap."""
    pages: list[pd.DataFrame] = []
    start: str | None = None
    while True:
        rows = client.bond_yields(
            symbol=symbol,
            start=start,
            order="asc",
            limit=PAGE_SIZE,
        )
        if not rows:
            break
        page = pd.DataFrame(rows)
        pages.append(page)
        if len(page) < PAGE_SIZE:
            break
        last_date = pd.to_datetime(page["date"], errors="raise").max()
        start = (last_date + timedelta(days=1)).date().isoformat()

    if not pages:
        raise RuntimeError(f"London Strategic Edge returned no rows for {symbol}")

    frame = pd.concat(pages, ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame = (
        frame.drop_duplicates(["symbol", "date"], keep="last")
        .sort_values(["symbol", "date"])
        .reset_index(drop=True)
    )
    if set(frame["symbol"]) != {symbol}:
        raise RuntimeError(f"unexpected symbols in {symbol} response: {set(frame['symbol'])}")
    return frame


def quality(frame: pd.DataFrame) -> dict[str, Any]:
    dates = frame["date"]
    delta_days = dates.diff().dt.days
    prices = frame[["open", "high", "low", "close"]]
    large_gap_rows = frame.loc[delta_days > 7, ["date"]].copy()
    large_gap_rows["previous_date"] = dates.shift(1).loc[large_gap_rows.index]
    large_gap_rows["gap_days"] = delta_days.loc[large_gap_rows.index]
    large_gaps = [
        {
            "previous_date": row.previous_date.date().isoformat(),
            "next_date": row.date.date().isoformat(),
            "calendar_days": int(row.gap_days),
        }
        for row in large_gap_rows.itertuples()
    ]
    invalid_envelope = (
        (frame["high"] < prices.max(axis=1))
        | (frame["low"] > prices.min(axis=1))
    )
    return {
        "rows": int(len(frame)),
        "first_date": dates.min().date().isoformat(),
        "last_date": dates.max().date().isoformat(),
        "duplicate_symbol_dates": int(frame.duplicated(["symbol", "date"]).sum()),
        "out_of_order_dates": int((delta_days < 0).sum()),
        "null_cells": int(frame.isna().sum().sum()),
        "null_ohlc_cells": int(prices.isna().sum().sum()),
        # Negative sovereign yields are economically valid, so these are
        # distribution diagnostics rather than error counts.
        "zero_ohlc_cells": int((prices == 0).sum().sum()),
        "negative_ohlc_cells": int((prices < 0).sum().sum()),
        "invalid_ohlc_envelopes": int(invalid_envelope.sum()),
        "calendar_gaps_over_7_days": int((delta_days > 7).sum()),
        "largest_calendar_gap_days": int(delta_days.max()),
        "calendar_gap_intervals_over_7_days": large_gaps,
        "years_with_observations": int(dates.dt.year.nunique()),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = api_client()
    catalog = pd.DataFrame(client.catalog("bonds"))
    catalog = catalog.loc[catalog["symbol"].isin(SYMBOLS)].copy()
    missing = sorted(set(SYMBOLS) - set(catalog["symbol"]))
    if missing:
        raise RuntimeError(f"requested symbols missing from the LSE catalog: {missing}")
    catalog = catalog.set_index("symbol").loc[list(SYMBOLS)].reset_index()
    catalog.to_csv(OUT / "catalog.csv", index=False)

    frames: list[pd.DataFrame] = []
    records: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        print(f"{symbol}: downloading full daily history", flush=True)
        frame = download_symbol(client, symbol)
        path = OUT / f"{symbol}.parquet"
        frame.to_parquet(path, index=False, compression="zstd")
        advertised = catalog.loc[catalog["symbol"] == symbol].iloc[0]
        checks = quality(frame)
        records.append(
            {
                "symbol": symbol,
                "name": advertised["name"],
                "country": advertised["country"],
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "columns": pq.ParquetFile(path).schema_arrow.names,
                "advertised_ticks": int(advertised["ticks"]),
                "advertised_first": str(advertised["first"]),
                "advertised_last": str(advertised["last"]),
                "quality": checks,
                "matches_advertised_ticks": checks["rows"] == int(advertised["ticks"]),
            }
        )
        frames.append(frame)
        print(
            f"{symbol}: {checks['rows']:,} rows, "
            f"{checks['first_date']} through {checks['last_date']}",
            flush=True,
        )

    combined = pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"])
    combined_path = OUT / "sovereign_2y_yields.parquet"
    combined.to_parquet(combined_path, index=False, compression="zstd")
    manifest = {
        "created_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "London Strategic Edge bond_yields API",
        "credential_variable": "londonstrategicedge_api",
        "frequency": "daily",
        "value_unit": "percent yield as supplied by provider",
        "symbols": list(SYMBOLS),
        "files": records,
        "combined": {
            "path": str(combined_path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": combined_path.stat().st_size,
            "sha256": sha256(combined_path),
            "rows": int(len(combined)),
            "columns": pq.ParquetFile(combined_path).schema_arrow.names,
            "duplicate_symbol_dates": int(combined.duplicated(["symbol", "date"]).sum()),
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"saved manifest: {OUT / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
