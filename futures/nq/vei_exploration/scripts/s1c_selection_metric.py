"""Next action 0b -- is `IC_fwdvol` a valid metric for SELECTING a VEI variant?

EXP-0006 left an open lead: longer-memory VEI scores monotonically higher on
forward-vol IC (`wilder_20_100` reached +0.396 NQ / +0.353 ES against the canonical
`wilder_10_50`'s +0.202 / +0.207). Adopting the winner would be a mistake if the metric
is rewarding the wrong thing, because Study B established that the vol LEVEL forecasts
forward realized vol all by itself at rank IC +0.86 -- far better than any VEI variant.

THE SUSPICION. VEI = ATR(short)/ATR(long) is meant to measure volatility EXPANSION,
i.e. the CHANGE in vol relative to its own recent baseline, which is a different
quantity from the vol LEVEL. But as the denominator's memory grows, ATR(long) becomes
nearly constant within a session, and dividing by a near-constant is not forming a
ratio at all -- it is rescaling ATR(short). In that limit VEI degenerates INTO the
level. So a variant can climb the `IC_fwdvol` table simply by becoming more level-like
and less ratio-like, i.e. by ceasing to measure the thing the project is studying.

THE TEST. Four columns, all on ONE common sample (see below):

  corr_lvl    Spearman(variant, vol level). How level-like the variant is. Rises with
              denominator memory if the degeneracy story is right.
  IC_fwdvol   the incumbent metric.
  IC_partial  Spearman(variant, fwd vol | level) -- the variant's own contribution
              after the level is partialled out of both sides. This is what a vol-
              forecasting selection metric SHOULD score.
  contrast    the project's actual primary metric: Study D's count-weighted WITHIN-SLOT
              high-vs-rest momentum contrast, at a MATCHED SELECTION RATE so a variant
              cannot win by relabelling more decisions as "high".

The decisive controls are the two `LEVEL:` rows, which are ATR(short) with NO
denominator -- pure level, zero ratio content. They are not candidate features; they
are the degenerate limit. If `IC_fwdvol` is measuring level-likeness then the pure
level must TOP that column, and the cross-variant regression of IC_fwdvol on corr_lvl
must be tight. If instead the ratio carries genuine forward-vol information, the pure
level should not dominate a metric that variants are being selected on.

COMMON SAMPLE. Variants have different warm-ups, so `long=100` is undefined until bar
99 and defines a smaller, later set of decisions than `long=25`. Comparing ICs across
different samples confounds the estimator with the time of day it is measured at (the
project's standing hazard -- see FINDINGS section A-corrected (b)). Every number here
is therefore computed on the intersection where EVERY variant is defined, and the
per-variant own-sample count is printed alongside so the cost is visible.

RULE 26. Scanning variants against the project's primary metric is a SEARCH. The
`contrast` column is reported so the selection decision is made with its consequence
for the primary metric visible -- it is NOT a licence to crown the argmax as a finding.
Study D is already qualified/inconclusive on consumed history; a variant that scores
higher here has not revived it.

Usage: python -u -m futures.nq.vei_exploration.scripts.s1c_selection_metric {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import loaders as L
from ..core import vei as V
from ..core import analysis as A
from .s4_term_structure import (slot_contrast_arrays, weighted_slot_contrast,
                                boot_slot_contrast)

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0008"
SEED = 76000
DM = A.DM
H = 30                     # forward vol / forward return horizon, matches Study B/D
NBOOT_IC = 500
NBOOT_CONTRAST = 400
T_HIGH = 1.10              # the Study D cut, used ONLY to set the matched selection rate
CANON = dict(short=10, long=50, atr_method="wilder", smooth=0)

# (label, kind, kwargs). kind 'vei' = ratio; kind 'level' = ATR(short) alone, the
# degenerate no-denominator control.
VARIANTS = [
    ("LEVEL: atr_10 (no ratio)", "level", dict(n=10, atr_method="wilder")),
    ("LEVEL: atr_20 (no ratio)", "level", dict(n=20, atr_method="wilder")),
    ("wilder_5_25",   "vei", dict(short=5,  long=25,  atr_method="wilder")),
    ("wilder_10_25",  "vei", dict(short=10, long=25,  atr_method="wilder")),
    ("wilder_10_50 [CANON]", "vei", dict(short=10, long=50, atr_method="wilder")),
    ("wilder_5_50",   "vei", dict(short=5,  long=50,  atr_method="wilder")),
    ("wilder_20_50",  "vei", dict(short=20, long=50,  atr_method="wilder")),
    ("wilder_10_100", "vei", dict(short=10, long=100, atr_method="wilder")),
    ("wilder_20_100", "vei", dict(short=20, long=100, atr_method="wilder")),
    ("sma_19_99 [com=w10_50]", "vei", dict(short=19, long=99, atr_method="sma")),
]


def build(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """One row per decision point, one column per variant, plus targets."""
    ff = A.forward_features(bars, DM, horizons=(H,), past_win=30)
    keep = ["date", "mfo", "past_rv", "past_ret", f"fwd_absvar_{H}", f"fwd_ret_{H}"]
    d = ff[keep].copy()
    own_n = {}
    for name, kind, kw in VARIANTS:
        if kind == "level":
            s = V.intraday_atr(bars, kw["n"], kw["atr_method"])
        else:
            s = V.vei_series(bars, **kw)
        col = bars[["sdate", "mfo"]].copy()
        col["v"] = s.to_numpy()
        col = col[col["mfo"].isin(DM)].rename(columns={"sdate": "date"})
        d = d.merge(col.rename(columns={"v": name}), on=["date", "mfo"], how="left")
        own_n[name] = int(d[name].notna().sum())
    return d, own_n


def run(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bars = L.load_1m_rth(inst)
    d, own_n = build(bars)

    names = [n for n, _, _ in VARIANTS]
    targets = ["past_rv", "past_ret", f"fwd_absvar_{H}", f"fwd_ret_{H}"]
    common = d.dropna(subset=names + targets).copy()

    print(f"\n===== 0b: is IC_fwdvol a valid selection metric? — {inst} =====")
    print(f"sessions={bars['sdate'].nunique()}  decision clock=30m  horizon={H}m")
    print(f"common sample n={len(common)} over "
          f"{common['mfo'].nunique()}/{len(DM)} slots "
          f"(mfo {common['mfo'].min()}..{common['mfo'].max()}); "
          f"level = past_rv (Study B's baseline predictor)")

    # matched selection rate: the share the CANONICAL cut would take on this sample
    canon_col = "wilder_10_50 [CANON]"
    rate = float((common[canon_col] > T_HIGH).mean())
    print(f"matched selection rate = {rate:.4f} "
          f"(share of common sample with canonical VEI > {T_HIGH}), "
          f"n_high={int(round(rate*len(common)))}")

    print(f"\n{'variant':>26} {'own_n':>7} {'corr_lvl':>9} {'IC_fwdvol':>10} "
          f"{'IC_partial':>11} {'partial_CI':>18} {'contrast':>9} {'contrast_CI':>18}")
    rows = []
    for name in names:
        corr_lvl = A.spearman(common[name].to_numpy(float),
                              common["past_rv"].to_numpy(float))
        ic, _, _ = A.block_boot_ic(common, name, f"fwd_absvar_{H}", rng, NBOOT_IC)
        pic, plo, phi = A.block_boot_partial_ic(common, name, f"fwd_absvar_{H}",
                                                "past_rv", rng, NBOOT_IC)
        # primary metric at MATCHED count
        c = common.copy()
        c["_hi"] = c[name] >= c[name].quantile(1.0 - rate)
        arr = slot_contrast_arrays(c, "_hi", "past_ret", f"fwd_ret_{H}")
        _, _, diff = weighted_slot_contrast(arr)
        clo, chi = boot_slot_contrast(c, arr, rng, NBOOT_CONTRAST)
        print(f"{name:>26} {own_n[name]:>7} {corr_lvl:>+9.3f} {ic:>+10.4f} "
              f"{pic:>+11.4f} [{plo:+.4f},{phi:+.4f}] {diff:>+9.4f} "
              f"[{clo:+.4f},{chi:+.4f}]")
        rows.append({"variant": name, "own_n": own_n[name], "common_n": len(common),
                     "corr_lvl": corr_lvl, "ic_fwdvol": ic, "ic_partial": pic,
                     "partial_lo": plo, "partial_hi": phi,
                     "contrast": diff, "contrast_lo": clo, "contrast_hi": chi})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"selection_metric_{inst}.csv", index=False)

    # ---- the diagnostic: does corr_lvl EXPLAIN IC_fwdvol across variants? ----
    print("\n--- cross-variant diagnostic: regress each metric on corr_lvl ---")
    x = res["corr_lvl"].to_numpy(float)
    diag = []
    for col in ("ic_fwdvol", "ic_partial", "contrast"):
        y = res[col].to_numpy(float)
        m = np.isfinite(x) & np.isfinite(y)
        b, a = np.polyfit(x[m], y[m], 1)
        r = float(np.corrcoef(x[m], y[m])[0, 1])
        print(f"  {col:>10} = {a:+.4f} {b:+.4f}*corr_lvl   r={r:+.3f}  R2={r*r:.3f}")
        diag.append({"metric": col, "intercept": a, "slope": b, "r": r, "r2": r * r})
    pd.DataFrame(diag).to_csv(OUT / f"selection_diag_{inst}.csv", index=False)

    lvl_rows = res[res["variant"].str.startswith("LEVEL:")]
    vei_rows = res[~res["variant"].str.startswith("LEVEL:")]
    print("\n--- degenerate-limit control (pure level vs best ratio) ---")
    for col, lab in (("ic_fwdvol", "IC_fwdvol"), ("ic_partial", "IC_partial"),
                     ("contrast", "contrast")):
        bl = lvl_rows[col].max()
        bv = vei_rows[col].max()
        who = vei_rows.loc[vei_rows[col].idxmax(), "variant"]
        flag = "LEVEL WINS" if bl >= bv else "ratio wins"
        print(f"  {lab:>10}: best LEVEL {bl:+.4f}   best ratio {bv:+.4f} ({who})"
              f"   -> {flag}")
    print(f"\nReads: if corr_lvl explains IC_fwdvol (high R2) AND the pure level tops "
          f"the IC_fwdvol\ncolumn, that metric is scoring level-likeness and must not "
          f"select a RATIO.\nartifacts -> {OUT}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
