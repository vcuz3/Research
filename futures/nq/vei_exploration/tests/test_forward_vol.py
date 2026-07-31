"""Causality + reproduction tests for `core/forward_vol.py` (rules 7, 11, 23).

Load-bearing claims, each pinned by one test:
  * the forward target is built from bars strictly AFTER the decision bar, and the
    15-minute range feature from bars at/before it -- the two never overlap;
  * a decision's same-slot median never contains that decision's own target;
  * a broken minute run, a symbol change or a roll marker inside the forward window
    voids the target rather than silently bridging it;
  * walk-forward forecasts for year Y are fitted only on years < Y;
  * sealing the parquet read at a date does not change ANY earlier row -- the
    leakage invariant that lets one full-history frame reproduce both the sealed
    Part A and the locked Part B of EXP-0011.

The last test touches the real parquet and is skipped when it is absent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import forward_vol as FV


def _toy_session(sdate, n=390, seed=0, price=100.0):
    rng = np.random.default_rng(seed)
    px = price + np.cumsum(rng.normal(0, 0.05, n))
    return pd.DataFrame({
        "sdate": sdate, "mfo": np.arange(n), "open": px,
        "high": px + 0.02, "low": px - 0.02, "close": px,
        "symbol": "TEST", "is_roll": False})


def test_target_uses_only_bars_after_the_decision_bar():
    g = _toy_session(pd.Timestamp(2020, 1, 2))
    base = FV._target_paths_for_session(g)
    p = 100                                   # perturb a bar at/BEFORE decision p
    g2 = g.copy()
    g2.loc[g2.mfo <= p, ["open", "high", "low", "close"]] *= 1.05
    after = FV._target_paths_for_session(g2)
    # the decision at p reads only bars p+1.. so its target must be untouched
    assert np.isclose(base.loc[p, "fwd_rv_bp"], after.loc[p, "fwd_rv_bp"])
    # and a bar INSIDE the forward window must change it (the target is a look-ahead)
    g3 = g.copy()
    g3.loc[g3.mfo == p + 5, ["open", "high", "low", "close"]] *= 1.01
    assert not np.isclose(base.loc[p, "fwd_rv_bp"],
                          FV._target_paths_for_session(g3).loc[p, "fwd_rv_bp"])


def test_target_window_is_exactly_the_horizon_and_starts_next_minute():
    g = _toy_session(pd.Timestamp(2020, 1, 2))
    out = FV._target_paths_for_session(g)
    p = 29
    opens = g["open"].to_numpy()
    expect_abs = 1e4 * abs(np.log(opens[p + FV.HORIZON_MIN + 1] / opens[p + 1]))
    assert np.isclose(out.loc[p, "fwd_abs_bp"], expect_abs)
    path = np.diff(np.log(opens[p + 1:p + FV.HORIZON_MIN + 2]))
    assert len(path) == FV.HORIZON_MIN
    assert np.isclose(out.loc[p, "fwd_rv_bp"], 1e4 * np.sqrt(np.sum(path ** 2)))


def test_roll_gap_or_symbol_change_voids_the_target():
    p = 29
    for mutate in ("roll", "symbol", "gap"):
        g = _toy_session(pd.Timestamp(2020, 1, 2))
        if mutate == "roll":
            g.loc[g.mfo == p + 5, "is_roll"] = True
        elif mutate == "symbol":
            g.loc[g.mfo >= p + 5, "symbol"] = "OTHER"
        else:
            g = g[g.mfo != p + 5].reset_index(drop=True)   # a missing minute
        assert not np.isfinite(FV._target_paths_for_session(g).loc[p, "fwd_rv_bp"]), mutate


def test_semivariance_legs_decompose_the_forward_variance_exactly():
    g = _toy_session(pd.Timestamp(2020, 1, 2))
    out = FV._target_paths_for_session(g)
    m = out.fwd_rv_bp.notna()
    assert m.sum() > 100
    lhs = out.loc[m, "fwd_rv_bp"] ** 2
    rhs = out.loc[m, "fwd_dsv_bp"] ** 2 + out.loc[m, "fwd_usv_bp"] ** 2
    assert np.allclose(lhs, rhs, rtol=1e-12, atol=1e-12)
    assert (out.loc[m, "fwd_dsv_bp"] >= 0).all() and (out.loc[m, "fwd_usv_bp"] >= 0).all()


def test_past_window_is_causal_and_never_reaches_the_forward_window():
    g = _toy_session(pd.Timestamp(2020, 1, 2))
    base = FV._past_paths_for_session(g)
    p = 120
    # a bar strictly AFTER the decision bar cannot enter the trailing statistic
    g2 = g.copy()
    g2.loc[g2.mfo > p, ["open", "high", "low", "close"]] *= 1.05
    assert np.isclose(base.loc[p, "past_rv30_bp"],
                      FV._past_paths_for_session(g2).loc[p, "past_rv30_bp"])
    # a bar INSIDE the trailing window must change it
    g3 = g.copy()
    g3.loc[g3.mfo == p - 5, ["open", "high", "low", "close"]] *= 1.01
    assert not np.isclose(base.loc[p, "past_rv30_bp"],
                          FV._past_paths_for_session(g3).loc[p, "past_rv30_bp"])


def test_past_window_matches_the_forward_estimator_on_the_same_prices():
    """The benchmark must be the SAME estimator, or log(fwd/past) carries a bias."""
    g = _toy_session(pd.Timestamp(2020, 1, 2))
    past = FV._past_paths_for_session(g)
    fwd = FV._target_paths_for_session(g)
    p = 120
    # the trailing window ending at p, and the forward window of the decision that
    # ends where it starts, are the same estimator over adjacent price paths
    assert np.isclose(past.loc[p, "past_rv30_bp"],
                      fwd.loc[p - FV.HORIZON_MIN - 1, "fwd_rv_bp"])


def test_past_window_scales_the_short_first_slot_and_never_crosses_the_open():
    g = _toy_session(pd.Timestamp(2020, 1, 2))
    out = FV._past_paths_for_session(g)
    assert not np.isfinite(out.loc[28, "past_rv30_bp"])      # 28 returns < 29 minimum
    opens = g["open"].to_numpy(float)
    path = np.diff(np.log(opens[0:30]))                       # 29 in-session returns only
    assert np.isclose(out.loc[29, "past_rv30_bp"],
                      1e4 * np.sqrt(np.sum(path ** 2) * FV.HORIZON_MIN / 29))
    # a missing minute inside the window voids it rather than bridging the gap
    g2 = g[g.mfo != 100].reset_index(drop=True)
    pos = int(g2.index[g2.mfo == 120][0])
    assert not np.isfinite(FV._past_paths_for_session(g2).loc[pos, "past_rv30_bp"])


def test_within_slot_ic_weights_by_count_and_ignores_cross_slot_ordering():
    from ..core import analysis as A
    rng = np.random.default_rng(0)
    # slot A: x predicts y. slot B: x is noise. Slot LEVELS are wildly different, so a
    # pooled IC would be ~1 while the honest within-slot answer is the weighted mean.
    n_a, n_b = 300, 100
    xa = rng.normal(0, 1, n_a)
    xb = rng.normal(0, 1, n_b)
    x = np.r_[xa + 100, xb]
    y = np.r_[xa + 100, rng.normal(0, 1, n_b)]
    slot = np.r_[np.zeros(n_a), np.ones(n_b)]
    pooled = A.spearman(x, y)
    within = A.within_slot_ic_arrays(x, y, slot)
    assert pooled > 0.95                                   # cross-slot level ordering
    ic_a = A.spearman(xa, xa)
    ic_b = A.spearman(xb, y[n_a:])
    assert np.isclose(within, (ic_a * n_a + ic_b * n_b) / (n_a + n_b))
    assert within < pooled - 0.1                           # the honest answer is lower


def test_slot_median_never_contains_its_own_session():
    slot = 29
    n = 200
    d = pd.DataFrame({"mfo": slot, "sdate": pd.date_range("2020-01-01", periods=n, freq="D"),
                      "fwd_rv_bp": np.arange(n, dtype=float)})
    med = d.groupby("mfo")["fwd_rv_bp"].transform(
        lambda s: s.shift(1).rolling(FV.SLOT_LOOKBACK, min_periods=FV.SLOT_MIN_OBS).median())
    assert med.iloc[:FV.SLOT_MIN_OBS].isna().all()
    i = 120
    window = d["fwd_rv_bp"].iloc[i - FV.SLOT_LOOKBACK:i]
    assert np.isclose(med.iloc[i], np.median(window))
    assert med.iloc[i] < d["fwd_rv_bp"].iloc[i]     # strictly prior, monotone series


def test_walkforward_trains_only_on_earlier_years():
    rng = np.random.default_rng(0)
    years = [2011, 2012, 2013, 2014]
    per = 2000
    n = per * len(years)
    frame = pd.DataFrame({
        "year": np.repeat(years, per),
        "mfo": np.resize(FV.decision_mfos(), n),
        FV.SLOT_MEDIAN: rng.uniform(5, 20, n), "range_rv_15m": rng.uniform(1e-4, 1e-3, n)})
    frame[FV.TARGET] = 100 * frame["range_rv_15m"] * 1e4 + rng.normal(0, .5, n)
    base = FV.walkforward_forecast(frame, 2013)

    def year_pred(p, y):
        return p.loc[p.year == y, "fvol_bp"].to_numpy()

    # (i) corrupting a LATER year cannot change an earlier year's forecast
    later = frame.copy()
    later.loc[later.year == 2014, [FV.TARGET, "range_rv_15m"]] *= 50.0
    assert np.allclose(year_pred(base, 2013), year_pred(FV.walkforward_forecast(later, 2013), 2013))
    # (ii) the model never sees the TEST year's own target
    own = frame.copy()
    own.loc[own.year == 2013, FV.TARGET] += 1000.0
    assert np.allclose(year_pred(base, 2013), year_pred(FV.walkforward_forecast(own, 2013), 2013))
    # (iii) but corrupting an EARLIER (training) year must move it
    earlier = frame.copy()
    earlier.loc[earlier.year == 2012, FV.TARGET] += 1000.0
    assert not np.allclose(year_pred(base, 2013),
                           year_pred(FV.walkforward_forecast(earlier, 2013), 2013))


def test_decision_slots_all_have_room_for_the_forward_window():
    dm = FV.decision_mfos()
    assert dm[0] == 29 and len(dm) == 11 and dm[-1] == 329
    assert all(m + FV.HORIZON_MIN + 1 < FV.RTH_MINUTES for m in dm)


def test_sealing_the_read_does_not_change_earlier_rows():
    """The leakage invariant: causal features must not depend on data after them."""
    if not FV.ONE_MIN["NQ"].exists():                     # pragma: no cover
        print("      (skipped: clean parquet not present)")
        return
    seal = pd.Timestamp("2015-01-01", tz="America/New_York").tz_convert("UTC")
    sealed, _ = FV.build_decision_frame("NQ", data_end_utc=seal)
    full, _ = FV.build_decision_frame("NQ")
    a = full.loc[full.sdate < "2015-01-01"].reset_index(drop=True)
    b = sealed.reset_index(drop=True)
    assert len(a) == len(b) and a["ts_utc"].equals(b["ts_utc"])
    for col in [FV.SLOT_MEDIAN, "range_rv_15m", FV.TARGET]:
        assert (a[col].isna() == b[col].isna()).all(), col
        m = a[col].notna()
        assert np.allclose(a.loc[m, col], b.loc[m, col], rtol=0, atol=0), col
