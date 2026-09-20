import pandas as pd

from futures.nq.percentile_rank_momentum.backtest_engine.adapter import run_desired_positions
from futures.nq.percentile_rank_momentum.strategy.signal import hysteresis_state


def fixture_bars():
    date = pd.Timestamp("2024-01-02")
    return pd.DataFrame({
        "date": [date] * 5,
        "tod": [600, 605, 610, 615, 620],
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [101.0, 102.0, 103.0, 104.0, 105.0],
        "low": [99.0, 100.0, 101.0, 102.0, 103.0],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1] * 5,
    })


def test_adapter_fills_after_signal_at_next_bar_open():
    bars = fixture_bars()
    desired = pd.DataFrame({
        "date": bars["date"], "tod": bars["tod"], "desired": [1, 1, 0, 0, 0]
    })
    trades = run_desired_positions(bars, desired)
    assert len(trades) == 1
    assert trades.iloc[0].entry_tod == 605
    assert trades.iloc[0].entry_px == 101.0
    assert trades.iloc[0].exit_tod == 615
    assert trades.iloc[0].exit_px == 103.0
    assert trades.iloc[0].points == 2.0


def test_hysteresis_is_session_reset_and_exits_only_below_lower_band():
    date = pd.Timestamp("2024-01-02")
    scores = pd.DataFrame({
        "date": [date] * 4,
        "tod": [600, 605, 610, 615],
        "score_long": [0.9, 0.7, 0.6, 0.4],
        "score_short": [0.0] * 4,
    })
    got = hysteresis_state(scores, 0.85, 0.55)
    assert got["desired"].tolist() == [1, 1, 1, 0]
