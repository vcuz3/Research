"""Invariant tests for the exploration_4 orchestration and reused fill core."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _run_baseline import cluster_stats, stateful_select
from _bracket_engine import simulate_bracket
from _rsi_stop_engine import simulate


def paths(open_, high, low):
    return {"open": np.asarray([open_], float), "high": np.asarray([high], float),
            "low": np.asarray([low], float), "close": np.asarray([open_], float)}


def test_next_bar_entry_and_gap_through_stop():
    p = paths([1.0000, 0.9980, 0.9970], [1.0005, 0.9990, 0.9980],
              [0.9995, 0.9975, 0.9965])
    pnl, stopped, bar = simulate(p, np.array([1.0]), np.array([10.0]), 2,
                                  slippage_pips=0.0, pip=0.0001)
    assert stopped[0] and bar[0] == 1
    assert np.isclose(pnl[0], -20.0)  # gap fills at bar open, not stale stop level


def test_bracket_same_bar_ambiguity_is_adverse():
    p = paths([1.0000, 1.0000], [1.0020, 1.0000], [0.9980, 1.0000])
    pnl, kind = simulate_bracket(p, np.array([1.0]), 10.0, 10.0, 1,
                                  slippage_pips=0.0, pip=0.0001)
    assert kind[0] == -1
    assert np.isclose(pnl[0], -10.0)


def test_stateful_nonoverlap_recomputes_book():
    d = pd.DataFrame({"signal_idx": [10, 12, 21, 22], "actual_exit_idx": [20, 13, 24, 23]})
    keep = stateful_select(d, pd.Series([True, True, True, True]))
    assert keep.tolist() == [True, False, True, False]
    veto = stateful_select(d, pd.Series([False, True, True, True]))
    assert veto.tolist() == [False, True, True, False]


def test_cluster_stats_uses_signal_weighted_mean():
    values = np.array([1.0, -1.0, -1.0])
    groups = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-02"])
    stats = cluster_stats(values, groups)
    assert np.isclose(stats["mean"], -1 / 3)
    assert stats["clusters"] == 2
