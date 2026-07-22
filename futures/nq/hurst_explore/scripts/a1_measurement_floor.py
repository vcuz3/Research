"""A1 -- the measurement-error floor of an intraday Hurst estimate.

Question: is an *intraday* Hurst number a well-determined quantity, or is it
mostly estimator/sample noise?  Before any predictive use of H we need its
standard error as a function of window length, sampling frequency, and
estimator, plus how much four standard estimators disagree on the same real
window.

Three parts, all measurement (nothing trades):

  PART A -- synthetic floor.  For fBm of known H, many draws at each window
    length n and estimator -> bias(Hhat) and std(Hhat).  n spans the intraday
    windows actually available: the 1m session-to-date decision points
    (n ~ 30..390 bars) and the 1s equivalents (n ~ 900..23400 bars).  std(Hhat)
    IS the floor: no real-data H claim can be sharper than this.

  PART B -- real cross-estimator agreement (NQ 1m/1s, ES 1m).  On real
    whole-session paths, the spread across {ghe1,ghe2,rs,dfa} at a matched lag
    range.  If real spread >> the synthetic floor at that n, the estimators are
    seeing genuinely different structure (multi-scale / bias), not just noise.

  PART C -- 1s vs 1m on the SAME NQ sessions.  Whole-day H at 1s (full lag
    range, reaching sub-minute) vs 1m, and 1s restricted to minute+ lags.  If
    the minute-matched 1s agrees with 1m but full-range 1s does not, the extra
    1s information lives at sub-minute scales -> motivates A2.

Usage:
  python -u -m futures.nq.hurst_explore.scripts.a1_measurement_floor
  python -u -m futures.nq.hurst_explore.scripts.a1_measurement_floor --quick
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

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0003"
EST = ["ghe1", "ghe2", "rs", "dfa"]
FILL_MIN = 0.90
ERA_MIN = 2015

# window lengths (in bars) matching real intraday availability
N_1M = [30, 45, 60, 90, 120, 195, 390]          # 1m session-to-date bars
N_1S = [900, 1800, 5400, 11700, 23400]          # 1s session-to-date bars
H_TRUE = [0.40, 0.50, 0.60]


def _lags_for(n: int) -> np.ndarray:
    return H.log_lags(2, max(4, n // 2), 14)


# --------------------------------------------------------------------------- #
# PART A: synthetic floor
# --------------------------------------------------------------------------- #
def synthetic_floor(draws: int, seed: int = 1000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for n in N_1M + N_1S:
        lags = _lags_for(n)
        for h_true in H_TRUE:
            acc = {k: [] for k in EST}
            for _ in range(draws):
                p = H.fbm(h_true, n, rng)
                pan = H.estimate_panel(p, lags)
                for k in EST:
                    acc[k].append(pan[k])
            for k in EST:
                v = np.array(acc[k], float)
                rows.append({
                    "n_bars": n, "H_true": h_true, "estimator": k,
                    "bias": float(np.nanmean(v) - h_true),
                    "std": float(np.nanstd(v)),
                    "mean": float(np.nanmean(v)),
                })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# PART B/C: real data
# --------------------------------------------------------------------------- #
def real_1m(inst: str, dates: set | None = None) -> pd.DataFrame:
    lags = H.log_lags(2, 195, 14)          # 2..195 minutes
    rows = []
    for sd, logp, mfo in L.sessions_1m(inst):
        if dates is not None and pd.Timestamp(sd) not in dates:
            continue
        pan = H.estimate_panel(logp, lags)
        pan.update({"sdate": sd, "inst": inst, "freq": "1m", "n": len(logp)})
        rows.append(pan)
    return pd.DataFrame(rows)


def real_1s_nq(sample_dates: np.ndarray) -> pd.DataFrame:
    lags_full = H.log_lags(2, 4000, 18)    # 2s .. ~66min
    lags_min = H.log_lags(60, 4000, 12)    # 60s+ (minute-matched)
    rows = []
    for sd, sec, close, vol in L.iter_1s_rth(sample_dates):
        if pd.Timestamp(sd).year < ERA_MIN:
            continue
        logp, real, fr = L.grid_1s(sec, close)
        if fr < FILL_MIN:
            continue
        r = np.diff(logp)
        row = {
            "sdate": sd, "inst": "NQ", "freq": "1s", "n": len(logp),
            "fill_rate": fr,
            "ghe1": H.ghe(logp, lags_full, 1.0),
            "ghe2": H.ghe(logp, lags_full, 2.0),
            "rs": H.rs_hurst(r, lags_full),
            "dfa": H.dfa_hurst(r, lags_full),
            "ghe1_min": H.ghe(logp, lags_min, 1.0),   # minute-matched
        }
        rows.append(row)
    return pd.DataFrame(rows)


def stratified_sample(dates: np.ndarray, per_year: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    d = pd.DatetimeIndex(dates)
    out = []
    for yr, idx in pd.Series(range(len(d)), index=d.year).groupby(level=0):
        picks = idx.to_numpy()
        take = min(per_year, len(picks))
        out.append(rng.choice(picks, take, replace=False))
    sel = np.sort(np.concatenate(out))
    return dates[sel]


def spread(df: pd.DataFrame) -> dict:
    """Cross-estimator mean-abs deviation from the row mean, per session."""
    M = df[EST].to_numpy(float)
    rowmean = np.nanmean(M, axis=1, keepdims=True)
    mad = np.nanmean(np.abs(M - rowmean), axis=1)
    return {"cross_est_mad_mean": float(np.nanmean(mad)),
            "cross_est_mad_median": float(np.nanmedian(mad))}


def dist(df: pd.DataFrame, col: str) -> dict:
    v = df[col].dropna().to_numpy()
    return {"mean": float(v.mean()), "std": float(v.std()),
            "p10": float(np.quantile(v, .1)), "p50": float(np.quantile(v, .5)),
            "p90": float(np.quantile(v, .9)), "n": int(len(v))}


def bias_calibrated_level(observed: float, floor: pd.DataFrame,
                          n_bars: int, estimator: str) -> float:
    """Invert the estimator's synthetic mean-vs-truth calibration curve.

    This is preferable to narratively subtracting the H=0.5 bias: finite-sample
    bias changes with the unknown true H.  Linear interpolation is deliberately
    restricted to the simulated H range and returns NaN outside it.
    """
    tab = floor[(floor["n_bars"] == n_bars) &
                (floor["estimator"] == estimator)].sort_values("mean")
    x = tab["mean"].to_numpy(float)
    y = tab["H_true"].to_numpy(float)
    if len(x) < 2 or observed < x.min() or observed > x.max():
        return np.nan
    return float(np.interp(observed, x, y))


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    draws = 40 if args.quick else 200
    per_year = 6 if args.quick else 20
    t0 = time.time()

    # PART A
    floor = synthetic_floor(draws)
    floor.to_csv(OUT / "synthetic_floor.csv", index=False)

    # PART B/C real
    nq1m = real_1m("NQ")
    es1m = real_1m("ES")
    nq1m.to_parquet(OUT / "real_1m_NQ.parquet")
    es1m.to_parquet(OUT / "real_1m_ES.parquet")

    dates1s = np.array([sd for sd, _, _ in L.sessions_1m("NQ")],
                       dtype="datetime64[ns]")
    sample = stratified_sample(dates1s, per_year)
    nq1s = real_1s_nq(sample)
    nq1s.to_parquet(OUT / "real_1s_NQ.parquet")
    matched_dates = set(pd.to_datetime(nq1s["sdate"]))
    nq1m_matched = real_1m("NQ", matched_dates)
    nq1m_matched.to_parquet(OUT / "real_1m_NQ_matched.parquet")

    dq_nq = L.data_quality_1m("NQ")
    dq_es = L.data_quality_1m("ES")
    pd.concat([dq_nq.assign(inst="NQ"), dq_es.assign(inst="ES")],
              ignore_index=True).to_csv(OUT / "data_quality_1m.csv", index=False)

    # ---- report ----
    lines = []
    P = lines.append
    P("=" * 78)
    P("A1  MEASUREMENT-ERROR FLOOR OF AN INTRADAY HURST ESTIMATE")
    P(f"draws={draws}  1s_sessions={len(nq1s)}  1m_sessions NQ={len(nq1m)} "
      f"ES={len(es1m)}  elapsed={time.time()-t0:.0f}s")
    P("=" * 78)

    P("\nPART A -- SYNTHETIC FLOOR  std(Hhat) [bias in brackets], H_true=0.50")
    P(f"{'n_bars':>7} | " + " ".join(f"{k:>16}" for k in EST))
    sub = floor[floor.H_true == 0.50]
    for n in N_1M + N_1S:
        cells = []
        for k in EST:
            r = sub[(sub.n_bars == n) & (sub.estimator == k)].iloc[0]
            cells.append(f"{r['std']:.3f}[{r['bias']:+.2f}]")
        P(f"{n:>7} | " + " ".join(f"{c:>16}" for c in cells))
    P("  (std is the irreducible sampling noise; an intraday H is only")
    P("   meaningful to +/- this at the given window length.)")

    P("\nPART B -- REAL WHOLE-SESSION H distribution (mean +/- std over sessions)")
    for name, df, cols in [("NQ 1m", nq1m, EST), ("ES 1m", es1m, EST),
                           ("NQ 1s (full lags)", nq1s, EST)]:
        P(f"  {name}:")
        for k in cols:
            d = dist(df, k)
            P(f"     {k:>5}: {d['mean']:.3f} +/- {d['std']:.3f}"
              f"   [p10 {d['p10']:.3f}  p50 {d['p50']:.3f}  p90 {d['p90']:.3f}]")
        sp = spread(df)
        P(f"     cross-estimator MAD: mean {sp['cross_est_mad_mean']:.3f} "
          f"median {sp['cross_est_mad_median']:.3f}")

    P("\nBIAS-CALIBRATED WHOLE-SESSION LEVELS")
    P("  (inverse interpolation through synthetic mean(H_true), n=390;")
    P("   NaN means the observation lies outside the simulated H range)")
    calibrated = {}
    for name, df in [("NQ", nq1m), ("ES", es1m)]:
        vals = {k: bias_calibrated_level(float(df[k].mean()), floor, 390, k)
                for k in EST}
        calibrated[name] = vals
        P(f"  {name}: " + "  ".join(f"{k}={v:.3f}" for k, v in vals.items()))

    P("\nPART C -- 1s vs 1m on NQ (matched-scale check)")
    dm = dist(nq1m_matched, "ghe1"); ds_full = dist(nq1s, "ghe1"); ds_min = dist(nq1s, "ghe1_min")
    P(f"  matched sessions      : {len(nq1m_matched)}")
    P(f"  ghe1 NQ 1m matched   : {dm['mean']:.3f} +/- {dm['std']:.3f}")
    P(f"  ghe1 NQ 1s full lags : {ds_full['mean']:.3f} +/- {ds_full['std']:.3f}")
    P(f"  ghe1 NQ 1s min+ lags : {ds_min['mean']:.3f} +/- {ds_min['std']:.3f}")
    P("  (if min+ 1s ~ 1m but full 1s differs, the extra 1s info is sub-minute")
    P("   -> the micro/meso split A2 measures.)")

    P("\nRule 9a DATA QUALITY (1s grid)")
    fr = nq1s["fill_rate"]
    P(f"  1s sessions sampled: {len(nq1s)}  fill_rate mean {fr.mean():.3f} "
      f"min {fr.min():.3f} p10 {np.quantile(fr,.1):.3f}")
    yr = pd.DatetimeIndex(nq1s["sdate"]).year
    P("  1s fill_rate by era (forward-fill injects artificial zero-returns; a")
    P("  low-fill session's SUB-MINUTE H is unreliable -> A2 must filter on this):")
    for lo, hi in [(2011, 2014), (2015, 2018), (2019, 2022), (2023, 2026)]:
        m = (yr >= lo) & (yr <= hi)
        if m.any():
            sub = fr[m]
            P(f"     {lo}-{hi}: sessions {int(m.sum()):3d}  fill mean "
              f"{sub.mean():.3f}  min {sub.min():.3f}")
    P(f"  1m NQ sessions {len(nq1m)}  ES {len(es1m)}  degraded days excluded: "
      f"{len(L.DEGRADED)}")
    for inst, dq in [("NQ", dq_nq), ("ES", dq_es)]:
        P(f"  {inst} incomplete 1m grids excluded: {(~dq.complete_grid).sum()} "
          f"of {len(dq)}; duplicates={dq.duplicate_slots.sum()} "
          f"missing_slots={dq.missing_slots.sum()} internal_gaps={dq.internal_gaps.sum()}")

    report = "\n".join(lines)
    (OUT / "a1_summary.txt").write_text(report, encoding="utf-8")
    meta = {"draws": draws, "per_year": per_year, "n_1s_sessions": int(len(nq1s)),
            "n_1m_NQ": int(len(nq1m)), "n_1m_ES": int(len(es1m)),
            "n_matched_sessions": int(len(nq1m_matched)),
            "fill_min": FILL_MIN, "era_min": ERA_MIN,
            "bias_calibrated_levels": calibrated,
            "elapsed_s": round(time.time() - t0, 1),
            "sample_first": str(pd.Timestamp(sample.min()).date()),
            "sample_last": str(pd.Timestamp(sample.max()).date())}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_manifest(
        OUT, "EXP-0003",
        "python -u -m futures.nq.hurst_explore.scripts.a1_measurement_floor",
        [Path(__file__), Path(H.__file__), Path(L.__file__)],
        [L.ONE_MIN["NQ"], L.ONE_MIN["ES"], L.ONE_SEC_NQ])
    print(report)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
