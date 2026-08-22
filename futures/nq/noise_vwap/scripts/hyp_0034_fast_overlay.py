"""Test HYP-0034: the fast-alpha EXECUTION OVERLAY (Zarattini & Pagani, 2026).

A fast-decaying 5-min mean-reversion alpha (unprofitable standalone after its own
turnover) is used only to TIME the fills of the slow breakout: after a breakout is
confirmed, postpone the entry until a fast opposite bar prints (a micro-pullback);
after the band/VWAP stop first triggers, postpone the liquidation until a fast
favourable bar prints (a bounce). The structural signal and the mandatory EOD flat
are unchanged; only fill TIMING moves. The paper reports Sharpe 0.87 -> 0.99.

Single default-off overlay on the frozen continuous-stop baseline (`core.engine2`,
bands lb90, RTH, 30-min Concretum clock, VWAP gate, every-bar band/VWAP stop,
next-open fills, explicit costs). When `fast_overlay=False` the engine is bit-exact
the baseline (asserted).

The overlay's machinery (arm a pending entry/exit, wait, release) is IDENTICAL
across the real arm and every control; only the RELEASE TRIGGER differs
(mirroring the EXP-0043 discipline):

  * opposite  -- the paper: entry on a pullback, exit on a bounce (the REAL arm).
  * same      -- inverted control: entry on a same-dir bar, exit on an adverse bar.
                 A symmetric result falsifies the mean-reversion mechanism.
  * fixed     -- fixed-delay control: release exactly `fast_fixed_delay` bars after
                 arming, calibrated to the real arm's mean achieved delay. A blind
                 wait that reproduces the gain means the fast alpha carries no info.
  * random    -- DECISIVE random-release null: release on a coin flip at hazard
                 `fast_hazard`, calibrated (bisection) to the real arm's trade
                 count. Keeps the wait/exposure, destroys only the information.
                 (This project has repeatedly found "waiting/less exposure" to be
                 machinery: the FX random-exit control, EXP-0043 control 1b.)

Also reported: entry-only vs exit-only decomposition; a signal_close vs next_open
fill ablation (LEARNINGS Section 6 shared-close / touch-vs-fill: ~all contiguous
minutes open at the prior close, so "enter at the pullback" can be the same number
that ended the displacement); and coverage (drop rate + achieved-delay dist).

Per the standing rule the drift-preserving Null C runs ONLY if the REAL (opposite)
arm on the PRIMARY market clears dSharpe >= +0.10 AND net R does not fall.

Examples:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0034_fast_overlay real NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0034_fast_overlay real ES
  python -u -m futures.nq.noise_vwap.scripts.hyp_0034_fast_overlay null NQ 40
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .studies import _null_c_frame, diffusivity
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, common_dates, round_trip_cost_points,
    LOOKBACK, PERIOD, UPLIFT_GATE,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0046"

HORIZON = 5                 # the paper's 5-min fast alpha (the only free knob)
RELEASES = ("opposite", "same", "fixed", "random")
REAL = "opposite"
RAND_DRAWS = 200
RAND_SEED0 = 46000
NULLC_SEED0 = 46500


# --------------------------------------------------------------------------- #
# engine helpers
# --------------------------------------------------------------------------- #
def run_overlay(bars, bands, dm, *, fill_mode="next_open", fast_overlay=False,
                fast_release="opposite", fast_entry=True, fast_exit=True,
                fast_fixed_delay=5, fast_hazard=None, fast_seed=0,
                fast_audit=None):
    return E.run(bars, bands, dm, fill_mode=fill_mode, require_vwap=True,
                 exit_check="every_bar", fast_overlay=fast_overlay,
                 fast_release=fast_release, fast_horizon=HORIZON,
                 fast_entry=fast_entry, fast_exit=fast_exit,
                 fast_fixed_delay=fast_fixed_delay, fast_hazard=fast_hazard,
                 fast_seed=fast_seed, fast_audit=fast_audit)


def assert_parity(bars, bands, dm) -> None:
    """The overlay must be inert at its default (rule 23), under both fill modes."""
    for fm in ("next_open", "signal_close"):
        a = E.run(bars, bands, dm, fill_mode=fm, require_vwap=True,
                  exit_check="every_bar")
        b = run_overlay(bars, bands, dm, fill_mode=fm, fast_overlay=False)
        assert a.equals(b), f"fast_overlay=False is not bit-exact under fill_mode={fm}"


def gross_pt(sc: Score, inst: str) -> float:
    return sc.net_pt_per_trade + round_trip_cost_points(inst)


def hit_rate(t: pd.DataFrame, bars: pd.DataFrame, inst: str) -> float:
    if t.empty:
        return float("nan")
    rt = round_trip_cost_points(inst)
    return float(((t["points"] - rt) > 0).mean())


# --------------------------------------------------------------------------- #
# coverage (rule 9a): drops and achieved-delay distribution
# --------------------------------------------------------------------------- #
def coverage(audit: list[dict]) -> dict:
    ad = pd.DataFrame(audit) if audit else pd.DataFrame(
        columns=["kind", "side", "delay", "dropped"])
    out = {}
    for kind in ("entry", "exit"):
        k = ad[ad["kind"] == kind] if "kind" in ad else ad
        rel = k[~k["dropped"]] if "dropped" in k else k
        drp = k[k["dropped"]] if "dropped" in k else k.iloc[0:0]
        out[kind] = dict(
            n_armed=int(len(k)), n_released=int(len(rel)), n_dropped=int(len(drp)),
            drop_frac=float(len(drp) / len(k)) if len(k) else float("nan"),
            mean_delay=float(rel["delay"].mean()) if len(rel) else float("nan"),
            median_delay=float(rel["delay"].median()) if len(rel) else float("nan"),
            p90_delay=float(rel["delay"].quantile(0.90)) if len(rel) else float("nan"),
        )
    rel_all = ad[~ad["dropped"]] if "dropped" in ad else ad
    out["mean_delay_all"] = (float(rel_all["delay"].mean())
                             if len(rel_all) else float("nan"))
    return out


# --------------------------------------------------------------------------- #
# the release-arm grid (opposite / same / fixed / random), each at matched wait
# --------------------------------------------------------------------------- #
def calibrate_fixed_delay(bars, bands, dm) -> tuple[int, dict]:
    """Fixed-delay = the REAL arm's mean achieved release delay (entry+exit)."""
    aud: list[dict] = []
    run_overlay(bars, bands, dm, fast_overlay=True, fast_release=REAL,
                fast_audit=aud)
    cov = coverage(aud)
    md = cov["mean_delay_all"]
    return int(max(1, round(md))) if np.isfinite(md) else 5, cov


