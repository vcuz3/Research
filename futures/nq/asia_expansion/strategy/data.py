"""
Asia-session 5-minute NQ bars + the Rule 9a data-quality gate.

Source: futures/nq/data/NQ_1m_clean.parquet (Databento, 2011-08 -> 2026-07, all hours,
carries `symbol` and `is_roll`).

Session convention
------------------
The Asia window runs across ET midnight, so a session is labelled by its **trade date**
= the ET calendar date of the RTH session that FOLLOWS it. A window of 18:00-03:00 on
trade date D therefore spans 18:00 (D-1) .. 02:59 (D).

Bars are 5-minute, LEFT-labelled: the 18:00 bar aggregates 1-min bars in [18:00, 18:05).
open=first, high=max, low=min, close=last, volume=sum. Empty 5-min slots are simply
absent (not forward-filled) so that missing data stays visible to the coverage report
rather than being silently manufactured.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"      # futures/nq/data
CACHE = Path(__file__).resolve().parent / "_cache"
CACHE.mkdir(exist_ok=True)

SRC = DATA / "NQ_1m_clean.parquet"

TICK = 0.25
MNQ_POINT_VALUE = 2.0
NQ_POINT_VALUE = 20.0

# Named Asia windows, (start_hour, end_hour) in ET. end is exclusive.
# A start >= 18 with an end <= start means the window wraps past midnight.
WINDOWS = {
    "18-03": (18, 3),
    "19-03": (19, 3),
    "20-04": (20, 4),
    "18-24": (18, 24),
}

MIN_BARS_PER_SESSION = 24    # >= 2 hours of 5-min bars for a session to be usable


def _load_1m() -> pd.DataFrame:
    df = pd.read_parquet(SRC)
    et = df["ts_utc"].dt.tz_convert("America/New_York")
    # Drop tz keeping the LOCAL ET wall clock (.values would keep the UTC instant).
    df = df.assign(et=et.dt.tz_localize(None).values)
    return df


def _in_window(hour: pd.Series, start: int, end: int) -> pd.Series:
    if start < end:
        return (hour >= start) & (hour < end)
    return (hour >= start) | (hour < end)      # wraps midnight


def build_asia_5m(window: str = "18-03", rebuild: bool = False) -> pd.DataFrame:
    cache = CACHE / f"asia_5m_{window}.parquet"
    if cache.exists() and not rebuild:
        return pd.read_parquet(cache)

    start, end = WINDOWS[window]
    df = _load_1m()
    hour = df["et"].dt.hour
    df = df[_in_window(hour, start, end)].copy()

    # trade date: bars at hour >= 18 belong to the NEXT calendar date's session.
    et = df["et"]
    trade_date = et.dt.normalize()
    if start >= 18:
        trade_date = trade_date + pd.to_timedelta((et.dt.hour >= 18).astype(int), unit="D")
    df["trade_date"] = trade_date.values

    df = df.set_index("et").sort_index()
    g = df.groupby("trade_date").resample("5min")
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"),
                n_1m=("open", "size"),
                n_symbols=("symbol", "nunique"),
                n_roll=("is_roll", "sum")).dropna(subset=["open"]).reset_index()

    nb = out.groupby("trade_date")["open"].transform("size")
    out = out[nb >= MIN_BARS_PER_SESSION].reset_index(drop=True)
    out["bar_i"] = out.groupby("trade_date").cumcount()
    out["slot"] = out["et"].dt.strftime("%H:%M")
    out["range"] = out["high"] - out["low"]
    out = out[["et", "trade_date", "bar_i", "slot", "open", "high", "low", "close",
               "volume", "range", "n_1m", "n_symbols", "n_roll"]]
    out.to_parquet(cache)
    return out


def data_quality(bars: pd.DataFrame, window: str) -> dict:
    """Rule 9a report. Everything here must be READ before any P&L is interpreted."""
    start, end = WINDOWS[window]
    span_h = (end - start) % 24 or 24
    expected_bars = span_h * 12

    per_session = bars.groupby("trade_date").agg(
        n_bars=("bar_i", "size"), n_sym=("n_symbols", "max"), n_roll=("n_roll", "sum"))

    slot_cov = bars.groupby("slot").size()
    n_sessions = per_session.shape[0]

    # duplicate / out-of-order timestamps
    dup = int(bars.duplicated(subset=["et"]).sum())
    ooo = int((bars.sort_values(["trade_date", "bar_i"])["et"].diff() <= pd.Timedelta(0)).sum())

    # a 5-min bar built from < 5 one-minute bars is a partially-missing bar
    thin = bars["n_1m"] < 5

    return {
        "window": window,
        "sessions": int(n_sessions),
        "first_session": str(bars["trade_date"].min().date()),
        "last_session": str(bars["trade_date"].max().date()),
        "bars": int(len(bars)),
        "expected_bars_per_session": int(expected_bars),
        "median_bars_per_session": float(per_session["n_bars"].median()),
        "sessions_below_90pct_coverage": int((per_session["n_bars"] < 0.9 * expected_bars).sum()),
        "bar_coverage_overall": float(len(bars) / (n_sessions * expected_bars)),
        "partial_bars_frac": float(thin.mean()),
        "duplicate_timestamps": dup,
        "out_of_order_timestamps": ooo,
        "sessions_with_multi_symbol_bar": int((per_session["n_sym"] > 1).sum()),
        "sessions_touching_a_roll": int((per_session["n_roll"] > 0).sum()),
        "slot_coverage_min": float(slot_cov.min() / n_sessions),
        "slot_coverage_max": float(slot_cov.max() / n_sessions),
        "worst_covered_slots": slot_cov.nsmallest(5).div(n_sessions).round(4).to_dict(),
        "median_volume_per_bar": float(bars["volume"].median()),
    }
