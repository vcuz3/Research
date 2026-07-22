"""Validate the estimator panel against synthetic paths with KNOWN Hurst H.

Run: python -m pytest futures/nq/hurst_explore/tests/test_hurst.py -q
or:  python -m futures.nq.hurst_explore.tests.test_hurst   (self-check main)

The panel is only trustworthy on real data if it recovers truth on synthetic
data.  These are the acceptance gates for A1's estimator core:

  * white-noise increments (ordinary BM) -> H = 0.5 for every estimator;
  * a near-pure trend -> structure-function H -> 1;
  * exact fBm with H in {0.3,0.4,0.6,0.7} -> every estimator recovers H to a
    tolerance consistent with a LONG window (this is truth-recovery, not the
    small-sample floor A1 goes on to measure);
  * the fGn generator is unbiased in mean and finite in variance.
"""
from __future__ import annotations

import numpy as np

from ..core import hurst as H
from ..core import loaders as L


LONG_LAGS = H.log_lags(2, 4000, 18)


# Per-estimator truth-recovery tolerances at a LONG window.  The structure
# function (ghe1/ghe2) and DFA are near-unbiased; R/S is known to carry a
# positive finite-sample bias (Anis-Lloyd/Peters), strongest at low H -- that
# bias is a real A1 result recorded in the recovery table, so R/S gets a looser
# gate here rather than being "fixed".
TOL = {"ghe1": 0.05, "ghe2": 0.05, "dfa": 0.05, "rs": 0.11}


def _panel_bias(h_true, n=16000, draws=40, seed=0):
    rng = np.random.default_rng(seed)
    ests = {k: [] for k in ("ghe1", "ghe2", "rs", "dfa")}
    for _ in range(draws):
        p = H.fbm(h_true, n, rng)
        pan = H.estimate_panel(p, LONG_LAGS)
        for k, v in pan.items():
            ests[k].append(v)
    return {k: (np.nanmean(v), np.nanstd(v)) for k, v in ests.items()}


def test_white_noise_is_half():
    # ordinary BM: increments iid -> H = 0.5 (R/S biased slightly high)
    res = _panel_bias(0.5, n=16000, draws=40, seed=1)
    for k, (mean, sd) in res.items():
        assert abs(mean - 0.5) < TOL[k], (k, mean, sd)


def test_trend_is_one():
    logp = np.linspace(0, 1, 4000) + 1e-6 * np.random.default_rng(2).standard_normal(4000)
    h = H.ghe(logp, LONG_LAGS, 1.0)
    assert h > 0.95, h


def test_fbm_recovery_persistent():
    for h_true in (0.6, 0.7):
        res = _panel_bias(h_true, n=16000, draws=40, seed=3)
        for k, (mean, sd) in res.items():
            assert abs(mean - h_true) < TOL[k], (k, h_true, mean, sd)


def test_fbm_recovery_antipersistent():
    for h_true in (0.3, 0.4):
        res = _panel_bias(h_true, n=16000, draws=40, seed=4)
        for k, (mean, sd) in res.items():
            assert abs(mean - h_true) < TOL[k], (k, h_true, mean, sd)


def test_fgn_generator_moments():
    rng = np.random.default_rng(5)
    x = H.fgn(0.7, 20000, rng)
    assert abs(x.mean()) < 0.05, x.mean()
    assert 0.3 < x.std() < 3.0, x.std()   # finite, O(1); exact scale is irrelevant


def test_scale_invariance():
    # multiplying the path by a constant must not move a slope-based estimate
    rng = np.random.default_rng(6)
    p = H.fbm(0.65, 8000, rng)
    a = H.estimate_panel(p, LONG_LAGS)
    b = H.estimate_panel(1000.0 * p, LONG_LAGS)
    for k in a:
        assert abs(a[k] - b[k]) < 1e-9, (k, a[k], b[k])


def test_complete_1m_grid_gate():
    """Every path admitted to scale estimators must have true one-minute spacing."""
    for inst in ("NQ", "ES"):
        for _, logp, mfo in L.sessions_1m(inst):
            assert len(logp) == L.EXPECTED_BARS_1M
            assert np.array_equal(mfo, np.arange(L.EXPECTED_BARS_1M))


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
    # also print the recovery table for the record
    print("\nTruth-recovery table (n=16000, 40 draws, LONG lags):")
    print(f"{'H_true':>7} | {'ghe1':>16} {'ghe2':>16} {'rs':>16} {'dfa':>16}")
    for h_true in (0.3, 0.4, 0.5, 0.6, 0.7):
        res = _panel_bias(h_true, n=16000, draws=40, seed=10)
        cells = " ".join(f"{res[k][0]:.3f}+/-{res[k][1]:.3f}"
                         for k in ("ghe1", "ghe2", "rs", "dfa"))
        print(f"{h_true:>7.2f} | {cells}")
    raise SystemExit(1 if fails else 0)
