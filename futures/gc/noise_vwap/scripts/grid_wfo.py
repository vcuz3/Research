"""
Grid + WFO + holdout study for the GC Noise-Area + VWAP momentum strategy.

Axes (2 x 5 x 5 = 50 cells):
  * VWAP anchor  : rth (reset 09:30)  |  eth (reset 18:00 Globex, overnight-inclusive)
  * band vol mult: k in {0.5, 1.0, 1.25, 1.5, 2.0}   (band = ref*(1 +/- k*sigma))
  * noise lookbk : lb in {5, 14, 30, 60, 90} sessions

Exit clock = decision (baseline-faithful): the max(band,vwap)/min(band,vwap) stop is
checked only on the 30-min Concretum clock, exactly like the frozen baseline. Fills
next-open, require_vwap gate ON, stop_ref both -- all baseline. The ONLY things the
grid varies are the three axes above (single-family search), run through the audited
numba engine (core.engine2_nb, bit-exact vs core.engine).

Scoring is ERA-NEUTRAL: gold ran ~1200->3300 over 2011-2026, so raw points inflate
the recent era (NQ WFO lesson -- score in normalized units, not points). Primary
metric = annualized daily Sharpe on per-trade NET RETURN (net_pts / entry_px), summed
per session over a COMMON date set (all cells share the lb=90 warmup). Tradable units
(net pt/trade, day$net) are reported alongside (rule 19/21).

Selection rigor (rule 17/26): all history here is CONSUMED -- the "holdout" is a
time-split robustness diagnostic, NOT a sealed holdout. A grid best-of-50 is a
multiple-testing search, so `mode=null` runs the max-statistic Null-C gate: rerun the
whole 50-cell search on each return-shuffled tape and compare the REAL best-of-50 to
the null best-of-50 distribution.

Usage:
  python -m futures.gc.noise_vwap.scripts.grid_wfo grid            # real grid+WFO+holdout
  python -m futures.gc.noise_vwap.scripts.grid_wfo null 200        # max-stat Null-C gate
"""
from __future__ import annotations

import os
import sys
import json
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2_nb as ENB
from ..core import nulls_session as NS

INST = "GC"
ANCHORS = ["rth", "eth"]
KS = [0.5, 1.0, 1.25, 1.5, 2.0]
LOOKBACKS = [5, 14, 30, 60, 90]
PERIOD = 30                                  # 30-min decision clock
FEES_PT = 2.25 / S.POINT_VALUE[INST]         # $2.25/side -> points
TICK = S.TICK[INST]
COST = FEES_PT + 0.50 * TICK                  # primary: 0.50 tick/side + fees
COST_25 = FEES_PT + 0.25 * TICK
ANN = 252.0
CACHE = os.path.join(os.path.dirname(__file__), "..", "outputs", "gc_rth_both.parquet")
OUTDIR = os.path.join(os.path.dirname(__file__), "..", "artifacts", "runs", "EXP-0003")

VCOL = {"rth": "vwap_rth", "eth": "vwap_eth"}


def load_frame() -> pd.DataFrame:
    if os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    df = S.load_rth_both(INST)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    df.to_parquet(CACHE)
    return df


def base_bands_by_lb(frame: pd.DataFrame) -> dict:
    """k=1 base bands (with hi_ref/lo_ref/sigma) per lookback -- rescaled by k cheaply."""
    return {lb: S._base_bands(frame, lb) for lb in LOOKBACKS}


def cell_trades(frame_a: pd.DataFrame, base: pd.DataFrame, k: float, dmfo) -> pd.DataFrame:
    """Trades for one (anchor-set frame, lookback-base, k) cell via the numba engine."""
    bands = S.scale_bands(base, k)
    return ENB.run(frame_a, bands, dmfo)


def day_ret_series(trades: pd.DataFrame, cost: float, dates: pd.Index) -> pd.Series:
    """Per-session summed NET RETURN (net_pts/entry_px), reindexed to `dates` (0 if no
    trade). entry_px normalization makes the series era-neutral."""
    if trades.empty:
        return pd.Series(0.0, index=dates, dtype=float)
    net = trades["points"] - 2.0 * cost
    ret = net / trades["entry_px"]
    day = ret.groupby(trades["date"]).sum()
    return day.reindex(dates, fill_value=0.0)


