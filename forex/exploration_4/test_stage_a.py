"""Unit tests for the Stage-A (EXP-0002) characterization primitives.

Every estimator is checked against a synthetic series whose answer is known
analytically, not against a previous run of itself. The variance-ratio tests
matter most: VR is the view the grain choice rests on, and a sign error there
would be invisible in the final report.

Run: python -m pytest forex/exploration_4/test_stage_a.py -q -p no:cacheprovider
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import _stage_a_lib as lib


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _minute_index(n, start="2020-01-06 00:00"):
    return pd.DatetimeIndex(pd.date_range(start, periods=n, freq="min"))


def _acc_from_returns(r, minute_pos=None, sess=None):
    r = np.asarray(r, float)
    n = len(r)
    if minute_pos is None:
        minute_pos = np.arange(n, dtype=np.int64)
    if sess is None:
        sess = np.zeros(n, np.int16)
    valid = np.isfinite(r)
    dm = np.where(valid, r - r[valid].mean(), 0.0)
    return lib.accumulate_vr(dm, minute_pos, valid, sess, max_lag=30)


def _analytic_vr_ar1(phi, tau):
    return 1.0 + 2.0 * sum((1 - k / tau) * phi ** k for k in range(1, tau))


# --------------------------------------------------------------------------- #
# View 1: variance ratio
# --------------------------------------------------------------------------- #

def test_vr_random_walk_is_one():
    rng = np.random.default_rng(11)
    r = rng.standard_normal(400_000)
    acc = _acc_from_returns(r)
    for tau in (5, 15, 30):
        out = lib.variance_ratio(acc, tau, cell=len(lib.ALL_SESSIONS) - 1)
        assert out["vr"] == pytest.approx(1.0, abs=0.02), tau
        assert abs(out["z"]) < 3.0, (tau, out["z"])


def test_vr_matches_analytic_ar1_both_signs():
    for phi in (-0.30, 0.25):
        rng = np.random.default_rng(7)
        n = 600_000
        e = rng.standard_normal(n)
        r = np.empty(n)
        r[0] = e[0]
        for i in range(1, n):          # explicit recursion: no library shortcut to trust
            r[i] = phi * r[i - 1] + e[i]
        acc = _acc_from_returns(r)
        for tau in (5, 10, 30):
            out = lib.variance_ratio(acc, tau, cell=len(lib.ALL_SESSIONS) - 1)
            assert out["vr"] == pytest.approx(_analytic_vr_ar1(phi, tau), abs=0.02), (phi, tau)
        # sign of the deviation must follow the sign of phi
        vr30 = lib.variance_ratio(acc, 30, cell=len(lib.ALL_SESSIONS) - 1)
        assert (vr30["vr"] < 1) == (phi < 0)
        assert abs(vr30["z"]) > 10


def test_vr_robust_z_is_not_fooled_by_volatility_clustering():
    """Heteroskedastic but serially uncorrelated returns must stay VR ~ 1 with a
    moderate robust z. This is the whole reason for the Lo-MacKinlay form."""
    rng = np.random.default_rng(3)
    n = 400_000
    vol = np.exp(rng.standard_normal(n).cumsum() * 0.01)     # slow-moving vol
    vol = 0.5 + 3.0 * (vol / vol.mean())
    r = rng.standard_normal(n) * vol
    acc = _acc_from_returns(r)
    out = lib.variance_ratio(acc, 30, cell=len(lib.ALL_SESSIONS) - 1)
    assert out["vr"] == pytest.approx(1.0, abs=0.03)
    assert abs(out["z"]) < 3.5


def test_vr_pairs_respect_gaps_and_never_bridge_them():
    """A lag-k pair is only counted when the timestamps are exactly k apart."""
    r = np.ones(10)
    minute_pos = np.array([0, 1, 2, 3, 4, 100, 101, 102, 103, 104], np.int64)
    acc = lib.accumulate_vr(r, minute_pos, np.ones(10, bool), np.zeros(10, np.int16), max_lag=3)
    cell = len(lib.ALL_SESSIONS) - 1
    # two contiguous runs of 5 -> lag1: 4+4, lag2: 3+3, lag3: 2+2. No cross-gap pair.
    assert acc["n_k"][0, cell] == 8
    assert acc["n_k"][1, cell] == 6
    assert acc["n_k"][2, cell] == 4
    assert acc["n0"][cell] == 10


def test_vr_session_cells_require_both_endpoints_in_session():
    r = np.ones(6)
    minute_pos = np.arange(6, dtype=np.int64)
    sess = np.array([0, 0, 0, 1, 1, 1], np.int16)
    acc = lib.accumulate_vr(r, minute_pos, np.ones(6, bool), sess, max_lag=1)
    assert acc["n_k"][0, 0] == 2                       # within session 0
    assert acc["n_k"][0, 1] == 2                       # within session 1
    assert acc["n_k"][0, len(lib.ALL_SESSIONS) - 1] == 5   # pooled cell bridges them


def test_vr_session_cells_use_session_demeaned_returns_f5():
    """Stage-A repair F5: a per-session VR must be demeaned WITHIN the session.

    Two contiguous iid (random-walk) sessions with opposite drifts. Globally demeaned,
    each session still carries a constant offset, which a lag-k autocovariance reads as
    strong spurious POSITIVE serial correlation (VR >> 1). Session-demeaning removes the
    offset and the per-session VR returns to ~1, while the pooled 'all' cell is ~1 in
    both cases (it is globally demeaned regardless).
    """
    rng = np.random.default_rng(19)
    n = 200_000
    r0 = rng.standard_normal(n) + 0.30       # session 0: +drift
    r1 = rng.standard_normal(n) - 0.30       # session 1: -drift
    r = np.concatenate([r0, r1])
    minute_pos = np.arange(2 * n, dtype=np.int64)          # fully contiguous
    sess = np.concatenate([np.zeros(n, np.int16), np.ones(n, np.int16)])
    valid = np.ones(2 * n, bool)
    dm = r - r.mean()                                       # global demean
    dm_sess = np.array(dm, copy=True)                       # session demean
    for code in (0, 1):
        cell = sess == code
        dm_sess[cell] = r[cell] - r[cell].mean()

    # Without the F5 fix (session cells fed the globally-demeaned series): inflated.
    acc_bad = lib.accumulate_vr(dm, minute_pos, valid, sess, max_lag=30)
    vr_bad = lib.variance_ratio(acc_bad, 30, cell=0)
    assert vr_bad["vr"] > 2.5, vr_bad["vr"]                 # spurious, offset-driven

    # With the F5 fix: session-demeaned returns feed the session cells -> VR ~ 1.
    acc = lib.accumulate_vr(dm, minute_pos, valid, sess, max_lag=30, returns_sess=dm_sess)
    vr0 = lib.variance_ratio(acc, 30, cell=0)
    assert vr0["vr"] == pytest.approx(1.0, abs=0.05), vr0["vr"]
    # the pooled 'all' cell is unaffected by returns_sess (still globally demeaned)
    all_cell = len(lib.ALL_SESSIONS) - 1
    vr_all_a = lib.variance_ratio(acc, 30, cell=all_cell)["vr"]
    vr_all_b = lib.variance_ratio(acc_bad, 30, cell=all_cell)["vr"]
    assert vr_all_a == pytest.approx(vr_all_b, abs=1e-9)


def test_vr_invalid_returns_are_excluded_not_zero_filled():
    rng = np.random.default_rng(5)
    r = rng.standard_normal(50_000)
    valid = np.ones(len(r), bool)
    valid[::7] = False                       # would be a huge fake lag structure if zero-filled
    dm = np.where(valid, r - r[valid].mean(), 0.0)
    acc = lib.accumulate_vr(dm, np.arange(len(r), dtype=np.int64), valid,
                            np.zeros(len(r), np.int16), max_lag=10)
    out = lib.variance_ratio(acc, 10, cell=len(lib.ALL_SESSIONS) - 1)
    assert out["vr"] == pytest.approx(1.0, abs=0.05)
    assert acc["n0"][len(lib.ALL_SESSIONS) - 1] == valid.sum()


# --------------------------------------------------------------------------- #
# Calendars
# --------------------------------------------------------------------------- #

def test_session_codes_dst_aware_and_overlap_dominates():
    cfg = {"tokyo": {"tz": "Asia/Tokyo", "open_minute": 540, "close_minute": 900},
           "london": {"tz": "Europe/London", "open_minute": 480, "close_minute": 990},
           "new_york": {"tz": "America/New_York", "open_minute": 480, "close_minute": 1020}}
    idx = pd.DatetimeIndex(["2020-01-15 01:00",   # Tokyo 10:00 -> asia
                            "2020-01-15 09:00",   # London 09:00, NY 04:00 -> london
                            "2020-01-15 14:00",   # London 14:00, NY 09:00 -> overlap
                            "2020-01-15 17:30",   # London closed, NY 12:30 -> ny
                            "2020-01-15 23:00"])  # nothing -> off
    got = [lib.SESSION_LABELS[c] for c in lib.session_codes(idx, cfg)]
    assert got == ["asia", "london", "overlap", "ny", "off"]
    # summer: the same UTC 13:00 is inside the overlap, and 07:30 UTC is London only
    summer = pd.DatetimeIndex(["2020-07-15 07:30", "2020-07-15 13:00"])
    got_s = [lib.SESSION_LABELS[c] for c in lib.session_codes(summer, cfg)]
    assert got_s == ["london", "overlap"]


def test_era_of_boundaries():
    idx = pd.DatetimeIndex(["2020-12-31 23:59", "2021-01-01 00:00",
                            "2023-12-31 23:59", "2024-01-01 00:00"])
    got = lib.era_of(idx, pd.Timestamp("2021-01-01"), pd.Timestamp("2024-01-01"))
    assert list(got) == ["early", "late", "late", "holdout"]


# --------------------------------------------------------------------------- #
# Grain construction
# --------------------------------------------------------------------------- #

def _synthetic_minutes(n=4000, seed=1, drop=()):
    idx = _minute_index(n)
    rng = np.random.default_rng(seed)
    px = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    frame = pd.DataFrame({"time": idx, "open": px, "high": px + 2e-4,
                          "low": px - 2e-4, "close": px})
    if drop:
        frame = frame.drop(index=list(drop)).reset_index(drop=True)
    return frame


def test_incomplete_grain_bars_are_nulled_not_filled():
    frame = _synthetic_minutes(600, drop=(10,))       # kills the 00:10-00:15 bar
    bars, meta = lib.build_grain_bars(frame, 5, sigma_window_minutes=100, min_fraction=0.9)
    bad = bars.loc[bars.minute_count.between(1, 4)]
    assert len(bad) >= 1
    assert bad[["open", "high", "low", "close"]].isna().all().all()
    # returns never bridge an incomplete bar
    assert bars.ret[~bars.contiguous].isna().all()
    assert meta["window_bars"] == 20 and meta["min_periods"] == 18


def test_sigma_survives_market_closures():
    """A window counted in raw BINS is unsatisfiable on spot FX (~71% calendar
    coverage), which nulls sigma everywhere. It must be counted in tradable bars."""
    idx = _minute_index(60 * 24 * 90)                     # 90 days of minutes
    rng = np.random.default_rng(9)
    px = 1.1 + np.cumsum(rng.standard_normal(len(idx))) * 1e-5
    frame = pd.DataFrame({"time": idx, "open": px, "high": px + 2e-4,
                          "low": px - 2e-4, "close": px})
    weekend = idx.weekday >= 5                            # drop ~28% of calendar minutes
    frame = frame.loc[~weekend].reset_index(drop=True)
    bars, meta = lib.build_grain_bars(frame, 5, sigma_window_minutes=28_800, min_fraction=0.9)
    assert meta["window_bars"] == 5760 and meta["min_periods"] == 5184
    live = bars.loc[bars.complete]
    assert live.sigma.notna().mean() > 0.6, "sigma must exist once warmed up"
    assert live.sigma.tail(500).notna().all()
    # warm-up is exactly min_periods TRADABLE bars, and nothing before that
    tradable = bars.ret.dropna()
    assert bars.sigma.dropna().index.min() == tradable.index[meta["min_periods"] - 1]


def test_sigma_window_is_time_not_bar_count():
    frame = _synthetic_minutes(40_000)
    _, m5 = lib.build_grain_bars(frame, 5, sigma_window_minutes=28_800, min_fraction=0.9)
    _, m60 = lib.build_grain_bars(frame, 60, sigma_window_minutes=28_800, min_fraction=0.9)
    assert m5["window_bars"] * 5 == m60["window_bars"] * 60 == 28_800


def test_z_is_one_bar_displacement_over_sigma():
    frame = _synthetic_minutes(6000)
    bars, _ = lib.build_grain_bars(frame, 15, sigma_window_minutes=3000, min_fraction=0.9)
    live = bars.dropna(subset=["z", "sigma", "ret"])
    assert len(live) > 50
    assert np.allclose(live.z, live.ret / live.sigma)


def _slot_fixture(days=400, tau=60, seed=3):
    """Minutes whose volatility has a strong, fixed intraday profile."""
    idx = _minute_index(days * 24 * 60)
    rng = np.random.default_rng(seed)
    hour = idx.hour.to_numpy()
    scale = np.where((hour >= 12) & (hour < 16), 5e-4, 5e-5)   # 10x busier midday
    px = 1.1 + np.cumsum(rng.standard_normal(len(idx)) * scale)
    frame = pd.DataFrame({"time": idx, "open": px, "high": px + 1e-4,
                          "low": px - 1e-4, "close": px})
    return frame.loc[idx.weekday < 5].reset_index(drop=True), tau


def test_same_slot_moments_are_causal_and_slot_specific():
    frame, tau = _slot_fixture()
    bars, _ = lib.build_grain_bars(frame, tau, sigma_window_minutes=28_800, min_fraction=0.9)
    mu, sd = lib.same_slot_moments(bars, tau, lookback_sessions=90, min_fraction=2 / 3)
    live = bars.complete & sd.notna()
    hours = pd.DatetimeIndex(bars.index).hour
    busy = live & hours.isin([12, 13, 14, 15])
    quiet = live & hours.isin([2, 3, 4, 5])
    # the estimator must recover the 10x intraday scale difference
    assert sd[busy].median() / sd[quiet].median() > 5
    # an all-hours sigma must NOT (that is the whole problem being fixed)
    assert 0.8 < bars.sigma[busy].median() / bars.sigma[quiet].median() < 1.25
    # The slot estimator warms up LATER than the all-hours one (90 sessions vs ~18
    # days), so it is null on an early band by design. Once warmed it must be complete.
    warm = bars.z.notna() & (bars.index >= sd.first_valid_index())
    assert sd[warm].notna().mean() > 0.99
    assert sd.first_valid_index() > bars.z.first_valid_index()
    # location term is tiny next to scale for a return series
    assert (mu[live].abs().median() / sd[live].median()) < 0.25


def test_same_slot_normalisation_flattens_the_firing_rate():
    """The pass signal from LEARNINGS §1: selection-rate CV across slots collapses."""
    frame, tau = _slot_fixture()
    bars, _ = lib.build_grain_bars(frame, tau, sigma_window_minutes=28_800, min_fraction=0.9)
    mu, sd = lib.same_slot_moments(bars, tau, lookback_sessions=90, min_fraction=2 / 3)
    z_abs = bars.z
    z_slot = (bars.ret - mu) / sd
    usable = bars.complete & z_abs.notna() & z_slot.notna()
    hours = pd.DatetimeIndex(bars.index).hour

    def cv(z, k):
        rate = (z[usable].abs() >= k).groupby(hours[usable]).mean()
        return rate.std() / rate.mean()

    # compare at MATCHED overall selection rate, not at a matched threshold
    target = float((z_abs[usable].abs() >= 2.0).mean())
    k_slot = float(np.quantile(z_slot[usable].abs(), 1 - target))
    assert cv(z_slot, k_slot) < cv(z_abs, 2.0) / 3


def test_same_slot_moments_never_use_the_current_session():
    """A one-session lag is the difference between a feature and a leak."""
    frame, tau = _slot_fixture(days=200, tau=120)
    bars, _ = lib.build_grain_bars(frame, tau, sigma_window_minutes=28_800, min_fraction=0.9)
    mu, sd = lib.same_slot_moments(bars, tau, lookback_sessions=30, min_fraction=2 / 3)
    spiked = bars.copy()
    target = np.flatnonzero((bars.complete & sd.notna()).to_numpy())[-1]
    spiked.iloc[target, spiked.columns.get_loc("ret")] = 500.0
    mu2, sd2 = lib.same_slot_moments(spiked, tau, lookback_sessions=30, min_fraction=2 / 3)
    assert sd2.iloc[target] == pytest.approx(sd.iloc[target]), "current session leaked in"
    assert mu2.iloc[target] == pytest.approx(mu.iloc[target])


def test_first_crossing_fires_once_per_excursion_and_rearms_after_a_gap():
    z = pd.Series([0.0, 3.0, 3.5, 0.1, -4.0, -4.0, 0.0])
    complete = pd.Series([True] * 7)
    contiguous = pd.Series([False, True, True, True, True, True, True])
    assert list(lib.first_crossing(z, complete, contiguous, 2.0)) == [1, 4]
    broken = contiguous.copy()
    broken.iloc[2] = False                    # a gap between bar 1 and 2 re-arms
    assert list(lib.first_crossing(z, complete, broken, 2.0)) == [1, 2, 4]


# --------------------------------------------------------------------------- #
# Minute grid
# --------------------------------------------------------------------------- #

def test_minute_grid_completeness_and_lookups():
    frame = _synthetic_minutes(200, drop=(50,))
    grid = lib.MinuteGrid(pd.DatetimeIndex(frame.time), frame.open, frame.high, frame.low)
    pos = lib.minute_positions(pd.DatetimeIndex(frame.time))
    off = grid.offsets(pos)
    assert np.allclose(grid.open_at(off), frame.open.to_numpy())
    # a 10-minute window that straddles the dropped minute 50 is incomplete
    start_at_45 = off[frame.time.eq(_minute_index(200)[45]).to_numpy()]
    assert not grid.path_complete(start_at_45, 10)[0]
    start_at_60 = off[frame.time.eq(_minute_index(200)[60]).to_numpy()]
    assert grid.path_complete(start_at_60, 10)[0]


def test_forward_extremes_match_bruteforce():
    frame = _synthetic_minutes(500)
    grid = lib.MinuteGrid(pd.DatetimeIndex(frame.time), frame.open, frame.high, frame.low)
    hi, lo = grid.forward_extremes(20)
    for m in (0, 37, 120, 300):
        assert hi[m] == pytest.approx(np.nanmax(grid.high[m:m + 21]))
        assert lo[m] == pytest.approx(np.nanmin(grid.low[m:m + 21]))


def test_extract_paths_alignment():
    frame = _synthetic_minutes(300)
    grid = lib.MinuteGrid(pd.DatetimeIndex(frame.time), frame.open, frame.high, frame.low)
    off = np.array([10, 100], np.int64)
    paths = grid.extract_paths(off, 6)
    assert paths["open"].shape == (2, 7)
    assert paths["open"][0, 0] == pytest.approx(frame.open.iloc[10])
    assert paths["open"][0, 6] == pytest.approx(frame.open.iloc[16])
    assert paths["high"][1, 3] == pytest.approx(frame.high.iloc[103])


# --------------------------------------------------------------------------- #
# Inference and metrics
# --------------------------------------------------------------------------- #

def test_cluster_se_exceeds_iid_se_under_within_day_dependence():
    rng = np.random.default_rng(2)
    day_effect = rng.standard_normal(200) * 1.0
    vals, clusters = [], []
    for d in range(200):
        vals.extend(day_effect[d] + rng.standard_normal(30) * 0.1)
        clusters.extend([d] * 30)
    out = lib.cluster_stats(vals, clusters)
    iid_se = np.std(vals, ddof=1) / np.sqrt(len(vals))
    assert out["se"] > 3 * iid_se
    assert out["n"] == 6000 and out["clusters"] == 200
    assert out["ci_low"] < out["mean"] < out["ci_high"]


def test_cluster_stats_degenerate_inputs_return_nan_not_significance():
    out = lib.cluster_stats([1.0], ["a"])
    assert np.isnan(out["t"])
    out2 = lib.cluster_stats([1.0, 2.0, 3.0], ["a", "a", "a"])
    assert np.isnan(out2["t"])


def test_cell_frames_pool_exactly_once_across_pairs():
    """The POOLED cell must be produced from all pairs at once. Calling the pooler
    inside a per-pair loop silently emits one 'POOLED' row per pair, each secretly a
    single pair -- a bug that looks like a plausible table."""
    import _run_stage_a as run
    frame = pd.DataFrame({
        "pair": ["EURUSD"] * 4 + ["GBPUSD"] * 6,
        "era": ["early", "early", "late", "late"] + ["early"] * 3 + ["late"] * 3,
        "session": ["asia"] * 10,
        "utc_day": pd.DatetimeIndex(pd.date_range("2020-01-01", periods=10, freq="D")),
        "v": np.arange(10.0),
    })
    counts = {}
    for f in run.cell_frames(frame):
        for (pair, era), g in f.groupby(["pair", "era"]):
            counts[(pair, era)] = counts.get((pair, era), 0) + len(g)
    # 'all'-session relabelling duplicates each cell once, hence the factor of 2
    assert counts[("POOLED", "consumed")] == 2 * 10
    assert counts[("POOLED", "early")] == 2 * 5      # 2 EURUSD + 3 GBPUSD early rows
    assert counts[("EURUSD", "consumed")] == 2 * 4


def test_profit_factor():
    assert lib.profit_factor([1.0, -1.0]) == pytest.approx(1.0)
    assert lib.profit_factor([2.0, 1.0, -1.0]) == pytest.approx(3.0)
    assert np.isinf(lib.profit_factor([1.0, 2.0]))
    assert lib.profit_factor([-1.0, -2.0]) == pytest.approx(0.0)


def test_greedy_non_overlap_enforces_one_position():
    entry = np.array([0, 5, 20, 25, 60])
    exit_ = np.array([10, 15, 30, 35, 70])
    keep = lib.greedy_non_overlap(entry, exit_)
    assert list(keep) == [True, False, True, False, True]


def test_three_sharpes_diverge_when_most_days_are_flat():
    days = pd.DatetimeIndex(pd.date_range("2020-01-01", periods=500, freq="D"))
    rng = np.random.default_rng(4)
    traded_days = days[::5]
    daily = pd.Series(rng.normal(0.02, 0.05, len(traded_days)), index=traded_days)
    out = lib.three_sharpes(daily, days)
    assert out["n_days_zero_filled"] == 500 and out["n_trade_days"] == 100
    assert out["sharpe_zero_day"] < out["sharpe_trade_days"]
    assert np.isfinite(out["sharpe_vol_targeted"])
