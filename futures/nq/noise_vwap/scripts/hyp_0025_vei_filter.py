"""Test HYP-0025: a causal Volatility-Expansion-Index (VEI) entry gate on the
Noise-Area + VWAP momentum baseline.

VEI = intraday ATR(short)/ATR(long) (baseline 10/50), causal within-session
(core.vei). Thesis: a breakout that fires while intraday volatility is EXPANDING
(VEI high) has genuine impulse behind it and follows through, whereas a breakout in
a CONTRACTING tape (VEI low) is drift into a thin band and fails. Distinct from the
RVOL level (EXP-0016) and the daily ATR scale: VEI is a vol-of-vol / regime-change
ratio. We gate entries on VEI and sweep the threshold in both directions across
(short,long) variants (the requested exploration of other variants).

Filter = a per-signal ENTRY GATE (rule 18: stateful engine rerun via `entry_gate`,
NOT a post-hoc trade drop). For variant (short,long), threshold T and direction, the
engine may open only at decision keys with VEI>=T ("high") or VEI<=T ("low").

Baseline frozen: continuous-stop NQ baseline (noise_bands lb90, RTH, 30-min clock,
VWAP gate, every-bar band/VWAP stop, next-open fills, per-instrument costs).

Primary metric = full-sample zero-trade-day daily net-ATR-R Sharpe uplift over
baseline at the family-best cell, net R co-primary. Per the standing rule the paired
Null-C runs ONLY if the family-best clears dSharpe>=+0.10 AND net R>=baseline; the
matched-count random-signal-drop null is cheap and always run on the family-best as
the rarity-filter discriminator.

Examples:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0025_vei_filter real NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0025_vei_filter real ES
  python -u -m futures.nq.noise_vwap.scripts.hyp_0025_vei_filter null NQ 30
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
from ..core import vei as V
from .studies import _null_c_frame
from .wfo import candidate_signals
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, common_dates, round_trip_cost_points,
    LOOKBACK, PERIOD, UPLIFT_GATE,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0035"
# ATR estimator for VEI: 'sma' (EXP-0035, default -> reproduces the original run) or
# 'wilder' (the RMA revisit, EXP-0036; far cleaner regime signal per vei_exploration
# Study A). Set by CLI in main(); routes OUT accordingly.
ATR_METHOD = "sma"

VARIANTS = [(5, 20), (10, 50), (10, 100), (14, 50), (20, 100)]
QGRID = np.array([0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80])
RAND_DRAWS = 200
RAND_SEED0 = 35000
NULLC_SEED0 = 35500


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


def gate_from(feat: pd.DataFrame, thr: float, direction: str) -> set:
    d = feat.dropna(subset=["vei"])
    sub = d[d["vei"] >= thr] if direction == "high" else d[d["vei"] <= thr]
    return set(zip(sub["date"], sub["mfo"].astype(int)))


def exp_r(sc: Score) -> float:
    return sc.net_r / sc.trades if sc.trades else np.nan


def run_and_score(bars, bands, dm, dates, inst, gate, name) -> Score:
    return score_candidate(run_gated(bars, bands, dm, gate), bars, dates, inst, name)


# --------------------------------------------------------------------------- #
# sweep across variants x thresholds x direction
# --------------------------------------------------------------------------- #
def sweep(inst, bars, bands, dm, dates, base: Score) -> pd.DataFrame:
    rt = round_trip_cost_points(inst)
    rows = []
    for (sh, lo) in VARIANTS:
        feat = V.vei_features(bars, dm, sh, lo, method=ATR_METHOD)
        vals = feat["vei"].dropna().to_numpy()
        thrs = np.unique(np.round(np.quantile(vals, QGRID), 4))
        for direction in ("high", "low"):
            for thr in thrs:
                gate = gate_from(feat, thr, direction)
                sc = run_and_score(bars, bands, dm, dates, inst, gate,
                                   f"{sh}_{lo}_{direction}_{thr:.3f}")
                rows.append({
                    "short": sh, "long": lo, "dir": direction, "thr": float(thr),
                    "n": sc.trades,
                    "retain": sc.trades / base.trades if base.trades else np.nan,
                    "gross_pt_per_trade": sc.net_pt_per_trade + rt,
                    "exp_netR_per_trade": exp_r(sc), "sumR": sc.net_r,
                    "sharpe": sc.sharpe, "d_sharpe": sc.sharpe - base.sharpe,
                    "d_sumR": sc.net_r - base.net_r,
                    "recent_sharpe": sc.recent_sharpe, "max_dd": sc.max_dd,
                })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# matched-count random-signal-drop null (rarity-filter discriminator)
# --------------------------------------------------------------------------- #
def matched_count_null(bars, bands, dm, dates, inst, base: Score,
                       best: pd.Series, ndraw: int = RAND_DRAWS):
    feat = V.vei_features(bars, dm, int(best["short"]), int(best["long"]), method=ATR_METHOD)
    cand = candidate_signals(bars, bands, dm)
    cand_keys = list(zip(cand["date"], cand["signal_mfo"].astype(int)))
    defined = set(zip(feat.loc[feat["vei"].notna(), "date"],
                      feat.loc[feat["vei"].notna(), "mfo"].astype(int)))
    pool = [k for k in cand_keys if k in defined]
    gate = gate_from(feat, best["thr"], best["dir"])
    K = sum(1 for k in pool if k in gate)
    rng = np.random.default_rng(RAND_SEED0)
    idx = np.arange(len(pool))
    rows = []
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
def nullc(inst, best: pd.Series, ndraw: int) -> pd.DataFrame:
    rows = []
    for i in range(ndraw):
        nb = _null_c_frame(S.load_session(inst, "RTH"), seed=NULLC_SEED0 + i)
        bands = S.noise_bands(nb, LOOKBACK)
        dm = S.decision_mfos(PERIOD, int(nb["mfo"].max()))
        dates = common_dates(nb)
        feat = V.vei_features(nb, dm, int(best["short"]), int(best["long"]), method=ATR_METHOD)
        base = score_candidate(run_gated(nb, bands, dm, None), nb, dates, inst, "nbase")
        gate = gate_from(feat, best["thr"], best["dir"])
        sc = score_candidate(run_gated(nb, bands, dm, gate), nb, dates, inst, "ntreat")
        rows.append({"draw": i + 1, "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  Null-C draw {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def fmt(df: pd.DataFrame) -> str:
    cols = ["short", "long", "dir", "thr", "n", "retain", "gross_pt_per_trade",
            "exp_netR_per_trade", "sumR", "sharpe", "d_sharpe", "d_sumR", "recent_sharpe"]
    return df[cols].to_string(index=False, float_format=lambda v: f"{v:.4f}")


def real(inst: str, run_null: bool = False, ndraw: int = 30) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    assert_parity(bars, bands, dm)

    base = score_candidate(run_gated(bars, bands, dm, None), bars, dates, inst, "baseline")
    print(f"\n=== HYP-0025 VEI entry gate — {inst} ===")
    print(f"baseline: trades={base.trades} Sharpe={base.sharpe:.4f} netR={base.net_r:.2f} "
          f"expR/trade={exp_r(base):+.4f} "
          f"grossPt/trade={base.net_pt_per_trade + round_trip_cost_points(inst):+.4f}")

    sw = sweep(inst, bars, bands, dm, dates, base)
    sw.to_csv(OUT / f"sweep_{inst}.csv", index=False)
    for (sh, lo) in VARIANTS:
        for direction in ("high", "low"):
            sub = sw[(sw["short"] == sh) & (sw["long"] == lo) & (sw["dir"] == direction)]
            print(f"\n--- VEI({sh}/{lo}) direction={direction} "
                  f"(keep {'>=' if direction == 'high' else '<='} thr) ---")
            print(fmt(sub))

    cand = sw[sw["retain"] < 0.999]
    best = cand.loc[cand["d_sharpe"].idxmax()] if len(cand) else sw.iloc[0]
    print(f"\nFAMILY-BEST (max dSharpe among filtering cells): VEI({int(best['short'])}/"
          f"{int(best['long'])}) dir={best['dir']} thr={best['thr']:.4f} "
          f"retain={best['retain']:.3f} dSharpe={best['d_sharpe']:+.4f} "
          f"dSumR={best['d_sumR']:+.2f} grossPt/trade={best['gross_pt_per_trade']:+.4f} "
          f"(base {base.net_pt_per_trade + round_trip_cost_points(inst):+.4f})")
    real_gate = bool(best["d_sharpe"] >= UPLIFT_GATE and best["sumR"] >= base.net_r)
    print(f"REAL GATE (dSharpe>=+{UPLIFT_GATE:.2f} AND netR>=base): "
          f"{'PASS' if real_gate else 'REJECT'}")

    rnd, K, pooln = matched_count_null(bars, bands, dm, dates, inst, base, best)
    rnd.to_csv(OUT / f"random_null_{inst}.csv", index=False)
    p_sh = float((rnd["d_sharpe"] >= best["d_sharpe"]).mean())
    p_r = float((rnd["d_sumR"] >= best["d_sumR"]).mean())
    print(f"\nmatched-count random-signal-drop null (keep {K} of {pooln} candidates, "
          f"{len(rnd)} draws):")
    print(f"  real  dSharpe={best['d_sharpe']:+.4f}  dSumR={best['d_sumR']:+.2f}")
    print(f"  rand  dSharpe mean={rnd['d_sharpe'].mean():+.4f} "
          f"sd={rnd['d_sharpe'].std(ddof=1):.4f}  dSumR mean={rnd['d_sumR'].mean():+.2f}")
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
    global ATR_METHOD, OUT
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    inst = sys.argv[2] if len(sys.argv) > 2 else "NQ"
    ndraw = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    ATR_METHOD = sys.argv[4] if len(sys.argv) > 4 else "sma"
    if ATR_METHOD == "wilder":
        OUT = ROOT / "artifacts" / "runs" / "EXP-0036"
    elif ATR_METHOD != "sma":
        raise SystemExit(f"unknown atr method {ATR_METHOD!r} (use sma|wilder)")
    print(f"[VEI ATR method = {ATR_METHOD}; artifacts -> {OUT.name}]")
    real(inst, run_null=(mode == "null"), ndraw=ndraw)


if __name__ == "__main__":
    main()
