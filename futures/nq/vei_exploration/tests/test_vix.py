"""Causality + construction tests for `core/vix.py` (rules 7, 9a).

Load-bearing claims, each pinned by one test:
  * a VIX bar is joined only if its 15-minute window CLOSED at or before the decision's
    information cutoff -- a bar still in progress can never be used;
  * `lag_bars` moves the join strictly further into the past, never forwards;
  * a decision with no VIX bar inside the tolerance is left NaN rather than
    forward-filled from an arbitrary distance, and its staleness is reported;
  * the VIX -> basis-point rescaling is the documented closed form, so `vrp_log == 0`
    really does mean "implied equals what the last 30 minutes realised";
  * the same-slot z-score is causal (a slot's own value never enters its own norm).

The tests that touch the real 10-tile export are skipped when it is absent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import vix as VX


def _toy_vix(n=8, start="2020-01-02 14:30", step=15, base=20.0):
    """`n` consecutive 15-minute VIX bars stamped at their OPEN."""
    ts = pd.date_range(pd.Timestamp(start, tz="UTC"), periods=n, freq=f"{step}min")
    close = base + np.arange(n, dtype=float)
    return pd.DataFrame({"ts_utc": ts, "open": close - .1, "high": close + .2,
                         "low": close - .2, "close": close})


def _toy_decisions(ts_list, past_rv=20.0):
    ts = pd.DatetimeIndex(ts_list)
    return pd.DataFrame({
        "ts_utc": ts,
        "sdate": ts.tz_convert("America/New_York").tz_localize(None).normalize(),
        "mfo": np.arange(len(ts)) * 30 + 29,
        "past_rv30_bp": past_rv, "past_ret30_bp": 0.0})


def _patched_attach(monkey_frame, decisions, **kw):
    """Run `attach_vix` against an in-memory VIX panel instead of the CSV tiles."""
    real = VX.load_vix_15m
    v = monkey_frame.sort_values("ts_utc").reset_index(drop=True)
    et = v.ts_utc.dt.tz_convert("America/New_York")
    v["date"] = et.dt.tz_localize(None).dt.normalize()
    v["tod"] = et.dt.hour * 60 + et.dt.minute
    v["avail_utc"] = v.ts_utc + pd.Timedelta(minutes=VX.BAR_MINUTES)
    VX.load_vix_15m = lambda: (v, {"files": 0, "raw_rows": len(v), "rows": len(v),
                                   "duplicate_ts": 0, "first": v.ts_utc.min(),
                                   "last": v.ts_utc.max(),
                                   "sessions": int(v.date.nunique()),
                                   "rth_rows": len(v), "median_bars_per_session": 0.0,
                                   "short_sessions": 0, "frozen_bars": 0,
                                   "repeat_close_bars": 0, "nonpositive": 0,
                                   "min_close": float(v.close.min()),
                                   "max_close": float(v.close.max())})
    try:
        return VX.attach_vix(decisions, **kw)
    finally:
        VX.load_vix_15m = real


def test_a_bar_still_in_progress_is_never_joined():
    """The decision at 14:59 closes at 15:00; the bar stamped 14:45 closes exactly then.

    The bar stamped 15:00 is still running and must not be used, even though its OPEN
    timestamp precedes the next decision.
    """
    v = _toy_vix(n=6, start="2020-01-02 14:30")      # bars open 14:30,14:45,15:00,...
    d = _toy_decisions([pd.Timestamp("2020-01-02 14:59", tz="UTC")])
    j, _ = _patched_attach(v, d)
    # the 14:45 bar closes at 15:00 == the cutoff, so it is the freshest admissible one
    assert j.avail_utc.iloc[0] == pd.Timestamp("2020-01-02 15:00", tz="UTC")
    assert j.vix.iloc[0] == v.close.iloc[1]
    assert j.vix_stale_min.iloc[0] == 0.0
    # and never a bar that had not closed
    assert bool((j.avail_utc <= j.cutoff_utc).all())


def test_a_decision_one_minute_earlier_falls_back_to_the_previous_bar():
    """At 14:58 the cutoff is 14:59, so the 14:45 bar has NOT closed; use 14:30's."""
    v = _toy_vix(n=6, start="2020-01-02 14:30")
    d = _toy_decisions([pd.Timestamp("2020-01-02 14:58", tz="UTC")])
    j, _ = _patched_attach(v, d)
    assert j.avail_utc.iloc[0] == pd.Timestamp("2020-01-02 14:45", tz="UTC")
    assert j.vix.iloc[0] == v.close.iloc[0]
    assert j.vix_stale_min.iloc[0] == 14.0


