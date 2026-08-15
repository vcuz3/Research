from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_engine.decay import paired_minute_decay, summarize_decay


def _minutes() -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=121, freq="1min")
    base = np.ones(len(index))
    frame = pd.DataFrame(index=index)
    for pair in ("audusd", "audjpy", "usdjpy"):
        frame[f"{pair}_open"] = base
        frame[f"{pair}_close"] = base
    frame.loc[index[30:60], "audusd_close"] = 1.001
    frame.loc[index[60:90], "audusd_close"] = 1.002
    return frame


def _signals() -> pd.DataFrame:
    return pd.DataFrame({"decision_ts": [pd.Timestamp("2020-01-01 00:30")], "direction": [1], "zscore": [-3.5]})


def test_delay_clock_and_constant_holding_period() -> None:
    events, coverage = paired_minute_decay(_minutes(), _signals(), [0, 30], 30, 0.5)
    zero = events.loc[events.delay_minutes.eq(0)].iloc[0]
    thirty = events.loc[events.delay_minutes.eq(30)].iloc[0]
    assert zero.entry_ts == pd.Timestamp("2020-01-01 00:30")
    assert zero.exit_ts == pd.Timestamp("2020-01-01 01:00")
    assert thirty.entry_ts == pd.Timestamp("2020-01-01 01:00")
    assert thirty.exit_ts == pd.Timestamp("2020-01-01 01:30")
    assert (events.exit_ts - events.entry_ts).eq(pd.Timedelta(minutes=30)).all()
    assert coverage.paired_signals.eq(1).all()


def test_cost_units_and_residual_identity() -> None:
    events, _ = paired_minute_decay(_minutes(), _signals(), [0], 30, 0.5)
    row = events.iloc[0]
    assert np.isclose(row.audusd_net, row.audusd_gross - 0.5e-4)
    assert np.isclose(row.residual_gross, row.audusd_gross)
    assert np.isclose(row.residual_net, row.residual_gross - 1.5e-4)


def test_gap_removes_signal_from_every_arm() -> None:
    minute = _minutes().drop(pd.Timestamp("2020-01-01 00:45"))
    events, coverage = paired_minute_decay(minute, _signals(), [0, 30], 30, 0.5)
    assert events.empty
    assert coverage.paired_signals.eq(0).all()


def test_summary_uses_all_observed_days_and_paired_difference() -> None:
    events, _ = paired_minute_decay(_minutes(), _signals(), [0, 30], 30, 0.5)
    observed = pd.date_range("2020-01-01", periods=3, freq="D")
    summary, decay = summarize_decay(events, observed)
    assert set(summary.accounting) == {"gross", "net"}
    assert set(decay.delay_minutes) == {0, 30}
    assert decay.loc[decay.delay_minutes.eq(0), "mean_change_vs_0_bps"].eq(0).all()
