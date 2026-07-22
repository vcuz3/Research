"""Tests for the alternative band constructions in core.bands (HYP-0012).

Covers the diffusion cone's four load-bearing claims:
  1. causality  — a date's cone band uses only strictly-prior sessions;
  2. √t shape   — sigma(mfo)/sigma(M) == sqrt(mfo/M), monotone increasing;
  3. width match — at the final slot the cone equals the faithful baseline
                   (calibrated so only the intraday SHAPE differs, not width);
  4. coverage   — the cone retains (date, slot) decisions the baseline drops via
                   its per-slot min_periods rule (the Rule-9a defect).

Uses a compact synthetic frame with the minimal columns both band factories read
(sdate, mfo, et, open, close), so the tests are fast and deterministic.
"""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from futures.nq.noise_vwap.core import bands as B
from futures.nq.noise_vwap.core import session as S

LOOKBACK = 3
M = 4                     # mfos 0..4
N_DATES = 8


def build_df(drop: set[tuple[int, int]] | None = None,
             mutate: dict[tuple[int, int], float] | None = None) -> pd.DataFrame:
    """Synthetic RTH-like frame. close[d,mfo] = 100 + 0.7*d + 1.3*mfo - 0.11*d*mfo
    gives per-slot displacement that varies by date and slot (so the empirical
    per-slot band is genuinely non-constant). open at mfo 0 is the anchor."""
    drop = drop or set()
    mutate = mutate or {}
    rows = []
    for d in range(N_DATES):
        sdate = pd.Timestamp("2026-01-05") + pd.Timedelta(days=d)
        for mfo in range(M + 1):
            if (d, mfo) in drop:
                continue
            close = 100.0 + 0.7 * d + 1.3 * mfo - 0.11 * d * mfo
            close = mutate.get((d, mfo), close)
            opn = 100.0 if mfo == 0 else close - 0.2
            rows.append(dict(
                sdate=sdate, mfo=mfo,
                et=sdate + pd.Timedelta(minutes=570 + mfo),
                open=opn, high=close + 0.5, low=close - 0.5,
                close=close, volume=1000.0,
            ))
    return pd.DataFrame(rows)


class TestDiffusionCone(unittest.TestCase):
    def test_sqrt_shape_monotone(self):
        cone = B.noise_bands_cone(build_df(), LOOKBACK)
        for _, g in cone.groupby("sdate"):
            g = g.sort_values("mfo")
            sig = g.set_index("mfo")["sigma"]
            # monotone non-decreasing in mfo
            self.assertTrue((sig.diff().dropna() >= -1e-12).all())
            # exact sqrt(mfo/M) profile relative to the final slot
            ref = sig.loc[M]
            if ref > 0:
                for mfo in sig.index:
                    self.assertAlmostEqual(sig.loc[mfo] / ref,
                                           np.sqrt(mfo / M), places=9)

    def test_matches_baseline_final_slot(self):
        df = build_df()
        cone = B.noise_bands_cone(df, LOOKBACK)
        base = S.noise_bands(df, LOOKBACK)
        merged = cone.merge(base, on=["sdate", "mfo"], suffixes=("_cone", "_base"))
        fin = merged[merged["mfo"] == M]
        self.assertGreater(len(fin), 0)
        # at the last slot the cone's session-vol scalar == the baseline's
        # empirical final-slot sigma, so sigma and the derived bands coincide.
        np.testing.assert_allclose(fin["sigma_cone"], fin["sigma_base"], atol=1e-12)
        np.testing.assert_allclose(fin["upper_cone"], fin["upper_base"], atol=1e-9)
        np.testing.assert_allclose(fin["lower_cone"], fin["lower_base"], atol=1e-9)

    def test_causal(self):
        base = B.noise_bands_cone(build_df(), LOOKBACK)
        # mutate the LAST date's prices; an earlier date's band must not move.
        pert = B.noise_bands_cone(build_df(mutate={(N_DATES - 1, m): 200.0
                                                   for m in range(M + 1)}), LOOKBACK)
        early = pd.Timestamp("2026-01-05") + pd.Timedelta(days=N_DATES - 2)
        b0 = base[base["sdate"] == early].set_index("mfo")["sigma"]
        b1 = pert[pert["sdate"] == early].set_index("mfo")["sigma"]
        np.testing.assert_allclose(b0.to_numpy(), b1.reindex(b0.index).to_numpy(),
                                   atol=1e-12)

    def test_coverage_ge_baseline(self):
        # drop a single interior slot from one mid-window session. The baseline's
        # rolling(min_periods=LOOKBACK) nulls that slot for every later date whose
        # trailing window includes it; the cone (session-level scalar) keeps them.
        df = build_df(drop={(4, 2)})
        cone = B.noise_bands_cone(df, LOOKBACK)
        base = S.noise_bands(df, LOOKBACK)
        cone_keys = set(map(tuple, cone[["sdate", "mfo"]].to_numpy()))
        base_keys = set(map(tuple, base[["sdate", "mfo"]].to_numpy()))
        self.assertTrue(base_keys.issubset(cone_keys))
        self.assertGreater(len(cone_keys), len(base_keys))
        # specifically the later dates' slot-2 decisions the baseline lost
        for d in (5, 6, 7):
            key = (pd.Timestamp("2026-01-05") + pd.Timedelta(days=d), 2)
            self.assertNotIn(key, base_keys)
            self.assertIn(key, cone_keys)