def metrics(day_ret: pd.Series, trades: pd.DataFrame, cost: float) -> dict:
    x = day_ret.to_numpy()
    sd = x.std(ddof=1)
    sharpe = (x.mean() / sd * np.sqrt(ANN)) if sd > 0 else 0.0
    n = len(x)
    t = (x.mean() / (sd / np.sqrt(n))) if sd > 0 else 0.0
    net_pt = float((trades["points"] - 2.0 * cost).mean()) if not trades.empty else 0.0
    # day$net (1 contract, tradable units) on the traded days
    if not trades.empty:
        dnet = (trades["points"] - 2.0 * cost).groupby(trades["date"]).sum() * S.POINT_VALUE[INST]
        day_usd = float(dnet.reindex(day_ret.index, fill_value=0.0).mean())
    else:
        day_usd = 0.0
    return dict(sharpe=float(sharpe), t=float(t), mean_ret=float(x.mean()),
                net_pt=net_pt, day_usd=day_usd, n_trades=int(len(trades)))


def run_grid(frame: pd.DataFrame, bases: dict, dmfo, dates: pd.Index,
             cost: float = COST) -> pd.DataFrame:
    """All 50 cells over the common `dates`. Returns a tidy results frame."""
    rows = []
    for anchor in ANCHORS:
        fa = frame.assign(vwap=frame[VCOL[anchor]])
        for lb in LOOKBACKS:
            base = bases[lb]
            for k in KS:
                tr = cell_trades(fa, base, k, dmfo)
                tr = tr[tr["date"].isin(dates)] if not tr.empty else tr
                dr = day_ret_series(tr, cost, dates)
                m = metrics(dr, tr, cost)
                m.update(anchor=anchor, lookback=lb, k=k)
                rows.append(m)
    return pd.DataFrame(rows)


def wfo(frame: pd.DataFrame, bases: dict, dmfo, is_dates: pd.Index,
        n_folds: int = 6) -> dict:
    """Expanding-window WFO on the in-sample dates. For each test fold (2..K): pick the
    best cell (Sharpe) on all prior IS dates, apply to the fold, collect trades. Returns
    the concatenated WFO stream metrics + the fold selections."""
    folds = np.array_split(is_dates.to_numpy(), n_folds)
    # precompute every cell's per-session ret over ALL is_dates once (fast), then slice.
    cell_day = {}   # (anchor,lb,k) -> full day_ret series over is_dates
    cell_tr = {}
    for anchor in ANCHORS:
        fa = frame.assign(vwap=frame[VCOL[anchor]])
        for lb in LOOKBACKS:
            for k in KS:
                tr = cell_trades(fa, bases[lb], k, dmfo)
                tr = tr[tr["date"].isin(is_dates)] if not tr.empty else tr
                cell_tr[(anchor, lb, k)] = tr
                cell_day[(anchor, lb, k)] = day_ret_series(tr, COST, pd.Index(is_dates))

    def sharpe_on(series_full: pd.Series, dmask: np.ndarray) -> float:
        x = series_full.loc[dmask].to_numpy()
        sd = x.std(ddof=1)
        return (x.mean() / sd * np.sqrt(ANN)) if sd > 0 else 0.0

    picks = []
    stream = []
    for f in range(1, n_folds):
        train = np.concatenate(folds[:f])
        test = folds[f]
        best, best_sh = None, -1e9
        for key, ser in cell_day.items():
            sh = sharpe_on(ser, train)
            if sh > best_sh:
                best_sh, best = sh, key
        picks.append(dict(fold=f, train_end=str(pd.Timestamp(train[-1]).date()),
                          test_start=str(pd.Timestamp(test[0]).date()),
                          anchor=best[0], lookback=best[1], k=best[2],
                          train_sharpe=round(best_sh, 3)))
        tr = cell_tr[best]
        stream.append(tr[tr["date"].isin(test)])
    wfo_tr = pd.concat(stream, ignore_index=True) if stream else pd.DataFrame()
    wfo_dates = pd.Index(np.concatenate(folds[1:]))
    dr = day_ret_series(wfo_tr, COST, wfo_dates)
    m = metrics(dr, wfo_tr[wfo_tr["date"].isin(wfo_dates)], COST)
    # baseline (rth,k1,lb90) over the same WFO dates
    btr = cell_tr[("rth", 90, 1.0)]
    bdr = day_ret_series(btr[btr["date"].isin(wfo_dates)], COST, wfo_dates)
    bm = metrics(bdr, btr[btr["date"].isin(wfo_dates)], COST)
    return dict(picks=picks, wfo=m, baseline=bm, wfo_dates=wfo_dates)


