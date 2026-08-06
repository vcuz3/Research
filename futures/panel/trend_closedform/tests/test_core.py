"""Invariant tests for `core/`. All must pass before any run is registered.

The load-bearing ones:

* `test_closed_form_is_an_exact_identity_*` -- the whole project is a comparison
  of a predicted number against a realised one, so if the two sides do not agree
  exactly when they are supposed to, nothing downstream can be interpreted.
  These are run at both execution lags and with injected rolls.
* `test_crossover_return_form_equals_price_form` -- pins the price-kernel to
  return-weight conversion that lets one closed form cover both rules.
* `test_slot_standardisation_kills_a_pure_intraday_scale_seasonal` -- pins the
  LEARNINGS 2026-08-03 defect: a pooled scale on a series with a deterministic
  per-slot volatility profile reports persistence that is not there.
* `test_cluster_bootstrap_is_wider_than_naive_under_duplicates` -- pins that the
  clustering is doing real work rather than being decoration.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import closedform as C
from ..core import engine as E
from ..core import filters as F
from ..core import panel as P
from ..core import stats as S


def _ar1(phi: float, n: int, rng, mu: float = 0.0) -> np.ndarray:
    e = rng.standard_normal(n)
    x = np.empty(n)
    x[0] = e[0]
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return x + mu


# --------------------------------------------------------------------------- #
# filters
# --------------------------------------------------------------------------- #
def test_ewma_kernel_is_the_articles_nu_to_the_m():
    w = F.ewma_kernel(span=32, length=10)
    nu = 1.0 - 2.0 / 33.0
    assert np.allclose(w, nu ** np.arange(1, 11))


def test_apply_kernel_is_strictly_causal():
    """Perturbing x at time T must not change any signal BEFORE T.

    `S_T` itself is allowed to move: `x_T` is observable at the close of bar T
    and `w[0]` multiplies it by construction.  Attainability is enforced by the
    engine's execution lag, not by the filter.
    """
    rng = np.random.default_rng(0)
    x = rng.standard_normal(400)
    w = F.ewma_kernel(16, 50)
    s0 = F.apply_kernel(x, w)
    x2 = x.copy()
    x2[300] += 10.0
    s1 = F.apply_kernel(x2, w)
    assert np.allclose(s0[:300], s1[:300], equal_nan=True)
    assert not np.isclose(s0[300], s1[300])


def test_apply_kernel_puts_the_most_recent_return_at_weight_one():
    """`w[0]` must multiply x_t, or every lag in the closed form is off by one."""
    x = np.zeros(50)
    x[20] = 1.0
    w = np.array([7.0, 3.0, 2.0])
    s = F.apply_kernel(x, w)
    assert s[20] == 7.0 and s[21] == 3.0 and s[22] == 2.0 and s[23] == 0.0


def test_apply_kernel_masks_the_unpopulated_head():
    x = np.ones(100)
    w = F.ewma_kernel(8, 30)
    s = F.apply_kernel(x, w)
    assert np.all(np.isnan(s[:29])) and np.all(np.isfinite(s[29:]))


def test_crossover_return_form_equals_price_form():
    """`EMA_f(P) - EMA_s(P)` computed on prices == kernel applied to returns."""
    rng = np.random.default_rng(3)
    r = rng.standard_normal(4000)
    price = np.cumsum(r) + 100.0
    fast, slow, M = 10.0, 40.0, 400
    cf = F._ema_price_weights(fast, M)
    cs = F._ema_price_weights(slow, M)
    c = cf / cf.sum() - cs / cs.sum()
    direct = np.full(price.size, np.nan)
    for t in range(M, price.size):
        direct[t] = float(np.dot(c, price[t::-1][:M]))
    w = F.crossover_kernel(fast, slow, M)
    via_returns = F.apply_kernel(r, w)
    ok = np.isfinite(direct) & np.isfinite(via_returns)
    assert ok.sum() > 3000
    assert np.max(np.abs(direct[ok] - via_returns[ok])) < 1e-8


def test_crossover_kernel_has_no_level_term():
    """A trend signal must not respond to the price LEVEL, only to changes."""
    w = F.crossover_kernel(10, 40, 400)
    x = np.zeros(2000)
    s = F.apply_kernel(x, w)                    # flat price -> zero signal
    assert np.nanmax(np.abs(s)) < 1e-12


def test_position_scale_gives_a_unit_variance_position_on_white_noise():
    rng = np.random.default_rng(5)
    x = rng.standard_normal(200_000)
    for w in (F.ewma_kernel(32), F.crossover_kernel(16, 64)):
        p = F.apply_kernel(x, w) / F.position_scale(w)
        assert abs(np.nanstd(p) - 1.0) < 0.02, w.size


# --------------------------------------------------------------------------- #
# the closed form
# --------------------------------------------------------------------------- #
def _identity_check(x, w, lag, tol=1e-10):
    ok = E.booked_mask(x, w, lag=lag)
    mom = C.booked_moments(x, maxlag=w.size, lag=lag, ok=ok)
    pred = C.predicted_pnl(w, mom)
    res, _ = E.run(x, w, lag=lag)
    assert abs(pred - res.gross) < tol, (lag, pred, res.gross)
    return pred, res.gross


def test_closed_form_is_an_exact_identity_at_lag_zero():
    rng = np.random.default_rng(7)
    _identity_check(_ar1(0.15, 6000, rng, mu=0.03), F.ewma_kernel(32, 120), lag=0)


def test_closed_form_is_an_exact_identity_at_lag_one():
    rng = np.random.default_rng(8)
    _identity_check(_ar1(0.15, 6000, rng, mu=0.03), F.ewma_kernel(32, 120), lag=1)


def test_closed_form_is_an_exact_identity_for_the_crossover():
    rng = np.random.default_rng(9)
    _identity_check(_ar1(-0.08, 6000, rng, mu=0.02), F.crossover_kernel(16, 64, 200), lag=1)


def test_closed_form_identity_survives_dropped_roll_returns():
    """A roll makes x NaN; predicted and realised must still agree exactly."""
    rng = np.random.default_rng(10)
    x = _ar1(0.1, 6000, rng, mu=0.02)
    x[rng.choice(6000, 60, replace=False)] = np.nan
    _identity_check(x, F.ewma_kernel(32, 120), lag=1)


def test_phi_decomposition_is_an_exact_partition():
    """PHI == autocorrelation term + drift term, with no residual."""
    rng = np.random.default_rng(11)
    x = _ar1(0.2, 4000, rng, mu=0.05)
    w = F.ewma_kernel(32, 120)
    ok = E.booked_mask(x, w, lag=1)
    mom = C.booked_moments(x, maxlag=w.size, lag=1, ok=ok)
    full = C.phi(w, mom)
    ac = C.phi(w, mom, include_drift=False)
    dr = C.phi(w, mom, include_autocorr=False)
    assert abs(full - (ac + dr)) < 1e-12


def test_a_pure_drift_series_puts_everything_in_the_drift_term():
    """No autocorrelation at all: PHI must be the SR^2 term alone."""
    rng = np.random.default_rng(12)
    x = rng.standard_normal(200_000) + 0.20
    w = F.ewma_kernel(32, 120)
    ok = E.booked_mask(x, w, lag=1)
    mom = C.booked_moments(x, maxlag=w.size, lag=1, ok=ok)
    ac = C.phi(w, mom, include_drift=False)
    dr = C.phi(w, mom, include_autocorr=False)
    assert abs(dr - 0.20 ** 2 * w.sum()) < 0.08 * abs(dr)
    assert abs(ac) < 0.15 * abs(dr)


def test_moments_recovers_a_known_ar1_autocorrelation():
    rng = np.random.default_rng(13)
    for phi in (-0.3, 0.0, 0.4):
        m = C.moments(_ar1(phi, 200_000, rng), maxlag=4)
        assert abs(m.rho[0] - 1.0) < 1e-12
        assert abs(m.rho[1] - phi) < 0.01
        assert abs(m.rho[2] - phi ** 2) < 0.01


def test_lag_one_prediction_drops_the_lag_one_autocorrelation():
    """The executable arm must not be paid for rho(1) -- it is unreachable."""
    rng = np.random.default_rng(14)
    x = _ar1(0.5, 200_000, rng)          # strong, purely lag-driven memory
    w = F.ewma_kernel(8, 40)
    m = C.moments(x, maxlag=w.size + 2)
    p0 = C.phi_from_rho(w, m.rho, m.sr, lag=0)
    p1 = C.phi_from_rho(w, m.rho, m.sr, lag=1)
    assert p0 > p1 > 0
    assert p1 < 0.85 * p0


def test_turnover_closed_form_matches_the_engines_measured_turnover():
    """`(2/sqrt(pi)) sqrt(1-nu)` is market-independent -- so check it on noise."""
    rng = np.random.default_rng(15)
    x = rng.standard_normal(300_000)
    for span in (16.0, 32.0, 64.0):
        w = F.ewma_kernel(span)
        res, _ = E.run(x, w, lag=1)
        pred = C.turnover_closed_form(span)
        assert abs(res.turnover_pos - pred) < 0.03 * pred, (span, res.turnover_pos, pred)


def test_contract_turnover_is_not_the_risk_unit_turnover():
    """The two must not be conflated: only the risk-unit one is market-free."""
    rng = np.random.default_rng(26)
    x = rng.standard_normal(20_000)
    w = F.ewma_kernel(32)
    res, _ = E.run(x, w, lag=1, vol=np.full(x.size, 0.004))
    assert abs(res.turnover / res.turnover_pos - 250.0) < 1.0     # 1 / 0.004


# --------------------------------------------------------------------------- #
# engine
# --------------------------------------------------------------------------- #
def test_engine_cost_reduces_net_and_scales_with_the_cost_level():
    rng = np.random.default_rng(16)
    x = rng.standard_normal(50_000) + 0.02
    w = F.ewma_kernel(32)
    vol = np.ones(x.size)
    r1, _ = E.run(x, w, lag=1, vol=vol, cost_per_contract=np.full(x.size, 0.01))
    r2, _ = E.run(x, w, lag=1, vol=vol, cost_per_contract=np.full(x.size, 0.02))
    assert r1.net < r1.gross
    assert abs(r2.cost - 2 * r1.cost) < 1e-9
    assert abs(r1.gross - r2.gross) < 1e-12          # cost must not touch gross


def test_engine_positions_do_not_anticipate_a_future_shock():
    rng = np.random.default_rng(17)
    x = rng.standard_normal(2000)
    w = F.ewma_kernel(32, 100)
    _, p0 = E.run(x, w, lag=1)
    x2 = x.copy()
    x2[1500] += 25.0
    _, p1 = E.run(x2, w, lag=1)
    # The decision at t books x[t+2], so t = 1498 is the first legitimately
    # affected row; everything strictly before it must be untouched.
    assert np.allclose(p0[:1498], p1[:1498], equal_nan=True)


def test_booked_mask_matches_what_the_engine_actually_books():
    rng = np.random.default_rng(18)
    x = rng.standard_normal(3000)
    x[rng.choice(3000, 40, replace=False)] = np.nan
    w = F.ewma_kernel(16, 60)
    for lag in (0, 1, 3):
        res, pnl = E.run(x, w, lag=lag)
        assert int(np.isfinite(pnl).sum()) == res.n == int(E.booked_mask(x, w, lag).sum())


# --------------------------------------------------------------------------- #
# panel: ticks, risk units, slot standardisation
# --------------------------------------------------------------------------- #
def test_infer_tick_recovers_decimal_and_binary_grids():
    rng = np.random.default_rng(19)
    for g, base in ((5e-5, 1.1), (0.25, 4500.0), (2.0 ** -6, 130.0), (0.01, 75.0)):
        px = base + g * rng.integers(-2000, 2000, 5000)
        assert abs(P.infer_tick(px) - g) < 1e-12, g


def test_infer_tick_reads_a_mid_sample_tick_change_per_year():
    """Six of seven CME FX contracts changed tick mid-sample -- this must show."""
    rng = np.random.default_rng(20)
    early = pd.DataFrame({"sdate": pd.to_datetime(["2012-01-02"] * 2000),
                          "close": 1.3 + 1e-4 * rng.integers(-500, 500, 2000)})
    late = pd.DataFrame({"sdate": pd.to_datetime(["2018-01-02"] * 2000),
                         "close": 1.1 + 5e-5 * rng.integers(-500, 500, 2000)})
    t = P.infer_ticks_by_year(pd.concat([early, late], ignore_index=True))
    assert abs(t.loc[2012] - 1e-4) < 1e-12 and abs(t.loc[2018] - 5e-5) < 1e-12


def test_risk_units_are_causal_and_drop_the_roll_return():
    n = 400
    price = pd.Series(np.cumsum(np.ones(n)) + 100.0)
    roll = pd.Series(np.zeros(n, dtype=bool))
    roll.iloc[200] = True
    ru = P.risk_units(price, roll, vol_window=63)
    assert np.isnan(ru["dp"].iloc[200])                 # roll return dropped
    # vol at row t must not move when the price at row t changes
    p2 = price.copy()
    p2.iloc[300] += 500.0
    ru2 = P.risk_units(p2, roll, vol_window=63)
    assert np.allclose(ru["vol"].iloc[:301], ru2["vol"].iloc[:301], equal_nan=True)
    assert not np.isclose(ru["vol"].iloc[301], ru2["vol"].iloc[301])


def test_fractional_min_periods_survives_scattered_roll_gaps():
    """LEARNINGS 2026-07-19, caught in this project's own first build.

    With rolls at ~5% of rows, a strict `min_periods == vol_window` needs all 63
    trailing sessions roll-free and almost never gets it, so the risk unit is
    defined nowhere.  This is not hypothetical: it deleted 100% of all six energy
    products before the default was changed.
    """
    rng = np.random.default_rng(25)
    n = 3000
    price = pd.Series(np.cumsum(rng.standard_normal(n)) + 100.0)
    roll = pd.Series(np.zeros(n, dtype=bool))
    roll.iloc[rng.choice(n, int(0.05 * n), replace=False)] = True
    strict = P.risk_units(price, roll, vol_window=63, min_periods=63)["x"]
    loose = P.risk_units(price, roll, vol_window=63)["x"]
    assert np.isfinite(strict).mean() < 0.15, np.isfinite(strict).mean()
    assert np.isfinite(loose).mean() > 0.90, np.isfinite(loose).mean()


def _synthetic_slots(rng, n_sess=600, n_slot=46, scale_profile=None, mean_profile=None):
    slot = np.tile(np.arange(n_slot), n_sess)
    sdate = np.repeat(pd.to_datetime("2015-01-01")
                      + pd.to_timedelta(np.arange(n_sess), "D"), n_slot)
    dp = rng.standard_normal(n_sess * n_slot)
    if scale_profile is not None:
        dp = dp * scale_profile[slot]
    if mean_profile is not None:
        dp = dp + mean_profile[slot]
    return pd.DataFrame({"sdate": sdate, "slot": slot,
                         "close": np.cumsum(dp), "roll": False})


def _ac1(v):
    v = np.asarray(v, dtype=np.float64)
    ok = np.isfinite(v[:-1]) & np.isfinite(v[1:])
    return float(np.corrcoef(v[:-1][ok], v[1:][ok])[0, 1])


def test_slot_scaling_equalises_per_slot_variance_and_pooled_scaling_does_not():
    """The intraday arm's risk units must actually be unit-risk in every slot."""
    rng = np.random.default_rng(21)
    n_slot = 46
    profile = np.linspace(0.4, 2.5, n_slot)
    frame = _synthetic_slots(rng, scale_profile=profile)
    dp = frame["close"].diff()
    pooled = dp / dp.rolling(500).std().shift(1)
    slotted = P.slot_risk_units(frame, lookback=90, min_periods=45)["x"]
    sd_pooled = pooled.groupby(frame["slot"]).std()
    sd_slotted = slotted.groupby(frame["slot"]).std()
    assert sd_pooled.max() / sd_pooled.min() > 4.0        # profile survives
    assert sd_slotted.max() / sd_slotted.min() < 1.25     # profile removed