class TestQuantileBand(unittest.TestCase):
    def test_same_coverage_as_baseline(self):
        # identical per-slot min_periods=lookback rule -> identical (date,mfo) keys
        df = build_df(drop={(4, 2)})
        q = B.noise_bands_quantile(df, LOOKBACK, 0.8)
        base = S.noise_bands(df, LOOKBACK)
        self.assertEqual(set(map(tuple, q[["sdate", "mfo"]].to_numpy())),
                         set(map(tuple, base[["sdate", "mfo"]].to_numpy())))

    def test_monotone_in_q(self):
        df = build_df()
        lo = B.noise_bands_quantile(df, LOOKBACK, 0.5).set_index(["sdate", "mfo"])["sigma"]
        hi = B.noise_bands_quantile(df, LOOKBACK, 0.9).set_index(["sdate", "mfo"])["sigma"]
        self.assertTrue((hi - lo.reindex(hi.index) >= -1e-12).all())

    def test_scale_is_linear(self):
        df = build_df()
        s1 = B.noise_bands_quantile(df, LOOKBACK, 0.8, scale=1.0).set_index(["sdate", "mfo"])["sigma"]
        s2 = B.noise_bands_quantile(df, LOOKBACK, 0.8, scale=2.0).set_index(["sdate", "mfo"])["sigma"]
        np.testing.assert_allclose(s2.to_numpy(), 2.0 * s1.reindex(s2.index).to_numpy(),
                                   atol=1e-12)

    def test_causal(self):
        base = B.noise_bands_quantile(build_df(), LOOKBACK, 0.8)
        pert = B.noise_bands_quantile(build_df(mutate={(N_DATES - 1, m): 200.0
                                                       for m in range(M + 1)}),
                                      LOOKBACK, 0.8)
        early = pd.Timestamp("2026-01-05") + pd.Timedelta(days=N_DATES - 2)
        b0 = base[base["sdate"] == early].set_index("mfo")["sigma"]
        b1 = pert[pert["sdate"] == early].set_index("mfo")["sigma"]
        np.testing.assert_allclose(b0.to_numpy(), b1.reindex(b0.index).to_numpy(),
                                   atol=1e-12)


