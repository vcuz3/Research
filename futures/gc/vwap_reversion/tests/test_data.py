import numpy as np
import pandas as pd

from futures.gc.vwap_reversion.core.data import _add_vwap_sigma


def test_compiled_session_features_match_reference_groupby():
    bars = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-02"] * 3 + ["2026-01-05"] * 2),
        "high": [10.2, 10.5, 10.4, 11.2, 11.5],
        "low": [9.8, 10.0, 10.1, 10.8, 11.0],
        "close": [10.0, 10.3, 10.2, 11.0, 11.3],
        "volume": [2, 3, 1, 4, 2],
    })
    tp = ((bars.high + bars.low + bars.close) / 3.0).to_numpy()
    vol = bars.volume.to_numpy(dtype=float)
    key = bars.date
    cv = pd.Series(vol).groupby(key).cumsum().to_numpy()
    expected_vwap = pd.Series(tp * vol).groupby(key).cumsum().to_numpy() / cv
    expected_second = pd.Series(tp * tp * vol).groupby(key).cumsum().to_numpy() / cv
    expected_sigma = np.sqrt(np.maximum(0.0, expected_second - expected_vwap**2))

    got = _add_vwap_sigma(bars.copy())

    np.testing.assert_allclose(got.vwap, expected_vwap, rtol=0, atol=1e-12)
    np.testing.assert_allclose(got.sigma, expected_sigma, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(got.bar_i, [0, 1, 2, 0, 1])