def main_grid():
    frame = load_frame()
    dmfo = S.decision_mfos(PERIOD, int(frame["mfo"].max()))
    bases = base_bands_by_lb(frame)
    # common date set = sessions where the deepest lookback (90) has bands
    common = pd.Index(np.sort(S.scale_bands(bases[90], 1.0)["sdate"].unique()))
    split = int(len(common) * 0.8)
    is_dates, hold_dates = common[:split], common[split:]
    print(f"=== GC grid+WFO+holdout | {len(common)} common sessions "
          f"{pd.Timestamp(common[0]).date()}->{pd.Timestamp(common[-1]).date()} ===")
    print(f"IS={len(is_dates)} ({pd.Timestamp(is_dates[0]).date()}->{pd.Timestamp(is_dates[-1]).date()})  "
          f"HOLDOUT={len(hold_dates)} ({pd.Timestamp(hold_dates[0]).date()}->{pd.Timestamp(hold_dates[-1]).date()})  "
          f"[consumed history -- robustness split, NOT a sealed holdout]")
    print(f"cost primary={COST:.4f}pt/side (0.50 tick + fees); metric=daily Sharpe on net return\n")

    # ---- full-sample grid (all 50 cells) ----
    res = run_grid(frame, bases, dmfo, common)
    res = res.sort_values("sharpe", ascending=False).reset_index(drop=True)
    base_row = res[(res.anchor == "rth") & (res.lookback == 90) & (res.k == 1.0)].iloc[0]
    print("--- FULL-SAMPLE GRID (top 12 of 50 by daily Sharpe) ---")
    print(f"{'anchor':6s} {'lb':>3s} {'k':>5s} {'Sharpe':>7s} {'t':>6s} {'net_pt':>7s} {'day$':>7s} {'n':>6s}")
    for _, r in res.head(12).iterrows():
        print(f"{r.anchor:6s} {int(r.lookback):3d} {r.k:5.2f} {r.sharpe:7.3f} {r.t:6.2f} "
              f"{r.net_pt:+7.3f} {r.day_usd:+7.1f} {int(r.n_trades):6d}")
    print(f"\nBASELINE (rth,lb90,k1.0): Sharpe={base_row.sharpe:.3f} t={base_row.t:.2f} "
          f"net_pt={base_row.net_pt:+.3f} day$={base_row.day_usd:+.1f} n={int(base_row.n_trades)}")

    # ---- WFO ----
    w = wfo(frame, bases, dmfo, is_dates)
    print(f"\n--- EXPANDING WFO (5 test folds on IS) ---")
    for p in w["picks"]:
        print(f" fold {p['fold']} train->{p['train_end']} test {p['test_start']}+: "
              f"pick anchor={p['anchor']} lb={p['lookback']} k={p['k']} (train Sh={p['train_sharpe']})")
    print(f" WFO stream : Sharpe={w['wfo']['sharpe']:.3f} t={w['wfo']['t']:.2f} "
          f"net_pt={w['wfo']['net_pt']:+.3f} day$={w['wfo']['day_usd']:+.1f} n={w['wfo']['n_trades']}")
    print(f" baseline   : Sharpe={w['baseline']['sharpe']:.3f} t={w['baseline']['t']:.2f} "
          f"net_pt={w['baseline']['net_pt']:+.3f} day$={w['baseline']['day_usd']:+.1f} n={w['baseline']['n_trades']}")

    # ---- best-IS-cell on the (consumed) holdout ----
    is_res = run_grid(frame, bases, dmfo, is_dates)
    best_is = is_res.sort_values("sharpe", ascending=False).iloc[0]
    fa = frame.assign(vwap=frame[VCOL[best_is.anchor]])
    htr = cell_trades(fa, bases[int(best_is.lookback)], float(best_is.k), dmfo)
    htr = htr[htr["date"].isin(hold_dates)]
    hdr = day_ret_series(htr, COST, hold_dates)
    hm = metrics(hdr, htr, COST)
    bfa = frame.assign(vwap=frame["vwap_rth"])
    bhtr = cell_trades(bfa, bases[90], 1.0, dmfo); bhtr = bhtr[bhtr["date"].isin(hold_dates)]
    bhm = metrics(day_ret_series(bhtr, COST, hold_dates), bhtr, COST)
    print(f"\n--- BEST-IS-CELL ON HOLDOUT (consumed; robustness only) ---")
    print(f" best IS cell: anchor={best_is.anchor} lb={int(best_is.lookback)} k={best_is.k} "
          f"(IS Sharpe={best_is.sharpe:.3f})")
    print(f" holdout    : Sharpe={hm['sharpe']:.3f} t={hm['t']:.2f} net_pt={hm['net_pt']:+.3f} "
          f"day$={hm['day_usd']:+.1f} n={hm['n_trades']}")
    print(f" baseline HO: Sharpe={bhm['sharpe']:.3f} t={bhm['t']:.2f} net_pt={bhm['net_pt']:+.3f} "
          f"day$={bhm['day_usd']:+.1f} n={bhm['n_trades']}")

    os.makedirs(OUTDIR, exist_ok=True)
    res.to_csv(os.path.join(OUTDIR, "grid_full.csv"), index=False)
    with open(os.path.join(OUTDIR, "wfo.json"), "w") as f:
        json.dump({"picks": w["picks"], "wfo": w["wfo"], "baseline": w["baseline"],
                   "best_is": {"anchor": best_is.anchor, "lookback": int(best_is.lookback),
                               "k": float(best_is.k), "is_sharpe": float(best_is.sharpe)},
                   "holdout": hm, "holdout_baseline": bhm,
                   "n_common": len(common), "n_is": len(is_dates), "n_hold": len(hold_dates)},
                  f, indent=2, default=str)
    print(f"\nsaved -> {OUTDIR}/grid_full.csv, wfo.json")
    return res


