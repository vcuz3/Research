"""Adapter from desired positions to the audited noise-VWAP next-open engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from futures.nq.noise_vwap.core import engine


def encode_desired_positions(
    bars: pd.DataFrame, desired: pd.DataFrame, tick: float = 0.25
) -> tuple[pd.DataFrame, pd.DataFrame, list[int]]:
    """Encode {-1,0,+1} desired state as synthetic bands.

    This changes only the audited engine's signal inputs.  Its state transitions,
    next-bar-open fills, flips, end-of-session flatten, and gross P&L remain
    untouched.  ``require_vwap=False`` makes the synthetic band the sole state.
    """
    required = {"date", "tod", "desired"}
    if not required.issubset(desired.columns):
        raise ValueError(f"desired frame missing {sorted(required - set(desired.columns))}")
    if not set(desired["desired"].dropna().astype(int).unique()).issubset({-1, 0, 1}):
        raise ValueError("desired must contain only -1, 0, +1")
    work = bars.copy().sort_values(["date", "tod"]).reset_index(drop=True)
    decisions = desired[list(required)].copy()
    decisions["desired"] = decisions["desired"].fillna(0).astype(int)
    if decisions.duplicated(["date", "tod"]).any():
        raise ValueError("duplicate desired date/tod rows")
    work = work.merge(decisions, on=["date", "tod"], how="left")
    work["desired"] = work["desired"].fillna(0).astype(int)
    close = work["close"].to_numpy(float)
    state = work["desired"].to_numpy(int)
    work["vwap"] = np.where(state > 0, close - tick, np.where(state < 0, close + tick, close))
    upper = np.where(state > 0, close - tick, close + tick)
    lower = np.where(state < 0, close + tick, close - tick)
    bands = work[["date", "tod"]].copy()
    bands["upper"] = upper
    bands["lower"] = lower
    decision_tods = sorted(decisions["tod"].astype(int).unique().tolist())
    return work, bands, decision_tods


def run_desired_positions(
    bars: pd.DataFrame, desired: pd.DataFrame, tick: float = 0.25
) -> pd.DataFrame:
    encoded, bands, decision_tods = encode_desired_positions(bars, desired, tick)
    trades = engine.run(
        encoded,
        bands,
        decision_tods=decision_tods,
        fill_mode="next_open",
        require_vwap=False,
        exit_check="decision",
    )
    if trades.empty:
        return pd.DataFrame(columns=[
            "date", "side", "entry_tod", "exit_tod", "entry_px", "exit_px", "points", "reason"
        ])
    return trades


def always_long_rth(bars: pd.DataFrame) -> pd.DataFrame:
    """One daily RTH open-to-last-close drift trade, the B0 economic floor."""
    rows = []
    for date, group in bars.groupby("date", sort=False):
        group = group.sort_values("tod")
        first, last = group.iloc[0], group.iloc[-1]
        rows.append({
            "date": date,
            "side": 1,
            "entry_tod": int(first["tod"]),
            "exit_tod": int(last["tod"]),
            "entry_px": float(first["open"]),
            "exit_px": float(last["close"]),
            "points": float(last["close"] - first["open"]),
            "reason": "rth_close",
        })
    return pd.DataFrame(rows)
