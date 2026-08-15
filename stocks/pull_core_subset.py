"""Download only the always-in NDX100 core (43 names) for the noise-VWAP pre-screen.

This is a DELIBERATELY survivorship-biased subset: names continuously in the
Nasdaq-100 from 2016-08-11 to 2026-08-11 with complete LSE coverage. Because the
subset is the set of long-run survivors, it can only *flatter* a long-drift
continuation edge, so it is a valid KILL-FIRST screen (absent here => dead) but
never a confirmation. It is NOT survivorship-bias-free and must never be
described as such (see stocks/MEMORY.md).

The full-universe downloader (download_nasdaq100_1m.py) fails closed on the
incomplete universe; this companion pulls only the scoped subset, reusing that
module's LSE client, rate-limit wait, parquet naming, and quality record so the
files are compatible with its verify() step. Resumable: existing files are
skipped. Respects the LSE 5-exports/hour limit.

Run from Research/:
    python stocks/pull_core_subset.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_nasdaq100_1m import (  # noqa: E402
    DATA_DIR,
    END,
    START,
    TIMEFRAME,
    api_client,
    atomic_json,
    parquet_record,
    say,
    utc_now,
    wait_for_export_quota,
)

PROJECT_ROOT = Path(__file__).resolve().parent
STATE_PATH = PROJECT_ROOT / "core_pull_state.json"

# 43 names: single continuous membership interval spanning the full 2016-08-11..
# 2026-08-11 window AND membership_coverage_complete == True in
# universe/provider_coverage_audit.csv. Derived, not hand-picked, from the
# point-in-time membership table. BKNG is always-in but has an LSE coverage gap
# and is intentionally excluded.
CORE = [
    "AAPL", "ADBE", "ADI", "ADP", "ADSK", "AMAT", "AMGN", "AMZN", "AVGO",
    "CMCSA", "COST", "CSCO", "CSX", "FAST", "GILD", "GOOG", "GOOGL", "INTC",
    "INTU", "ISRG", "KHC", "LRCX", "MAR", "MCHP", "MDLZ", "META", "MNST",
    "MSFT", "MU", "NFLX", "NVDA", "ORLY", "PAYX", "PCAR", "PYPL", "QCOM",
    "REGN", "ROST", "SBUX", "TMUS", "TSLA", "TXN", "VRTX",
]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"created_utc": utc_now(), "subset": "ndx100_always_in_core", "files": {}, "errors": {}}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    client = api_client()
    state = load_state()
    start = START.date().isoformat()
    end = END.date().isoformat()

    for number, ticker in enumerate(CORE, start=1):
        destination = DATA_DIR / f"stocks_{ticker}_{TIMEFRAME}.parquet"
        if destination.exists():
            if ticker not in state["files"]:
                state["files"][ticker] = parquet_record(destination)
                atomic_json(STATE_PATH, state)
            say(f"[{number}/{len(CORE)}] {ticker}: existing file verified")
            continue
        wait_for_export_quota(client)
        say(f"[{number}/{len(CORE)}] {ticker}: requesting {start} to {end}")
        try:
            result = client.history(
                ticker,
                dataset="stocks",
                timeframe=TIMEFRAME,
                start=start,
                end=end,
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
        except Exception as exc:  # noqa: BLE001 - record and continue, resumable
            state["errors"][ticker] = {"at_utc": utc_now(), "error": repr(exc)}
            atomic_json(STATE_PATH, state)
            say(f"{ticker}: ERROR {exc!r}")

    done = sorted(state["files"])
    say(f"core pull pass complete: {len(done)}/{len(CORE)} present; errors={sorted(state['errors'])}")


if __name__ == "__main__":
    main()
