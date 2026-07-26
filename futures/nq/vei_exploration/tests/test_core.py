"""Causality + correctness tests for the VEI-exploration core (rule 7/8).

Load-bearing claims:
  * VEI (any ATR method / smoothing) at a bar uses only bars at/before it within the
    session -> perturbing FUTURE bars must not change it.
  * analysis.forward_features PAST columns are causal; FORWARD columns are pure
    look-ahead targets (they SHOULD change when future bars change).
  * variance_ratio ~1 on i.i.d. noise, >1 on a trend, <1 on an alternating series.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import vei as V
from ..core import analysis as A


def _toy(n_per=70, n_sess=3, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_sess):
        px = 100.0 + np.cumsum(rng.normal(0, 0.2, n_per))
        for i in range(n_per):
            rows.append({"sdate": pd.Timestamp(2020, 1, 1) + pd.Timedelta(days=s),
                         "mfo": i, "open": px[i],
                         "high": px[i] + abs(rng.normal(0, 0.1)),
                         "low": px[i] - abs(rng.normal(0, 0.1)), "close": px[i],
                         "volume": 1.0})
    return pd.DataFrame(rows)


def test_true_range_first_bar():
    df = _toy()
    tr = V.true_range(df)
    first = df.groupby("sdate").head(1).index
    assert np.allclose(tr.loc[first].to_numpy(),
                       (df["high"] - df["low"]).loc[first].to_numpy())


def test_vei_causal_all_methods():
    df = _toy(seed=1)
    bound = 49
    for method in ("sma", "wilder", "ema"):
        for smooth in (0, 5):
            for seed in (V.SEED_SMA, V.SEED_FIRST):
                base = V.vei_series(df, 10, 50, method, smooth, seed)
                p = df.copy()
                mask = p["mfo"] > bound
                p.loc[mask, ["open", "high", "low", "close"]] *= 5.0
                after = V.vei_series(p, 10, 50, method, smooth, seed)
                m = (df["mfo"] <= bound)
                a = base[m].to_numpy(); b = after[m].to_numpy()
                ok = np.isfinite(a) & np.isfinite(b)
                assert np.allclose(a[ok], b[ok]), (method, smooth, seed)


def _wilder_loop(tr: np.ndarray, n: int, alpha: float) -> np.ndarray:
    """Literal textbook reference: SMA seed at bar n-1, then the recursion."""
    out = np.full(len(tr), np.nan)
    if len(tr) < n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(tr)):
        out[i] = (1.0 - alpha) * out[i - 1] + alpha * tr[i]
    return out


def test_wilder_seed_matches_reference_loop():
    """The closed-form correction in _ewm_sma_seeded must equal a literal loop, per
    session and for both exponential methods, including short/ragged sessions."""
    df = _toy(n_per=70, n_sess=3, seed=4)
    # a ragged 4th session shorter than the long window exercises the NaN path
    short = _toy(n_per=12, n_sess=1, seed=5)
    short["sdate"] = pd.Timestamp(2020, 2, 1)
    df = pd.concat([df, short], ignore_index=True)
    tr = V.true_range(df)
    for method, n in (("wilder", 10), ("wilder", 50), ("ema", 10), ("ema", 20)):
        got = V.intraday_atr(df, n, method, seed=V.SEED_SMA)
        a = V._alpha(n, method)
        for sd, g in df.groupby("sdate", sort=False):
            want = _wilder_loop(tr.loc[g.index].to_numpy(float), n, a)
            have = got.loc[g.index].to_numpy(float)
            ok = np.isfinite(want)
            assert np.array_equal(np.isfinite(have), ok), (method, n, sd)
            assert np.allclose(have[ok], want[ok], atol=1e-10), (method, n, sd)


def test_wilder_alpha_equals_ema_span_2n_minus_1():
    """Wilder(n) IS ewm(span=2n-1) -- they are one recursion, not two estimators."""
    df = _toy(seed=6)
    for n in (10, 25):
        w = V.intraday_atr(df, n, "wilder", seed=V.SEED_SMA)
        e = V.intraday_atr(df, 2 * n - 1, "ema", seed=V.SEED_FIRST)
        assert np.isclose(V._alpha(n, "wilder"), V._alpha(2 * n - 1, "ema"))
        # same alpha => identical once both are past their (different) warm-ups
        m = df["mfo"] >= 2 * n
        assert not np.allclose(w[m].to_numpy(), e[m].to_numpy()), n  # seeds differ
        w2 = V.intraday_atr(df, n, "wilder", seed=V.SEED_FIRST)
        assert np.allclose(w2[m].to_numpy(), e[m].to_numpy()), n


def test_seed_choice_changes_early_bars_only_in_the_documented_direction():
    """`sma` seeding must publish its first value AT bar n-1 and equal the n-bar SMA
    there; the legacy `first` seeding does not."""
    df = _toy(seed=7)
    n = 10
    tr = V.true_range(df)
    a_sma = V.intraday_atr(df, n, "wilder", seed=V.SEED_SMA)
    a_first = V.intraday_atr(df, n, "wilder", seed=V.SEED_FIRST)
    for _, g in df.groupby("sdate", sort=False):
        idx = g.index[n - 1]
        assert np.isnan(a_sma.loc[g.index[n - 2]])
        assert np.isclose(a_sma.loc[idx], tr.loc[g.index[:n]].mean())
        assert not np.isclose(a_first.loc[idx], tr.loc[g.index[:n]].mean())


def test_forward_features_causality():
    df = _toy(seed=2)
    dm = [29, 49]
    base = A.forward_features(df, dm, horizons=(10,), past_win=20)
    p = df.copy()
    p.loc[p["mfo"] > 49, ["open", "high", "low", "close"]] *= 3.0
    after = A.forward_features(p, dm, horizons=(10,), past_win=20)
    bk = base.set_index(["date", "mfo"]); ak = after.set_index(["date", "mfo"])
    # PAST columns unchanged at mfo<=49; FORWARD columns are allowed to change
    for key in bk.index:
        if key[1] <= 49:
            for col in ("past_absvar", "past_rv", "past_ret"):
                assert np.isclose(bk.loc[key, col], ak.loc[key, col]), (key, col)


def test_variance_ratio():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, 5000)
    assert abs(A.variance_ratio(noise, 5) - 1.0) < 0.15
    # positively autocorrelated (AR(1), phi>0) = trending -> VR>1
    eps = rng.normal(0, 1, 5000); ar = np.empty(5000); ar[0] = eps[0]
    for i in range(1, 5000):
        ar[i] = 0.5 * ar[i - 1] + eps[i]
    assert A.variance_ratio(ar, 5) > 1.3
    alt = np.tile([1.0, -1.0], 2500)                          # mean-reverting
    assert A.variance_ratio(alt, 2) < 0.5
