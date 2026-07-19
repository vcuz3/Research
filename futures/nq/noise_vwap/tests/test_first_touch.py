import numpy as np

from futures.nq.noise_vwap.core.first_touch import simulate_session_1s


def _base(sec_open, sec_high, sec_low):
    minute_ts = np.array([0, 60, 120], dtype=np.int64) * 1_000_000_000
    return simulate_session_1s(
        np.array([60, 61], dtype=np.int64) * 1_000_000_000,
        np.asarray(sec_open, float), np.asarray(sec_high, float), np.asarray(sec_low, float),
        minute_ts, np.array([100, 102, 101], float), np.array([102, 101, 101], float),
        np.array([100, 100, 100], float), np.array([101, 101, 101], float),
        np.array([99, 99, 99], float), np.array([True, False, False]), True,
    )


def test_touch_uses_prior_completed_bar_and_first_second():
    side, _, exit_ts, _, exit_px, reason = _base([102, 101], [103, 102], [101.5, 100.5])
    assert side.tolist() == [1]
    assert exit_ts[0] == 61_000_000_000
    assert exit_px[0] == 101.0
    assert reason[0] == 0


def test_gap_through_fills_at_worse_first_tradable_open():
    side, _, _, _, exit_px, _ = _base([100.0, 101], [100.5, 102], [99.5, 100.5])
    assert side.tolist() == [1]
    assert exit_px[0] == 100.0
