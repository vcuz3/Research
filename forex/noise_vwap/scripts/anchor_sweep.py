"""
HYP-0003 / EXP-0003 — is the FX Noise-Area failure caused by an ARBITRARY anchor?

    python -u -m forex.noise_vwap.scripts.anchor_sweep

Sweeps the session ANCHOR and holds everything else fixed. 24 hourly ET anchors
form the placebo family (the null distribution); four structural FX anchors and
the NQ cash open are the hypotheses. The NQ arm is a POSITIVE CONTROL and a
validity gate: a null result on FX is uninterpretable unless the same diagnostic
detects a known-real anchor.

The kill test, the fixed primary cell and the pass thresholds are preregistered in
`experiments/hypotheses/HYP-0003.md` and are not restated here as anything other
than code.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import anchor_measure as M
from ..core import anchors as A

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0003"

HORIZONS = (30, 60, 120, 240)
PRIMARY_H = 60
PRIMARY_EMBARGO = 1
PRIMARY_GATE = True

FX_INCUMBENT = "NY_ROLL"     # the frozen `fxday` anchor; sets the FX target rate
NQ_INCUMBENT = "RTH_OPEN"    # the real NQ boundary; sets the NQ target rate


def cell(prices, dense, anchor, gate, target_rate, horizons, roll_min=frozenset(),
         length=A.SESSION_LENGTH):
    """One (instrument, anchor) cell: build the anchored band, match the fire
    rate, and measure exit-neutral forward returns under both embargo arms.

    `roll_min` are contract-roll minutes (NQ). Any session containing one is
    dropped outright, so no synthetic adjustment jump can fall inside a measured
    forward return (rule 11).
    """
    o, c, lo = dense
    sess = A.anchored_sessions(prices, anchor, length)
    if roll_min:
        bad = sess.loc[sess["utc_min"].isin(roll_min), "date"].unique()
        sess = sess[~sess["date"].isin(bad)]
    ref = A.anchor_reference(sess)
    stability = float(ref["stable"].mean()) if len(ref) else np.nan

    stable_dates = ref.index[ref["stable"]]
    sess = sess[sess["date"].isin(stable_dates)]
    dec = A.decision_rows(sess, length)
    n_dec = len(dec)
    if n_dec == 0:
        return None

    sigma = A.band_sigma(dec, ref)
    rat = M.signal_ratios(dec, ref, sigma, gate=gate)
    if len(rat) == 0:
        return None
    band_cov = len(rat) / n_dec

    raw_rate = float(M.fire_rates(rat, np.array([1.0]))[0])
    if target_rate is None:
        k, matched_rate = 1.0, raw_rate
    else:
        k, matched_rate = M.pick_k(rat, target_rate)

    sig = M.take_signals(rat, k)
    res = {"anchor": anchor.name, "tz": anchor.tz,
           "hhmm": f"{anchor.hour:02d}:{anchor.minute:02d}",
           "structural": anchor.structural, "n_decisions": n_dec,
           "n_sessions": int(sess["date"].nunique()),
           "anchor_stability": stability, "band_coverage": band_cov,
           "raw_fire_rate": raw_rate, "k": k, "matched_fire_rate": matched_rate,
           "n_signals": len(sig)}

    for emb in (0, 1):
        fw = M.forward(sig, o, c, lo, horizons, emb, length)
        for h in horizons:
            col = f"fwd_{h}"
            x = fw[["date", col, "bw"]].dropna()
            if x.empty:
                continue
            norm = (x[col] / x["bw"]).to_numpy()
            res[f"e{emb}_h{h}_n"] = int(len(x))
            res[f"e{emb}_h{h}_mean_bw"] = float(norm.mean())
            res[f"e{emb}_h{h}_t"] = M.cluster_t(norm, x["date"].to_numpy())
        # keep the primary-cell rows so pairs can be pooled with a shared cluster
        if emb == PRIMARY_EMBARGO:
            col = f"fwd_{PRIMARY_H}"
            x = fw[["date", col, "bw"]].dropna()
            res["_rows"] = pd.DataFrame({"date": x["date"].to_numpy(),
                                         "norm": (x[col] / x["bw"]).to_numpy()})
    return res


def run_family(inst_list, structural, incumbent, label, emit,
               length=A.SESSION_LENGTH):
    """Sweep the 24-anchor placebo family plus the structural anchors.

    `length` is the session length in minutes. Holding it at 1,425 makes every
    anchor an all-hours session; running the NQ control at its NATIVE 390 keeps
    the decision universe the size the construct was built for. The placebo
    family at length=390 is simply 24 different 6.5-hour windows, one starting
    each hour, so the anchor is still the only swept variable.
    """
    family = A.placebo_family() + [a for a in structural
                                   if a.name not in {x.name for x in A.placebo_family()}]

    loaded = {}
    for inst in inst_list:
        prices, prov = A.load_prices(inst)
        if inst == "NQ" and "is_roll" in prices.columns:
            roll_min = frozenset(A.utc_minutes(pd.to_datetime(
                prices.loc[prices["is_roll"].astype(bool), "ts_utc"], utc=True)).tolist())
        else:
            roll_min = frozenset()
        loaded[inst] = (prices, M.dense_by_minute(
            prices.assign(utc_min=A.utc_minutes(
                pd.to_datetime(prices["ts_utc"], utc=True)))), prov, roll_min)
        emit(f"  loaded {inst:<7s} rows={len(prices):>9,d}  {prov}")

    # --- target fire rate: the incumbent anchor's own raw k=1 rate -----------
    inc = [a for a in family if a.name == incumbent][0]
    raws = []
    for inst in inst_list:
        prices, dense, _, rollm = loaded[inst]
        r = cell(prices, dense, inc, PRIMARY_GATE, None, HORIZONS, rollm, length)
        if r:
            raws.append(r["raw_fire_rate"])
    target = float(np.median(raws))
    emit(f"  target fire rate = median raw k=1 rate at {incumbent} = {target:.4f}")
    emit("")

    rows, pooled = [], []
    for anchor in family:
        per_pair, pool_rows = [], []
        for inst in inst_list:
            prices, dense, _, rollm = loaded[inst]
            r = cell(prices, dense, anchor, PRIMARY_GATE, target, HORIZONS, rollm,
                     length)
            if r is None:
                continue
            pr = r.pop("_rows", None)
            r["inst"] = inst
            r["length"] = length
            per_pair.append(r)
            rows.append(r)
            if pr is not None and len(pr):
                pool_rows.append(pr)
        if not per_pair:
            continue

        pk = f"e{PRIMARY_EMBARGO}_h{PRIMARY_H}"
        means = [p.get(f"{pk}_mean_bw", np.nan) for p in per_pair]
        means = [m for m in means if np.isfinite(m)]
        if pool_rows:
            allr = pd.concat(pool_rows, ignore_index=True)
            pm = float(allr["norm"].mean())
            pt = M.cluster_t(allr["norm"].to_numpy(), allr["date"].to_numpy())
            n = len(allr)
        else:
            pm, pt, n = np.nan, np.nan, 0
        same = max(sum(1 for m in means if m > 0), sum(1 for m in means if m < 0))
        pooled.append(dict(
            anchor=anchor.name, tz=anchor.tz,
            hhmm=f"{anchor.hour:02d}:{anchor.minute:02d}",
            structural=anchor.structural, family=label, length=length,
            n_signals=n, pooled_mean_bw=pm, pooled_t=pt, abs_pooled_t=abs(pt),
            n_same_sign=same, n_units=len(means),
            min_anchor_stability=float(np.min([p["anchor_stability"] for p in per_pair])),
            min_band_coverage=float(np.min([p["band_coverage"] for p in per_pair])),
            mean_matched_rate=float(np.mean([p["matched_fire_rate"] for p in per_pair])),
            k_range=f"{min(p['k'] for p in per_pair):.2f}-{max(p['k'] for p in per_pair):.2f}"))
        emit(f"    {anchor.name:<9s} {anchor.hhmm if hasattr(anchor,'hhmm') else '':<0s}"
             f"{f'{anchor.hour:02d}:{anchor.minute:02d}':<7s}"
             f"{anchor.tz:<20s} n={n:>7,d} mean/bw={pm:+.5f} t={pt:+6.2f} "
             f"sign {same}/{len(means)} stab={pooled[-1]['min_anchor_stability']:.3f}"
             + ("   <-- STRUCTURAL" if anchor.structural else ""))
    return pd.DataFrame(rows), pd.DataFrame(pooled)


def verdict(pool: pd.DataFrame, label: str, emit) -> dict:
    """The preregistered three-criterion kill test (HYP-0003)."""
    placebo_all = pool[~pool["structural"]]
    struct = pool[pool["structural"]]

    # A placebo whose t is NaN has NO usable statistic (small-cluster guard). It
    # must be DROPPED and counted, never left in: `NaN >= real` is False, so it
    # would silently count as "did not beat the real anchor" and make the test
    # easier to pass (LEARNINGS section 5).
    usable = np.isfinite(placebo_all["abs_pooled_t"].to_numpy())
    placebo = placebo_all[usable]
    dropped = placebo_all[~usable]

    emit("")
    emit(f"  ## KILL TEST — {label}")
    emit(f"     placebo family: {len(placebo)} usable of {len(placebo_all)} anchors "
         f"({len(dropped)} dropped for an unusable t: "
         f"{', '.join(dropped['anchor'].tolist()) if len(dropped) else 'none'})")
    emit(f"     placebo |t|: median {placebo['abs_pooled_t'].median():.2f}, "
         f"p90 {placebo['abs_pooled_t'].quantile(0.90):.2f}, "
         f"max {placebo['abs_pooled_t'].max():.2f} "
         f"({placebo.loc[placebo['abs_pooled_t'].idxmax(), 'anchor']})")
    emit("")
    best, out = None, []
    for _, r in struct.sort_values("abs_pooled_t", ascending=False).iterrows():
        if not np.isfinite(r["abs_pooled_t"]):
            emit(f"     {r['anchor']:<9s} NO USABLE t (small-cluster guard) -> FAIL")
            out.append(dict(anchor=r["anchor"], abs_t=None, pass_all=False,
                            reason="unusable t"))
            continue
        frac = float((placebo["abs_pooled_t"] >= r["abs_pooled_t"]).mean())
        c1 = bool(r["abs_pooled_t"] >= 2.0)
        c2 = bool(r["n_same_sign"] >= 3) if r["n_units"] >= 4 else bool(r["n_same_sign"] >= 1)
        c3 = bool(frac <= 0.10)
        stab_ok = bool(r["min_anchor_stability"] >= 0.98)
        p = bool(c1 and c2 and c3 and stab_ok)
        out.append(dict(anchor=r["anchor"], abs_t=r["abs_pooled_t"],
                        mean_bw=r["pooled_mean_bw"], frac_placebo_ge=frac,
                        c1_t_ge_2=c1, c2_sign_consistent=c2, c3_beats_placebo_p90=c3,
                        anchor_stability_ok=stab_ok, pass_all=p))
        emit(f"     {r['anchor']:<9s} |t|={r['abs_pooled_t']:5.2f}  "
             f"mean/bw={r['pooled_mean_bw']:+.5f}  frac(placebo>=)={frac:.3f}  "
             f"sign {int(r['n_same_sign'])}/{int(r['n_units'])}  stab={r['min_anchor_stability']:.3f}  "
             f"[1:{'P' if c1 else 'F'} 2:{'P' if c2 else 'F'} 3:{'P' if c3 else 'F'}] "
             f"-> {'PASS' if p else 'FAIL'}")
        if best is None or p:
            best = p if best is None else (best or p)
    passed = any(o["pass_all"] for o in out)
    emit(f"     {label} VERDICT: {'PASS' if passed else 'FAIL'}")
    return dict(label=label, passed=passed, criteria=out,
                n_placebo_usable=int(len(placebo)),
                n_placebo_dropped=int(len(dropped)),
                dropped_anchors=dropped["anchor"].tolist(),
                placebo_median_abs_t=float(placebo["abs_pooled_t"].median()),
                placebo_p90_abs_t=float(placebo["abs_pooled_t"].quantile(0.90)),
                placebo_max_abs_t=float(placebo["abs_pooled_t"].max()))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines = []

    def emit(s=""):
        lines.append(s)
        print(s, flush=True)

    emit("=" * 110)
    emit("HYP-0003 / EXP-0003 — session-ANCHOR sweep. Is the FX Noise-Area failure")
    emit("caused by an arbitrary anchor? 24 hourly ET placebos + structural anchors.")
    emit("=" * 110)
    emit(f"  primary cell: gate={PRIMARY_GATE}, h={PRIMARY_H}min, embargo={PRIMARY_EMBARGO} "
         f"(fill at open[t+2]), matched fire rate, session-clustered t")
    emit(f"  session length {A.SESSION_LENGTH} min, lookback {A.LOOKBACK}, "
         f"decision clock ET :29/:59")
    emit("")

    emit("## POSITIVE CONTROL A — NQ at its NATIVE 390-min RTH session length")
    emit("   (the length the construct was built for; 09:30 ET is the real open)")
    nq390_rows, nq390_pool = run_family(["NQ"], A.NQ_STRUCTURAL, NQ_INCUMBENT,
                                        "NQ@390", emit, length=390)
    v_nq390 = verdict(nq390_pool, "NQ positive control @390 (VALIDITY GATE)", emit)

    emit("")
    emit("## POSITIVE CONTROL B — NQ forced to the 1425-min all-hours length")
    emit("   (isolates whether SESSION LENGTH, not the anchor, is what carries NQ)")
    nq_rows, nq_pool = run_family(["NQ"], A.NQ_STRUCTURAL, NQ_INCUMBENT,
                                  "NQ@1425", emit, length=A.SESSION_LENGTH)
    v_nq = verdict(nq_pool, "NQ positive control @1425", emit)

    emit("")
    emit("## FX A — four USD majors, 1425-min all-hours session (fxday-comparable)")
    fx_rows, fx_pool = run_family(list(A.PAIRS), A.FX_STRUCTURAL, FX_INCUMBENT,
                                  "FX@1425", emit, length=A.SESSION_LENGTH)
    v_fx = verdict(fx_pool, "FX anchor hypothesis @1425", emit)

    emit("")
    emit("## FX B — four USD majors at 390 min, matched to the NQ control length")
    fx390_rows, fx390_pool = run_family(list(A.PAIRS), A.FX_STRUCTURAL, FX_INCUMBENT,
                                        "FX@390", emit, length=390)
    v_fx390 = verdict(fx390_pool, "FX anchor hypothesis @390", emit)

    pd.concat([nq390_rows, nq_rows, fx_rows, fx390_rows],
              ignore_index=True).to_csv(OUT / "cells.csv", index=False)
    pd.concat([nq390_pool, nq_pool, fx_pool, fx390_pool],
              ignore_index=True).to_csv(OUT / "pooled.csv", index=False)

    emit("")
    emit("=" * 110)
    fx_passed = v_fx["passed"] or v_fx390["passed"]
    if not v_nq390["passed"]:
        final = ("INCONCLUSIVE — the positive control FAILED at NQ's own native session "
                 "length, so this diagnostic is not shown to detect a known-real anchor "
                 "and the FX arms carry no information about FX (HYP-0003 validity gate). "
                 "The METHOD is the thing to fix, not FX.")
    elif fx_passed:
        final = ("HYP-0003 SUPPORTED — a structural FX anchor carries entry information "
                 "beyond its placebo family, at a length where the control is valid.")
    else:
        final = ("HYP-0003 REJECTED — the control detects NQ's real anchor, and no "
                 "structural FX anchor beats its placebo family. The anchor was NOT the "
                 "binding constraint; the Noise-Area family is closed for spot FX.")
    emit("  FINAL: " + final)
    emit("=" * 110)

    json.dump(dict(primary=dict(gate=PRIMARY_GATE, horizon=PRIMARY_H,
                                embargo=PRIMARY_EMBARGO),
                   nq_control_390=v_nq390, nq_control_1425=v_nq,
                   fx_1425=v_fx, fx_390=v_fx390, final=final),
              open(OUT / "summary.json", "w"), indent=2, default=str)
    (OUT / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
