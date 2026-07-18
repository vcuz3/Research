"""
Walk-forward-optimisation harness for the continuous_stop NQ momentum baseline.

Design decisions locked with the user:
  * ROLLING 3-year train -> 1-year OOS, refit annually, 5-trading-day embargo.
  * The DAY is the unit; all P&L is per-day-summed, day-clustered t (rule 12/13/22).
  * Everything scored in R = net_points / atr_pts (rule 19): NQ ran 2.6k->20k over the
    sample and ATR 34->383 pts, so raw-point sums are ~entirely the recent era. R
    equal-weights eras. Gross reported alongside net (rule 20).
  * THE VERDICT IS THE NULL-C TWIN (rule 17): the *identical* WFO procedure is re-run
    on >=30 path-preserving return-shuffle draws. A design is real only if its OOS
    uplift over always-trade beats the Null-C uplift distribution by z>=2 in NET R,
    and is not merely a shrinkage-only Sharpe gain (trade count is always reported).
    A/C are structurally the KAMA leading-regime corpse (select a subset by an
    in-sample criterion); if they help as much on noise, that is the verdict.

Design A (this file): entry-time (entry_mfo bucket) inclusion. Each fold ranks the
~13 clock buckets by robust expectancy on the train window under the user's
constraints, then RE-SIMULATES the OOS year through the engine with the decision
clock restricted to the selected buckets (rule 18 -- not a post-hoc row drop, which
would mis-state the position bookkeeping).

Run:  python -u -m futures.nq.noise_vwap.scripts.wfo A            # real tape
      python -u -m futures.nq.noise_vwap.scripts.wfo A_null 30    # Null-C twin
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from ..core.data import POINT_VALUE
from .studies import get_session, INST, COST_025, _null_c_frame
from .wfo_data import LOOKBACK

OUT = Path(__file__).resolve().parents[1] / "outputs"
RT_COST = 2.0 * COST_025
PV = POINT_VALUE[INST]

TEST_YEARS = list(range(2015, 2027))   # first fold trains 2012-14, last tests 2026
TRAIN_YEARS = 3
EMBARGO_DAYS = 5


# --------------------------------------------------------------------------- #
# scoring: everything in R (net/atr), day-summed, day-clustered t
# --------------------------------------------------------------------------- #
def score(trades: pd.DataFrame, label: str = "") -> dict:
    """trades must carry date, net_atr (and net_points). Returns day-clustered R
    stats. Empty -> zeros."""
    if trades is None or trades.empty:
        return dict(label=label, n=0, dayR_mean=0.0, dayR_t=0.0, sharpe=0.0,
                    R_per_trade=0.0, sumR=0.0, n_days=0)
    dayR = trades.groupby("date")["net_atr"].sum()
    n = len(dayR)
    m = dayR.mean(); sd = dayR.std(ddof=1)
    t = m / (sd / np.sqrt(n)) if (n > 1 and sd > 0) else 0.0
    sharpe = m / sd * np.sqrt(252) if sd > 0 else 0.0
    return dict(label=label, n=int(len(trades)), n_days=int(n),
                dayR_mean=float(m), dayR_t=float(t), sharpe=float(sharpe),
                R_per_trade=float(trades["net_atr"].mean()), sumR=float(dayR.sum()))


def add_pnl(trades: pd.DataFrame, atr_by_date: pd.Series) -> pd.DataFrame:
    """Attach net_points and net_atr to raw engine trades (points, date)."""
    t = trades.copy()
    t["atr_pts"] = t["date"].map(atr_by_date)
    t["net_points"] = t["points"] - RT_COST
    t["net_atr"] = t["net_points"] / t["atr_pts"]
    return t


# --------------------------------------------------------------------------- #
# fold generator (rolling 3y train / 1y test / 5d embargo)
# --------------------------------------------------------------------------- #
def folds(all_dates: np.ndarray):
    dates = pd.to_datetime(pd.Series(all_dates).sort_values().unique())
    for ty in TEST_YEARS:
        test_lo = pd.Timestamp(ty, 1, 1); test_hi = pd.Timestamp(ty, 12, 31)
        train_lo = pd.Timestamp(ty - TRAIN_YEARS, 1, 1)
        # embargo: drop the last EMBARGO_DAYS trading days before the test year
        pre = dates[(dates >= train_lo) & (dates < test_lo)]
        if len(pre) == 0:
            continue
        train_hi = pre[-EMBARGO_DAYS] if len(pre) > EMBARGO_DAYS else pre[-1]
        yield ty, (train_lo, train_hi), (test_lo, test_hi)


# --------------------------------------------------------------------------- #
# Design A -- entry_mfo bucket inclusion
# --------------------------------------------------------------------------- #
def bucket_stats(train: pd.DataFrame, min_n: int) -> pd.DataFrame:
    """Robust per-bucket expectancy on the train window, in R. Trimmed mean (10%),
    median, p25, n. Eligibility left to the caller."""
    def trim_mean(x, p=0.10):
        x = np.sort(x.to_numpy())
        k = int(len(x) * p)
        return x[k:len(x) - k].mean() if len(x) - 2 * k > 0 else x.mean()
    g = train.groupby("entry_mfo")["net_atr"]
    out = pd.DataFrame({
        "n": g.size(),
        "trim_mean": g.apply(trim_mean),
        "median": g.median(),
        "p25": g.apply(lambda s: s.quantile(0.25)),
        "mean": g.mean(),
    })
    out["min_n_ok"] = out["n"] >= min_n
    return out


def select_buckets(stats: pd.DataFrame, prev: set | None,
                   min_n: int, require_pos_median: bool, p25_floor: float,
                   sticky: bool) -> set:
    """User constraints: min trades, positive trimmed mean, positive median (or p25
    >= floor), low turnover (hysteresis vs previous fold)."""
    elig = stats["min_n_ok"] & (stats["trim_mean"] > 0)
    if require_pos_median:
        elig &= (stats["median"] > 0)
    if p25_floor is not None:
        elig &= (stats["p25"] >= p25_floor)
    sel = set(stats.index[elig])
    if sticky and prev:
        # hysteresis: keep a previously-selected bucket if it is not clearly broken
        # (trimmed mean still >= 0 and has enough data), to limit set churn.
        keep = set(stats.index[(stats.index.isin(prev)) &
                               (stats["trim_mean"] >= 0) & stats["min_n_ok"]])
        sel |= keep
    return sel


def run_design_A(bars, bands, dataset, *, min_n=20, require_pos_median=False,
                 p25_floor=None, sticky=True, verbose=False):
    """Returns (design_trades, always_trades) concatenated across OOS folds, both
    with net_atr attached. `dataset` supplies the per-trade R used to rank buckets
    (must be the SAME tape as bars/bands)."""
    atr_by_date = bars.groupby("sdate")["atr"].first()
    max_mfo = int(bars["mfo"].max())
    full_dm = S.decision_mfos(30, max_mfo)
    all_buckets = [m + 1 for m in full_dm]   # entry_mfo = decision + 1 (next-open)

    design_parts, always_parts, log = [], [], []
    prev: set | None = None
    for ty, (tr_lo, tr_hi), (te_lo, te_hi) in folds(bars["sdate"].unique()):
        train = dataset[(dataset["date"] >= tr_lo) & (dataset["date"] <= tr_hi)]
        if train.empty:
            continue
        st = bucket_stats(train, min_n)
        sel = select_buckets(st, prev, min_n, require_pos_median, p25_floor, sticky)
        if not sel:                       # never trade nothing -> fall back to all
            sel = set(all_buckets)
        prev = sel
        sel_dm = sorted(b - 1 for b in sel)

        te_bars = bars[(bars["sdate"] >= te_lo) & (bars["sdate"] <= te_hi)]
        te_bands = bands[(bands["sdate"] >= te_lo) & (bands["sdate"] <= te_hi)]
        d_tr = add_pnl(E.run(te_bars, te_bands, sel_dm, exit_check="every_bar"), atr_by_date)
        a_tr = add_pnl(E.run(te_bars, te_bands, full_dm, exit_check="every_bar"), atr_by_date)
        design_parts.append(d_tr); always_parts.append(a_tr)
        turnover = len(sel ^ (set(prev) if prev else set()))
        log.append((ty, len(sel), sorted(b for b in sel),
                    score(d_tr)["sumR"], score(a_tr)["sumR"]))
        if verbose:
            print(f"  {ty}: keep {len(sel):2d}/{len(all_buckets)} buckets "
                  f"tod={sorted((b-1+S.RTH_START) for b in sel)[:3]}... "
                  f"designR={score(d_tr)['sumR']:+.2f} alwaysR={score(a_tr)['sumR']:+.2f}")
    design = pd.concat(design_parts, ignore_index=True) if design_parts else pd.DataFrame()
    always = pd.concat(always_parts, ignore_index=True) if always_parts else pd.DataFrame()
    return design, always, log


# --------------------------------------------------------------------------- #
# runners
# --------------------------------------------------------------------------- #
def _load_real():
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dataset = pd.read_parquet(OUT / "wfo_dataset_continuous_stop.parquet")
    return bars, bands, dataset


CONSTRAINT_GRID = dict(
    lax=dict(min_n=20, require_pos_median=False, p25_floor=None, sticky=True),
    median=dict(min_n=20, require_pos_median=True, p25_floor=None, sticky=True),
    strict=dict(min_n=30, require_pos_median=True, p25_floor=-0.02, sticky=False),
)


def run_A_real():
    bars, bands, dataset = _load_real()
    print("=== DESIGN A (real tape): entry_mfo bucket inclusion WFO ===")
    print(f"folds: rolling {TRAIN_YEARS}y train / 1y OOS / {EMBARGO_DAYS}d embargo, "
          f"test {TEST_YEARS[0]}-{TEST_YEARS[-1]}; scored in R (net/atr)\n")
    for cname, kw in CONSTRAINT_GRID.items():
        design, always, log = run_design_A(bars, bands, dataset, verbose=(cname == "lax"), **kw)
        sd = score(design, "design"); sa = score(always, "always")
        upliftR = sd["sumR"] - sa["sumR"]
        print(f"\n[{cname}] constraints={kw}")
        print(f"  always : n={sa['n']:>4d} sumR={sa['sumR']:+.2f} dayR_t={sa['dayR_t']:+.2f} Sh={sa['sharpe']:.2f}")
        print(f"  design : n={sd['n']:>4d} sumR={sd['sumR']:+.2f} dayR_t={sd['dayR_t']:+.2f} Sh={sd['sharpe']:.2f}")
        print(f"  UPLIFT : dR(sumR)={upliftR:+.2f}  dR/trade={sd['R_per_trade']-sa['R_per_trade']:+.4f} "
              f"trades {sa['n']}->{sd['n']} ({sd['n']/sa['n']-1:+.0%})")


def run_A_null(ndraw=30):
    bars, bands, dataset = _load_real()
    # real uplift per constraint (baseline for z)
    from .wfo_data import enrich_trades
    print(f"=== DESIGN A Null-C twin ({ndraw} draws) ===")
    real_uplift = {}
    for cname, kw in CONSTRAINT_GRID.items():
        d, a, _ = run_design_A(bars, bands, dataset, **kw)
        real_uplift[cname] = score(d)["sumR"] - score(a)["sumR"]
    print("real uplift (sumR):", {k: round(v, 2) for k, v in real_uplift.items()})

    null_uplift = {c: [] for c in CONSTRAINT_GRID}
    max_mfo = int(bars["mfo"].max()); full_dm = S.decision_mfos(30, max_mfo)
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=3000 + k)
        nbands = S.noise_bands(nb, LOOKBACK)
        ntr = E.run(nb, nbands, full_dm, exit_check="every_bar", fill_mode="next_open")
        ndat = enrich_trades(nb, nbands, ntr)          # same features/excursions
        if ndat.empty:
            continue
        for cname, kw in CONSTRAINT_GRID.items():
            d, a, _ = run_design_A(nb, nbands, ndat, **kw)
            null_uplift[cname].append(score(d)["sumR"] - score(a)["sumR"])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()
    print(f"{'constraint':<10s} {'realUplift':>10s} {'nullMean':>9s} {'nullSD':>7s} "
          f"{'z':>6s} {'null>=real':>10s}")
    for cname in CONSTRAINT_GRID:
        nu = np.array(null_uplift[cname]); ru = real_uplift[cname]
        z = (ru - nu.mean()) / nu.std(ddof=1) if nu.std(ddof=1) > 0 else np.nan
        frac = float((nu >= ru).mean())
        print(f"{cname:<10s} {ru:>+10.2f} {nu.mean():>+9.2f} {nu.std(ddof=1):>7.2f} "
              f"{z:>+6.2f} {frac:>10.2f}")
    print("\nVERDICT RULE: real only if z>=2 AND null rarely (<~5%) matches real uplift.")


# --------------------------------------------------------------------------- #
# Design C -- bad-trade filter on causal geometry features
# --------------------------------------------------------------------------- #
# Scale-free features ONLY: no absolute ATR/price level, so the model cannot key on
# "recent era = good" (regime), which rolling-3y can't observe and won't generalise.
FEATS = ["ext_atr", "vwap_dist_atr", "sess_move", "open_gap", "band_width_bps",
         "tod", "dow", "side"]


def candidate_signals(bars, bands, dm) -> pd.DataFrame:
    """All potential entries: decision signal bars where the band+VWAP entry
    condition holds. Superset of realised trades (rule 18); the engine gate keys off
    (date, signal_mfo). Causal features computed at the signal bar, matching
    wfo_data.enrich_trades exactly."""
    atr_by_date = bars.groupby("sdate")["atr"].first()
    dec = bars[bars["mfo"].isin(set(dm))][["sdate", "mfo", "close", "vwap"]].copy()
    dec = dec.merge(bands[["sdate", "mfo", "upper", "lower", "sigma",
                           "rth_open", "prior_close"]], on=["sdate", "mfo"])
    dec["atr"] = dec["sdate"].map(atr_by_date)
    dec = dec[np.isfinite(dec["atr"]) & (dec["atr"] > 0)]
    lng = (dec["close"] > dec["upper"]) & (dec["close"] > dec["vwap"])
    sht = (dec["close"] < dec["lower"]) & (dec["close"] < dec["vwap"])
    dec = dec[lng | sht].copy()
    dec["side"] = np.where(lng[lng | sht], 1, -1)
    ref = np.where(dec["side"] == 1, dec["upper"], dec["lower"])
    dec["ext_atr"] = dec["side"] * (dec["close"] - ref) / dec["atr"]
    dec["vwap_dist_atr"] = dec["side"] * (dec["close"] - dec["vwap"]) / dec["atr"]
    dec["sess_move"] = dec["side"] * (dec["close"] / dec["rth_open"] - 1.0)
    dec["open_gap"] = dec["rth_open"] / dec["prior_close"] - 1.0
    dec["band_width_bps"] = (dec["upper"] - dec["lower"]) / dec["rth_open"] * 1e4
    dec["tod"] = dec["mfo"] + S.RTH_START
    dec["dow"] = pd.to_datetime(dec["sdate"]).dt.dayofweek
    return dec.rename(columns={"sdate": "date", "mfo": "signal_mfo"})


def ridge_fit(X, y, lam=10.0):
    mu = X.mean(0); sd = X.std(0); sd[sd == 0] = 1.0
    Xs = np.c_[np.ones(len(X)), (X - mu) / sd]
    A = Xs.T @ Xs + lam * np.eye(Xs.shape[1]); A[0, 0] -= lam  # don't penalise intercept
    w = np.linalg.solve(A, Xs.T @ y)
    return (w, mu, sd)


def ridge_pred(model, X):
    w, mu, sd = model
    return np.c_[np.ones(len(X)), (X - mu) / sd] @ w


def run_design_C(bars, bands, dataset, *, keep_frac=0.80, lam=10.0, verbose=False):
    atr_by_date = bars.groupby("sdate")["atr"].first()
    max_mfo = int(bars["mfo"].max()); full_dm = S.decision_mfos(30, max_mfo)
    cand = candidate_signals(bars, bands, full_dm)
    d_feat = dataset.dropna(subset=FEATS).copy()

    design_parts, always_parts, tail_keep = [], [], []
    for ty, (tr_lo, tr_hi), (te_lo, te_hi) in folds(bars["sdate"].unique()):
        train = d_feat[(d_feat["date"] >= tr_lo) & (d_feat["date"] <= tr_hi)]
        if len(train) < 100:
            continue
        Xtr = train[FEATS].to_numpy(float); ytr = train["net_atr"].to_numpy(float)
        model = ridge_fit(Xtr, ytr, lam)
        thr = np.quantile(ridge_pred(model, Xtr), 1.0 - keep_frac)  # keep top keep_frac

        c = cand[(cand["date"] >= te_lo) & (cand["date"] <= te_hi)].copy()
        if c.empty:
            continue
        c["pred"] = ridge_pred(model, c[FEATS].to_numpy(float))
        keep = c[c["pred"] >= thr]
        gate = set(zip(keep["date"], keep["signal_mfo"].astype(int)))

        te_bars = bars[(bars["sdate"] >= te_lo) & (bars["sdate"] <= te_hi)]
        te_bands = bands[(bands["sdate"] >= te_lo) & (bands["sdate"] <= te_hi)]
        d_tr = add_pnl(E.run(te_bars, te_bands, full_dm, exit_check="every_bar",
                             entry_gate=gate), atr_by_date)
        a_tr = add_pnl(E.run(te_bars, te_bands, full_dm, exit_check="every_bar"), atr_by_date)
        design_parts.append(d_tr); always_parts.append(a_tr)
        # right-tail participation: fraction of always-trade top-decile-R trades kept
        if not a_tr.empty:
            cut = a_tr["net_atr"].quantile(0.9)
            big = a_tr[a_tr["net_atr"] >= cut]
            kept_big = d_tr["net_atr"][d_tr["net_atr"] >= cut].shape[0] if not d_tr.empty else 0
            tail_keep.append(kept_big / max(len(big), 1))
        if verbose:
            print(f"  {ty}: keep {len(keep)}/{len(c)} cand ({len(keep)/len(c):.0%}) "
                  f"designR={score(d_tr)['sumR']:+.2f} alwaysR={score(a_tr)['sumR']:+.2f}")
    design = pd.concat(design_parts, ignore_index=True) if design_parts else pd.DataFrame()
    always = pd.concat(always_parts, ignore_index=True) if always_parts else pd.DataFrame()
    return design, always, (np.mean(tail_keep) if tail_keep else np.nan)


C_GRID = [0.90, 0.80, 0.70, 0.60]


def run_C_real():
    bars, bands, dataset = _load_real()
    print("=== DESIGN C (real tape): bad-trade filter (ridge on causal geometry) ===")
    print(f"features={FEATS}\nfolds: rolling {TRAIN_YEARS}y/1y/{EMBARGO_DAYS}d embargo, scored in R\n")
    for kf in C_GRID:
        design, always, tail = run_design_C(bars, bands, dataset, keep_frac=kf,
                                            verbose=(kf == 0.80))
        sd = score(design); sa = score(always)
        print(f"\n[keep_frac={kf:.2f}]")
        print(f"  always : n={sa['n']:>4d} sumR={sa['sumR']:+.2f} dayR_t={sa['dayR_t']:+.2f} Sh={sa['sharpe']:.2f}")
        print(f"  design : n={sd['n']:>4d} sumR={sd['sumR']:+.2f} dayR_t={sd['dayR_t']:+.2f} Sh={sd['sharpe']:.2f}")
        print(f"  UPLIFT : dR(sumR)={sd['sumR']-sa['sumR']:+.2f}  Sh {sa['sharpe']:.2f}->{sd['sharpe']:.2f}  "
              f"tail-kept={tail:.0%}  trades {sa['n']}->{sd['n']}")


def run_C_null(ndraw=30, keep_frac=0.80):
    bars, bands, dataset = _load_real()
    from .wfo_data import enrich_trades
    print(f"=== DESIGN C Null-C twin ({ndraw} draws, keep_frac={keep_frac}) ===")
    d, a, _ = run_design_C(bars, bands, dataset, keep_frac=keep_frac)
    real_up = score(d)["sumR"] - score(a)["sumR"]
    real_dsh = score(d)["sharpe"] - score(a)["sharpe"]
    print(f"real uplift: sumR={real_up:+.2f}  dSharpe={real_dsh:+.3f}")
    max_mfo = int(bars["mfo"].max()); full_dm = S.decision_mfos(30, max_mfo)
    nu, ndsh = [], []
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=4000 + k)
        nbands = S.noise_bands(nb, LOOKBACK)
        ntr = E.run(nb, nbands, full_dm, exit_check="every_bar", fill_mode="next_open")
        ndat = enrich_trades(nb, nbands, ntr)
        if ndat.empty:
            continue
        d, a, _ = run_design_C(nb, nbands, ndat, keep_frac=keep_frac)
        nu.append(score(d)["sumR"] - score(a)["sumR"])
        ndsh.append(score(d)["sharpe"] - score(a)["sharpe"])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()
    nu = np.array(nu); ndsh = np.array(ndsh)
    z = (real_up - nu.mean()) / nu.std(ddof=1) if nu.std(ddof=1) > 0 else np.nan
    print(f"sumR   : real={real_up:+.2f} null={nu.mean():+.2f}+/-{nu.std(ddof=1):.2f} "
          f"z={z:+.2f} null>=real={float((nu>=real_up).mean()):.2f}")
    zsh = (real_dsh - ndsh.mean()) / ndsh.std(ddof=1) if ndsh.std(ddof=1) > 0 else np.nan
    print(f"dSharpe: real={real_dsh:+.3f} null={ndsh.mean():+.3f}+/-{ndsh.std(ddof=1):.3f} "
          f"z={zsh:+.2f} null>=real={float((ndsh>=real_dsh).mean()):.2f}")
    print("\nVERDICT: real only if z>=2 on NET R AND not a shrinkage-only Sharpe gain.")


# --------------------------------------------------------------------------- #
# Design B -- re-tune the existing band/VWAP every-bar stop
# --------------------------------------------------------------------------- #
# The optimisation objective is train day-R Sharpe / net R, NOT "MFE capture"
# (rule 14/15): asymmetric barriers manufacture expectancy from geometry, so the
# bracket is tuned on realised risk-adjusted PnL and judged OOS + against Null-C.
B_REFS = ["both", "vwap", "band"]
B_BUFS = [-0.10, -0.05, 0.0, 0.05, 0.10, 0.20]
B_GRID = [(r, b) for r in B_REFS for b in B_BUFS]
B_BASE = ("both", 0.0)


def _b_configs(bars, bands, atr_by_date):
    """Run every stop config once over the full sample; slice by fold later."""
    max_mfo = int(bars["mfo"].max()); full_dm = S.decision_mfos(30, max_mfo)
    out = {}
    for (ref, buf) in B_GRID:
        tr = E.run(bars, bands, full_dm, exit_check="every_bar",
                   stop_ref=ref, stop_buf_atr=buf)
        out[(ref, buf)] = add_pnl(tr, atr_by_date)
    return out


def run_design_B(bars, bands, *, select="sharpe", verbose=False):
    atr_by_date = bars.groupby("sdate")["atr"].first()
    cfgs = _b_configs(bars, bands, atr_by_date)
    design_parts, always_parts, picks = [], [], []
    for ty, (tr_lo, tr_hi), (te_lo, te_hi) in folds(bars["sdate"].unique()):
        best, best_val = None, -np.inf
        for key, tr in cfgs.items():
            trn = tr[(tr["date"] >= tr_lo) & (tr["date"] <= tr_hi)]
            s = score(trn)
            val = s["sharpe"] if select == "sharpe" else s["sumR"]
            if s["n"] >= 100 and val > best_val:
                best_val, best = val, key
        if best is None:
            best = B_BASE
        picks.append((ty, best))
        d_tr = cfgs[best]
        a_tr = cfgs[B_BASE]
        design_parts.append(d_tr[(d_tr["date"] >= te_lo) & (d_tr["date"] <= te_hi)])
        always_parts.append(a_tr[(a_tr["date"] >= te_lo) & (a_tr["date"] <= te_hi)])
        if verbose:
            print(f"  {ty}: pick stop_ref={best[0]} buf={best[1]:+.2f} "
                  f"(trainSh={best_val:.2f})")
    design = pd.concat(design_parts, ignore_index=True)
    always = pd.concat(always_parts, ignore_index=True)
    return design, always, picks


def run_B_real():
    bars, bands, _ = _load_real()
    print("=== DESIGN B (real tape): re-tune band/VWAP every-bar stop ===")
    print(f"grid: stop_ref in {B_REFS} x buf(ATR) in {B_BUFS}; select by train day-R Sharpe\n")
    for sel in ("sharpe", "sumR"):
        design, always, picks = run_design_B(bars, bands, select=sel, verbose=(sel == "sharpe"))
        sd = score(design); sa = score(always)
        print(f"\n[select={sel}]")
        print(f"  always : n={sa['n']:>4d} sumR={sa['sumR']:+.2f} dayR_t={sa['dayR_t']:+.2f} Sh={sa['sharpe']:.2f}")
        print(f"  design : n={sd['n']:>4d} sumR={sd['sumR']:+.2f} dayR_t={sd['dayR_t']:+.2f} Sh={sd['sharpe']:.2f}")
        print(f"  UPLIFT : dR(sumR)={sd['sumR']-sa['sumR']:+.2f}  Sh {sa['sharpe']:.2f}->{sd['sharpe']:.2f}")
    # fill-feasibility (rule 1/2): most-picked config, next_open vs signal_close
    from collections import Counter
    top = Counter(p for _, p in picks).most_common(1)[0][0]
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(30, max_mfo)
    no = E.run(bars, bands, dm, exit_check="every_bar", stop_ref=top[0], stop_buf_atr=top[1], fill_mode="next_open")
    sc = E.run(bars, bands, dm, exit_check="every_bar", stop_ref=top[0], stop_buf_atr=top[1], fill_mode="signal_close")
    art = (sc["points"].mean() - no["points"].mean())
    print(f"\nfill check (most-picked {top}): next_open={no['points'].mean():+.3f} "
          f"signal_close={sc['points'].mean():+.3f} artifact={art:+.3f}pt (want ~0)")


def run_B_null(ndraw=30, select="sharpe"):
    bars, bands, _ = _load_real()
    print(f"=== DESIGN B Null-C twin ({ndraw} draws, select={select}) ===")
    d, a, _ = run_design_B(bars, bands, select=select)
    real_up = score(d)["sumR"] - score(a)["sumR"]
    real_dsh = score(d)["sharpe"] - score(a)["sharpe"]
    print(f"real uplift: sumR={real_up:+.2f}  dSharpe={real_dsh:+.3f}")
    nu, ndsh = [], []
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=5000 + k)
        nbands = S.noise_bands(nb, LOOKBACK)
        d, a, _ = run_design_B(nb, nbands, select=select)
        nu.append(score(d)["sumR"] - score(a)["sumR"])
        ndsh.append(score(d)["sharpe"] - score(a)["sharpe"])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()
    nu = np.array(nu); ndsh = np.array(ndsh)
    z = (real_up - nu.mean()) / nu.std(ddof=1) if nu.std(ddof=1) > 0 else np.nan
    zsh = (real_dsh - ndsh.mean()) / ndsh.std(ddof=1) if ndsh.std(ddof=1) > 0 else np.nan
    print(f"sumR   : real={real_up:+.2f} null={nu.mean():+.2f}+/-{nu.std(ddof=1):.2f} z={z:+.2f} null>=real={float((nu>=real_up).mean()):.2f}")
    print(f"dSharpe: real={real_dsh:+.3f} null={ndsh.mean():+.3f}+/-{ndsh.std(ddof=1):.3f} z={zsh:+.2f} null>=real={float((ndsh>=real_dsh).mean()):.2f}")
    print("\nVERDICT: real only if z>=2 on NET R AND not a shrinkage-only Sharpe gain.")


# --------------------------------------------------------------------------- #
# Design D -- walk-forward the NOISE-AREA VOLATILITY MULTIPLIER
# --------------------------------------------------------------------------- #
# The band is upper = hi_ref*(1 + k*sigma), lower = lo_ref*(1 - k*sigma). The
# baseline continuous_stop config uses k=1.0 implicitly. k is the Zarattini noise-
# area width knob: a WIDER band (k>1) makes entries rarer and more extreme AND
# LOOSENS the band-referenced every-bar stop; a TIGHTER band (k<1) does the opposite.
# Because k moves BOTH the entry rarity and the stop geometry, this is structurally a
# Design-B family (geometry, not timing): the verdict is the Null-C twin (rule 17).
# On drift-preserving noise a looser/tighter band just harvests more/less of the free
# session drift, so an apparent OOS uplift that the null reproduces is machinery.
D_MULTS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
D_BASE_MULT = 1.0     # the continuous_stop baseline
D_FLAT_MULT = 1.5     # the user's fixed-1.5-for-the-whole-period comparison


def _scale_bands(base: pd.DataFrame, mult: float) -> pd.DataFrame:
    """Rescale a mult=1.0 noise-band frame to an arbitrary multiplier k. sigma is the
    raw mean-move (mult-independent); only the band edges move. mult=1.0 reproduces
    `base` exactly (rule 23). Computed from the stored refs so it is exact, not an
    approximation of a re-pivot."""
    b = base.copy()
    hi_ref = np.maximum(b["rth_open"], b["prior_close"])
    lo_ref = np.minimum(b["rth_open"], b["prior_close"])
    b["upper"] = hi_ref * (1.0 + mult * b["sigma"])
    b["lower"] = lo_ref * (1.0 - mult * b["sigma"])
    return b


def _d_configs(bars, base_bands, atr_by_date):
    """Run the continuous_stop engine once per multiplier over the full sample; slice
    by fold later (mirrors Design B). exit_check='every_bar' == continuous_stop."""
    max_mfo = int(bars["mfo"].max()); full_dm = S.decision_mfos(30, max_mfo)
    out = {}
    for m in D_MULTS:
        bm = _scale_bands(base_bands, m)
        tr = E.run(bars, bm, full_dm, exit_check="every_bar")
        out[m] = add_pnl(tr, atr_by_date)
    return out


def run_design_D(bars, base_bands, *, select="sharpe", verbose=False):
    """Returns (design, baseline, flat, picks): WFO-selected-multiplier trades, the
    k=1.0 baseline, and the fixed k=1.5 book, each concatenated across OOS folds with
    net_atr attached. Selection is train-window day-R Sharpe (or sumR), applied OOS."""
    atr_by_date = bars.groupby("sdate")["atr"].first()
    cfgs = _d_configs(bars, base_bands, atr_by_date)
    design_parts, base_parts, flat_parts, picks = [], [], [], []
    for ty, (tr_lo, tr_hi), (te_lo, te_hi) in folds(bars["sdate"].unique()):
        best, best_val = None, -np.inf
        for m, tr in cfgs.items():
            trn = tr[(tr["date"] >= tr_lo) & (tr["date"] <= tr_hi)]
            s = score(trn)
            val = s["sharpe"] if select == "sharpe" else s["sumR"]
            if s["n"] >= 100 and val > best_val:
                best_val, best = val, m
        if best is None:
            best = D_BASE_MULT
        picks.append((ty, best))

        def slc(tr):
            return tr[(tr["date"] >= te_lo) & (tr["date"] <= te_hi)]
        design_parts.append(slc(cfgs[best]))
        base_parts.append(slc(cfgs[D_BASE_MULT]))
        flat_parts.append(slc(cfgs[D_FLAT_MULT]))
        if verbose:
            print(f"  {ty}: pick k={best:.2f} (train {select}={best_val:.2f})")
    design = pd.concat(design_parts, ignore_index=True)
    baseline = pd.concat(base_parts, ignore_index=True)
    flat = pd.concat(flat_parts, ignore_index=True)
    return design, baseline, flat, picks


def _d_grid_table(cfgs, lo, hi):
    """Full-OOS per-multiplier stats over [lo, hi] -- the shape of the k curve."""
    print(f"  {'k':>5s} {'n':>5s} {'sumR':>8s} {'dayR_t':>7s} {'Sharpe':>7s} "
          f"{'R/trade':>8s}")
    for m in D_MULTS:
        tr = cfgs[m]; tr = tr[(tr["date"] >= lo) & (tr["date"] <= hi)]
        s = score(tr)
        tag = " <-base" if m == D_BASE_MULT else (" <-flat" if m == D_FLAT_MULT else "")
        print(f"  {m:>5.2f} {s['n']:>5d} {s['sumR']:>+8.2f} {s['dayR_t']:>+7.2f} "
              f"{s['sharpe']:>7.2f} {s['R_per_trade']:>+8.4f}{tag}")


def run_D_real():
    bars, base_bands, _ = _load_real()
    lo = pd.Timestamp(TEST_YEARS[0], 1, 1); hi = pd.Timestamp(TEST_YEARS[-1], 12, 31)
    print("=== DESIGN D (real tape): walk-forward the noise-area vol multiplier k ===")
    print(f"band = ref*(1 +/- k*sigma); continuous_stop (every-bar stop). grid k in {D_MULTS}")
    print(f"folds: rolling {TRAIN_YEARS}y/1y/{EMBARGO_DAYS}d embargo, test "
          f"{TEST_YEARS[0]}-{TEST_YEARS[-1]}; scored in R (net/atr)\n")

    atr_by_date = bars.groupby("sdate")["atr"].first()
    cfgs = _d_configs(bars, base_bands, atr_by_date)
    print("full-OOS shape of the k curve (is any width better than k=1.0?):")
    _d_grid_table(cfgs, lo, hi)

    for sel in ("sharpe", "sumR"):
        design, baseline, flat, picks = run_design_D(bars, base_bands, select=sel,
                                                     verbose=(sel == "sharpe"))
        sd = score(design); sb = score(baseline); sf = score(flat)
        print(f"\n[select={sel}]")
        print(f"  baseline k=1.0 : n={sb['n']:>4d} sumR={sb['sumR']:+.2f} "
              f"dayR_t={sb['dayR_t']:+.2f} Sh={sb['sharpe']:.2f}")
        print(f"  WFO-selected k : n={sd['n']:>4d} sumR={sd['sumR']:+.2f} "
              f"dayR_t={sd['dayR_t']:+.2f} Sh={sd['sharpe']:.2f}  "
              f"UPLIFT dR={sd['sumR']-sb['sumR']:+.2f} Sh {sb['sharpe']:.2f}->{sd['sharpe']:.2f}")
        print(f"  flat k=1.5     : n={sf['n']:>4d} sumR={sf['sumR']:+.2f} "
              f"dayR_t={sf['dayR_t']:+.2f} Sh={sf['sharpe']:.2f}  "
              f"UPLIFT dR={sf['sumR']-sb['sumR']:+.2f} Sh {sb['sharpe']:.2f}->{sf['sharpe']:.2f}")
        from collections import Counter
        print(f"  picks: {Counter(m for _, m in picks).most_common()}")

    # fill-feasibility (rule 1/2): flat k=1.5 (widest routinely-traded book here),
    # next_open vs signal_close. A wider band selects more-extreme breakouts -- verify
    # the honest next-open fill still carries it (no wick capture).
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(30, max_mfo)
    b15 = _scale_bands(base_bands, D_FLAT_MULT)
    no = E.run(bars, b15, dm, exit_check="every_bar", fill_mode="next_open")
    sc = E.run(bars, b15, dm, exit_check="every_bar", fill_mode="signal_close")
    art = sc["points"].mean() - no["points"].mean()
    print(f"\nfill check (k=1.5): next_open={no['points'].mean():+.3f} "
          f"signal_close={sc['points'].mean():+.3f} artifact={art:+.3f}pt (want ~0)")


def run_D_null(ndraw=30, select="sharpe"):
    bars, base_bands, _ = _load_real()
    print(f"=== DESIGN D Null-C twin ({ndraw} draws, select={select}) ===")
    print("verdict: WFO-select-k and flat-k=1.5 are real only if their OOS uplift over")
    print("k=1.0 beats the Null-C uplift distribution by z>=2 in NET R (rule 17/24).\n")
    d, b, f, _ = run_design_D(bars, base_bands, select=select)
    sb = score(b)
    real_wfo = score(d)["sumR"] - sb["sumR"]
    real_wfo_sh = score(d)["sharpe"] - sb["sharpe"]
    real_flat = score(f)["sumR"] - sb["sumR"]
    real_flat_sh = score(f)["sharpe"] - sb["sharpe"]
    print(f"REAL uplift vs k=1.0: WFO sumR={real_wfo:+.2f} (dSh={real_wfo_sh:+.3f})  "
          f"flat1.5 sumR={real_flat:+.2f} (dSh={real_flat_sh:+.3f})")

    nu_wfo, nu_flat, nu_wfo_sh, nu_flat_sh = [], [], [], []
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=6000 + k)
        nbands = S.noise_bands(nb, LOOKBACK)
        d, b, f, _ = run_design_D(nb, nbands, select=select)
        sb = score(b)
        nu_wfo.append(score(d)["sumR"] - sb["sumR"])
        nu_flat.append(score(f)["sumR"] - sb["sumR"])
        nu_wfo_sh.append(score(d)["sharpe"] - sb["sharpe"])
        nu_flat_sh.append(score(f)["sharpe"] - sb["sharpe"])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()

    def line(tag, real, arr):
        a = np.array(arr); sd = a.std(ddof=1)
        z = (real - a.mean()) / sd if sd > 0 else np.nan
        print(f"{tag:<16s} real={real:+7.2f}  null={a.mean():+7.2f} +/- {sd:5.2f}  "
              f"z={z:+5.2f}  null>=real={float((a >= real).mean()):.2f}")
    print(f"{'':16s} {'':>7s}       {'':>7s}     {'':>5s}")
    line("WFO sumR", real_wfo, nu_wfo)
    line("flat1.5 sumR", real_flat, nu_flat)
    line("WFO dSharpe", real_wfo_sh, nu_wfo_sh)
    line("flat1.5 dSharpe", real_flat_sh, nu_flat_sh)
    print("\nVERDICT: real only if z>=2 on NET R AND not a shrinkage-only Sharpe gain.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "A"
    if cmd == "A":
        run_A_real()
    elif cmd == "B":
        run_B_real()
    elif cmd == "B_null":
        run_B_null(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif cmd == "C":
        run_C_real()
    elif cmd == "C_null":
        run_C_null(int(sys.argv[2]) if len(sys.argv) > 2 else 30,
                   float(sys.argv[3]) if len(sys.argv) > 3 else 0.80)
    elif cmd == "A_null":
        run_A_null(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif cmd == "D":
        run_D_real()
    elif cmd == "D_null":
        run_D_null(int(sys.argv[2]) if len(sys.argv) > 2 else 30,
                   sys.argv[3] if len(sys.argv) > 3 else "sharpe")
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
