"""
download_rates_futures_ibkr.py — daily AU & US bond-/yield-futures from IBKR, to
build a genuine daily AU–US rate differential for the macro-regime classifier.

WHY
---
The macro-regime classifier's weakest channel was "rates": FRED only gives AU
yields MONTHLY (they move ~once a month on the daily grid), so no honest daily
AU–US differential could be built and the rates driver was a US-2Y-only proxy
(CLAUDE.md gotcha #5). Bond FUTURES fix this — they trade daily and IBKR serves
long history. This script pulls them and derives clean daily yields.

WHAT IT PULLS (continuous front futures, daily bars)
----------------------------------------------------
AU legs (ASX 24 / SNFE, quoted as PRICE = 100 − yield):
    YT  = Australian 3-Year Treasury Bond future   -> au_3y_yield  = 100 − price
    XT  = Australian 10-Year Treasury Bond future  -> au_10y_yield = 100 − price
US legs (CBOT, CME "Treasury Yield" futures, quoted DIRECTLY in yield %):
    2YY = US 2-Year  yield future                  -> us_2y_yield  = price
    10YY= US 10-Year yield future                  -> us_10y_yield = price

The AU 3-Year is used (not 2-Year) because it is the liquid AU short-bond future
— there is no exchange-traded AU 2-Year. The US yield futures (2YY/10YY) are
yield-quoted so no cheapest-to-deliver conversion is needed; note they only list
from ~Aug-2022, so history is short. For the LONG-history differential the
classifier falls back to FRED US yields (already daily & point-in-time) and uses
these futures for the recent, pure-futures cross-check. AU futures history is
long, which is the piece that actually unlocks the daily differential.

SAFETY (identical to the rest of this repo — LIVE account):
    * connects read-only (ib.connect(..., readonly=True)),
    * places NO orders (there is no order code in this file),
    * 10 s pacing between historical requests.
IB Gateway must be running & logged in.  pip install ib_async first.

Output:
    data/rates_futures_daily.csv   index=date, cols: *_yield (and *_price raw)
    -> consumed automatically by macro_regime.build_driver_panel()

Usage:  python download_rates_futures_ibkr.py
"""

from pathlib import Path
from datetime import datetime, timezone
import os
import time

import pandas as pd

import forex.fred_common as fc  # .env loader

try:
    from ib_async import IB, ContFuture, util
except ImportError:  # pragma: no cover
    from ib_insync import IB, ContFuture, util


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

fc.load_env_file(BASE_DIR / ".env")

IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "4001"))          # LIVE Gateway (paper=4002)
IB_CLIENT_ID = int(os.environ.get("IB_CLIENT_ID", "17"))

# --- what to pull ---------------------------------------------------------- #
# name -> (IBKR symbol, exchange, currency, quote convention)
#   quote="price_100_minus_yield"  -> yield = 100 - close   (AU bond futures)
#   quote="yield"                  -> yield = close         (CME yield futures)
# NOTE: exact IBKR symbols/exchanges can vary by account/region. This script
# prints the resolved contract for each leg — verify the printout and adjust the
# map if a leg fails to qualify (common alternates noted inline).
FUTURES = {
    "au_3y":  dict(symbol="YT",  exchange="SNFE", currency="AUD", quote="price_100_minus_yield"),
    "au_10y": dict(symbol="XT",  exchange="SNFE", currency="AUD", quote="price_100_minus_yield"),
    "us_2y":  dict(symbol="2YY", exchange="CBOT", currency="USD", quote="yield"),
    "us_10y": dict(symbol="10YY", exchange="CBOT", currency="USD", quote="yield"),
    # alternates if the above don't qualify on your entitlement set:
    #   AU bonds sometimes list under exchange "ASX"; US yield futures under "ECBOT".
    #   US T-Note price futures (need CTD conversion to yield, not used here):
    #   "us_2y_note": dict(symbol="ZT", exchange="CBOT", currency="USD", quote="price_note"),
    #   "us_10y_note": dict(symbol="ZN", exchange="CBOT", currency="USD", quote="price_note"),
}

BAR_SIZE = "1 day"
WHAT_TO_SHOW = "TRADES"       # daily OHLC of traded prices (close ≈ daily settle)
CHUNK_DURATION = "1 Y"        # history per request; step back each loop
START = "2010-01-01"          # burn-in before the 2013 intraday era + 120d windows
USE_RTH = True                # daily bars: regular session is fine
PACING_SLEEP = 10.0           # IBKR: <= 60 hist requests / 10 min


