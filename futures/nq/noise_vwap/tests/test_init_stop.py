"""Mechanics test for the fixed INITIAL stop (init_stop_atr) in core.engine2.

The initial stop is a hard cap layered on the band/VWAP trail: the effective stop
is the TIGHTER of the two. A tight init line binds (reason 'istop') before the band;
a wide init line is inert and the tape is identical to baseline (parity).
"""
from __future__ import annotations

import unittest

import pandas as pd

from futures.nq.noise_vwap.core import engine2 as E


def _session():
    # decision at mfo=1 (close 106 > upper 105 > vwap 100) -> long, fill open[mfo2]=106.
    # band stop base = max(upper 105, vwap 100) = 105. atr=10.
    spec = [
        (0, 100.0, 100.0),
        (1, 105.0, 106.0),
        (2, 106.0, 105.3),   # close 105.3: below a tight init line, above the band 105
        (3, 105.4, 105.4),
        (4, 105.4, 105.4),
        (5, 105.4, 105.4),
    ]
    rows = [dict(sdate=pd.Timestamp("2026-01-05"), mfo=m, tod=570 + m, is_rth=True,
                 open=o, high=max(o, c) + 0.5, low=min(o, c) - 0.5, close=c,
                 vwap=100.0, atr=10.0) for m, o, c in spec]
    bars = pd.DataFrame(rows)
    band = pd.DataFrame([dict(sdate=pd.Timestamp("2026-01-05"), mfo=m,
                              upper=105.0, lower=95.0) for m in range(6)])
    return bars, band


class TestInitStop(unittest.TestCase):
    def test_tight_init_stop_binds(self):
        # init_line = 106 - 0.05*10 = 105.5 > band stop 105 -> tighter -> binds.
        # close[mfo2]=105.3 < 105.5 triggers it; band stop (105) would NOT have fired.
        bars, band = _session()
        trades = E.run(bars, band, decision_mfos=[1], fill_mode="next_open",
                       require_vwap=True, exit_check="every_bar", init_stop_atr=0.05)
        self.assertEqual(len(trades), 1)
        t = trades.iloc[0]
        self.assertEqual(t["reason"], "istop")
        self.assertAlmostEqual(t["points"], 105.4 - 106.0, places=9)  # -0.6

    def test_wide_init_stop_is_inert(self):
        # init_line = 106 - 2.0*10 = 86 << band 105: never binds. The band stop is
        # never breached (close stays >= 105), so the long rides to the daily flat --
        # identical to init_stop_atr=0 (baseline).
        bars, band = _session()
        wide = E.run(bars, band, decision_mfos=[1], fill_mode="next_open",
                     require_vwap=True, exit_check="every_bar", init_stop_atr=2.0)
        base = E.run(bars, band, decision_mfos=[1], fill_mode="next_open",
                     require_vwap=True, exit_check="every_bar", init_stop_atr=0.0)
        self.assertTrue(wide.equals(base))
        self.assertEqual(wide.iloc[0]["reason"], "eod")


if __name__ == "__main__":
    unittest.main()