def test_a_per_slot_MEAN_profile_inflates_pooled_ac1_and_slot_demeaning_fixes_it():
    """LEARNINGS 2026-08-03, stated for the mechanism that actually applies.

    A per-slot SCALE profile leaves a pooled autocorrelation alone -- independent
    draws stay independent however they are scaled.  A per-slot MEAN profile does
    not: two consecutive readings covary because of where in the session they
    sit, and a pooled `rho(1)` reports that as memory.  This pins both halves.
    """
    rng = np.random.default_rng(22)
    n_slot = 46
    scale_only = _synthetic_slots(rng, scale_profile=np.linspace(0.4, 2.5, n_slot))
    x_scale = P.slot_risk_units(scale_only)["x"]
    assert abs(_ac1(x_scale)) < 0.05, _ac1(x_scale)       # scale alone: no inflation

    mean_prof = 1.2 * np.sin(np.linspace(0, 2 * np.pi, n_slot, endpoint=False))
    mean_only = _synthetic_slots(rng, mean_profile=mean_prof)
    x_mean = P.slot_risk_units(mean_only)["x"]
    assert _ac1(x_mean) > 0.20, _ac1(x_mean)              # mean profile: inflated
    x_dm = P.slot_demean(x_mean, mean_only["slot"])
    assert abs(_ac1(x_dm)) < 0.06, _ac1(x_dm)             # and demeaning fixes it


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
def test_spearman_matches_scipy():
    from scipy import stats as sps
    rng = np.random.default_rng(22)
    for _ in range(5):
        a, b = rng.standard_normal(40), rng.standard_normal(40)
        assert abs(S.spearman(a, b) - sps.spearmanr(a, b).statistic) < 1e-12
    a = np.array([1.0, 1.0, 2.0, 3.0, 3.0, 3.0])       # ties
    b = np.array([2.0, 1.0, 5.0, 4.0, 4.0, 9.0])
    assert abs(S.spearman(a, b) - sps.spearmanr(a, b).statistic) < 1e-12


