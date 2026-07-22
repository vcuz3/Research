"""Regression tests for the review-driven A1/A2 corrections."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..scripts.a1_measurement_floor import bias_calibrated_level
from ..scripts.a2_timescale import corrected_band_bootstrap


def test_inverse_bias_calibration():
    floor = pd.DataFrame({
        "n_bars": [390, 390, 390],
        "estimator": ["x", "x", "x"],
        "H_true": [.4, .5, .6],
        "mean": [.44, .54, .64],
    })
    assert abs(bias_calibrated_level(.49, floor, 390, "x") - .45) < 1e-12
    assert np.isnan(bias_calibrated_level(.30, floor, 390, "x"))


def test_corrected_bootstrap_repeats_full_difference():
    taus = np.array([1, 2, 4, 8, 16])
    logt = np.log(taus)
    # Identical 0.5 slopes with session-specific intercepts must correct to 0.5.
    real = np.array([a + .5 * logt for a in np.linspace(-2, 2, 30)])
    ctrl = np.array([a + .5 * logt for a in np.linspace(-1, 1, 40)])
    point, lo, hi, se = corrected_band_bootstrap(
        real, ctrl, taus, 1, 16, reps=100, seed=12)
    assert abs(point - .5) < 1e-12
    assert lo <= .5 <= hi
    assert se < 1e-10


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