def calibrate_hazard(bars, bands, dm, dates, inst, target_n: int) -> float:
    """Per-bar release hazard reproducing the REAL arm's trade count. Higher hazard
    releases sooner -> fewer dropped entries -> more trades: monotone, so bisect."""
    def n_at(p):
        t = run_overlay(bars, bands, dm, fast_overlay=True, fast_release="random",
                        fast_hazard=p, fast_seed=999)
        return score_candidate(t, bars, dates, inst, "cal").trades
    lo, hi = 1e-3, 1.0
    for _ in range(16):
        mid = (lo + hi) / 2
        if n_at(mid) < target_n:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def arm_table(inst, bars, bands, dm, dates, fixed_delay, hazard):
    rows, scores, covs = [], {}, {}
    base = score_candidate(
        run_overlay(bars, bands, dm, fast_overlay=False), bars, dates, inst, "base")
    scores["baseline"] = base
    rows.append(dict(arm="(baseline)", n=base.trades, retain=1.0,
                     gross_pt=gross_pt(base, inst), sumR=base.net_r,
                     expR=base.net_r / base.trades if base.trades else np.nan,
                     sharpe=base.sharpe, d_sharpe=0.0, d_sumR=0.0,
                     max_dd=base.max_dd, recent_sharpe=base.recent_sharpe,
                     mean_delay=np.nan, drop_frac=np.nan))
    for rel in RELEASES:
        aud: list[dict] = []
        t = run_overlay(bars, bands, dm, fast_overlay=True, fast_release=rel,
                        fast_fixed_delay=fixed_delay, fast_hazard=hazard,
                        fast_seed=RAND_SEED0, fast_audit=aud)
        sc = score_candidate(t, bars, dates, inst, rel)
        cov = coverage(aud)
        scores[rel] = sc
        covs[rel] = cov
        rows.append(dict(
            arm=rel, n=sc.trades,
            retain=sc.trades / base.trades if base.trades else np.nan,
            gross_pt=gross_pt(sc, inst), sumR=sc.net_r,
            expR=sc.net_r / sc.trades if sc.trades else np.nan,
            sharpe=sc.sharpe, d_sharpe=sc.sharpe - base.sharpe,
            d_sumR=sc.net_r - base.net_r, max_dd=sc.max_dd,
            recent_sharpe=sc.recent_sharpe,
            mean_delay=cov["mean_delay_all"],
            drop_frac=cov["entry"]["drop_frac"]))
    return pd.DataFrame(rows), scores, covs


