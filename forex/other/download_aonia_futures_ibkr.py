r"""Download a 15-minute, next-full-month AONIA expectations series from IBKR.

The source instrument is the ASX 30-Day Interbank Cash Rate future (``IB`` on
IBKR exchange ``SNFE``).  Each contract settles to the average RBA overnight
cash rate (AONIA) for its expiry calendar month and is quoted as 100 minus the
rate.  During calendar month M this downloader selects the contract expiring
in M+1, avoiding the current-month contract whose settlement is already partly
realised.

The connection is read-only and this module contains no order code.

Typical run from the workspace root::

    .venv\Scripts\python.exe forex\download_aonia_futures_ibkr.py

Outputs under ``forex/data/ibkr/aonia/``:

* ``raw/IB*.parquet``: returned IBKR bars for each requested contract;
* ``aonia_next_full_month_15m.parquet``: selected continuous research series;
* ``manifest.json``: provenance and data-quality diagnostics.

IBKR generally retains expired futures for only two years after expiry.  The
script discovers the contracts that the connected account can currently see
instead of claiming a longer history than IBKR actually returns.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import fred_common as fc

try:
    from ib_async import Future, IB, util
except ImportError:  # pragma: no cover
    from ib_insync import Future, IB, util


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data" / "ibkr" / "aonia"
RAW_DIR = OUTPUT_DIR / "raw"
SYDNEY = ZoneInfo("Australia/Sydney")

fc.load_env_file(BASE_DIR / ".env")

IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "4001"))
IB_CLIENT_ID = int(os.environ.get("IB_CLIENT_ID", "17"))

SYMBOL = "IB"
EXCHANGE = "SNFE"
CURRENCY = "AUD"
DEFAULT_BAR_SIZE = "15 mins"
DEFAULT_DURATION = "1 M"
DEFAULT_PACING_SLEEP = 10.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def expiry_month_start(expiry: str) -> pd.Timestamp:
    ts = pd.Timestamp(expiry[:8], tz=SYDNEY)
    return ts.replace(day=1).normalize()


def selection_window(expiry: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Sydney-local month in which the next-month contract is selected."""
    end = expiry_month_start(expiry)
    start = end - pd.DateOffset(months=1)
    return start, end


def normalize_bars(frame: pd.DataFrame, contract) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.rename(columns={"date": "ts_utc", "average": "wap"}).copy()
    out["ts_utc"] = pd.to_datetime(out["ts_utc"], utc=True).dt.tz_localize(None)
    out["local_symbol"] = contract.localSymbol
    out["contract_expiry"] = contract.lastTradeDateOrContractMonth[:8]
    out["con_id"] = int(contract.conId)
    out["has_trade"] = (out["volume"] > 0) & (out["barCount"] > 0)
    columns = [
        "ts_utc", "local_symbol", "contract_expiry", "con_id",
        "open", "high", "low", "close", "volume", "wap", "barCount",
        "has_trade",
    ]
    return out[columns].drop_duplicates("ts_utc").sort_values("ts_utc")


