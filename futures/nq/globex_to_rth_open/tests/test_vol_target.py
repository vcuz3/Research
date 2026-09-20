from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backtest_engine.vol_target import (
    VolTargetSpec, build_vol_targeted_leg, summarize_return_period,
)


def _candidates(returns: np.ndarray, entry: float = 10000.0) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=len(returns), freq="B")
    entry_ts = dates.tz_localize("America/New_York") + pd.Timedelta(hours=18)
    exit_ts = entry_ts + pd.Timedelta(hours=15, minutes=30)
    return pd.DataFrame({
        "trade_date": dates,
        "entry_ts": entry_ts.tz_convert("UTC"),
        "exit_ts": exit_ts.tz_convert("UTC"),
        "entry_price": entry,
        "exit_price": entry * (1.0 + returns),
    })


def test_vol_window_is_60_observations_and_lagged_one_day():
    history = np.linspace(-0.01, 0.01, 60)
    returns = np.r_[history, 0.25, -0.20]
    spec = VolTargetSpec(lookback_days=60, lag_days=1)
    daily, quality = build_vol_targeted_leg(_candidates(returns), spec)
    expected = history.std(ddof=1) * np.sqrt(252)
    assert quality["warmup_removed"] == 60
    assert np.isclose(daily.loc[0, "annualized_vol_estimate"], expected)
    assert np.isclose(daily.loc[0, "leverage"], min(0.10 / expected, 3.0))
    # The 25% current return cannot enter its own volatility estimate.
    assert daily.loc[0, "gross_leg_return"] > 0.24


def test_half_bp_cost_is_capped_at_one_tick_per_side():
    returns = np.linspace(-0.01, 0.01, 61)
    spec = VolTargetSpec(lookback_days=60, cost_bps_per_side=0.5,
                         cost_cap_points_per_side=0.25)
    high, _ = build_vol_targeted_leg(_candidates(returns, entry=10000), spec)
    assert high.loc[0, "entry_cost_points"] == 0.25
    assert high.loc[0, "exit_cost_points"] == 0.25
    low, _ = build_vol_targeted_leg(_candidates(returns, entry=1000), spec)
    assert np.isclose(low.loc[0, "entry_cost_points"], 0.05)


def test_period_return_compounds_and_drawdown_is_percentage_wealth():
    frame = pd.DataFrame({
        "trade_date": pd.to_datetime(["2020-01-02", "2020-01-03"]),
        "gross_strategy_return": [0.10, -0.10],
        "net_strategy_return": [0.10, -0.10],
        "leverage": [1.0, 1.0],
        "annualized_vol_estimate": [0.10, 0.10],
    })
    result = summarize_return_period(frame)
    assert np.isclose(result["net_compound_return"], -0.01)
    assert np.isclose(result["max_drawdown"], -0.10)


def test_inactive_days_are_zero_return_observations_not_trades():
    frame = pd.DataFrame({
        "trade_date": pd.to_datetime(["2020-01-02", "2020-01-03"]),
        "gross_strategy_return": [0.10, 0.0],
        "net_strategy_return": [0.10, 0.0],
        "leverage": [1.0, 2.0], "effective_leverage": [1.0, 0.0],
        "annualized_vol_estimate": [0.10, 0.10], "active": [True, False],
    })
    result = summarize_return_period(frame)
    assert result["observations"] == 2
    assert result["trades"] == 1
    assert result["average_leverage"] == 1.0
    assert result["average_portfolio_leverage"] == 0.5