class TestAsymmetricBand(unittest.TestCase):
    def test_tilt0_is_baseline_bitexact(self):
        # tilt=0 -> sigma_up == sigma_down == sigma == baseline -> identical bands.
        df = build_df()
        asym = B.noise_bands_asymmetric(df, LOOKBACK, tilt=0.0)
        base = S.noise_bands(df, LOOKBACK)
        m = asym.merge(base, on=["sdate", "mfo"], suffixes=("_a", "_b"))
        self.assertGreater(len(m), 0)
        np.testing.assert_allclose(m["sigma_a"], m["sigma_b"], atol=1e-12)
        np.testing.assert_allclose(m["upper_a"], m["upper_b"], atol=1e-12)
        np.testing.assert_allclose(m["lower_a"], m["lower_b"], atol=1e-12)

    def test_total_halfwidth_conserved(self):
        # sig_up + sig_dn == 2*sigma == 2*baseline for EVERY tilt (no width dial),
        # as long as no side is clipped at 0 (moderate tilts on this frame).
        df = build_df()
        base = S.noise_bands(df, LOOKBACK).set_index(["sdate", "mfo"])["sigma"]
        for tilt in (0.5, 1.0):
            a = B.noise_bands_asymmetric(df, LOOKBACK, tilt=tilt).set_index(["sdate", "mfo"])
            tot = a["sig_up"] + a["sig_dn"]
            np.testing.assert_allclose(tot.to_numpy(),
                                       2.0 * base.reindex(tot.index).to_numpy(),
                                       atol=1e-12)
            # sigma column itself stays the conserved baseline sigma
            np.testing.assert_allclose(a["sigma"].to_numpy(),
                                       base.reindex(a.index).to_numpy(), atol=1e-12)

    def test_same_coverage_as_baseline(self):
        df = build_df(drop={(4, 2)})
        a = B.noise_bands_asymmetric(df, LOOKBACK, tilt=1.0)
        base = S.noise_bands(df, LOOKBACK)
        self.assertEqual(set(map(tuple, a[["sdate", "mfo"]].to_numpy())),
                         set(map(tuple, base[["sdate", "mfo"]].to_numpy())))

    def test_causal(self):
        base = B.noise_bands_asymmetric(build_df(), LOOKBACK, tilt=1.0)
        pert = B.noise_bands_asymmetric(build_df(mutate={(N_DATES - 1, m): 200.0
                                                         for m in range(M + 1)}),
                                        LOOKBACK, tilt=1.0)
        early = pd.Timestamp("2026-01-05") + pd.Timedelta(days=N_DATES - 2)
        b0 = base[base["sdate"] == early].set_index("mfo")[["sig_up", "sig_dn"]]
        b1 = pert[pert["sdate"] == early].set_index("mfo")[["sig_up", "sig_dn"]]
        np.testing.assert_allclose(b0.to_numpy(), b1.reindex(b0.index).to_numpy(),
                                   atol=1e-12)


class TestSurroundBand(unittest.TestCase):
    def test_w0_is_plain_short_history(self):
        # w=0 (no surround) reduces to the baseline noise_bands at that history.
        df = build_df()
        s = B.noise_bands_surround(df, hist=LOOKBACK, w=0)
        base = S.noise_bands(df, LOOKBACK)
        m = s.merge(base, on=["sdate", "mfo"], suffixes=("_s", "_b"))
        self.assertGreater(len(m), 0)
        np.testing.assert_allclose(m["sigma_s"], m["sigma_b"], atol=1e-12)
        np.testing.assert_allclose(m["upper_s"], m["upper_b"], atol=1e-12)
        np.testing.assert_allclose(m["lower_s"], m["lower_b"], atol=1e-12)

    def test_matches_explicit_box_mean(self):
        # sigma[d,mfo] == mean over prior `hist` days AND j in [mfo-w, mfo+w] of |move|,
        # with the window edge-truncated (center included).
        df = build_df()
        hist, w = 3, 1
        s = B.noise_bands_surround(df, hist=hist, w=w).set_index(["sdate", "mfo"])["sigma"]
        cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
        o0 = df[df["mfo"] == 0].set_index("sdate")["open"]
        move = (cm.div(o0, axis=0) - 1.0).abs()
        dates = sorted(df["sdate"].unique())
        for di in range(hist, len(dates)):          # first `hist` days undefined
            d = dates[di]
            for mfo in range(M + 1):
                lo, hi = max(0, mfo - w), min(M, mfo + w)
                vals = [move.loc[dates[p], j]
                        for p in range(di - hist, di) for j in range(lo, hi + 1)]
                self.assertAlmostEqual(s.loc[(d, mfo)], float(np.mean(vals)), places=12)

    def test_open_uses_forward_only(self):
        # at mfo==0 the truncated window is [0, w]: center + forward candles only.
        df = build_df()
        hist, w = 3, 2
        s = B.noise_bands_surround(df, hist=hist, w=w).set_index(["sdate", "mfo"])["sigma"]
        cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
        o0 = df[df["mfo"] == 0].set_index("sdate")["open"]
        move = (cm.div(o0, axis=0) - 1.0).abs()
        dates = sorted(df["sdate"].unique())
        di = hist + 1
        d = dates[di]
        vals = [move.loc[dates[p], j]
                for p in range(di - hist, di) for j in range(0, w + 1)]
        self.assertAlmostEqual(s.loc[(d, 0)], float(np.mean(vals)), places=12)

    def test_causal(self):
        base = B.noise_bands_surround(build_df(), hist=3, w=2)
        pert = B.noise_bands_surround(build_df(mutate={(N_DATES - 1, m): 200.0
                                                       for m in range(M + 1)}),
                                      hist=3, w=2)
        early = pd.Timestamp("2026-01-05") + pd.Timedelta(days=N_DATES - 2)
        b0 = base[base["sdate"] == early].set_index("mfo")["sigma"]
        b1 = pert[pert["sdate"] == early].set_index("mfo")["sigma"]
        np.testing.assert_allclose(b0.to_numpy(), b1.reindex(b0.index).to_numpy(),
                                   atol=1e-12)


