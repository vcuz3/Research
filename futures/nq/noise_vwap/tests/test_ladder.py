"""Mechanics test for the two-stage RR ladder exit in core.engine2.

Constructs one controlled session so 1R is exactly 1.0 point, then verifies the
paper Table-2 ladder (-1, 2, 0, 5) with a 50% partial: bank half at +2R, run the
rest to the +5R step-1 target, for a blended 3.5R gross trade.
"""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from futures.nq.noise_vwap.core import engine2 as E


def _session():
    # mfo, open, close chosen so: decision at mfo=1 (close 106 > upper 105 > vwap
    # 100) enters long, fills at open[mfo2]=106; band base (max(upper,vwap))=105,
    # so lad_r = |106 - 105| = 1.0. Step-0 TP at +2R=108 hits at mfo2 (bank 50% at
    # open[mfo3]=108); step-1 TP at +5R=111 hits at mfo3 (exit at open[mfo4]=111).
    rows = []
    spec = [
        # mfo, open, close
        (0, 100.0, 100.0),
        (1, 105.0, 106.0),   # decision -> long, fill next open
        (2, 106.0, 108.5),   # step-0 TP (>=108); partial banked at open[mfo3]
        (3, 108.0, 112.0),   # step-1 TP (>=111); exit at open[mfo4]
        (4, 111.0, 111.0),
        (5, 111.0, 111.0),
        (6, 111.0, 111.0),
        (7, 111.0, 111.0),
    ]
    for mfo, o, c in spec:
        rows.append(dict(
            sdate=pd.Timestamp("2026-01-05"), mfo=mfo, tod=570 + mfo, is_rth=True,
            open=o, high=max(o, c) + 0.5, low=min(o, c) - 0.5, close=c,
            vwap=100.0, atr=10.0,
        ))
    bars = pd.DataFrame(rows)
    band = pd.DataFrame([dict(sdate=pd.Timestamp("2026-01-05"), mfo=m,
                              upper=105.0, lower=95.0) for m in range(8)])
    return bars, band


class TestLadder(unittest.TestCase):
    def test_two_stage_blended_payoff(self):
        bars, band = _session()
        trades = E.run(bars, band, decision_mfos=[1], fill_mode="next_open",
                       require_vwap=True, exit_check="every_bar", ladder=True,
                       ladder_levels=(-1.0, 2.0, 0.0, 5.0), ladder_frac=0.5)
        self.assertEqual(len(trades), 1)
        t = trades.iloc[0]
        self.assertEqual(t["side"], 1)
        self.assertEqual(t["reason"], "ladder_tp")
        self.assertAlmostEqual(t["tp_frac"], 0.5)
        # banked 0.5*(108-106) + runner 0.5*(111-106) = 1.0 + 2.5 = 3.5
        self.assertAlmostEqual(t["points"], 3.5, places=9)

    def test_step0_stop_is_minus_1r(self):
        # Same entry, but price collapses through the step-0 stop (105 = -1R) before
        # any TP: a full -1R loss, no partial.
        bars, band = _session()
        bars.loc[bars["mfo"] == 2, "close"] = 104.0   # <= sl_abs 105 -> stop
        bars.loc[bars["mfo"] == 2, "low"] = 103.0
        bars.loc[bars["mfo"] == 3, "open"] = 104.5    # stop fills here
        trades = E.run(bars, band, decision_mfos=[1], fill_mode="next_open",
                       require_vwap=True, exit_check="every_bar", ladder=True,
                       ladder_levels=(-1.0, 2.0, 0.0, 5.0), ladder_frac=0.5)
        self.assertEqual(len(trades), 1)
        t = trades.iloc[0]
        self.assertEqual(t["reason"], "ladder_sl")
        self.assertAlmostEqual(t["tp_frac"], 0.0)
        # full size, fill 104.5 vs entry 106 = -1.5 points
        self.assertAlmostEqual(t["points"], -1.5, places=9)

    def test_ladder_off_is_untouched(self):
        # ladder=False must behave exactly like the baseline band stop (no ladder
        # columns/logic engaged); here that means the long is carried to the daily
        # flat since price never falls back through max(band, vwap).
        bars, band = _session()
        trades = E.run(bars, band, decision_mfos=[1], fill_mode="next_open",
                       require_vwap=True, exit_check="every_bar", ladder=False)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["reason"], "eod")


if __name__ == "__main__":
    unittest.main()
