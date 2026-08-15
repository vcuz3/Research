from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_engine.engine import build_event_returns
from strategy.triangle import apply_signal_blackout, build_triangle_features


def _panel(n: int = 80) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=n, freq="5min")
    audjpy = np.full(n, 100.0)
    usdjpy = np.full(n, 100.0)
    audusd = np.ones(n)
    return pd.DataFrame(
        {
            "audusd_open": audusd,
            "audusd_high": audusd,
            "audusd_low": audusd,
            "audusd_close": audusd,
            "audjpy_open": audjpy,
            "audjpy_high": audjpy,
            "audjpy_low": audjpy,
            "audjpy_close": audjpy,
            "usdjpy_open": usdjpy,
            "usdjpy_high": usdjpy,
            "usdjpy_low": usdjpy,
            "usdjpy_close": usdjpy,
        },
        index=index,
    )


def test_synthetic_identity_and_zero_basis() -> None:
    panel = _panel()
    features = build_triangle_features(panel, 20, 2.0)
    assert np.allclose(features["actual_audusd"], features["synthetic_audusd"])
    assert np.allclose(features["log_basis"], 0.0)


def test_normalizer_is_strictly_lagged() -> None:
    panel = _panel()
    panel.loc[panel.index[-1], "audusd_close"] = 1.1
    features = build_triangle_features(panel, 20, 2.0)
    assert features["normalizer_mean"].iat[-1] == 0.0
    assert features["log_basis"].iat[-1] > 0


def test_rich_actual_produces_short_signal() -> None:
    panel = _panel()
    # Give the historical basis nonzero variance, then create a fresh positive shock.
    panel["audusd_close"] = 1 + np.sin(np.arange(len(panel))) * 0.0001
    panel.loc[panel.index[-1], "audusd_close"] = 1.01
    features = build_triangle_features(panel, 20, 2.0, signal_mode="cross")
    assert features["direction"].iat[-1] == -1


def test_new_york_blackout_tracks_dst_and_includes_endpoints() -> None:
    index = pd.DatetimeIndex(
        [
            "2020-01-02 21:45",  # 16:45 EST
            "2020-01-02 22:00",  # 17:00 EST
            "2020-01-02 23:00",  # 18:00 EST
            "2020-07-02 20:30",  # 16:30 EDT
            "2020-07-02 21:00",  # 17:00 EDT
            "2020-07-02 22:15",  # 18:15 EDT
        ]
    )
    features = pd.DataFrame({"direction": [1, -1, 1, -1, 1, -1]}, index=index)
    filtered, mask = apply_signal_blackout(features, "America/New_York", "16:45", "18:00")
    assert mask.tolist() == [True, True, True, False, True, False]
    assert filtered["direction"].tolist() == [0, 0, 0, -1, 0, -1]


def test_next_bar_entry_and_cost_accounting() -> None:
    panel = _panel()
    features = build_triangle_features(panel, 20, 2.0)
    features["direction"] = 0
    features["zscore"] = 0.0
    decision = 30
    features.iloc[decision, features.columns.get_loc("direction")] = 1
    features.iloc[decision, features.columns.get_loc("zscore")] = -3.0
    panel.iloc[decision + 1, panel.columns.get_loc("audusd_open")] = 1.0
    panel.iloc[decision + 1, panel.columns.get_loc("audusd_close")] = np.exp(0.001)
    events = build_event_returns(panel, features, 1, 5, round_trip_cost_bps_per_leg=1.0)
    assert len(events) == 1
    assert events.iloc[0]["entry_ts"] == panel.index[decision]
    assert np.isclose(events.iloc[0]["audusd_gross"], 0.001)
    assert np.isclose(events.iloc[0]["audusd_net"], 0.0009)
    assert np.isclose(events.iloc[0]["residual_net"], 0.0007)


def test_event_cannot_cross_a_gap() -> None:
    panel = _panel().drop(_panel().index[31])
    features = build_triangle_features(panel, 20, 2.0)
    features["direction"] = 0
    features["zscore"] = 0.0
    features.iloc[30, features.columns.get_loc("direction")] = 1
    assert build_event_returns(panel, features, 1, 5).empty
