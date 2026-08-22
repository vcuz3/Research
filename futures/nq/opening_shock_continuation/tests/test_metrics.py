"""Synthetic daily-estimand and risk-metric tests."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from futures.nq.opening_shock_continuation.backtest_engine.metrics import (
    era_label,
    grouped_summaries,
    summarize,
)


def _metric_frame(net: list[float], trade: list[bool] | None = None) -> pd.DataFrame:
    n = len(net)
    traded = np.ones(n, dtype=bool) if trade is None else np.asarray(trade, dtype=bool)
    side = np.zeros(n, dtype=int)
    side[traded] = np.resize(np.array([1, -1]), int(traded.sum()))
    gross = np.asarray(net, dtype=float) + np.where(traded, 2.0, 0.0)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-02", periods=n),
            "side": side,
            "trade": traded,
            "gross_dollars": gross,
            "net_dollars": np.asarray(net, dtype=float),
            "gross_bps": gross / 10.0,
            "net_bps": np.asarray(net, dtype=float) / 10.0,
            "slippage_dollars": np.where(traded, 1.0, 0.0),
            "fees_dollars": np.where(traded, 1.0, 0.0),
        }
    )


def test_summary_includes_flat_sessions_in_daily_estimand() -> None:
    frame = _metric_frame([10.0, 0.0, -5.0, 0.0], [True, False, True, False])
    result = summarize(frame, hac_lags=1)
    values = np.array([10.0, 0.0, -5.0, 0.0])
    expected_sharpe = math.sqrt(252.0) * values.mean() / values.std(ddof=1)
    expected_t = values.mean() / (values.std(ddof=1) / math.sqrt(len(values)))
    assert result["eligible_sessions"] == 4
    assert result["trades"] == 2
    assert result["trade_rate"] == pytest.approx(0.5)
    assert result["net_total_dollars"] == pytest.approx(5.0)
    assert result["net_mean_daily_dollars"] == pytest.approx(1.25)
    assert result["net_mean_trade_dollars"] == pytest.approx(2.5)
    assert result["daily_sharpe_net"] == pytest.approx(expected_sharpe)
    assert result["iid_t_net"] == pytest.approx(expected_t)
    assert result["annualized_net_dollars"] == pytest.approx(315.0)
    assert result["long_trades"] == 1
    assert result["short_trades"] == 1
    assert result["trade_hit_rate"] == pytest.approx(0.5)
    assert result["profit_factor"] == pytest.approx(2.0)


def test_summary_cost_totals_and_drawdown_are_hand_reconciled() -> None:
    frame = _metric_frame([-5.0, 10.0, -3.0, -8.0], [True, True, True, True])
    result = summarize(frame)
    assert result["gross_total_dollars"] == pytest.approx(2.0)
    assert result["slippage_total_dollars"] == pytest.approx(4.0)
    assert result["fees_total_dollars"] == pytest.approx(4.0)
    assert result["net_total_dollars"] == pytest.approx(-6.0)
    # Equity: -5, +5, +2, -6; peak including starting equity is +5.
    assert result["max_drawdown_dollars"] == pytest.approx(-11.0)


def test_summary_rejects_missing_columns_duplicate_dates_and_nonfinite_pnl() -> None:
    frame = _metric_frame([1.0, -1.0])
    with pytest.raises(ValueError, match="missing trade columns"):
        summarize(frame.drop(columns="fees_dollars"))

    duplicate = frame.copy()
    duplicate.loc[1, "date"] = duplicate.loc[0, "date"]
    with pytest.raises(ValueError, match="one row per eligible session"):
        summarize(duplicate)

    nonfinite = frame.copy()
    nonfinite.loc[1, "net_dollars"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        summarize(nonfinite)


def test_empty_summary_has_zero_counts_and_no_undefined_statistics() -> None:
    result = summarize(_metric_frame([]))
    assert result["eligible_sessions"] == 0
    assert result["trades"] == 0
    assert result["trade_rate"] is None
    assert result["daily_sharpe_net"] is None
    assert result["iid_t_net"] is None
    assert result["hac_t_net_lag5"] is None
    assert result["max_drawdown_dollars"] is None


def test_grouped_summaries_retain_zero_days_inside_each_group() -> None:
    frame = _metric_frame([5.0, 0.0, -2.0, 0.0], [True, False, True, False])
    groups = pd.Series(["a", "a", "b", "b"], index=frame.index)
    result = grouped_summaries(frame, groups).set_index("group")
    assert result.loc["a", "eligible_sessions"] == 2
    assert result.loc["a", "trades"] == 1
    assert result.loc["a", "net_mean_daily_dollars"] == pytest.approx(2.5)
    assert result.loc["b", "eligible_sessions"] == 2
    assert result.loc["b", "trades"] == 1
    assert result.loc["b", "net_mean_daily_dollars"] == pytest.approx(-1.0)


def test_era_boundaries_are_explicit_and_inclusive() -> None:
    dates = pd.Series(
        pd.to_datetime(
            ["2010-12-31", "2018-12-31", "2019-01-01", "2022-12-31", "2023-01-01"]
        )
    )
    assert era_label(dates).tolist() == [
        "outside_scope",
        "discovery_2011_2018",
        "validation_2019_2022",
        "validation_2019_2022",
        "validation_b_2023_2026",
    ]
