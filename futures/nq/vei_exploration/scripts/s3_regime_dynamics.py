"""Study D -- does the VEI REGIME select momentum vs mean-reversion?

"Volatility plays a role in every strategy": the classic claim is that CALM /
CONTRACTING tapes (VEI < 1) mean-revert (fades work) while EXPANDING tapes (VEI > 1)
trend (breakouts/momentum work). We test it directly and causally, with NO trading:

  For each decision bar, split by VEI regime (low / calm / high). Within each regime
  measure the sign of the trailing->forward return relationship:
    corr( past_ret over last 30m , fwd_ret over next 30m )
  NEGATIVE = mean-reverting (fade the move); POSITIVE = trending (go with the move).
  Session-block bootstrap CI. Also report the forward variance ratio VR(q) of the
  1-min return path following each regime (>1 trending, <1 reverting).

If the thesis holds we expect corr < 0 in low VEI and corr >= 0 (less negative / positive)
in high VEI -- i.e. VEI is a strategy-TYPE selector even though it predicts no direction.

Usage: python -u -m futures.nq.vei_exploration.scripts.s3_regime_dynamics {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import loaders as L
from ..core import vei as V
from ..core import analysis as A

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "D_regime_dynamics"
PERIOD = 30
DM = [j * PERIOD - 1 for j in range(1, 14)]
SEED = 73000
VEI_KW = dict(short=10, long=50, atr_method="wilder", smooth=0)
REGIMES = [("low(<0.90)", -np.inf, 0.90),
           ("calm(0.90-1.10)", 0.90, 1.10),
           ("high(>1.10)", 1.10, np.inf)]


def boot_corr_ci(df, xcol, ycol, rng, nboot=1000):
    d = df.dropna(subset=[xcol, ycol])
    if len(d) < 50:
        return np.nan, np.nan, np.nan
    x = d[xcol].to_numpy(float); y = d[ycol].to_numpy(float)
    real = float(np.corrcoef(x, y)[0, 1])
    codes, uniq = pd.factorize(d["date"].to_numpy())
    order = np.argsort(codes, kind="stable")
    x = x[order]; y = y[order]
    counts = np.bincount(codes, minlength=len(uniq))
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    sl = [slice(starts[i], starts[i] + counts[i]) for i in range(len(uniq))]
    out = np.empty(nboot)
    for b in range(nboot):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        xx = np.concatenate([x[sl[j]] for j in pick])
        yy = np.concatenate([y[sl[j]] for j in pick])
        out[b] = np.corrcoef(xx, yy)[0, 1] if len(xx) > 2 else np.nan
    return real, float(np.nanpercentile(out, 5)), float(np.nanpercentile(out, 95))


def run(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bars = L.load_1m_rth(inst)
    b = V.add_vei(bars, **VEI_KW)
    feat = b[b["mfo"].isin(DM)][["sdate", "mfo", "vei"]].rename(columns={"sdate": "date"})
    ff = A.forward_features(bars, DM, horizons=(30,), past_win=30)
    d = feat.merge(ff, on=["date", "mfo"]).dropna(subset=["vei", "past_ret", "fwd_ret_30"])

    print(f"\n======== Study D: VEI regime -> momentum vs mean-reversion — {inst} ========")
    print(f"VEI variant: {VEI_KW}  (seed={VEI_KW.get('seed', V.SEED_SMA)})")
    print(f"{'regime':>18} {'n':>7} {'corr(past,fwd)':>16} {'CI':>20} {'read':>14}")
    rows = []
    for name, lo, hi in REGIMES:
        sub = d[(d["vei"] >= lo) & (d["vei"] < hi)]
        c, clo, chi = boot_corr_ci(sub, "past_ret", "fwd_ret_30", rng)
        read = "reverting" if chi < 0 else ("trending" if clo > 0 else "random-walk")
        print(f"{name:>18} {len(sub):>7} {c:>+16.4f} [{clo:+.4f},{chi:+.4f}] {read:>14}")
        rows.append({"regime": name, "n": len(sub), "corr": c,
                     "ci_lo": clo, "ci_hi": chi, "read": read})
    pd.DataFrame(rows).to_csv(OUT / f"regime_{inst}.csv", index=False)
    print("\ncorr<0 = trailing move reverses (fade works); corr>0 = continues (momentum).")

    # ---- HYP-0003 kill test 3: is the high-regime result a FEATURE effect or a
    # THRESHOLD effect? Repairing the ATR warm-up shifts the VEI distribution, so a
    # fixed 1.10 cut selects a different-sized set. Re-run the high regime at the
    # LEGACY-seed selection RATE so the comparison holds the count fixed.
    bl = V.add_vei(bars, **{**VEI_KW, "seed": V.SEED_FIRST})
    dl = bl[bl["mfo"].isin(DM)][["sdate", "mfo", "vei"]].rename(
        columns={"sdate": "date", "vei": "vei_legacy"})
    dd = d.merge(dl, on=["date", "mfo"], how="left")
    share_legacy = float((dd["vei_legacy"] > 1.10).mean())
    t_match = float(dd["vei"].quantile(1.0 - share_legacy))

    print(f"\n--- threshold confound control (HYP-0003 kill test 3) ---")
    print(f"legacy-seed share above 1.10 = {share_legacy:.4f}; "
          f"matched-rate threshold on repaired VEI = {t_match:.4f}")
    print(f"{'cut':>28} {'n':>7} {'corr(past,fwd)':>16} {'CI':>20}")
    ctrl = []
    for label, mask in [
        (f"repaired, abs T>1.10", dd["vei"] > 1.10),
        (f"repaired, matched-rate T>{t_match:.3f}", dd["vei"] > t_match),
        (f"LEGACY, abs T>1.10", dd["vei_legacy"] > 1.10),
    ]:
        sub = dd[mask]
        c, clo, chi = boot_corr_ci(sub, "past_ret", "fwd_ret_30", rng)
        print(f"{label:>28} {len(sub):>7} {c:>+16.4f} [{clo:+.4f},{chi:+.4f}]")
        ctrl.append({"cut": label, "n": len(sub), "corr": c,
                     "ci_lo": clo, "ci_hi": chi})
    pd.DataFrame(ctrl).to_csv(OUT / f"threshold_control_{inst}.csv", index=False)
    print("Read: if the repaired result holds at BOTH the absolute and the matched-rate\n"
          "cut, it is a feature effect; if only at one, it is a threshold effect.")
    print(f"artifacts -> {OUT}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
