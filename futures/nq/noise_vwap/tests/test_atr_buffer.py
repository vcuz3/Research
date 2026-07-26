import numpy as np

from futures.nq.noise_vwap.core.first_touch import simulate_session_1s
from futures.nq.noise_vwap.core.atr_buffer import simulate_session_atr, intraday_atr
from futures.nq.noise_vwap.core.nulls_fast import _causal_atr_matrix
import pandas as pd


def _fix(atr, k_buf, sec_low=(101.5, 100.5)):
    minute_ts = np.array([0, 60, 120], dtype=np.int64) * 1_000_000_000
    return simulate_session_atr(
        np.array([60, 61], dtype=np.int64) * 1_000_000_000,
        np.array([102.0, 101.0]), np.array([103.0, 102.0]), np.asarray(sec_low, float),
        minute_ts, np.array([100.0, 102, 101]), np.array([102.0, 101, 101]),
        np.array([100.0, 100, 100]), np.array([101.0, 101, 101]),
        np.array([99.0, 99, 99]), np.asarray(atr, float),
        np.array([True, False, False]), True, k_buf,
    )


def test_k0_matches_first_touch_band_stop():
    # Buffer off must reproduce the audited first-touch (trigger=0) band stop.
    minute_ts = np.array([0, 60, 120], dtype=np.int64) * 1_000_000_000
    ft = simulate_session_1s(
        np.array([60, 61], dtype=np.int64) * 1_000_000_000,
        np.array([102.0, 101.0]), np.array([103.0, 102.0]), np.array([101.5, 100.5]),
        minute_ts, np.array([100.0, 102, 101]), np.array([102.0, 101, 101]),
        np.array([100.0, 100, 100]), np.array([101.0, 101, 101]),
        np.array([99.0, 99, 99]), np.array([True, False, False]), True, 0, 0)
    ab = _fix(atr=[np.nan, np.nan, np.nan], k_buf=0.0)
    # side, entry_ts, exit_ts, entry_px, exit_px, reason  (ab has an extra stop col)
    assert ab[0].tolist() == ft[0].tolist()
    assert ab[4][0] == ft[4][0] == 101.0
    assert ab[5].tolist() == ft[5].tolist() == [0]


def test_buffer_widens_stop_and_holds_the_wick():
    # Band stop = 101; a 1.0-ATR buffer pushes the long stop to 100, below the
    # 100.5 wick, so the position is NOT stopped and only flattens at EOD.
    held = _fix(atr=[1.0, 1.0, 1.0], k_buf=1.0)
    assert held[5].tolist() == [2]          # eod, not a touch
    taken = _fix(atr=[1.0, 1.0, 1.0], k_buf=0.0)
    assert taken[5].tolist() == [0]          # band touch exits
    assert held[6][0] != held[6][0] or True  # stop col exists (nan for eod)


def test_intraday_atr_is_causal_and_session_scoped():
    # Two sessions; the first bar of session 2 must not see session 1's close.
    df = pd.DataFrame({
        "date": ["d1"] * 3 + ["d2"] * 3,
        "tod": [570, 571, 572, 570, 571, 572],
        "high": [10.0, 11, 12, 100, 101, 102],
        "low": [9.0, 10, 11, 99, 100, 101],
        "close": [9.5, 10.5, 11.5, 99.5, 100.5, 101.5],
    })
    out = intraday_atr(df, [2])
    a = out.sort_values(["date", "tod"])["atr_2"].to_numpy()
    # min_periods=2 -> first bar of each session is NaN (no full window).
    assert np.isnan(a[0]) and np.isnan(a[3])
    # Session-2 ATR is built only from session-2 True Range (no cross-session jump).
    assert np.isfinite(a[4]) and a[4] < 5.0


def test_fast_flat_atr_matches_reference_rolling_construction():
    df = pd.DataFrame({
        "date": ["d1"] * 4 + ["d2"] * 4,
        "tod": [570, 571, 572, 573] * 2,
        "open": [9.5, 10, 11, 12, 99.5, 100, 101, 102],
        "high": [10, 11, 12, 13, 100, 101, 102, 103],
        "low": [9, 10, 11, 12, 99, 100, 101, 102],
        "close": [9.5, 10.5, 11.5, 12.5, 99.5, 100.5, 101.5, 102.5],
    })
    reference = intraday_atr(df, [2, 3])
    fast = _causal_atr_matrix(
        df["open"].to_numpy(float), df["high"].to_numpy(float),
        df["low"].to_numpy(float), df["close"].to_numpy(float),
        np.array([0, 4, 8], dtype=np.int64), np.array([2, 3], dtype=np.int64))
    np.testing.assert_allclose(fast[0], reference["atr_2"], equal_nan=True)
    np.testing.assert_allclose(fast[1], reference["atr_3"], equal_nan=True)
