"""HYP-0001 Study 3 (Cell A) -- is the expanding-window Hurst gate a clock?

``noise_vwap/scripts/hyp_0017_hurst_filter.py`` computes ``H = ghe1(logp[:i+1])`` at
each 30-minute decision, so the estimator sees 30 one-minute bars at mfo=29 and 390 at
mfo=389, and then applies a FIXED ``H_GRID`` threshold at every one of them. Study 1
showed a finite-window persistence estimator's bias AND its sampling sd are both
deterministic functions of the window length. If that carries to ``ghe1``, the gate
selects a different fraction of the day at different times of day for reasons that have
nothing to do with the market.

Two degenerate controls, both with true H = 0.50 by construction:

  * ``fbm05``    -- constant-volatility fractional Brownian motion. Isolates PURE
                    estimator behaviour.
  * ``signflip`` -- the session's REAL |returns| with iid random signs. Preserves the
                    real intraday volatility seasonality exactly, minute by minute, and
                    destroys every trace of memory. This is the sharper control: if the
                    real per-slot H profile matches it, none of the profile is genuine
                    time-varying persistence.

Primary metric: per-slot selection-rate CV of the fixed threshold versus a causal
same-slot z-score of the same H at MATCHED global selection rate on a COMMON sample.
Calibration (vwap_exploration finding I1): same-slot z ~0.06; a fixed cut ruled a
time-of-day selector scored 0.22-0.36.

Usage: python -u -m futures.nq.estimator_bias.scripts.s3_hurst_gate [NQ|ES]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ...hurst_explore.core import hurst as HX
from ...hurst_explore.core import loaders as HL
from ..core import arbias as A

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0001"
PERIOD = 30
DM = np.array([j * PERIOD - 1 for j in range(1, 14)])     # 29, 59, ..., 389
LOOKBACK, MIN_OBS = 90, 45
SEED = 83000


# --------------------------------------------------------------------------- #
# feature construction: the deployed gate, plus its two null siblings
# --------------------------------------------------------------------------- #
def build(inst: str, rng: np.random.Generator) -> pd.DataFrame:
    """One row per (date, decision mfo) with H under each of the three paths."""
    rows = []
    for sd, logp, _mfo in HL.sessions_1m(inst):
        r = np.diff(logp)

        flip = np.empty_like(logp)
        flip[0] = logp[0]
        flip[1:] = logp[0] + np.cumsum(np.abs(r) * rng.choice((-1.0, 1.0), size=r.size))

        synth = logp[0] + HX.fbm(0.5, len(logp), rng) * float(np.std(r))

        h_real = A.expanding_ghe1(logp, DM)
        h_flip = A.expanding_ghe1(flip, DM)
        h_fbm = A.expanding_ghe1(synth, DM)
        for k, m in enumerate(DM):
            rows.append((sd, int(m), int(m) + 1,
                         h_real[k], h_flip[k], h_fbm[k]))
    return pd.DataFrame(rows, columns=["date", "mfo", "window_bars",
                                       "H_real", "H_signflip", "H_fbm05"])


# --------------------------------------------------------------------------- #
# the diagnostic
# --------------------------------------------------------------------------- #
def gate_profile(df: pd.DataFrame, col: str, zcol: str) -> pd.DataFrame:
    """Per-slot selection-rate CV of a fixed cut vs a matched same-slot z cut."""
    common = df[np.isfinite(df[col]) & np.isfinite(df[zcol])]
    out = []
    for thr in A.H_GRID:
        sel = common[col].to_numpy() >= thr
        rate = float(sel.mean())
        if rate < 0.01 or rate > 0.99:
            out.append({"thr": thr, "global_rate": rate, "n_sel": int(sel.sum()),
                        "cv_fixed": np.nan, "cv_slotz": np.nan, "ratio": np.nan})
            continue
        tz = A.threshold_at_rate(common[zcol].to_numpy(), rate)
        selz = common[zcol].to_numpy() >= tz
        cvf = A.selection_rate_cv(A.per_slot_selection_rate(common, sel))
        cvz = A.selection_rate_cv(A.per_slot_selection_rate(common, selz))
        out.append({"thr": thr, "global_rate": rate, "n_sel": int(sel.sum()),
                    "cv_fixed": cvf, "cv_slotz": cvz,
                    "ratio": cvf / cvz if cvz else np.nan})
    return pd.DataFrame(out)


def run(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    df = build(inst, rng)

    # causal same-slot z of the DEPLOYED feature (rule 9a fractional min_obs)
    df = df.sort_values(["date", "mfo"]).reset_index(drop=True)
    df["z_real"] = A.causal_slot_z(df, "H_real", lookback=LOOKBACK, min_obs=MIN_OBS)

    print(f"\n===== Study 3 (Cell A): expanding-window Hurst gate -- {inst} =====")
    print(f"sessions={df['date'].nunique()}  decisions={len(df)}  "
          f"window grows {DM[0] + 1} -> {DM[-1] + 1} bars within each session")

    # ---- 1. the per-slot profile, real vs the two zero-memory controls ---------- #
    prof = df.groupby("window_bars").agg(
        mean_real=("H_real", "mean"), sd_real=("H_real", "std"),
        mean_flip=("H_signflip", "mean"), sd_flip=("H_signflip", "std"),
        mean_fbm=("H_fbm05", "mean"), sd_fbm=("H_fbm05", "std"),
        n=("H_real", "size")).reset_index()

    print("\n----- per-slot H: real vs two paths with TRUE H = 0.50 -----")
    print(f"{'window':>7} {'n':>6} | {'real':>7} {'sd':>6} | {'signflip':>9} {'sd':>6} "
          f"| {'fbm05':>7} {'sd':>6} | {'real-flip':>10}")
    for _, r in prof.iterrows():
        print(f"{int(r['window_bars']):>7} {int(r['n']):>6} | "
              f"{r['mean_real']:>7.4f} {r['sd_real']:>6.4f} | "
              f"{r['mean_flip']:>9.4f} {r['sd_flip']:>6.4f} | "
              f"{r['mean_fbm']:>7.4f} {r['sd_fbm']:>6.4f} | "
              f"{r['mean_real'] - r['mean_flip']:>+10.4f}")
    print(f"  range of the MEAN across slots:  real {prof['mean_real'].max() - prof['mean_real'].min():.4f}"
          f"   signflip {prof['mean_flip'].max() - prof['mean_flip'].min():.4f}"
          f"   fbm05 {prof['mean_fbm'].max() - prof['mean_fbm'].min():.4f}")
    print(f"  sd compression first->last slot: real "
          f"{prof['sd_real'].iloc[0] / prof['sd_real'].iloc[-1]:.2f}x   signflip "
          f"{prof['sd_flip'].iloc[0] / prof['sd_flip'].iloc[-1]:.2f}x   fbm05 "
          f"{prof['sd_fbm'].iloc[0] / prof['sd_fbm'].iloc[-1]:.2f}x")

    # ---- 2. rule 9a: what the same-slot z deletes, and is it uniform? ----------- #
    cov = df.groupby("window_bars").apply(
        lambda g: float(np.isfinite(g["z_real"]).mean()), include_groups=False)
    print(f"\n----- rule 9a: same-slot z coverage (lookback={LOOKBACK}, "
          f"min_obs={MIN_OBS}) -----")
    print(f"  per-slot coverage min {cov.min():.4f}  max {cov.max():.4f}  "
          f"spread {cov.max() - cov.min():.4f}  (uniform = the pass signal)")

    # ---- 3. THE PRIMARY METRIC ------------------------------------------------- #
    print("\n----- primary metric: per-slot selection-rate CV, matched global rate ---")
    print("(common sample = both the fixed gate and the same-slot z defined)\n")
    tables = {}
    for label, col in (("real", "H_real"), ("signflip", "H_signflip"),
                       ("fbm05", "H_fbm05")):
        zc = "z_real" if col == "H_real" else None
        if zc is None:
            d = df.copy()
            d[f"z_{label}"] = A.causal_slot_z(d, col, lookback=LOOKBACK,
                                              min_obs=MIN_OBS)
            zc = f"z_{label}"
            t = gate_profile(d, col, zc)
        else:
            t = gate_profile(df, col, zc)
        tables[label] = t
        print(f"  path = {label}")
        print(f"  {'H>=thr':>7} {'rate':>7} {'n_sel':>7} {'CV fixed':>9} "
              f"{'CV slot-z':>10} {'ratio':>7}")
        for _, r in t.iterrows():
            if not np.isfinite(r["cv_fixed"]):
                print(f"  {r['thr']:>7.2f} {r['global_rate']:>7.4f} "
                      f"{r['n_sel']:>7} {'--':>9} {'--':>10} {'--':>7}"
                      "   (degenerate rate)")
                continue
            print(f"  {r['thr']:>7.2f} {r['global_rate']:>7.4f} {r['n_sel']:>7} "
                  f"{r['cv_fixed']:>9.4f} {r['cv_slotz']:>10.4f} "
                  f"{r['ratio']:>7.2f}x")
        print()

    real_t = tables["real"].dropna(subset=["ratio"])
    print("----- verdict inputs (Cell A kill test: REJECT if ratio <= 2.0) -----")
    print(f"  usable thresholds: {len(real_t)} of {len(A.H_GRID)}")
    print(f"  CV ratio  min {real_t['ratio'].min():.2f}x   "
          f"median {real_t['ratio'].median():.2f}x   max {real_t['ratio'].max():.2f}x")
    print(f"  fixed-gate CV range: {real_t['cv_fixed'].min():.4f} .. "
          f"{real_t['cv_fixed'].max():.4f}")
    print(f"  slot-z   CV range: {real_t['cv_slotz'].min():.4f} .. "
          f"{real_t['cv_slotz'].max():.4f}   "
          f"(finding I1 benchmark for a same-slot z: 0.060-0.064)")
    flip_t = tables["signflip"].dropna(subset=["ratio"])
    print(f"  degenerate control -- signflip (true H=0.50) fixed-gate CV: "
          f"{flip_t['cv_fixed'].min():.4f} .. {flip_t['cv_fixed'].max():.4f}")

    df.to_parquet(OUT / f"hurst_gate_{inst}.parquet", index=False)
    prof.to_csv(OUT / f"hurst_slot_profile_{inst}.csv", index=False)
    pd.concat([t.assign(path=k) for k, t in tables.items()]).to_csv(
        OUT / f"hurst_gate_cv_{inst}.csv", index=False)
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
