"""Fast invariants for the Bollinger breakout path engine."""

import numpy as np
import pandas as pd

from _bollinger_engine import _simulate, observed_bar_rolling


def base_arrays(n=6):
    open_ = np.full(n, 100.0)
    high = np.full(n, 101.0)
    low = np.full(n, 99.0)
    close = np.full(n, 100.0)
    signal = np.zeros(n, np.int8)
    long_stop = np.full(n, 95.0)
    short_stop = np.full(n, 105.0)
    segment = np.zeros(n, np.int64)
    force = np.zeros(n, bool)
    return open_, high, low, close, signal, long_stop, short_stop, segment, force


def test_observed_bar_bollinger_does_not_reset_at_wall_clock_gap():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    valid = pd.Series([True] * 5)
    # There is deliberately no timestamp or segment input: 4.0 continues the
    # last-three-observed-close window even if a closure occurred before it.
    got = observed_bar_rolling(series, valid, 3, "mean")
    assert np.allclose(got.dropna(), [2.0, 3.0, 4.0])


def test_signal_enters_next_open_and_fill_bar_stop_is_live():
    a = base_arrays()
    a[4][1] = 1
    a[0][2] = 102.0
    a[2][2] = 94.0
    out = _simulate(*a, 0.0)
    assert out[0].tolist() == [2]
    assert out[1].tolist() == [2]
    assert out[3][0] == 102.0
    assert out[4][0] == 95.0


def test_gap_through_stop_fills_at_open_not_stale_stop():
    a = base_arrays()
    a[4][1] = 1
    a[0][2] = 94.0
    a[1][2] = 95.0
    a[2][2] = 93.0
    out = _simulate(*a, 0.0)
    assert out[4][0] == 94.0
    assert bool(out[7][0])
    assert bool(out[8][0])


def test_long_stop_only_ratchets_up():
    a = base_arrays()
    a[4][1] = 1
    a[0][2:] = [100.0, 100.0, 100.0, 100.0]
    a[1][:] = 104.0
    a[2][:] = 98.0
    a[5][:] = [95.0, 95.0, 97.0, 96.0, 96.0, 96.0]
    a[8][4] = True
    out = _simulate(*a, 0.0)
    # Candidate 97 becomes live on bar 3; the later 96 cannot loosen it.
    assert out[4][0] == 100.0
    assert out[6][0] == 2


def test_friday_close_precedes_sample_end():
    a = base_arrays()
    a[4][1] = -1
    a[3][4] = 98.0
    a[8][4] = True
    out = _simulate(*a, 0.0)
    assert out[1][0] == 4
    assert out[4][0] == 98.0
    assert out[6][0] == 2


if __name__ == "__main__":
    test_observed_bar_bollinger_does_not_reset_at_wall_clock_gap()
    test_signal_enters_next_open_and_fill_bar_stop_is_live()
    test_gap_through_stop_fills_at_open_not_stale_stop()
    test_long_stop_only_ratchets_up()
    test_friday_close_precedes_sample_end()
    print("5 engine invariants passed")
