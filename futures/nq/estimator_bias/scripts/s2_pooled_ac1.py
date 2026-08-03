"""HYP-0001 Study 2 (Cell B) -- audit vei_exploration's AC1 persistence column.

Two opposite-signed biases live in the same statistic, and Study 1 already showed
they cannot both matter:

  * SMALL-SAMPLE bias pulls a lag-1 estimate toward zero, by -(1+3phi)/T. The
    published AC1 pools ~4.5e4 within-session pairs, so this is ~1e-4. PREDICTED
    NULL: correction moves nothing.
  * SLOT POOLING pushes it UP. VEI has a documented deterministic intraday profile
    (mean 0.745 -> 1.165 across the session, FINDINGS section A), so two consecutive
    readings covary partly because both are late-session, not because the regime
    persisted. PREDICTED MATERIAL: slot-demeaning cuts AC1.

The third column is the one that would actually have bitten someone: the same
statistic computed PER SESSION (T=13 pairs, the natural thing to do) instead of
pooled -- where Study 1 says the bias is -0.10 to -0.28.

Rule 23: the `published` column reproduces FINDINGS section A / EXP-0006 before
anything is audited.

Usage: python -u -m futures.nq.estimator_bias.scripts.s2_pooled_ac1 [NQ|ES]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ...vei_exploration.core import loaders as VL
from ...vei_exploration.core import vei as V
from ..core import arbias as A

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0001"
PERIOD = 30
DM = [j * PERIOD - 1 for j in range(1, 14)]      # 29, 59, ..., 389
SEED = 82000

# The published rows we are auditing. Values read from the frozen artifact
# vei_exploration/artifacts/runs/A_smoothing/smoothing_{NQ,ES}.csv (rule 23), not from
# the rounded table in FINDINGS section A.
VARIANTS = [
    ("sma_10_50_raw",  dict(short=10, long=50, atr_method="sma", smooth=0)),
    ("L:wilder_10_50", dict(short=10, long=50, atr_method="wilder", smooth=0,
                            seed=V.SEED_FIRST)),
    ("wilder_10_50",   dict(short=10, long=50, atr_method="wilder", smooth=0,
                            seed=V.SEED_SMA)),
    ("L:ema_10_50",    dict(short=10, long=50, atr_method="ema", smooth=0,
                            seed=V.SEED_FIRST)),
]
PUBLISHED = {
    "NQ": {"sma_10_50_raw": -0.011181, "L:wilder_10_50": 0.549460,
           "wilder_10_50": 0.441143, "L:ema_10_50": 0.160876},
    "ES": {"sma_10_50_raw": -0.015066, "L:wilder_10_50": 0.506246,
           "wilder_10_50": 0.403646, "L:ema_10_50": 0.138612},
}
REPRO_TOL = 1e-4      # rule 23: deterministic work on identical inputs


def per_session_ac1(df: pd.DataFrame, col: str) -> tuple[float, float, int]:
    """Mean and sd of the WITHIN-session lag-1 estimate (T = 13 pairs each)."""
    vals = []
    for _, g in df.groupby("date", sort=False):
        v = g.sort_values("mfo")[col].to_numpy(float)
        v = v[np.isfinite(v)]
        if len(v) >= 8:
            vals.append(A.ols_ar1(v))
    a = np.array(vals, dtype=float)
    a = a[np.isfinite(a)]
    return float(a.mean()), float(a.std(ddof=1)), len(a)


def run(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bars = VL.load_1m_rth(inst)

    print(f"\n===== Study 2 (Cell B): pooled AC1 audit -- {inst} =====")
    print(f"sessions={bars['sdate'].nunique()}  decision clock={PERIOD}m  "
          f"slots={len(DM)}")
    print("\nPooled AC1 = one corrcoef over every within-session consecutive pair")
    print("(reproduces vei_exploration/scripts/s1_smoothing.py::persistence_and_whipsaw)\n")
    print(f"{'variant':>16} {'pairs':>7} {'published':>10} {'pooled':>8} {'repro':>7} "
          f"{'kendall':>8} {'d_kend':>8} {'slot-dm':>8} {'d_slot':>8}")

    rows = []
    for name, kw in VARIANTS:
        published = PUBLISHED[inst][name]
        b = V.add_vei(bars, **kw)
        feat = (b[b["mfo"].isin(DM)][["sdate", "mfo", "vei"]]
                .rename(columns={"sdate": "date"}))
        ac, npair = A.pooled_lag1(feat, "vei")
        ken = A.kendall_correct(ac, npair)
        dm, _ = A.pooled_lag1_slot_demeaned(feat, "vei")
        ok = "OK" if abs(ac - published) < REPRO_TOL else "DIFF"
        print(f"{name:>16} {npair:>7} {published:>+10.4f} {ac:>+8.4f} {ok:>7} "
              f"{ken:>+8.4f} {ken - ac:>+8.4f} {dm:>+8.4f} {dm - ac:>+8.4f}")
        rows.append({"inst": inst, "variant": name, "pairs": npair,
                     "published": published, "pooled_ac1": ac,
                     "kendall_ac1": ken, "d_kendall": ken - ac,
                     "slot_demeaned_ac1": dm, "d_slot": dm - ac})

    # ---- the short-window sibling: what a PER-SESSION estimate would have said ---- #
    print("\n----- the same statistic computed PER SESSION (T=13 pairs) -----")
    print("Study 1 says a T=13 lag-1 estimate is biased -0.10 to -0.28. This is what a")
    print("per-session persistence column would have reported, and its repair:\n")
    print(f"{'variant':>16} {'sessions':>9} {'mean AC1':>9} {'sd':>7} "
          f"{'kendall':>8} {'bootstrap':>10}")
    for name, kw in VARIANTS:
        b = V.add_vei(bars, **kw)
        feat = (b[b["mfo"].isin(DM)][["sdate", "mfo", "vei"]]
                .rename(columns={"sdate": "date"}))
        m, s, n = per_session_ac1(feat, "vei")
        ken = A.kendall_correct(m, len(DM))
        # bootstrap corrector on one representative session-length series each draw
        boots = []
        for _, g in list(feat.groupby("date", sort=False))[:120]:
            v = g.sort_values("mfo")["vei"].to_numpy(float)
            v = v[np.isfinite(v)]
            if len(v) >= 10:
                boots.append(A.bootstrap_ar1_correct(v, rng, nboot=200))
        boo = float(np.nanmean(boots)) if boots else np.nan
        print(f"{name:>16} {n:>9} {m:>+9.4f} {s:>7.4f} {ken:>+8.4f} {boo:>+10.4f}")
        rows[[r["variant"] for r in rows].index(name)].update(
            {"per_session_mean_ac1": m, "per_session_sd": s,
             "per_session_kendall": ken, "per_session_bootstrap": boo})

    df = pd.DataFrame(rows)
    fp = OUT / f"pooled_ac1_{inst}.csv"
    df.to_csv(fp, index=False)

    print("\n----- verdict inputs -----")
    print(f"  max |kendall - pooled| over variants: "
          f"{df['d_kendall'].abs().max():.5f}   (Cell B kill threshold 0.01)")
    print(f"  max |slot-demeaned - pooled|:         "
          f"{df['d_slot'].abs().max():.5f}")
    print(f"\nartifacts -> {fp}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
