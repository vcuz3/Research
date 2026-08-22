"""Synthetic-only tests for the frozen paper-baseline validation gate."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futures.nq.opening_shock_continuation.backtest_engine.metrics import hac_mean_se, hac_t
from futures.nq.opening_shock_continuation.scripts.run_baseline import _frozen_scope
from futures.nq.opening_shock_continuation.validation.baseline import (
    injected_positive_control,
    primary_cost_mde,
    year_conditioned_circular_null,
)


def test_baseline_scope_cannot_expand_when_local_data_grows() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2013-12-31", "2014-01-02", "2026-07-14", "2026-07-15"]),
            "value": [1, 2, 3, 4],
        }
    )
    scoped = _frozen_scope(
        frame,
        {"paper_overlap_start": "2014-01-01", "persistence_end": "2026-07-14"},
    )
    assert scoped["value"].tolist() == [2, 3]


def test_baseline_null_scores_zero_filled_primary_cost_hac_t_deterministically() -> None:
    n = 520
    dates = pd.Series(pd.bdate_range("2022-01-03", periods=n))
    side = np.resize(np.array([1, -1, 1, 1, -1], dtype=int), n)
    outcome_points = np.sin(np.arange(n) / 13.0) + side * 0.08
    multiplier = 50.0
    cost = 29.5
    pnl = side * outcome_points * multiplier - cost

    first = year_conditioned_circular_null(
        outcome_points,
        side,
        dates,
        multiplier=multiplier,
        round_trip_cost_dollars=cost,
        hac_lags=5,
        draws=79,
        seed=1234,
    )
    second = year_conditioned_circular_null(
        outcome_points,
        side,
        dates,
        multiplier=multiplier,
        round_trip_cost_dollars=cost,
        hac_lags=5,
        draws=79,
        seed=1234,
    )
    assert first.observed_hac_t == pytest.approx(hac_t(pnl, max_lag=5))
    assert np.isfinite(first.null_hac_t).all()
    assert len(first.null_hac_t) == 79
    assert first.pvalue == pytest.approx((1 + first.exceedances) / 80)
    np.testing.assert_allclose(first.null_hac_t, second.null_hac_t)


def test_baseline_null_rejects_zero_variance_draw_distribution() -> None:
    dates = pd.Series(pd.bdate_range("2023-01-02", periods=30))
    side = np.resize(np.array([1, -1], dtype=int), len(dates))
    with pytest.raises(ValueError, match="zero variance"):
        year_conditioned_circular_null(
            np.ones(len(dates)),
            side,
            dates,
            multiplier=50.0,
            round_trip_cost_dollars=0.0,
            hac_lags=1,
            draws=19,
            seed=7,
        )


def test_primary_cost_mde_reports_daily_and_per_trade_units() -> None:
    net_dollars = np.array([20.0, 0.0, -10.0, 0.0, 30.0, -5.0])
    trade = np.array([True, False, True, False, True, True])
    side = np.array([1, 0, -1, 0, 1, -1])
    trades = pd.DataFrame(
        {
            "trade": trade,
            "side": side,
            "net_dollars": net_dollars,
            "net_bps": net_dollars / 10.0,
        }
    )
    result = primary_cost_mde(
        trades,
        instrument="ES",
        hac_lags=1,
        multiplier=2.49,
    )
    expected_daily_dollars = 2.49 * hac_mean_se(net_dollars, max_lag=1)
    trade_rate = trade.mean()
    assert result["trade_rate"] == pytest.approx(trade_rate)
    assert result["mde_daily"]["dollars"] == pytest.approx(expected_daily_dollars)
    assert result["mde_per_trade"]["dollars"] == pytest.approx(
        expected_daily_dollars / trade_rate
    )
    assert result["mde_daily"]["points"] == pytest.approx(expected_daily_dollars / 50.0)
    assert result["mde_daily"]["ticks"] == pytest.approx(
        result["mde_daily"]["points"] / 0.25
    )
    assert result["mde_daily"]["bps"] == pytest.approx(
        2.49 * hac_mean_se(net_dollars / 10.0, max_lag=1)
    )


def test_injected_positive_control_hits_sharpe_half_and_passes_full_synthetic_null() -> None:
    n = 3_200
    rng = np.random.default_rng(20260820)
    dates = pd.Series(pd.bdate_range("2020-01-02", periods=n))
    side = rng.choice(np.array([-1, 1], dtype=int), size=n)
    outcome_points = rng.normal(0.0, 1.0, size=n)

    result = injected_positive_control(
        outcome_points,
        side,
        dates,
        multiplier=50.0,
        round_trip_cost_dollars=29.5,
        target_zero_filled_net_sharpe=0.50,
        hac_lags=5,
        draws=4_999,
        seed=20260821,
    )
    assert result.achieved_zero_filled_net_sharpe == pytest.approx(0.50, abs=1e-12)
    assert result.injected_effect_points_per_trade > 0
    assert np.isfinite(result.null.null_hac_t).all()
    assert result.null.pvalue <= 0.05
