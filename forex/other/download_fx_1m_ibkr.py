"""
Download 1-minute FX OHLCV bars from Interactive Brokers.

This is the multi-pair/resumable version of download_intraday_ibkr.py. It uses
the same read-only IBKR connection settings from .env and places no orders.

Typical run:

    python download_fx_1m_ibkr.py

Outputs:

    data/eurusd_intraday_1min.csv
    data/gbpusd_intraday_1min.csv
    data/audusd_intraday_1min.csv
    data/nzdusd_intraday_1min.csv

FX "volume" from IBKR is not true centralized volume. MIDPOINT bars are the
clean price substrate; pull BID_ASK separately when building transaction costs.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import fred_common as fc  # .env loader only

try:
    from ib_async import IB, Forex, util
except ImportError:  # pragma: no cover
    from ib_insync import IB, Forex, util


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

fc.load_env_file(BASE_DIR / ".env")

IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "4001"))
IB_CLIENT_ID = int(os.environ.get("IB_CLIENT_ID", "17"))

DEFAULT_PAIRS = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")
DEFAULT_START = "2011-07-19"  # 15 years before this workspace date.
BAR_SIZE = "1 min"
WHAT_TO_SHOW = "MIDPOINT"
USE_RTH = False


def pair_to_path(pair: str, what_to_show: str) -> Path:
    suffix = "1min" if what_to_show.upper() == "MIDPOINT" else f"1min_{what_to_show.lower()}"
    return DATA_DIR / f"{pair.lower()}_intraday_{suffix}.csv"


def normalize_bars(df: pd.DataFrame, start_ts: pd.Timestamp) -> pd.DataFrame:
    out = df.rename(columns={"date": "time"}).copy()
    out["time"] = pd.to_datetime(out["time"], utc=True)
    out = (
        out[["time", "open", "high", "low", "close", "volume"]]
        .drop_duplicates(subset="time")
        .sort_values("time")
        .set_index("time")
    )
    return out[out.index >= start_ts]


def merge_existing(path: Path, fresh: pd.DataFrame) -> pd.DataFrame:
    if not path.exists():
        return fresh

    existing = pd.read_csv(path, parse_dates=["time"]).set_index("time")
    existing.index = pd.to_datetime(existing.index, utc=True)
    merged = pd.concat([existing, fresh])
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    return merged


def save_checkpoint(path: Path, data: pd.DataFrame) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    data.to_csv(tmp_path)
    tmp_path.replace(path)


def fetch_pair(
    ib: IB,
    pair: str,
    start: str,
    chunk_duration: str,
    pacing_sleep: float,
    what_to_show: str,
    max_chunks: int | None,
) -> Path:
    pair = pair.upper()
    start_ts = pd.Timestamp(start, tz="UTC")
    out_path = pair_to_path(pair, what_to_show)

    contract = Forex(pair)
    ib.qualifyContracts(contract)

    end_dt = datetime.now(timezone.utc)
    chunks_done = 0
    data = merge_existing(out_path, pd.DataFrame())
    existing_min = data.index.min() if not data.empty else None
    if existing_min is not None and existing_min <= start_ts:
        print(f"{pair}: existing file already reaches {existing_min}; skipping.")
        return out_path

    print(f"\n{pair}: downloading {BAR_SIZE} {what_to_show} bars back to {start_ts.date()}")
    if existing_min is not None:
        print(f"{pair}: existing earliest checkpoint is {existing_min}; continuing backward.")
        end_dt = existing_min.to_pydatetime()

    while True:
        if max_chunks is not None and chunks_done >= max_chunks:
            print(f"{pair}: stopped after --max-chunks={max_chunks}.")
            break

        print(f"{pair}: requesting {chunk_duration} ending {end_dt:%Y-%m-%d %H:%M} UTC")
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_dt,
            durationStr=chunk_duration,
            barSizeSetting=BAR_SIZE,
            whatToShow=what_to_show,
            useRTH=USE_RTH,
            formatDate=2,
        )
        if not bars:
            print(f"{pair}: empty response; stopping this pair.")
            break

        chunk = normalize_bars(util.df(bars), start_ts)
        if chunk.empty:
            print(f"{pair}: returned chunk is before requested start; stopping.")
            break

        data = merge_existing(out_path, chunk)
        save_checkpoint(out_path, data)

        earliest = data.index.min()
        latest = data.index.max()
        print(f"{pair}: checkpoint {len(data):,} rows, {earliest} -> {latest}")
        chunks_done += 1

        if earliest <= start_ts:
            break

        end_dt = earliest.to_pydatetime()
        time.sleep(pacing_sleep)

    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", nargs="+", default=list(DEFAULT_PAIRS))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--chunk-duration", default="1 W")
    parser.add_argument("--pacing-sleep", type=float, default=10.0)
    parser.add_argument("--what-to-show", default=WHAT_TO_SHOW, choices=["MIDPOINT", "BID_ASK"])
    parser.add_argument("--client-id", type=int, default=IB_CLIENT_ID)
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Debug/smoke-test limit per pair; omit for the full download.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ib = IB()
    print(f"Connecting read-only to IBKR at {IB_HOST}:{IB_PORT} (clientId={args.client_id})...")
    ib.connect(IB_HOST, IB_PORT, clientId=args.client_id, readonly=True, timeout=30)
    try:
        for pair in args.pairs:
            fetch_pair(
                ib=ib,
                pair=pair,
                start=args.start,
                chunk_duration=args.chunk_duration,
                pacing_sleep=args.pacing_sleep,
                what_to_show=args.what_to_show,
                max_chunks=args.max_chunks,
            )
    finally:
        ib.disconnect()
        print("\nDisconnected.")


if __name__ == "__main__":
    main()