def fetch_daily(ib, symbol, exchange, currency):
    """Pull daily bars for one continuous future back to START. Returns a
    Series of daily close indexed by date (tz-naive), or empty on failure."""
    c = ContFuture(symbol=symbol, exchange=exchange, currency=currency)
    try:
        ib.qualifyContracts(c)
    except Exception as e:                                     # noqa: BLE001
        print(f"  [!] could not qualify {symbol}@{exchange} {currency}: {e}")
        return pd.Series(dtype="float64")
    print(f"  resolved: {c.localSymbol or c.symbol}  conId={c.conId}  "
          f"({c.lastTradeDateOrContractMonth or 'cont'})")

    start_ts = pd.Timestamp(START)
    end_dt = datetime.now(timezone.utc)
    frames = []
    while True:
        bars = ib.reqHistoricalData(
            c, endDateTime=end_dt, durationStr=CHUNK_DURATION,
            barSizeSetting=BAR_SIZE, whatToShow=WHAT_TO_SHOW,
            useRTH=USE_RTH, formatDate=2,
        )
        if not bars:
            if not frames:
                print(f"  [!] empty response for {symbol} — check entitlement.")
            break
        df = util.df(bars)
        frames.append(df)
        earliest = pd.Timestamp(df["date"].iloc[0])
        if earliest.tzinfo is not None:
            earliest = earliest.tz_localize(None)
        if earliest <= start_ts:
            break
        end_dt = pd.Timestamp(earliest).to_pydatetime()
        time.sleep(PACING_SLEEP)

    if not frames:
        return pd.Series(dtype="float64")
    out = pd.concat(frames, ignore_index=True).drop_duplicates(subset="date")
    idx = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    s = pd.Series(out["close"].to_numpy("float64"), index=idx).sort_index()
    return s[s.index >= start_ts]


def main():
    ib = IB()
    print(f"Connecting read-only to {IB_HOST}:{IB_PORT} (clientId={IB_CLIENT_ID})...")
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, readonly=True, timeout=20)
    print("Connected. Server version:", ib.client.serverVersion())

    prices, yields = {}, {}
    try:
        for name, spec in FUTURES.items():
            print(f"\n{name}: {spec['symbol']}@{spec['exchange']} ({spec['currency']})")
            s = fetch_daily(ib, spec["symbol"], spec["exchange"], spec["currency"])
            if s.empty:
                continue
            prices[f"{name}_price"] = s
            if spec["quote"] == "price_100_minus_yield":
                yields[f"{name}_yield"] = 100.0 - s
            elif spec["quote"] == "yield":
                yields[f"{name}_yield"] = s
            print(f"  got {len(s):,} daily bars  {s.index.min().date()} -> {s.index.max().date()}")
            time.sleep(PACING_SLEEP)
    finally:
        ib.disconnect()
        print("\nDisconnected.")

    if not yields:
        raise SystemExit("No futures data returned. Is Gateway running & entitled? "
                         "Check the resolved-contract printouts above and adjust FUTURES{}.")

    out = pd.concat({**prices, **yields}, axis=1)
    out.index.name = "date"
    # derived spreads (only where both legs exist)
    if {"au_10y_yield", "us_10y_yield"} <= set(out.columns):
        out["rate_diff_10y_futures"] = out["au_10y_yield"] - out["us_10y_yield"]
    if {"au_3y_yield", "us_2y_yield"} <= set(out.columns):
        out["rate_diff_3y2y_futures"] = out["au_3y_yield"] - out["us_2y_yield"]

    path = DATA_DIR / "rates_futures_daily.csv"
    out.to_csv(path)
    print(f"\nSaved {out.shape[0]:,} rows x {out.shape[1]} cols -> {path}")
    print("Columns:", ", ".join(out.columns))
    print("Coverage (non-null %):")
    print((out.notna().mean() * 100).round(1).to_string())
    print("\nNext: re-run  python run_macro_regime.py  — the classifier will "
          "auto-detect this file and switch the rates driver to the genuine "
          "daily AU–US differential.")


if __name__ == "__main__":
    main()
