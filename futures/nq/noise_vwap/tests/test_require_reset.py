"""Mechanics tests for the HYP-0031 `require_reset` re-entry lock in core.engine2.

The rule: after a STOP exit on side S, block fresh same-side entries until price
has been observed back INSIDE the noise area. Opposite-side entries are never
blocked, and the default policy ("later_decision") must be bit-exact unchanged.
"""
from __future__ import annotations

import unittest

import pandas as pd

from futures.nq.noise_vwap.core import engine2 as E

DATE = pd.Timestamp("2026-01-05")
UPPER, LOWER, VWAP = 105.0, 95.0, 100.0
DECISIONS = [1, 3, 5, 7, 9, 11]


def _session(spec):
    """spec: list of (mfo, open, close). Band is a constant 95..105, VWAP 100."""
    bars = pd.DataFrame([
        dict(sdate=DATE, mfo=m, tod=570 + m, is_rth=True, open=o,
             high=max(o, c) + 0.5, low=min(o, c) - 0.5, close=c,
             vwap=VWAP, atr=10.0)
        for m, o, c in spec
    ])
    band = pd.DataFrame([dict(sdate=DATE, mfo=m, upper=UPPER, lower=LOWER)
                         for m, _, _ in spec])
    return bars, band


def _run(bars, band, **kw):
    return E.run(bars, band, decision_mfos=DECISIONS, fill_mode="next_open",
                 require_vwap=True, exit_check="decision", **kw)


# Long at mfo1; stopped at mfo3; the same-side breakout is STILL true at mfo5/mfo7
# (price never came back inside the band); price resets inside at mfo9; a fresh
# breakout at mfo11 is then legal again.
BLOCK_SPEC = [
    (0, 100.0, 100.0),
    (1, 100.0, 106.0),   # decision: long
    (2, 106.0, 104.0),
    (3, 104.0, 104.0),   # decision: close < max(upper,vwap)=105 -> STOP, lock arms
    (4, 104.0, 106.0),
    (5, 106.0, 107.0),   # decision: breakout still true, price OUTSIDE -> blocked
    (6, 107.0, 107.0),
    (7, 107.0, 107.0),   # decision: still outside -> still blocked
    (8, 107.0, 100.0),
    (9, 100.0, 100.0),   # decision: inside the band -> reset observed
    (10, 100.0, 106.0),
    (11, 106.0, 107.0),  # decision: fresh breakout, now permitted
    (12, 107.0, 107.0),
    (13, 107.0, 107.0),  # last bar: forced flat
]


class TestRequireReset(unittest.TestCase):
    def test_blocks_same_side_reentry_until_price_returns_inside(self):
        bars, band = _session(BLOCK_SPEC)
        base = _run(bars, band, reentry="later_decision")
        treat = _run(bars, band, reentry="require_reset")

        # baseline re-enters immediately at mfo5; require_reset waits for mfo11.
        self.assertEqual(list(base["entry_mfo"]), [2, 6, 12])
        self.assertEqual(list(treat["entry_mfo"]), [2, 12])
        # the first trade (before any lock exists) is identical in both books
        self.assertEqual(base.iloc[0]["reason"], "stop")
        self.assertTrue(base.iloc[0].equals(treat.iloc[0]))

    def test_reset_is_recognised_before_the_stop_arms_the_lock(self):
        # The stop bar (mfo3, close 104) is itself INSIDE the band. Spec order is
        # reset-then-stop, so the lock must end up ARMED, not cleared.
        bars, band = _session(BLOCK_SPEC)
        treat = _run(bars, band, reentry="require_reset")
        self.assertEqual(len(treat), 2)   # would be 3 if the reset survived the stop

    def test_opposite_side_entry_is_never_blocked(self):
        spec = list(BLOCK_SPEC)
        spec[5] = (5, 106.0, 90.0)    # decision at mfo5: a SHORT breakout instead
        spec[6] = (6, 90.0, 90.0)
        bars, band = _session(spec)
        treat = _run(bars, band, reentry="require_reset")
        # long stopped at mfo3, yet the short at mfo5 is admitted
        self.assertIn(-1, list(treat["side"]))
        self.assertEqual(int(treat.iloc[1]["side"]), -1)

    def test_default_policy_is_bit_exact(self):
        bars, band = _session(BLOCK_SPEC)
        self.assertTrue(_run(bars, band).equals(_run(bars, band,
                                                     reentry="later_decision")))

    def test_audit_records_the_pool_and_the_blocked_subset(self):
        bars, band = _session(BLOCK_SPEC)
        pool, blocked = [], []
        _run(bars, band, reentry="later_decision", audit_out=pool)
        _run(bars, band, reentry="require_reset", audit_out=blocked)
        # baseline records the same-side re-entry candidates but blocks none
        self.assertEqual([r["mfo"] for r in pool], [5, 11])
        self.assertFalse(any(r["blocked"] for r in pool))
        # treatment blocks mfo5 and mfo7, then admits mfo11
        self.assertEqual([(r["mfo"], r["blocked"]) for r in blocked],
                         [(5, True), (7, True), (11, False)])

    def test_lock_does_not_survive_the_session(self):
        # Same tape on two consecutive dates: the day-2 open breakout is taken even
        # though day 1 ended with the lock armed and price outside the band.
        bars, band = _session(BLOCK_SPEC[:8])   # ends locked, price outside
        d2b, d2n = bars.copy(), band.copy()
        d2b["sdate"] = d2n["sdate"] = DATE + pd.Timedelta(days=1)
        two = _run(pd.concat([bars, d2b], ignore_index=True),
                   pd.concat([band, d2n], ignore_index=True),
                   reentry="require_reset")
        self.assertEqual(two["date"].nunique(), 2)
        self.assertEqual(int(two.groupby("date").size().iloc[1]), 1)

    def test_unknown_policy_raises(self):
        bars, band = _session(BLOCK_SPEC)
        with self.assertRaises(ValueError):
            _run(bars, band, reentry="reset_maybe")


if __name__ == "__main__":
    unittest.main()
