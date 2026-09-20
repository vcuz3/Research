import numpy as np
import pandas as pd

from backtest_engine.engine import add_costs, simulate_asset
from run_backtest import daily_metrics


def minutes(rows):
    idx = pd.date_range("2024-01-01 00:30", periods=len(rows), freq="min")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def signals(items):
    records = []
    index = []
    for signal_time, decision_time, side, atr in items:
        index.append(pd.Timestamp(signal_time))
        records.append({"decision_time": pd.Timestamp(decision_time), "signal": side, "atr": atr})
    return pd.DataFrame(records, index=pd.DatetimeIndex(index))


def test_next_open_entry_and_adverse_dual_touch_on_entry_bar():
    minute = minutes([(100.0, 102.0, 98.0, 101.0), (101.0, 101.0, 101.0, 101.0)])
    sig = signals([("2024-01-01 00:00", "2024-01-01 00:30", 1, 1.0)])
    trades = simulate_asset("X", minute, sig, 1.5, 1.5, 12.0, 1.0)
    trade = trades.iloc[0]
    assert trade.entry_time == pd.Timestamp("2024-01-01 00:30")
    assert trade.exit_reason == "stop_ambiguous"
    assert trade.exit_price == 98.5
    assert trade.gross_r == -1.0


def test_gap_through_stop_fills_at_open():
    minute = minutes([(100.0, 100.5, 99.5, 100.0), (98.0, 99.0, 97.0, 98.5)])
    sig = signals([("2024-01-01 00:00", "2024-01-01 00:30", 1, 1.0)])
    trade = simulate_asset("X", minute, sig, 1.0, 3.0, 12.0, 1.0).iloc[0]
    assert trade.exit_reason == "stop_gap"
    assert trade.exit_time == pd.Timestamp("2024-01-01 00:31")
    assert trade.exit_price == 98.0
    assert trade.gross_r == -2.0


def test_opposite_signal_exits_at_its_decision_open_without_reversal():
    minute = minutes([
        (100.0, 100.2, 99.8, 100.0),
        (100.0, 100.2, 99.8, 100.0),
        (100.4, 100.5, 100.3, 100.4),
        (100.4, 100.5, 100.3, 100.4),
    ])
    sig = signals([
        ("2024-01-01 00:00", "2024-01-01 00:30", 1, 1.0),
        ("2024-01-01 00:01", "2024-01-01 00:32", -1, 1.0),
    ])
    trades = simulate_asset("X", minute, sig, 3.0, 3.0, 12.0, 1.0)
    assert len(trades) == 1
    assert trades.iloc[0].exit_reason == "opposite_signal"
    assert trades.iloc[0].exit_time == pd.Timestamp("2024-01-01 00:32")
    assert np.isclose(trades.iloc[0].gross_r, 0.4 / 3.0)


def test_elapsed_time_exit_and_cost_once():
    minute = minutes([(100.0, 100.1, 99.9, 100.0)] * 3 + [(100.2, 100.2, 100.2, 100.2)])
    sig = signals([("2024-01-01 00:00", "2024-01-01 00:30", 1, 1.0)])
    trades = simulate_asset("X", minute, sig, 3.0, 3.0, 2 / 60, 1.0)
    assert trades.iloc[0].exit_reason == "time"
    assert trades.iloc[0].exit_time == pd.Timestamp("2024-01-01 00:32")
    costed = add_costs(trades, 0.1, pip_size=1.0)
    assert np.isclose(costed.iloc[0].net_pips, trades.iloc[0].gross_pips - 0.1)
    assert np.isclose(costed.iloc[0].net_r, trades.iloc[0].gross_r - 0.1 / 3.0)


def test_daily_metrics_keeps_sunday_fx_pnl():
    trades = pd.DataFrame({
        "exit_time": pd.to_datetime(["2024-01-07 22:00", "2024-01-08 10:00"]),
        "gross_r": [1.0, 0.0],
    })
    result = daily_metrics(trades, "gross_r")
    expected = np.sqrt(365.0) * 0.5 / np.std([1.0, 0.0], ddof=1)
    assert np.isclose(result["daily_sharpe"], expected)
