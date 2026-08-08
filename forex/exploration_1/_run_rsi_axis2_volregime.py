"""Axis 2 (volatility regime) conviction filters on the SESSION-TWAP baseline.

Baseline promoted 2026-08-07: fade displacement from the SESSION TWAP
(same-slot-normalised z_twap), event clock, non-overlap, horizon-scaled 3R stop,
240-min hold. Depth (|z_twap|) is the baseline's own conviction lever and already
raises pips/trade, so every vol-regime gate is scored as EXCESS mean R over the
|z_twap| >= k depth frontier interpolated in log(signals/year) to the gate's own
rate. A gate that only sits on the frontier reduced trade count without adding
conviction -- it must BEAT going deeper on z_twap.

Features (causal, decision-time):
  rv30_pct   same-slot percentile of trailing 30-min realised vol   (relative)
  rv5_pct    same-slot percentile of trailing 5-min realised vol    (relative)
  vei_atr_z  same-slot z of ATR(14)/ATR(50) -- vol EXPANSION         (relative)
  abs_sigma  trailing 30-min sigma in PIPS, early-era global cut     (ABSOLUTE;
             the lever MEMORY flagged best for cost economics; per-slot CV is
             expected high BY DESIGN and reported, not hidden)
  combined   rv30 hi AND vei hi (the confirmed EMA-baseline survivor)

Relative features run BOTH hi and lo (no post-hoc flip); the project's prior
finding is reversion is stronger in HIGH vol, tested here on the new baseline.
Both exits (time, target). Delay 0 and 1. Per-slot selection-rate CV reported.
Consumed history; 2024+ sealed. Screen (rule 26); a survivor earns a null next.

Reproduce:  python -u _run_rsi_axis2_volregime.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    build_features,
    exact_roll,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    slot_pct,
    years_of,
)
from _run_rsi_exit_horizon import (
    EXTRA,
    HORIZON,
    SCALE,
    SLIPPAGE,
    STOP_K,
    Z_GRID,
    target_exit_idx,
)
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_axis2_volregime_results.json"
CSV = ROOT / "rsi_axis2_volregime.csv"

BASE_K = 1.5
KEEPS = [0.40, 0.20, 0.10]


def add_vol_features(f):
    time = f.time
    one = time.diff().eq(pd.Timedelta(minutes=1))
    logc = pd.Series(np.log(f.close.astype(float)), index=f.index)
    ret1 = logc.diff().where(one)
    f["rv_5m"] = np.sqrt(exact_roll(ret1.pow(2), time, 5, "sum"))
    f["rv5_pct"] = slot_pct(f, "rv_5m")
    f["rv30_pct"] = f.vol_pct                       # same-slot RV(30) percentile
    f["abs_sigma_pips"] = f.rv_30m * 1e4 * f.close.astype(float)
    return f


def early_q(f, col, q):
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(q)) if len(s) else np.nan


def slot_cv(f, base_cond, gate):
    mm = base_cond & f.z_twap.notna()
    d = pd.DataFrame({"slot": f.session_minute[mm], "p": gate[mm].astype(float)})
    r = d.groupby("slot")["p"].mean()
    r = r[d.groupby("slot")["p"].size() >= 30]
    return float(r.std() / r.mean()) if r.mean() else np.nan


def build_arms(f):
    z = f.z_twap
    zl, zs = z.le(-BASE_K), z.ge(BASE_K)
    base = (zl | zs).fillna(False)
    arms, cvs = [], {}

    def add(label, family, cond, direction=""):
        cond = cond.fillna(False)
        arms.append((label, family, cond.to_numpy(),
                     np.where(cond & zl.fillna(False), 1.0,
                              np.where(cond & zs.fillna(False), -1.0, 0.0)),
                     direction))

    for k in Z_GRID:
        add(f"z {k}", "frontier |z|", f.z_twap.le(-k) | f.z_twap.ge(k))

    def cut_gate(colname, keep, side):
        q = early_q(f, colname, 1 - keep if side == "hi" else keep)
        return (f[colname].ge(q) if side == "hi" else f[colname].le(q))

    gates = {}
    for name, colname in [("rv30", "rv30_pct"), ("rv5", "rv5_pct"), ("vei", "vei_atr_z")]:
        for keep in KEEPS:
            for side in ("hi", "lo"):
                g = cut_gate(colname, keep, side)
                add(f"{name} {side} {int(keep*100)}", "regime", base & g, side)
                gates[(name, keep, side)] = g
                if keep == 0.20:
                    cvs[f"{name}_{side}"] = slot_cv(f, base, g)

    for keep in KEEPS:
        g = cut_gate("abs_sigma_pips", keep, "hi")
        add(f"abs_sigma hi {int(keep*100)}", "regime", base & g, "hi")
        if keep == 0.20:
            cvs["abs_sigma_hi"] = slot_cv(f, base, g)

    for keep in KEEPS:
        g = gates[("rv30", keep, "hi")] & gates[("vei", keep, "hi")]
        add(f"rv30&vei hi {int(keep*100)}", "regime", base & g, "hi")

    return arms, base.to_numpy(), cvs


def run_arm(f, arrays, cond, side_all, zp_col):
    idx = select_events(f, cond, horizon=HORIZON)
    if len(idx) < 200:
        return []
    d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
    side = side_all[idx]
    take = (idx[:, None] + 1) + np.arange(HORIZON + 1 + EXTRA)[None, :]
    zp_full = zp_col[take]
    rv_at = f.rv_30m.to_numpy()[idx]
    years = years_of(d)
    rows = []
    for delay in (0, 1):
        pp = shift_paths(paths, delay, horizon=HORIZON)
        zp = zp_full[:, delay:delay + HORIZON + 1]
        entry = pp["open"][:, 0]
        sgH = rv_at * SCALE * 1e4 * entry
        stop = STOP_K * sgH
        pnl_t, st_t, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)
        ex, _ = target_exit_idx(zp, side, HORIZON)
        pnl_g, st_g, _ = simulate(pp, side, stop, ex, SLIPPAGE)
        for exit_name, pnl, st in [("time", pnl_t, st_t), ("target", pnl_g, st_g)]:
            m0 = {"exit": exit_name, "delay": delay, "era": "all"}
            rows.append({**m0, **metrics(pnl, sgH, d.sdate.values, years, st)})
            if delay == 0:
                for era in ("early", "late"):
                    mask = d.era.eq(era).to_numpy()
                    yrs = max(d.loc[mask].sdate.nunique() / 252, 1e-9)
                    rows.append({"exit": exit_name, "delay": 0, "era": era,
                                 **metrics(pnl[mask], sgH[mask], d.sdate.values[mask],
                                           yrs, st[mask])})
    return rows


def add_excess(df):
    df = df.copy()
    df["excess_R"] = np.nan
    df["clamped"] = False
    for (exit_name, delay, era), grp in df.groupby(["exit", "delay", "era"], observed=True):
        fr = grp.loc[grp.family.eq("frontier |z|")].dropna(subset=["mean_R"]).sort_values(
            "signals_per_year")
        if len(fr) < 3:
            continue
        x, y = np.log(fr.signals_per_year.values), fr.mean_R.values
        rate = np.log(grp.signals_per_year.values)
        df.loc[grp.index, "excess_R"] = grp.mean_R.values - np.interp(rate, x, y)
        df.loc[grp.index, "clamped"] = (rate < x.min()) | (rate > x.max())
    return df


def analyse(pair):
    f = add_vol_features(add_twap_z(build_features(pair)))
    arrays = ohlc_arrays(f)
    arms, base_cond, cvs = build_arms(f)
    zp_col = f.z_twap.to_numpy()
    rows = []
    for label, family, cond, side_all, direction in arms:
        for r in run_arm(f, arrays, cond, side_all, zp_col):
            rows.append({"pair": pair, "arm": label, "family": family,
                         "direction": direction, **r})
    return rows, {"pair": pair, **cvs}


def main():
    rows, cvrows = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, c = analyse(pair)
        rows.extend(r)
        cvrows.append(c)
    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_R"]))

    print("\n=== Per-slot selection-rate CV of vol gates (keep 20%) ===")
    print("   (abs_sigma is an ABSOLUTE selector, high CV expected by design)")
    print(pd.DataFrame(cvrows).round(3).to_string(index=False))

    for exit_name in ("time", "target"):
        m0 = df[(df.exit == exit_name) & (df.delay == 0) & (df.era == "all")]
        print(f"\n=== |z_twap| frontier, {exit_name} exit, d0 (median) ===")
        fr = m0[m0.family.eq("frontier |z|")]
        print(fr.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), t=("cluster_t", "median"),
        ).reindex([f"z {k}" for k in Z_GRID]).round(4).to_string())

        print(f"\n=== Vol-regime gates on |z_twap|>=1.5, {exit_name} exit, d0 (median) ===")
        s = m0[m0.family.eq("regime")]
        print(s.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), excess_R=("excess_R", "median"),
            t=("cluster_t", "median"), clamped=("clamped", "max"),
        ).round(4).to_string())

    print("\n=== KILL TEST (time exit): excess>=+0.005 R, >=3/4 pairs, delay1+late ===")
    verdict = {}
    for arm, grp in df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
                       & df.family.eq("regime")].groupby("arm"):
        w = grp.set_index("pair").excess_R
        med, npos = float(w.median()), int((w >= 0.005).sum())
        d1 = df[(df.arm == arm) & (df.exit == "time") & (df.delay == 1) & (df.era == "all")]
        late = df[(df.arm == arm) & (df.exit == "time") & (df.delay == 0) & (df.era == "late")]
        md1 = float(d1.excess_R.median()) if len(d1) else np.nan
        mlate = float(late.excess_R.median()) if len(late) else np.nan
        clamped = bool(grp.clamped.max())
        if med >= 0.005 and npos >= 3 and not clamped:
            status = "SUPPORTED" if (md1 > 0 and mlate > 0) else "fragile"
        elif med <= -0.005:
            status = "REJECTED (worse than frontier)"
        else:
            status = "REJECTED (dial)"
        if clamped and "REJECTED" not in status:
            status += " [CLAMPED]"
        verdict[arm] = {"median_excess_R": med, "pairs_ge_0.005": npos,
                        "delay1": md1, "late": mlate, "status": status,
                        "per_pair": {k: float(v) for k, v in w.items()}}
        print(f"   {arm:16s} excess {med:+.4f} R  {npos}/4  | d1 {md1:+.4f} "
              f"| late {mlate:+.4f}  -> {status}")

    print("\n=== Per-pair excess (time exit, d0): key arms ===")
    key = ["rv30 hi 20", "rv5 hi 20", "vei hi 20", "abs_sigma hi 20", "rv30&vei hi 20",
           "rv30 hi 10", "abs_sigma hi 10", "rv30&vei hi 10"]
    p = df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
           & df.arm.isin(key)].pivot_table(index="arm", columns="pair", values="excess_R")
    print(p.reindex([k for k in key if k in p.index]).round(4).to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "baseline": "session-TWAP z_twap, horizon-scaled 3R stop, 240m hold",
            "primary_metric": "excess mean R over the |z_twap| frontier at matched rate",
            "pairs": PAIRS, "z_grid": Z_GRID, "keeps": KEEPS, "base_k": BASE_K,
        },
        "slot_cv": cvrows, "verdicts": verdict,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
