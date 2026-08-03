"""
Executable invariants for the FX Noise-Area port. Run:

    python -u -m forex.noise_vwap.tests.test_core

The load-bearing claims tested here are:
  * TWAP is the VWAP formula under constant volume, and is NOT the same thing as
    a volume-weighted average when the weights actually vary (the whole basis of
    the no-volume adaptation);
  * bands and TWAP are causal (a future bar cannot change a past value);
  * the engine never fills at the signal bar's own close and never at the band
    or stop level (RULES.md A1/A2);
  * `stop_ref="band"` uses no anchor at all, so it is genuinely volume-free;
  * the Null C shuffle pins the opening atom and preserves the session net move,
    the atom multiset and diffusivity (rule 17-bis / the 2026-07-18 learning).
"""
from __future__ import annotations

import sys
import traceback

import numpy as np
import pandas as pd

from ..core import engine, nulls, session

FAILURES: list[str] = []


def check(name: str, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
        traceback.print_exc(limit=3)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

def toy_bars(n=12, date="2020-01-02", start=100.0, step=0.5, seed=0):
    """Toy session. Bars carry a non-zero open-to-prior-close LINK so that the
    next bar's open is never numerically equal to the signal bar's close --
    otherwise a same-close fill and an honest next-open fill are
    indistinguishable and the fill test cannot fail."""
    rng = np.random.default_rng(seed)
    c = start + np.cumsum(np.full(n, step) + rng.normal(0, 0.05, n))
    link = rng.normal(0, 0.03, n) + 0.02 * np.sign(rng.normal(0, 1, n) + 0.5)
    o = np.concatenate(([start], c[:-1] + link[1:]))
    h = np.maximum(o, c) + 0.1
    l = np.minimum(o, c) - 0.1
    df = pd.DataFrame(dict(date=pd.Timestamp(date), mfo=np.arange(n),
                           open=o, high=h, low=l, close=c))
    tp = (df.high + df.low + df.close) / 3.0
    df["twap"] = tp.cumsum() / np.arange(1, n + 1)
    df["bar_i"] = np.arange(n)
    df["et"] = pd.Timestamp(date) + pd.to_timedelta(df.mfo, "m")
    return df


def toy_band(bars, half=0.5):
    o0 = bars["open"].iloc[0]
    return pd.DataFrame(dict(date=bars["date"].iloc[0], mfo=bars["mfo"].to_numpy(),
                             upper=o0 + half, lower=o0 - half))


# --------------------------------------------------------------------------
# 1. the no-volume adaptation
# --------------------------------------------------------------------------

def test_twap_is_vwap_under_constant_volume():
    b = toy_bars(20, seed=3)
    tp = (b.high + b.low + b.close) / 3.0
    for v in (1.0, 7.5, 1e6):
        vol = np.full(len(b), v)
        vwap = (tp * vol).cumsum() / vol.cumsum()
        assert np.allclose(vwap.to_numpy(), b["twap"].to_numpy(), atol=1e-12), v


def test_twap_differs_from_a_real_volume_weighted_average():
    """Guards the honest limitation: TWAP is the degenerate limit, not a proxy
    that recovers VWAP when weights vary."""
    b = toy_bars(20, seed=4)
    tp = (b.high + b.low + b.close) / 3.0
    rng = np.random.default_rng(11)
    vol = rng.lognormal(0, 1.0, len(b))
    vwap = (tp * vol).cumsum() / vol.cumsum()
    assert np.abs(vwap.to_numpy() - b["twap"].to_numpy()).max() > 1e-6


def test_twap_is_causal():
    b = toy_bars(20, seed=5)
    tp = (b.high + b.low + b.close) / 3.0
    ref = (tp.cumsum() / np.arange(1, len(b) + 1)).to_numpy()
    b2 = b.copy()
    b2.loc[b2.index[-1], ["high", "low", "close"]] = [999.0, 998.0, 998.5]
    tp2 = (b2.high + b2.low + b2.close) / 3.0
    got = (tp2.cumsum() / np.arange(1, len(b2) + 1)).to_numpy()
    assert np.allclose(ref[:-1], got[:-1])


# --------------------------------------------------------------------------
# 2. bands
# --------------------------------------------------------------------------

def _panel(n_sess=140, n_min=20, seed=1):
    rng = np.random.default_rng(seed)
    frames = []
    for k in range(n_sess):
        d = pd.Timestamp("2020-01-01") + pd.Timedelta(days=k)
        base = 100.0 + k * 0.01
        r = rng.normal(0, 0.02, n_min)
        c = base + np.cumsum(r)
        o = np.concatenate(([base], c[:-1]))
        frames.append(pd.DataFrame(dict(
            date=d, mfo=np.arange(n_min), open=o, close=c,
            high=np.maximum(o, c) + 0.01, low=np.minimum(o, c) - 0.01,
            et=d + pd.to_timedelta(np.arange(n_min), "m"))))
    df = pd.concat(frames, ignore_index=True)
    tp = (df.high + df.low + df.close) / 3.0
    df["twap"] = (tp.groupby(df["date"]).cumsum()
                  / (df.groupby("date").cumcount() + 1)).to_numpy()
    return df


def test_bands_use_only_strictly_prior_sessions():
    df = _panel()
    lb = 90
    b = session.noise_bands(df, lookback=lb)
    ds = np.sort(df["date"].unique())
    target = ds[120]
    ref = b[b.date == target].set_index("mfo")["sigma"]
    # corrupt the target session and every later one; prior history untouched
    df2 = df.copy()
    m = df2["date"] >= target
    df2.loc[m, ["open", "high", "low", "close"]] *= 3.0
    b2 = session.noise_bands(df2, lookback=lb)
    got = b2[b2.date == target].set_index("mfo")["sigma"]
    assert len(ref) > 0
    assert np.allclose(ref.to_numpy(), got.reindex(ref.index).to_numpy())


def test_band_min_periods_is_fractional_not_strict():
    """Rule 9a: one missing same-slot session must not null the whole window."""
    df = _panel(n_sess=120, n_min=10, seed=7)
    ds = np.sort(df["date"].unique())
    # delete slot 5 from a single mid-history session
    hole = (df["date"] == ds[40]) & (df["mfo"] == 5)
    df_hole = df.loc[~hole].reset_index(drop=True)
    b = session.noise_bands(df_hole, lookback=90, min_frac=0.90)
    late = b[(b.date == ds[110])]
    assert (late["mfo"] == 5).any(), "fractional min_periods should keep slot 5"
    strict = session.noise_bands(df_hole, lookback=90, min_frac=1.0)
    late_strict = strict[strict.date == ds[110]]
    assert not (late_strict["mfo"] == 5).any(), "strict rule should have nulled it"


def test_band_is_symmetric_when_there_is_no_gap():
    df = _panel(n_sess=110, n_min=8, seed=9)
    b = session.noise_bands(df, lookback=90)
    r = b.iloc[0]
    hi = max(r.sess_open, r.prior_close)
    lo = min(r.sess_open, r.prior_close)
    assert np.isclose(r.upper, hi * (1 + r.sigma))
    assert np.isclose(r.lower, lo * (1 - r.sigma))
    assert r.upper > r.lower


def test_decision_clock_is_on_the_et_wall_clock_and_drops_the_final_block():
    for sess, step in (("fxday", 30), ("active", 30), ("fxday", 60)):
        start_tod, length = session.SESSIONS[sess]
        ms = session.decision_mfos(sess, step)
        assert ms[0] >= step - 1, (sess, step)
        assert max(ms) < length - 1, (sess, step)
        # every decision lands on an ET minute-of-hour of step-1 mod step
        for m in ms:
            assert ((start_tod + m) % 60 + 1) % step == 0, (sess, step, m)
        assert len(set(np.diff(ms))) == 1 and np.diff(ms)[0] == step


def test_decision_clock_avoids_the_archive_holes():
    """The measured IBKR gaps are the first 15 minutes of an hour. No decision
    may land there or the NZDUSD afternoon decisions silently disappear."""
    for sess in ("fxday", "active"):
        start_tod, _ = session.SESSIONS[sess]
        for m in session.decision_mfos(sess, 30):
            assert (start_tod + m) % 60 >= 15, (sess, m)


# --------------------------------------------------------------------------
# 3. engine fills and stops
# --------------------------------------------------------------------------

def test_entry_fills_at_the_next_bar_open_never_the_signal_close():
    b = toy_bars(12, seed=2)
    bd = toy_band(b, half=0.3)
    tr = engine.simulate_session(b, bd, decision_mfos=[2, 5, 8], require_gate=False)
    assert len(tr) >= 1
    t0 = tr[0]
    i = int(np.where(b["mfo"].to_numpy() == t0["entry_mfo"])[0][0])
    assert np.isclose(t0["entry_px"], b["open"].to_numpy()[i])
    prev_close = b["close"].to_numpy()[i - 1]
    assert not np.isclose(t0["entry_px"], prev_close), "filled at the signal close"


def test_no_fill_at_the_band_or_stop_level():
    b = toy_bars(24, seed=6)
    bd = toy_band(b, half=0.2)
    tr = engine.run(b, bd, decision_mfos=[3, 7, 11, 15, 19], require_gate=False)
    px = np.r_[tr["entry_px"].to_numpy(), tr["exit_px"].to_numpy()]
    lv = np.r_[bd["upper"].unique(), bd["lower"].unique()]
    assert not np.isclose(px[:, None], lv[None, :], atol=1e-12).any()


def test_band_stop_ignores_the_anchor_entirely():
    """`stop_ref='band'` must be volume-free: perturbing TWAP cannot move it."""
    b = toy_bars(30, seed=8)
    bd = toy_band(b, half=0.25)
    a = engine.run(b, bd, [4, 9, 14, 19, 24], require_gate=False, stop_ref="band")
    b2 = b.copy()
    # Wreck the anchor UPWARD so it actually binds for a long under
    # stop_ref="both" (stop = max(upper, anchor)); halving it would sit far
    # below the band and change nothing, which would make the contrast vacuous.
    b2["twap"] = b2["close"].to_numpy() + 0.05
    c = engine.run(b2, bd, [4, 9, 14, 19, 24], require_gate=False, stop_ref="band")
    pd.testing.assert_frame_equal(a, c)
    # and the anchor DOES move the anchor-dependent references
    d = engine.run(b, bd, [4, 9, 14, 19, 24], require_gate=False, stop_ref="both")
    e = engine.run(b2, bd, [4, 9, 14, 19, 24], require_gate=False, stop_ref="both")
    assert not d.equals(e), "anchor perturbation did not bind under stop_ref='both'"


def test_gate_only_restricts_entries():
    b = toy_bars(40, seed=12)
    bd = toy_band(b, half=0.15)
    ms = [4, 9, 14, 19, 24, 29, 34]
    gated = engine.run(b, bd, ms, require_gate=True, stop_ref="band")
    open_ = engine.run(b, bd, ms, require_gate=False, stop_ref="band")
    assert len(gated) <= len(open_)


def test_positions_never_overlap_and_pnl_matches_prices():
    b = toy_bars(60, seed=13)
    bd = toy_band(b, half=0.2)
    tr = engine.run(b, bd, list(range(4, 60, 5)), require_gate=False)
    assert (tr["entry_mfo"].to_numpy() < tr["exit_mfo"].to_numpy()).all()
    assert (tr["exit_mfo"].to_numpy()[:-1] <= tr["entry_mfo"].to_numpy()[1:]).all()
    assert np.allclose(tr["points"],
                       (tr["exit_px"] - tr["entry_px"]) * tr["side"])


def test_every_bar_stop_check_is_at_least_as_tight_as_the_decision_clock():
    b = toy_bars(60, seed=14)
    bd = toy_band(b, half=0.2)
    ms = list(range(4, 60, 5))
    dec = engine.run(b, bd, ms, stop_ref="both", exit_check="decision", require_gate=False)
    eb = engine.run(b, bd, ms, stop_ref="both", exit_check="every_bar", require_gate=False)
    hold_dec = (dec["exit_mfo"] - dec["entry_mfo"]).mean()
    hold_eb = (eb["exit_mfo"] - eb["entry_mfo"]).mean()
    assert hold_eb <= hold_dec + 1e-9


def test_force_dir_control_is_one_trade_held_to_the_close():
    b = toy_bars(40, seed=15)
    bd = toy_band(b, half=0.2)
    tr = engine.run(b, bd, list(range(4, 40, 5)), force_dir=1, require_gate=False)
    assert len(tr) == 1 and tr["side"].iloc[0] == 1
    assert tr["reason"].iloc[0] == "eod"
    assert np.isclose(tr["exit_px"].iloc[0], b["close"].iloc[-1])


# --------------------------------------------------------------------------
# 4. Null C invariants
# --------------------------------------------------------------------------

def test_null_pins_the_opening_atom():
    df = _panel(n_sess=6, n_min=25, seed=21)
    for seed in (0, 1, 2, 3, 4):
        sh = nulls.null_c_returns(df, seed)
        for d in df["date"].unique():
            a = df[df.date == d].sort_values("mfo").iloc[0]
            b = sh[sh.date == d].sort_values("mfo").iloc[0]
            for col in ("open", "high", "low", "close"):
                assert np.isclose(a[col], b[col]), (seed, d, col)


def test_null_preserves_session_net_move_and_atoms():
    df = _panel(n_sess=8, n_min=30, seed=22)
    real_net = nulls.session_net_move(df)
    for seed in (0, 5, 9):
        sh = nulls.null_c_returns(df, seed)
        assert np.allclose(real_net.to_numpy(),
                           nulls.session_net_move(sh).reindex(real_net.index).to_numpy(),
                           atol=1e-9), seed
        for d in df["date"].unique():
            a = df[df.date == d].sort_values("mfo")
            b = sh[sh.date == d].sort_values("mfo")
            for col in ("high", "low", "close"):
                x = np.sort(np.round((a[col] - a["open"]).to_numpy(), 12))
                y = np.sort(np.round((b[col] - b["open"]).to_numpy(), 12))
                assert np.allclose(x, y), (seed, d, col)


def test_null_preserves_diffusivity_and_destroys_order():
    df = _panel(n_sess=40, n_min=60, seed=23)
    real = nulls.diffusivity(df)
    got = [nulls.diffusivity(nulls.null_c_returns(df, s)) for s in range(6)]
    assert np.isclose(real, np.mean(got), rtol=0.10), (real, got)
    # order really is destroyed: the shuffled close path differs
    sh = nulls.null_c_returns(df, 0)
    assert not np.allclose(df.sort_values(["date", "mfo"])["close"].to_numpy(),
                           sh.sort_values(["date", "mfo"])["close"].to_numpy())


def test_null_recomputes_twap_on_the_shuffled_path():
    df = _panel(n_sess=5, n_min=30, seed=24)
    sh = nulls.null_c_returns(df, 3)
    g = sh.sort_values(["date", "mfo"])
    tp = (g.high + g.low + g.close) / 3.0
    ref = (tp.groupby(g["date"]).cumsum()
           / (g.groupby("date").cumcount() + 1)).to_numpy()
    assert np.allclose(ref, g["twap"].to_numpy())


# --------------------------------------------------------------------------
# 5. metrics
# --------------------------------------------------------------------------

def test_zero_day_series_includes_untraded_sessions():
    from ..core import metrics
    tr = pd.DataFrame(dict(date=[pd.Timestamp("2020-01-01")] * 2,
                           side=[1, -1], points=[10 * session.PIP, -4 * session.PIP],
                           reason=["stop", "eod"], entry_mfo=[1, 2], exit_mfo=[5, 9]))
    dates = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
    s = metrics.summarize(tr, 0.0, all_dates=dates, label="x")
    assert s["n_sessions"] == 3 and s["n_trade_sessions"] == 1
    assert np.isclose(s["day_net_pips"], 6.0 / 3.0)
    s2 = metrics.summarize(tr, 0.0, all_dates=None, label="x")
    assert np.isclose(s2["day_net_pips"], 6.0)


def test_costs_are_two_sides_per_round_trip():
    from ..core import metrics
    tr = pd.DataFrame(dict(date=[pd.Timestamp("2020-01-01")], side=[1],
                           points=[10 * session.PIP], reason=["eod"],
                           entry_mfo=[1], exit_mfo=[5]))
    s = metrics.summarize(tr, 0.5, label="x")
    assert np.isclose(s["gross_pips_per_trade"], 10.0)
    assert np.isclose(s["net_pips_per_trade"], 9.0)


def main():
    print("forex/noise_vwap core invariants")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name[5:], fn)
    print()
    if FAILURES:
        print(f"FAILED {len(FAILURES)}: {', '.join(FAILURES)}")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
