from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_engine.pine_strategy import run_pine_strategy
from strategy.pine_translation import build_pine_features, wilder_rma


def _bars(n: int = 4) -> pd.DataFrame:
    index = pd.date_range("2024-01-01 00:05", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "audusd_open": np.ones(n),
            "audusd_high": np.full(n, 1.0005),
            "audusd_low": np.full(n, 0.9995),
            "audusd_close": np.ones(n),
        },
        index=index,
    )


def _minutes(n: int = 20) -> pd.DataFrame:
    index = pd.date_range("2024-01-01 00:00", periods=n, freq="1min")
    return pd.DataFrame({"open": 1.0, "high": 1.0005, "low": 0.9995, "close": 1.0}, index=index)


def _features(bars: pd.DataFrame, z: list[float], atr: float = 0.001) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "actual_audusd": bars["audusd_close"],
            "zscore": z,
            "atr": atr,
            "feature_ready": True,
        },
        index=bars.index,
    )


def test_wilder_rma_uses_sma_seed() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 6.0])
    actual = wilder_rma(values, 3)
    assert actual.iloc[:2].isna().all()
    assert np.isclose(actual.iloc[2], 2.0)
    assert np.isclose(actual.iloc[3], 2.0 + (6.0 - 2.0) / 3.0)


def test_pine_zscore_includes_current_bar_and_uses_population_std() -> None:
    bars = _bars(6)
    panel = bars.copy()
    panel["audjpy_close"] = 100.0
    panel["usdjpy_close"] = 100.0
    panel["audusd_close"] = [1.00, 1.01, 1.02, 1.03, 1.04, 1.10]
    features = build_pine_features(panel, bars, lookback_period=5, atr_period=1)
    window = np.array([1.01, 1.02, 1.03, 1.04, 1.10]) - 1.0
    expected = (window[-1] - window.mean()) / window.std(ddof=0)
    assert np.isclose(features["zscore"].iloc[-1], expected)


def test_entry_is_next_bar_and_dual_touch_is_stop_first() -> None:
    bars = _bars()
    minute = _minutes()
    minute.loc[pd.Timestamp("2024-01-01 00:05"), ["high", "low"]] = [1.004, 0.997]
    features = _features(bars, [-2.0, 0.0, 0.0, 0.0])
    trades, _, _ = run_pine_strategy(bars, minute, features, 5)
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade.entry_ts == pd.Timestamp("2024-01-01 00:05")
    assert trade.exit_ts == pd.Timestamp("2024-01-01 00:05")
    assert trade.exit_reason == "atr_stop"
    assert np.isclose(trade.exit_price, 0.998)


def test_z_reversion_exits_at_following_bar_open() -> None:
    bars = _bars()
    bars.loc[pd.Timestamp("2024-01-01 00:20"), "audusd_open"] = 1.001
    features = _features(bars, [-2.0, -1.0, -0.20, 0.0])
    trades, _, _ = run_pine_strategy(bars, _minutes(), features, 5, use_atr_risk=False)
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade.entry_ts == pd.Timestamp("2024-01-01 00:05")
    assert trade.exit_ts == pd.Timestamp("2024-01-01 00:15")
    assert trade.exit_reason == "z_reversion"
    assert np.isclose(trade.exit_price, 1.001)


def test_gap_through_stop_fills_at_minute_open() -> None:
    bars = _bars()
    minute = _minutes()
    minute.loc[pd.Timestamp("2024-01-01 00:05"), ["open", "high", "low", "close"]] = [0.997, 0.9975, 0.9965, 0.997]
    bars.loc[pd.Timestamp("2024-01-01 00:10"), "audusd_open"] = 0.997
    features = _features(bars, [-2.0, 0.0, 0.0, 0.0])
    trades, _, _ = run_pine_strategy(bars, minute, features, 5)
    assert len(trades) == 1
    assert trades.iloc[0].exit_reason == "atr_stop"
    assert np.isclose(trades.iloc[0].entry_price, 0.997)
    assert np.isclose(trades.iloc[0].exit_price, 0.997)
