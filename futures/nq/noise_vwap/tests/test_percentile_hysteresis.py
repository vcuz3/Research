import numpy as np
import pandas as pd

from futures.nq.noise_vwap.scripts.hyp_0021_percentile_hysteresis import (
    causal_sign_rank,
)


def test_causal_sign_rank_uses_only_prior_window_and_sign():
    x = np.array([1.0, -100.0, 2.0, 3.0, 4.0])
    got = causal_sign_rank(x, window=3, min_sign_obs=1)
    assert np.isnan(got[0])
    assert np.isnan(got[1])
    assert got[2] == 1.0       # 2 ranks only against prior positive 1
    assert got[3] == 1.0       # prior-session window is [1,-100,2]
    assert got[4] == 1.0       # oldest 1 has rolled out; compares with 2,3


def test_causal_sign_rank_is_invariant_to_future_change():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    a = causal_sign_rank(x, window=3, min_sign_obs=2)
    x[-1] = -999.0
    b = causal_sign_rank(x, window=3, min_sign_obs=2)
    np.testing.assert_allclose(a[:-1], b[:-1], equal_nan=True)
