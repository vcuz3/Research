"""Test HYP-0035 (EXP-0047): exit-only fast-alpha overlay at a fixed SHORT horizon.

Confirmatory follow-up to EXP-0046's searched exit-only lead. The fast 5-min
mean-reversion cue is used ONLY to time the stop-exit (delay liquidation to a
favourable micro-bounce); the harmful entry leg is dropped. The horizon-sweep
exploration showed the exit uplift is front-loaded, so we restrict the horizon to
{1,2,3} and, to avoid selecting on the same data we read, PICK h* on a TRAIN era
only, freeze it, and evaluate on a later TEST era + the full null battery.

Protocol (preregistered, HYP-0035.md):
  1. NQ common sessions split by index: TRAIN = first 60%, TEST = last 40%.
     Engine runs once over full continuous history; each era scored by subsetting
     `dates`.
  2. Select h* = argmax TRAIN exit-only dSharpe over h in {1,2,3}. Freeze it.
  3. NQ TEST kill test (ALL must hold): dSharpe>=+0.10 AND netR not fall; beats
     random-release null (frac<0.05, matched trade count); beats fixed-delay;
     inverted `same` not as good; uplift survives next_open (not only signal_close).
  4. If pass: Null C on TEST + ES TEST transfer (same-sign gate).

NOTE: all history is consumed research data, so TEST is a temporal validation
split, not a sealed holdout; the null battery + fill ablation carry the
confirmatory weight (rule 26).

Usage:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0035_exit_overlay NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0035_exit_overlay ES <h*>
  python -u -m futures.nq.noise_vwap.scripts.hyp_0035_exit_overlay null NQ <h*> 60
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
OUT = ROOT / "artifacts" / "runs" / "EXP-0047"

SPLIT_FRAC = 0.60
CANDIDATE_HORIZONS = (1, 2, 3)
RAND_DRAWS = 200
RAND_SEED0 = 47000
NULLC_SEED0 = 47500


# --------------------------------------------------------------------------- #
def load(inst):
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    return bars, bands, dm, dates


def split_dates(dates):
    k = int(round(len(dates) * SPLIT_FRAC))
    return dates[:k], dates[k:]


def gross_pt(sc: Score, inst: str) -> float:
    return sc.net_pt_per_trade + round_trip_cost_points(inst)


def run_ov(bars, bands, dm, *, fill_mode="next_open", fast_overlay=False,
           fast_release="opposite", fast_horizon=2, fast_fixed_delay=5,
           fast_hazard=None, fast_seed=0, fast_audit=None):
    """Exit-only overlay (entry leg OFF) on the frozen continuous-stop baseline."""
    return E.run(bars, bands, dm, fill_mode=fill_mode, require_vwap=True,
                 exit_check="every_bar", stop_ref="both",
                 fast_overlay=fast_overlay, fast_release=fast_release,
                 fast_horizon=fast_horizon, fast_entry=False, fast_exit=True,
                 fast_fixed_delay=fast_fixed_delay, fast_hazard=fast_hazard,
                 fast_seed=fast_seed, fast_audit=fast_audit)


def assert_parity(bars, bands, dm) -> None:
    for fm in ("next_open", "signal_close"):
        a = E.run(bars, bands, dm, fill_mode=fm, require_vwap=True,
                  exit_check="every_bar", stop_ref="both")
        b = run_ov(bars, bands, dm, fill_mode=fm, fast_overlay=False)
        assert a.equals(b), f"fast_overlay=False not bit-exact under {fm}"


def coverage(audit) -> dict:
    ad = pd.DataFrame(audit) if audit else pd.DataFrame(
        columns=["kind", "side", "delay", "dropped"])
    k = ad[ad["kind"] == "exit"] if "kind" in ad else ad
    rel = k[~k["dropped"]] if "dropped" in k else k
    drp = k[k["dropped"]] if "dropped" in k else k.iloc[0:0]
    return dict(n_armed=int(len(k)), n_released=int(len(rel)), n_dropped=int(len(drp)),
                drop_frac=float(len(drp) / len(k)) if len(k) else float("nan"),
                mean_delay=float(rel["delay"].mean()) if len(rel) else float("nan"),
                median_delay=float(rel["delay"].median()) if len(rel) else float("nan"),
                p90_delay=float(rel["delay"].quantile(0.90)) if len(rel) else float("nan"))


# --------------------------------------------------------------------------- #
# Step 2: select h* on TRAIN only
# --------------------------------------------------------------------------- #
def select_horizon(inst, bars, bands, dm, train_dates):
    base = score_candidate(run_ov(bars, bands, dm, fast_overlay=False),
                           bars, train_dates, inst, "base")
    rows = []
    for h in CANDIDATE_HORIZONS:
        sc = score_candidate(
            run_ov(bars, bands, dm, fast_overlay=True, fast_horizon=h),
            bars, train_dates, inst, f"h{h}")
        rows.append(dict(horizon=h, n=sc.trades, sharpe=sc.sharpe,
                         d_sharpe=sc.sharpe - base.sharpe,
                         d_sumR=sc.net_r - base.net_r, gross_pt=gross_pt(sc, inst)))
    tab = pd.DataFrame(rows)
    hstar = int(tab.loc[tab["d_sharpe"].idxmax(), "horizon"])
    return hstar, tab, base


# --------------------------------------------------------------------------- #
# calibration + arms on a given `dates` era
# --------------------------------------------------------------------------- #
def calibrate_fixed_delay(bars, bands, dm, hstar) -> tuple[int, dict]:
    aud = []
    run_ov(bars, bands, dm, fast_overlay=True, fast_horizon=hstar, fast_audit=aud)
    cov = coverage(aud)
    md = cov["mean_delay"]
    return (int(max(1, round(md))) if np.isfinite(md) else 5), cov


def calibrate_hazard(bars, bands, dm, dates, inst, hstar, target_n) -> float:
    def n_at(p):
        t = run_ov(bars, bands, dm, fast_overlay=True, fast_release="random",
                   fast_horizon=hstar, fast_hazard=p, fast_seed=999)
        return score_candidate(t, bars, dates, inst, "cal").trades
    lo, hi = 1e-3, 1.0
    for _ in range(18):
        mid = (lo + hi) / 2
        if n_at(mid) < target_n:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def arm_table(inst, bars, bands, dm, dates, hstar, fixed_delay, hazard):
    base = score_candidate(run_ov(bars, bands, dm, fast_overlay=False),
                           bars, dates, inst, "base")
    scores = {"baseline": base}
    rows = [dict(arm="(baseline)", n=base.trades, gross_pt=gross_pt(base, inst),
                 sumR=base.net_r, sharpe=base.sharpe, d_sharpe=0.0, d_sumR=0.0,
                 recent_sharpe=base.recent_sharpe)]
    for rel, kw in (("opposite", {}), ("same", {}),
                    ("fixed", {"fast_fixed_delay": fixed_delay}),
                    ("random", {"fast_hazard": hazard})):
        sc = score_candidate(
            run_ov(bars, bands, dm, fast_overlay=True, fast_release=rel,
                   fast_horizon=hstar, fast_seed=RAND_SEED0, **kw),
            bars, dates, inst, rel)
        scores[rel] = sc
        rows.append(dict(arm=rel, n=sc.trades, gross_pt=gross_pt(sc, inst),
                         sumR=sc.net_r, sharpe=sc.sharpe,
                         d_sharpe=sc.sharpe - base.sharpe,
                         d_sumR=sc.net_r - base.net_r,
                         recent_sharpe=sc.recent_sharpe))
    return pd.DataFrame(rows), scores


def fill_ablation(inst, bars, bands, dm, dates, hstar):
    out = {}
    for fm in ("next_open", "signal_close"):
        b = score_candidate(run_ov(bars, bands, dm, fill_mode=fm,
                                   fast_overlay=False), bars, dates, inst, "b")
        o = score_candidate(run_ov(bars, bands, dm, fill_mode=fm, fast_overlay=True,
                                   fast_horizon=hstar), bars, dates, inst, "o")
        out[fm] = dict(base_sharpe=b.sharpe, overlay_sharpe=o.sharpe,
                       d_sharpe=o.sharpe - b.sharpe, d_sumR=o.net_r - b.net_r)
    return out


def random_release_null(inst, bars, bands, dm, dates, base, hstar, hazard,
                        ndraw=RAND_DRAWS):
    rows = []
    for i in range(ndraw):
        sc = score_candidate(
            run_ov(bars, bands, dm, fast_overlay=True, fast_release="random",
                   fast_horizon=hstar, fast_hazard=hazard, fast_seed=RAND_SEED0 + i),
            bars, dates, inst, "rand")
        rows.append({"draw": i + 1, "n": sc.trades,
                     "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  random-release null {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


def nullc(inst, real_bars, dates, hstar, ndraw):
    rows = []
    for i in range(ndraw):
        nb = _null_c_frame(real_bars, seed=NULLC_SEED0 + i)
        bands = S.noise_bands(nb, LOOKBACK)
        dm = S.decision_mfos(PERIOD, int(nb["mfo"].max()))
        base = score_candidate(run_ov(nb, bands, dm, fast_overlay=False),
                               nb, dates, inst, "nb")
        sc = score_candidate(run_ov(nb, bands, dm, fast_overlay=True,
                                    fast_horizon=hstar), nb, dates, inst, "nt")
        rows.append({"draw": i + 1, "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  Null-C draw {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def evaluate(inst, hstar=None, run_null=False, ndraw=60):
    OUT.mkdir(parents=True, exist_ok=True)
    bars, bands, dm, dates = load(inst)
    train, test = split_dates(dates)
    assert_parity(bars, bands, dm)
    print(f"\n=== HYP-0035 exit-only fast-alpha overlay — {inst} ===")
    print(f"sessions={len(dates)}  TRAIN={len(train)} "
          f"({pd.Timestamp(train[0]).date()}->{pd.Timestamp(train[-1]).date()})  "
          f"TEST={len(test)} "
          f"({pd.Timestamp(test[0]).date()}->{pd.Timestamp(test[-1]).date()})")
    print("default-off parity: PASS (bit-exact under both fill modes)")

    # Step 2: select horizon on TRAIN (NQ) or accept the frozen h* (ES/transfer)
    if hstar is None:
        hstar, seltab, _ = select_horizon(inst, bars, bands, dm, train)
        print("\n--- horizon selection on TRAIN (exit-only dSharpe, h in {1,2,3}) ---")
        print(seltab.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        seltab.to_csv(OUT / f"horizon_select_{inst}.csv", index=False)
    print(f"\nFROZEN h* = {hstar} min")

    # Step 3: TEST-era kill test
    fixed_delay, cov = calibrate_fixed_delay(bars, bands, dm, hstar)
    base_test = score_candidate(run_ov(bars, bands, dm, fast_overlay=False),
                                bars, test, inst, "base")
    real_test = score_candidate(
        run_ov(bars, bands, dm, fast_overlay=True, fast_horizon=hstar),
        bars, test, inst, "real")
    hazard = calibrate_hazard(bars, bands, dm, test, inst, hstar, real_test.trades)
    print(f"fixed-delay={fixed_delay} bars (real mean exit delay); "
          f"random hazard p={hazard:.4f} (target TEST n={real_test.trades})")

    tab, scores = arm_table(inst, bars, bands, dm, test, hstar, fixed_delay, hazard)
    tab.to_csv(OUT / f"arms_test_{inst}.csv", index=False)
    print("\n--- TEST-era arm grid ---")
    print(tab.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    base, real = scores["baseline"], scores["opposite"]
    d_sh = real.sharpe - base.sharpe
    d_r = real.net_r - base.net_r
    same_sh = scores["same"].sharpe - base.sharpe
    fixed_sh = scores["fixed"].sharpe - base.sharpe
    real_gate = bool(d_sh >= UPLIFT_GATE and real.net_r >= base.net_r)
    print(f"\nTEST PRIMARY: dSharpe={d_sh:+.4f}  dNetR={d_r:+.2f}  "
          f"grossPt/t {gross_pt(base, inst):+.4f}->{gross_pt(real, inst):+.4f}")
    print(f"  REAL GATE (dSharpe>=+{UPLIFT_GATE:.2f} AND netR>=base): "
          f"{'PASS' if real_gate else 'REJECT'}")
    print(f"  vs inverted same={same_sh:+.4f}  vs fixed={fixed_sh:+.4f}")

    fabl = fill_ablation(inst, bars, bands, dm, test, hstar)
    with open(OUT / f"fill_ablation_test_{inst}.json", "w") as f:
        json.dump(fabl, f, indent=2, default=float)
    print("\n--- fill ablation (TEST) ---")
    for fm, v in fabl.items():
        print(f"  {fm:<12s} base={v['base_sharpe']:.4f} overlay={v['overlay_sharpe']:.4f} "
              f"dSharpe={v['d_sharpe']:+.4f} dSumR={v['d_sumR']:+.2f}")
    survives_next_open = bool(fabl["next_open"]["d_sharpe"] > 0
                              and fabl["next_open"]["d_sumR"] > 0)

    print("\n--- random-release null (TEST, matched trade count) ---")
    rnd = random_release_null(inst, bars, bands, dm, test, base, hstar, hazard)
    rnd.to_csv(OUT / f"random_null_test_{inst}.csv", index=False)
    p_sh = float((rnd["d_sharpe"] >= d_sh).mean())
    print(f"  real n={real.trades} rand n mean={rnd['n'].mean():.0f} "
          f"[{rnd['n'].min()},{rnd['n'].max()}]  (base {base.trades})")
    print(f"  real dSharpe={d_sh:+.4f}  rand mean={rnd['d_sharpe'].mean():+.4f} "
          f"sd={rnd['d_sharpe'].std(ddof=1):.4f}  frac(rand>=real)={p_sh:.3f}")

    beats_random = bool(p_sh < 0.05)
    beats_fixed = bool(d_sh > fixed_sh)
    beats_same = bool(d_sh > same_sh)
    kill = dict(real_gate=real_gate, beats_random=beats_random,
                beats_fixed=beats_fixed, beats_same=beats_same,
                survives_next_open=survives_next_open)
    passed = all(kill.values())
    print(f"\nKILL TEST (NQ TEST, all must hold): {kill} -> "
          f"{'SURVIVES' if passed else 'REJECT'}")

    verdict = dict(inst=inst, hstar=hstar, split_frac=SPLIT_FRAC,
                   n_train=int(len(train)), n_test=int(len(test)),
                   fixed_delay=fixed_delay, hazard=hazard,
                   base={"n": base.trades, "sharpe": base.sharpe, "netR": base.net_r,
                         "gross_pt": gross_pt(base, inst),
                         "recent_sharpe": base.recent_sharpe},
                   real={"n": real.trades, "sharpe": real.sharpe, "netR": real.net_r,
                         "gross_pt": gross_pt(real, inst),
                         "recent_sharpe": real.recent_sharpe},
                   d_sharpe=d_sh, d_sumR=d_r, same_d_sharpe=same_sh,
                   fixed_d_sharpe=fixed_sh, rand_frac_ge_real=p_sh,
                   rand_dSharpe_mean=float(rnd["d_sharpe"].mean()),
                   fill_ablation=fabl, coverage=cov,
                   kill_test=kill, kill_test_passed=passed)

    if run_null and real_gate:
        print(f"\n--- drift-preserving Null C on TEST ({ndraw} draws) ---")
        print(f"  real diffusivity={diffusivity(bars):.6f}")
        nc = nullc(inst, bars, test, hstar, ndraw)
        nc.to_csv(OUT / f"nullc_test_{inst}.csv", index=False)
        sd = nc["d_sharpe"].std(ddof=1)
        z = (d_sh - nc["d_sharpe"].mean()) / sd if sd > 0 else np.nan
        p = float((nc["d_sharpe"] >= d_sh).mean())
        verdict.update(nullc_z=float(z), nullc_frac_ge_real=p,
                       nullc_dSharpe_mean=float(nc["d_sharpe"].mean()))
        print(f"  Null-C dSharpe mean={nc['d_sharpe'].mean():+.4f} sd={sd:.4f} "
              f"z={z:+.2f} frac(null>=real)={p:.3f}")
    elif run_null:
        print("\nReal gate did not pass -> Null C skipped (standing gate rule).")

    with open(OUT / f"verdict_{inst}.json", "w") as f:
        json.dump(verdict, f, indent=2, default=float)
    print(f"\nartifacts -> {OUT}")
    return verdict


def main():
    a = sys.argv
    if len(a) > 1 and a[1] == "null":
        inst = a[2] if len(a) > 2 else "NQ"
        hstar = int(a[3]) if len(a) > 3 else None
        ndraw = int(a[4]) if len(a) > 4 else 60
        evaluate(inst, hstar=hstar, run_null=True, ndraw=ndraw)
        return
    inst = a[1] if len(a) > 1 else "NQ"
    hstar = int(a[2]) if len(a) > 2 else None
    evaluate(inst, hstar=hstar, run_null=False)


if __name__ == "__main__":
    main()
