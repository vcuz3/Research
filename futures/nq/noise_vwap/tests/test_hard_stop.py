"""Mechanics tests for the mandatory protective stop (HYP-0032) in core.engine2.

The stop is a RESTING order frozen at entry on the strategy's own band/VWAP touch
level, widened by a volatility buffer:
    risk = max(entry - stop_ref_at_entry, 0) + buf*ATR      (long; mirrored short)
It is live on every bar including the fill bar (rule 3), fills AT its level, and
fills at the bar's OPEN when the bar gaps through it (rule 5).
"""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from futures.nq.noise_vwap.core import engine2 as E

DATE = pd.Timestamp("2026-01-05")
UPPER, LOWER, VWAP, ATR = 105.0, 95.0, 100.0, 10.0


def _bars(spec):
    """spec: (mfo, open, high, low, close)."""
    bars = pd.DataFrame([
        dict(sdate=DATE, mfo=m, tod=570 + m, is_rth=True, open=o, high=h, low=l,
             close=c, vwap=VWAP, atr=ATR) for m, o, h, l, c in spec])
    band = pd.DataFrame([dict(sdate=DATE, mfo=m, upper=UPPER, lower=LOWER)
                         for m, _, _, _, _ in spec])
    return bars, band


def _run(bars, band, **kw):
    kw.setdefault("exit_check", "decision")
    return E.run(bars, band, decision_mfos=[1], fill_mode="next_open",
                 require_vwap=True, **kw)


# Long entry at mfo1 (close 106 > upper 105 > vwap 100), fill = open[mfo2] = 106.
# stop_ref at entry = max(105, 100) = 105 -> raw risk = 106 - 105 = 1.0.
BASE = [
    (0, 100.0, 100.5, 99.5, 100.0),
    (1, 100.0, 106.5, 99.5, 106.0),
    (2, 106.0, 106.5, 105.5, 106.0),
    (3, 106.0, 106.5, 105.5, 106.0),
    (4, 106.0, 106.5, 105.5, 106.0),
]


