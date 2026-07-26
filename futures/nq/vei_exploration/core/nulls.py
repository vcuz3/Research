"""Path-preserving Null C for the VEI momentum test.

Reuses the AUDITED reference implementation `noise_vwap.core.nulls.null_c_returns`
(RULES rule 17 names it as a maintained reference; it pins the opening atom, preserving
the session net move / bar geometry / volumes while destroying intraday ORDER). We only
adapt the column names: this project keys sessions by (sdate, mfo); the reference keys
by (date, tod). For a MOMENTUM strategy this null destroys the serial dependence the
edge exploits while preserving drift, so a real edge must beat it (the excess over the
null is machinery-manufactured P&L).
"""
from __future__ import annotations

import pandas as pd

from futures.nq.noise_vwap.core.nulls import (
    null_c_returns as _null_c_returns, diffusivity as _diffusivity,
)


def _to_ref(bars: pd.DataFrame) -> pd.DataFrame:
    return (bars[["sdate", "mfo", "open", "high", "low", "close", "volume"]]
            .rename(columns={"sdate": "date", "mfo": "tod"}))


def null_c(bars: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Return-shuffled bars with (sdate, mfo, open, high, low, close, volume)."""
    out = _null_c_returns(_to_ref(bars), seed)
    return (out[["date", "tod", "open", "high", "low", "close", "volume"]]
            .rename(columns={"date": "sdate", "tod": "mfo"})
            .sort_values(["sdate", "mfo"]).reset_index(drop=True))


def diffusivity(bars: pd.DataFrame) -> float:
    """Median |next_open - this_close| across within-session steps (rule 17-bis gate)."""
    return _diffusivity(_to_ref(bars))
