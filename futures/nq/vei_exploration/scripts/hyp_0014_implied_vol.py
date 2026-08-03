"""HYP-0014 / EXP-0017 -- does intraday IMPLIED volatility (VIX) add what past price cannot?

Backlog item 17 recorded "trade volatility as the object itself" as DATA-BLOCKED for want
of an intraday implied series; `futures/data/vix/` supplies one. Backlog item 13 names the
same gap from the other side: every feature tested so far is a function of PAST PRICE, and
finding P showed they all converge on the same saturated level-IC ceiling. VIX is the first
input that is not past price, so it is the first that can contain volatility which has been
SCHEDULED but has not yet happened.

The deciding metric is therefore NOT level IC (finding P: saturated, cannot discriminate)
but the EXPANSION-CALL log-MSE skill over persistence -- the cell EXP-0015 found the core
cannot handle (+0.008 NQ / +0.061 ES) and EXP-0016 found is still capable of moving
(+0.100 / +0.120 for a redundant control). Gates are declared in
`experiments/hypotheses/HYP-0014.md` and read ONLY on `core_vix`.

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0014_implied_vol {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ..core import analysis as A
from ..core import forward_vol as FV
from ..core import vix as VX

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0017"

FIRST_TEST_YEAR = 2016
NBOOT = 500
SEED = 20260731
IC_TOL = 5e-4
NOTEBOOK_IC = {("NQ", 2016, 2023): 0.8996, ("ES", 2016, 2023): 0.8886,
               ("NQ", 2024, None): 0.8503, ("ES", 2024, None): 0.8419}

#: KT2 bar, taken from EXP-0016's PUBLISHED redundant-level control before this run.
#: Beating the bare core (+0.008 NQ / +0.061 ES) is not evidence: three unrelated
#: past-price feature sets already do that.
EXPANSION_BAR = {"NQ": 0.100, "ES": 0.120}
CORE_EXPANSION = {"NQ": 0.008, "ES": 0.061}

VIX_CORE = ["vix_fwd30_bp", "vix_slot_z", "vrp_log_slot_z"]
LEVELS3 = ["rv_15m", "rv_60m", "rv_120m"]

ARMS: dict[str, list[str]] = {
    "core":          [FV.SLOT_MEDIAN, "range_rv_15m"],
    "core_vix":      [FV.SLOT_MEDIAN, "range_rv_15m"] + VIX_CORE,
    "core_vix_all":  [FV.SLOT_MEDIAN, "range_rv_15m"] + VX.VIX_ALL,
    "core_pastrv":   [FV.SLOT_MEDIAN, "range_rv_15m", "past_rv30_bp"],
    "core_levels3":  [FV.SLOT_MEDIAN, "range_rv_15m"] + LEVELS3,
    "vix_only":      VIX_CORE,
}
ALL_FEATURES = sorted({f for fs in ARMS.values() for f in fs})


def log_mse(actual, pred) -> float:
    return float(np.mean(np.square(np.log(np.clip(actual, 1e-9, None))
                                   - np.log(np.clip(pred, 1e-9, None)))))


def skill(actual, pred, base) -> float:
    e0 = log_mse(actual, base)
    return float(1.0 - log_mse(actual, pred) / e0) if e0 > 0 else np.nan


def main(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    log(f"=== HYP-0014 / EXP-0017 -- intraday IMPLIED volatility (VIX) vs the core ({inst}) ===")

    frame, q = FV.build_decision_frame(inst, candidates=True)
    log(f"\nfutures: {q['decision_rows']:,} decision rows over {q['sessions']:,} sessions "
        f"{q['first'].date()}..{q['last'].date()}")

    # ---- rule 23: the core must reproduce EXP-0011 before anything is compared to it -- #
    log("\nrule-23 reproduction of artifacts/runs/EXP-0011 "
        "(notebook sha256 ccb9f5e9..79606):")
    for (i, first, last), want in NOTEBOOK_IC.items():
        if i != inst:
            continue
        p = FV.walkforward_forecast(frame, first, last)
        got = spearmanr(p["fvol_bp"], p[FV.TARGET]).statistic
        ok = abs(got - want) <= IC_TOL
        log(f"  test years {first}..{last or 'end'}: n={len(p):,} IC {got:+.6f} vs "
            f"published {want:+.4f}  |diff| {abs(got - want):.2e}  {'PASS' if ok else 'FAIL'}")
        assert ok, "rule-23 reproduction failed"

    # ---- the VIX join, and what it costs (rule 9a) ---------------------------------- #
    d0, vq = VX.attach_vix(frame)
    log("\n--- rule 9a: the causal VIX join ---")
    log(f"  source: {vq['files']} contiguous TradingView tiles, {vq['rows']:,} bars "
        f"{str(vq['first'])[:10]}..{str(vq['last'])[:10]}, duplicate ts {vq['duplicate_ts']}")
    log(f"  median bars/session {vq['median_bars_per_session']:.0f}; frozen bars "
        f"{vq['frozen_bars']:,}; repeated closes {vq['repeat_close_bars']:,}; "
        f"VIX range {vq['min_close']:.2f}..{vq['max_close']:.2f}")
    log(f"  joined {vq['joined']:,}/{vq['decision_rows']:,} decision rows "
        f"({vq['join_rate']:.4f}); quote staleness median {vq['stale_median_min']:.1f} min, "
        f"p99 {vq['stale_p99_min']:.1f} min, >20 min on {vq['stale_gt_20min']} rows")
    unjoined = d0[d0.vix.isna()]
    per_session = d0.groupby("sdate").size()
    partial = sum(1 for s in unjoined.sdate.unique() if per_session[s] < 11)
    log(f"  UNJOINED: {len(unjoined):,} rows over {unjoined.sdate.nunique()} sessions, of "
        f"which {partial} are PARTIAL futures sessions (<11 decisions).")
    log("  These are US market holidays: CME trades a shortened session, cash VIX does not")
    log("  publish at all. The loss is therefore WHOLE-SESSION, not slot-selective, and the")
    log("  holiday calendar is known in advance, so the exclusion is causal.")
    jr = d0.groupby("mfo").vix.apply(lambda s: s.notna().mean())
    log("  join rate by slot: " + ", ".join(f"{int(m)}:{v:.4f}" for m, v in jr.items()))

    # ---- the common sample: every arm sees identical rows ---------------------------- #
    need = ALL_FEATURES + [FV.TARGET, "past_rv30_bp"]
    common = d0.dropna(subset=need).copy()
    common = common[(common.past_rv30_bp > 0) & (common[FV.TARGET] > 0)]
    log(f"\ncommon sample: {len(common):,} of {len(d0):,} decision rows "
        f"({len(common) / len(d0):.2%}); every arm trains and tests on these rows.")
    keep = (common.groupby("mfo").size() / d0.groupby("mfo").size()).sort_index()
    log("  retention by slot: " + ", ".join(f"{int(m)}:{v:.3f}" for m, v in keep.items()))
    log(f"  worst {keep.min():.3f}, best {keep.max():.3f} -> "
        f"{'UNIFORM (pass signal)' if keep.max() - keep.min() < 0.05 else 'TIME-OF-DAY DEPENDENT (reportable)'}")

    # ---- DESCRIPTIVE: what IS the relationship? -------------------------------------- #
    Tz = common[FV.TARGET].to_numpy(float)
    sz = common.mfo.to_numpy(float)
    log("\n--- DESCRIPTIVE: univariate association with realised forward 30-min RV ---")
    log(f"{'feature':<26}{'pooled IC':>11}{'within-slot IC':>16}   note")
    notes = {
        "past_rv30_bp": "persistence benchmark (not a core feature)",
        "range_rv_15m": "the core's only state variable",
        FV.SLOT_MEDIAN: "the core's seasonal",
        "vix_fwd30_bp": "VIX rescaled to a 30-min expected move, bp",
        "vrp_log": "log(implied30/realised30) -- see the denominator warning",
        "vix_slot_z": "VIX vs its own trailing same-slot norm",
    }
    for c in ["past_rv30_bp", "range_rv_15m", FV.SLOT_MEDIAN, "vix_fwd30_bp",
              "vix_slot_z", "vrp_log", "vrp_log_slot_z", "vix_chg_15m", "vix_chg_60m",
              "vix_chg_since_open", "vix_overnight_chg", "vix_intraday_range"]:
        v = common[c].to_numpy(float)
        m = np.isfinite(v)
        log(f"{c:<26}{spearmanr(v[m], Tz[m]).statistic:>+11.4f}"
            f"{A.within_slot_ic_arrays(v[m], Tz[m], sz[m]):>+16.4f}   {notes.get(c, '')}")

    log("\n--- the VARIANCE RISK PREMIUM is mostly its own DENOMINATOR (finding H) ---")
    log(f"  corr(vrp_log, past_rv30_bp)   = "
        f"{spearmanr(common.vrp_log, common.past_rv30_bp).statistic:+.4f}")
    log(f"  corr(vix_fwd30_bp, past_rv30) = "
        f"{spearmanr(common.vix_fwd30_bp, common.past_rv30_bp).statistic:+.4f}")
    log(f"  corr(vix_chg_15m, past_ret30) = "
        f"{spearmanr(common.vix_chg_15m, common.past_ret30_bp).statistic:+.4f}"
        "   <- VIX CHANGE is substantially a restatement of past price")
    log("  VIX is a daily-scale quantity: it barely moves across a 30-minute decision")
    log("  clock, so log(implied)-log(realised) is dominated by the realised leg. The")
    log("  degenerate control is the bare denominator, exactly as in finding H.")

    log("\n--- and the RAW premium is a CLOCK (finding I): implied is flat, realised decays ---")
    g = common.groupby("mfo").agg(vrp=("vrp_log", "mean"), implied=("vix_fwd30_bp", "mean"),
                                  realised=("past_rv30_bp", "mean"),
                                  fwd=(FV.TARGET, "mean"))
    g["imp_over_real"] = g.implied / g.realised
    log(f"  {'mfo':>5}{'vrp_log':>10}{'implied bp':>12}{'realised bp':>13}"
        f"{'fwd bp':>9}{'imp/real':>10}")
    for m, r in g.iterrows():
        log(f"  {int(m):>5}{r.vrp:>+10.3f}{r.implied:>12.2f}{r.realised:>13.2f}"
            f"{r.fwd:>9.2f}{r.imp_over_real:>10.3f}")
    log("  A fixed threshold on the raw premium is therefore a time-of-day selector;")
    log("  the slot-z form is the one used as a feature.")

    # ---- run every arm ---------------------------------------------------------------- #
    log(f"\n--- walk-forward, expanding window, first tested year {FIRST_TEST_YEAR}, "
        "one frozen learner ---")
    preds = None
    for arm, feats in ARMS.items():
        p = FV.walkforward_forecast(common, FIRST_TEST_YEAR, features=feats,
                                    pred_col=f"p_{arm}")
        cols = ["ts_utc", f"p_{arm}"]
        preds = p[cols] if preds is None else preds.merge(p[cols], on="ts_utc", how="inner")
        log(f"  {arm:<14} {len(feats)} feature(s): {', '.join(feats)}")
    d = common.merge(preds, on="ts_utc", how="inner").copy()
    d["date"] = d["sdate"]
    log(f"  evaluated on {len(d):,} rows, {d.date.nunique():,} sessions, "
        f"{d.year.min()}..{d.year.max()}")

    Aa = d[FV.TARGET].to_numpy(float)
    P = d["past_rv30_bp"].to_numpy(float)
    slot = d["mfo"].to_numpy(float)
    rng = np.random.default_rng(SEED)

    # ---- SECONDARY (saturated, reported, NOT deciding) --------------------------------- #
    log("\n--- SECONDARY: within-slot IC vs realised forward RV, paired delta over `core` ---")
    log("finding P: this axis is SATURATED at +0.009..+0.011 for every feature set tried,")
    log("so it is reported for comparability and CANNOT decide between arms.")
    log(f"{'arm':<14}{'within-slot IC':>15}{'pooled IC':>11}{'delta vs core':>15}"
        f"{'90% CI':>22}{'log-MSE':>9}{'MAE bp':>8}")
    rows = []
    for arm in ARMS:
        col = f"p_{arm}"
        v = d[col].to_numpy(float)
        wic = A.within_slot_ic_arrays(v, Aa, slot)
        pic = spearmanr(v, Aa).statistic
        lm, mae = log_mse(Aa, v), float(np.mean(np.abs(Aa - v)))
        if arm == "core":
            dl = lo = hi = np.nan
            ci = "(baseline)"
        else:
            dl, lo, hi = A.block_boot_within_slot_ic_delta(
                d, col, "p_core", FV.TARGET, rng, nboot=NBOOT, date_col="date")
            ci = f"[{lo:+.4f},{hi:+.4f}]" + (" *" if lo * hi > 0 else "")
        log(f"{arm:<14}{wic:>+15.4f}{pic:>+11.4f}"
            f"{('' if arm == 'core' else f'{dl:+.4f}'):>15}{ci:>22}{lm:>9.5f}{mae:>8.3f}")
        rows.append({"inst": inst, "arm": arm, "n": len(d), "within_slot_ic": wic,
                     "pooled_ic": pic, "delta_vs_core": dl, "delta_lo": lo,
                     "delta_hi": hi, "log_mse": lm, "mae_bp": mae,
                     "features": "|".join(ARMS[arm])})
    log("  * = 90% session-block CI excludes zero")
    log(f"\n  reference  persistence P within-slot IC "
        f"{A.within_slot_ic_arrays(P, Aa, slot):+.4f}; seasonal M "
        f"{A.within_slot_ic_arrays(d[FV.SLOT_MEDIAN].to_numpy(float), Aa, slot):+.4f}")

    # ---- PRIMARY: the expansion cell --------------------------------------------------- #
    log("\n--- PRIMARY: the EXPANSION cell (the metric declared in HYP-0014) ---")
    log("EXP-0015: the core ranks expansions well but cannot SIZE them -- log-MSE skill")
    log(f"over persistence +{CORE_EXPANSION['NQ']:.3f} NQ / +{CORE_EXPANSION['ES']:.3f} ES, "
        "against +0.300/+0.211 on contractions.")
    log("Reported twice: on each arm's OWN expansion set (EXP-0016's definition, so the")
    log("numbers are comparable to that run) and on the COMMON set the CORE calls, so the")
    log("arms are also compared on identical rows.")
    core_pc = np.log(d["p_core"].to_numpy(float) / P)
    common_e = core_pc > 0
    log(f"\n{'arm':<14}{'own exp n':>10}{'skill vs P':>12}{'contr skill':>12}"
        f"{'common-set skill':>18}{'change-IC':>11}{'exp change-IC':>14}")
    for arm in ARMS:
        F = d[f"p_{arm}"].to_numpy(float)
        pc, rc = np.log(F / P), np.log(Aa / P)
        e, c = pc > 0, pc <= 0
        ch = A.within_slot_ic_arrays(pc, rc, slot)
        che = A.within_slot_ic_arrays(pc[e], rc[e], slot[e]) if e.sum() > 500 else np.nan
        own = skill(Aa[e], F[e], P[e]) if e.sum() > 500 else np.nan
        con = skill(Aa[c], F[c], P[c]) if c.sum() > 500 else np.nan
        com = skill(Aa[common_e], F[common_e], P[common_e])
        log(f"{arm:<14}{int(e.sum()):>10,}{own:>+12.4f}{con:>+12.4f}{com:>+18.4f}"
            f"{ch:>+11.4f}{che:>+14.4f}")
        for r in rows:
            if r["arm"] == arm:
                r.update({"exp_n": int(e.sum()), "exp_skill_vs_P": own,
                          "con_skill_vs_P": con, "common_exp_skill": com,
                          "change_ic": ch, "exp_change_ic": che})

    # ---- gates ------------------------------------------------------------------------- #
    cand = next(r for r in rows if r["arm"] == "core_vix")
    ctrl_l3 = next(r for r in rows if r["arm"] == "core_levels3")
    ctrl_pr = next(r for r in rows if r["arm"] == "core_pastrv")
    base = next(r for r in rows if r["arm"] == "core")

    kt1 = bool(np.isfinite(cand["delta_lo"]) and cand["delta_lo"] * cand["delta_hi"] > 0
               and cand["delta_vs_core"] > 0)
    kt2 = bool(cand["exp_skill_vs_P"] >= EXPANSION_BAR[inst])
    kt4 = bool(cand["exp_skill_vs_P"] > ctrl_pr["exp_skill_vs_P"])

    log("\n=== GATES (declared in experiments/hypotheses/HYP-0014.md before the run) ===")
    log(f"KT1 statistical ({inst}): within-slot IC delta {cand['delta_vs_core']:+.4f} "
        f"[{cand['delta_lo']:+.4f},{cand['delta_hi']:+.4f}] -> "
        f"{'PASS' if kt1 else 'FAIL'}  (necessary only; saturated axis)")
    log(f"KT2 decision   ({inst}): expansion skill {cand['exp_skill_vs_P']:+.4f} vs the "
        f"REDUNDANT-control bar +{EXPANSION_BAR[inst]:.3f} -> {'PASS' if kt2 else 'FAIL'}")
    log(f"    (core here {base['exp_skill_vs_P']:+.4f}; core_levels3 here "
        f"{ctrl_l3['exp_skill_vs_P']:+.4f}; EXP-0016 published +{EXPANSION_BAR[inst]:.3f})")
    log(f"KT4 degenerate ({inst}): core_vix {cand['exp_skill_vs_P']:+.4f} vs core_pastrv "
        f"{ctrl_pr['exp_skill_vs_P']:+.4f} -> {'PASS' if kt4 else 'FAIL'}")
    log("    (if VIX cannot beat simply handing the model its own persistence benchmark,")
    log("     the gain is not implied-volatility information)")
    log(f"KT3 mechanism: compare the core_vix expansion skill across markets after both "
        f"runs. VIX is an SPX measure, so the mechanism predicts ES >= NQ.")

    # ---- stability --------------------------------------------------------------------- #
    log("\n--- stability of the core_vix-minus-core within-slot IC delta ---")
    yr = []
    for y, gg in d.groupby("year"):
        if len(gg) < 200:
            continue
        a = A.within_slot_ic_arrays(gg.p_core_vix.to_numpy(float),
                                    gg[FV.TARGET].to_numpy(float), gg.mfo.to_numpy(float))
        b = A.within_slot_ic_arrays(gg.p_core.to_numpy(float),
                                    gg[FV.TARGET].to_numpy(float), gg.mfo.to_numpy(float))
        yr.append((int(y), a - b))
    log("  by year: " + ", ".join(f"{y}:{v:+.4f}" for y, v in yr))
    log(f"  positive in {sum(1 for _, v in yr if v > 0)}/{len(yr)} years")
    sl = [(int(m), spearmanr(gg.p_core_vix, gg[FV.TARGET]).statistic
           - spearmanr(gg.p_core, gg[FV.TARGET]).statistic) for m, gg in d.groupby("mfo")]
    log("  by slot: " + ", ".join(f"{m}:{v:+.4f}" for m, v in sl))

    # ---- robustness: the join boundary ------------------------------------------------- #
    log("\n--- ROBUSTNESS: lag the VIX quote a further 15 minutes (lag_bars=1) ---")
    log("the decision cutoff coincides exactly with a VIX bar close, so this shows whether")
    log("anything depended on that boundary.")
    d_lag, _ = VX.attach_vix(frame, lag_bars=1)
    lag_common = d_lag.dropna(subset=need).copy()
    lag_common = lag_common[(lag_common.past_rv30_bp > 0) & (lag_common[FV.TARGET] > 0)]
    pl = FV.walkforward_forecast(lag_common, FIRST_TEST_YEAR, features=ARMS["core_vix"],
                                 pred_col="p_lag")
    dl_ = lag_common.merge(pl[["ts_utc", "p_lag"]], on="ts_utc", how="inner")
    Al, Pl = dl_[FV.TARGET].to_numpy(float), dl_.past_rv30_bp.to_numpy(float)
    Fl = dl_.p_lag.to_numpy(float)
    el = np.log(Fl / Pl) > 0
    log(f"  n={len(dl_):,}  within-slot IC "
        f"{A.within_slot_ic_arrays(Fl, Al, dl_.mfo.to_numpy(float)):+.4f} "
        f"(fresh {cand['within_slot_ic']:+.4f});  expansion skill "
        f"{skill(Al[el], Fl[el], Pl[el]):+.4f} (fresh {cand['exp_skill_vs_P']:+.4f})")

    pd.DataFrame(rows).to_csv(OUT / f"implied_vol_{inst}.csv", index=False)
    (OUT / f"implied_vol_{inst}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / f'implied_vol_{inst}.txt'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
