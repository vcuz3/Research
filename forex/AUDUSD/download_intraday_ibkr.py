"""
Download intraday AUDUSD bars from Interactive Brokers.

IBKR has NO static API key. You connect to a locally running Trader Workstation
(TWS) or IB Gateway over a socket; your normal IBKR login authenticates it. See
the setup steps in README_pipeline.md ("IBKR API setup"). In short:

  1. Install & run IB Gateway (or TWS). Log in (use the PAPER account first).
  2. Configure -> Settings -> API -> Settings:
       * enable "ActiveX and Socket Clients"
       * add 127.0.0.1 to Trusted IPs
       * note the Socket port (Gateway paper 4002 / live 4001;
         TWS paper 7497 / live 7496)
  3. pip install ib_async        (maintained fork of ib_insync)
  4. Put connection details in AUDUSD/.env:
       IB_HOST=127.0.0.1
       IB_PORT=4001          # LIVE Gateway (paper would be 4002)
       IB_CLIENT_ID=17
  5. Keep Gateway/TWS running, then: python download_intraday_ibkr.py

Output (standard schema shared with any other vendor):
    data/audusd_intraday_{bar}.csv   index=time (UTC), cols open/high/low/close/volume
"""

from pathlib import Path
from datetime import datetime, timezone
import os
import time

import pandas as pd

import forex.fred_common as fc  # only for the .env loader

# ib_async is the maintained fork; ib_insync has the same API. Support both.
try:
    from ib_async import IB, Forex, util
except ImportError:  # pragma: no cover
    from ib_insync import IB, Forex, util


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

fc.load_env_file(BASE_DIR / ".env")

IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "4001"))          # Gateway LIVE default (paper=4002)
IB_CLIENT_ID = int(os.environ.get("IB_CLIENT_ID", "17"))

# --- what to pull ---------------------------------------------------------- #
INSTRUMENT = "AUDUSD"        # IBKR CASH pair -> Forex('AUDUSD') = AUD.USD @ IDEALPRO
BAR_SIZE = "15 mins"          # '1 min','5 mins','15 mins','1 hour', ...
WHAT_TO_SHOW = "MIDPOINT"    # FX has no true volume; MIDPOINT is the clean choice.
                             # Use 'BID_ASK' in a second pull if you want spreads for TCA.
CHUNK_DURATION = "3 M"       # history per request; step back by this each loop
START = "2013-01-01"         # earliest date to fetch back to
USE_RTH = False              # FX trades ~24h; keep all hours
PACING_SLEEP = 10.0          # seconds between requests (IBKR: <=60 hist req / 10 min)


def _bar_tag(bar_size):
    return bar_size.replace(" ", "")


def fetch_history(ib):
    contract = Forex(INSTRUMENT)
    ib.qualifyContracts(contract)

    start_ts = pd.Timestamp(START, tz="UTC")
    end_dt = datetime.now(timezone.utc)
    frames = []

    while True:
        print(f"  requesting {CHUNK_DURATION} of {BAR_SIZE} ending {end_dt:%Y-%m-%d %H:%M} UTC")
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_dt,
            durationStr=CHUNK_DURATION,
            barSizeSetting=BAR_SIZE,
            whatToShow=WHAT_TO_SHOW,
            useRTH=USE_RTH,
            formatDate=2,          # 2 = UTC
        )
        if not bars:
            print("  (empty response -- stopping; check subscriptions / connection)")
            break

        df = util.df(bars)
        frames.append(df)

        earliest = pd.Timestamp(df["date"].iloc[0])
        if earliest.tzinfo is None:
            earliest = earliest.tz_localize("UTC")
        if earliest <= start_ts:
            break

        end_dt = earliest.to_pydatetime()
        time.sleep(PACING_SLEEP)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"date": "time"})
    out["time"] = pd.to_datetime(out["time"], utc=True)
    out = (out[["time", "open", "high", "low", "close", "volume"]]
           .drop_duplicates(subset="time")
           .sort_values("time")
           .set_index("time"))
    out = out[out.index >= start_ts]
    return out


def main():
    ib = IB()
    print(f"Connecting to IBKR at {IB_HOST}:{IB_PORT} (clientId={IB_CLIENT_ID})...")
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, readonly=True)
    try:
        data = fetch_history(ib)
    finally:
        ib.disconnect()

    if data.empty:
        raise SystemExit("No data returned. Is Gateway/TWS running and logged in?")

    out_path = DATA_DIR / f"audusd_intraday_{_bar_tag(BAR_SIZE)}.csv"
    data.to_csv(out_path)
    print(f"\nSaved {len(data):,} bars -> {out_path}")
    print("Range:", data.index.min(), "->", data.index.max())


if __name__ == "__main__":
    main()
