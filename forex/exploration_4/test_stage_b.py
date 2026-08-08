"""Trade-level parity tests for the Stage-B (EXP-0004) anchor-retrace exit simulator.

Each case is a hand-built synthetic path whose fill, P&L and exit bar are known by
inspection -- not a comparison against a previous run of the simulator. The fill rules
being pinned are exactly the ones RULES.md §A says have manufactured fake edges before:
a touch is not a fill (guard), a gap is not improved (fill at the anchor), and a bar at
index == cap is a market exit, not a live bar.

Run: python -m pytest forex/exploration_4/test_stage_b.py -q -p no:cacheprovider
"""

from __future__ import annotations

import numpy as np
import pytest

import _stage_b_lib as sb


def _paths(open_, high, low):
    return {"open": np.asarray(open_, float),
            "high": np.asarray(high, float),
            "low": np.asarray(low, float)}


# --------------------------------------------------------------------------- #
# guarded anchor fill
# --------------------------------------------------------------------------- #

def test_long_immediate_anchor_fill():
    # entry 100, anchor 101 (favourable, above), guard 0.2 -> trigger at 101.2.
    p = _paths([[100, 100, 100, 100, 100]],
               [[100, 101.5, 100, 100, 100]],   # bar 1 trades through 101.2
               [[100, 99, 99, 99, 99]])
    pnl, kind, bar = sb.simulate_anchor_retrace(
        p, side=[1], entry_px=[100.0], anchor_px=[101.0], guard_px=[0.2], cap=4,
        mode="guarded", pip=1.0)
    assert kind[0] == 1
    assert bar[0] == 1
    assert pnl[0] == pytest.approx(1.0)          # filled AT the anchor: 101-100


def test_guard_blocks_bare_touch_but_touch_mode_fills():
    # bar 1 reaches 101.1: through the anchor (101) but NOT through 101.2.
    p = _paths([[100, 100, 100, 100, 100.5]],
               [[100, 101.1, 100, 100, 100.5]],
               [[100, 99, 99, 99, 99]])
    guarded = sb.simulate_anchor_retrace(
        p, [1], [100.0], [101.0], [0.2], 4, mode="guarded", pip=1.0)
    assert guarded[1][0] == 0                     # time exit
    assert guarded[2][0] == 4
    assert guarded[0][0] == pytest.approx(0.5)    # market exit at open[:,4] = 100.5

    touched = sb.simulate_anchor_retrace(
        p, [1], [100.0], [101.0], [0.2], 4, mode="touch", pip=1.0)
    assert touched[1][0] == 1                      # guard ignored -> fills
    assert touched[0][0] == pytest.approx(1.0)


def test_gap_through_fills_at_anchor_not_the_better_open():
    # bar 1 OPENS at 102, far beyond the anchor. Fill is still credited at 101 (Rule 1).
    p = _paths([[100, 102, 102, 102, 102]],
               [[100, 102, 102, 102, 102]],
               [[100, 101.9, 101.9, 101.9, 101.9]])
    pnl, kind, bar = sb.simulate_anchor_retrace(
        p, [1], [100.0], [101.0], [0.2], 4, mode="guarded", pip=1.0)
    assert kind[0] == 1
    assert bar[0] == 1
    assert pnl[0] == pytest.approx(1.0)           # anchor, not 102-100


def test_short_side_is_symmetric():
    # entry 100, anchor 99 (favourable, below), side -1, guard 0.2 -> through 98.8.
    p = _paths([[100, 100, 100, 100, 100]],
               [[100, 101, 101, 101, 101]],
               [[100, 98.5, 99, 99, 99]])         # bar 1 low trades through 98.8
    pnl, kind, bar = sb.simulate_anchor_retrace(
        p, [-1], [100.0], [99.0], [0.2], 4, mode="guarded", pip=1.0)
    assert kind[0] == 1
    assert bar[0] == 1
    assert pnl[0] == pytest.approx(1.0)           # (-1)*(99-100) = 1


# --------------------------------------------------------------------------- #
# no fill / degenerate cases ride to the cap
# --------------------------------------------------------------------------- #

def test_no_touch_takes_market_exit_at_cap():
    p = _paths([[100, 100.1, 100.2, 100.3, 100.4]],
               [[100, 100.2, 100.3, 100.4, 100.5]],  # never reaches 101.2
               [[100, 99.9, 99.9, 99.9, 99.9]])
    pnl, kind, bar = sb.simulate_anchor_retrace(
        p, [1], [100.0], [101.0], [0.2], 4, mode="guarded", pip=1.0)
    assert kind[0] == 0
    assert bar[0] == 4
    assert pnl[0] == pytest.approx(0.4)           # open[:,4]=100.4


