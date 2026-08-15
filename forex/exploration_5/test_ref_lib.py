"""Unit tests for exploration_5 reference-location primitives."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ref_lib as rl  # noqa: E402
import _stage_a_lib as lib  # noqa: E402


def _minute_frame(prices, start="2020-01-01 00:00"):
    """Contiguous 1-minute frame with open==close==price and a tiny hi/lo band."""
    t = pd.date_range(start, periods=len(prices), freq="1min")
    p = np.asarray(prices, float)
    return pd.DataFrame({"time": t, "open": p, "high": p + 1e-6, "low": p - 1e-6, "close": p})


def test_attach_atr_and_prior_levels():
    # Three full UTC days, each 1440 minutes, with a known intraday range per day.
    days = []
    for d, (base, rng) in enumerate([(1.0, 0.01), (1.1, 0.02), (1.2, 0.03)]):
        n = 1440
        p = base + rng * np.sin(np.linspace(0, np.pi, n))  # min=base, max=base+rng
        days.append(p)
    prices = np.concatenate(days)
    mf = _minute_frame(prices)
    daily = rl.attach_atr(rl.daily_frame(mf), lookback_days=2, min_fraction=0.5)
    # Day 2 (index 2) prior high/low come from day 1.
    assert daily["pdh"].iloc[2] == pytest.approx(1.1 + 0.02, abs=1e-6)
    assert daily["pdl"].iloc[2] == pytest.approx(1.1, abs=1e-6)
    # ATR is causal: day-0 has no prior days -> NaN.
    assert np.isnan(daily["atr"].iloc[0])
    assert np.isfinite(daily["atr"].iloc[2])


def test_crossing_first_and_rearm():
    # level=1.0, atr=1.0, k=0.5: price path crosses above, retreats, re-crosses.
    price = np.array([1.0, 1.2, 1.6, 1.3, 1.1, 1.7, 1.0])
    level = np.full(7, 1.0)
    atr = np.full(7, 1.0)
    contiguous = np.array([False, True, True, True, True, True, True])
    ev = rl.crossing_events(price, level, atr, contiguous, k=0.5, side="above")
    # First crossing at idx 2 (z=0.6>=0.5; idx1 z=0.2 not hot). Re-arm at idx5 after leaving.
    assert list(ev["rows"]) == [2, 5]
    assert list(ev["disp_sign"]) == [1.0, 1.0]


def test_crossing_gap_rearms():
    price = np.array([1.6, 1.6, 1.6])
    level = np.full(3, 1.0)
    atr = np.full(3, 1.0)
    contiguous = np.array([False, False, True])  # idx1 not contiguous with idx0
    ev = rl.crossing_events(price, level, atr, contiguous, k=0.5, side="above")
    # idx0 fires (first). idx1 is hot but NOT contiguous -> re-arms -> fires. idx2 contiguous+prev hot -> no.
    assert list(ev["rows"]) == [0, 1]


def test_forward_reversion_sign():
    # price rises to 1.5 then falls back: an 'above' crossing should book positive reversion.
    price = np.array([1.0, 1.5, 1.4, 1.3, 1.2])
    mf = _minute_frame(price)
    grid = lib.MinuteGrid(pd.DatetimeIndex(mf["time"]), mf["open"], mf["high"], mf["low"])
    pos = lib.minute_positions(pd.DatetimeIndex(mf["time"]))
    # signal at minute idx1 (price 1.5, above), disp_sign=+1, horizon=2:
    out = rl.forward_reversion(grid, entry_pos=pos[1:2], disp_sign=np.array([1.0]), horizon=2)
    # entry open = open at idx2 = 1.4; exit open at idx4 = 1.2; rev = -(+1)*(1.2-1.4)=+0.2 price
    assert out["rev_price"][0] == pytest.approx(0.2, abs=1e-9)
    assert out["rev_pips"][0] == pytest.approx(0.2 / rl.PIP, rel=1e-9)


def test_repair_preserves_multiset_within_era():
    daily = pd.DataFrame({"pdh": [1.0, 2.0, 3.0, 4.0], "pdl": [0.5, 1.5, 2.5, 3.5],
                          "atr": [0.1, 0.2, 0.3, 0.4]},
                         index=pd.date_range("2020-01-01", periods=4))
    era = np.array(["a", "a", "b", "b"])
    rng = np.random.default_rng(0)
    out = rl.repair_daily_levels(daily, ["pdh", "pdl"], era, rng)
    # multiset of pdh preserved within each era; atr untouched
    assert sorted(out["pdh"].iloc[:2]) == [1.0, 2.0]
    assert sorted(out["pdh"].iloc[2:]) == [3.0, 4.0]
    assert list(out["atr"]) == [0.1, 0.2, 0.3, 0.4]
    # pdh/pdl stay paired per donor day
    for i in range(4):
        donor = np.flatnonzero(daily["pdh"].to_numpy() == out["pdh"].iloc[i])[0]
        assert out["pdl"].iloc[i] == daily["pdl"].iloc[donor]


def test_donchian_is_prior_extreme():
    daily = pd.DataFrame({"high": [1.0, 2.0, 1.5, 3.0, 2.5], "low": [0.5, 0.4, 0.6, 0.3, 0.7],
                          "close": [0.9, 1.9, 1.4, 2.9, 2.4]},
                         index=pd.date_range("2020-01-01", periods=5))
    dch, dcl = rl.donchian_levels(daily, lookback_days=3, min_fraction=0.34)
    # day index 3 uses prior days 0,1,2: max high = 2.0, min low = 0.4
    assert dch.iloc[3] == pytest.approx(2.0)
    assert dcl.iloc[3] == pytest.approx(0.4)
    # current day never included (shift(1)): day 3's own high 3.0 not in its level
    assert dch.iloc[3] < 3.0


def test_swing_level_is_causal():
    # A clean pivot high at day 3 (high=5), half_width=2 -> confirmed at day 5.
    highs = [1.0, 2.0, 3.0, 5.0, 3.0, 2.0, 1.0, 4.0]
    lows = [0.5] * 8
    daily = pd.DataFrame({"high": highs, "low": lows, "close": highs},
                         index=pd.date_range("2020-01-01", periods=8))
    sh, sl = rl.swing_levels(daily, half_width=2)
    # Before confirmation day 5 the pivot must NOT be visible.
    assert np.isnan(sh.iloc[3]) and np.isnan(sh.iloc[4])
    # From day 5 onward the swing-high level = 5.0 (until a newer pivot confirms).
    assert sh.iloc[5] == pytest.approx(5.0)
    assert sh.iloc[6] == pytest.approx(5.0)


def test_noon_et_level_valid_from_noon():
    # 2020-06-01 is EDT (UTC-4); local noon = 16:00 UTC.
    t = pd.date_range("2020-06-01 15:30", periods=90, freq="1min", tz="UTC").tz_convert(None)
    price = np.arange(90, dtype=float)
    mf = pd.DataFrame({"time": t, "open": price, "high": price, "low": price, "close": price})
    lvl = rl.noon_et_level(mf)
    # before 16:00 UTC (first 30 minutes) -> NaN; at/after -> the 16:00 open (price index 30 = 30.0)
    assert np.all(np.isnan(lvl[:30]))
    assert lvl[30] == pytest.approx(30.0)
    assert lvl[60] == pytest.approx(30.0)
