import numpy as np
import pandas as pd

from strategy.signals import build_decision_bars, build_signals, wilder_atr


def test_wilder_atr_uses_sma_seed_then_recursive_update():
    idx = pd.date_range("2024-01-01", periods=4, freq="30min")
    bars = pd.DataFrame({
        "open": [9.5, 10.5, 12.5, 15.5],
        "high": [10.0, 12.0, 15.0, 19.0],
        "low": [9.0, 10.0, 12.0, 15.0],
        "close": [9.5, 11.0, 14.0, 18.0],
    }, index=idx)
    # TR = 1, 2.5, 4, 5; seed = 2.5 then Wilder = (2*2.5+5)/3.
    atr = wilder_atr(bars, 3)
    assert np.isnan(atr.iloc[0]) and np.isnan(atr.iloc[1])
    assert atr.iloc[2] == 2.5
    assert np.isclose(atr.iloc[3], 10 / 3)


def test_features_exclude_current_bar_and_breakout_is_contrarian_sell():
    idx = pd.date_range("2024-01-01", periods=20, freq="30min")
    bars = pd.DataFrame({
        "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0,
        "minute_count": 30, "complete": True,
    }, index=idx)
    bars.loc[idx[-1], ["open", "high", "low", "close"]] = [100.0, 100.15, 100.0, 100.15]
    out = build_signals(bars, "30min", atr_period=14, atr_percentile=0.5,
                        percentile_lookback=2, breakout_lookback=10)
    assert np.isclose(out.loc[idx[-1], "prior_high"], 100.1)
    assert np.isclose(out.loc[idx[-1], "atr_threshold"], 0.2)
    assert out.loc[idx[-1], "atr"] < out.loc[idx[-1], "atr_threshold"]
    assert out.loc[idx[-1], "signal"] == -1
    assert out.loc[idx[-1], "decision_time"] == idx[-1] + pd.Timedelta(minutes=30)


def test_incomplete_decision_candle_is_reported_and_dropped():
    idx = pd.date_range("2024-01-01", periods=60, freq="min").delete(10)
    minute = pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0}, index=idx)
    bars, diagnostics = build_decision_bars(minute, "30min", require_complete=True)
    assert len(diagnostics) == 2
    assert diagnostics["complete"].tolist() == [False, True]
    assert len(bars) == 1
