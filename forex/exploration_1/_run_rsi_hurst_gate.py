"""Hurst-exponent regime conditioner screen for the |z| >= 1.5 fade.

Frozen in RSI_HURST_GATE_SPEC.md. Gates the fade on the recent path's persistence
regime (fixed-window generalized Hurst, same-slot z-scored) and scores every arm as
EXCESS mean R over the |z| frontier at its own signals/year. Both LOW and HIGH Hurst
sides are run; the directional kill decides. A redundancy PREVIEW (Spearman of hurst_z
with the ADX/KER directional axis and the vol-gate features) is reported inline, because
Hurst is a priori close to that axis. Engine identical to the confirmed regime matrix
(event clock, non-overlap, 2R stop, 1-pip slippage, 30-min horizon).

Screen only: an arm is SUPPORTED iff median excess >= +0.005 R AND >= 3/4 pairs at
delay 1. Survivors go to a separate step-2 null + full redundancy run; if none survive,
NO-GO.

Reproduce:
    python -u _run_rsi_hurst_gate.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

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
from _hurst_feature import add_hurst_features
from _efficiency_features import add_efficiency_features
from _run_rsi_z_regime_matrix import Z_GRID, add_extra_features, early_cut
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_hurst_gate_results.json"
CSV = ROOT / "rsi_hurst_gate.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
KEEPS = [0.40, 0.20, 0.10]


def low_cut(f, col, keep):
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(keep)) if len(s) else np.nan


def high_cut(f, col, keep):
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(1 - keep)) if len(s) else np.nan


def frontier_of(f, arrays, delay):
    xs, ys = [], []
    for k in Z_GRID:
        zl, zs = f.z.le(-k), f.z.ge(k)
        cond = (zl | zs).fillna(False).to_numpy()
        side = np.where(zl.fillna(False), 1.0, np.where(zs.fillna(False), -1.0, 0.0))
        idx = select_events(f, cond)
        d, paths = extract(f, arrays, idx)
        pp = shift_paths(paths, delay)
        sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
        pnl, st, _ = simulate(pp, side[idx], STOP_K * sg, HORIZON, SLIPPAGE)
        m = metrics(pnl, sg, d.sdate.values, years_of(d), st)
        xs.append(np.log(m["signals_per_year"]))
        ys.append(m["mean_R"])
    o = np.argsort(xs)
    return np.asarray(xs)[o], np.asarray(ys)[o]


def build_arms(f):
    z = f.z
    zl, zs = z.le(-BASE_K), z.ge(BASE_K)
    out = []

    def add(label, family, long_c, short_c):
        cond = (long_c | short_c).fillna(False).to_numpy()
        side = np.where(long_c.fillna(False), 1.0,
                        np.where(short_c.fillna(False), -1.0, 0.0))
        out.append((label, family, cond, side))

    for k in Z_GRID:
        add(f"z {k}", "frontier |z|", z.le(-k), z.ge(k))

    for keep in KEEPS:
        lc = f.hurst_z.le(low_cut(f, "hurst_z", keep))
        hc = f.hurst_z.ge(high_cut(f, "hurst_z", keep))
        add(f"low_hurst_z {int(keep*100)}", "low_hurst", zl & lc, zs & lc)
        add(f"high_hurst_z {int(keep*100)}", "high_hurst", zl & hc, zs & hc)

    for keep in KEEPS:
        rc = f.hurst.le(low_cut(f, "hurst", keep))
        add(f"low_hurst_raw {int(keep*100)}", "raw_contrast", zl & rc, zs & rc)
    return out


def evaluate(f, arrays, cond, side_all, delay, fx, fy):
    idx = select_events(f, cond)
    if len(idx) < 300:
        return None
    d, paths = extract(f, arrays, idx)
    pp = shift_paths(paths, delay)
    sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
    pnl, st, _ = simulate(pp, side_all[idx], STOP_K * sg, HORIZON, SLIPPAGE)
    m = metrics(pnl, sg, d.sdate.values, years_of(d), st)
    if "mean_R" not in m:
        return None
    m["excess_R"] = m["mean_R"] - float(np.interp(np.log(m["signals_per_year"]), fx, fy))
    return m


def coverage(f):
    cond = (f.z.le(-BASE_K) | f.z.ge(BASE_K)).fillna(False).to_numpy()
    d = f.iloc[select_events(f, cond)]
    return {era: {"n": int(d.era.eq(era).sum()),
                  "hurst_defined": float(d.loc[d.era.eq(era), "hurst_z"].notna().mean())}
            for era in ["early", "late"]}


def redundancy_preview(f):
    """Spearman of hurst_z with the directional axis and vol-gate features, traded rows."""
    zrows = f.loc[f.z.abs().ge(BASE_K).fillna(False)]
    return {c: float(zrows.hurst_z.corr(zrows[c], method="spearman"))
            for c in ["adx_z", "ker_z", "vei_atr_z", "rv30_pct"]}


def analyse(pair):
    f = add_hurst_features(add_efficiency_features(add_extra_features(build_features(pair))))
    arrays = ohlc_arrays(f)
    fx1, fy1 = frontier_of(f, arrays, 1)
    fx0, fy0 = frontier_of(f, arrays, 0)
    rows = []
    for label, family, cond, side in build_arms(f):
        for delay, fx, fy in [(1, fx1, fy1), (0, fx0, fy0)]:
            m = evaluate(f, arrays, cond, side, delay, fx, fy)
            if m is None:
                continue
            rows.append({"pair": pair, "arm": label, "family": family,
                         "delay": delay, **m})
    return rows, coverage(f), redundancy_preview(f)


def main():
    rows, covs, reds = [], {}, {}
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, c, rd = analyse(pair)
        rows.extend(r)
        covs[pair] = c
        reds[pair] = rd

    df = pd.DataFrame(rows)
    d1 = df.loc[df.delay.eq(1)]
    d0 = df.loc[df.delay.eq(0)]

    print("\n=== 0. hurst_z coverage among base |z|>=1.5 signals (rule 9a) ===")
    for pair, c in covs.items():
        for era, r in c.items():
            print(f"   {pair} {era:5s}: n={r['n']:6d}  hurst_z defined {r['hurst_defined']:.4f}")

    print("\n=== 1. Redundancy preview: Spearman(hurst_z, X) on traded rows ===")
    for pair, rd in reds.items():
        print(f"   {pair}: adx_z {rd['adx_z']:+.3f}  ker_z {rd['ker_z']:+.3f}  "
              f"vei_atr_z {rd['vei_atr_z']:+.3f}  rv30_pct {rd['rv30_pct']:+.3f}")

    print("\n=== 2. |z| frontier (median across pairs), delay 1 ===")
    fr = d1.loc[d1.family.eq("frontier |z|")]
    print(fr.groupby("arm").agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
        cluster_t=("cluster_t", "median"), hit=("hit_rate", "median"),
    ).reindex([f"z {k}" for k in Z_GRID]).round(3).to_string())

    print("\n=== 3. Gate arms: excess over the frontier at matched rate (delay 1) ===")
    g = d1.loc[~d1.family.eq("frontier |z|")]
    print(g.groupby("arm").agg(
        family=("family", "first"),
        per_year=("signals_per_year", "median"), gross_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), excess_R=("excess_R", "median"),
        risk_unit=("implied_risk_unit_pips", "median"), cluster_t=("cluster_t", "median"),
    ).sort_values("excess_R", ascending=False).round(4).to_string())

    print("\n=== 4. DIRECTIONAL KILL: LOW vs HIGH Hurst (median excess R, delay 1) ===")
    for keep in KEEPS:
        lo = g.loc[g.arm.eq(f"low_hurst_z {int(keep*100)}"), "excess_R"].median()
        hi = g.loc[g.arm.eq(f"high_hurst_z {int(keep*100)}"), "excess_R"].median()
        who = "LOW (classical)" if lo > hi else "HIGH (ADX-like)"
        print(f"   keep {int(keep*100):>2}%: low {lo:+.4f}  high {hi:+.4f}  -> {who} wins")

    print("\n=== 5. KILL TEST per arm (delay 1 primary; delay 0 shown) ===")
    print("   SUPPORTED >= +0.005 R median AND >=3/4 pairs positive")
    verdict = {}
    for arm, grp in g.groupby("arm"):
        w = grp.set_index("pair").excess_R
        med, npos = float(w.median()), int((w >= 0.005).sum())
        d0a = d0.loc[d0.arm.eq(arm)]
        med0 = float(d0a.excess_R.median()) if len(d0a) else np.nan
        if med >= 0.005 and npos >= 3:
            status = "SUPPORTED" if med0 > 0 else "supported-but-fragile(delay0<=0)"
        elif med <= -0.005:
            status = "REJECTED (worse than frontier)"
        else:
            status = "REJECTED (selectivity dial)"
        verdict[arm] = {"median_excess_R": med, "pairs_ge_0.005": npos,
                        "median_excess_delay0": med0, "status": status,
                        "per_pair": {k: float(v) for k, v in w.items()}}
        print(f"   {arm:22s} excess {med:+.4f} R  {npos}/4  | delay0 {med0:+.4f}  -> {status}")

    print("\n=== 6. Per-pair excess R, all Hurst gates (delay 1) ===")
    p = g.pivot_table(index="arm", columns="pair", values="excess_R")
    print(p.round(4).to_string())

    any_sup = any(v["status"].startswith("SUPPORTED") for v in verdict.values())
    print(f"\n   >>> Any arm SUPPORTED at delay 1: {any_sup}")
    print("   " + ("-> a survivor exists: run step-2 null + full redundancy" if any_sup
                   else "-> NO-GO: Hurst regime does not condition the fade beyond selectivity"))

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_HURST_GATE_SPEC.md", "pairs": PAIRS,
            "stop_R": STOP_K, "slippage_pips": SLIPPAGE, "keeps": KEEPS,
            "primary_metric": "excess mean R over the |z| frontier, delay 1",
        },
        "coverage": covs, "redundancy_preview": reds, "verdicts": verdict,
        "any_supported": bool(any_sup),
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
