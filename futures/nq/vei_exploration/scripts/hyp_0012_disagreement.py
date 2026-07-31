"""HYP-0012 / EXP-0015 -- the disagreement set: is the core a TIMING instrument?

EXP-0012 showed the two-input core beats the SEASONAL benchmark (the causal same-slot
median) by a wide within-slot margin. It has never been tested against the other trivial
benchmark, the one a practitioner would actually default to:

    P = "the next thirty minutes will look like the last thirty minutes"

`P` here is `past_rv30_bp`, the strict BACKWARD TWIN of the target -- same estimator,
same prices, window ending at the decision bar's own open -- so `log(fwd/P)` is a clean
"did volatility change" quantity with no scale bias (pinned by tests).

A forecast that agrees with persistence changes no decision however accurate it is, so
all usable content lives in the disagreement set. The question is therefore not "is F
accurate" but "when F says volatility will DIFFER from recent volatility, is it right?":

    predicted log-change  pc = log(F / P)
    realised  log-change  rc = log(A / P)

PRIMARY: within-slot Spearman IC(pc, rc), both markets, session-block CI.
GATE:    the EXPANSION side (pc > 0) must clear zero on its own. Volatility mean-reverts,
         so calling a contraction after a spike is nearly free; a pass carried entirely by
         contraction calls is arithmetic, not timing skill.

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0012_disagreement {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ..core import analysis as A
from ..core import forward_vol as FV

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0015"

FIRST_TEST_YEAR = 2016
NBOOT = 500
SEED = 20260731
IC_TOL = 5e-4
NOTEBOOK_IC = {("NQ", 2016, 2023): 0.8996, ("ES", 2016, 2023): 0.8886,
               ("NQ", 2024, None): 0.8503, ("ES", 2024, None): 0.8419}


def log_mse(actual, pred) -> float:
    return float(np.mean(np.square(np.log(np.clip(actual, 1e-9, None))
                                   - np.log(np.clip(pred, 1e-9, None)))))


def skill(actual, pred, base) -> float:
    """1 - MSE(log pred) / MSE(log base). Positive = beats the benchmark."""
    e0 = log_mse(actual, base)
    return float(1.0 - log_mse(actual, pred) / e0) if e0 > 0 else np.nan


def main(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    log(f"=== HYP-0012 / EXP-0015 -- the disagreement set ({inst}) ===")

    frame, q = FV.build_decision_frame(inst)
    log(f"\ndata (rule 9a): {q['decision_rows']:,} decision rows over {q['sessions']:,} "
        f"sessions {q['first'].date()}..{q['last'].date()}; duplicate ts "
        f"{q['duplicate_ts']}, out-of-order {q['out_of_order_ts']}, missing target "
        f"{q['missing_rv_targets']}, missing past_rv30 {q['missing_past_rv30']:,}")

    log("\nrule-23 reproduction of artifacts/runs/EXP-0011 "
        "(notebook sha256 ccb9f5e9..79606):")
    for (i, first, last), want in NOTEBOOK_IC.items():
        if i != inst:
            continue
        p = FV.walkforward_forecast(frame, first, last)
        got = spearmanr(p["fvol_bp"], p[FV.TARGET]).statistic
        log(f"  test years {first}..{last or 'end'}: n={len(p):,} IC {got:+.6f} vs "
            f"published {want:+.4f}  |diff| {abs(got - want):.2e}  "
            f"{'PASS' if abs(got - want) <= IC_TOL else 'FAIL'}")
        assert abs(got - want) <= IC_TOL, "rule-23 reproduction failed"

    pred = FV.walkforward_forecast(frame, FIRST_TEST_YEAR)
    d = pred.dropna(subset=["fvol_bp", FV.TARGET, "past_rv30_bp", FV.SLOT_MEDIAN]).copy()
    d = d[(d.past_rv30_bp > 0) & (d[FV.TARGET] > 0) & (d[FV.SLOT_MEDIAN] > 0)]
    d["date"] = d["sdate"]
    n_drop = len(pred) - len(d)
    log(f"\nbenchmark coverage: {len(d):,} of {len(pred):,} walk-forward rows keep a "
        f"defined trailing benchmark ({len(d) / len(pred):.2%}); {n_drop:,} dropped for a "
        f"broken/zero trailing window. Per-slot coverage "
        f"{pred.groupby('mfo').past_rv30_bp.apply(lambda s: s.notna().mean()).min():.4f}.."
        f"{pred.groupby('mfo').past_rv30_bp.apply(lambda s: s.notna().mean()).max():.4f}")

    F = d["fvol_bp"].to_numpy(float)
    P = d["past_rv30_bp"].to_numpy(float)
    M = d[FV.SLOT_MEDIAN].to_numpy(float)
    Aa = d[FV.TARGET].to_numpy(float)
    slot = d["mfo"].to_numpy(float)
    d["pc"] = np.log(F / P)
    d["rc"] = np.log(Aa / P)
    d["mc"] = np.log(M / P)          # the same call made by seasonality alone

    # ---- three-way head-to-head ---------------------------------------------- #
    log("\nthree-way accuracy against the realised forward RV (log-MSE, lower better):")
    for nm, v in [("model F", F), ("persistence P (trailing 30m)", P),
                  ("seasonal M (same-slot median)", M)]:
        log(f"  {nm:<32} log-MSE {log_mse(Aa, v):.5f}   "
            f"within-slot IC vs actual {A.within_slot_ic_arrays(v, Aa, slot):+.4f}")
    log(f"  model skill vs persistence  {skill(Aa, F, P):+.4f}")
    log(f"  model skill vs seasonality  {skill(Aa, F, M):+.4f}")
    log(f"  persistence skill vs seasonality {skill(Aa, P, M):+.4f}"
        "   (>0 = persistence is the harder benchmark)")

    # ---- how often does the model even disagree? ----------------------------- #
    q10, q90 = np.percentile(d["pc"], [10, 90])
    log(f"\ndisagreement pc = log(F/P): mean {d['pc'].mean():+.4f}, sd {d['pc'].std():.4f}, "
        f"p10 {q10:+.4f}, p90 {q90:+.4f}; the model calls an EXPANSION "
        f"{(d['pc'] > 0).mean():.1%} of the time. Realised rc: mean {d['rc'].mean():+.4f}, "
        f"sd {d['rc'].std():.4f}.")

    # ---- PRIMARY -------------------------------------------------------------- #
    rng = np.random.default_rng(SEED)
    ic, lo, hi = A.block_boot_within_slot_ic(d, "pc", "rc", rng, nboot=NBOOT,
                                             date_col="date")
    log(f"\nPRIMARY within-slot IC(predicted log-change, realised log-change): "
        f"{ic:+.4f} [{lo:+.4f},{hi:+.4f}] "
        f"{'EXCLUDES 0' if lo * hi > 0 else 'spans 0'}")
    ic_p = spearmanr(d["pc"], d["rc"]).statistic
    log(f"  (pooled equivalent {ic_p:+.4f})")

    log("\nsides -- the gate is the EXPANSION side on its own:")
    res = {"inst": inst, "n": len(d), "ic": ic, "ic_lo": lo, "ic_hi": hi}
    for nm, sub in [("expansion calls (pc>0)", d[d.pc > 0]),
                    ("contraction calls (pc<=0)", d[d.pc <= 0])]:
        i2, l2, h2 = A.block_boot_within_slot_ic(sub, "pc", "rc",
                                                 np.random.default_rng(SEED),
                                                 nboot=NBOOT, date_col="date")
        log(f"  {nm:<26} n={len(sub):>6,}  IC {i2:+.4f} [{l2:+.4f},{h2:+.4f}]  "
            f"mean rc {sub['rc'].mean():+.4f}  skill vs P {skill(sub[FV.TARGET], sub['fvol_bp'], sub['past_rv30_bp']):+.4f}")
        key = "exp" if "expansion" in nm else "con"
        res.update({f"ic_{key}": i2, f"ic_{key}_lo": l2, f"ic_{key}_hi": h2})

    # ---- degenerate control: does seasonality alone call the change? ---------- #
    icm, lom, him = A.block_boot_within_slot_ic(d, "mc", "rc",
                                                np.random.default_rng(SEED),
                                                nboot=NBOOT, date_col="date")
    log(f"\ndegenerate control -- the SAME statistic using the free same-slot median in "
        f"place of the model:\n  within-slot IC(log(M/P), rc) {icm:+.4f} "
        f"[{lom:+.4f},{him:+.4f}]. The model's marginal value on this axis is "
        f"{ic - icm:+.4f}.")
    res.update(ic_median=icm)

    # ---- skill vs the SIZE of the disagreement -------------------------------- #
    log("\nskill by |disagreement| decile (does the model get better or WORSE exactly")
    log("where it would actually be used?):")
    d["_dec"] = pd.qcut(d["pc"].abs(), 10, labels=False, duplicates="drop")
    log(f"  {'decile':>6} {'n':>6} {'|pc| mean':>10} {'IC(pc,rc)':>10} "
        f"{'skill vs P':>11} {'mean rc':>9}")
    for dec, g in d.groupby("_dec", observed=True):
        log(f"  {int(dec) + 1:>6} {len(g):>6,} {g['pc'].abs().mean():>10.4f} "
            f"{spearmanr(g['pc'], g['rc']).statistic:>+10.4f} "
            f"{skill(g[FV.TARGET], g['fvol_bp'], g['past_rv30_bp']):>+11.4f} "
            f"{g['rc'].mean():>+9.4f}")

    # ---- stability ------------------------------------------------------------ #
    log("\nper-year within-slot IC(pc, rc):")
    for year, g in d.groupby(d.sdate.dt.year):
        if len(g) < 200:
            continue
        log(f"  {year}  n={len(g):>5,}  IC "
            f"{A.within_slot_ic_arrays(g['pc'].to_numpy(float), g['rc'].to_numpy(float), g['mfo'].to_numpy(float)):+.4f}"
            f"   expansion-only "
            f"{A.within_slot_ic_arrays(*[g[g.pc > 0][c].to_numpy(float) for c in ('pc', 'rc')], g[g.pc > 0]['mfo'].to_numpy(float)):+.4f}")

    log("\nper-slot within-slot IC(pc, rc):")
    for s, g in d.groupby("mfo"):
        log(f"  mfo {int(s):>3} ({570 + int(s)//60*60 + int(s)%60:>4})  n={len(g):>5,}  "
            f"IC {spearmanr(g['pc'], g['rc']).statistic:+.4f}")

    gate = (lo > 0) and (res["ic_exp_lo"] > 0)
    log("\n=== VERDICT INPUTS (kill test needs BOTH markets) ===")
    log(f"  primary within-slot IC(pc,rc) {ic:+.4f} [{lo:+.4f},{hi:+.4f}] -> "
        f"{'clears 0' if lo > 0 else 'does NOT clear 0'}")
    log(f"  expansion side               {res['ic_exp']:+.4f} "
        f"[{res['ic_exp_lo']:+.4f},{res['ic_exp_hi']:+.4f}] -> "
        f"{'clears 0' if res['ic_exp_lo'] > 0 else 'does NOT clear 0'}")
    log(f"  {inst} gate: {'PASS' if gate else 'FAIL'}")

    path = OUT / f"disagreement_{inst}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pd.DataFrame([res]).to_csv(OUT / f"disagreement_{inst}.csv", index=False)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main(sys.argv[1].upper() if len(sys.argv) > 1 else "NQ")
