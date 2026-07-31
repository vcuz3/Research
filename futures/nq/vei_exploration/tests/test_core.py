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


def test_opening_tr_ratio_is_causal_and_matches_definition():
    df = _toy(n_per=70, n_sess=3, seed=8)
    tr = V.true_range(df)
    got = A.opening_tr_ratio(df, tr, windows=(5, 10, 50)).set_index("date")
    for sd, g in df.groupby("sdate", sort=False):
        tg = tr.loc[g.index].to_numpy(float)
        for n in (5, 10, 50):
            assert np.isclose(got.loc[sd, f"open_rel_{n}"], tg[0] / tg[:n].mean())

    # Anything after the opening window cannot change the feature.
    p = df.copy()
    p.loc[p["mfo"] >= 50, ["open", "high", "low", "close"]] *= 7.0
    after = A.opening_tr_ratio(p, V.true_range(p), windows=(5, 10, 50)).set_index("date")
    assert np.allclose(got[["open_rel_5", "open_rel_10", "open_rel_50"]],
                       after[["open_rel_5", "open_rel_10", "open_rel_50"]])


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


def test_partial_spearman_removes_the_conditioning_variable():
    """Three load-bearing properties of the 0b selection metric.

    1. If x is a monotone function of z ALONE, x adds nothing about y once z is
       partialled out -- even when its raw IC vs y is large. This is exactly the
       degenerate case the metric exists to catch: a VEI whose denominator is so slow
       that the ratio is just a rescaled level.
    2. A genuinely independent contribution survives partialling.
    3. Partialling out something unrelated leaves the plain Spearman ~unchanged.
    """
    rng = np.random.default_rng(11)
    n = 4000
    z = rng.normal(0, 1, n)
    y = z + rng.normal(0, 0.5, n)

    # 1. x is a monotone transform of z => raw IC is high, partial IC ~ 0
    x_deg = np.exp(0.7 * z)
    assert A.spearman(x_deg, y) > 0.7
    assert abs(A.partial_spearman(x_deg, y, z)) < 0.05

    # 2. x carries its own information about y beyond z
    own = rng.normal(0, 1, n)
    y2 = z + own + rng.normal(0, 0.3, n)
    x_own = own + 0.3 * z
    assert A.partial_spearman(x_own, y2, z) > 0.5

    # 3. partialling an irrelevant variable barely moves the estimate
    junk = rng.normal(0, 1, n)
    assert abs(A.partial_spearman(x_own, y2, junk) - A.spearman(x_own, y2)) < 0.05


def test_partial_spearman_matches_manual_rank_residual_correlation():
    rng = np.random.default_rng(12)
    n = 500
    z = rng.normal(0, 1, n)
    x = 0.6 * z + rng.normal(0, 1, n)
    y = 0.4 * z + 0.5 * x + rng.normal(0, 1, n)
    rx, ry, rz = (pd.Series(v).rank().to_numpy(float) for v in (x, y, z))
    X = np.c_[np.ones(n), rz]
    ex = rx - X @ np.linalg.lstsq(X, rx, rcond=None)[0]
    ey = ry - X @ np.linalg.lstsq(X, ry, rcond=None)[0]
    want = float(np.corrcoef(ex, ey)[0, 1])
    assert np.isclose(A.partial_spearman(x, y, z), want, atol=1e-10)


def _slot_frame(n_sess=200, slots=(29, 59, 89), seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_sess):
        for s in slots:
            # a deliberate per-slot LEVEL shift, which is exactly what the
            # normalisation is supposed to remove
            rows.append({"date": pd.Timestamp(2020, 1, 1) + pd.Timedelta(days=d),
                         "mfo": s, "v": s / 30.0 + rng.normal(0, 0.1)})
    return pd.DataFrame(rows)


def test_causal_slot_stats_is_causal_and_matches_definition():
    df = _slot_frame()
    mu, sd = A.causal_slot_stats(df, "v", lookback=90, min_obs=60)

    # matches a literal trailing-window computation, per slot, strictly prior
    for _, g in df.groupby("mfo", sort=False):
        g = g.sort_values("date")
        v = g["v"].to_numpy(float)
        for i in range(len(v)):
            w = v[max(0, i - 90):i]
            if len(w) >= 60:
                assert np.isclose(mu.loc[g.index[i]], w.mean())
                assert np.isclose(sd.loc[g.index[i]], w.std(ddof=1))
            else:
                assert np.isnan(mu.loc[g.index[i]])

    # CAUSALITY: perturbing later sessions cannot change an earlier session's stats
    cut = df["date"] > pd.Timestamp(2020, 1, 1) + pd.Timedelta(days=150)
    pert = df.copy()
    pert.loc[cut, "v"] *= 9.0
    mu2, sd2 = A.causal_slot_stats(pert, "v", lookback=90, min_obs=60)
    keep = ~cut.to_numpy()
    assert np.allclose(mu[keep].to_numpy(), mu2[keep].to_numpy(), equal_nan=True)
    assert np.allclose(sd[keep].to_numpy(), sd2[keep].to_numpy(), equal_nan=True)


def test_slot_normalisation_removes_a_per_slot_level_shift():
    """At a fixed global threshold, a per-slot LEVEL shift makes the RAW feature a
    slot selector. Dividing by the trailing same-slot mean removes the location shift
    but NOT a per-slot scale difference, so `rel` improves calibration without
    perfecting it; the z-score removes both and is near-uniform.

    This separation is the reason both variants are carried into the study: `rel`
    preserves the natural "1.0 = normal for this time of day" reading, `z` is better
    calibrated. Which one to prefer is an empirical question about whether VEI's
    per-slot dispersion is proportional to its per-slot level.
    """
    df = _slot_frame(n_sess=400, seed=1)
    mu, sd = A.causal_slot_stats(df, "v", lookback=90, min_obs=60)
    d = df.assign(rel=df["v"] / mu, z=(df["v"] - mu) / sd).dropna(subset=["rel", "z"])

    def spread(col):
        thr = d[col].quantile(0.80)
        share = d.assign(hi=d[col] >= thr).groupby("mfo")["hi"].mean()
        return float(share.max() - share.min())

    raw, rel, z = spread("v"), spread("rel"), spread("z")
    assert raw > 0.5             # raw: the threshold is a TIME-OF-DAY selector
    assert rel < 0.5 * raw       # location removed
    assert z < 0.05              # location AND scale removed -> near-uniform
    assert z < rel


def test_first_session_upcross_is_first_only_and_requires_observed_transition():
    df = pd.DataFrame({
        "date": [pd.Timestamp("2020-01-01")] * 6 + [pd.Timestamp("2020-01-02")] * 3,
        "mfo": [49, 54, 59, 64, 69, 74, 49, 54, 59],
        "z": [1.6, 1.7, 0.2, 1.5, 0.1, 2.0, 0.1, 1.5, 1.8],
    })
    got = A.first_session_upcross(df, "z", 1.5)
    # Session 1 starts high (not an observed onset); only its later first crossing
    # counts despite a second crossing. Session 2 has one ordinary crossing.
    assert got.tolist() == [False, False, False, True, False, False,
                            False, True, False]

    # Perturbing later readings cannot change an already observed onset.
    pert = df.copy()
    pert.loc[pert["mfo"] >= 69, "z"] = 99.0
    got2 = A.first_session_upcross(pert, "z", 1.5)
    assert got2.iloc[:4].equals(got.iloc[:4])
