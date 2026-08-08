"""Axis 1 (signal strength) conviction filters on a LONG (240-min) hold.

User request: reduce trade count to only the highest-conviction fades, and use a
longer hold (~4h) rather than the 30-minute horizon. This tests the Axis-1
dimensions that actually VARY at a fresh crossing on the event clock:

  - DEPTH        : |z| itself  -> the reference frontier every filter must beat.
  - VELOCITY     : how fast price punched to the extreme (Delta|z| over 5 min,
                   and the short-window thrust |r5|/rv5).
  - DECELERATION : is the last-minute move stalling relative to the recent 5-min
                   average (exhaustion), or still accelerating (regime change)?

FRESHNESS is intentionally NOT tested: the event engine fires on the first
minute the condition becomes true, so every trade is age-0 by construction and
time-in-zone cannot discriminate.

--- Preregistration (rule 24/26) ---------------------------------------------
Primary metric: mean R (pips / entry-time sigma) EXCESS over the |z| >= k
frontier, interpolated in log(signals/year) to each arm's own rate. An arm that
sits ON the frontier only traded less; it is a selectivity dial, not conviction.

Both directions of every feature are run. A direction is credited only if the
excess is >= +0.005 R median AND >= 3/4 pairs AND survives the one-minute entry
delay AND holds in the late (2021-2023) era. No post-hoc direction flip. This is
a SCREEN on consumed history (four correlated pairs ~ 2 effective); a survivor
earns a claim-matched null next, not deployment. 2024+ stays sealed.

Setup mirrors the project's 240-min work: event clock, non-overlap (cooldown =
horizon), compulsory 3R single-barrier stop, 1-pip adverse slippage, delay 0
and 1. Feature gates are cut on the EARLY era only and applied unchanged to the
late era. Per-slot selection-rate CV is reported so a gate acting as a
time-of-day clock is visible.

Reproduce:  python -u _run_rsi_axis1_conviction.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    BASE_K,
    COSTS,
    build_features,
    exact_roll,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    years_of,
)
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_axis1_conviction_results.json"
CSV = ROOT / "rsi_axis1_conviction.csv"

HORIZON = 240          # ~4-hour hold (user: previous studies found ~4h a good spot)
STOP_K = 3.0           # widest stop the prior 240m candidate used
SLIPPAGE = 1.0
Z_GRID = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
KEEPS = [0.40, 0.20, 0.10]
HORIZON_SENS = [120, 240, 360]   # base-only, to justify the 4h choice
MAXH = max([HORIZON] + HORIZON_SENS)


def add_axis1_features(f):
    """Causal decision-time signal-strength features on the full minute grid."""
    time = f.time
    one = time.diff().eq(pd.Timedelta(minutes=1))
    logc = pd.Series(np.log(f.close.astype(float)), index=f.index)
    ret1 = logc.diff().where(one)
    absret = ret1.abs()

    # penetration velocity: how much deeper |z| got over the last 5 contiguous min
    zabs = f.z.abs()
    zabs5 = zabs.shift(5).where(time.shift(5).eq(time - pd.Timedelta(minutes=5)))
    f["zvel5"] = zabs - zabs5

    # short-window directional thrust into the move: |r5| / trailing-5m realised vol
    r5 = (logc - logc.shift(5)).where(time.shift(5).eq(time - pd.Timedelta(minutes=5)))
    rv5 = np.sqrt(exact_roll(ret1.pow(2), time, 5, "sum"))
    f["thrust5"] = (r5.abs() / rv5.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    # deceleration / exhaustion: last-minute |return| vs the trailing 5-min mean.
    # <1 = stalling (exhaustion), >1 = still accelerating.
    mean5 = exact_roll(absret, time, 5, "mean")
    f["decel5"] = (absret / mean5.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    return f


FEATURES = ["zvel5", "thrust5", "decel5"]


def early_q(f, col, q):
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(q)) if len(s) else np.nan


def slot_cv(f, base_cond, gate):
    """CV across session-minutes of the fraction of base signals that pass `gate`.

    High CV = the gate fires at systematically different rates by time of day,
    i.e. it is partly a clock (LEARNINGS 2026-07-27). Low CV = calibrated.
    """
    m = base_cond & f.z.notna()
    d = pd.DataFrame({"slot": f.session_minute[m], "pass": gate[m].astype(float)})
    rate = d.groupby("slot")["pass"].mean()
    rate = rate[d.groupby("slot")["pass"].size() >= 30]
    return float(rate.std() / rate.mean()) if rate.mean() else np.nan


def build_arms(f):
    """(label, family, condition-bool, side-array, direction) for every arm."""
    z = f.z
    zl, zs = z.le(-BASE_K), z.ge(BASE_K)          # the |z|>=1.5 base fade
    base = zl | zs
    base_side = np.where(zl, 1.0, np.where(zs, -1.0, 0.0))

    arms = []

    def add(label, family, cond, direction=""):
        cond = cond.fillna(False)
        arms.append((label, family, cond.to_numpy(),
                     np.where(cond & zl, 1.0, np.where(cond & zs, -1.0, 0.0)),
                     direction))

    # reference frontier: plain |z| >= k
    for k in Z_GRID:
        add(f"z {k}", "frontier |z|", z.le(-k) | z.ge(k))

    # conviction gates: base AND feature in the hi/lo tail, cut on the early era
    cvs = {}
    for col in FEATURES:
        for keep in KEEPS:
            hi_cut = early_q(f, col, 1 - keep)
            lo_cut = early_q(f, col, keep)
            g_hi, g_lo = f[col].ge(hi_cut), f[col].le(lo_cut)
            add(f"{col} hi {int(keep*100)}", "conviction", base & g_hi, "hi")
            add(f"{col} lo {int(keep*100)}", "conviction", base & g_lo, "lo")
            if keep == 0.20:
                cvs[f"{col}_hi"] = slot_cv(f, base, g_hi)
                cvs[f"{col}_lo"] = slot_cv(f, base, g_lo)
    return arms, base.to_numpy(), base_side, cvs


def run_arm(f, arrays, cond, side_all, horizon, delays=(0, 1)):
    idx = select_events(f, cond, horizon=horizon)
    if len(idx) < 200:
        return []
    d, paths = extract(f, arrays, idx, horizon=horizon)
    side = side_all[idx]
    years = years_of(d)
    rows = []
    for delay in delays:
        pp = shift_paths(paths, delay, horizon=horizon)
        sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
        pnl, st, _ = simulate(pp, side, STOP_K * sg, horizon, SLIPPAGE)
        base = dict(delay=delay, era="all")
        rows.append({**base, **metrics(pnl, sg, d.sdate.values, years, st)})
        if delay == 0:
            for era in ("early", "late"):
                m = d.era.eq(era).to_numpy()
                yrs = max(d.loc[m].sdate.nunique() / 252, 1e-9)
                rows.append({"delay": 0, "era": era,
                             **metrics(pnl[m], sg[m], d.sdate.values[m], yrs, st[m])})
    return rows


def add_excess(df):
    df = df.copy()
    df["excess_R"] = np.nan
    df["frontier_R"] = np.nan
    df["clamped"] = False
    for (delay, era), grp in df.groupby(["delay", "era"], observed=True):
        fr = grp.loc[grp.family.eq("frontier |z|")].dropna(subset=["mean_R"])
        fr = fr.sort_values("signals_per_year")
        if len(fr) < 3:
            continue
        x, y = np.log(fr.signals_per_year.values), fr.mean_R.values
        rate = np.log(grp.signals_per_year.values)
        df.loc[grp.index, "frontier_R"] = np.interp(rate, x, y)
        df.loc[grp.index, "excess_R"] = grp.mean_R.values - np.interp(rate, x, y)
        df.loc[grp.index, "clamped"] = (rate < x.min()) | (rate > x.max())
    return df


def analyse(pair):
    f = add_axis1_features(build_features(pair))
    arrays = ohlc_arrays(f)
    arms, base_cond, base_side, cvs = build_arms(f)

    rows = []
    for label, family, cond, side_all, direction in arms:
        for r in run_arm(f, arrays, cond, side_all, HORIZON):
            rows.append({"pair": pair, "arm": label, "family": family,
                         "direction": direction, **r})

    # base-only horizon sensitivity (justify the 4h hold)
    sens = []
    for h in HORIZON_SENS:
        rr = run_arm(f, arrays, pd.Series(base_cond).fillna(False).to_numpy(),
                     base_side, h, delays=(0,))
        for r in rr:
            if r.get("era") == "all":
                sens.append({"pair": pair, "horizon": h,
                             "mean_R": r.get("mean_R"), "mean_pips": r.get("mean_pips"),
                             "signals_per_year": r.get("signals_per_year"),
                             "risk_unit": r.get("implied_risk_unit_pips"),
                             "cluster_t": r.get("cluster_t"),
                             "stopped_frac": r.get("stopped_frac")})
    return rows, sens, {"pair": pair, **cvs}


def main():
    rows, sens, cvrows = [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, s, c = analyse(pair)
        rows.extend(r)
        sens.extend(s)
        cvrows.append(c)

    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_R"]))
    main0 = df.loc[df.delay.eq(0) & df.era.eq("all")]

    print("\n=== 0. Base |z|>=1.5 horizon sensitivity (median across pairs, delay 0) ===")
    sdf = pd.DataFrame(sens)
    print(sdf.groupby("horizon").agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), risk_unit=("risk_unit", "median"),
        cluster_t=("cluster_t", "median"), stopped=("stopped_frac", "median"),
    ).round(4).to_string())

    print(f"\n=== 1. The |z| reference frontier @ {HORIZON}m, 3R stop (median) ===")
    fr = main0.loc[main0.family.eq("frontier |z|")]
    print(fr.groupby("arm").agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
        cluster_t=("cluster_t", "median"), hit=("hit_rate", "median"),
        stopped=("stopped_frac", "median"),
    ).reindex([f"z {k}" for k in Z_GRID]).round(3).to_string())

    print("\n=== 2. Per-slot selection-rate CV of the conviction gates (keep 20%) ===")
    print("   (high CV => the gate is partly a time-of-day clock)")
    print(pd.DataFrame(cvrows).round(3).to_string(index=False))

    print("\n=== 3. Conviction arms: excess mean R over the frontier at matched rate ===")
    conv = main0.loc[main0.family.eq("conviction")]
    tbl = conv.groupby(["arm", "direction"]).agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), frontier_R=("frontier_R", "median"),
        excess_R=("excess_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
        clamped=("clamped", "max"),
    ).round(4)
    print(tbl.to_string())

    print("\n=== 4. KILL TEST: excess >= +0.005 R, >=3/4 pairs, survives delay1 + late ===")
    verdict = {}
    for arm, grp in conv.groupby("arm"):
        w = grp.set_index("pair").excess_R
        med, npos = float(w.median()), int((w >= 0.005).sum())
        d1 = df.loc[df.arm.eq(arm) & df.delay.eq(1) & df.era.eq("all")]
        late = df.loc[df.arm.eq(arm) & df.delay.eq(0) & df.era.eq("late")]
        med_d1 = float(d1.excess_R.median()) if len(d1) else np.nan
        med_late = float(late.excess_R.median()) if len(late) else np.nan
        clamped = bool(grp.clamped.max())
        if med >= 0.005 and npos >= 3 and not clamped:
            status = "SUPPORTED" if (med_d1 > 0 and med_late > 0) else "fragile"
        elif med <= -0.005:
            status = "REJECTED (worse than frontier)"
        else:
            status = "REJECTED (dial)"
        if clamped and "REJECTED" not in status:
            status += " [CLAMPED-rate]"
        verdict[arm] = {"median_excess_R": med, "pairs_ge_0.005": npos,
                        "delay1": med_d1, "late": med_late, "clamped": clamped,
                        "status": status, "per_pair": {k: float(v) for k, v in w.items()}}
        print(f"   {arm:16s} excess {med:+.4f} R  {npos}/4  "
              f"| d1 {med_d1:+.4f} | late {med_late:+.4f}  -> {status}")

    print("\n=== 5. Per-pair excess, all conviction arms ===")
    p = conv.pivot_table(index="arm", columns="pair", values="excess_R")
    print(p.round(4).to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "inline docstring (Axis-1 conviction, long hold)",
            "pairs": PAIRS, "horizon_min": HORIZON, "stop_R": STOP_K,
            "slippage_pips": SLIPPAGE, "z_grid": Z_GRID, "keeps": KEEPS,
            "features": FEATURES, "costs_pips": COSTS,
            "primary_metric": "mean R excess over the |z| frontier at matched signals/year",
        },
        "slot_cv": cvrows,
        "horizon_sensitivity": sens,
        "verdicts": verdict,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
