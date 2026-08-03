"""
Assemble the INTRADAY modeling panel: intraday AUDUSD bars as the trading
substrate, with the daily/monthly macro+market features as slow conditioning
variables joined without look-ahead.

Vendor-agnostic: reads any intraday CSV with a UTC 'time' index and
open/high/low/close columns (produced by download_intraday_ibkr.py).

No-look-ahead rules:
  * Intraday features use only bars up to and including the current bar.
  * Daily/monthly conditioning features (from audusd_modeling_panel_daily.csv)
    are stamped at a daily date; they are made available the NEXT business day
    and as-of joined backward, so a feature built from day D's close is never
    visible to intraday bars before D+1.
  * The target is a strictly forward return over TARGET_BARS.

Usage:
    python build_intraday_panel.py [intraday_csv]
    -> data/audusd_intraday_modeling_panel.csv
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

DEFAULT_INTRADAY = DATA_DIR / "audusd_intraday_15mins.csv"
DAILY_PANEL = DATA_DIR / "audusd_modeling_panel_daily.csv"

TARGET_BARS = 12         # forward horizon in bars (e.g. 12 x 5min = 1 hour)
RET_WINDOWS = [1, 3, 6, 12, 48]   # momentum lookbacks in bars
DAILY_AVAIL_LAG_BDAYS = 1         # daily features usable from the next business day


def load_intraday(path):
    df = pd.read_csv(path, parse_dates=["time"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").set_index("time")
    return df


def load_daily_conditioning():
    daily = pd.read_csv(DAILY_PANEL, parse_dates=["date"], index_col="date")
    cond_cols = [c for c in daily.columns if c.startswith(("f_", "macro_"))]
    cond = daily[cond_cols].copy()
    # make each daily row available on the next business day, in UTC
    cond.index = (cond.index + pd.offsets.BusinessDay(DAILY_AVAIL_LAG_BDAYS))
    cond.index = cond.index.tz_localize("UTC")
    return cond.sort_index()


def intraday_features(bars):
    f = pd.DataFrame(index=bars.index)
    logc = np.log(bars["close"])

    for w in RET_WINDOWS:
        f[f"ret_{w}b"] = logc.diff(w)
    f["realized_vol_48b"] = f["ret_1b"].rolling(48).std()
    f["range_1b"] = (bars["high"] - bars["low"]) / bars["close"]

    # simple mean-reversion / momentum state
    ma = bars["close"].rolling(48).mean()
    sd = bars["close"].rolling(48).std()
    f["zscore_48b"] = (bars["close"] - ma) / sd

    # session / time-of-day (UTC hour) -- FX behaviour is strongly session-dependent
    hour = bars.index.hour
    f["sess_sydney"] = ((hour >= 21) | (hour < 6)).astype(int)   # ~Sydney/early Asia
    f["sess_tokyo"] = ((hour >= 0) & (hour < 8)).astype(int)
    f["sess_london"] = ((hour >= 7) & (hour < 16)).astype(int)
    f["sess_newyork"] = ((hour >= 12) & (hour < 21)).astype(int)
    f["dow"] = bars.index.dayofweek
    return f


def build(intraday_path):
    bars = load_intraday(intraday_path)
    feats = intraday_features(bars)

    panel = pd.concat([bars[["open", "high", "low", "close"]], feats], axis=1)

    # as-of join daily/monthly conditioning features (backward, next-day-available)
    cond = load_daily_conditioning()
    panel = pd.merge_asof(
        panel.reset_index(),
        cond.reset_index().rename(columns={"date": "time"}),
        on="time", direction="backward",
    ).set_index("time")

    # strictly-forward target
    logc = np.log(panel["close"])
    panel["target_fwd_ret"] = logc.shift(-TARGET_BARS) - logc
    panel["target_fwd_dir"] = np.sign(panel["target_fwd_ret"])

    panel.to_csv(DATA_DIR / "audusd_intraday_modeling_panel.csv")

    n_cond = len([c for c in panel.columns if c.startswith(("f_", "macro_"))])
    n_intr = len([c for c in feats.columns])
    print("Saved:", DATA_DIR / "audusd_intraday_modeling_panel.csv")
    print(f"Bars: {len(panel):,}   range: {panel.index.min()} -> {panel.index.max()}")
    print(f"Intraday features: {n_intr}   conditioning features joined: {n_cond}")
    print(f"Target: forward {TARGET_BARS}-bar return "
          f"(non-null: {panel['target_fwd_ret'].notna().sum():,})")

    # leak check: conditioning columns must be constant within a UTC day (they are
    # daily, carried forward) -- a sanity assertion, not a full audit.
    if n_cond:
        col = next(c for c in panel.columns if c.startswith(("f_", "macro_")))
        per_day_unique = panel[col].groupby(panel.index.normalize()).nunique(dropna=True)
        assert per_day_unique.max() <= 1, "conditioning feature varies intraday -> leak!"
        print("Leak check OK: conditioning features are constant within each day.")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INTRADAY
    if not path.exists():
        raise SystemExit(f"Intraday file not found: {path}\n"
                         "Run download_intraday_ibkr.py first (needs IB Gateway running).")
    build(path)