class TestLaplaceBand(unittest.TestCase):
    def test_binf_is_flat_baseline_bitexact(self):
        # b -> inf gives uniform weights over 1..lookback == the flat mean band.
        df = build_df()
        lap = B.noise_bands_laplace(df, mu=1, b=np.inf, lookback=LOOKBACK)
        base = S.noise_bands(df, LOOKBACK)
        m = lap.merge(base, on=["sdate", "mfo"], suffixes=("_l", "_b"))
        self.assertGreater(len(m), 0)
        np.testing.assert_allclose(m["sigma_l"], m["sigma_b"], atol=1e-12)
        np.testing.assert_allclose(m["upper_l"], m["upper_b"], atol=1e-12)
        np.testing.assert_allclose(m["lower_l"], m["lower_b"], atol=1e-12)

    def test_matches_explicit_weighted_mean(self):
        # sigma[d,mfo] == weighted mean over prior `lookback` days of |move|,
        # weights w_k = exp(-|k-mu|/b), k=1 the most recent prior session.
        df = build_df()
        mu, b = 2.0, 3.0
        lap = B.noise_bands_laplace(df, mu=mu, b=b, lookback=LOOKBACK
                                    ).set_index(["sdate", "mfo"])["sigma"]
        cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
        o0 = df[df["mfo"] == 0].set_index("sdate")["open"]
        move = (cm.div(o0, axis=0) - 1.0).abs()
        w = np.exp(-np.abs(np.arange(1, LOOKBACK + 1) - mu) / b)
        dates = sorted(df["sdate"].unique())
        for di in range(LOOKBACK, len(dates)):          # first `lookback` days undefined
            d = dates[di]
            for mfo in range(M + 1):
                vals = np.array([move.loc[dates[di - k], mfo] for k in range(1, LOOKBACK + 1)])
                self.assertAlmostEqual(lap.loc[(d, mfo)],
                                       float((w * vals).sum() / w.sum()), places=12)

    def test_scale_is_linear(self):
        df = build_df()
        s1 = B.noise_bands_laplace(df, 1, 5.0, LOOKBACK, scale=1.0).set_index(["sdate", "mfo"])["sigma"]
        s2 = B.noise_bands_laplace(df, 1, 5.0, LOOKBACK, scale=2.0).set_index(["sdate", "mfo"])["sigma"]
        np.testing.assert_allclose(s2.to_numpy(), 2.0 * s1.reindex(s2.index).to_numpy(),
                                   atol=1e-12)

    def test_same_coverage_as_baseline(self):
        # strict min_periods=lookback (NaN propagation) -> identical (date,mfo) keys.
        df = build_df(drop={(4, 2)})
        lap = B.noise_bands_laplace(df, mu=1, b=2.0, lookback=LOOKBACK)
        base = S.noise_bands(df, LOOKBACK)
        self.assertEqual(set(map(tuple, lap[["sdate", "mfo"]].to_numpy())),
                         set(map(tuple, base[["sdate", "mfo"]].to_numpy())))

    def test_recency_tilt_weights_latest_more(self):
        # a small b puts more weight on k=1 than a mid-lag; check the kernel shape.
        w = B.laplace_weights(mu=1, b=2.0, lookback=10)
        self.assertTrue((np.diff(w) < 0).all())          # monotone decreasing from k=1
        wflat = B.laplace_weights(mu=1, b=np.inf, lookback=10)
        np.testing.assert_allclose(wflat, np.ones(10), atol=1e-12)

    def test_causal(self):
        base = B.noise_bands_laplace(build_df(), mu=2, b=3.0, lookback=LOOKBACK)
        pert = B.noise_bands_laplace(build_df(mutate={(N_DATES - 1, m): 200.0
                                                      for m in range(M + 1)}),
                                     mu=2, b=3.0, lookback=LOOKBACK)
        early = pd.Timestamp("2026-01-05") + pd.Timedelta(days=N_DATES - 2)
        b0 = base[base["sdate"] == early].set_index("mfo")["sigma"]
        b1 = pert[pert["sdate"] == early].set_index("mfo")["sigma"]
        np.testing.assert_allclose(b0.to_numpy(), b1.reindex(b0.index).to_numpy(),
                                   atol=1e-12)


if __name__ == "__main__":
    unittest.main()
