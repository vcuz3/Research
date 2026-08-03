"""Invariant tests for `core/arbias.py`. 14 checks; all must pass before a run.

The load-bearing ones are the DIRECTION tests: that OLS is biased toward zero for
BOTH signs at small T (test 3), that slot-demeaning kills a pure clock while the
pooled estimator reports it as persistence (test 9), and that the audited ghe1
constants still match the script being audited (test 11).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import arbias as A

ROOT = Path(__file__).resolve().parents[1]
AUDITED = (ROOT.parents[0] / "noise_vwap" / "scripts" / "hyp_0017_hurst_filter.py")


def _mean_phi_hat(phi: float, T: int, draws: int, seed: int) -> float:
    rng = np.random.default_rng(seed)
    return float(np.mean([A.ols_ar1(A.simulate_ar1(phi, T, rng))
                          for _ in range(draws)]))


# --------------------------------------------------------------------------- #
# AR(1) estimation and correction
# --------------------------------------------------------------------------- #
def test_kendall_correct_inverts_kendall_bias():
    """The corrector must be the exact algebraic inverse of the bias it assumes."""
    for T in (20, 50, 200, 5000):
        for phi in (-0.5, -0.2, 0.0, 0.3, 0.7, 0.9):
            phi_c = A.kendall_correct(phi + A.kendall_bias(phi, T), T)
            assert abs(phi_c - phi) < 1e-9, (T, phi, phi_c)


def test_ols_ar1_is_consistent_at_large_T():
    """With enough data the naive estimator is fine -- the defect is small-sample."""
    rng = np.random.default_rng(11)
    for phi in (-0.4, 0.0, 0.5, 0.85):
        x = A.simulate_ar1(phi, 200_000, rng)
        assert abs(A.ols_ar1(x) - phi) < 0.01, phi


def test_ols_ar1_is_biased_toward_zero_at_small_T_for_both_signs():
    """The headline claim: the pull is toward zero regardless of sign."""
    T = 30
    for phi in (0.7, 0.4, -0.4, -0.7):
        got = _mean_phi_hat(phi, T, draws=4000, seed=abs(int(phi * 100)))
        assert abs(got) < abs(phi), (phi, got)          # shrunk toward zero
        assert np.sign(got) == np.sign(phi), (phi, got)  # but not flipped


def test_kendall_formula_predicts_the_measured_bias_at_small_T():
    """Validate -(1+3phi)/T empirically rather than trusting the citation."""
    T = 40
    for phi in (0.0, 0.3, 0.6, 0.8):
        measured = _mean_phi_hat(phi, T, draws=8000, seed=7 + int(phi * 10)) - phi
        predicted = A.kendall_bias(phi, T)
        assert abs(measured - predicted) < 0.02, (phi, measured, predicted)


def test_kendall_correction_reduces_bias_at_small_T():
    T, draws = 40, 3000
    for phi in (0.6, -0.5):
        rng = np.random.default_rng(21 + int(phi * 10))
        raw, cor = [], []
        for _ in range(draws):
            x = A.simulate_ar1(phi, T, rng)
            ph = A.ols_ar1(x)
            raw.append(ph)
            cor.append(A.kendall_correct(ph, T))
        assert abs(np.mean(cor) - phi) < abs(np.mean(raw) - phi), phi


def test_bootstrap_correction_reduces_bias_and_agrees_with_kendall():
    """Two independent correctors: a bug in one must not look like a finding."""
    T, phi = 60, 0.6
    rng = np.random.default_rng(33)
    raw, ken, boo = [], [], []
    for _ in range(150):
        x = A.simulate_ar1(phi, T, rng)
        ph = A.ols_ar1(x)
        raw.append(ph)
        ken.append(A.kendall_correct(ph, T))
        boo.append(A.bootstrap_ar1_correct(x, rng, nboot=120))
    assert abs(np.mean(boo) - phi) < abs(np.mean(raw) - phi)
    assert abs(np.mean(boo) - np.mean(ken)) < 0.03, (np.mean(boo), np.mean(ken))


def test_bias_shrinks_monotonically_with_window_length():
    """The mechanism behind the whole hypothesis: bias is a function of T."""
    phi = 0.6
    biases = [abs(_mean_phi_hat(phi, T, draws=3000, seed=90 + T) - phi)
              for T in (20, 40, 80, 160)]
    assert all(b1 > b2 for b1, b2 in zip(biases, biases[1:])), biases


# --------------------------------------------------------------------------- #
# the pooled estimator, and the clock it can mistake for memory
# --------------------------------------------------------------------------- #
def test_pooled_lag1_matches_a_hand_built_corrcoef():
    df = pd.DataFrame({"date": [1, 1, 1, 2, 2, 2],
                       "mfo": [29, 59, 89, 29, 59, 89],
                       "v": [1.0, 2.0, 3.0, 2.0, 4.0, 5.0]})
    ac, n = A.pooled_lag1(df, "v")
    x0 = np.array([1.0, 2.0, 2.0, 4.0])
    x1 = np.array([2.0, 3.0, 4.0, 5.0])
    assert n == 4
    assert abs(ac - np.corrcoef(x0, x1)[0, 1]) < 1e-12


def test_pooled_lag1_never_joins_two_groups():
    """A pair must never straddle a session boundary."""
    df = pd.DataFrame({"date": [1, 1, 2, 2],
                       "mfo": [29, 59, 29, 59],
                       "v": [0.0, 0.0, 10.0, 10.0]})
    _, n = A.pooled_lag1(df, "v")
    assert n == 2      # 1 pair per session, not 3 across the concatenation


def test_slot_demeaning_kills_a_pure_clock_that_pooling_reports_as_persistence():
    """Pins the Cell B sub-claim, and the direction of that second bias.

    Data = a deterministic per-slot ramp + iid noise. There is NO memory at all,
    but consecutive readings covary because both are high late in the session.
    """
    rng = np.random.default_rng(5)
    slots = np.array([29, 59, 89, 119, 149, 179, 209])
    ramp = np.linspace(0.0, 4.0, len(slots))
    rows = []
    for d in range(400):
        for s, r in zip(slots, ramp):
            rows.append((d, int(s), r + rng.normal(0.0, 0.30)))
    df = pd.DataFrame(rows, columns=["date", "mfo", "v"])

    pooled, _ = A.pooled_lag1(df, "v")
    demeaned, _ = A.pooled_lag1_slot_demeaned(df, "v")
    assert pooled > 0.85, pooled          # pure clock reads as strong persistence
    assert abs(demeaned) < 0.05, demeaned  # and vanishes once the clock is removed


# --------------------------------------------------------------------------- #
# the audited Hurst estimator
# --------------------------------------------------------------------------- #
def test_ghe1_constants_still_match_the_audited_script():
    """If noise_vwap's LAGS or H_GRID change, this audit is measuring a ghost."""
    src = AUDITED.read_text(encoding="utf-8")
    lags = re.search(r"LAGS\s*=\s*np\.array\(\[([^\]]*)\]\)", src)
    grid = re.search(r"H_GRID\s*=\s*np\.array\(\[([^\]]*)\]\)", src)
    assert lags and grid, "could not locate the constants in the audited script"
    got_lags = [int(t) for t in lags.group(1).replace(" ", "").split(",") if t]
    got_grid = [float(t) for t in grid.group(1).replace(" ", "").split(",") if t]
    assert got_lags == list(A.GHE_LAGS), (got_lags, list(A.GHE_LAGS))
    assert np.allclose(got_grid, A.H_GRID), (got_grid, list(A.H_GRID))