class TestHardStop(unittest.TestCase):
    def test_off_by_default_is_bit_exact(self):
        bars, band = _bars(BASE)
        self.assertTrue(_run(bars, band).equals(_run(bars, band, hard_stop_buf_atr=None)))

    def test_risk_is_entry_distance_plus_buffer(self):
        # buf=0.5 ATR = 5.0 -> risk = 1.0 + 5.0 = 6.0 -> line at 100.0
        spec = list(BASE)
        spec[3] = (3, 106.0, 106.5, 99.0, 100.5)   # dips to 99 < 100 -> stop fills at 100
        bars, band = _bars(spec)
        t = _run(bars, band, hard_stop_buf_atr=0.5)
        self.assertEqual(t.iloc[0]["reason"], "hard_stop")
        self.assertAlmostEqual(t.iloc[0]["hard_risk"], 6.0, places=9)
        self.assertAlmostEqual(t.iloc[0]["exit_px"], 100.0, places=9)
        self.assertAlmostEqual(t.iloc[0]["points"], -6.0, places=9)

    def test_gap_through_fills_at_the_open_not_the_level(self):
        # Same 100.0 line, but the bar OPENS at 97 -> first tradable price is 97.
        spec = list(BASE)
        spec[3] = (3, 97.0, 97.5, 96.0, 96.5)
        bars, band = _bars(spec)
        t = _run(bars, band, hard_stop_buf_atr=0.5)
        self.assertEqual(t.iloc[0]["reason"], "hard_stop")
        self.assertAlmostEqual(t.iloc[0]["exit_px"], 97.0, places=9)
        self.assertAlmostEqual(t.iloc[0]["points"], -9.0, places=9)   # worse than -6

    def test_live_on_the_fill_bar(self):
        # The stop must be armed on the very bar the entry fills (rule 3).
        spec = list(BASE)
        spec[2] = (2, 106.0, 106.5, 99.0, 100.5)
        bars, band = _bars(spec)
        t = _run(bars, band, hard_stop_buf_atr=0.5)
        self.assertEqual(len(t), 1)
        self.assertEqual(int(t.iloc[0]["exit_mfo"]), 2)
        self.assertEqual(t.iloc[0]["reason"], "hard_stop")

    def test_checked_every_bar_regardless_of_soft_trail_cadence(self):
        # exit_check='decision' means the soft trail only looks at mfo1, but the
        # resting order still fires at mfo3.
        spec = list(BASE)
        spec[3] = (3, 106.0, 106.5, 99.0, 100.5)
        bars, band = _bars(spec)
        t = _run(bars, band, hard_stop_buf_atr=0.5, exit_check="decision")
        self.assertEqual(t.iloc[0]["reason"], "hard_stop")

    def test_wide_buffer_is_inert(self):
        bars, band = _bars(BASE)
        wide = _run(bars, band, hard_stop_buf_atr=50.0)
        self.assertEqual(wide.iloc[0]["reason"], "eod")

    def test_short_side_mirrors(self):
        spec = [
            (0, 100.0, 100.5, 99.5, 100.0),
            (1, 100.0, 100.5, 93.5, 94.0),      # close 94 < lower 95 and < vwap
            (2, 94.0, 94.5, 93.5, 94.0),        # fill 94; ref=min(95,100)=95; raw=1
            (3, 94.0, 101.0, 93.5, 100.5),      # line at 94+6=100 -> touched
            (4, 100.0, 100.5, 99.5, 100.0),
        ]
        bars, band = _bars(spec)
        t = _run(bars, band, hard_stop_buf_atr=0.5)
        self.assertEqual(int(t.iloc[0]["side"]), -1)
        self.assertEqual(t.iloc[0]["reason"], "hard_stop")
        self.assertAlmostEqual(t.iloc[0]["hard_risk"], 6.0, places=9)
        self.assertAlmostEqual(t.iloc[0]["points"], -6.0, places=9)

    def test_risk_floor_when_entry_gaps_past_its_own_reference(self):
        # Fill BELOW the entry reference would give a negative raw distance; the
        # (.)+ floor must leave a positive buffer-only risk, never a stop above entry.
        spec = list(BASE)
        spec[2] = (2, 104.0, 106.5, 103.5, 106.0)   # fill 104 < ref 105
        spec[3] = (3, 106.0, 106.5, 98.9, 99.5)     # dips below the 99.0 line
        bars, band = _bars(spec)
        t = _run(bars, band, hard_stop_buf_atr=0.5)
        # raw distance is negative and floors to 0, leaving buffer-only risk, and the
        # line lands BELOW the fill (99.0 < 104.0) -- never above it.
        self.assertAlmostEqual(t.iloc[0]["hard_risk"], 5.0, places=9)
        self.assertEqual(t.iloc[0]["reason"], "hard_stop")
        self.assertAlmostEqual(t.iloc[0]["exit_px"], 99.0, places=9)

    def test_hard_stop_arms_the_require_reset_lock(self):
        # A hard stop is a stop-driven exit: under require_reset it must block the
        # same side until price returns inside the band, exactly like the soft trail.
        spec = [
            (0, 100.0, 100.5, 99.5, 100.0),
            (1, 100.0, 106.5, 99.5, 106.0),   # decision -> long, fill 106, line 100
            (2, 106.0, 106.5, 99.0, 106.0),   # hard stop fires at 100
            (3, 106.0, 107.0, 105.5, 106.5),  # decision: still outside the band
            (4, 106.0, 107.0, 105.5, 106.5),
        ]
        bars, band = _bars(spec)
        locked = E.run(bars, band, decision_mfos=[1, 3], fill_mode="next_open",
                       require_vwap=True, exit_check="decision",
                       reentry="require_reset", hard_stop_buf_atr=0.5)
        free = E.run(bars, band, decision_mfos=[1, 3], fill_mode="next_open",
                     require_vwap=True, exit_check="decision",
                     reentry="later_decision", hard_stop_buf_atr=0.5)
        self.assertEqual(list(locked["reason"]), ["hard_stop"])
        self.assertEqual(len(free), 2)   # re-buys the same breakout at mfo3

    def test_loss_is_bounded_by_risk_absent_gaps(self):
        rng = np.random.default_rng(0)
        spec = [(0, 100.0, 100.5, 99.5, 100.0), (1, 100.0, 106.5, 99.5, 106.0)]
        px = 106.0
        for m in range(2, 60):
            nxt = px + rng.normal(0, 0.8)
            spec.append((m, px, max(px, nxt) + 0.2, min(px, nxt) - 0.2, nxt))
            px = nxt
        bars, band = _bars(spec)
        t = _run(bars, band, hard_stop_buf_atr=0.5, exit_check="every_bar")
        self.assertGreaterEqual(t.iloc[0]["points"], -6.0 - 1e-9)


if __name__ == "__main__":
    unittest.main()
