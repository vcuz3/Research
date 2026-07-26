"""Study A -- SMOOTHING the VEI (user request: "did you try a smoothing function?").

REVISED 2026-07-26 (EXP-0006). The original run concluded "the ATR estimator dominates";
that was a confounded comparison and has been withdrawn (reports/FINDINGS.md
section A-corrected). Two things are now controlled for:
  * MEMORY. SMA(n) has centre-of-mass (n-1)/2 but Wilder(n) has n-1, so comparing
    sma(10,50) with wilder(10,50) moves estimator form AND effective memory together.
    Memory-matched cells are included in BOTH directions (sma_19_99 up, wilder_5_25 down).
  * WARM-UP. `ewm(adjust=False, min_periods=n)` seeds at bar 0 rather than at the first
    n-bar SMA; with a per-session ATR reset that bias is paid every session. Cells marked
    `L:` use the legacy seeding and reproduce EXP-0001 exactly (rule 23).
Rows are directly comparable only at equal `defined` counts -- read the com-matched pairs.

Raw VEI = ATR(short)/ATR(long) with simple rolling-mean ATR is jumpy and whipsaws
across the 1.0 regime line. We compare smoothing choices on THREE axes that matter
for a regime signal:
  1. persistence  = lag-1 autocorr of VEI across consecutive decision bars (higher =
     a steadier regime read);
  2. whipsaw rate = fraction of consecutive decision pairs that cross VEI=1 (lower =
     fewer false regime flips);
  3. forward-vol information = block-bootstrap Spearman IC of VEI vs forward realized
     abs-variation over the next 30 min (smoothing must not destroy the signal).

Smoothing choices: ATR method {sma, wilder, ema} and an EMA on the ratio (spans).
A good smoother RAISES persistence and CUTS whipsaws while HOLDING the forward-vol IC.

Usage: python -u -m futures.nq.vei_exploration.scripts.s1_smoothing {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import loaders as L
from ..core import vei as V
from ..core import analysis as A

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "A_smoothing"
PERIOD = 30
DM = [j * PERIOD - 1 for j in range(1, 14)]   # 29,59,...,389
SEED = 71000

L_ = V.SEED_FIRST   # legacy pandas ewm warm-up (reproduces EXP-0001)
S_ = V.SEED_SMA     # textbook Wilder warm-up (current default)

VARIANTS = [
    # --- EXP-0001's original six, rerun under the LEGACY seed (rule 23 reproduction) --
    ("sma_10_50_raw",     dict(short=10, long=50, atr_method="sma",    smooth=0)),
    ("L:wilder_10_50",    dict(short=10, long=50, atr_method="wilder", smooth=0, seed=L_)),
    ("L:ema_10_50",       dict(short=10, long=50, atr_method="ema",    smooth=0, seed=L_)),
    ("sma_10_50_s3",      dict(short=10, long=50, atr_method="sma",    smooth=3)),
    ("sma_10_50_s5",      dict(short=10, long=50, atr_method="sma",    smooth=5)),
    ("sma_10_50_s10",     dict(short=10, long=50, atr_method="sma",    smooth=10)),
    # --- the WARM-UP repair (section A-corrected part 2) -----------------------------
    ("wilder_10_50",      dict(short=10, long=50, atr_method="wilder", smooth=0, seed=S_)),
    ("ema_10_50",         dict(short=10, long=50, atr_method="ema",    smooth=0, seed=S_)),
    # --- MEMORY-matched controls, both directions (section A-corrected part 1) --------
    # SMA(n) com=(n-1)/2, Wilder(n) com=n-1. So sma(19,99) ~ wilder(10,50) and
    # wilder(5,25) ~ sma(10,50). Matching only one direction can be explained away.
    ("sma_19_99  [com=w10_50]",  dict(short=19, long=99, atr_method="sma", smooth=0)),
    ("wilder_5_25 [com=sma10_50]", dict(short=5, long=25, atr_method="wilder", smooth=0, seed=S_)),
    # Wilder alpha=1/n IS ewm(span=2n-1): same recursion, so this isolates min_periods.
    ("ema_19_99  [alpha=w10_50]", dict(short=19, long=99, atr_method="ema", smooth=0, seed=L_)),
    # --- longer-memory Wilder cells, now that memory is the identified axis -----------
    ("wilder_20_100",     dict(short=20, long=100, atr_method="wilder", smooth=0, seed=S_)),
]


def persistence_and_whipsaw(feat: pd.DataFrame) -> tuple[float, float]:
    """lag-1 autocorr across consecutive decision bars within session; whipsaw =
    fraction of consecutive pairs that cross the VEI=1 line."""
    x0, x1, cross, npair = [], [], 0, 0
    for _, g in feat.groupby("date", sort=False):
        v = g.sort_values("mfo")["vei"].to_numpy(float)
        for i in range(len(v) - 1):
            if np.isfinite(v[i]) and np.isfinite(v[i + 1]):
                x0.append(v[i]); x1.append(v[i + 1]); npair += 1
                if (v[i] - 1.0) * (v[i + 1] - 1.0) < 0:
                    cross += 1
    x0 = np.asarray(x0); x1 = np.asarray(x1)
    ac = float(np.corrcoef(x0, x1)[0, 1]) if len(x0) > 2 else np.nan
    return ac, (cross / npair if npair else np.nan)


def run(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bars = L.load_1m_rth(inst)
    ff = A.forward_features(bars, DM, horizons=(30,), past_win=30)

    print(f"\n============ Study A: VEI smoothing — {inst} ============")
    print(f"sessions={bars['sdate'].nunique()}  decision clock={PERIOD}m")
    print(f"{'variant':>28} {'defined':>8} {'mean':>6} {'p10':>6} {'p90':>6} "
          f"{'AC1':>6} {'whipsaw':>8} {'IC_fwdvol':>10} {'IC_CI':>18}")
    rows = []
    for name, kw in VARIANTS:
        b = V.add_vei(bars, **kw)
        feat = b[b["mfo"].isin(DM)][["sdate", "mfo", "vei"]].rename(
            columns={"sdate": "date"})
        ac, whip = persistence_and_whipsaw(feat)
        m = feat.merge(ff[["date", "mfo", "fwd_absvar_30"]], on=["date", "mfo"])
        ic, lo, hi = A.block_boot_ic(m, "vei", "fwd_absvar_30", rng)
        v = feat["vei"].dropna()
        print(f"{name:>28} {len(v):>8} {v.mean():>6.3f} {v.quantile(.1):>6.3f} "
              f"{v.quantile(.9):>6.3f} {ac:>6.3f} {whip:>8.3f} {ic:>+10.4f} "
              f"[{lo:+.4f},{hi:+.4f}]")
        rows.append({"variant": name, "defined": len(v), "mean": v.mean(),
                     "ac1": ac, "whipsaw": whip, "ic_fwdvol": ic,
                     "ic_lo": lo, "ic_hi": hi})
    pd.DataFrame(rows).to_csv(OUT / f"smoothing_{inst}.csv", index=False)
    print(f"\nReads: a good smoother RAISES AC1 and LOWERS whipsaw while HOLDING "
          f"IC_fwdvol. artifacts -> {OUT}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