def test_anchor_already_passed_at_entry_rides_to_cap():
    # anchor 99.5 is BELOW entry 100 -> not a valid resting sell limit; hold to cap even
    # though highs blow through everything.
    p = _paths([[100, 100, 100, 100, 98.0]],
               [[100, 200, 200, 200, 200]],
               [[100, 100, 100, 100, 100]])
    for mode in ("guarded", "touch"):
        pnl, kind, bar = sb.simulate_anchor_retrace(
            p, [1], [100.0], [99.5], [0.2], 4, mode=mode, pip=1.0)
        assert kind[0] == 0, mode
        assert pnl[0] == pytest.approx(-2.0), mode  # market exit 98-100


def test_time_mode_ignores_anchor():
    p = _paths([[100, 100, 100, 100, 100.7]],
               [[100, 105, 105, 105, 105]],       # would trigger any anchor
               [[100, 99, 99, 99, 99]])
    pnl, kind, bar = sb.simulate_anchor_retrace(
        p, [1], [100.0], [101.0], [0.2], 4, mode="time", pip=1.0)
    assert kind[0] == 0
    assert bar[0] == 4
    assert pnl[0] == pytest.approx(0.7)


# --------------------------------------------------------------------------- #
# cap boundary and per-trade caps
# --------------------------------------------------------------------------- #

def test_trigger_at_bar_equal_cap_is_not_live():
    # cap 2 -> live bars are 0 and 1 only. A through-the-anchor high at bar 2 must NOT fill;
    # it is the market-exit bar.
    p = _paths([[100, 100, 100.9]],
               [[100, 100, 101.5]],               # only bar 2 (== cap) trades through
               [[100, 99, 99]])
    pnl, kind, bar = sb.simulate_anchor_retrace(
        p, [1], [100.0], [101.0], [0.2], 2, mode="guarded", pip=1.0)
    assert kind[0] == 0
    assert bar[0] == 2
    assert pnl[0] == pytest.approx(0.9)           # open[:,2]=100.9


def test_per_trade_cap_array():
    # two trades: cap 2 and cap 4. Trade 0 fills at bar 1; trade 1 never fills and market-
    # exits at its own cap column (4).
    p = _paths([[100, 100, 100, 100, 100],
                [100, 100, 100, 100, 100.3]],
               [[100, 101.5, 100, 100, 100],
                [100, 100.1, 100.1, 100.1, 100.1]],
               [[100, 99, 99, 99, 99],
                [100, 99.9, 99.9, 99.9, 99.9]])
    pnl, kind, bar = sb.simulate_anchor_retrace(
        p, side=[1, 1], entry_px=[100.0, 100.0], anchor_px=[101.0, 101.0],
        guard_px=[0.2, 0.2], cap=np.array([2, 4]), mode="guarded", pip=1.0)
    assert kind.tolist() == [1, 0]
    assert bar.tolist() == [1, 4]
    assert pnl[0] == pytest.approx(1.0)
    assert pnl[1] == pytest.approx(0.3)


def test_pip_scaling():
    # same geometry as the immediate-fill case but in realistic price/pip units.
    p = _paths([[1.1000, 1.1000, 1.1000]],
               [[1.1000, 1.1030, 1.1000]],
               [[1.1000, 1.0990, 1.0990]])
    pnl, kind, bar = sb.simulate_anchor_retrace(
        p, [1], [1.1000], [1.1020], [0.0005], 2, mode="guarded", pip=1e-4)
    assert kind[0] == 1
    assert pnl[0] == pytest.approx(20.0)          # 20 pips = anchor - entry


# --------------------------------------------------------------------------- #
# friday cap
# --------------------------------------------------------------------------- #

def test_friday_cap_minutes():
    cap = sb.friday_cap_minutes(
        ny_weekday=[4, 4, 2, 4], ny_minute=[900, 1000, 800, 1015],
        base_cap=240, friday_flat_ny_minute=1015)
    assert cap.tolist() == [115, 15, 240, 0]      # last is at the flat -> cap 0 (veto)


def test_cap_exceeding_width_raises():
    p = _paths([[100, 100, 100]], [[100, 100, 100]], [[100, 100, 100]])
    with pytest.raises(ValueError):
        sb.simulate_anchor_retrace(p, [1], [100.0], [101.0], [0.2], 3, mode="time", pip=1.0)
