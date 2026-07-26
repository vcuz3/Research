"""HYP-0006 -- the noise-area construction applied to VEI itself.

VEI is not centred on 1 and drifts monotonically upward all session (mean by slot
0.745->1.165 NQ), because the session-reset long ATR stays anchored on the volatile open
while the short one walks off it. So `VEI > 1.10` is a LATE-SESSION selector wearing a
volatility label -- it fires on ~1% of morning decisions and 19-64% of late ones. That is
a calibration defect that makes the feature undeployable as a regime gate, whatever its
information content.

The fix is the noise-area idea applied to the feature rather than to displacement:
compare each reading with its own trailing history AT THE SAME TIME OF DAY. Four
features, all at MATCHED selection rate on ONE common sample:

  raw   the canonical repaired VEI (baseline; single-variable change)
  rel   VEI / trailing same-slot MEAN          -- location removed, magnitude kept
  z     (VEI - mu_slot) / sd_slot              -- location AND scale removed
  pct   causal same-slot PERCENTILE            -- ordinal; what EXP-0005/0006 tested

`rel` and `z` are the magnitude-preserving members of the family and have never been
run; `pct` discards how far above normal a reading is. Carrying `pct` keeps the result
comparable with EXP-0005's "de-seasonalising destroys information" and EXP-0006's
reversal of it.

TWO CO-PRIMARY METRICS (HYP-0006):
  1. CALIBRATION -- spread of the per-slot selection rate at a fixed global rate. Close
     to mechanical (the construction is designed to flatten this, and the unit test shows
     it does on a toy); reported to size the fix, not as a discriminating test.
  2. INFORMATION -- the count-weighted WITHIN-SLOT momentum contrast (the project's
     established primary metric), plus the POOLED contrast, which is where the
     calibration gain should show up because raw's pooled selection is slot-confounded
     and the normalised features' is not.

The real risk is metric 2. EXP-0008 showed the momentum information lives in the RATIO
and that the vol LEVEL carries none of it, so normalising the ratio again could normalise
the signal away -- which is what EXP-0005 originally concluded before EXP-0006 reversed
it on overlapping CIs. Kill test 1 in HYP-0006 is the decision rule.

This CANNOT revive Study D and is not evidence for an edge; see HYP-0006.

Usage: python -u -m futures.nq.vei_exploration.scripts.s5_slot_normalised {NQ|ES}
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
                                boot_slot_contrast, clock)

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0009"
SEED = 77000
DM = A.DM
H = 30
T_HIGH = 1.10                 # the Study D cut, used ONLY to set the matched rate
CANON = dict(short=10, long=50, atr_method="wilder", smooth=0)
LOOKBACK, MIN_OBS = 90, 60    # matched to causal_slot_percentile (single-variable)
LB_SENSITIVITY = [30, 90, 180]
NBOOT = 400

FEATURES = ["raw", "rel", "z", "pct"]


def pooled_contrast(d: pd.DataFrame, hicol: str, xcol: str, ycol: str,
                    rng, nboot: int = NBOOT):
    """Pooled corr(past, fwd) among high minus among the rest, block-bootstrapped.

    The counterpart to the within-slot statistic. Reported because a deployed gate
    selects POOLED -- and for the raw feature that selection is slot-confounded, which
    is precisely what the normalisation is meant to remove.
    """
    hi = d[d[hicol]]
    lo = d[~d[hicol]]
    if len(hi) < 50 or len(lo) < 50:
        return np.nan, np.nan, np.nan
    c_hi = float(np.corrcoef(hi[xcol], hi[ycol])[0, 1])
    c_lo = float(np.corrcoef(lo[xcol], lo[ycol])[0, 1])
    order, sl = A.session_slices(d, "date")
    x = d[xcol].to_numpy(float)[order]
    y = d[ycol].to_numpy(float)[order]
    h = d[hicol].to_numpy(bool)[order]
    idx = [np.arange(s.start, s.stop) for s in sl]
    boots = np.empty(nboot)
    for b in range(nboot):
        pick = rng.integers(0, len(sl), size=len(sl))
        take = np.concatenate([idx[j] for j in pick])
        xb, yb, hb = x[take], y[take], h[take]
        if hb.sum() < 20 or (~hb).sum() < 20:
            boots[b] = np.nan
            continue
        boots[b] = (np.corrcoef(xb[hb], yb[hb])[0, 1]
                    - np.corrcoef(xb[~hb], yb[~hb])[0, 1])
    return (c_hi - c_lo, float(np.nanpercentile(boots, 5)),
            float(np.nanpercentile(boots, 95)))


def _min_obs_for(lookback: int) -> int:
    """Hold the fractional min_obs POLICY constant as the lookback varies.

    The default pair is (90, 60) = two thirds, matched to `causal_slot_percentile`.
    A fixed `min_obs=60` would be unreachable at `lookback=30` and would silently
    define nothing, so the sensitivity sweep scales it (rule 9a: the coverage rule is
    part of the feature, and changing it mid-sweep would confound the comparison).
    """
    return max(5, int(round(lookback * MIN_OBS / LOOKBACK)))


def build(bars: pd.DataFrame, lookback: int = LOOKBACK) -> pd.DataFrame:
    """Decision-clock frame with the four features and the momentum targets."""
    mo = _min_obs_for(lookback)
    b = V.add_vei(bars, **CANON)
    feat = b[b["mfo"].isin(DM)][["sdate", "mfo", "vei"]].rename(
        columns={"sdate": "date"})
    ff = A.forward_features(bars, DM, horizons=(H,), past_win=30)
    d = feat.merge(ff[["date", "mfo", "past_ret", f"fwd_ret_{H}"]],
                   on=["date", "mfo"]).sort_values(["date", "mfo"]).reset_index(drop=True)
    mu, sd = A.causal_slot_stats(d, "vei", lookback=lookback, min_obs=mo)
    d["raw"] = d["vei"]
    d["rel"] = d["vei"] / mu.where(mu > 0)
    d["z"] = (d["vei"] - mu) / sd.where(sd > 0)
    d["pct"] = A.causal_slot_percentile(d, "vei", lookback=lookback, min_obs=mo)
    return d


def run(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bars = L.load_1m_rth(inst)
    d = build(bars)
    targets = ["past_ret", f"fwd_ret_{H}"]
    common = d.dropna(subset=FEATURES + targets).copy()

    print(f"\n===== HYP-0006: slot-normalised VEI — {inst} =====")
    print(f"sessions={bars['sdate'].nunique()}  clock=30m  horizon={H}m  "
          f"trailing window: lookback={LOOKBACK} sessions, min_obs={MIN_OBS}")
    print(f"raw-VEI decisions={int(d['raw'].notna().sum())}  "
          f"common sample n={len(common)} over {common['mfo'].nunique()}/{len(DM)} slots")

    rate = float((common["raw"] > T_HIGH).mean())
    print(f"matched selection rate = {rate:.4f} (share with raw VEI > {T_HIGH})")

    # ---- rule 9a: what the trailing window costs, per slot ----
    print("\n--- (rule 9a) decisions defined per slot ---")
    cov = d.groupby("mfo").agg(raw=("raw", "count"), rel=("rel", "count"),
                               z=("z", "count"), pct=("pct", "count"))
    cov["kept_frac"] = (cov["rel"] / cov["raw"]).round(4)
    cov.index = [f"{m} ({clock(m)})" for m in cov.index]
    print(cov.to_string())
    cov.to_csv(OUT / f"coverage_{inst}.csv")

    # ---- co-primary 1: CALIBRATION ----
    print("\n--- CO-PRIMARY 1: calibration (per-slot selection rate at matched rate) ---")
    print(f"{'feature':>8} {'thr':>9} {'min':>7} {'max':>7} {'spread':>8} {'CV':>7}")
    cal_rows, shares = [], {}
    for f in FEATURES:
        thr = common[f].quantile(1.0 - rate)
        sh = common.assign(hi=common[f] >= thr).groupby("mfo")["hi"].mean()
        shares[f] = sh
        spread = float(sh.max() - sh.min())
        cv = float(sh.std() / sh.mean()) if sh.mean() > 0 else np.nan
        print(f"{f:>8} {thr:>9.4f} {sh.min():>7.4f} {sh.max():>7.4f} "
              f"{spread:>8.4f} {cv:>7.4f}")
        cal_rows.append({"feature": f, "thr": thr, "min": sh.min(), "max": sh.max(),
                         "spread": spread, "cv": cv})
    pd.DataFrame(cal_rows).to_csv(OUT / f"calibration_{inst}.csv", index=False)
    print("\n  per-slot selection share:")
    print(pd.DataFrame(shares).round(3).rename(
        index=lambda m: f"{m} ({clock(m)})").to_string())
    pd.DataFrame(shares).to_csv(OUT / f"slot_share_{inst}.csv")

    # ---- co-primary 2: INFORMATION ----
    print("\n--- CO-PRIMARY 2: momentum contrast at matched selection rate ---")
    print(f"{'feature':>8} {'within_slot':>12} {'within_CI':>20} "
          f"{'pooled':>9} {'pooled_CI':>20}")
    info_rows = []
    for f in FEATURES:
        c = common.copy()
        c["_hi"] = c[f] >= c[f].quantile(1.0 - rate)
        arr = slot_contrast_arrays(c, "_hi", "past_ret", f"fwd_ret_{H}")
        _, _, w = weighted_slot_contrast(arr)
        wlo, whi = boot_slot_contrast(c, arr, rng, NBOOT)
        p, plo, phi = pooled_contrast(c, "_hi", "past_ret", f"fwd_ret_{H}", rng)
        print(f"{f:>8} {w:>+12.4f} [{wlo:+.4f},{whi:+.4f}] {p:>+9.4f} "
              f"[{plo:+.4f},{phi:+.4f}]")
        info_rows.append({"feature": f, "within": w, "within_lo": wlo,
                          "within_hi": whi, "pooled": p, "pooled_lo": plo,
                          "pooled_hi": phi})
    res = pd.DataFrame(info_rows)
    res.to_csv(OUT / f"contrast_{inst}.csv", index=False)

    base = float(res.loc[res["feature"] == "raw", "within"].iloc[0])
    print(f"\n  kill test 1 reference: raw within-slot = {base:+.4f}; "
          f"'materially below' = < {0.75*base:+.4f}")
    for f in ("rel", "z"):
        v = float(res.loc[res["feature"] == f, "within"].iloc[0])
        print(f"    {f}: {v:+.4f} = {v/base*100:5.1f}% of raw"
              f"{'   <-- below 75% gate' if v < 0.75*base else ''}")

    # ---- sensitivity: lookback (NOT a selection dimension) ----
    print("\n--- SENSITIVITY: trailing lookback for `rel` (reported, not selected on) ---")
    sens = []
    for lb in LB_SENSITIVITY:
        dd = build(bars, lookback=lb).dropna(subset=["raw", "rel"] + targets)
        r = float((dd["raw"] > T_HIGH).mean())
        dd["_hi"] = dd["rel"] >= dd["rel"].quantile(1.0 - r)
        arr = slot_contrast_arrays(dd, "_hi", "past_ret", f"fwd_ret_{H}")
        _, _, w = weighted_slot_contrast(arr)
        sh = dd.groupby("mfo")["_hi"].mean()
        print(f"  lb={lb:>3} (min_obs={_min_obs_for(lb):>3})  n={len(dd):>6}  "
              f"within_slot={w:+.4f}  slot-share spread={float(sh.max()-sh.min()):.4f}")
        sens.append({"lookback": lb, "n": len(dd), "within": w,
                     "spread": float(sh.max() - sh.min())})
    pd.DataFrame(sens).to_csv(OUT / f"sensitivity_{inst}.csv", index=False)
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
