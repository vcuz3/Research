"""Executable timing and causality checks for the area mean-reversion engine."""

import numpy as np
import pandas as pd

from _area_mean_reversion_engine import (
    AreaConfig,
    add_forward_horizons,
    build_area_bands,
    checkpoint_while_flat,
    first_cross_per_session,
)


def synthetic_frame(periods=40, start="2023-01-03 00:00", session_id=1):
    times = pd.date_range(start, periods=periods, freq="5min", tz="UTC")
    close = np.full(periods, 100.0)
    frame = pd.DataFrame({
        "bar_open": times,
        "open": close.copy(), "high": close + 1, "low": close - 1, "close": close,
        "complete_5m": True,
        "session_date": pd.Timestamp("2023-01-03"),
        "session_id": session_id,
        "session_slot": np.arange(periods, dtype=np.int16),
        "upper_band": 102.0, "lower_band": 98.0, "band_ready": True,
        "breach_side": np.int8(0),
    })
    return frame


def test_first_cross_uses_next_open_and_only_one_trade_per_session():
    frame = synthetic_frame(periods=20)
    frame.loc[1, ["close", "breach_side"]] = [103.0, 1]
    frame.loc[3, ["close", "breach_side"]] = [103.0, 1]
    frame.loc[2, "open"] = 102.5
    frame.loc[14, "open"] = 101.5
    trades = first_cross_per_session(frame, AreaConfig(holding_minutes=60))
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade.entry_time == frame.bar_open.iloc[2]
    assert trade.exit_time == frame.bar_open.iloc[14]
    assert trade.entry_price == 102.5 and trade.exit_price == 101.5
    assert trade.direction == "short" and trade.gross_pips > 0


def test_checkpoint_skips_while_open_and_can_reenter_at_exit_time():
    # Bar opens at :25/:55 have completed-bar decisions at :30/:00.
    frame = synthetic_frame(periods=32, start="2023-01-03 00:20")
    for i in (1, 7, 13):
        frame.loc[i, ["close", "breach_side"]] = [103.0, 1]
    trades = checkpoint_while_flat(frame, AreaConfig(holding_minutes=60, checkpoint_minutes=30))
    assert len(trades) == 2
    assert trades.entry_time.tolist() == [frame.bar_open.iloc[2], frame.bar_open.iloc[14]]
    assert trades.exit_time.iloc[0] == trades.entry_time.iloc[1]


def test_gap_blocks_unattainable_next_open():
    frame = synthetic_frame(periods=20)
    frame.loc[1, ["close", "breach_side"]] = [103.0, 1]
    frame = frame.drop(index=2).reset_index(drop=True)
    trades = first_cross_per_session(frame, AreaConfig(holding_minutes=60))
    assert trades.empty


def test_band_is_causal_and_keeps_all_candles():
    sessions = 8
    times = pd.date_range("2023-01-01", periods=sessions, freq="1D", tz="UTC")
    bars = pd.DataFrame({
        "bar_open": times,
        "open": 100.0, "high": 101.0, "low": 99.0,
        "close": [100, 101, 99, 102, 98, 101, 99, 150],
        "complete_5m": True,
        "session_date": times.tz_localize(None),
        "session_id": np.arange(sessions),
        "session_slot": 0,
    })
    config = AreaConfig(window="30D", min_observations=3)
    original = build_area_bands(bars, config)
    changed = bars.copy()
    changed.loc[7, "close"] = 50
    revised = build_area_bands(changed, config)
    assert len(original) == len(bars)
    assert np.allclose(
        original.upper_band.iloc[:7], revised.upper_band.iloc[:7], equal_nan=True
    )
    assert np.allclose(
        original.lower_band.iloc[:7], revised.lower_band.iloc[:7], equal_nan=True
    )


def test_direction_adjusted_horizons_and_explicit_cost_components():
    frame = synthetic_frame(periods=30)
    frame.loc[1, ["close", "breach_side"]] = [103.0, 1]
    frame.loc[2, "open"] = 102.0
    frame.loc[5, "open"] = 101.9   # 15m after entry: profitable short
    frame.loc[8, "open"] = 101.8   # 30m
    frame.loc[14, "open"] = 101.7  # 60m
    frame.loc[26, "open"] = 101.6  # 120m
    config = AreaConfig(
        holding_minutes=60, spread_pips=0.5,
        slippage_per_side_pips=0.1, commission_round_trip_pips=0.7,
    )
    trades = first_cross_per_session(frame, config)
    got = add_forward_horizons(frame, trades, config)
    assert config.total_cost_pips == 1.4
    for horizon in (15, 30, 60, 120):
        assert got[f"gross_pips_{horizon}m"].iloc[0] > 0
        assert np.isclose(
            got[f"net_pips_{horizon}m"].iloc[0],
            got[f"gross_pips_{horizon}m"].iloc[0] - 1.4,
        )


if __name__ == "__main__":
    test_first_cross_uses_next_open_and_only_one_trade_per_session()
    test_checkpoint_skips_while_open_and_can_reenter_at_exit_time()
    test_gap_blocks_unattainable_next_open()
    test_band_is_causal_and_keeps_all_candles()
    test_direction_adjusted_horizons_and_explicit_cost_components()
    print("5 area mean-reversion engine invariants passed")