# --------------------------------------------------------------------------- #
# entry-only vs exit-only decomposition (which leg carries any effect)
# --------------------------------------------------------------------------- #
def leg_table(inst, bars, bands, dm, dates, base: Score):
    rows = {}
    for name, (fe, fx) in (("entry_only", (True, False)),
                           ("exit_only", (False, True)),
                           ("both", (True, True))):
        sc = score_candidate(
            run_overlay(bars, bands, dm, fast_overlay=True, fast_release=REAL,
                        fast_entry=fe, fast_exit=fx),
            bars, dates, inst, name)
        rows[name] = dict(n=sc.trades, sharpe=sc.sharpe,
                          d_sharpe=sc.sharpe - base.sharpe,
                          sumR=sc.net_r, d_sumR=sc.net_r - base.net_r,
                          gross_pt=gross_pt(sc, inst))
    return rows


# --------------------------------------------------------------------------- #
# fill ablation: does any uplift survive a pessimistic-vs-optimistic fill swap?
# --------------------------------------------------------------------------- #
def fill_ablation(inst, bars, bands, dm, dates):
    out = {}
    for fm in ("next_open", "signal_close"):
        b = score_candidate(run_overlay(bars, bands, dm, fill_mode=fm,
                                        fast_overlay=False), bars, dates, inst, "b")
        o = score_candidate(run_overlay(bars, bands, dm, fill_mode=fm,
                                        fast_overlay=True, fast_release=REAL),
                            bars, dates, inst, "o")
        out[fm] = dict(base_sharpe=b.sharpe, overlay_sharpe=o.sharpe,
                       d_sharpe=o.sharpe - b.sharpe,
                       base_sumR=b.net_r, overlay_sumR=o.net_r,
                       d_sumR=o.net_r - b.net_r)
    return out


