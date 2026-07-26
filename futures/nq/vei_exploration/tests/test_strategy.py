"""Causality + accounting tests for the momentum simulator (HYP-0001 / EXP-0004).

Load-bearing: a bet decided at bar i fills at open[i+1] and exits at open[i+1+H];
perturbing bars STRICTLY AFTER a bet's exit index must not change that bet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import vei as V
from ..core import strategy as ST


def _toy(n_per=70, n_sess=2, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_sess):
        px = 100.0 + np.cumsum(rng.normal(0, 0.3, n_per))
        for i in range(n_per):
            rows.append({"sdate": pd.Timestamp(2020, 1, 1) + pd.Timedelta(days=s),
                         "mfo": i, "open": px[i],
                         "high": px[i] + abs(rng.normal(0, 0.1)),
                         "low": px[i] - abs(rng.normal(0, 0.1)), "close": px[i],
                         "volume": 1.0})
    return pd.DataFrame(rows)


def test_fill_and_horizon_math():
    df = _toy(n_sess=1, seed=1)
    vei = np.zeros(len(df))
    tr = ST.simulate(df, [29], vei, mode="all", thr=0.0, horizon=30,
                     cost_pts=0.1, past_win=30)
    assert len(tr) == 1
    row = tr.iloc[0]
    o = df.sort_values("mfo")["open"].to_numpy()
    c = df.sort_values("mfo")["close"].to_numpy()
    side = np.sign(c[29] - c[max(0, 29 - 30)])
    assert row["side"] == side
    assert np.isclose(row["entry"], o[30])   # next-open fill
    assert np.isclose(row["exit"], o[60])    # +horizon open
    assert np.isclose(row["points"], side * (o[60] - o[30]))
    assert np.isclose(row["net"], row["points"] - 0.1)


def test_causal_future_perturbation():
    df = _toy(n_sess=1, seed=2)
    vei = np.zeros(len(df))
    base = ST.simulate(df, [29, 59], vei, mode="all", thr=0.0, horizon=30,
                       cost_pts=0.0, past_win=30).set_index("mfo")
    p = df.copy()
    p.loc[p["mfo"] > 60, ["open", "high", "low", "close"]] += 10.0  # after mfo=29 bet's exit(60)
    after = ST.simulate(p, [29, 59], vei, mode="all", thr=0.0, horizon=30,
                        cost_pts=0.0, past_win=30).set_index("mfo")
    # the mfo=29 bet (entry 30, exit 60) must be untouched by bars after idx 60
    assert np.isclose(base.loc[29, "points"], after.loc[29, "points"])
    # the mfo=59 bet (exit at idx 69) SHOULD change
    assert not np.isclose(base.loc[59, "points"], after.loc[59, "points"])


def test_no_overlap_is_the_default():
    """A hold longer than the decision spacing must NOT silently run 2 positions.

    HYP-0001 declares non-overlapping single-position bets, but a 60-min horizon on a
    30-min clock would fill a second bet before the first exits — a 2-unit book whose
    daily R sum is not the declared estimand (rule 13). The default must drop those.
    """
    df = _toy(n_per=200, n_sess=1, seed=4)
    vei = np.zeros(len(df))
    dm = [29, 59, 89, 119]                        # 30-min spacing
    kw = dict(mode="all", thr=0.0, cost_pts=0.0, past_win=30)

    over = ST.simulate(df, dm, vei, horizon=60, allow_overlap=True, **kw)
    assert (over["entry_i"].to_numpy()[1:]
            < over["exit_i"].to_numpy()[:-1]).any(), "fixture must actually overlap"

    tight = ST.simulate(df, dm, vei, horizon=60, **kw)     # default: enforced
    e, x = tight["entry_i"].to_numpy(), tight["exit_i"].to_numpy()
    assert (e[1:] >= x[:-1]).all(), "default simulate must not hold 2 positions"
    assert len(tight) < len(over)

    # at a horizon equal to the decision spacing nothing overlaps, so the guard is a
    # no-op and every previously published H<=30 cell is unaffected
    a = ST.simulate(df, dm, vei, horizon=30, **kw)
    b = ST.simulate(df, dm, vei, horizon=30, allow_overlap=True, **kw)
    pd.testing.assert_frame_equal(a, b)


def test_vei_gate_selects():
    df = _toy(n_sess=2, seed=3)
    vei = V.vei_series(df, 10, 50, "wilder", 0).to_numpy()
    hi = ST.simulate(df, [59, 89], vei, mode="high", thr=1.0, horizon=20,
                     cost_pts=0.0, past_win=30)
    lo = ST.simulate(df, [59, 89], vei, mode="low", thr=1.0, horizon=20,
                     cost_pts=0.0, past_win=30)
    alln = ST.simulate(df, [59, 89], vei, mode="all", thr=0.0, horizon=20,
                       cost_pts=0.0, past_win=30)
    # high + low partition all (every decided bet is in exactly one)
    assert len(hi) + len(lo) == len(alln)
