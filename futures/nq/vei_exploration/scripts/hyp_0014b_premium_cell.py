"""HYP-0014 follow-up / EXP-0017b -- WHERE, if anywhere, does implied volatility pay?

POST-HOC MECHANISM DIAGNOSTIC, not a gate. The preregistered gates were read in
`hyp_0014_implied_vol.py` and KT2/KT4 failed on both markets. This script asks the one
question that failure does not answer: the aggregate expansion cell averages over ~12,000
calls, so if VIX's contribution is concentrated in the handful of windows where the
mechanism actually predicts it -- implied unusually rich against realised, the pre-event
signature -- an aggregate metric would never see it.

The conditioning variable is `vrp_log_slot_z`, the causal trailing same-slot z-score of
log(implied30/realised30). High = options are charging much more for the next 30 minutes
than the last 30 minutes delivered, relative to what is normal at this time of day. That
is the pre-announcement pattern: realised volatility collapses into a scheduled event
while implied stays bid, so a past-price model sees calm and forecasts calm.

Read as: does the core_vix-minus-core gap WIDEN in the top premium cell? If it does not,
implied volatility has no concentrated pocket of value here either, and backlog item 13
must be pursued with an explicit event calendar rather than with VIX as its proxy.

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0014b_premium_cell {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import analysis as A
from ..core import forward_vol as FV
from ..core import vix as VX
from .hyp_0014_implied_vol import ARMS, FIRST_TEST_YEAR, log_mse, skill

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0017"

#: The 13:59 decision forecasts 14:00-14:30 ET, the FOMC statement window and the single
#: most concentrated scheduled intraday volatility event in the US equity session.
ANNOUNCEMENT_MFO = 269
KEEP = ["core", "core_vix", "core_pastrv", "core_levels3"]


def main(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    log(f"=== EXP-0017b -- POST-HOC: where does implied volatility pay? ({inst}) ===")
    log("NOT a gate. The preregistered gates are in hyp_0014_implied_vol.py; KT2 and KT4")
    log("failed on both markets. This asks whether the aggregate metric hid a pocket.")

    frame, _ = FV.build_decision_frame(inst, candidates=True)
    d0, _ = VX.attach_vix(frame)
    need = sorted({f for a in KEEP for f in ARMS[a]}) + [FV.TARGET, "past_rv30_bp",
                                                         "vrp_log_slot_z"]
    common = d0.dropna(subset=need).copy()
    common = common[(common.past_rv30_bp > 0) & (common[FV.TARGET] > 0)]

    preds = None
    for arm in KEEP:
        p = FV.walkforward_forecast(common, FIRST_TEST_YEAR, features=ARMS[arm],
                                    pred_col=f"p_{arm}")
        cols = ["ts_utc", f"p_{arm}"]
        preds = p[cols] if preds is None else preds.merge(p[cols], on="ts_utc", how="inner")
    d = common.merge(preds, on="ts_utc", how="inner").copy()
    log(f"\nevaluated on {len(d):,} rows, {d.sdate.nunique():,} sessions, "
        f"{d.year.min()}..{d.year.max()}")

    Aa = d[FV.TARGET].to_numpy(float)
    P = d.past_rv30_bp.to_numpy(float)

    # ---- 1. the premium cell ---------------------------------------------------------- #
    d["prem_q"] = pd.qcut(d.vrp_log_slot_z.rank(method="first"), 5, labels=False)
    log("\n--- 1. expansion-call skill over persistence, BY PREMIUM QUINTILE ---")
    log("q5 = options unusually rich vs what the last 30 minutes realised, for this slot.")
    log("If VIX pays anywhere, the core_vix-minus-core gap should WIDEN toward q5.")
    log(f"\n{'quintile':<10}{'n':>8}{'mean vrp_z':>12}{'realised/pred':>14}"
        + "".join(f"{a:>15}" for a in KEEP) + f"{'vix-core':>11}")
    for q, g in d.groupby("prem_q"):
        idx = g.index.to_numpy()
        a_, p_ = Aa[idx], P[idx]
        e = np.log(g.p_core.to_numpy(float) / p_) > 0          # the CORE's expansion set
        if e.sum() < 200:
            continue
        sk = {arm: skill(a_[e], g[f"p_{arm}"].to_numpy(float)[e], p_[e]) for arm in KEEP}
        log(f"q{int(q) + 1:<9}{int(e.sum()):>8,}{g.vrp_log_slot_z.mean():>+12.3f}"
            f"{float(np.mean(a_[e] / p_[e])):>14.3f}"
            + "".join(f"{sk[a]:>+15.4f}" for a in KEEP)
            + f"{sk['core_vix'] - sk['core']:>+11.4f}")

    # ---- 2. does a high premium actually mark forward expansion? ----------------------- #
    log("\n--- 2. the mechanism's precondition: does a rich premium PRECEDE expansion? ---")
    log("if log(realised_fwd / realised_past) does not rise with the premium, there is no")
    log("anticipation channel for any model to exploit, however it is featurised.")
    rc = np.log(Aa / P)
    log(f"{'quintile':<10}{'n':>8}{'mean log(fwd/past)':>20}{'P(expansion)':>14}"
        f"{'mean fwd bp':>13}")
    for q, g in d.groupby("prem_q"):
        idx = g.index.to_numpy()
        log(f"q{int(q) + 1:<9}{len(idx):>8,}{float(np.mean(rc[idx])):>+20.4f}"
            f"{float(np.mean(rc[idx] > 0)):>14.3f}{float(np.mean(Aa[idx])):>13.2f}")
    log(f"\n  within-slot IC(vrp_log_slot_z, log(fwd/past)) = "
        f"{A.within_slot_ic_arrays(d.vrp_log_slot_z.to_numpy(float), rc, d.mfo.to_numpy(float)):+.4f}")
    log("  (positive = a rich premium does mark forward expansion, which is the")
    log("   precondition; it does not by itself mean the model can USE it)")

    # ---- 3. the announcement window ---------------------------------------------------- #
    log(f"\n--- 3. the 13:59 slot (mfo {ANNOUNCEMENT_MFO}), which forecasts 14:00-14:30 ET ---")
    log("the FOMC statement window: the most concentrated scheduled intraday volatility")
    log("event in the session, and the place a forward-looking measure should earn most.")
    log(f"\n{'slot':<8}{'n':>8}{'exp n':>8}" + "".join(f"{a:>15}" for a in KEEP)
        + f"{'vix-core':>11}")
    for m, g in d.groupby("mfo"):
        idx = g.index.to_numpy()
        a_, p_ = Aa[idx], P[idx]
        e = np.log(g.p_core.to_numpy(float) / p_) > 0
        if e.sum() < 100:
            continue
        sk = {arm: skill(a_[e], g[f"p_{arm}"].to_numpy(float)[e], p_[e]) for arm in KEEP}
        mark = "  <-- announcement window" if m == ANNOUNCEMENT_MFO else ""
        log(f"{int(m):<8}{len(idx):>8,}{int(e.sum()):>8,}"
            + "".join(f"{sk[a]:>+15.4f}" for a in KEEP)
            + f"{sk['core_vix'] - sk['core']:>+11.4f}{mark}")

    # ---- 4. the biggest core errors ---------------------------------------------------- #
    log("\n--- 4. backlog item 13's diagnostic: the core's WORST calls ---")
    log("rank |log(realised/core forecast)| and ask whether implied volatility helps more")
    log("in the tail than in the body. A calendar feature is only worth building if the")
    log("residual is concentrated somewhere identifiable.")
    err = np.abs(np.log(np.clip(Aa, 1e-9, None) / np.clip(d.p_core.to_numpy(float), 1e-9, None)))
    d["err_dec"] = pd.qcut(pd.Series(err).rank(method="first"), 10, labels=False)
    log(f"\n{'error decile':<14}{'n':>8}{'mean |log err|':>16}"
        + "".join(f"{a:>15}" for a in ["core", "core_vix", "core_pastrv"])
        + f"{'vix-core':>11}")
    for q, g in d.groupby("err_dec"):
        idx = g.index.to_numpy()
        a_, p_ = Aa[idx], P[idx]
        sk = {arm: skill(a_, g[f"p_{arm}"].to_numpy(float), p_)
              for arm in ["core", "core_vix", "core_pastrv"]}
        log(f"d{int(q) + 1:<13}{len(idx):>8,}{float(np.mean(err[idx])):>16.4f}"
            + "".join(f"{sk[a]:>+15.4f}" for a in ["core", "core_vix", "core_pastrv"])
            + f"{sk['core_vix'] - sk['core']:>+11.4f}")

    (OUT / f"premium_cell_{inst}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / f'premium_cell_{inst}.txt'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
