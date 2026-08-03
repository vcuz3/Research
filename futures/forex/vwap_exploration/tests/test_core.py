"""Executable invariants for the FX-futures VWAP exploration core.

Run:  python -m futures.forex.vwap_exploration.tests.test_core
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import stats as S
from futures.forex.vwap_exploration.core import vwap as V

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def _toy(n_sessions=8, n_bars=30, seed=0):
    """A small synthetic bar frame with the same columns the loader produces."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_sessions):
        sd = pd.Timestamp("2015-01-05") + pd.Timedelta(days=s)
        px = 1.20 + 0.001 * s
        for m in range(n_bars):
            px = px + rng.normal(0, 2e-4)
            hi, lo = px + 1e-4, px - 1e-4
            rows.append({"sdate": sd, "mfo": m, "open": px, "high": hi,
                         "low": lo, "close": px,
                         "volume": float(rng.integers(1, 100))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# session geometry
# --------------------------------------------------------------------------- #
@check("session columns map 18:00 ET to mfo 0 and 16:59 ET to mfo 1379")
def t_session_map():
    ts = pd.to_datetime(["2015-06-01 22:00", "2015-06-02 20:59", "2015-06-02 04:00"],
                        utc=True)  # ET: 18:00 Mon, 16:59 Tue, 00:00 Tue
    out = D.add_session_columns(pd.DataFrame({"ts_event": ts}))
    assert list(out["mfo"]) == [0, 1379, 360], list(out["mfo"])
    assert list(out["sdate"].dt.date.astype(str)) == ["2015-06-02"] * 3, out["sdate"]


@check("blocks partition the session with no gaps or overlaps")
def t_blocks():
    mods = np.arange(1440)
    lab = D.block_of_mod(mods)
    assert set(lab) == {"asia", "ldn_am", "overlap", "ny_pm"}
    # the halt minutes are labelled but never loaded; every other minute has one label
    assert D.block_of_mod(np.array([D.FIX_MOD]))[0] == "overlap"
    assert D.block_of_mod(np.array([18 * 60]))[0] == "asia"
    assert D.block_of_mod(np.array([2 * 60 + 59]))[0] == "asia"
    assert D.block_of_mod(np.array([3 * 60]))[0] == "ldn_am"


@check("6E tick size halves in 2016 and 6B never changes")
def t_ticks():
    assert D.tick_size("6E", 2015) == 1e-4
    assert D.tick_size("6E", 2016) == 5e-5
    assert D.tick_size("6B", 2010) == D.tick_size("6B", 2023) == 1e-4


# --------------------------------------------------------------------------- #
# anchors
# --------------------------------------------------------------------------- #
@check("TWAP is exactly VWAP evaluated at constant volume")
def t_twap_is_degenerate_vwap():
    b = _toy()
    flat = b.copy()
    flat["volume"] = 7.0
    a_flat = V.add_anchors(flat)
    a_real = V.add_anchors(b)
    assert np.allclose(a_flat["vwap"], a_flat["twap"], atol=1e-12)
    # ... and NOT equal once the weights actually vary
    assert not np.allclose(a_real["vwap"], a_real["twap"], atol=1e-9)


@check("VWAP/TWAP are causal: recomputing on a truncated session is unchanged")
def t_causal():
    b = _toy()
    full = V.add_anchors(b)
    cut = V.add_anchors(b[b["mfo"] <= 12].copy())
    m = full["mfo"] <= 12
    assert np.allclose(full.loc[m, "vwap"].to_numpy(), cut["vwap"].to_numpy())
    assert np.allclose(full.loc[m, "twap"].to_numpy(), cut["twap"].to_numpy())


@check("anchors reset at the session boundary (first bar VWAP == its typical price)")
def t_reset():
    b = _toy()
    a = V.add_anchors(b)
    first = a[a["mfo"] == 0]
    tp = (first["high"] + first["low"] + first["close"]) / 3.0
    assert np.allclose(first["vwap"], tp)
    assert np.allclose(first["twap"], tp)
    assert np.allclose(first["open_anchor"], first["open"])


@check("pclose is the PRIOR session's last close and is NaN on the first session")
def t_pclose():
    b = _toy()
    a = V.add_anchors(b)
    lasts = b.groupby("sdate")["close"].last()
    sds = sorted(b["sdate"].unique())
    assert a.loc[a["sdate"] == sds[0], "pclose"].isna().all()
    got = a.loc[a["sdate"] == sds[3], "pclose"].unique()
    assert len(got) == 1 and np.isclose(got[0], lasts.loc[sds[2]])


@check("causal_slot_scale uses only strictly prior sessions")
def t_slot_scale_causal():
    b = _toy(n_sessions=12, n_bars=5)
    b["dev_x"] = np.arange(len(b), dtype=float)
    sc = V.causal_slot_scale(b, "dev_x", lookback=3, min_frac=1.0)
    b2 = b.copy()
    # corrupting the LAST session must not change any earlier scale
    last = b2["sdate"] == b2["sdate"].max()
    b2.loc[last, "dev_x"] = 1e9
    sc2 = V.causal_slot_scale(b2, "dev_x", lookback=3, min_frac=1.0)
    assert np.allclose(sc[~last.to_numpy()], sc2[~last.to_numpy()], equal_nan=True)
    # first `lookback` sessions have no full window
    assert np.isnan(sc[:3 * 5]).all()


@check("dev_z removes the mechanical intraday growth of |close - vwap|")
def t_dev_z_calibration():
    rng = np.random.default_rng(3)
    rows = []
    for s in range(200):
        sd = pd.Timestamp("2015-01-05") + pd.Timedelta(days=s)
        px = 1.2
        for m in range(60):
            px += rng.normal(0, 1e-4)
            rows.append({"sdate": sd, "mfo": m, "open": px, "high": px, "low": px,
                         "close": px, "volume": 10.0})
    b = V.add_deviations(V.add_anchors(pd.DataFrame(rows)), anchors=("vwap",),
                         lookback=60)
    b = b[np.isfinite(b["dev_vwap_z"])]
    late = b[b["mfo"] >= 45]["dev_vwap_pip"].abs().mean()
    early = b[b["mfo"] <= 10]["dev_vwap_pip"].abs().mean()
    assert late / early > 2.0, (early, late)          # raw grows through the session
    lz = b[b["mfo"] >= 45]["dev_vwap_z"].abs().mean()
    ez = b[b["mfo"] <= 10]["dev_vwap_z"].abs().mean()
    assert 0.8 < lz / ez < 1.25, (ez, lz)             # z-scored does not


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
@check("cluster_t reduces to the iid t when every block has one observation")
def t_cluster_iid():
    rng = np.random.default_rng(1)
    x = rng.normal(0.1, 1.0, 500)
    m, se, t, n = S.cluster_t(x, np.arange(500))
    iid_se = x.std(ddof=0) / np.sqrt(500)
    assert np.isclose(se, iid_se, rtol=1e-6), (se, iid_se)


@check("cluster_t inflates the SE when observations are perfectly block-correlated")
def t_cluster_dependence():
    rng = np.random.default_rng(2)
    blocks = np.repeat(np.arange(100), 10)
    x = np.repeat(rng.normal(0.0, 1.0, 100), 10)     # identical within a block
    _, se_c, _, _ = S.cluster_t(x, blocks)
    _, se_i, _, _ = S.cluster_t(x, np.arange(1000))
    assert se_c / se_i > 2.5, (se_c, se_i)


@check("mean_count_corr detects an endogenous block count and is ~0 when there is none")
def t_mean_count():
    rng = np.random.default_rng(4)
    xs, bs = [], []
    for b in range(300):
        k = rng.integers(2, 40)
        xs.append(rng.normal(0.05 * k, 1.0, k))       # mean grows with count
        bs.append(np.full(k, b))
    assert S.mean_count_corr(np.concatenate(xs), np.concatenate(bs)) > 0.5
    xs, bs = [], []
    for b in range(300):
        k = rng.integers(2, 40)
        xs.append(rng.normal(0.0, 1.0, k))
        bs.append(np.full(k, b))
    assert abs(S.mean_count_corr(np.concatenate(xs), np.concatenate(bs))) < 0.2


@check("rank IC and mean spread can disagree: a tail-only effect is invisible to rank")
def t_rank_vs_mean():
    rng = np.random.default_rng(5)
    n = 20000
    x = rng.normal(size=n)
    y = rng.normal(size=n)
    tail = x > 2.5
    y[tail] += 6.0                                    # payoff only in the far tail
    assert abs(S.spearman(x, y)) < 0.03
    spread, _ = S.quantile_spread(x, y, 5)
    assert spread > 0.15, spread


@check("partial_spearman removes the conditioning variable")
def t_partial():
    rng = np.random.default_rng(6)
    z = rng.normal(size=5000)
    x = z + 0.3 * rng.normal(size=5000)
    y = z + 0.3 * rng.normal(size=5000)
    assert S.spearman(x, y) > 0.7
    assert abs(S.partial_spearman(x, y, z)) < 0.1


@check("RSI is EXACTLY 50 + 50*Wilder(dp)/Wilder(|dp|) -- the up/down form is the same thing")
def t_rsi_identity():
    from futures.forex.vwap_exploration.core import rsi as R
    rng = np.random.default_rng(21)
    n_s, n_b = 12, 46
    rows = []
    for s in range(n_s):
        sd = pd.Timestamp("2015-01-05") + pd.Timedelta(days=s)
        px = 1.20
        for j in range(n_b):
            px += rng.normal(0, 2e-4)
            rows.append({"sdate": sd, "mfo": 29 + 30 * j, "close": px})
    pan = pd.DataFrame(rows)
    fr = R.rsi_frame(pan, 14)
    textbook = R.rsi_from_updown(pan, 14)
    a, b = fr["rsi_14"].to_numpy(), textbook
    m = np.isfinite(a) & np.isfinite(b)
    assert m.sum() > 300, m.sum()
    assert np.nanmax(np.abs(a[m] - b[m])) < 1e-9, np.nanmax(np.abs(a[m] - b[m]))
    # bounded, and 50 exactly when the smoothed return is zero
    assert np.nanmin(a) >= 0.0 and np.nanmax(a) <= 100.0
    assert np.isclose(50 + 50 * fr["rsi_num_14"].to_numpy()[m][0]
                      / fr["rsi_den_14"].to_numpy()[m][0], a[m][0])


@check("wilder_rma seeds with the n-bar SMA, which pandas ewm(adjust=False) does NOT")
def t_wilder_seed():
    from futures.forex.vwap_exploration.core import rsi as R
    rng = np.random.default_rng(22)
    v = rng.normal(5.0, 1.0, 400)
    got = R.wilder_rma(v, 14)
    assert np.isnan(got[:13]).all() and np.isfinite(got[13])
    assert np.isclose(got[13], v[:14].mean())                 # textbook SMA seed
    assert np.isclose(got[14], got[13] + (v[14] - got[13]) / 14)
    # the ewm shortcut this workspace has been bitten by is materially different
    ewm = pd.Series(v).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean().to_numpy()
    assert abs(ewm[13] - got[13]) > 1e-6, (ewm[13], got[13])
    # ... and a monotone ramp exposes the direction of the bias
    ramp = np.arange(100.0)
    assert R.wilder_rma(ramp, 14)[13] == ramp[:14].mean()


@check("RSI is causal and resets only where the retained session sequence BREAKS")
def t_rsi_causal_resets():
    from futures.forex.vwap_exploration.core import rsi as R
    days = [pd.Timestamp("2015-01-05") + pd.Timedelta(days=k)
            for k in (0, 1, 2, 3, 4, 7, 8, 30, 31)]      # a hole before 30
    brk = R.run_breaks(np.repeat(np.array(days, dtype="datetime64[ns]"), 3))
    starts = np.flatnonzero(brk)
    assert starts.tolist() == [0, 21], starts.tolist()    # first row and after the hole
    # weekends (Fri->Mon) must NOT reset
    assert not brk[3 * 4 + 1] and not brk[3 * 5]
    # causality: truncating the tail cannot change earlier values
    rows = []
    rng = np.random.default_rng(23)
    for s in range(10):
        sd = pd.Timestamp("2015-01-05") + pd.Timedelta(days=s)
        px = 1.2
        for j in range(46):
            px += rng.normal(0, 2e-4)
            rows.append({"sdate": sd, "mfo": 29 + 30 * j, "close": px})
    pan = pd.DataFrame(rows)
    full = R.rsi_frame(pan, 14)["rsi_14"].to_numpy()
    trunc = R.rsi_frame(pan.iloc[:300].copy(), 14)["rsi_14"].to_numpy()
    m = np.isfinite(trunc)
    assert np.allclose(full[:300][m], trunc[m], equal_nan=True)


@check("a single missing bar costs 1 decision under 'bridge' but n+1 under 'reset'")
def t_rsi_gap_policy():
    """The recursive-feature version of finding G: under `reset` the deletion lands
    n decisions AFTER the gap, so per-block gap counts do not predict coverage."""
    from futures.forex.vwap_exploration.core import rsi as R
    rng = np.random.default_rng(24)
    rows, px = [], 1.20
    for s in range(6):
        sd = pd.Timestamp("2015-01-05") + pd.Timedelta(days=s)
        for j in range(46):
            px += rng.normal(0, 2e-4)
            rows.append({"sdate": sd, "mfo": 29 + 30 * j, "close": px})
    pan = pd.DataFrame(rows)
    base = R.rsi_frame(pan, 14, gap_policy="bridge")["rsi_14"].to_numpy()
    holed = pan.copy()
    hole = 120
    holed.loc[hole, "close"] = np.nan
    br = R.rsi_frame(holed, 14, gap_policy="bridge")["rsi_14"].to_numpy()
    rs = R.rsi_frame(holed, 14, gap_policy="reset")["rsi_14"].to_numpy()
    lost_br = int(np.isfinite(base).sum() - np.isfinite(br).sum())
    lost_rs = int(np.isfinite(base).sum() - np.isfinite(rs).sum())
    assert lost_br == 1, lost_br                    # only the gap itself
    assert lost_rs >= 14, lost_rs                   # the gap plus a full rebuild
    # and the reset damage is DISPLACED: rows well after the hole are the casualties
    dead = np.flatnonzero(~np.isfinite(rs) & np.isfinite(base))
    assert dead.min() == hole and dead.max() >= hole + 13, (dead.min(), dead.max())


@check("6J's reporting unit is worth the same dollars as 6E's, and its tick halved in 2015")
def t_6j_units():
    # The unit exists so cross-product magnitudes are comparable in DOLLARS.
    for prod in ("6E", "6J"):
        assert np.isclose(D.CONTRACT[prod]["notional"] * D.pip_size(prod), 12.50), prod
    assert np.isclose(D.CONTRACT["6B"]["notional"] * D.pip_size("6B"), 6.25)
    # 6E/6B units are UNCHANGED by the 6J addition -- prior runs must reproduce.
    assert D.pip_size("6E") == D.pip_size("6B") == D.PIP == 1e-4
    assert D.pip_size("6J") == 1e-6
    # one pre-2015 6J tick is exactly one reporting unit; it halves thereafter
    assert D.tick_size("6J", 2014) == D.pip_size("6J")
    assert D.tick_size("6J", 2015) == D.tick_size("6J", 2023) == 5e-7
    # a tick is worth $6.25 on every product in its fine-tick era
    for prod, yr in (("6E", 2020), ("6B", 2020), ("6J", 2020)):
        usd = D.tick_size(prod, yr) / D.pip_size(prod) * D.usd_per_pip(prod)
        assert np.isclose(usd, 6.25), (prod, usd)


@check("stratified_contrast kills a PURE confound: raw contrast large, adjusted ~0")
def t_strat_confound():
    """The 2026-07-31c scenario. `group` has NO effect within a stratum; the two
    groups merely sit at different points of the confounder's distribution."""
    rng = np.random.default_rng(11)
    n = 40000
    v = rng.uniform(0, 1, n)                       # the confounder
    # group A concentrates at low v, group B at high v -- exactly what `asia` vs
    # `overlap` looks like against absolute volatility
    p = np.clip(1.0 - v, 0.05, 0.95)
    grp = np.where(rng.uniform(size=n) < p, "A", "B")
    pnl = 4.0 * (1.0 - v) + rng.normal(0, 0.5, n)  # driven ONLY by the confounder
    bins, _ = S.quantile_bins(v, 5)
    out = S.stratified_contrast(pnl, grp, bins, "A", "B", cov=v)
    assert out["raw"] > 1.0, out["raw"]            # looks like a big group effect
    assert abs(out["adj"]) < 0.10 * out["raw"], (out["adj"], out["raw"])
    # the control must be shown to have worked, not merely weakened the split
    assert out["cov_ratio_raw"] < 0.75, out["cov_ratio_raw"]
    assert abs(out["cov_ratio_adj"] - 1.0) < 0.10, out["cov_ratio_adj"]
    assert out["retention"] > 0.5, out["retention"]
    # residual within-bin confounding must fall monotonically as strata refine --
    # a stratified estimate that does NOT do this is not removing a confounder
    prev = abs(out["adj"])
    for nb in (10, 20):
        bq, _ = S.quantile_bins(v, nb)
        o = S.stratified_contrast(pnl, grp, bq, "A", "B", cov=v)
        assert abs(o["adj"]) < prev, (nb, o["adj"], prev)
        prev = abs(o["adj"])


@check("stratified_contrast PRESERVES a real group effect that is constant in strata")
def t_strat_real():
    rng = np.random.default_rng(12)
    n = 40000
    v = rng.uniform(0, 1, n)
    p = np.clip(1.0 - v, 0.05, 0.95)
    grp = np.where(rng.uniform(size=n) < p, "A", "B")
    pnl = (4.0 * (1.0 - v) + np.where(grp == "A", 1.0, 0.0)
           + rng.normal(0, 0.5, n))               # a genuine +1.0 group effect
    bins, _ = S.quantile_bins(v, 5)
    out = S.stratified_contrast(pnl, grp, bins, "A", "B", cov=v)
    assert abs(out["adj"] - 1.0) < 0.20, out["adj"]
    assert out["adj"] < out["raw"], (out["adj"], out["raw"])   # confound removed too


@check("stratified_contrast weights only common support and reports the shortfall")
def t_strat_support():
    """Disjoint confounder distributions => no common support => n_eff collapses,
    which is how a 'merely weakened split' is told apart from a removed confound."""
    v = np.r_[np.zeros(2000), np.ones(2000)]
    grp = np.r_[np.full(2000, "A"), np.full(2000, "B")]   # perfectly separated
    pnl = np.r_[np.ones(2000), np.zeros(2000)]
    bins, _ = S.quantile_bins(v, 2)
    out = S.stratified_contrast(pnl, grp, bins, "A", "B", cov=v)
    assert np.isnan(out["adj"]), out["adj"]
    assert out["n_eff"] == 0.0 and out["retention"] == 0.0
    # and with proportional support the effective count is the pooled harmonic one
    rng = np.random.default_rng(13)
    v2 = rng.uniform(0, 1, 4000)
    grp2 = np.where(rng.uniform(size=4000) < 0.5, "A", "B")
    bins2, _ = S.quantile_bins(v2, 4)
    out2 = S.stratified_contrast(np.zeros(4000), grp2, bins2, "A", "B", cov=v2)
    assert 0.9 < out2["retention"] <= 1.0, out2["retention"]


@check("quantile_bins reuses supplied edges so a bootstrap resamples data, not bins")
def t_quantile_bins_edges():
    rng = np.random.default_rng(14)
    x = rng.normal(size=5000)
    b1, edges = S.quantile_bins(x, 5)
    assert set(np.unique(b1)) == {0, 1, 2, 3, 4}
    counts = np.bincount(b1, minlength=5)
    assert counts.max() - counts.min() <= 2, counts
    sub = x[:100]
    b2, _ = S.quantile_bins(sub, 5, edges=edges)
    b3, _ = S.quantile_bins(sub, 5)
    assert not np.array_equal(b2, b3)             # refitting the bins is different
    assert np.array_equal(b2, b1[:100])           # supplied edges reproduce exactly
    x_nan = np.r_[x[:10], np.nan]
    b4, _ = S.quantile_bins(x_nan, 5, edges=edges)
    assert b4[-1] == -1


@check("realized_vol windows are causal and exclude the lagged window's overlap")
def t_realized_vol_windows():
    """Pins the two window slices against a hand-computed series (the off-by-one
    in `diff` indexing is the whole risk here)."""
    from futures.forex.vwap_exploration.core import vol as VOL
    # close(k) = k  =>  every one-minute change is exactly 1.0 price unit
    absd = np.abs(np.diff(np.arange(200.0)[None, :], axis=1))
    got = VOL._window_mean(absd, 100 - 60, 100, 0.5)
    assert np.isclose(got[0], 1.0), got
    # a ramp whose per-minute change is the minute index: mean over (m-w, m]
    close = np.cumsum(np.arange(200.0))[None, :]
    absd = np.abs(np.diff(close, axis=1))
    m, w, lag = 120, 60, 30
    assert np.isclose(VOL._window_mean(absd, m - w, m, 0.5)[0],
                      np.arange(m - w + 1, m + 1).mean())
    assert np.isclose(VOL._window_mean(absd, m - w - lag, m - lag, 0.5)[0],
                      np.arange(m - w - lag + 1, m - lag + 1).mean())
    # the lagged window must not touch any minute used by past_30 = close(m)-close(m-30)
    assert (m - lag) <= (m - 30)
    # under-populated windows return NaN rather than a partial mean
    holed = absd.copy()
    holed[0, m - w:m - 10] = np.nan
    assert np.isnan(VOL._window_mean(holed, m - w, m, 0.5)[0])


@check("block_bootstrap resamples whole sessions")
def t_bootstrap():
    rng = np.random.default_rng(7)
    df = pd.DataFrame({"sdate": np.repeat(np.arange(50), 20),
                       "x": rng.normal(size=1000)})
    out = S.block_bootstrap(df, ["x"], lambda a: float(np.mean(a)), rng, nboot=200)
    assert out.size == 200 and np.isfinite(out).all()
    lo, hi = S.ci(out)
    assert lo < np.mean(df["x"]) < hi


def main():
    fails = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:                        # noqa: BLE001
            fails += 1
            print(f"  FAIL  {name}\n          {type(exc).__name__}: {exc}")
    print(f"\n{len(CHECKS) - fails}/{len(CHECKS)} checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
