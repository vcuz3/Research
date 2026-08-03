import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from backtest_engine.engine import run_variant, simulate_trade
from core.data import _wilder_atr, _wilder_rsi


def minutes(rows):
    return pd.DataFrame(rows, columns=["slot","open","high","low","close"])


def test_same_minute_stop_target_is_adverse_for_long():
    frame = minutes([(500,100.0,103.0,97.0,101.0),(1439,101,101,101,101)])
    result = simulate_trade(frame, 500, 1, atr=1.0, atr_mult=2.0, target=102.0, pip_size=1.0)
    assert result["exit_reason"] == "stop_ambiguous"
    assert result["gross_pips"] == -2.0


def test_first_entry_bar_is_processed():
    frame = minutes([(500,100.0,100.5,97.5,98.0),(1439,98,98,98,98)])
    result = simulate_trade(frame, 500, 1, atr=1.0, atr_mult=2.0, target=105.0, pip_size=1.0)
    assert result["exit_reason"] == "stop"
    assert result["exit_slot"] == 500


def test_target_already_marketable_is_skipped():
    frame = minutes([(500,100.0,101.0,99.0,100.0),(1439,100,100,100,100)])
    assert simulate_trade(frame, 500, -1, 1.0, 2.0, target=101.0, pip_size=1.0) is None


def test_wilder_indicators_on_monotone_path():
    close = np.arange(1.0, 21.0)
    rsi = _wilder_rsi(close, 14)
    atr = _wilder_atr(close + 0.5, close - 0.5, close, 14)
    assert rsi[14] == 100.0
    assert np.isfinite(atr[13:]).all()
    assert np.isnan(rsi[:14]).all()


def test_bounded_rsi_and_one_trade_daily_cap_are_stateful():
    date = pd.Timestamp("2022-01-03")
    raw = pd.DataFrame({
        "trading_date":[date]*5, "slot":[15,425,435,440,1439],
        "open":[100,102,102,102,100], "high":[101,102,102,102,100],
        "low":[99,100,100,100,100], "close":[100,100,100,100,100],
    })
    bars = pd.DataFrame({
        "trading_date":[date,date,date], "slot_start":[420,430,440],
        "slot_end":[424,434,444], "high":[102,102,102], "low":[101,101,101],
        "rsi":[72.0,74.0,76.0], "atr":[1.0,1.0,1.0],
    })
    cfg = {"rsi_high":70.0,"rsi_high_cap":75.0,"rsi_low":30.0,"rsi_low_floor":25.0,
           "atr_multiplier":2.0,"signal_start_slot":420,"signal_end_slot_start":775,
           "max_trades_per_day":1}
    trades, audit = run_variant(raw, bars, {date}, "EURUSD", 1.0, "midpoint", cfg)
    assert len(trades) == 1
    assert trades.iloc[0].signal_rsi == 72.0
    assert audit.iloc[0].capped_signals == 1  # RSI 74 is eligible; RSI 76 is outside the band.
