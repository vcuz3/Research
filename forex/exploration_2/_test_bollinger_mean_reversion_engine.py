"""Executable invariants for the Bollinger re-entry mean-reversion engine."""

import numpy as np
import pandas as pd

from _bollinger_mean_reversion_engine import (
    _simulate_reentry,
    causal_same_slot_median,
    observed_bar_rolling,
    reentry_signals,
)


def test_observed_bar_bollinger_does_not_reset_at_wall_clock_gap():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    valid = pd.Series([True] * 5)
    # The helper has no wall-clock input by design: the fourth value continues
    # the last-three-observed-bars window even if a closure occurred before it.
    got = observed_bar_rolling(s, valid, 3, "mean")
    assert np.allclose(got.dropna(), [2.0, 3.0, 4.0])


def test_slot_median_is_shifted_and_causal():
    values = pd.Series([1.0, 100.0, 3.0, 4.0])
    slots = pd.Series([7, 7, 7, 7])
    sessions = pd.Series([0, 1, 2, 3])
    got = causal_same_slot_median(values, slots, sessions, 3, min_fraction=1 / 3)
    assert np.isnan(got.iloc[0])
    assert got.iloc[1] == 1.0
    assert got.iloc[2] == 50.5
    # Changing the future cannot change an earlier median.
    changed = causal_same_slot_median(pd.Series([1.0, 100.0, 3.0, -999.0]), slots, sessions, 3, 1 / 3)
    assert changed.iloc[2] == got.iloc[2]


def test_reentry_requires_later_close_back_inside():
    close = np.array([100.0, 103.0, 102.5, 101.5, 100.0])
    upper = np.full(5, 102.0)
    lower = np.full(5, 98.0)
    signal, age = reentry_signals(close, upper, lower, np.ones(5, bool), 4)
    assert signal.tolist() == [0, 0, 0, -1, 0]
    assert age[3] == 2


def base_arrays(n=8):
    open_ = np.full(n, 100.0)
    high = np.full(n, 101.0)
    low = np.full(n, 99.0)
    close = np.full(n, 100.0)
    signal = np.zeros(n, np.int8)
    target_long = np.full(n, 102.0)
    target_short = np.full(n, 98.0)
    stop_long = np.full(n, 95.0)
    stop_short = np.full(n, 105.0)
    sizing_long = np.full(n, 95.0)
    sizing_short = np.full(n, 105.0)
    min_risk = np.full(n, 1.0)
    friday = np.zeros(n, bool)
    return (open_, high, low, close, signal, target_long, target_short,
            stop_long, stop_short, sizing_long, sizing_short, min_risk, friday)


def test_next_open_entry_and_entry_bar_target():
    a = base_arrays()
    a[4][1] = 1
    a[0][2] = 100.5
    a[1][2] = 102.5
    out = _simulate_reentry(*a, 12, 0.0)
    assert out[0].tolist() == [2]
    assert out[1].tolist() == [2]
    assert out[3][0] == 100.5 and out[4][0] == 102.0
    assert out[6][0] == 1


def test_same_bar_stop_and_target_resolves_to_stop():
    a = base_arrays()
    a[4][1] = 1
    a[1][2] = 103.0
    a[2][2] = 94.0
    out = _simulate_reentry(*a, 12, 0.0)
    assert out[4][0] == 95.0
    assert out[6][0] == 2
    assert bool(out[7][0])


def test_gap_stop_fills_at_open_and_timeout_is_open_to_open():
    a = base_arrays()
    a[4][1] = 1
    a[0][2] = 94.0
    out = _simulate_reentry(*a, 12, 0.0)
    assert out[4][0] == 94.0 and bool(out[8][0])

    b = base_arrays()
    b[4][1] = 1
    b[5][:] = np.nan  # no target
    b[7][:] = np.nan  # no stop
    b[0][5] = 101.0
    out = _simulate_reentry(*b, 3, 0.0)
    assert out[0][0] == 2 and out[1][0] == 5
    assert out[4][0] == 101.0 and out[6][0] == 3


def test_subminimum_stop_distance_rejects_entry():
    a = list(base_arrays())
    a[4][1] = 1
    a[0][2] = 95.2  # only 0.2 from the sizing stop at 95
    a[11][:] = 1.0  # require at least 1.0 price unit of initial risk
    out = _simulate_reentry(*a, 12, 0.0)
    assert len(out[0]) == 0


if __name__ == "__main__":
    test_observed_bar_bollinger_does_not_reset_at_wall_clock_gap()
    test_slot_median_is_shifted_and_causal()
    test_reentry_requires_later_close_back_inside()
    test_next_open_entry_and_entry_bar_target()
    test_same_bar_stop_and_target_resolves_to_stop()
    test_gap_stop_fills_at_open_and_timeout_is_open_to_open()
    test_subminimum_stop_distance_rejects_entry()
    print("7 mean-reversion engine invariants passed")
