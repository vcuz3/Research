"""HYP-0001 Study 1 -- how big is the AR(1) small-sample bias AT OUR WINDOW LENGTHS?

The point of this table is to make the hypothesis's own scope honest before any real
data is touched. It answers two questions with one grid:

  * where is the bias NEGLIGIBLE (so the audit predicts nothing moves -- Cells B/C), and
  * where is it comparable to the effects we report (so a threshold on it is a defect)?

T values are the ones this workspace actually uses:
    13     decisions in one RTH session (a per-session estimate)
    30     bars in the expanding Hurst gate's FIRST decision window
    46     decisions in one CME FX session
    90     the standard same-slot lookback
    390    bars in the expanding Hurst gate's LAST decision window
    3710   NQ/ES sessions in the sample
    44516  pooled decision pairs behind vei_exploration's AC1

Also reported: the ratio |bias| / sd(phi_hat). A bias much smaller than the estimator's
own sampling noise cannot be seen in one estimate -- but it does not average away, so it
is exactly what a per-slot MEAN of many estimates will surface.

Usage: python -u -m futures.nq.estimator_bias.scripts.s1_bias_table
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core import arbias as A

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0001"
SEED = 81000

PHIS = (-0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.8)
TS = (13, 30, 46, 90, 390, 3710, 44516)


def draws_for(T: int) -> int:
    """Enough draws that the Monte-Carlo error on the mean is well under the bias."""
    if T <= 400:
        return 20_000
    if T <= 4_000:
        return 4_000
    return 1_000


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    rows = []
    for T in TS:
        d = draws_for(T)
        for phi in PHIS:
            x = A.simulate_ar1(phi, T, rng, draws=d)
            ph = A.ols_ar1_batch(x)
            ken = np.array([A.kendall_correct(p, T) for p in ph])
            rows.append({
                "T": T, "phi": phi, "draws": d,
                "mean_phi_hat": float(np.nanmean(ph)),
                "bias": float(np.nanmean(ph)) - phi,
                "kendall_pred": A.kendall_bias(phi, T),
                "sd_phi_hat": float(np.nanstd(ph, ddof=1)),
                "bias_over_sd": ((float(np.nanmean(ph)) - phi)
                                 / float(np.nanstd(ph, ddof=1))),
                "resid_bias_kendall": float(np.nanmean(ken)) - phi,
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "bias_table.csv", index=False)

    print("\n===== Study 1: OLS AR(1) bias at this workspace's window lengths =====")
    print(f"seed={SEED}  estimator=ols_ar1 (with intercept)\n")
    print(f"{'T':>7} {'phi':>6} {'E[phi_hat]':>11} {'bias':>9} {'-(1+3phi)/T':>12} "
          f"{'sd':>8} {'|bias|/sd':>10} {'bias after':>11}")
    print(f"{'':>7} {'':>6} {'':>11} {'':>9} {'':>12} {'':>8} {'':>10} {'Kendall':>11}")
    for T in TS:
        for _, r in df[df["T"] == T].iterrows():
            print(f"{int(r['T']):>7} {r['phi']:>+6.2f} {r['mean_phi_hat']:>+11.4f} "
                  f"{r['bias']:>+9.4f} {r['kendall_pred']:>+12.4f} "
                  f"{r['sd_phi_hat']:>8.4f} {abs(r['bias_over_sd']):>10.3f} "
                  f"{r['resid_bias_kendall']:>+11.4f}")
        print()

    # ---- the quantity the hypothesis actually turns on --------------------------- #
    print("----- the differential across the Hurst gate's own window range -----")
    print("The gate's window grows 30 -> 390 bars within a single session, so a feature")
    print("with a CONSTANT true phi still drifts by this much from estimator bias alone:")
    print(f"{'phi':>6} {'bias@T=30':>11} {'bias@T=390':>12} {'drift':>9} "
          f"{'sd@T=30':>9} {'sd@T=390':>10}")
    for phi in PHIS:
        a = df[(df["T"] == 30) & (df["phi"] == phi)].iloc[0]
        b = df[(df["T"] == 390) & (df["phi"] == phi)].iloc[0]
        print(f"{phi:>+6.2f} {a['bias']:>+11.4f} {b['bias']:>+12.4f} "
              f"{b['bias'] - a['bias']:>+9.4f} "
              f"{a['sd_phi_hat']:>9.4f} {b['sd_phi_hat']:>10.4f}")

    print("\n----- exposure of the predicted-NULL cells -----")
    for T, label in ((44516, "vei_exploration AC1 (pooled pairs)"),
                     (3710, "a per-session statistic over the sample")):
        sub = df[df["T"] == T]
        print(f"  T={T:>6}  {label}: max |bias| over phi = "
              f"{sub['bias'].abs().max():.5f}")
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    run()
