"""HYP-0013 / EXP-0016 -- does a LOW-CORRELATION feature set beat the two-input core?

The adopted core is two volatility-LEVEL proxies. EXP-0011 added six MORE level proxies
(the multi-horizon set) and bought only +0.009 IC, which is evidence that the LEVEL is
saturated -- not that the forecast cannot be improved, because that set never contained a
second dimension. The proposal under test is that REDUNDANCY, not saturation, was the
binding constraint, and that a set chosen for low mutual correlation spans dimensions the
core cannot see: jump vs diffusive composition, the short-vs-long term structure, whether
price travelled or churned, and volatility that arrived overnight.

Arms (all on ONE common sample, identical rows, identical learner, identical target):

    core        [fwd_rv_bp_slot_median90, range_rv_15m]                     baseline
    user6       the requested set                                           THE candidate
    core_plus4  core + the four new state variables      isolates the INCREMENT
    swap_only   [fwd_abs_bp_slot_median90, range_rv_15m] isolates the SEASONAL SWAP
    new4_only   the four new state variables alone       degenerate control

The requested set makes two changes at once -- it ADDS four state variables and SWAPS the
core's seasonal for the seasonal of a different target -- so the attribution arms exist to
stop a gain or a loss being credited to the bundle.

Gates are read ONLY on `user6` (see `experiments/hypotheses/HYP-0013.md`):
  KT1 statistical -- paired within-slot IC delta over core, CI excludes 0, BOTH markets.
  KT2 adoption    -- and delta >= +0.010 on both, the bar EXP-0011's +0.009 failed.
  KT3 meaning     -- does it lift the EXP-0015 weak cell (expansion-call log-MSE skill
                     over persistence: core +0.008 NQ / +0.061 ES)?

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0013_decorrelated_features {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ..core import analysis as A
from ..core import forward_vol as FV

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0016"

FIRST_TEST_YEAR = 2016
NBOOT = 500
SEED = 20260731
IC_TOL = 5e-4
NOTEBOOK_IC = {("NQ", 2016, 2023): 0.8996, ("ES", 2016, 2023): 0.8886,
               ("NQ", 2024, None): 0.8503, ("ES", 2024, None): 0.8419}

ADOPT_GATE = 0.010                    # KT2, set from EXP-0011 precedent before the run
NEW4 = list(FV.CANDIDATE_FEATURES)    # jump/ratio/path-efficiency/overnight
ABS_MEDIAN = "fwd_abs_bp_slot_median90"

#: `core_levels3` was added AFTER the preregistered arms were run, as a CONTROL, once
#: the level-IC gain came out at +0.009/+0.010 -- indistinguishable from the +0.0088 /
#: +0.0095 that EXP-0011's six REDUNDANT multi-horizon level proxies bought. It is the
#: cheap analogue of that set (three more measurements of the same quantity over
#: different windows) and it answers the question the preregistered arms cannot: is the
#: lift caused by these particular DIMENSIONS, or by adding any few features at all?
#: A control can only weaken the candidate's interpretation, never manufacture a pass;
#: the KT1/KT2/KT3 gates stay read on `user6` exactly as declared.
LEVELS3 = ["rv_15m", "rv_60m", "rv_120m"]

ARMS: dict[str, list[str]] = {
    "core":         [FV.SLOT_MEDIAN, "range_rv_15m"],
    "user6":        NEW4 + ["range_rv_15m", ABS_MEDIAN],
    "core_plus4":   [FV.SLOT_MEDIAN, "range_rv_15m"] + NEW4,
    "swap_only":    [ABS_MEDIAN, "range_rv_15m"],
    "new4_only":    NEW4,
    "core_levels3": [FV.SLOT_MEDIAN, "range_rv_15m"] + LEVELS3,
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

    log(f"=== HYP-0013 / EXP-0016 -- decorrelated feature set vs the core ({inst}) ===")

    frame, q = FV.build_decision_frame(inst, candidates=True)
    log(f"\ndata: {q['decision_rows']:,} decision rows over {q['sessions']:,} sessions "
        f"{q['first'].date()}..{q['last'].date()}; duplicate ts {q['duplicate_ts']}, "
        f"out-of-order {q['out_of_order_ts']}, missing target {q['missing_rv_targets']}")

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

    # ---- rule 9a: what does each candidate feature COST in decisions? ---------------- #
    log("\n--- rule 9a: candidate-feature coverage (share of decision rows DEFINED) ---")
    log("the 60-minute windows run on the CONTINUOUS series, so at the early slots they")
    log("reach back across the thin overnight session. A null rate that tracks time of")
    log("day is a reportable finding, not an implementation detail.")
    cov = frame.groupby("mfo")[ALL_FEATURES].apply(lambda g: g.notna().mean())
    log("\n  mfo   " + "  ".join(f"{c[:16]:>16}" for c in ALL_FEATURES))
    for mfo, row in cov.iterrows():
        log(f"  {int(mfo):>3}   " + "  ".join(f"{row[c]:>16.4f}" for c in ALL_FEATURES))
    log("\n  overall " + "  ".join(
        f"{frame[c].notna().mean():>15.4f}" for c in ALL_FEATURES))

    # ---- the common sample: every arm sees identical rows ---------------------------- #
    need = ALL_FEATURES + [FV.TARGET, "past_rv30_bp"]
    common = frame.dropna(subset=need).copy()
    common = common[(common.past_rv30_bp > 0) & (common[FV.TARGET] > 0)]
    log(f"\ncommon sample: {len(common):,} of {len(frame):,} decision rows "
        f"({len(common) / len(frame):.2%}); every arm trains and tests on these rows, so")
    log("no arm can win by being evaluated on an easier subset.")
    lost = frame.groupby("mfo").size() - common.groupby("mfo").size().reindex(
        frame.mfo.unique()).fillna(0)
    keep_by_slot = (common.groupby("mfo").size()
                    / frame.groupby("mfo").size()).sort_index()
    log("  retention by slot: " + ", ".join(
        f"{int(m)}:{v:.3f}" for m, v in keep_by_slot.items()))
    log(f"  worst slot retains {keep_by_slot.min():.3f}, best {keep_by_slot.max():.3f} "
        f"-> {'UNIFORM (pass signal)' if keep_by_slot.max() - keep_by_slot.min() < 0.05 else 'TIME-OF-DAY DEPENDENT (reportable)'}")
    by_era = common.groupby("year").size() / frame.groupby("year").size()
    log("  retention by year: " + ", ".join(f"{int(y)}:{v:.3f}"
                                            for y, v in by_era.dropna().items()))

    # ---- the stated premise, measured ------------------------------------------------ #
    log("\n--- the PREMISE under test: Spearman correlation among the candidate set ---")
    cm = common[ALL_FEATURES].corr(method="spearman")
    log("        " + "  ".join(f"{c[:14]:>14}" for c in ALL_FEATURES))
    for c in ALL_FEATURES:
        log(f"  {c[:14]:<14}" + "  ".join(f"{cm.loc[c, o]:>+14.3f}" for o in ALL_FEATURES))
    off = [(abs(cm.loc[a, b]), a, b) for i, a in enumerate(ALL_FEATURES)
           for b in ALL_FEATURES[i + 1:]]
    off.sort(reverse=True)
    log("\n  strongest pairs: " + "; ".join(f"{a}~{b} {v:+.3f}" for v, a, b in off[:4]))
    log(f"  weakest  pairs: " + "; ".join(f"{a}~{b} {v:+.3f}" for v, a, b in off[-3:]))
    log(f"  the two SEASONALS {FV.SLOT_MEDIAN} ~ {ABS_MEDIAN}: "
        f"{cm.loc[FV.SLOT_MEDIAN, ABS_MEDIAN]:+.4f}   <- if near 1.0 the 'swap' is "
        "close to a no-op and `user6` is really core+4 with a noisier seasonal")

    # ---- run every arm ---------------------------------------------------------------- #
    log("\n--- walk-forward, expanding window, first tested year "
        f"{FIRST_TEST_YEAR}, one frozen learner ---")
    preds = None
    for arm, feats in ARMS.items():
        p = FV.walkforward_forecast(common, FIRST_TEST_YEAR, features=feats,
                                    pred_col=f"p_{arm}")
        cols = ["ts_utc", f"p_{arm}"]
        preds = p[cols] if preds is None else preds.merge(p[cols], on="ts_utc", how="inner")
        log(f"  {arm:<11} {len(feats)} feature(s): {', '.join(feats)}")
    d = common.merge(preds, on="ts_utc", how="inner").copy()
    d["date"] = d["sdate"]
    log(f"  evaluated on {len(d):,} rows, {d.date.nunique():,} sessions, "
        f"{d.year.min()}..{d.year.max()}")

    Aa = d[FV.TARGET].to_numpy(float)
    P = d["past_rv30_bp"].to_numpy(float)
    slot = d["mfo"].to_numpy(float)
    rng = np.random.default_rng(SEED)

    # ---- PRIMARY ---------------------------------------------------------------------- #
    log("\n--- PRIMARY: within-slot IC vs realised forward RV, and the PAIRED delta "
        "over `core` ---")
    log(f"{'arm':<11} {'within-slot IC':>15} {'pooled IC':>11} {'delta vs core':>15} "
        f"{'90% CI':>22} {'log-MSE':>9} {'MAE bp':>8}")
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
        log(f"{arm:<11} {wic:>+15.4f} {pic:>+11.4f} "
            f"{('' if arm == 'core' else f'{dl:+.4f}'):>15} {ci:>22} "
            f"{lm:>9.5f} {mae:>8.3f}")
        rows.append({"inst": inst, "arm": arm, "n": len(d), "within_slot_ic": wic,
                     "pooled_ic": pic, "delta_vs_core": dl, "delta_lo": lo,
                     "delta_hi": hi, "log_mse": lm, "mae_bp": mae,
                     "features": "|".join(ARMS[arm])})
    log("  * = 90% session-block CI excludes zero")

    # reference legs that are not models
    log(f"\n  reference  persistence P within-slot IC "
        f"{A.within_slot_ic_arrays(P, Aa, slot):+.4f}; seasonal M "
        f"{A.within_slot_ic_arrays(d[FV.SLOT_MEDIAN].to_numpy(float), Aa, slot):+.4f}")

    # ---- KT1 / KT2 ---------------------------------------------------------------------- #
    u = next(r for r in rows if r["arm"] == "user6")
    kt1 = bool(np.isfinite(u["delta_lo"]) and u["delta_lo"] * u["delta_hi"] > 0
               and u["delta_vs_core"] > 0)
    kt2 = bool(kt1 and u["delta_vs_core"] >= ADOPT_GATE)
    log(f"\nKT1 ({inst}): delta {u['delta_vs_core']:+.4f} "
        f"[{u['delta_lo']:+.4f},{u['delta_hi']:+.4f}] -> "
        f"{'PASS (positive, CI excludes 0)' if kt1 else 'FAIL'}")
    log(f"KT2 ({inst}): delta vs the +{ADOPT_GATE:.3f} adoption bar -> "
        f"{'PASS' if kt2 else 'FAIL'}  (EXP-0011 confirmed +0.009 and declined to adopt)")

    # ---- attribution --------------------------------------------------------------------- #
    core_ic = next(r for r in rows if r["arm"] == "core")["within_slot_ic"]
    log("\n--- attribution: which of the two changes moved it? ---")
    for arm, what in [("core_plus4", "the four ADDITIONS, RV seasonal retained"),
                      ("swap_only", "the SEASONAL SWAP alone, no additions"),
                      ("new4_only", "the four additions with NO seasonal (degenerate)"),
                      ("core_levels3", "POST-HOC CONTROL: 3 REDUNDANT level proxies "
                                       "instead -- is it the dimensions or just more features?")]:
        r = next(x for x in rows if x["arm"] == arm)
        log(f"  {arm:<11} {r['within_slot_ic']:+.4f} "
            f"({r['within_slot_ic'] - core_ic:+.4f} vs core)   {what}")

    # ---- per-year and per-slot stability --------------------------------------------------- #
    log("\n--- stability of the user6-minus-core within-slot IC delta ---")
    yr = []
    for y, g in d.groupby("year"):
        if len(g) < 200:
            continue
        a = A.within_slot_ic_arrays(g.p_user6.to_numpy(float),
                                    g[FV.TARGET].to_numpy(float), g.mfo.to_numpy(float))
        b = A.within_slot_ic_arrays(g.p_core.to_numpy(float),
                                    g[FV.TARGET].to_numpy(float), g.mfo.to_numpy(float))
        yr.append((int(y), a - b))
    log("  by year: " + ", ".join(f"{y}:{v:+.4f}" for y, v in yr))
    pos = sum(1 for _, v in yr if v > 0)
    log(f"  positive in {pos}/{len(yr)} years")
    sl = []
    for m, g in d.groupby("mfo"):
        a = spearmanr(g.p_user6, g[FV.TARGET]).statistic
        b = spearmanr(g.p_core, g[FV.TARGET]).statistic
        sl.append((int(m), a - b))
    log("  by slot: " + ", ".join(f"{m}:{v:+.4f}" for m, v in sl))

    # ---- KT3: the cell that actually matters ------------------------------------------------ #
    log("\n--- KT3: does it lift the EXP-0015 WEAK CELL (expansion calls)? ---")
    log("EXP-0015 found the core ranks expansions well but barely beats persistence at")
    log("their MAGNITUDE: log-MSE skill over P of +0.008 NQ / +0.061 ES, against")
    log("+0.300/+0.211 on contractions. That is the cell with the economic value.")
    log(f"\n{'arm':<11} {'expansion n':>12} {'skill vs P':>12} {'contraction n':>14} "
        f"{'skill vs P':>12} {'change-IC':>11} {'exp change-IC':>14}")
    for arm in ARMS:
        F = d[f"p_{arm}"].to_numpy(float)
        pc, rc = np.log(F / P), np.log(Aa / P)
        e, c = pc > 0, pc <= 0
        ch = A.within_slot_ic_arrays(pc, rc, slot)
        che = (A.within_slot_ic_arrays(pc[e], rc[e], slot[e]) if e.sum() > 500 else np.nan)
        log(f"{arm:<11} {int(e.sum()):>12,} "
            f"{(skill(Aa[e], F[e], P[e]) if e.sum() > 500 else np.nan):>+12.4f} "
            f"{int(c.sum()):>14,} "
            f"{(skill(Aa[c], F[c], P[c]) if c.sum() > 500 else np.nan):>+12.4f} "
            f"{ch:>+11.4f} {che:>+14.4f}")
        for r in rows:
            if r["arm"] == arm:
                r["exp_n"] = int(e.sum())
                r["exp_skill_vs_P"] = (skill(Aa[e], F[e], P[e]) if e.sum() > 500 else np.nan)
                r["con_skill_vs_P"] = (skill(Aa[c], F[c], P[c]) if c.sum() > 500 else np.nan)
                r["change_ic"] = ch
                r["exp_change_ic"] = che
    ce = next(r for r in rows if r["arm"] == "core")["exp_skill_vs_P"]
    ue = u["exp_skill_vs_P"]
    log(f"\nKT3 ({inst}): user6 expansion skill {ue:+.4f} vs core {ce:+.4f} "
        f"-> {'LIFTS the weak cell' if ue > ce else 'does NOT lift the weak cell'} "
        f"({ue - ce:+.4f})")

    pd.DataFrame(rows).to_csv(OUT / f"decorrelated_{inst}.csv", index=False)
    (OUT / f"decorrelated_{inst}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / f'decorrelated_{inst}.txt'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
