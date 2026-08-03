"""
Minimal, read-only IBKR connectivity + data-entitlement test.

Run this FIRST (before download_intraday_ibkr.py) to confirm, on a live account,
that:
  * the socket connection to IB Gateway works,
  * the connection is read-only (cannot place orders),
  * you are entitled to AUDUSD historical 5-min data.

It pulls only the last ~1 day of 5-minute bars and places NO orders. There is no
order code anywhere in this file.

    python test_ibkr_connection.py
"""

from pathlib import Path
import os

import forex.fred_common as fc

try:
    from ib_async import IB, Forex, util
except ImportError:
    from ib_insync import IB, Forex, util


BASE_DIR = Path(__file__).resolve().parent
fc.load_env_file(BASE_DIR / ".env")

IB_HOST = os.environ.get("IB_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_PORT", "4001"))       # live Gateway default
IB_CLIENT_ID = int(os.environ.get("IB_CLIENT_ID", "17"))


def main():
    ib = IB()
    print(f"Connecting read-only to {IB_HOST}:{IB_PORT} (clientId={IB_CLIENT_ID})...")
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, readonly=True, timeout=15)
    print("Connected. Server version:", ib.client.serverVersion())

    try:
        contract = Forex("AUDUSD")
        ib.qualifyContracts(contract)
        print("Qualified contract:", contract)

        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",          # now
            durationStr="1 D",
            barSizeSetting="5 mins",
            whatToShow="MIDPOINT",
            useRTH=False,
            formatDate=2,            # UTC
        )
        if not bars:
            print("\nNO DATA returned. Connection works but you may lack FX historical")
            print("entitlements. Check Client Portal -> Settings -> Market Data.")
            return

        df = util.df(bars)
        print(f"\nGot {len(df)} five-minute bars. Sample:")
        print(df[["date", "open", "high", "low", "close"]].head(3).to_string(index=False))
        print("...")
        print(df[["date", "open", "high", "low", "close"]].tail(3).to_string(index=False))
        print("\nOK -- ready to run download_intraday_ibkr.py")
    finally:
        ib.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
