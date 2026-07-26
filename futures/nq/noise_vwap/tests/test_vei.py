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
