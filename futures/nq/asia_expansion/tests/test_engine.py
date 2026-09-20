"""Engine audit: hand-computable fixtures for the signal, the fill, and the SE."""
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3].parent))
from futures.nq.asia_expansion.strategy.signal import signals, _trailing_mean
from futures.nq.asia_expansion.backtest_engine.stats import cluster_t, COST_LADDER


def _bars(ranges, closes=None, opens=None, date="2020-01-02"):
    """Build a synthetic session whose bar ranges are EXACTLY `ranges`.

    open/close default to a +0.5 up-bar; the remaining range is split evenly above
    and below the body so that high-low == the requested range exactly.
    """
    n = len(ranges)
    opens = np.arange(100.0, 100.0 + n) if opens is None else np.asarray(opens, float)
    closes = opens + 0.5 if closes is None else np.asarray(closes, float)
    rng = np.asarray(ranges, float)
    body = np.abs(closes - opens)
    assert (rng >= body - 1e-12).all(), "requested range smaller than the body"
    pad = (rng - body) / 2.0
    hi = np.maximum(opens, closes) + pad
    lo = np.minimum(opens, closes) - pad
    out = pd.DataFrame({
        "et": pd.date_range("2020-01-01 18:00", periods=n, freq="5min"),
        "trade_date": pd.Timestamp(date), "bar_i": np.arange(n),
        "slot": "18:00", "open": opens, "high": hi, "low": lo, "close": closes,
        "volume": 100, "range": hi - lo,
    })
    assert np.allclose(out["range"], rng)
    return out


def test_rolling_mean_is_causal_and_excludes_current_bar():
    x = np.array([1.0, 2, 3, 4, 100])
    m, cnt = _trailing_mean(x, start=np.zeros(5, int), n=3, min_periods=2)
    assert np.isnan(m[0]) and np.isnan(m[1])          # under-populated
    assert m[2] == 1.5                                 # mean(1,2)
    assert m[3] == 2.0                                 # mean(1,2,3)
    assert m[4] == 3.0                                 # mean(2,3,4) -- NOT the 100
    print("PASS causal rolling mean excludes the current bar")


def test_rolling_window_never_crosses_a_session_boundary():
    # two 5-bar sessions laid end to end; session 2's window must ignore session 1
    x = np.array([9.0, 9, 9, 9, 9, 1, 2, 3, 4, 5])
    start = np.array([0] * 5 + [5] * 5)
    m, cnt = _trailing_mean(x, start=start, n=3, min_periods=2)
    assert np.isnan(m[5]) and np.isnan(m[6])           # session 2 has no history yet
    assert m[7] == 1.5                                 # mean(1,2) -- no 9s leak in
    assert m[9] == 3.0                                 # mean(2,3,4)
    assert cnt[9] == 3
    print("PASS the trailing window clamps at the session open")


def test_trigger_is_exactly_k_times_the_trailing_mean():
    # ranges: four bars of 1.0 then one bar of exactly 1.5 -> fires at k=1.5, not at 1.6
    b = _bars([1, 1, 1, 1, 1.5, 1.4])
    s = signals(b, k=1.5, n=4, hold=1)
    assert list(s["bar_i"]) == [4], list(s["bar_i"])
    s2 = signals(b, k=1.6, n=4, hold=1)
    assert len(s2) == 0
    print("PASS trigger boundary is exact (>= k*M)")


def test_fill_is_next_bar_open_and_exit_is_hold_bars_later():
    b = _bars([1, 1, 1, 1, 5, 1, 1, 1, 1])
    s = signals(b, k=1.5, n=4, hold=2)
    r = s.iloc[0]
    t = int(r["bar_i"])
    assert r["entry"] == b["open"].iloc[t + 1]
    assert r["exit"] == b["open"].iloc[t + 1 + 2]
    assert not r["truncated"]
    assert np.isclose(r["gross_pts"], r["dir"] * (r["exit"] - r["entry"]))
    print("PASS next-open entry, open[t+1+H] exit")


def test_no_signal_can_use_a_bar_that_does_not_exist():
    # expansion on the LAST bar: no next bar to fill at -> must be dropped entirely
    b = _bars([1, 1, 1, 1, 5])
    assert len(signals(b, k=1.5, n=4, hold=1)) == 0
    # expansion on the second-to-last bar: entry exists, exit truncates to last close
    b2 = _bars([1, 1, 1, 1, 5, 1])
    s = signals(b2, k=1.5, n=4, hold=5)
    assert len(s) == 1 and bool(s.iloc[0]["truncated"])
    assert s.iloc[0]["exit"] == b2["close"].iloc[-1]
    print("PASS no fill is credited from a bar outside the session")


def test_direction_is_the_expansion_bars_own_sign():
    # bar 4 is the expansion; bar 5 exists only so the entry has a bar to fill at
    up = _bars([1, 1, 1, 1, 5, 1], opens=[100, 101, 102, 103, 104, 105],
               closes=[100.5, 101.5, 102.5, 103.5, 106.0, 105.5])
    dn = _bars([1, 1, 1, 1, 5, 1], opens=[100, 101, 102, 103, 104, 105],
               closes=[100.5, 101.5, 102.5, 103.5, 101.0, 105.5])
    assert signals(up, k=1.5, n=4, hold=1).iloc[0]["dir"] == 1
    assert signals(dn, k=1.5, n=4, hold=1).iloc[0]["dir"] == -1
    assert signals(dn, k=1.5, n=4, hold=1, direction="fade").iloc[0]["dir"] == 1
    print("PASS continuation takes the bar's own sign; fade mirrors it")


def test_cluster_se_exceeds_iid_se_under_within_session_dependence():
    rng = np.random.default_rng(0)
    # 200 sessions x 5 signals, each session shares a common shock -> dependent
    shock = rng.normal(0, 1, 200)
    x, cl = [], []
    for i in range(200):
        x.extend(shock[i] + rng.normal(0, 0.1, 5))
        cl.extend([i] * 5)
    x = pd.Series(x)
    _, tc = cluster_t(x, pd.Series(cl))
    t_iid = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    assert abs(tc) < abs(t_iid) * 0.7, (tc, t_iid)
    print(f"PASS cluster t {tc:.2f} is properly smaller than iid t {t_iid:.2f}")


def test_cost_ladder_arithmetic():
    assert np.isclose(COST_LADDER["mnq_spread1"], 1.10)
    assert np.isclose(COST_LADDER["mnq_spread2"], 1.35)
    assert np.isclose(COST_LADDER["nq_spread1"], 0.335)
    # the SAME dollar fee is 10x cheaper in points on the full contract
    assert np.isclose((COST_LADDER["mnq_spread1"] - 0.25) /
                      (COST_LADDER["nq_spread1"] - 0.25), 10.0)
    print("PASS cost ladder arithmetic")


if __name__ == "__main__":
    for f in list(globals().values()):
        if callable(f) and getattr(f, "__name__", "").startswith("test_"):
            f()
    print("\nALL ENGINE TESTS PASSED")