def add_implied_rate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert price OHLC to rate OHLC, reversing high/low correctly."""
    out = frame.copy()
    out["rate_open"] = 100.0 - out["open"]
    out["rate_high"] = 100.0 - out["low"]
    out["rate_low"] = 100.0 - out["high"]
    out["rate_close"] = 100.0 - out["close"]
    return out


def discover_contracts(ib: IB) -> list:
    template = Future(
        symbol=SYMBOL,
        exchange=EXCHANGE,
        currency=CURRENCY,
        includeExpired=True,
    )
    details = ib.reqContractDetails(template)
    contracts = [d.contract for d in details]
    contracts.sort(key=lambda c: c.lastTradeDateOrContractMonth)
    return contracts


def request_contract_bars(ib: IB, contract, bar_size: str) -> pd.DataFrame:
    start_local, end_local = selection_window(contract.lastTradeDateOrContractMonth)
    now_local = pd.Timestamp.now(tz=SYDNEY)
    if start_local >= now_local:
        return pd.DataFrame()
    request_end = min(end_local, now_local).tz_convert("UTC").to_pydatetime()
    bars = ib.reqHistoricalData(
        contract,
        endDateTime=request_end,
        durationStr=DEFAULT_DURATION,
        barSizeSetting=bar_size,
        whatToShow="TRADES",
        useRTH=False,
        formatDate=2,
        timeout=60,
    )
    if not bars:
        return pd.DataFrame()
    return normalize_bars(util.df(bars), contract)


def select_window(frame: pd.DataFrame, expiry: str) -> pd.DataFrame:
    start_local, end_local = selection_window(expiry)
    start_utc = start_local.tz_convert("UTC").tz_localize(None)
    end_utc = end_local.tz_convert("UTC").tz_localize(None)
    now_utc = pd.Timestamp.now(tz="UTC").tz_localize(None)
    end_utc = min(end_utc, now_utc)
    return frame[(frame["ts_utc"] >= start_utc) & (frame["ts_utc"] < end_utc)].copy()


def contract_quality(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"rows": 0}
    gaps = frame["ts_utc"].sort_values().diff().dropna()
    return {
        "rows": int(len(frame)),
        "start_utc": frame["ts_utc"].min().isoformat(),
        "end_utc": frame["ts_utc"].max().isoformat(),
        "trade_bars": int(frame["has_trade"].sum()),
        "trade_bar_pct": round(float(frame["has_trade"].mean() * 100), 4),
        "zero_volume_bars": int((frame["volume"] == 0).sum()),
        "total_volume": float(frame["volume"].sum()),
        "close_changes": int(frame["close"].diff().fillna(0).ne(0).sum()),
        "gaps_over_15m": int((gaps > pd.Timedelta(minutes=15)).sum()),
        "duplicate_timestamps": int(frame["ts_utc"].duplicated().sum()),
        "out_of_order_timestamps": int((frame["ts_utc"].diff().dropna() < pd.Timedelta(0)).sum()),
    }


def build_manifest(
    output: pd.DataFrame,
    output_path: Path,
    raw_records: list[dict],
    discovered: list,
    bar_size: str,
) -> dict:
    by_hour = (
        output.assign(utc_hour=output["ts_utc"].dt.hour)
        .groupby("utc_hour", observed=True)
        .agg(rows=("ts_utc", "size"), trade_bars=("has_trade", "sum"))
        .reset_index()
    )
    quality = contract_quality(output)
    quality["contract_transitions"] = int(
        output["local_symbol"].ne(output["local_symbol"].shift()).sum() - (not output.empty)
    )
    quality["by_utc_hour"] = by_hour.to_dict(orient="records")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Interactive Brokers TWS API historical TRADES bars",
        "instrument": {
            "symbol": SYMBOL,
            "exchange": EXCHANGE,
            "currency": CURRENCY,
            "description": "ASX 30-Day Interbank Cash Rate Futures",
            "quote_conversion": "implied AONIA percent = 100 - futures price",
        },
        "construction": (
            "During each Sydney calendar month, select the contract expiring in "
            "the following month. No cross-contract price adjustment or filling."
        ),
        "parameters": {
            "bar_size": bar_size,
            "what_to_show": "TRADES",
            "use_rth": False,
            "duration_per_contract": DEFAULT_DURATION,
        },
        "limitations": [
            "IBKR normally exposes expired futures only up to two years after expiry.",
            "Many returned bars have zero volume and barCount=0; use has_trade to distinguish them.",
            "This is a market expectation for average AONIA in a future calendar month, not realised AONIA.",
            "The series rolls monthly and is not back-adjusted.",
        ],
        "discovered_contracts": len(discovered),
        "discovered_range": [
            discovered[0].lastTradeDateOrContractMonth if discovered else None,
            discovered[-1].lastTradeDateOrContractMonth if discovered else None,
        ],
        "raw_contracts": raw_records,
        "output": {
            "path": str(output_path.relative_to(BASE_DIR)),
            "sha256": sha256(output_path),
            **quality,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bar-size", default=DEFAULT_BAR_SIZE)
    parser.add_argument("--pacing-sleep", type=float, default=DEFAULT_PACING_SLEEP)
    parser.add_argument("--client-id", type=int, default=IB_CLIENT_ID)
    parser.add_argument(
        "--max-contracts",
        type=int,
        default=None,
        help="Only fetch the most recent N eligible contracts (smoke testing).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    ib = IB()
    print(f"Connecting read-only to {IB_HOST}:{IB_PORT} (clientId={args.client_id})...")
    ib.connect(IB_HOST, IB_PORT, clientId=args.client_id, readonly=True, timeout=20)
    try:
        discovered = discover_contracts(ib)
        now_local = pd.Timestamp.now(tz=SYDNEY)
        eligible = [
            c for c in discovered
            if selection_window(c.lastTradeDateOrContractMonth)[0] < now_local
        ]
        if args.max_contracts is not None:
            eligible = eligible[-args.max_contracts :]
        print(
            f"Discovered {len(discovered)} contracts; fetching {len(eligible)} eligible "
            "next-full-month windows."
        )

        selected_frames: list[pd.DataFrame] = []
        raw_records: list[dict] = []
        for number, contract in enumerate(eligible, start=1):
            expiry = contract.lastTradeDateOrContractMonth[:8]
            start_local, end_local = selection_window(expiry)
            print(
                f"[{number}/{len(eligible)}] {contract.localSymbol} expiry={expiry}; "
                f"selection={start_local.date()}..{end_local.date()}"
            )
            frame = request_contract_bars(ib, contract, args.bar_size)
            if frame.empty:
                print("  no bars returned")
                raw_records.append({"local_symbol": contract.localSymbol, "expiry": expiry, "rows": 0})
            else:
                raw_path = RAW_DIR / f"{contract.localSymbol}_{args.bar_size.replace(' ', '')}.parquet"
                frame.to_parquet(raw_path, index=False)
                selected = select_window(frame, expiry)
                if not selected.empty:
                    selected_frames.append(selected)
                stats = contract_quality(selected)
                raw_records.append(
                    {
                        "local_symbol": contract.localSymbol,
                        "expiry": expiry,
                        "raw_path": str(raw_path.relative_to(BASE_DIR)),
                        "raw_sha256": sha256(raw_path),
                        **stats,
                    }
                )
                print(
                    f"  selected {len(selected):,} bars; "
                    f"traded {int(selected['has_trade'].sum()):,} "
                    f"({selected['has_trade'].mean() * 100:.1f}%)"
                )
            if number < len(eligible):
                time.sleep(args.pacing_sleep)
    finally:
        ib.disconnect()
        print("Disconnected.")

    if not selected_frames:
        raise SystemExit("No AONIA futures bars were returned; check IBKR entitlements.")

    output = pd.concat(selected_frames, ignore_index=True).sort_values("ts_utc")
    output = output.drop_duplicates("ts_utc", keep="last")
    output = add_implied_rate_columns(output)
    output_path = OUTPUT_DIR / "aonia_next_full_month_15m.parquet"
    output.to_parquet(output_path, index=False)

    manifest = build_manifest(output, output_path, raw_records, discovered, args.bar_size)
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    q = manifest["output"]
    print(f"Saved {q['rows']:,} bars to {output_path}")
    print(f"Coverage: {q['start_utc']} -> {q['end_utc']}")
    print(f"Actual trade bars: {q['trade_bars']:,} ({q['trade_bar_pct']:.2f}%)")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
