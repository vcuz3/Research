"""Tests for core.vei — the Volatility Expansion Index feature (HYP-0025/EXP-0035).

The load-bearing claim is CAUSALITY (RULES rule 7/8): VEI at a decision bar must use
only bars at or before that bar within the session. We prove it by perturbing FUTURE
bars and asserting the decision-bar VEI is unchanged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import vei as V


def _toy(n_per: int = 60, n_sess: int = 3, seed: int = 0) -> pd.DataFrame:
    """Synthetic multi-session 1-min RTH frame with the columns core.vei needs."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_sess):
        px = 100.0 + np.cumsum(rng.normal(0, 0.2, n_per))
        for i in range(n_per):
            hi = px[i] + abs(rng.normal(0, 0.1))
            lo = px[i] - abs(rng.normal(0, 0.1))
            rows.append({"sdate": pd.Timestamp(2020, 1, 1) + pd.Timedelta(days=s),
                         "mfo": i, "open": px[i], "high": hi, "low": lo,
                         "close": px[i], "et": pd.Timestamp(2020, 1, 1)
                         + pd.Timedelta(days=s, minutes=i)})
    return pd.DataFrame(rows)


def test_true_range_first_bar_is_high_low():
    df = _toy()
    tr = V.true_range(df)
    first = df.groupby("sdate").head(1).index
    hl = (df["high"] - df["low"]).loc[first]
    assert np.allclose(tr.loc[first].to_numpy(), hl.to_numpy())


def test_atr_min_periods_strict():
    df = _toy(n_per=60, n_sess=1)
    atr = V.intraday_atr(df, 50)
    # undefined for the first 49 bars of the session, defined from bar index 49
    assert atr.iloc[:49].isna().all()
    assert np.isfinite(atr.iloc[49:]).all()


def test_vei_is_causal_future_perturbation():
    """Perturbing bars AFTER a decision bar must not change VEI at that bar."""
    df = _toy(n_per=60, n_sess=2, seed=1)
    dm = [29, 49, 59]
    base = V.vei_features(df, dm, 10, 50).set_index(["date", "mfo"])["vei"]

    pert = df.copy()
    # blow up every bar strictly after mfo 49 in every session
    mask = pert["mfo"] > 49
    pert.loc[mask, ["open", "high", "low", "close"]] *= 5.0
    after = V.vei_features(pert, dm, 10, 50).set_index(["date", "mfo"])["vei"]

    for key in base.index:
        if key[1] <= 49:  # decision bars at/ before the perturbation boundary
            b, a = base[key], after[key]
            if np.isfinite(b) or np.isfinite(a):
                assert np.isclose(b, a, equal_nan=True), (key, b, a)


def test_vei_ratio_definition():
    df = _toy(n_per=80, n_sess=1, seed=2)
    atr_s = V.intraday_atr(df, 10)
    atr_l = V.intraday_atr(df, 50)
    vei = V.vei_series(df, 10, 50)
    ok = np.isfinite(atr_s) & np.isfinite(atr_l) & (atr_l > 0)
    assert np.allclose(vei[ok].to_numpy(), (atr_s[ok] / atr_l[ok]).to_numpy())


def _wilder_loop(tr: np.ndarray, n: int, alpha: float) -> np.ndarray:
    """Literal textbook recursion: seed at the first n-bar SMA, then recurse."""
    out = np.full(len(tr), np.nan)
    if len(tr) < n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(tr)):
        out[i] = (1.0 - alpha) * out[i - 1] + alpha * tr[i]
    return out


def test_wilder_seed_matches_reference_loop():
    """The closed-form seeded EWM must equal a literal per-session textbook loop.

    Covers both exponential methods and a ragged short session (fewer bars than the
    long window), where the feature must be all-NaN rather than partially seeded.
    """
    df = pd.concat([_toy(n_per=70, n_sess=2, seed=3),
                    _toy(n_per=12, n_sess=1, seed=4).assign(
                        sdate=pd.Timestamp(2021, 5, 5))], ignore_index=True)
    tr = V.true_range(df)
    for method, n in (("wilder", 10), ("wilder", 50), ("ema", 10), ("ema", 20)):
        a = V._alpha(n, method)
        got = V.intraday_atr(df, n, method, seed=V.SEED_SMA)
        for sd, g in df.groupby("sdate", sort=False):
            want = _wilder_loop(tr.loc[g.index].to_numpy(float), n, a)
            assert np.allclose(got.loc[g.index].to_numpy(float), want,
                               equal_nan=True), (method, n, sd)


def test_wilder_alpha_equals_ema_span_2n_minus_1():
    """Wilder alpha=1/n IS ewm(span=2n-1) -- 'wilder' vs 'ema' is one recursion."""
    df = _toy(n_per=80, n_sess=2, seed=5)
    n = 10
    assert np.isclose(V._alpha(n, "wilder"), V._alpha(2 * n - 1, "ema"))
    w = V.intraday_atr(df, n, "wilder", seed=V.SEED_FIRST)
    e = V.intraday_atr(df, 2 * n - 1, "ema", seed=V.SEED_FIRST)
    ok = np.isfinite(w) & np.isfinite(e)
    assert ok.sum() > 50
    assert np.allclose(w[ok].to_numpy(), e[ok].to_numpy())


def test_legacy_seed_is_reproducible_and_differs_from_repaired():
    """`seed='first'` must reproduce the pandas legacy path exactly (rule 23), and
    must actually differ from the repaired default -- otherwise EXP-0036's re-run
    would be a no-op and the repair meaningless."""
    df = _toy(n_per=70, n_sess=3, seed=6)
    n, a = 50, 1.0 / 50
    legacy = V.intraday_atr(df, n, "wilder", seed=V.SEED_FIRST)
    want = V.true_range(df).groupby(df["sdate"], sort=False).transform(
        lambda s: s.ewm(alpha=a, min_periods=n, adjust=False).mean())
    assert np.allclose(legacy.to_numpy(float), want.to_numpy(float), equal_nan=True)

    repaired = V.intraday_atr(df, n, "wilder", seed=V.SEED_SMA)
    both = np.isfinite(legacy) & np.isfinite(repaired)
    assert both.sum() > 0
    assert not np.allclose(legacy[both].to_numpy(), repaired[both].to_numpy())
    # the SMA path has no recursion to seed, so it must be seed-invariant
    for s in (V.SEED_FIRST, V.SEED_SMA):
        assert np.allclose(V.intraday_atr(df, n, "sma", seed=s).to_numpy(float),
                           V.intraday_atr(df, n, "sma").to_numpy(float),
                           equal_nan=True)


def test_vei_is_causal_under_both_seeds():
    """Causality (rule 7/8) must hold for the repaired warm-up too."""
    df = _toy(n_per=60, n_sess=2, seed=7)
    dm = [29, 49, 59]
    for s in (V.SEED_FIRST, V.SEED_SMA):
        base = V.vei_features(df, dm, 10, 50, method="wilder",
                              seed=s).set_index(["date", "mfo"])["vei"]
        pert = df.copy()
        mask = pert["mfo"] > 49
        pert.loc[mask, ["open", "high", "low", "close"]] *= 5.0
        after = V.vei_features(pert, dm, 10, 50, method="wilder",
                               seed=s).set_index(["date", "mfo"])["vei"]
        for key in base.index:
            if key[1] <= 49:
                assert np.isclose(base[key], after[key], equal_nan=True), (s, key)
