"""Directional-EFFICIENCY conditioner screen (KER / ADX / HTF slope).

Frozen in RSI_EFFICIENCY_GATE_SPEC.md. Gates the |z| >= 1.5 fade on LOW directional
efficiency (choppy = reversion-friendly) and scores every arm as EXCESS mean R over
the |z| frontier interpolated to its own signals/year -- an arm ON the frontier
added nothing but selectivity. The engine is identical to the confirmed regime
matrix (event clock, non-overlap, 2R stop, 1-pip slippage, 30-min horizon), so the
only moving part vs the regime family is the conditioning variable.

Primary: median excess R at delay 1, >= +0.005 R AND >= 3/4 pairs. Directional kill:
LOW efficiency must beat its HIGH-efficiency mirror. Risk unit reported so a win by
volatility selection (not efficiency) is visible.

Reproduce:
    python -u _run_rsi_efficiency_gate.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _efficiency_features import add_efficiency_features
from _rsi_stop_engine import (
    BASE_K,
    HORIZON,
    build_features,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    years_of,
)
from _run_rsi_z_regime_matrix import Z_GRID, add_excess
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_efficiency_gate_results.json"
CSV = ROOT / "rsi_efficiency_gate.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
KEEPS = [0.40, 0.20, 0.10]


def low_cut(f, col, keep):
    """Early-era-fitted LOW-side cutpoint: gate f[col] <= cut keeps the bottom `keep`."""
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(keep)) if len(s) else np.nan


def high_cut(f, col, keep):
    """Early-era-fitted HIGH-side cutpoint: gate f[col] >= cut keeps the top `keep`."""
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(1 - keep)) if len(s) else np.nan


def build_arms(f):
    """(label, family, cond, side) for the frontier and every gate arm."""
    z = f.z
    zl, zs = z.le(-BASE_K), z.ge(BASE_K)
    out = []

    def add(label, family, long_c, short_c):
        cond = (long_c | short_c).fillna(False).to_numpy()
        side = np.where(long_c.fillna(False), 1.0,
                        np.where(short_c.fillna(False), -1.0, 0.0))
        out.append((label, family, cond, side))

    # reference frontier
    for k in Z_GRID:
        add(f"z {k}", "frontier |z|", z.le(-k), z.ge(k))

    # LOW / HIGH efficiency gates on the z1.5 base (slot-z normalised)
    for col, tag in [("ker_z", "ker"), ("adx_z", "adx")]:
        for keep in KEEPS:
            lc = f[col].le(low_cut(f, col, keep))
            hc = f[col].ge(high_cut(f, col, keep))
            add(f"low_{tag}_z {int(keep*100)}", "low_eff", zl & lc, zs & lc)
            add(f"high_{tag}_z {int(keep*100)}", "high_eff", zl & hc, zs & hc)

    # raw-KER low-side cut (transparency contrast, NOT the primary)
    for keep in KEEPS:
        rc = f.ker.le(low_cut(f, "ker", keep))
        add(f"low_ker_raw {int(keep*100)}", "raw_contrast", zl & rc, zs & rc)

    # HTF slope: fade WITH vs AGAINST the 120-min trend (side-specific)
    up, dn = f.htf_slope.gt(0), f.htf_slope.lt(0)
    add("withtrend", "htf", zl & up, zs & dn)         # buy dip in uptrend / sell rip in downtrend
    add("countertrend", "htf", zl & dn, zs & up)      # mirror control

    # combined: do the two independent axes stack?
    ker20 = f.ker_z.le(low_cut(f, "ker_z", 0.20))
    adx20 = f.adx_z.le(low_cut(f, "adx_z", 0.20))
    add("low_ker_z20 AND low_adx_z20", "combined", zl & ker20 & adx20, zs & ker20 & adx20)
    return out


def coverage(f):
    """Among base z1.5 crossings, is the KER/ADX definition time-of-day selective?"""
    cond = (f.z.le(-BASE_K) | f.z.ge(BASE_K))
    idx = select_events(f, cond.fillna(False).to_numpy())
    d = f.iloc[idx]
    rows = {}
    for era in ["early", "late"]:
        m = d.era.eq(era)
        base = int(m.sum())
        ker_ok = d.loc[m, "ker_z"].notna()
        adx_ok = d.loc[m, "adx_z"].notna()
        rows[era] = {
            "base_signals": base,
            "ker_defined_frac": float(ker_ok.mean()),
            "adx_defined_frac": float(adx_ok.mean()),
            "median_smin_ker_defined": float(d.loc[m][ker_ok.values].session_minute.median()),
            "median_smin_ker_missing": float(d.loc[m][(~ker_ok).values].session_minute.median())
            if (~ker_ok).any() else np.nan,
        }
    return rows


def analyse(pair):
    f = add_efficiency_features(build_features(pair))
    arrays = ohlc_arrays(f)
    rows = []
    for label, family, cond, side_all in build_arms(f):
        idx = select_events(f, cond)
        if len(idx) < 300:
            continue
        d, paths = extract(f, arrays, idx)
        side = side_all[idx]
        years = years_of(d)
        for delay in (0, 1):
            pp = shift_paths(paths, delay)
            sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
            pnl, st, _ = simulate(pp, side, STOP_K * sg, HORIZON, SLIPPAGE)
            base = dict(pair=pair, arm=label, family=family, delay=delay, era="all")
            rows.append({**base, **metrics(pnl, sg, d.sdate.values, years, st)})
    return rows, coverage(f)


def main():
    rows, covs = [], {}
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, c = analyse(pair)
        rows.extend(r)
        covs[pair] = c

    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_pips"]))
    d1 = df.loc[df.delay.eq(1) & df.era.eq("all")]
    d0 = df.loc[df.delay.eq(0) & df.era.eq("all")]

    print("\n=== 0. Feature-coverage among base z1.5 signals (rule 9a) ===")
    for pair, c in covs.items():
        for era, r in c.items():
            print(f"   {pair} {era:5s}: n={r['base_signals']:5d}  ker {r['ker_defined_frac']:.3f}  "
                  f"adx {r['adx_defined_frac']:.3f}  | median session-min defined "
                  f"{r['median_smin_ker_defined']:.0f} vs missing {r['median_smin_ker_missing']}")

    print("\n=== 1. |z| reference frontier (median across pairs), delay 1, 2R + 1 pip ===")
    fr = d1.loc[d1.family.eq("frontier |z|")]
    print(fr.groupby("arm").agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
        cluster_t=("cluster_t", "median"), hit=("hit_rate", "median"),
    ).reindex([f"z {k}" for k in Z_GRID]).round(3).to_string())

    print("\n=== 2. Gate arms: excess over the |z| frontier at matched rate (delay 1) ===")
    g = d1.loc[~d1.family.eq("frontier |z|")]
    tbl = g.groupby("arm").agg(
        family=("family", "first"),
        per_year=("signals_per_year", "median"), gross_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), frontier_R=("frontier_R", "median"),
        excess_R=("excess_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
        cluster_t=("cluster_t", "median"), hit=("hit_rate", "median"),
    ).sort_values("excess_R", ascending=False)
    print(tbl.round(4).to_string())

    print("\n=== 3. DIRECTIONAL KILL: LOW vs HIGH efficiency (median excess R, delay 1) ===")
    for tag in ["ker", "adx"]:
        for keep in KEEPS:
            lo = g.loc[g.arm.eq(f"low_{tag}_z {int(keep*100)}"), "excess_R"].median()
            hi = g.loc[g.arm.eq(f"high_{tag}_z {int(keep*100)}"), "excess_R"].median()
            verdict = "LOW wins (thesis)" if lo > hi else "HIGH wins (thesis FALSIFIED)"
            print(f"   {tag} keep {int(keep*100):>2}%: low {lo:+.4f}  high {hi:+.4f}  -> {verdict}")
    wt = g.loc[g.arm.eq("withtrend"), "excess_R"].median()
    ct = g.loc[g.arm.eq("countertrend"), "excess_R"].median()
    print(f"   htf slope: withtrend {wt:+.4f}  countertrend {ct:+.4f}  -> "
          f"{'with-trend better' if wt > ct else 'counter-trend better'}")

    print("\n=== 4. KILL TEST per arm (delay 1 primary; delay 0 shown) ===")
    print("   SUPPORTED >= +0.005 R median AND >=3/4 pairs positive")
    verdict = {}
    for arm, grp in g.groupby("arm"):
        w = grp.set_index("pair").excess_R
        med, npos = float(w.median()), int((w >= 0.005).sum())
        med_d0 = float(d0.loc[d0.arm.eq(arm)].excess_R.median()) if len(d0.loc[d0.arm.eq(arm)]) else np.nan
        if med >= 0.005 and npos >= 3:
            status = "SUPPORTED" if med_d0 > 0 else "supported-but-fragile(delay0<=0)"
        elif med <= -0.005:
            status = "REJECTED (worse than frontier)"
        else:
            status = "REJECTED (selectivity dial)"
        verdict[arm] = {"median_excess_R": med, "pairs_ge_0.005": npos,
                        "median_excess_delay0": med_d0, "status": status,
                        "per_pair": {k: float(v) for k, v in w.items()}}
        print(f"   {arm:28s} excess {med:+.4f} R  {npos}/4  | delay0 {med_d0:+.4f}  -> {status}")

    print("\n=== 5. Per-pair excess R, primary low-efficiency arms (delay 1) ===")
    key = [f"low_ker_z {int(k*100)}" for k in KEEPS] + \
          [f"low_adx_z {int(k*100)}" for k in KEEPS] + \
          ["withtrend", "low_ker_z20 AND low_adx_z20"]
    p = g.loc[g.arm.isin(key)].pivot_table(index="arm", columns="pair", values="excess_R")
    print(p.reindex([k for k in key if k in p.index]).round(4).to_string())

    any_supported = any(v["status"].startswith("SUPPORTED") for v in verdict.values())
    print(f"\n   >>> Any arm SUPPORTED at delay 1: {any_supported} "
          f"(if False, no claim-matched null is warranted)")

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_EFFICIENCY_GATE_SPEC.md",
            "pairs": PAIRS, "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "horizon": HORIZON, "z_grid": Z_GRID, "keeps": KEEPS,
            "primary_metric": ("mean R excess over the |z| frontier interpolated in "
                               "log signals/year to the arm's own rate, delay 1"),
            "directional_kill": "LOW efficiency must beat HIGH efficiency mirror",
        },
        "coverage": covs,
        "verdicts": verdict,
        "any_supported_delay1": bool(any_supported),
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