def test_ghe1_recovers_one_half_on_a_long_random_walk():
    rng = np.random.default_rng(3)
    est = [A.ghe1(np.cumsum(rng.normal(size=20_000))) for _ in range(20)]
    assert abs(float(np.mean(est)) - 0.5) < 0.02, float(np.mean(est))


def test_expanding_ghe1_matches_the_deployed_loop():
    """`expanding_ghe1` must equal ghe1(logp[:e+1]) call-for-call."""
    rng = np.random.default_rng(4)
    logp = np.cumsum(rng.normal(size=390)) * 1e-4 + 9.0
    ends = np.arange(29, 390, 30)
    got = A.expanding_ghe1(logp, ends)
    want = np.array([A.ghe1(logp[: int(e) + 1]) for e in ends])
    assert np.allclose(got, want, equal_nan=True)


# --------------------------------------------------------------------------- #
# normalisation and the selection-rate diagnostic
# --------------------------------------------------------------------------- #
def test_causal_slot_stats_uses_only_strictly_prior_sessions():
    """Truncation test: appending future sessions cannot change earlier output."""
    rng = np.random.default_rng(6)
    rows = [(d, s, float(rng.normal())) for d in range(200) for s in (29, 59)]
    df = pd.DataFrame(rows, columns=["date", "mfo", "v"])
    full_mu, _ = A.causal_slot_stats(df, "v", lookback=90, min_obs=45)
    head = df[df["date"] < 150].copy()
    head_mu, _ = A.causal_slot_stats(head, "v", lookback=90, min_obs=45)
    a = full_mu.loc[head.index].to_numpy()
    b = head_mu.to_numpy()
    assert np.allclose(a, b, equal_nan=True)


def test_threshold_at_rate_hits_the_requested_global_rate():
    rng = np.random.default_rng(8)
    v = rng.normal(size=50_000)
    for rate in (0.1, 0.3, 0.5):
        t = A.threshold_at_rate(v, rate)
        assert abs(float(np.mean(v >= t)) - rate) < 0.01, rate


def test_ols_ar1_batch_matches_the_scalar_estimator_row_for_row():
    """The fast path used by the calibration table must equal the tested one."""
    rng = np.random.default_rng(12)
    x = A.simulate_ar1(0.55, 200, rng, draws=25)
    fast = A.ols_ar1_batch(x)
    slow = np.array([A.ols_ar1(row) for row in x])
    assert np.allclose(fast, slow, atol=1e-12)


def test_selection_rate_cv_is_zero_when_flat_and_positive_when_clocked():
    flat = pd.Series({29: 0.30, 59: 0.30, 89: 0.30})
    clocked = pd.Series({29: 0.05, 59: 0.30, 89: 0.60})
    assert A.selection_rate_cv(flat) < 1e-12
    assert A.selection_rate_cv(clocked) > 0.5


def test_per_slot_rate_divides_by_defined_not_by_all_rows():
    """A coverage gap must not masquerade as a low selection rate."""
    df = pd.DataFrame({"mfo": [29, 29, 59, 59]})
    sel = np.array([True, False, True, False])
    defined = np.array([True, False, True, True])
    r = A.per_slot_selection_rate(df, sel, defined=defined)
    assert abs(r.loc[29] - 1.0) < 1e-12    # 1 of 1 DEFINED, not 1 of 2 rows
    assert abs(r.loc[59] - 0.5) < 1e-12


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
