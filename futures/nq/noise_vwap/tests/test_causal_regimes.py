"""Invariant tests for the HYP-0029 causal regime construction."""
from __future__ import annotations

import numpy as np
import pandas as pd

from futures.nq.noise_vwap.core.causal_regimes import (
    causal_regimes,
    hysteresis_labels,
    regime_indicators,
    trailing_percentile,
)


def _close(n: int = 1200) -> pd.Series:
    rng = np.random.default_rng(7)
    ret = rng.normal(0.0002, 0.012, n)
    return pd.Series(100.0 * np.exp(np.cumsum(ret)),
                     index=pd.bdate_range("2010-01-01", periods=n))


def test_indicator_uses_returns_only_through_prior_session():
    close = _close(100)
    base = regime_indicators(close, 20)
    changed = close.copy()
    changed.iloc[70:] *= np.linspace(2.0, 10.0, len(changed) - 70)
    after = regime_indicators(changed, 20)
    pd.testing.assert_frame_equal(base.iloc[:71], after.iloc[:71])


def test_trailing_percentile_excludes_current_value_and_uses_midrank_ties():
    s = pd.Series([1.0, 2.0, 2.0, 4.0])
    out = trailing_percentile(s, window=3, min_obs=2, quantiles=(0.5,))
    assert np.isnan(out.loc[1, "percentile"])
    assert out.loc[2, "percentile"] == 0.75  # history [1,2], current tie at 2
    assert out.loc[3, "percentile"] == 1.0   # history [1,2,2], current 4
    assert out.loc[3, "q0.500000"] == 2.0


def test_future_mutation_cannot_change_past_regimes():
    close = _close()
    base = causal_regimes(close, 20, 252)
    changed = close.copy()
    changed.iloc[900:] *= np.linspace(1.0, 50.0, len(changed) - 900)
    after = causal_regimes(changed, 20, 252)
    pd.testing.assert_frame_equal(base.iloc[:900], after.iloc[:900])


def test_prefix_run_matches_same_prefix_of_full_run():
    close = _close()
    full = causal_regimes(close, 20, 252)
    prefix = causal_regimes(close.iloc[:900], 20, 252)
    pd.testing.assert_frame_equal(full.iloc[:900], prefix)


def test_bucket_boundaries_are_stable():
    close = _close()
    out = causal_regimes(close, 10, 252)
    valid = out.dropna(subset=["vol_percentile", "trend_percentile"])
    assert set(valid["vol_regime"].unique()) <= {"low", "normal", "elevated", "high"}
    assert set(valid["trend_regime"].unique()) <= {"chop", "weak", "trend"}


def test_zero_hysteresis_reproduces_raw_terciles_exactly():
    p = pd.Series([0.0, 0.2, 1 / 3, 0.5, 2 / 3, 0.9, np.nan])
    got = hysteresis_labels(p, (1 / 3, 2 / 3), ("chop", "weak", "trend"), 0.0)
    expected = pd.Series(["chop", "chop", "weak", "weak", "trend", "trend", pd.NA],
                         dtype="string")
    pd.testing.assert_series_equal(got, expected)


def test_hysteresis_ignores_small_boundary_wobbles_but_accepts_large_move():
    p = pd.Series([0.20, 0.34, 0.37, 0.39, 0.35, 0.20, 0.90])
    got = hysteresis_labels(p, (1 / 3, 2 / 3), ("chop", "weak", "trend"), 0.05)
    expected = pd.Series(["chop", "chop", "chop", "weak", "weak", "chop", "trend"],
                         dtype="string")
    pd.testing.assert_series_equal(got, expected)


def test_hysteresis_future_mutation_cannot_change_past_states():
    p = pd.Series(np.linspace(0.0, 1.0, 200))
    base = hysteresis_labels(p, (1 / 3, 2 / 3), ("chop", "weak", "trend"), 0.05)
    changed = p.copy()
    changed.iloc[150:] = np.linspace(1.0, 0.0, 50)
    after = hysteresis_labels(changed, (1 / 3, 2 / 3),
                              ("chop", "weak", "trend"), 0.05)
    pd.testing.assert_series_equal(base.iloc[:150], after.iloc[:150])
