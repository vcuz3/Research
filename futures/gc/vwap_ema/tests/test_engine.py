"""
Fill-correctness fixtures for core.engine. These prove the Stage-1 NO-GO is the
strategy's, not an engine bug: the EMA50 trail is close-only (wick-immune), the
initial 0.5-ATR stop / 3R target are ordered stop-first on the 1s path, gaps fill
adversely, and the last RTH bar forces flat.

Run:  python -m pytest futures/gc/vwap_ema/tests/test_engine.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import unittest

from futures.gc.vwap_ema.core.engine import run
from futures.gc.vwap_ema.core.data import RTH_START_SEC, BAR_SEC, N_BARS

DATE = np.datetime64("2024-06-03", "ns")


def load_tests(loader, tests, pattern):
    """Expose pytest-style function fixtures to the standard-library runner."""
    suite = unittest.TestSuite()
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            suite.addTest(unittest.FunctionTestCase(fn, description=name))
    return suite


def _bars(rows):
    """rows: list of dict(open,high,low,close,ema50,sig_side,sig_ref,sig_atr).
    Bars are laid on consecutive 15m slots from the session open."""
    recs = []
    for k, r in enumerate(rows):
        r = dict(r)
        r.setdefault("ema20", r["ema50"])
        recs.append(dict(date=DATE, tsec=RTH_START_SEC + k * BAR_SEC, sess_bar=k,
                         **r))
    return pd.DataFrame(recs)


def _s1s(bar_slot, ticks):
    """Build a 1s stream for one 15m bar `bar_slot` from (dt, open, high, low)
    tuples spaced 1s apart."""
    base = RTH_START_SEC + bar_slot * BAR_SEC
    ts = np.array([base + i for i, _ in enumerate(ticks)], np.int64)
    op = np.array([t[0] for t in ticks], np.float64)
    hi = np.array([t[1] for t in ticks], np.float64)
    lo = np.array([t[2] for t in ticks], np.float64)
    # pad to >= MIN_1S check is bypassed here (engine reads the dict directly)
    return {DATE: (ts, op, hi, lo)}


def test_trail_is_close_only_wick_immune():
    # long entry at bar1 open=100; ema50=99. Bar2 low wicks to 95 (below ema50)
    # but CLOSES at 100 (above ema50) -> must NOT exit on the wick. Bar3 closes
    # 98 (below ema50) -> exit at close 98.
    rows = [
        dict(open=100, high=101, low=95.0, close=100.5, ema50=99, sig_side=1,
             sig_ref=95.0, sig_atr=2.0),                 # stop=94, signal bar
        dict(open=100, high=100.2, low=99.9, close=100.1, ema50=99, sig_side=0,
             sig_ref=np.nan, sig_atr=np.nan),            # entry bar (bar1)
        dict(open=100.1, high=100.3, low=95.0, close=100.0, ema50=99, sig_side=0,
             sig_ref=np.nan, sig_atr=np.nan),            # deep wick, closes above
        dict(open=100.0, high=100.1, low=97.5, close=98.0, ema50=99, sig_side=0,
             sig_ref=np.nan, sig_atr=np.nan),            # closes below ema50
    ]
    b = _bars(rows)
    # Stop is 94, safely below the wick, so only the close-conditioned trail exits.
    s1s = {DATE: (np.array([RTH_START_SEC + 2 * BAR_SEC + i for i in range(3)]),
                  np.array([100.1, 100.2, 100.0]),
                  np.array([100.3, 100.3, 100.1]),
                  np.array([99.7, 99.8, 99.9]))}   # low never <= 98.6 -> no stop
    tr = run(b, s1s)
    assert len(tr) == 1
    row = tr.iloc[0]
    assert row["reason"] == "trail50"
    assert abs(row["exit_px"] - 98.0) < 1e-9      # exits at bar3 close, not the wick


def test_stop_before_target_on_1s_path():
    # long entry 100, atr=2 -> stop = sig_ref(99)-1 = 98 ; risk=2 ; target=100+6=106.
    # entry bar's 1s path dips to 97 (hits stop 98) BEFORE spiking to 107 -> STOP.
    rows = [
        dict(open=100, high=100, low=99.0, close=100, ema50=90, sig_side=1,
             sig_ref=99.0, sig_atr=2.0),
        dict(open=100, high=108, low=97.0, close=101, ema50=90, sig_side=0,
             sig_ref=np.nan, sig_atr=np.nan),
    ]
    b = _bars(rows)
    s1s = _s1s(1, [(100, 100, 100), (98.5, 98.5, 97.0), (107, 107, 106)])
    tr = run(b, s1s)
    assert tr.iloc[0]["reason"] == "stop"
    assert abs(tr.iloc[0]["exit_px"] - 98.0) < 1e-9


def test_target_before_stop_on_1s_path():
    rows = [
        dict(open=100, high=100, low=99.0, close=100, ema50=90, sig_side=1,
             sig_ref=99.0, sig_atr=2.0),
        dict(open=100, high=108, low=97.0, close=101, ema50=90, sig_side=0,
             sig_ref=np.nan, sig_atr=np.nan),
    ]
    b = _bars(rows)
    # target 106 touched (2nd tick) before stop 98 (3rd tick) -> TARGET
    s1s = _s1s(1, [(100, 100, 100), (106, 107, 105.9), (97.5, 98.5, 97.0)])
    tr = run(b, s1s)
    assert tr.iloc[0]["reason"] == "target"
    assert abs(tr.iloc[0]["exit_px"] - 106.0) < 1e-9


def test_gap_through_stop_fills_at_open():
    # 1s bar OPENS below the stop (gap) -> fill at the open (worse), not the stop.
    rows = [
        dict(open=100, high=100, low=99.0, close=100, ema50=90, sig_side=1,
             sig_ref=99.0, sig_atr=2.0),                 # stop = 98
        dict(open=100, high=100, low=95.0, close=99, ema50=90, sig_side=0,
             sig_ref=np.nan, sig_atr=np.nan),
    ]
    b = _bars(rows)
    s1s = _s1s(1, [(100, 100, 100), (96.5, 96.5, 95.0)])   # opens 96.5 < stop 98
    tr = run(b, s1s)
    assert tr.iloc[0]["reason"] == "stop"
    assert abs(tr.iloc[0]["exit_px"] - 96.5) < 1e-9        # filled at gap open


def test_risk_and_target_geometry():
    rows = [
        dict(open=100, high=100, low=99.0, close=100, ema50=90, sig_side=1,
             sig_ref=99.0, sig_atr=2.0),
        dict(open=100, high=100.1, low=99.9, close=100.0, ema50=101, sig_side=0,
             sig_ref=np.nan, sig_atr=np.nan),
    ]
    b = _bars(rows)
    s1s = _s1s(1, [(100, 100.1, 99.95)])
    tr = run(b, s1s)
    r = tr.iloc[0]
    assert abs(r["stop_px"] - 98.0) < 1e-9        # 99 - 0.5*2
    assert abs(r["risk_pts"] - 2.0) < 1e-9        # 100 - 98
    assert abs(r["target_px"] - 106.0) < 1e-9     # 100 + 3*2


def test_ema20_tightens_after_2_5r():
    rows = [
        dict(open=100, high=100, low=96, close=100, ema50=90, ema20=99,
             sig_side=1, sig_ref=96, sig_atr=2),
        # risk=5, +2.5R=112.5 touched, target=115 not touched; close below EMA20
        # but above EMA50, so the final-leg rule must exit via EMA20.
        dict(open=100, high=113, low=98.4, close=98.5, ema50=90, ema20=99,
             sig_side=0, sig_ref=np.nan, sig_atr=np.nan),
    ]
    tr = run(_bars(rows), {})
    assert tr.iloc[0]["reason"] == "trail20"
    assert bool(tr.iloc[0]["ema20_tightened"])


def test_daily_limit_blocks_fourth_loss():
    rows = []
    for k in range(4):
        rows.append(dict(open=100, high=100, low=99, close=100, ema50=90,
                         sig_side=1, sig_ref=99, sig_atr=2))
        rows.append(dict(open=100, high=100, low=97, close=99, ema50=90,
                         sig_side=0, sig_ref=np.nan, sig_atr=np.nan))
    tr = run(_bars(rows), {}, cost_R=0.24)
    assert len(tr) == 3
    assert (tr.reason == "stop").all()


def test_news_blackout_blocks_entry():
    rows = [
        dict(open=100, high=100, low=99, close=100, ema50=90, sig_side=1,
             sig_ref=99, sig_atr=2, entry_blocked=False),
        dict(open=100, high=101, low=99, close=100, ema50=90, sig_side=0,
             sig_ref=np.nan, sig_atr=np.nan, entry_blocked=True),
    ]
    assert run(_bars(rows), {}).empty


def test_forced_flat_last_bar():
    # a position still open at the last RTH bar (15:45) exits at that close (eod).
    rows = []
    rows.append(dict(open=100, high=100, low=99.0, close=100, ema50=90,
                     sig_side=1, sig_ref=99.0, sig_atr=2.0))          # bar0 signal
    for k in range(1, N_BARS):
        rows.append(dict(open=100, high=100.5, low=99.6, close=100.2, ema50=90,
                         sig_side=0, sig_ref=np.nan, sig_atr=np.nan))
    b = _bars(rows)
    # 1s streams that never hit stop(98)/target(106) on any managed bar
    s1s = {DATE: (np.array([RTH_START_SEC + BAR_SEC + i for i in range(2)]),
                  np.array([100.0, 100.2]), np.array([100.5, 100.5]),
                  np.array([99.7, 99.8]))}
    tr = run(b, s1s)
    assert tr.iloc[0]["reason"] == "eod"
    last_close = rows[-1]["close"]
    assert abs(tr.iloc[0]["exit_px"] - last_close) < 1e-9
