"""Test HYP-0017: a causal intraday Hurst-exponent regime filter on trades.

The Noise-Area + VWAP entry is a momentum BREAKOUT; the thesis is that a breakout
continues in a PERSISTENT/trending tape (Hurst H > 0.5) and fails in a chop /
mean-reverting tape (H < 0.5). We gate entries on a causal, session-to-date Hurst
estimate and sweep the threshold to trace Sharpe and expected net-R-per-trade vs
the filter (the requested sensitivity). We test the LEVEL H, the 1st derivative
dH (ROC of H along the within-session decision clock), and the 2nd derivative d2H.

Estimator: generalized Hurst exponent of order 1 (structure function
    E|X(t+tau) - X(t)| ~ tau^H,  H = log-log slope over tau in LAGS capped at n/2),
computed on the session-to-date log-close path X (mfo 0 .. this decision bar),
anchored at the same session open the noise band is built from. Strictly causal:
X uses only closes at or before the decision bar; the fill is still next-open.
Derivatives run ALONG the within-session decision sequence (dH = H_k - H_{k-1},
d2H = dH_k - dH_{k-1}; NaN until enough same-day decisions exist).

Filter = a per-signal ENTRY GATE (rule 18: stateful engine rerun via `entry_gate`,
NOT a post-hoc trade drop, because removing an entry can change a later flip). For
signal S in {H, dH, d2H}, threshold T and direction, the engine may open only at
decision keys with S>=T ("high") or S<=T ("low").

Baseline frozen: continuous-stop NQ baseline (noise_bands lb90, RTH, 30-min clock,
VWAP gate, every-bar band/VWAP stop, next-open fills, per-instrument costs).

Primary metric = full-sample zero-trade-day daily net-ATR-R Sharpe uplift over
baseline at the family-best (signal, direction, threshold) cell, net R co-primary.
Per the standing rule the paired Null-C runs ONLY if the family-best clears
dSharpe>=+0.10 AND net R>=baseline; the matched-count random-signal-drop null is
cheap and always run on the family-best as the rarity-filter discriminator.

Examples:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0017_hurst_filter real NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0017_hurst_filter real ES
  python -u -m futures.nq.noise_vwap.scripts.hyp_0017_hurst_filter null NQ 30
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import engine2_nb as NB
from ..core import session as S
from .studies import _null_c_frame
from .wfo import candidate_signals
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, common_dates, round_trip_cost_points,
    LOOKBACK, PERIOD, UPLIFT_GATE,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0026"

LAGS = np.array([1, 2, 3, 4, 5, 7, 10, 15, 20])
H_GRID = np.array([0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65])
DERIV_Q = np.array([0.15, 0.30, 0.45, 0.60, 0.75, 0.90])   # quantile-based thresholds
RAND_DRAWS = 200
RAND_SEED0 = 26000
NULLC_SEED0 = 26500


# --------------------------------------------------------------------------- #
# Hurst features (causal, session-to-date)
# --------------------------------------------------------------------------- #
def ghe1(logp: np.ndarray) -> float:
    """Generalized Hurst exponent, order 1, of a log-price path."""
    n = len(logp)
    lags = LAGS[LAGS <= n // 2]
    if len(lags) < 3:
        return np.nan
    xs, ys = [], []
    for tau in lags:
        d = np.abs(logp[tau:] - logp[:-tau])
        m = d.mean()
        if m > 0:
            xs.append(np.log(tau))
            ys.append(np.log(m))
    if len(xs) < 3:
        return np.nan
    return float(np.polyfit(xs, ys, 1)[0])


def hurst_features(bars: pd.DataFrame, dm) -> pd.DataFrame:
    """Per (date, decision-mfo): causal H, dH (ROC), d2H. Cached to parquet."""
    dmset = {int(m) for m in dm}
    rows = []
    for sd, g in bars.groupby("sdate", sort=False):
        g = g.sort_values("mfo")
        mfo = g["mfo"].to_numpy()
        logp = np.log(g["close"].to_numpy(float))
        prevH = prevdH = np.nan
        for i in range(len(mfo)):
            if int(mfo[i]) not in dmset:
                continue
            H = ghe1(logp[: i + 1])
            dH = (H - prevH) if (np.isfinite(H) and np.isfinite(prevH)) else np.nan
            d2H = (dH - prevdH) if (np.isfinite(dH) and np.isfinite(prevdH)) else np.nan
            rows.append((sd, int(mfo[i]), H, dH, d2H))
            prevH, prevdH = H, dH
    return pd.DataFrame(rows, columns=["date", "mfo", "H", "dH", "d2H"])


def load_features(inst: str, bars: pd.DataFrame, dm, cache: bool = True) -> pd.DataFrame:
    fp = OUT / f"hurst_features_{inst}.parquet"
    if cache and fp.exists():
        return pd.read_parquet(fp)
    feats = hurst_features(bars, dm)
    OUT.mkdir(parents=True, exist_ok=True)
    if cache:
        feats.to_parquet(fp)
    return feats


# --------------------------------------------------------------------------- #
# engine helpers
# --------------------------------------------------------------------------- #
def run_gated(bars, bands, dm, gate):
    return NB.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                  exit_check="every_bar", entry_gate=gate)


def assert_parity(bars, bands, dm) -> None:
    a = NB.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
               exit_check="every_bar")
    b = E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
              exit_check="every_bar")
    assert len(a) == len(b), (len(a), len(b))
    assert abs(a["points"].sum() - b["points"].sum()) < 1e-6, "nb vs engine2 mismatch"


def gate_from(feats: pd.DataFrame, sig: str, thr: float, direction: str) -> set:
    sub = feats[feats[sig] >= thr] if direction == "high" else feats[feats[sig] <= thr]
    return set(zip(sub["date"], sub["mfo"].astype(int)))


def exp_r(sc: Score) -> float:
    return sc.net_r / sc.trades if sc.trades else np.nan


# --------------------------------------------------------------------------- #
# sensitivity sweep
# --------------------------------------------------------------------------- #
def thresholds(feats: pd.DataFrame, sig: str) -> np.ndarray:
    if sig == "H":
        return H_GRID
    vals = feats[sig].dropna().to_numpy()
    q = np.quantile(vals, DERIV_Q)
    return np.unique(np.round(np.concatenate([q, [0.0]]), 6))


def sweep(inst, bars, bands, dm, dates, feats, base: Score,
          sig: str, direction: str) -> pd.DataFrame:
    rt = round_trip_cost_points(inst)
    rows = []
    for thr in thresholds(feats, sig):
        gate = gate_from(feats, sig, thr, direction)
        sc = run_and_score(bars, bands, dm, dates, inst, gate, f"{sig}{direction}{thr:.3f}")
        rows.append({
            "sig": sig, "dir": direction, "thr": float(thr),
            "n": sc.trades, "retain": sc.trades / base.trades if base.trades else np.nan,
            "gross_pt_per_trade": sc.net_pt_per_trade + rt,  # net_pt/t = mean(pts)-rt
            "exp_netR_per_trade": exp_r(sc),
            "sumR": sc.net_r, "sharpe": sc.sharpe,
            "d_sharpe": sc.sharpe - base.sharpe, "d_sumR": sc.net_r - base.net_r,
            "recent_sharpe": sc.recent_sharpe, "max_dd": sc.max_dd,
        })
    return pd.DataFrame(rows)


def run_and_score(bars, bands, dm, dates, inst, gate, name) -> Score:
    tr = run_gated(bars, bands, dm, gate)
    return score_candidate(tr, bars, dates, inst, name)


# --------------------------------------------------------------------------- #
# matched-count random-signal-drop null (rarity-filter discriminator)
# --------------------------------------------------------------------------- #
def matched_count_null(bars, bands, dm, dates, inst, feats, base: Score,
                       best_row: pd.Series, ndraw: int = RAND_DRAWS) -> pd.DataFrame:
    """Keep the SAME number of CANDIDATE breakout signals at random (from the pool
    where the best cell's signal is defined) and rerun. If random equal-count
    keeping lifts Sharpe/net R as much as the Hurst gate, the gate is a
    rarity/variance filter, not information."""
    sig = best_row["sig"]
    cand = candidate_signals(bars, bands, dm)
    cand_keys = list(zip(cand["date"], cand["signal_mfo"].astype(int)))
    # restrict the pool to candidates whose signal is DEFINED (fair for dH/d2H)
    defined = set(zip(feats.loc[feats[sig].notna(), "date"],
                      feats.loc[feats[sig].notna(), "mfo"].astype(int)))
    pool = [k for k in cand_keys if k in defined]
    # K = number of candidate breakouts the best gate keeps
    gate = gate_from(feats, sig, best_row["thr"], best_row["dir"])
    K = sum(1 for k in pool if k in gate)
    rows = []
    rng = np.random.default_rng(RAND_SEED0)
    idx = np.arange(len(pool))
    for i in range(ndraw):
        pick = rng.choice(idx, size=K, replace=False)
        gate_r = {pool[j] for j in pick}
        sc = run_and_score(bars, bands, dm, dates, inst, gate_r, f"rand{i}")
        rows.append({"draw": i + 1, "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  matched-count random null {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows), K, len(pool)


# --------------------------------------------------------------------------- #
# paired drift-preserving Null-C (only if the real gate passes)
# --------------------------------------------------------------------------- #
def nullc(inst, best_row: pd.Series, ndraw: int) -> pd.DataFrame:
    rows = []
    for i in range(ndraw):
        nb = _null_c_frame(S.load_session(inst, "RTH"), seed=NULLC_SEED0 + i)
        bands = S.noise_bands(nb, LOOKBACK)
        dm = S.decision_mfos(PERIOD, int(nb["mfo"].max()))
        dates = common_dates(nb)
        feats = hurst_features(nb, dm)
        base = score_candidate(run_gated(nb, bands, dm, None), nb, dates, inst, "nbase")
        gate = gate_from(feats, best_row["sig"], best_row["thr"], best_row["dir"])
        sc = score_candidate(run_gated(nb, bands, dm, gate), nb, dates, inst, "ntreat")
        rows.append({"draw": i + 1, "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  Null-C draw {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def fmt_sweep(df: pd.DataFrame) -> str:
    cols = ["thr", "n", "retain", "gross_pt_per_trade", "exp_netR_per_trade",
            "sumR", "sharpe", "d_sharpe", "d_sumR", "recent_sharpe"]
    return df[cols].to_string(index=False, float_format=lambda v: f"{v:.4f}")


def real(inst: str, run_null: bool = False, ndraw: int = 30) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    assert_parity(bars, bands, dm)
    feats = load_features(inst, bars, dm)

    base = score_candidate(run_gated(bars, bands, dm, None), bars, dates, inst, "baseline")
    print(f"\n=== HYP-0017 Hurst filter — {inst} ===")
    print(f"baseline: trades={base.trades} Sharpe={base.sharpe:.4f} "
          f"netR={base.net_r:.2f} expR/trade={exp_r(base):+.4f} "
          f"grossPt/trade={base.net_pt_per_trade + round_trip_cost_points(inst):+.4f}")
    # Hurst distribution sanity
    print(f"Hurst H: mean={feats['H'].mean():.3f} median={feats['H'].median():.3f} "
          f"p10={feats['H'].quantile(0.1):.3f} p90={feats['H'].quantile(0.9):.3f} "
          f"frac>0.5={np.mean(feats['H'] > 0.5):.3f}  (n_dec={len(feats)})")

    sweeps = []
    for sig in ("H", "dH", "d2H"):
        for direction in ("high", "low"):
            sw = sweep(inst, bars, bands, dm, dates, feats, base, sig, direction)
            sweeps.append(sw)
            print(f"\n--- signal={sig} direction={direction} "
                  f"(keep {'>=' if direction == 'high' else '<='} thr) ---")
            print(fmt_sweep(sw))
    allsw = pd.concat(sweeps, ignore_index=True)
    allsw.to_csv(OUT / f"sweep_{inst}.csv", index=False)

    # family-best by dSharpe among cells that actually filter (retain < ~0.999)
    cand = allsw[allsw["retain"] < 0.999]
    best = cand.loc[cand["d_sharpe"].idxmax()] if len(cand) else allsw.iloc[0]
    print(f"\nFAMILY-BEST (max dSharpe among filtering cells): sig={best['sig']} "
          f"dir={best['dir']} thr={best['thr']:.4f} retain={best['retain']:.3f} "
          f"dSharpe={best['d_sharpe']:+.4f} dSumR={best['d_sumR']:+.2f} "
          f"grossPt/trade={best['gross_pt_per_trade']:+.4f} (base "
          f"{base.net_pt_per_trade + round_trip_cost_points(inst):+.4f})")
    real_gate = bool(best["d_sharpe"] >= UPLIFT_GATE and best["sumR"] >= base.net_r)
    print(f"REAL GATE (dSharpe>=+{UPLIFT_GATE:.2f} AND netR>=base): "
          f"{'PASS' if real_gate else 'REJECT'}")

    # matched-count random-signal-drop null (always run on the family-best)
    rnd, K, pooln = matched_count_null(bars, bands, dm, dates, inst, feats, base, best)
    rnd.to_csv(OUT / f"random_null_{inst}.csv", index=False)
    p_sh = float((rnd["d_sharpe"] >= best["d_sharpe"]).mean())
    p_r = float((rnd["d_sumR"] >= best["d_sumR"]).mean())
    print(f"\nmatched-count random-signal-drop null (keep {K} of {pooln} candidates, "
          f"{len(rnd)} draws):")
    print(f"  real  dSharpe={best['d_sharpe']:+.4f}  dSumR={best['d_sumR']:+.2f}")
    print(f"  rand  dSharpe mean={rnd['d_sharpe'].mean():+.4f} sd={rnd['d_sharpe'].std(ddof=1):.4f}  "
          f"dSumR mean={rnd['d_sumR'].mean():+.2f}")
    print(f"  frac(rand>=real): Sharpe={p_sh:.3f}  sumR={p_r:.3f}  "
          f"(<0.05 = real beats a random equal-count drop)")

    verdict = {
        "inst": inst, "base_sharpe": base.sharpe, "base_netR": base.net_r,
        "base_trades": base.trades, "base_expR": exp_r(base),
        "best": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                 for k, v in best.to_dict().items()},
        "real_gate_passed": real_gate,
        "rand_frac_ge_real_sharpe": p_sh, "rand_frac_ge_real_sumR": p_r,
        "rand_dSharpe_mean": float(rnd["d_sharpe"].mean()),
        "rand_dSumR_mean": float(rnd["d_sumR"].mean()),
        "matched_K": int(K), "cand_pool": int(pooln),
    }

    if run_null and real_gate:
        nc = nullc(inst, best, ndraw)
        nc.to_csv(OUT / f"nullc_{inst}.csv", index=False)
        z = ((best["d_sumR"] - nc["d_sumR"].mean()) / nc["d_sumR"].std(ddof=1)
             if nc["d_sumR"].std(ddof=1) > 0 else np.nan)
        p = float((nc["d_sumR"] >= best["d_sumR"]).mean())
        verdict.update(nullc_z=float(z), nullc_frac_ge_real=p,
                       nullc_dSumR_mean=float(nc["d_sumR"].mean()))
        print(f"\nNull-C dSumR mean={nc['d_sumR'].mean():+.2f} z={z:+.2f} "
              f"frac(null>=real)={p:.3f}")
    elif run_null:
        print("\nReal gate did not pass -> Null-C skipped (standing rule).")

    (OUT / f"verdict_{inst}.json").write_text(json.dumps(verdict, indent=2) + "\n")
    print(f"\nartifacts -> {OUT}")
    return verdict


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    inst = sys.argv[2] if len(sys.argv) > 2 else "NQ"
    ndraw = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    real(inst, run_null=(mode == "null"), ndraw=ndraw)


if __name__ == "__main__":
    main()
