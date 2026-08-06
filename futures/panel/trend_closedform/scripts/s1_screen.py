"""EXP-0001 -- does the trend-following closed form pre-screen the CME panel?

Runs every arm declared in `experiments/hypotheses/HYP-0001.md`:

  control 1  the identity check (predicted == realised at the same lag)
  K1         published lag-0 PHI vs realised executable (lag-1) P&L, gross + net
  control 3  the same, for PHI's autocorrelation and drift terms separately
  control 4  re-pairing null, cluster bootstrap, leave-one-class-out, de-duplicated
  K2         out-of-sample by era, against the degenerate prior-era-realised screen
  K3         the declared NQ > ES > YM/GC > RTY ordering, decomposed
  sensitivity spans {8,16,32,64,128}, the EWMA crossover, the 30-minute clock

    python -u -m futures.panel.trend_closedform.scripts.s1_screen [daily|slot30]

Writes artifacts/runs/EXP-0001/.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import closedform as C
from ..core import engine as E
from ..core import filters as F
from ..core import panel as P
from ..core import stats as S

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RUN = ROOT / "artifacts" / "runs" / "EXP-0001"

# ---- declared configuration (HYP-0001) ------------------------------------ #
PRIMARY_SPAN = 32.0
SPANS = (8.0, 16.0, 32.0, 64.0, 128.0)
CROSSOVER = (16.0, 64.0)
PRIMARY_LAG = 1                    # executable: decide at close(t), hold over t+2
COST_TICKS_ONE_WAY = 0.5           # half a measured increment; optimistic floor
COST_STRESS_TICKS = 1.0
ERAS = ((2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026))
MIN_ERA_OBS = 250                  # daily rows needed before an era is scored
MIN_ERA_OBS_SLOT = 5000
LADDER_YM = ["NQ", "ES", "YM", "RTY"]
LADDER_GC = ["NQ", "ES", "GC", "RTY"]


@dataclass
class Series:
    product: str
    asset_class: str
    x: np.ndarray                  # risk-unit returns
    vol: np.ndarray                # causal scale, price units per risk unit
    cost: np.ndarray               # one-way cost per contract, price units
    year: np.ndarray
    n_rows: int
    roll_frac: float


def build_series(clock: str) -> list[Series]:
    ticks = pd.read_csv(DATA / "ticks.csv")
    tick_map = {(r.product, int(r.year)): float(r.tick) for r in ticks.itertuples()}
    out: list[Series] = []
    if clock == "daily":
        df = pd.read_parquet(DATA / "daily.parquet")
        for prod, g in df.groupby("product", sort=False):
            g = g.sort_values("sdate").reset_index(drop=True)
            ru = P.risk_units(g["close"], g["roll"])
            year = g["sdate"].dt.year.to_numpy()
            tk = np.array([tick_map.get((prod, int(y)), np.nan) for y in year])
            out.append(Series(prod, P.PANEL[prod], ru["x"].to_numpy(),
                              ru["vol"].to_numpy(), COST_TICKS_ONE_WAY * tk,
                              year, len(g), float(g["roll"].mean())))
    elif clock == "slot30":
        df = pd.read_parquet(DATA / "slot30.parquet")
        for prod, g in df.groupby("product", sort=False):
            g = g.sort_values(["sdate", "slot"], kind="mergesort").reset_index(drop=True)
            ru = P.slot_risk_units(g)
            year = g["sdate"].dt.year.to_numpy()
            tk = np.array([tick_map.get((prod, int(y)), np.nan) for y in year])
            out.append(Series(prod, P.PANEL[prod], ru["x"].to_numpy(),
                              ru["vol"].to_numpy(), COST_TICKS_ONE_WAY * tk,
                              year, len(g), float(g["roll"].mean())))
    else:
        raise ValueError(clock)
    return out


def era_of(year: np.ndarray) -> np.ndarray:
    out = np.full(year.shape, -1, dtype=np.int64)
    for i, (lo, hi) in enumerate(ERAS):
        out[(year >= lo) & (year <= hi)] = i
    return out


def _annual_oos(series: list[Series], w: np.ndarray, min_obs_est: int,
                min_obs_real: int, est_years: int = 4) -> dict | None:
    """PHI from a fixed trailing `est_years` window, scored on the next year."""
    M = w.size
    recs = []
    for s in series:
        _, pnl = E.run(s.x, w, lag=PRIMARY_LAG)
        years = np.unique(s.year)
        for y in years:
            est = (s.year >= y - est_years) & (s.year <= y - 1)
            real = s.year == y
            if est.sum() < min_obs_est:
                continue
            booked_real = real & np.isfinite(pnl)
            booked_est = est & np.isfinite(pnl)
            if booked_real.sum() < min_obs_real or booked_est.sum() < min_obs_est // 2:
                continue
            try:
                mom = C.moments(np.where(est, s.x, np.nan), maxlag=M + PRIMARY_LAG + 1)
                phi = C.phi_from_rho(w, mom.rho, mom.sr, lag=PRIMARY_LAG)
            except ValueError:
                continue
            recs.append({"product": s.product, "asset_class": s.asset_class,
                         "year": int(y), "phi": phi,
                         "naive": float(pnl[booked_est].mean()),
                         "real": float(pnl[booked_real].mean())})
    fr = pd.DataFrame(recs)
    if not fr.empty:
        keep = fr.groupby("year")["product"].transform("size") >= 8
        fr = fr.loc[keep].reset_index(drop=True)
    return {"frame": fr}


# --------------------------------------------------------------------------- #
def main(clock: str = "daily") -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    series = build_series(clock)
    min_era = MIN_ERA_OBS if clock == "daily" else MIN_ERA_OBS_SLOT
    w_primary = F.ewma_kernel(PRIMARY_SPAN)
    M = w_primary.size

    emit("=" * 78)
    emit(f"EXP-0001  trend-following closed form as an instrument pre-screen")
    emit(f"clock={clock}  primary span={PRIMARY_SPAN:g} (kernel M={M})  "
         f"executable lag={PRIMARY_LAG}")
    emit(f"cost={COST_TICKS_ONE_WAY} measured increment one way (stress "
         f"{COST_STRESS_TICKS}); products={len(series)}")
    emit("=" * 78)

    # ------------------------------------------------------------ control 1 --
    emit("")
    emit("CONTROL 1 -- IDENTITY CHECK (implementation, not evidence)")
    emit("PHI computed on the engine's own booked rows must EQUAL realised P&L at")
    emit("the same lag.  This is exact algebra; it is reported so that any later")
    emit("disagreement can be attributed to the market rather than to the code.")
    worst = 0.0
    id_rows = []
    for s in series:
        for lag in (0, 1):
            ok = E.booked_mask(s.x, w_primary, lag=lag)
            mom = C.booked_moments(s.x, maxlag=M, lag=lag, ok=ok)
            pred = C.predicted_pnl(w_primary, mom)
            res, _ = E.run(s.x, w_primary, lag=lag)
            err = abs(pred - res.gross)
            worst = max(worst, err)
            id_rows.append({"product": s.product, "lag": lag, "predicted": pred,
                            "realised": res.gross, "abs_err": err, "n": res.n})
    pd.DataFrame(id_rows).to_csv(RUN / f"identity_{clock}.csv", index=False)
    emit(f"  worst |predicted - realised| over {len(series)} products x 2 lags: "
         f"{worst:.3e}")
    emit(f"  -> {'PASS' if worst < 1e-9 else 'FAIL'} (tolerance 1e-9)")
    if worst >= 1e-9:
        emit("  STOP: the machinery does not reproduce its own algebra.")
        (RUN / f"screen_{clock}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    # -------------------------------------------------------- primary table --
    emit("")
    emit("PER-PRODUCT TABLE (primary cell)")
    emit("PHI0      the article's published closed form, lag 0, ordinary")
    emit("          full-sample autocorrelations -- the number a screener computes")
    emit("PHI0_ac   its autocorrelation term alone      PHI0_dr  its drift term alone")
    emit("gross/net realised P&L per period, risk units, EXECUTABLE lag-1 rule")
    emit("turn      measured turnover; turn_cf the closed form's market-independent")
    emit("          prediction (2/sqrt(pi))sqrt(1-nu) -- identical for every product")
    rows = []
    turn_cf = C.turnover_closed_form(PRIMARY_SPAN)
    for s in series:
        mom = C.moments(s.x, maxlag=M + PRIMARY_LAG + 1)
        phi0 = C.phi_from_rho(w_primary, mom.rho, mom.sr, lag=0)
        phi0_ac = C.phi_from_rho(w_primary, mom.rho, 0.0, lag=0)
        phi0_dr = float(mom.sr ** 2 * w_primary.sum())
        phi1 = C.phi_from_rho(w_primary, mom.rho, mom.sr, lag=PRIMARY_LAG)
        scale = F.position_scale(w_primary)
        res, pnl = E.run(s.x, w_primary, lag=PRIMARY_LAG, vol=s.vol,
                         cost_per_contract=s.cost)
        res_stress, _ = E.run(s.x, w_primary, lag=PRIMARY_LAG, vol=s.vol,
                              cost_per_contract=s.cost * (COST_STRESS_TICKS
                                                          / COST_TICKS_ONE_WAY))
        rows.append({
            "product": s.product, "asset_class": s.asset_class, "n": res.n,
            "roll_frac": s.roll_frac, "sr": mom.sr, "rho1": mom.rho[1],
            "rho2": mom.rho[2], "var": mom.var,
            "PHI0": phi0, "PHI0_ac": phi0_ac, "PHI0_dr": phi0_dr, "PHI1": phi1,
            "pred0": mom.var * phi0 / scale, "pred1": mom.var * phi1 / scale,
            "gross": res.gross, "net": res.net, "net_stress": res_stress.net,
            "cost": res.cost, "turnover_contracts": res.turnover,
            "turnover_pos": res.turnover_pos, "sharpe_gross": res.sharpe_gross,
        })
    tab = pd.DataFrame(rows)
    tab.to_csv(RUN / f"per_product_{clock}.csv", index=False)

    emit("")
    emit(f"{'prod':<5}{'cls':<7}{'n':>7}{'SR':>8}{'rho1':>8}{'PHI0':>9}{'PHI0_ac':>9}"
         f"{'PHI0_dr':>9}{'gross':>9}{'net':>9}{'turn_p':>8}{'cost':>9}")
    for _, r in tab.iterrows():
        emit(f"{r['product']:<5}{r['asset_class']:<7}{int(r['n']):>7}{r['sr']:>8.4f}"
             f"{r['rho1']:>8.4f}{r['PHI0']:>9.4f}{r['PHI0_ac']:>9.4f}"
             f"{r['PHI0_dr']:>9.4f}{r['gross']:>9.4f}{r['net']:>9.4f}"
             f"{r['turnover_pos']:>8.3f}{r['cost']:>9.4f}")
    ppy = 250.0 if clock == "daily" else 250.0 * 46
    tab["sharpe_ann_gross"] = tab["sharpe_gross"] * np.sqrt(ppy)
    tab["sharpe_ann_net"] = (tab["net"] / (tab["gross"] / tab["sharpe_gross"])) * np.sqrt(ppy)
    tab.to_csv(RUN / f"per_product_{clock}.csv", index=False)
    emit("")
    emit("  DEPLOYABILITY (rules 20, 21) -- annualised Sharpe of the executable rule")
    emit(f"  gross: median {tab['sharpe_ann_gross'].median():+.3f}  "
         f"best {tab.loc[tab['sharpe_ann_gross'].idxmax(), 'product']} "
         f"{tab['sharpe_ann_gross'].max():+.3f}  "
         f"worst {tab.loc[tab['sharpe_ann_gross'].idxmin(), 'product']} "
         f"{tab['sharpe_ann_gross'].min():+.3f}")
    emit(f"  net:   median {tab['sharpe_ann_net'].median():+.3f}  "
         f"products with net > 0: {int((tab['net'] > 0).sum())} / {len(tab)}")
    emit(f"  cost as a share of gross, median over products with gross > 0: "
         f"{(tab.loc[tab['gross'] > 0, 'cost'] / tab.loc[tab['gross'] > 0, 'gross']).median():.3f}")
    emit("")
    emit(f"  turnover of the RISK-UNIT position: min {tab['turnover_pos'].min():.4f} "
         f"max {tab['turnover_pos'].max():.4f}, closed form {turn_cf:.4f}")
    emit("  The article's claim that turnover depends only on the filter span and")
    emit("  not on the market is the one part of it that holds exactly here.")
    emit("  (Contract turnover is in each product's own price scale and is NOT")
    emit("  comparable across products; it is in the CSV, used only inside cost.)")

    # ------------------------------------------------- identity in disguise --
    emit("")
    emit("HOW MUCH OF K1 IS ALGEBRA?  (asked before K1 is read, not after)")
    emit("PHI0 and the realised lag-1 P&L share 159 of their 160 weighted lags --")
    emit("PHI0 sums rho(1..160), the realised rule is an exact identity with")
    emit("PHI1 = rho(2..161).  So a high K1 is mostly the SAME statistic at a")
    emit("one-lag offset, and the honest question is how much the offset moves it.")
    emit(f"  Spearman(PHI0, PHI1)                    {S.spearman(tab['PHI0'], tab['PHI1']):+.4f}")
    emit(f"  Spearman(PHI1, realised gross)          {S.spearman(tab['PHI1'], tab['gross']):+.4f}"
         "   <- near +1 is expected: identity")
    emit(f"  Spearman(pred1, realised gross)         {S.spearman(tab['pred1'], tab['gross']):+.4f}"
         "   <- same, in engine units")
    emit("  Read K1 as 'the published lag-0 form survives the execution lag and the")
    emit("  cost', NOT as 'the formula predicts'.  Only K2 can say that.")

    # ------------------------------------------------------------------- K1 --
    cls = tab["asset_class"].to_numpy()
    emit("")
    emit("K1 -- DOES THE PUBLISHED NUMBER PREDICT THE DEPLOYABLE RESULT?")
    emit("gate: Spearman > +0.50 with a cluster-bootstrap CI excluding zero.")

    def score(name: str, pred: np.ndarray, real: np.ndarray,
              mask: np.ndarray | None = None) -> dict:
        m = np.ones(len(tab), dtype=bool) if mask is None else mask
        ci = S.cluster_bootstrap_spearman(pred[m], real[m], cls[m], draws=5000, seed=7)
        _, frac = S.repairing_null_spearman(pred[m], real[m], draws=20000, seed=11)
        emit(f"  {name:<44}{str(ci):<44} null frac>=real {frac:.4f}")
        return {"arm": name, "rho": ci.point, "lo": ci.lo, "hi": ci.hi,
                "n": ci.n, "k": ci.n_clusters, "null_frac": frac}

    k1 = []
    gross = tab["gross"].to_numpy()
    net = tab["net"].to_numpy()
    phi0 = tab["PHI0"].to_numpy()
    k1.append(score("PHI0 -> gross  [PRIMARY]", phi0, gross))
    k1.append(score("PHI0 -> net", phi0, net))
    k1.append(score("PHI0 -> net (cost stress 1.0)", phi0, tab["net_stress"].to_numpy()))
    emit("")
    emit("  control 3 -- which TERM of PHI carries the ranking?")
    k1.append(score("PHI0 autocorrelation term -> gross", tab["PHI0_ac"].to_numpy(), gross))
    k1.append(score("PHI0 drift term only -> gross", tab["PHI0_dr"].to_numpy(), gross))
    k1.append(score("bare SR (no formula at all) -> gross", tab["sr"].to_numpy(), gross))
    k1.append(score("bare rho(1) -> gross", tab["rho1"].to_numpy(), gross))
    emit("")
    emit("  robustness -- panel composition")
    dedup = ~tab["product"].isin(P.MINI_DUPLICATES).to_numpy()
    light = (tab["roll_frac"] < 0.10).to_numpy()
    k1.append(score("PHI0 -> gross, de-duplicated (no MGC/MCL)", phi0, gross, dedup))
    k1.append(score("PHI0 -> gross, roll_frac < 10%", phi0, gross, light))
    loo = S.leave_one_cluster_out(phi0, gross, cls)
    emit("  leave-one-asset-class-out Spearman(PHI0, gross): "
         + "  ".join(f"-{k}:{v:+.3f}" for k, v in loo.items()))

    emit("")
    emit("  LIQUIDITY CONFOUND -- is the net arm a trend result or a cost ranking?")
    emit("  Bid-ask bounce makes rho(1) negative in proportion to tick-over-")
    emit("  volatility, and that same ratio IS the cost.  So PHI0 and net P&L can")
    emit("  share a driver that has nothing to do with trend.  If rho(cost,net) is")
    emit("  large, the net arm is a liquidity ranking wearing the formula's coat.")
    cost_v = tab["cost"].to_numpy()
    conf = {"rho(rho1, cost)": S.spearman(tab["rho1"].to_numpy(), cost_v),
            "rho(PHI0, cost)": S.spearman(phi0, cost_v),
            "rho(cost, gross)": S.spearman(cost_v, gross),
            "rho(cost, net)": S.spearman(cost_v, net)}
    emit("  " + "   ".join(f"{k} {v:+.3f}" for k, v in conf.items()))
    k1.append({"arm": "confound", **conf})
    pd.DataFrame(k1).to_csv(RUN / f"k1_{clock}.csv", index=False)

    # ------------------------------------------------------------------- K2 --
    emit("")
    emit("K2 -- OUT-OF-SAMPLE BY ERA (the actual pre-screen question)")
    emit("PHI estimated on era k must rank realised P&L on era k+1, and must beat")
    emit("the degenerate screen: era k's own realised P&L, which uses no theory.")
    emit(f"eras: " + ", ".join(f"{lo}-{hi}" for lo, hi in ERAS)
         + f"; an era is scored when it has >= {min_era} bookable rows")

    era_pred, era_real = {}, {}
    for s in series:
        era = era_of(s.year)
        _, pnl = E.run(s.x, w_primary, lag=PRIMARY_LAG)
        for k in range(len(ERAS)):
            m = era == k
            booked = m & np.isfinite(pnl)
            if booked.sum() < min_era:
                continue
            era_real[(s.product, k)] = float(pnl[booked].mean())
            xe = np.where(m, s.x, np.nan)
            try:
                mom = C.moments(xe, maxlag=M + PRIMARY_LAG + 1)
                era_pred[(s.product, k)] = C.phi_from_rho(w_primary, mom.rho, mom.sr,
                                                          lag=PRIMARY_LAG)
            except ValueError:
                pass

    k2_rows, pooled = [], {"phi": [], "naive": [], "real": [], "trans": []}
    for k in range(len(ERAS) - 1):
        prods = [s.product for s in series
                 if (s.product, k) in era_pred and (s.product, k + 1) in era_real]
        if len(prods) < 5:
            emit(f"  {ERAS[k][0]}-{ERAS[k][1]} -> {ERAS[k+1][0]}-{ERAS[k+1][1]}: "
                 f"only {len(prods)} products, skipped")
            continue
        pv = np.array([era_pred[(p, k)] for p in prods])
        nv = np.array([era_real[(p, k)] for p in prods])
        rv = np.array([era_real[(p, k + 1)] for p in prods])
        cl = np.array([P.PANEL[p] for p in prods])
        r_phi = S.spearman(pv, rv)
        r_nai = S.spearman(nv, rv)
        ci = S.cluster_bootstrap_spearman(pv, rv, cl, draws=5000, seed=13)
        emit(f"  {ERAS[k][0]}-{ERAS[k][1]} -> {ERAS[k+1][0]}-{ERAS[k+1][1]}  "
             f"n={len(prods):>2}   PHI {r_phi:+.4f} {str(ci)[7:]:<26} "
             f"degenerate(prior realised) {r_nai:+.4f}")
        k2_rows.append({"from": ERAS[k][0], "to": ERAS[k + 1][0], "n": len(prods),
                        "rho_phi": r_phi, "lo": ci.lo, "hi": ci.hi,
                        "rho_naive": r_nai})
        pooled["phi"] += list(S.rankdata(pv) / (len(pv) + 1))
        pooled["naive"] += list(S.rankdata(nv) / (len(nv) + 1))
        pooled["real"] += list(S.rankdata(rv) / (len(rv) + 1))
        pooled["trans"] += [k] * len(prods)
    if pooled["phi"]:
        pp = np.array(pooled["phi"])
        pn = np.array(pooled["naive"])
        pr = np.array(pooled["real"])
        emit(f"  POOLED (within-transition ranks, n={pp.size}): "
             f"PHI {S.spearman(pp, pr):+.4f}   degenerate {S.spearman(pn, pr):+.4f}")
    pd.DataFrame(k2_rows).to_csv(RUN / f"k2_{clock}.csv", index=False)

    # --------------------------------------------------- K2b: annual OOS ----
    emit("")
    emit("K2b -- ANNUAL OUT-OF-SAMPLE, EQUAL 4-YEAR ESTIMATION WINDOWS")
    emit("Three era transitions is too few to settle K2, so the same question is")
    emit("asked once per year: PHI from the trailing 4 years ranks the NEXT year.")
    emit("The window is a FIXED length for every product and every year, because a")
    emit("growing window has a shrinking sampling sd and would make later years'")
    emit("PHI systematically better estimated than earlier ones (LEARNINGS")
    emit("2026-08-03).  The degenerate benchmark uses the identical window.")
    ann = _annual_oos(series, w_primary, min_obs_est=(500 if clock == "daily" else 10_000),
                      min_obs_real=(100 if clock == "daily" else 2_000))
    if ann is None or ann["frame"].empty:
        emit("  insufficient data for the annual arm")
    else:
        fr = ann["frame"]
        fr.to_csv(RUN / f"k2b_annual_{clock}.csv", index=False)
        emit(f"{'year':>6}{'n':>5}{'rho(PHI)':>11}{'rho(degenerate)':>17}")
        for y, g in fr.groupby("year"):
            emit(f"{int(y):>6}{len(g):>5}"
                 f"{S.spearman(g['phi'], g['real']):>11.4f}"
                 f"{S.spearman(g['naive'], g['real']):>17.4f}")
        a_iv, b_iv, d_iv = S.cluster_bootstrap_pooled_diff(
            fr["phi"].to_numpy(), fr["naive"].to_numpy(), fr["real"].to_numpy(),
            fr["year"].to_numpy(), fr["asset_class"].to_numpy(),
            fr["product"].to_numpy(), draws=3000, seed=17)
        emit("")
        emit(f"  pooled PHI          {a_iv}")
        emit(f"  pooled degenerate   {b_iv}")
        emit(f"  DIFFERENCE          {d_iv}"
             f"   {'excludes' if d_iv.excludes_zero() else 'SPANS'} zero")
        emit("  The difference is the decision statistic: two wide overlapping")
        emit("  intervals can still differ reliably, and 'does the theory beat the")
        emit("  no-theory benchmark' is a question about the difference.")

        emit("")
        emit("  WHY -- three diagnostics, each one line")
        emit(f"  (i)   Spearman(PHI, degenerate) within year, pooled  "
             f"{S.pooled_rank_spearman(fr['phi'], fr['naive'], fr['year']):+.4f}")
        emit("        PHI over a window IS that window's in-sample trend P&L plus a")
        emit("        drift term, so 'the theory' and 'the backtest' are near enough")
        emit("        the same predictor.  The closed form does not add information")
        emit("        to a backtest; it is the backtest, written in closed form.")
        prev = fr.copy()
        prev["year"] = prev["year"] + 1
        j = fr.merge(prev[["product", "year", "phi", "real"]], on=["product", "year"],
                     suffixes=("", "_prev"))
        emit(f"  (ii)  rank persistence of PHI itself, year to year     "
             f"{S.pooled_rank_spearman(j['phi_prev'], j['phi'], j['year']):+.4f}"
             f"   (n={len(j)})")
        emit(f"  (iii) rank persistence of REALISED P&L, year to year   "
             f"{S.pooled_rank_spearman(j['real_prev'], j['real'], j['year']):+.4f}")
        emit("        If a product's own PHI does not persist from one window to the")
        emit("        next, no screen built on it can rank the next window -- and the")
        emit("        limit is then the STABILITY of the autocorrelation function,")
        emit("        not this particular formula.  That is a claim about every")
        emit("        autocorrelation-based screen at this horizon, not just this one.")
        j.to_csv(RUN / f"k2b_persistence_{clock}.csv", index=False)

    # ------------------------------------------------------------------- K3 --
    emit("")
    emit("K3 -- THE DECLARED ORDERING (reported, decomposed, not a standalone gate)")
    emit("(a) does PHI reproduce the ordering of the REALISED EWMA rule -- a real test")
    emit("(b) does the realised EWMA ladder itself match noise_vwap's NQ>ES>YM/GC>RTY")
    emit("    -- a cross-family question: that ladder is an intraday BARRIER breakout")
    emit("    result, and the source item's own traps section says not to benchmark")
    emit("    the closed form against it.")
    vals = {r["product"]: r for _, r in tab.iterrows()}
    for label, ladder in (("NQ>ES>YM>RTY", LADDER_YM), ("NQ>ES>GC>RTY", LADDER_GC)):
        for col, what in (("PHI0", "(b1) predicted PHI0"),
                          ("gross", "(b2) realised gross"),
                          ("net", "(b3) realised net")):
            d = {p: float(vals[p][col]) for p in ladder if p in vals}
            ok, tot, bad = S.kendall_tau_pairs(ladder, d)
            emit(f"  vs declared ladder: {what:<22}{label:<14} {ok}/{tot} adjacent pairs"
                 + (f"   failed: {', '.join(bad)}" if bad else ""))
        # (a) the real test: does PHI order these four the way REALISED does?
        realised_order = sorted(ladder, key=lambda p: -float(vals[p]["gross"]))
        d_phi = {p: float(vals[p]["PHI0"]) for p in ladder}
        ok, tot, bad = S.kendall_tau_pairs(realised_order, d_phi)
        emit(f"  (a) PHI0 vs the REALISED ordering {' > '.join(realised_order):<22}"
             f" {ok}/{tot} adjacent pairs"
             + (f"   failed: {', '.join(bad)}" if bad else ""))
        emit(f"      values  "
             + "  ".join(f"{p} PHI0 {float(vals[p]['PHI0']):+.4f} / gross "
                         f"{float(vals[p]['gross']):+.4f}" for p in ladder if p in vals))
        emit("")

    # ---------------------------------------------------------- sensitivity --
    emit("")
    emit("SENSITIVITY (a distribution, not an argmax -- HYP-0001 multiple-testing note)")
    emit(f"{'rule':<22}{'K1 rho(PHI0,gross)':>20}{'rho(PHI0,net)':>16}"
         f"{'median gross':>14}{'products net>0':>16}")
    sens = []
    kernels = [(f"ewma span {sp:g}", F.ewma_kernel(sp)) for sp in SPANS]
    kernels.append((f"crossover {CROSSOVER[0]:g}/{CROSSOVER[1]:g}",
                    F.crossover_kernel(*CROSSOVER)))
    for name, w in kernels:
        Mk = w.size
        pv, gv, nv = [], [], []
        for s in series:
            mom = C.moments(s.x, maxlag=Mk + PRIMARY_LAG + 1)
            pv.append(C.phi_from_rho(w, mom.rho, mom.sr, lag=0))
            res, _ = E.run(s.x, w, lag=PRIMARY_LAG, vol=s.vol, cost_per_contract=s.cost)
            gv.append(res.gross)
            nv.append(res.net)
        pv, gv, nv = np.array(pv), np.array(gv), np.array(nv)
        rg, rn = S.spearman(pv, gv), S.spearman(pv, nv)
        emit(f"{name:<22}{rg:>20.4f}{rn:>16.4f}{np.median(gv):>14.4f}"
             f"{int((nv > 0).sum()):>10} / {len(nv)}")
        sens.append({"rule": name, "rho_gross": rg, "rho_net": rn,
                     "median_gross": float(np.median(gv)),
                     "median_net": float(np.median(nv)),
                     "n_net_positive": int((nv > 0).sum()), "n": len(nv)})
    pd.DataFrame(sens).to_csv(RUN / f"sensitivity_{clock}.csv", index=False)

    (RUN / f"screen_{clock}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {RUN / f'screen_{clock}.txt'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "daily"))