def test_lag_bars_moves_the_join_strictly_backwards():
    v = _toy_vix(n=8, start="2020-01-02 14:30")
    d = _toy_decisions([pd.Timestamp("2020-01-02 15:59", tz="UTC")])
    fresh, _ = _patched_attach(v, d)
    lagged, _ = _patched_attach(v, d, lag_bars=1)
    assert lagged.avail_utc.iloc[0] == fresh.avail_utc.iloc[0] - pd.Timedelta(minutes=15)
    assert lagged.vix.iloc[0] < fresh.vix.iloc[0]          # the toy series is increasing
    assert bool((lagged.avail_utc <= lagged.cutoff_utc).all())


def test_a_gap_beyond_tolerance_is_left_null_not_forward_filled():
    v = _toy_vix(n=2, start="2020-01-02 14:30")
    d = _toy_decisions([pd.Timestamp("2020-01-02 14:59", tz="UTC"),
                        pd.Timestamp("2020-01-02 20:59", tz="UTC")])
    j, q = _patched_attach(v, d, tolerance_min=45)
    assert np.isfinite(j.vix.iloc[0])
    assert not np.isfinite(j.vix.iloc[1]), "a six-hour-old quote was forward-filled"
    assert q["unjoined"] == 1 and q["joined"] == 1


def test_vix_to_bp_is_the_documented_closed_form():
    got = VX.vix_to_bp(np.array([16.0]), horizon_min=30)[0]
    want = 1e4 * 0.16 * np.sqrt(30 / (252 * 390))
    assert abs(got - want) < 1e-9
    # a 30-minute window is sqrt(2) narrower than a 60-minute one
    assert abs(VX.vix_to_bp(np.array([16.0]), 60)[0] / got - np.sqrt(2)) < 1e-9


def test_vrp_is_zero_when_implied_equals_realised():
    """Pins the interpretation: `vrp_log == 0` means options price the next 30 minutes
    exactly as the last 30 minutes delivered."""
    level = 20.0
    realised = float(VX.vix_to_bp(np.array([level]), 30)[0])
    v = _toy_vix(n=4, start="2020-01-02 14:30", base=level)
    v["close"] = level                                     # flat VIX
    d = _toy_decisions([pd.Timestamp("2020-01-02 14:59", tz="UTC")], past_rv=realised)
    j, _ = _patched_attach(v, d)
    assert abs(float(j.vrp_log.iloc[0])) < 1e-9


def test_slot_z_never_uses_the_row_s_own_value():
    """A single slot whose history is constant and then jumps: the jump must not be
    absorbed into its own mean, so its z-score must be large and positive."""
    n = 80
    frame = pd.DataFrame({"mfo": 29, "x": [10.0] * (n - 1) + [99.0]})
    frame["x"] = frame.x + np.linspace(0, 1e-6, n)         # avoid a zero std
    z = VX._slot_z(frame, "x", lookback=90, min_obs=60)
    assert not np.isfinite(z.iloc[0])                      # min_obs not yet met
    assert z.iloc[-1] > 10.0, "the jump leaked into its own normaliser"


def test_real_export_is_contiguous_and_unique():
    """Rule 9a on the shipped tiles: no duplicate timestamps, plausible VIX range."""
    try:
        v, q = VX.load_vix_15m()
    except FileNotFoundError:
        return
    assert q["duplicate_ts"] == 0
    assert q["nonpositive"] == 0
    assert 5.0 < q["min_close"] < 15.0 and 50.0 < q["max_close"] < 200.0
    assert v.ts_utc.is_monotonic_increasing
    assert q["median_bars_per_session"] == 27.0            # 09:30..16:00 at 15 minutes