# --------------------------------------------------------------------------- #
# DECISIVE control: random-release null (matched trade count)
# --------------------------------------------------------------------------- #
def random_release_null(inst, bars, bands, dm, dates, base: Score, real: Score,
                        hazard: float, ndraw: int = RAND_DRAWS):
    rows = []
    for i in range(ndraw):
        t = run_overlay(bars, bands, dm, fast_overlay=True, fast_release="random",
                        fast_hazard=hazard, fast_seed=RAND_SEED0 + i)
        sc = score_candidate(t, bars, dates, inst, "rand")
        rows.append({"draw": i + 1, "hazard": hazard, "n": sc.trades,
                     "sharpe": sc.sharpe, "sumR": sc.net_r,
                     "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  random-release null {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# drift-preserving Null C (gated on the primary metric)
# --------------------------------------------------------------------------- #
def nullc(inst, real_bars, fixed_delay, ndraw: int) -> pd.DataFrame:
    rows = []
    for i in range(ndraw):
        nb = _null_c_frame(real_bars, seed=NULLC_SEED0 + i)
        bands = S.noise_bands(nb, LOOKBACK)
        dm = S.decision_mfos(PERIOD, int(nb["mfo"].max()))
        dates = common_dates(nb)
        base = score_candidate(run_overlay(nb, bands, dm, fast_overlay=False),
                               nb, dates, inst, "nb")
        sc = score_candidate(
            run_overlay(nb, bands, dm, fast_overlay=True, fast_release=REAL,
                        fast_fixed_delay=fixed_delay), nb, dates, inst, "nt")
        rows.append({"draw": i + 1, "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  Null-C draw {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def real(inst: str, run_null: bool = False, ndraw: int = 40) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    assert_parity(bars, bands, dm)

    print(f"\n=== HYP-0034 fast-alpha execution overlay — {inst} ===")
    print(f"sessions={len(dates)}  {pd.Timestamp(dates[0]).date()} -> "
          f"{pd.Timestamp(dates[-1]).date()}  (lb{LOOKBACK}, {PERIOD}m clock, "
          f"VWAP gate, next-open fills, {HORIZON}m fast alpha)")
    print("default-off parity: PASS (fast_overlay=False is bit-exact under both fill modes)")

    fixed_delay, real_cov = calibrate_fixed_delay(bars, bands, dm)
    print(f"fixed-delay calibrated to real arm mean achieved delay = {fixed_delay} bars")
    # calibrate the random-release hazard to the REAL arm's trade count
    real0_aud: list[dict] = []
    real0 = score_candidate(
        run_overlay(bars, bands, dm, fast_overlay=True, fast_release=REAL,
                    fast_audit=real0_aud), bars, dates, inst, "real")
    hazard = calibrate_hazard(bars, bands, dm, dates, inst, target_n=real0.trades)
    print(f"random-release hazard calibrated to p={hazard:.4f} "
          f"(target real n={real0.trades})")

    tab, scores, covs = arm_table(inst, bars, bands, dm, dates, fixed_delay, hazard)
    tab.to_csv(OUT / f"arms_{inst}.csv", index=False)
    print("\n--- release-arm grid (opposite=paper, same=inverted, fixed, random) ---")
    print(tab.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    base, real_sc = scores["baseline"], scores[REAL]
    d_sh = real_sc.sharpe - base.sharpe
    d_r = real_sc.net_r - base.net_r
    real_gate = bool(d_sh >= UPLIFT_GATE and real_sc.net_r >= base.net_r)
    print(f"\nPRIMARY (REAL '{REAL}' arm, entry+exit): "
          f"dSharpe={d_sh:+.4f}  dNetR={d_r:+.2f}  "
          f"grossPt/t {gross_pt(base, inst):+.4f}->{gross_pt(real_sc, inst):+.4f}")
    print(f"  REAL GATE (dSharpe>=+{UPLIFT_GATE:.2f} AND netR>=base): "
          f"{'PASS' if real_gate else 'REJECT'}")

    # kill-test comparators from the arm grid
    same_sh = scores["same"].sharpe - base.sharpe
    fixed_sh = scores["fixed"].sharpe - base.sharpe
    print(f"  vs inverted 'same' dSharpe={same_sh:+.4f} "
          f"(real must clearly beat it)  vs 'fixed' dSharpe={fixed_sh:+.4f}")

    print("\n--- coverage (rule 9a): drops + achieved delay, REAL arm ---")
    for kind in ("entry", "exit"):
        c = covs[REAL][kind]
        print(f"  {kind:5s} armed={c['n_armed']:5d} released={c['n_released']:5d} "
              f"dropped={c['n_dropped']:4d} ({c['drop_frac']:.3f})  "
              f"mean_delay={c['mean_delay']:.2f} median={c['median_delay']:.1f} "
              f"p90={c['p90_delay']:.1f}")
    with open(OUT / f"coverage_{inst}.json", "w") as f:
        json.dump(covs, f, indent=2, default=float)

    print("\n--- entry-only vs exit-only decomposition (REAL arm) ---")
    legs = leg_table(inst, bars, bands, dm, dates, base)
    for k, v in legs.items():
        print(f"  {k:<11s} n={v['n']:5d} dSharpe={v['d_sharpe']:+.4f} "
              f"dSumR={v['d_sumR']:+.2f} grossPt/t={v['gross_pt']:+.4f}")
    with open(OUT / f"legs_{inst}.json", "w") as f:
        json.dump(legs, f, indent=2, default=float)

    print("\n--- fill ablation (next_open vs signal_close) ---")
    fabl = fill_ablation(inst, bars, bands, dm, dates)
    for fm, v in fabl.items():
        print(f"  {fm:<12s} base Sharpe={v['base_sharpe']:.4f} "
              f"overlay={v['overlay_sharpe']:.4f} dSharpe={v['d_sharpe']:+.4f} "
              f"dSumR={v['d_sumR']:+.2f}")
    with open(OUT / f"fill_ablation_{inst}.json", "w") as f:
        json.dump(fabl, f, indent=2, default=float)

    print("\n--- DECISIVE control: random-release null (matched trade count) ---")
    rnd = random_release_null(inst, bars, bands, dm, dates, base, real_sc, hazard)
    rnd.to_csv(OUT / f"random_null_{inst}.csv", index=False)
    p_sh = float((rnd["d_sharpe"] >= d_sh).mean())
    p_r = float((rnd["d_sumR"] >= d_r).mean())
    print(f"  EXPOSURE MATCH: real n={real_sc.trades}  random n mean="
          f"{rnd['n'].mean():.0f} [{rnd['n'].min()}, {rnd['n'].max()}]  "
          f"(baseline {base.trades})")
    print(f"  real dSharpe={d_sh:+.4f}  dSumR={d_r:+.2f}")
    print(f"  rand dSharpe mean={rnd['d_sharpe'].mean():+.4f} "
          f"sd={rnd['d_sharpe'].std(ddof=1):.4f}  dSumR mean={rnd['d_sumR'].mean():+.2f}")
    print(f"  frac(rand>=real): Sharpe={p_sh:.3f}  sumR={p_r:.3f}  "
          f"(<0.05 = the fast alpha beats a random wait at matched exposure)")

    # kill-test assembly
    beats_random = bool(p_sh < 0.05)
    beats_fixed = bool(d_sh > fixed_sh)
    beats_same = bool(d_sh > same_sh)
    kill = dict(real_gate=real_gate, beats_random=beats_random,
                beats_fixed=beats_fixed, beats_same=beats_same)
    passed = all(kill.values())
    print(f"\nKILL TEST (all must hold on NQ): {kill} -> "
          f"{'SURVIVES' if passed else 'REJECT'}")

    verdict = {
        "inst": inst, "horizon": HORIZON, "sessions": int(len(dates)),
        "fixed_delay": fixed_delay, "hazard": hazard,
        "base": {"n": base.trades, "sharpe": base.sharpe, "netR": base.net_r,
                 "gross_pt": gross_pt(base, inst), "max_dd": base.max_dd,
                 "recent_sharpe": base.recent_sharpe},
        "real": {"n": real_sc.trades, "sharpe": real_sc.sharpe,
                 "netR": real_sc.net_r, "gross_pt": gross_pt(real_sc, inst),
                 "max_dd": real_sc.max_dd, "recent_sharpe": real_sc.recent_sharpe},
        "d_sharpe": d_sh, "d_sumR": d_r,
        "same_d_sharpe": same_sh, "fixed_d_sharpe": fixed_sh,
        "rand_frac_ge_real_sharpe": p_sh, "rand_frac_ge_real_sumR": p_r,
        "rand_dSharpe_mean": float(rnd["d_sharpe"].mean()),
        "rand_n_mean": float(rnd["n"].mean()),
        "legs": legs, "fill_ablation": fabl, "coverage": covs[REAL],
        "kill_test": kill, "kill_test_passed": passed,
        "arms": tab.to_dict(orient="records"),
    }

    if run_null and real_gate:
        print(f"\n--- drift-preserving Null C ({ndraw} draws) ---")
        print(f"  real diffusivity={diffusivity(bars):.6f}")
        nc = nullc(inst, bars, fixed_delay, ndraw)
        nc.to_csv(OUT / f"nullc_{inst}.csv", index=False)
        sd = nc["d_sharpe"].std(ddof=1)
        z = (d_sh - nc["d_sharpe"].mean()) / sd if sd > 0 else np.nan
        p = float((nc["d_sharpe"] >= d_sh).mean())
        verdict.update(nullc_z=float(z), nullc_frac_ge_real=p,
                       nullc_dSharpe_mean=float(nc["d_sharpe"].mean()))
        print(f"  Null-C dSharpe mean={nc['d_sharpe'].mean():+.4f} sd={sd:.4f} "
              f"z={z:+.2f} frac(null>=real)={p:.3f}")
    elif run_null:
        print("\nReal gate did not pass -> Null C skipped (standing project rule).")

    with open(OUT / f"verdict_{inst}.json", "w") as f:
        json.dump(verdict, f, indent=2, default=float)
    print(f"\nartifacts -> {OUT}")
    return verdict


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    inst = sys.argv[2] if len(sys.argv) > 2 else "NQ"
    ndraw = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    real(inst, run_null=(mode == "null"), ndraw=ndraw)


if __name__ == "__main__":
    main()
