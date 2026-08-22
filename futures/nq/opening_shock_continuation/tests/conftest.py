"""Small deterministic fixtures for engine and feature unit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def session_factory():
    """Return a factory for complete daily rows without touching market data."""

    def make(n: int = 8, start: str = "2024-01-02") -> pd.DataFrame:
        dates = pd.bdate_range(start, periods=n)
        anchor = 100.0 + np.arange(n, dtype=float)
        gap_log = np.resize(np.array([0.010, -0.010, 0.006, -0.006]), n)
        opening_log = np.resize(np.array([0.008, -0.008, -0.004, 0.004]), n)
        r12_log = np.resize(np.array([0.003, -0.003]), n)
        r13_log = np.resize(np.array([0.005, -0.005]), n)

        o0930 = anchor * np.exp(gap_log)
        c0959 = o0930 * np.exp(opening_log)
        o1500 = anchor + 1.0
        c1529 = o1500 * np.exp(r12_log)
        o1530 = anchor + 1.5
        c1559 = o1530 * np.exp(r13_log)
        high30 = np.maximum(o0930, c0959) + 1.0
        low30 = np.minimum(o0930, c0959) - 1.0

        return pd.DataFrame(
            {
                "date": dates,
                "prev_close": anchor,
                "o0930": o0930,
                "c0959": c0959,
                "o1000": c0959 + 0.10,
                "o1001": c0959 + 0.20,
                "o1500": o1500,
                "c1529": c1529,
                "o1530": o1530,
                "c1559": c1559,
                "high30": high30,
                "low30": low30,
                "volume30": 1_000.0 + 100.0 * np.arange(n),
                "rv30": 0.010 + 0.001 * np.arange(n),
                "path30": np.abs(opening_log) + 0.020,
            }
        )

    return make
