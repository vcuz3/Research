"""A2 -- the term structure of the Hurst exponent across TIMESCALE.

A single fixed-lag GHE returns one number that blends every scale.  Markets are
famously anti-persistent at the microstructure scale (bid-ask bounce, discrete
ticks) and can be diffusive-to-persistent at coarser scales.  A2 measures the
LOCAL structure-function exponent H(tau) as a function of lag tau, to answer:
is the intraday NQ tape one Hurst regime or a mixture of two?

Method (translation-invariant, stationary lags -- NOT anchored at the open):
  For each session, K_q(tau) = mean_t |logp[t+tau]-logp[t]|^q.  Average log K
  across sessions per tau (slope is intercept-invariant, so cross-session
  volatility differences do not bias the shape).  The centered local log-log
  slope of <log K_1> vs log tau is H(tau).

Frequencies:
  * NQ 1s  -> tau 1s..1h : the ONLY view that reaches sub-minute (micro band).
             Restricted to high-fill sessions (Rule 9a: forward-fill injects
             artificial zero-returns that deflate the tau=1-2s points).
  * NQ/ES 1m -> tau 1..190 min : meso band only, but on BOTH markets, and it
             OVERLAPS the 1s curve for tau in [1min,60min] -> a cross-frequency
             consistency check that the micro extension is real, not a 1s
             artifact.

Usage:
  python -u -m futures.nq.hurst_explore.scripts.a2_timescale
  python -u -m futures.nq.hurst_explore.scripts.a2_timescale --quick
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import hurst as H
from ..core import loaders as L
from ..core.provenance import write_manifest

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0004"

TAU_1S = H.log_lags(1, 3600, 36)          # 1 s .. 1 h
TAU_1M = H.log_lags(1, 190, 22)           # 1 min .. ~3.2 h
FILL_MIN = 0.90                           # micro band needs near-complete grid
ERA_MIN = 2015                            # skip the sparse early-2010s 1s tape


def _collect_logk(paths, taus):
    """Return dates and the per-session log K matrix used for inference."""
    dates, rows = [], []
    for sd, logp in paths:
        vals = np.full(len(taus), np.nan)
        for i, tau in enumerate(taus):
            if tau <= len(logp) - 1:
                m = np.abs(logp[tau:] - logp[:-tau]).mean()
                if m > 0:
                    vals[i] = np.log(m)
        dates.append(pd.Timestamp(sd))
        rows.append(vals)
    return pd.DatetimeIndex(dates), np.asarray(rows, float)


def _accumulate_logk(paths, taus):
    """Mean over sessions of log K_1(tau) for each tau.  `paths` yields log-close
    arrays.  Returns (mean_logk, n_used per tau)."""
    _, matrix = _collect_logk(((i, p) for i, p in enumerate(paths)), taus)
    c = np.isfinite(matrix).sum(axis=0)
    return np.nanmean(matrix, axis=0), c, len(matrix)


def _synthetic_rw_matrix(length, taus, draws, seed):
    """Matched H=0.5 random-walk control: the SAME H(tau) machinery on driftless
    random walks of the real path length.  Any coarse-scale droop here is a
    finite-sample structure-function SATURATION artifact (displacement is bounded
    as tau -> N), not genuine mean-reversion; the signal is real(tau)-control(tau).
    """
    rng = np.random.default_rng(seed)
    def gen():
        for _ in range(draws):
            yield _, np.concatenate([[0.0], np.cumsum(rng.standard_normal(length - 1))])
    _, matrix = _collect_logk(gen(), taus)
    return matrix


def _paths_1m(inst):
    for sd, logp, mfo in L.sessions_1m(inst):
        yield sd, logp


def _paths_1s(sample_dates):
    """High-fill, recent-era 1s log-close paths (Rule 9a filtered)."""
    for sd, sec, close, vol in L.iter_1s_rth(sample_dates):
        if pd.Timestamp(sd).year < ERA_MIN:
            continue
        logp, real, fr = L.grid_1s(sec, close)
        if fr >= FILL_MIN:
            yield sd, logp


def _moving_block_indices(n, block, rng):
    """Circular moving-block bootstrap indices preserving weekly dependence."""
    starts = rng.integers(0, n, size=int(np.ceil(n / block)))
    return np.concatenate([(s + np.arange(block)) % n for s in starts])[:n]


def corrected_band_bootstrap(real, ctrl, taus, lo, hi, reps=500,
                             block=5, seed=0):
    """Point estimate and 95% CI for 0.5 + H_real - H_RW.

    Real sessions use a moving-block bootstrap; independent RW paths are
    resampled iid.  The full real-minus-control operation is repeated each draw.
    """
    rng = np.random.default_rng(seed)
    point = 0.5 + band_H(taus, np.nanmean(real, axis=0), lo, hi) - \
        band_H(taus, np.nanmean(ctrl, axis=0), lo, hi)
    draws = np.empty(reps)
    for b in range(reps):
        ri = _moving_block_indices(len(real), block, rng)
        ci = rng.integers(0, len(ctrl), size=len(ctrl))
        draws[b] = 0.5 + band_H(taus, np.nanmean(real[ri], axis=0), lo, hi) - \
            band_H(taus, np.nanmean(ctrl[ci], axis=0), lo, hi)
    lo_ci, hi_ci = np.nanquantile(draws, [.025, .975])
    return point, float(lo_ci), float(hi_ci), float(np.nanstd(draws, ddof=1))


def band_H(taus, mean_logk, lo, hi):
    """Global log-log slope of K over the lag sub-band [lo,hi] (in tau units)."""
    m = (taus >= lo) & (taus <= hi) & np.isfinite(mean_logk)
    if m.sum() < 3:
        return np.nan
    return float(np.polyfit(np.log(taus[m]), mean_logk[m], 1)[0])


def stratified_sample(dates, per_year, seed=11):
    rng = np.random.default_rng(seed)
    d = pd.DatetimeIndex(dates)
    out = []
    for yr, idx in pd.Series(range(len(d)), index=d.year).groupby(level=0):
        if yr < ERA_MIN:
            continue
        picks = idx.to_numpy()
        out.append(rng.choice(picks, min(per_year, len(picks)), replace=False))
    return dates[np.sort(np.concatenate(out))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    per_year = 8 if args.quick else 30
    t0 = time.time()

    # 1m both markets (full history)
    dates_nq1m, mat_nq1m = _collect_logk(_paths_1m("NQ"), TAU_1M)
    dates_es1m, mat_es1m = _collect_logk(_paths_1m("ES"), TAU_1M)
    lk_nq1m, c_nq1m, ns_nq1m = np.nanmean(mat_nq1m, 0), np.isfinite(mat_nq1m).sum(0), len(mat_nq1m)
    lk_es1m, c_es1m, ns_es1m = np.nanmean(mat_es1m, 0), np.isfinite(mat_es1m).sum(0), len(mat_es1m)

    # 1s NQ (high-fill sample)
    dates1s = np.array([sd for sd, _, _ in L.sessions_1m("NQ")], dtype="datetime64[ns]")
    sample = stratified_sample(dates1s, per_year)
    dates_nq1s, mat_nq1s = _collect_logk(_paths_1s(sample), TAU_1S)
    lk_nq1s, c_nq1s, ns_nq1s = np.nanmean(mat_nq1s, 0), np.isfinite(mat_nq1s).sum(0), len(mat_nq1s)

    # matched synthetic random-walk controls (saturation artifact reference)
    ctrl_draws = 60 if args.quick else 300
    mat_ctrl_1s = _synthetic_rw_matrix(23400, TAU_1S, ctrl_draws, seed=202)
    mat_ctrl_1m = _synthetic_rw_matrix(390, TAU_1M, ctrl_draws, seed=203)
    lk_ctrl_1s = np.nanmean(mat_ctrl_1s, axis=0)
    lk_ctrl_1m = np.nanmean(mat_ctrl_1m, axis=0)

    # local H(tau) curves (real and control)
    H_nq1s = H.local_slope(np.log(TAU_1S), lk_nq1s, win=2)
    H_nq1m = H.local_slope(np.log(TAU_1M), lk_nq1m, win=2)
    H_es1m = H.local_slope(np.log(TAU_1M), lk_es1m, win=2)
    H_ctrl1s = H.local_slope(np.log(TAU_1S), lk_ctrl_1s, win=2)
    H_ctrl1m = H.local_slope(np.log(TAU_1M), lk_ctrl_1m, win=2)

    # persist curves
    def frame(freq, inst, taus, lk, hl, c):
        return pd.DataFrame({"freq": freq, "inst": inst, "tau_sec":
                             taus * (1 if freq == "1s" else 60),
                             "tau_bars": taus, "mean_logk": lk,
                             "H_local": hl, "n_sess_used": c})
    curves = pd.concat([
        frame("1s", "NQ", TAU_1S, lk_nq1s, H_nq1s, c_nq1s),
        frame("1m", "NQ", TAU_1M, lk_nq1m, H_nq1m, c_nq1m),
        frame("1m", "ES", TAU_1M, lk_es1m, H_es1m, c_es1m),
        frame("1s", "RW_ctrl", TAU_1S, lk_ctrl_1s, H_ctrl1s, np.zeros(len(TAU_1S), int)),
        frame("1m", "RW_ctrl", TAU_1M, lk_ctrl_1m, H_ctrl1m, np.zeros(len(TAU_1M), int)),
    ], ignore_index=True)
    curves.to_csv(OUT / "scale_curve.csv", index=False)

    # band summaries; corrected = real - control (control's own deviation from
    # 0.5 IS the saturation artifact at that band/length)
    def cb(taus, lk, ctrl, lo, hi):
        return band_H(taus, lk, lo, hi), band_H(taus, ctrl, lo, hi)
    bands = {
        "NQ 1s micro   tau 1-8s":   cb(TAU_1S, lk_nq1s, lk_ctrl_1s, 1, 8),
        "NQ 1s sub-min tau 8-45s":  cb(TAU_1S, lk_nq1s, lk_ctrl_1s, 8, 45),
        "NQ 1s meso    tau 2-30m":  cb(TAU_1S, lk_nq1s, lk_ctrl_1s, 120, 1800),
        "NQ 1m meso    tau 2-30m":  cb(TAU_1M, lk_nq1m, lk_ctrl_1m, 2, 30),
        "ES 1m meso    tau 2-30m":  cb(TAU_1M, lk_es1m, lk_ctrl_1m, 2, 30),
        "NQ 1m coarse  tau 30-180m": cb(TAU_1M, lk_nq1m, lk_ctrl_1m, 30, 180),
        "ES 1m coarse  tau 30-180m": cb(TAU_1M, lk_es1m, lk_ctrl_1m, 30, 180),
    }

    # Repeat the complete real-minus-control operation under resampling.
    reps = 200 if args.quick else 1000
    band_inputs = {
        "NQ 1s micro   tau 1-8s": (TAU_1S, mat_nq1s, mat_ctrl_1s, 1, 8),
        "NQ 1s sub-min tau 8-45s": (TAU_1S, mat_nq1s, mat_ctrl_1s, 8, 45),
        "NQ 1s meso    tau 2-30m": (TAU_1S, mat_nq1s, mat_ctrl_1s, 120, 1800),
        "NQ 1m meso    tau 2-30m": (TAU_1M, mat_nq1m, mat_ctrl_1m, 2, 30),
        "ES 1m meso    tau 2-30m": (TAU_1M, mat_es1m, mat_ctrl_1m, 2, 30),
        "NQ 1m coarse  tau 30-180m": (TAU_1M, mat_nq1m, mat_ctrl_1m, 30, 180),
        "ES 1m coarse  tau 30-180m": (TAU_1M, mat_es1m, mat_ctrl_1m, 30, 180),
    }
    uncertainty = []
    for seed, (name, (taus, real, ctrl, lo, hi)) in enumerate(band_inputs.items(), 700):
        point, ci_lo, ci_hi, se = corrected_band_bootstrap(
            real, ctrl, taus, lo, hi, reps=reps, seed=seed)
        uncertainty.append({"band": name, "lo": lo, "hi": hi, "corrected": point,
                            "ci_2.5": ci_lo, "ci_97.5": ci_hi, "bootstrap_se": se,
                            "reps": reps, "block_sessions": 5})
    uncertainty = pd.DataFrame(uncertainty)
    uncertainty.to_csv(OUT / "band_uncertainty.csv", index=False)

    # Endpoint sensitivity for the load-bearing coarse-scale claim.
    sensitivity = []
    for inst, real in [("NQ", mat_nq1m), ("ES", mat_es1m)]:
        for lo, hi in [(20, 150), (30, 150), (30, 180), (45, 180)]:
            point, ci_lo, ci_hi, se = corrected_band_bootstrap(
                real, mat_ctrl_1m, TAU_1M, lo, hi, reps=reps, seed=900 + lo + hi)
            sensitivity.append({"inst": inst, "lo_min": lo, "hi_min": hi,
                                "corrected": point, "ci_2.5": ci_lo,
                                "ci_97.5": ci_hi, "bootstrap_se": se})
    sensitivity = pd.DataFrame(sensitivity)
    sensitivity.to_csv(OUT / "coarse_band_sensitivity.csv", index=False)

    era_rows = []
    for inst, dates, real in [("NQ", dates_nq1m, mat_nq1m),
                              ("ES", dates_es1m, mat_es1m)]:
        years = dates.year.to_numpy()
        for era_lo, era_hi in [(2011, 2014), (2015, 2018),
                               (2019, 2022), (2023, 2026)]:
            mask = (years >= era_lo) & (years <= era_hi)
            if mask.sum() < 20:
                continue
            point, ci_lo, ci_hi, se = corrected_band_bootstrap(
                real[mask], mat_ctrl_1m, TAU_1M, 30, 180, reps=reps,
                seed=1200 + era_lo)
            era_rows.append({"inst": inst, "era": f"{era_lo}-{era_hi}",
                             "n_sessions": int(mask.sum()), "corrected": point,
                             "ci_2.5": ci_lo, "ci_97.5": ci_hi,
                             "bootstrap_se": se})
    era_stability = pd.DataFrame(era_rows)
    era_stability.to_csv(OUT / "coarse_era_stability.csv", index=False)

    lines = []
    P = lines.append
    P("=" * 78)
    P("A2  HURST TERM STRUCTURE ACROSS TIMESCALE  H(tau)")
    P(f"1s sessions used (fill>={FILL_MIN}, era>={ERA_MIN}): {ns_nq1s}   "
      f"1m sessions NQ={ns_nq1m} ES={ns_es1m}   elapsed={time.time()-t0:.0f}s")
    P("=" * 78)

    P("\nBAND HURST  raw H  |  RW-control H  |  corrected (real-control, vs 0.5)")
    for k, (raw, ctrl) in bands.items():
        corr = 0.5 + (raw - ctrl) if (np.isfinite(raw) and np.isfinite(ctrl)) else np.nan
        u = uncertainty[uncertainty.band == k].iloc[0]
        P(f"  {k:>27}:  {raw:.3f}  |  {ctrl:.3f}  |  {corr:.3f} "
          f"[95% CI {u['ci_2.5']:.3f},{u['ci_97.5']:.3f}]")
    P("  (control near 0.5 => band is artifact-free and raw H is trustworthy;")
    P("   control below 0.5 => that band's raw anti-persistence is saturation.)")

    P("\nH(tau) CURVE  (local slope; tau in seconds; ctrl = matched RW)")
    P(f"  {'tau_s':>7} {'NQ_1s':>8} {'NQ_1m':>8} {'ES_1m':>8} {'ctrl':>7}  n1s")
    # merge onto a common tau_sec axis for display
    disp_taus = sorted(set(list(TAU_1S) + list(TAU_1M * 60)))
    hs = dict(zip(TAU_1S, H_nq1s))
    hnm = dict(zip(TAU_1M * 60, H_nq1m))
    hem = dict(zip(TAU_1M * 60, H_es1m))
    ct1s = dict(zip(TAU_1S, H_ctrl1s))
    ct1m = dict(zip(TAU_1M * 60, H_ctrl1m))
    cs = dict(zip(TAU_1S, c_nq1s))
    for ts in disp_taus:
        if ts > 3600:
            continue
        a = f"{hs[ts]:.3f}" if ts in hs and np.isfinite(hs[ts]) else "  .  "
        b = f"{hnm[ts]:.3f}" if ts in hnm and np.isfinite(hnm[ts]) else "  .  "
        c = f"{hem[ts]:.3f}" if ts in hem and np.isfinite(hem[ts]) else "  .  "
        ct = ct1s.get(ts) if ts in ct1s else ct1m.get(ts)
        ctx = f"{ct:.3f}" if ct is not None and np.isfinite(ct) else "  .  "
        nn = cs.get(ts, "")
        P(f"  {ts:>7} {a:>8} {b:>8} {c:>8} {ctx:>7}  {nn}")

    P("\nREAD (corrected = 0.5 + raw - RW_control):")
    def corr(key):
        raw, ct = bands[key]
        return 0.5 + (raw - ct)
    micro = corr("NQ 1s micro   tau 1-8s")
    meso1s = corr("NQ 1s meso    tau 2-30m")
    meso1m = corr("NQ 1m meso    tau 2-30m")
    coarse = corr("NQ 1m coarse  tau 30-180m")
    coarse_es = corr("ES 1m coarse  tau 30-180m")
    def tag(h):
        return "ANTI-persistent" if h < 0.47 else ("~random-walk" if h < 0.53 else "persistent")
    P(f"  micro  (1-8s)   H={micro:.3f}  {tag(micro)}  [1s OHLCV cannot resolve")
    P("                  sub-1s bid-ask bounce; true-tick data needed for that]")
    P(f"  meso   (2-30m)  H(1s)={meso1s:.3f}  H(1m)={meso1m:.3f}  {tag(meso1m)}  "
      f"cross-freq gap {abs(meso1s-meso1m):.3f}")
    P(f"  coarse (30-180m) NQ={coarse:.3f}  ES={coarse_es:.3f}  {tag(coarse)}")
    P("  Shape: H(tau) DECLINES with scale (RW at seconds -> anti-persistent at")
    P("  tens-of-minutes), transfers NQ<->ES.  This STATIONARY-lag mean-reversion")
    P("  is a DIFFERENT object from the anchored-at-open morning super-diffusion")
    P("  (the cone learning): that is time-of-day dispersion growth (A3), this is")
    P("  translation-invariant lag persistence averaged over the whole day.")

    report = "\n".join(lines)
    (OUT / "a2_summary.txt").write_text(report, encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps({
        "per_year": per_year, "n_1s_sessions": int(ns_nq1s),
        "n_1m_NQ": int(ns_nq1m), "n_1m_ES": int(ns_es1m),
        "fill_min": FILL_MIN, "era_min": ERA_MIN,
        "bootstrap_reps": reps, "bootstrap_block_sessions": 5,
        "elapsed_s": round(time.time() - t0, 1),
        "bands": {k: {"raw": None if not np.isfinite(raw) else round(raw, 4),
                      "rw_control": None if not np.isfinite(ct) else round(ct, 4),
                      "corrected": None if not (np.isfinite(raw) and np.isfinite(ct))
                      else round(0.5 + raw - ct, 4)}
                  for k, (raw, ct) in bands.items()}}, indent=2), encoding="utf-8")
    write_manifest(
        OUT, "EXP-0004",
        "python -u -m futures.nq.hurst_explore.scripts.a2_timescale",
        [Path(__file__), Path(H.__file__), Path(L.__file__)],
        [L.ONE_MIN["NQ"], L.ONE_MIN["ES"], L.ONE_SEC_NQ])
    print(report)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
