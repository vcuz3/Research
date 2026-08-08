"""Executable invariants for features, state transitions, and fills."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_engine.engine import _simulate_strategy, clustered_mean_t, run_config
from strategy.twap_zband import StrategyConfig, _wilder_rma, build_signal_bars


def fixture_arrays():
    n_raw = 12
    raw_open = np.full(n_raw, 100.0)
    raw_high = np.full(n_raw, 100.1)
    raw_low = np.full(n_raw, 99.9)
    raw_close = np.full(n_raw, 100.0)
    raw_open[6] = raw_close[6] = 98.2
    raw_high[6], raw_low[6] = 98.4, 98.0
    raw_open[7] = raw_close[7] = 100.0
    raw_high[7], raw_low[7] = 100.4, 99.8

    bar_high = np.full(6, 101.0)
    bar_low = np.full(6, 99.0)
    bar_close = np.array([100.0, 97.0, 98.0, 100.0, 100.0, 100.0])
    bar_start = np.arange(0, 12, 2, dtype=np.int64)
    bar_end = bar_start + 1
    baseline = np.full(6, 100.0)
    stdev = np.full(6, 1.0)
    atr = np.full(6, 1.0)
    return [
        bar_high, bar_low, bar_close, bar_start, bar_end, baseline, stdev, atr,
        raw_open, raw_high, raw_low, raw_close,
    ]


def simulate(arrays, max_arm=10):
    return _simulate_strategy(*arrays, 2.5, max_arm, 2.0, 1.0)


def test_user_parameters_arm_at_2_5_and_enter_next_open():
    out = simulate(fixture_arrays())
    assert out[0].tolist() == [2]  # signal after the close back inside
    assert out[1].tolist() == [6]  # next coarse bar's first one-minute open
    assert np.isclose(out[4][0], 98.2)
    assert np.isclose(out[6][0], 96.2)  # 2 ATR below actual entry
    assert np.isclose(out[7][0], 100.2)  # symmetric 1R target
    assert out[10][0] == 1


def test_entry_minute_both_barriers_resolves_to_stop():
    arrays = fixture_arrays()
    arrays[9][6] = 101.0
    arrays[10][6] = 95.0
    out = simulate(arrays)
    assert out[2][0] == 6
    assert np.isclose(out[5][0], 96.2)
    assert out[10][0] == 2
    assert bool(out[11][0])


def test_gap_through_stop_fills_at_first_tradable_open():
    arrays = fixture_arrays()
    arrays[8][7] = 95.0
    arrays[9][7] = 95.2
    arrays[10][7] = 94.8
    arrays[11][7] = 95.0
    out = simulate(arrays)
    assert out[2][0] == 7
    assert np.isclose(out[5][0], 95.0)
    assert out[10][0] == 2
    assert bool(out[12][0])


def test_timeout_matches_pine_strict_greater_than():
    arrays = fixture_arrays()
    # Re-entry one bar after arming is permitted when max_arm_bars == 1.
    assert len(simulate(arrays, max_arm=1)[0]) == 1
    # Move re-entry one additional bar later: age 2 > 1 disarms first.
    arrays[2][2] = 97.2
    arrays[2][3] = 98.0
    assert len(simulate(arrays, max_arm=1)[0]) == 0


def test_wilder_atr_has_sma_seed_not_ewm_first_value_seed():
    values = np.array([1.0, 2.0, 3.0, 6.0])
    got = _wilder_rma(values, 3)
    assert np.isnan(got[0]) and np.isnan(got[1])
    assert np.isclose(got[2], 2.0)
    assert np.isclose(got[3], 2.0 + (6.0 - 2.0) / 3.0)


def test_session_twap_and_pine_style_running_dispersion_are_causal():
    ts = pd.date_range("2019-01-02 22:00", periods=45, freq="min")
    close = np.linspace(1.0, 1.0044, len(ts))
    raw = pd.DataFrame(
        {
            "ts_utc": ts,
            "open": close,
            "high": close + 0.0001,
            "low": close - 0.0001,
            "close": close,
            "raw_i": np.arange(len(ts), dtype=np.int64),
        }
    )
    cfg = StrategyConfig(bar_minutes=15)
    bars, coverage = build_signal_bars(raw, [cfg])
    src = (bars.high + bars.low + bars.close) / 3
    assert len(bars) == 3 and coverage.complete_bars.sum() == 3
    assert np.isclose(bars.session_twap.iloc[1], src.iloc[:2].mean())
    changed = raw.copy()
    changed.loc[30:, ["open", "high", "low", "close"]] += 10
    earlier, _ = build_signal_bars(changed, [cfg])
    assert np.isclose(earlier.session_twap.iloc[1], bars.session_twap.iloc[1])


def test_cost_is_subtracted_once_and_cluster_t_is_session_robust():
    arrays = fixture_arrays()
    out = simulate(arrays)
    bars = pd.DataFrame(
        {
            "bar_open": pd.date_range("2019-01-01", periods=6, freq="15min"),
            "high": arrays[0], "low": arrays[1], "close": arrays[2],
            "raw_start_i": arrays[3], "raw_end_i": arrays[4],
            "session_id": ["2018-12-31"] * 6,
            "session_twap": arrays[5], "session_std": arrays[6], "atr_14": arrays[7],
        }
    )
    raw = pd.DataFrame(
        {
            "ts_utc": pd.date_range("2019-01-01", periods=12, freq="min"),
            "open": arrays[8], "high": arrays[9], "low": arrays[10], "close": arrays[11],
        }
    )
    cfg = StrategyConfig(round_trip_cost_pips=1.0)
    trades = run_config(bars, raw, "EURUSD", cfg)
    assert len(trades) == len(out[0]) == 1
    assert np.isclose(trades.net_pips.iloc[0], trades.gross_pips.iloc[0] - 1.0)
    se, t = clustered_mean_t(pd.Series([1.0, 0.0, 2.0, -2.0]), pd.Series([1, 1, 2, 2]))
    assert np.isfinite(se) and np.isfinite(t)


def test_no_overlapping_positions():
    arrays = fixture_arrays()
    # Keep the first position alive to end-of-data; later excursion cannot enter.
    arrays[9][:] = arrays[8] + 0.1
    arrays[10][:] = arrays[8] - 0.1
    arrays[2][3:] = np.array([103.0, 102.0, 100.0])
    out = simulate(arrays)
    assert len(out[0]) == 1