def test_cluster_bootstrap_is_wider_than_naive_under_duplicates():
    """Six near-copies of one product must not count as six observations."""
    rng = np.random.default_rng(23)
    base_a, base_b = rng.standard_normal(5), rng.standard_normal(5)
    a = np.repeat(base_a, 6) + 0.01 * rng.standard_normal(30)
    b = np.repeat(base_b, 6) + 0.01 * rng.standard_normal(30)
    clusters = np.repeat([f"c{i}" for i in range(5)], 6)
    clustered = S.cluster_bootstrap_spearman(a, b, clusters, draws=2000, seed=1)
    singleton = S.cluster_bootstrap_spearman(a, b, np.arange(30).astype(str),
                                             draws=2000, seed=1)
    assert (clustered.hi - clustered.lo) > 1.5 * (singleton.hi - singleton.lo)


def test_repairing_null_centres_at_zero_and_flags_a_real_relationship():
    rng = np.random.default_rng(24)
    a = rng.standard_normal(30)
    b = a + 0.3 * rng.standard_normal(30)
    draws, frac = S.repairing_null_spearman(a, b, draws=4000, seed=2)
    assert abs(draws.mean()) < 0.05 and frac < 0.01
    _, frac_null = S.repairing_null_spearman(a, rng.standard_normal(30),
                                             draws=4000, seed=3)
    assert 0.05 < frac_null < 0.95


def test_kendall_tau_pairs_counts_a_declared_ordering():
    vals = {"NQ": 3.0, "ES": 2.0, "GC": 2.5, "RTY": 1.0}
    ok, tot, bad = S.kendall_tau_pairs(["NQ", "ES", "GC", "RTY"], vals)
    assert (ok, tot) == (2, 3) and bad == ["ES<=GC"]


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception:
            fails += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    raise SystemExit(1 if fails else 0)