def main_null(n_null: int):
    frame = load_frame()
    dmfo = S.decision_mfos(PERIOD, int(frame["mfo"].max()))
    bases = base_bands_by_lb(frame)
    common = pd.Index(np.sort(S.scale_bands(bases[90], 1.0)["sdate"].unique()))
    # REAL best-of-50
    real = run_grid(frame, bases, dmfo, common)
    real_max = real["sharpe"].max()
    real_best = real.sort_values("sharpe", ascending=False).iloc[0]
    print(f"=== max-stat Null-C gate | {n_null} draws | REAL best-of-50 Sharpe={real_max:.3f} "
          f"({real_best.anchor},lb{int(real_best.lookback)},k{real_best.k}) ===")
    print(f"REAL diffusivity={NS.diffusivity(frame):.4f}pt")
    null_max, null_best_cell = [], []
    for s in range(n_null):
        nf = NS.null_c_returns(frame, seed=2000 + s)
        nbases = {lb: S._base_bands(nf, lb) for lb in LOOKBACKS}
        # keep only common dates that survived (band warmup identical structure)
        ncommon = pd.Index(np.sort(S.scale_bands(nbases[90], 1.0)["sdate"].unique()))
        nres = run_grid(nf, nbases, dmfo, ncommon)
        mx = nres["sharpe"].max()
        null_max.append(mx)
        br = nres.sort_values("sharpe", ascending=False).iloc[0]
        null_best_cell.append(f"{br.anchor},lb{int(br.lookback)},k{br.k}")
        print(f"  null {s:3d}: diff={NS.diffusivity(nf):.4f} max_Sharpe={mx:.3f} ({null_best_cell[-1]})",
              flush=True)
        # checkpoint every draw so a partial run is never lost
        if s % 5 == 0 or s == n_null - 1:
            _nm = np.array(null_max)
            os.makedirs(OUTDIR, exist_ok=True)
            with open(os.path.join(OUTDIR, "null_maxstat.json"), "w") as f:
                json.dump(dict(n_null=len(null_max), real_max=float(real_max),
                               real_best=f"{real_best.anchor},lb{int(real_best.lookback)},k{real_best.k}",
                               null_max=[float(x) for x in _nm],
                               z=float((real_max - _nm.mean()) / _nm.std()) if _nm.std() > 0 else None,
                               p=float((1.0 + (_nm >= real_max).sum()) / (len(_nm) + 1.0)),
                               null_best_cells=null_best_cell), f, indent=2)
    nm = np.array(null_max)
    z = (real_max - nm.mean()) / nm.std() if nm.std() > 0 else np.inf
    p = (1.0 + float((nm >= real_max).sum())) / (len(nm) + 1.0)
    print(f"\n--- MAX-STAT NULL-C SUMMARY ---")
    print(f"null best-of-50 Sharpe: mean={nm.mean():.3f} std={nm.std():.3f} "
          f"[min {nm.min():.3f}, max {nm.max():.3f}]")
    print(f"real best-of-50 Sharpe: {real_max:.3f}")
    print(f"real vs null-max: z={z:+.2f}  upper-tail p={p:.4f}")
    print(f"  interpretation: p<~0.05 => the best cell beats what the search finds on noise;")
    print(f"                  p>~0.05 => best-of-50 is a multiple-testing artifact.")
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "null_maxstat.json"), "w") as f:
        json.dump(dict(n_null=n_null, real_max=float(real_max),
                       real_best=f"{real_best.anchor},lb{int(real_best.lookback)},k{real_best.k}",
                       null_max=[float(x) for x in nm], z=float(z), p=float(p),
                       null_best_cells=null_best_cell), f, indent=2)
    print(f"saved -> {OUTDIR}/null_maxstat.json")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "grid"
    if mode == "grid":
        main_grid()
    elif mode == "null":
        main_null(int(sys.argv[2]) if len(sys.argv) > 2 else 200)
    else:
        raise SystemExit("mode must be 'grid' or 'null [N]'")
