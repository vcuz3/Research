"""HYP-0011 / EXP-0014 -- does the frozen two-input core transfer to DOWNSIDE vol,
and is the up/down SPLIT itself forecastable?

Two independent preregistered claims, reported separately:

  A (transfer)  Apply the frozen EXP-0011 recipe -- causal trailing 90-session same-slot
                median of the target + `range_rv_15m`, same learner, same walk-forward --
                unchanged to `fwd_dsv_bp` and `fwd_usv_bp`. Gate: the downside within-slot
                IC delta over its own same-slot median must clear zero on both markets AND
                retain >= 75% of the delta the same recipe achieves on total `fwd_rv_bp`.

  B (asymmetry) Apply it to the SHARE `fwd_down_share = dsv^2 / rv^2`. `range_rv_15m` is a
                symmetric feature and carries no up/down information, so a second
                candidate swaps in its asymmetric counterpart `past_down_share_30m`.
                Gate: one candidate must clear zero on both markets. If it passes, the
                DRIFT control decides whether it is information or a restatement of drift
                (noise_vwap EXP-0022 found exactly that trap in the band's asymmetry).

Within-slot IC is the primary metric because a pooled IC on an intraday panel is
dominated by time-of-day ordering no decision ever requires (EXP-0012).

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0011_semivariance {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ..core import analysis as A
from ..core import forward_vol as FV

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0014"

FIRST_TEST_YEAR = 2016
NBOOT = 500
SEED = 20260731
RETENTION_GATE = 0.75
IC_TOL = 5e-4
NOTEBOOK_IC = {("NQ", 2016, 2023): 0.8996, ("ES", 2016, 2023): 0.8886,
               ("NQ", 2024, None): 0.8503, ("ES", 2024, None): 0.8419}

#: target -> label. `fwd_rv_bp` is the reference the retention gate is measured against.
LEVEL_TARGETS = {"fwd_rv_bp": "total RV (reference)",
                 "fwd_dsv_bp": "downside semivariance",
                 "fwd_usv_bp": "upside semivariance"}


def log_mse_skill(actual, pred, base) -> float:
    """1 - MSE(log pred)/MSE(log base). Positive = the model beats the free forecast."""
    a = np.log(np.clip(actual, 1e-9, None))
    e1 = np.square(a - np.log(np.clip(pred, 1e-9, None)))
    e0 = np.square(a - np.log(np.clip(base, 1e-9, None)))
    return float(1.0 - e1.mean() / e0.mean()) if e0.mean() > 0 else np.nan


def evaluate(pred: pd.DataFrame, target: str, median_col: str, model_col: str,
             rng) -> dict:
    """Within-slot (primary) and pooled IC of the model vs the free same-slot median."""
    d = pred.dropna(subset=[target, median_col, model_col]).copy()
    d["date"] = d["sdate"]
    slot = d["mfo"].to_numpy(float)
    t = d[target].to_numpy(float)
    ws_model = A.within_slot_ic_arrays(d[model_col].to_numpy(float), t, slot)
    ws_median = A.within_slot_ic_arrays(d[median_col].to_numpy(float), t, slot)
    delta, lo, hi = A.block_boot_within_slot_ic_delta(
        d, model_col, median_col, target, rng, nboot=NBOOT, date_col="date")
    return {
        "n": len(d),
        "ws_model": ws_model, "ws_median": ws_median,
        "ws_delta": delta, "ws_lo": lo, "ws_hi": hi,
        "pooled_model": spearmanr(d[model_col], t).statistic,
        "pooled_median": spearmanr(d[median_col], t).statistic,
        "skill": log_mse_skill(t, d[model_col].to_numpy(float),
                               d[median_col].to_numpy(float)),
        "mae_model": float(np.abs(t - d[model_col].to_numpy(float)).mean()),
        "mae_median": float(np.abs(t - d[median_col].to_numpy(float)).mean()),
        "frame": d,
    }


def main(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    log(f"=== HYP-0011 / EXP-0014 -- downside semivariance and the up/down split "
        f"({inst}) ===")

    frame, q = FV.build_decision_frame(inst)
    log(f"\ndata (rule 9a): {q['decision_rows']:,} decision rows over {q['sessions']:,} "
        f"sessions {q['first'].date()}..{q['last'].date()}; duplicate ts "
        f"{q['duplicate_ts']}, out-of-order {q['out_of_order_ts']}, roll rows "
        f"{q['roll_rows']:,}, missing target {q['missing_rv_targets']}, missing "
        f"range_rv_15m {q['missing_range_rv_15m']}, missing slot median "
        f"{q['missing_slot_median']:,}, missing past_rv30 {q['missing_past_rv30']:,}")

    # ---- rule 23 + the decomposition identity -------------------------------- #
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

    m = frame.fwd_rv_bp.notna()
    ident = np.abs(frame.loc[m, "fwd_rv_bp"] ** 2
                   - (frame.loc[m, "fwd_dsv_bp"] ** 2 + frame.loc[m, "fwd_usv_bp"] ** 2))
    log(f"\ndecomposition identity rv^2 == dsv^2 + usv^2 over {int(m.sum()):,} rows: "
        f"max |error| {ident.max():.3e}  {'PASS' if ident.max() < 1e-6 else 'FAIL'}")
    assert ident.max() < 1e-6
    log(f"realised down-share: mean {frame.fwd_down_share.mean():.4f}, "
        f"sd {frame.fwd_down_share.std():.4f}, "
        f"slot means {frame.groupby('mfo').fwd_down_share.mean().min():.4f}.."
        f"{frame.groupby('mfo').fwd_down_share.mean().max():.4f}")

    # ---- CLAIM A ------------------------------------------------------------- #
    log("\n" + "=" * 78)
    log("CLAIM A -- does the frozen recipe transfer to the semivariance legs?")
    log("=" * 78)
    log(f"  {'target':<26} {'n':>7} {'ws_model':>9} {'ws_median':>10} {'ws_delta':>9} "
        f"{'90% CI':>20} {'skill':>7} {'MAE m/med':>16}")
    resA = {}
    for target, label in LEVEL_TARGETS.items():
        median_col = f"{target}_slot_median90"
        pred = FV.walkforward_forecast(frame, FIRST_TEST_YEAR, target=target,
                                       features=[median_col, "range_rv_15m"],
                                       pred_col="model")
        r = evaluate(pred, target, median_col, "model", np.random.default_rng(SEED))
        resA[target] = r
        log(f"  {label:<26} {r['n']:>7,} {r['ws_model']:>+9.4f} {r['ws_median']:>+10.4f} "
            f"{r['ws_delta']:>+9.4f} [{r['ws_lo']:+.4f},{r['ws_hi']:+.4f}] "
            f"{r['skill']:>+7.3f} {r['mae_model']:>7.2f}/{r['mae_median']:<8.2f}")

    ref = resA["fwd_rv_bp"]["ws_delta"]
    dsv = resA["fwd_dsv_bp"]
    retention = dsv["ws_delta"] / ref if ref else np.nan
    a_pass = (dsv["ws_lo"] > 0) and (retention >= RETENTION_GATE)
    log(f"\n  downside delta {dsv['ws_delta']:+.4f} vs total reference {ref:+.4f} "
        f"= retention {retention:.1%} (gate {RETENTION_GATE:.0%}); CI "
        f"{'excludes' if dsv['ws_lo'] > 0 else 'spans'} 0 -> "
        f"claim A {'PASS' if a_pass else 'FAIL'} on {inst}")

    log("\n  per-year within-slot delta (downside leg):")
    fr = dsv["frame"]
    for year, g in fr.groupby(fr.sdate.dt.year):
        if len(g) < 200:
            continue
        s = g["mfo"].to_numpy(float)
        t = g["fwd_dsv_bp"].to_numpy(float)
        dd = (A.within_slot_ic_arrays(g["model"].to_numpy(float), t, s)
              - A.within_slot_ic_arrays(g["fwd_dsv_bp_slot_median90"].to_numpy(float), t, s))
        log(f"    {year}  n={len(g):>5,}  delta {dd:+.4f}")

    # ---- CLAIM B ------------------------------------------------------------- #
    log("\n" + "=" * 78)
    log("CLAIM B -- is the up/down SPLIT itself forecastable?")
    log("=" * 78)
    share, share_med = "fwd_down_share", "fwd_down_share_slot_median90"
    sd = frame.dropna(subset=[share, share_med])
    resid = sd[share] - sd[share_med]
    log(f"  degenerate control: sd(share) {sd[share].std():.4f} -> sd(share - slot "
        f"median) {resid.std():.4f}; the per-slot median removes "
        f"{1 - resid.var() / sd[share].var():.1%} of the variance. A share that is a "
        f"per-slot constant plus noise has nothing left to forecast.")
    log(f"  {'candidate':<34} {'n':>7} {'ws_model':>9} {'ws_median':>10} {'ws_delta':>9} "
        f"{'90% CI':>20} {'skill':>7}")
    candidates = {
        "slot_median + range_rv_15m": [share_med, "range_rv_15m"],
        "slot_median + past_down_share_30m": [share_med, "past_down_share_30m"],
    }
    resB = {}
    for name, feats in candidates.items():
        pred = FV.walkforward_forecast(frame, FIRST_TEST_YEAR, target=share,
                                       features=feats, pred_col="model")
        r = evaluate(pred, share, share_med, "model", np.random.default_rng(SEED))
        resB[name] = r
        log(f"  {name:<34} {r['n']:>7,} {r['ws_model']:>+9.4f} {r['ws_median']:>+10.4f} "
            f"{r['ws_delta']:>+9.4f} [{r['ws_lo']:+.4f},{r['ws_hi']:+.4f}] "
            f"{r['skill']:>+7.3f}")
    b_pass = any(r["ws_lo"] > 0 for r in resB.values())
    log(f"\n  claim B {'PASS' if b_pass else 'FAIL'} on {inst} "
        f"(needs one candidate's CI above 0, and the same candidate on both markets)")

    # ---- DRIFT CONTROL ------------------------------------------------------- #
    log("\n  drift control (noise_vwap EXP-0022: a real up/down asymmetry can merely")
    log("  restate DRIFT, and acting on it was harmful there):")
    best = max(resB.items(), key=lambda kv: (kv[1]["ws_delta"]
                                             if np.isfinite(kv[1]["ws_delta"]) else -9))
    bf = best[1]["frame"].copy()          # already carries the trailing columns
    log(f"    best candidate = {best[0]}")
    log(f"    corr(predicted down-share, trailing 30m RETURN)      = "
        f"{spearmanr(bf['model'], bf['past_ret30_bp'], nan_policy='omit').statistic:+.4f}"
        f"   <- the drift channel")
    log(f"    corr(predicted down-share, trailing 30m DOWN-SHARE)  = "
        f"{spearmanr(bf['model'], bf['past_down_share_30m'], nan_policy='omit').statistic:+.4f}"
        f"   <- the persistence channel")
    log(f"    corr(realised  down-share, trailing 30m RETURN)      = "
        f"{spearmanr(bf[share], bf['past_ret30_bp'], nan_policy='omit').statistic:+.4f}")
    terc = pd.qcut(bf["past_ret30_bp"], 3,
                   labels=["down 30m (drift-)", "flat 30m", "up 30m (drift+)"])
    for name, g in bf.groupby(terc, observed=True):
        if len(g) < 300:
            continue
        s = g["mfo"].to_numpy(float)
        t = g[share].to_numpy(float)
        dd = (A.within_slot_ic_arrays(g["model"].to_numpy(float), t, s)
              - A.within_slot_ic_arrays(g[share_med].to_numpy(float), t, s))
        log(f"    {str(name):<26} n={len(g):>6,}  within-slot delta {dd:+.4f}")

    log("\n=== VERDICT INPUTS ===")
    log(f"  claim A (downside transfer): delta {dsv['ws_delta']:+.4f} "
        f"[{dsv['ws_lo']:+.4f},{dsv['ws_hi']:+.4f}], retention {retention:.1%} -> "
        f"{'PASS' if a_pass else 'FAIL'}")
    for name, r in resB.items():
        log(f"  claim B [{name}]: delta {r['ws_delta']:+.4f} "
            f"[{r['ws_lo']:+.4f},{r['ws_hi']:+.4f}] -> "
            f"{'clears 0' if r['ws_lo'] > 0 else 'spans 0'}")

    path = OUT / f"semivariance_{inst}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows = [{"inst": inst, "claim": "A", "target": t, **{k: v for k, v in r.items()
                                                         if k != "frame"}}
            for t, r in resA.items()]
    rows += [{"inst": inst, "claim": "B", "target": n, **{k: v for k, v in r.items()
                                                          if k != "frame"}}
             for n, r in resB.items()]
    pd.DataFrame(rows).to_csv(OUT / f"semivariance_{inst}.csv", index=False)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main(sys.argv[1].upper() if len(sys.argv) > 1 else "NQ")
