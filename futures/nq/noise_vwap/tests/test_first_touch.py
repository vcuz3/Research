import numpy as np

from futures.nq.noise_vwap.core.first_touch import simulate_session_1s


def _base(sec_open, sec_high, sec_low, latency=0, trigger=0):
    minute_ts = np.array([0, 60, 120], dtype=np.int64) * 1_000_000_000
    return simulate_session_1s(
        np.array([60, 61], dtype=np.int64) * 1_000_000_000,
        np.asarray(sec_open, float), np.asarray(sec_high, float), np.asarray(sec_low, float),
        minute_ts, np.array([100, 102, 101], float), np.array([102, 101, 101], float),
        np.array([100, 100, 100], float), np.array([101, 101, 101], float),
        np.array([99, 99, 99], float), np.array([True, False, False]), True, latency, trigger,
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


def test_latency_default_is_instant_touch():
    # Touch at the first second (low 101.5 does not reach stop 101; low 100.5 does
    # at k=1); default latency reproduces the instantaneous first-touch fill.
    a = _base([102, 101], [103, 102], [101.5, 100.5])
    b = _base([102, 101], [103, 102], [101.5, 100.5], latency=0)
    assert a[4][0] == b[4][0] == 101.0


def test_latency_fills_later_and_never_better():
    # Stop = 101. Touch at k=0 (low 100.5). Price keeps falling into k=1
    # (open 100.2 < open 100.8). A 1-second execution delay must fill at the
    # later, worse open, never better than the instant fill.
    instant = _base([100.8, 100.2], [101.0, 101.0], [100.5, 100.0], latency=0)
    delayed = _base([100.8, 100.2], [101.0, 101.0], [100.5, 100.0], latency=1)
    assert instant[4][0] == 100.8
    assert delayed[4][0] == 100.2
    assert delayed[4][0] <= instant[4][0]


def test_close_confirmed_ignores_a_wick_that_first_touch_takes():
    # Long, stop = max(upper[0]=101, vwap[0]=100) = 101. The seconds wick to
    # low 100.5 <= 101 (a touch) but both minute closes stay at/above 101, so
    # the bar never closes below the band.
    sec_open, sec_high, sec_low = [101.0, 101.0], [101.5, 101.5], [100.5, 100.5]
    touch = _base(sec_open, sec_high, sec_low, trigger=0)
    confirmed = _base(sec_open, sec_high, sec_low, trigger=1)
    # First-touch exits on the wick (reason 0 = touch/stop).
    assert touch[5].tolist() == [0]
    # Close-confirmed holds through the wick and only flattens at EOD (reason 2).
    assert confirmed[5].tolist() == [2]
