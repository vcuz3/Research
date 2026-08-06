"""Workstream A (D1 + D2): net economics under a modelled, time-of-day cost.

Replaces the project's hypothetical flat-cost stress with the causal, hour/era/
volatility-conditioned round trip of `_cost_model.py`, and reports net mean R and
net pips overall, by UTC hour, and by era, for the current best cell and the
ungated base. Frozen in RSI_COST_HOUR_ECONOMICS_SPEC.md.

Reproduce:
    python -u _run_cost_hour_economics.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _cost_model import CostParams, round_trip_pips
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
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "cost_hour_economics_results.json"
CSV = ROOT / "cost_hour_economics_per_hour.csv"

STOP_K = 3.0          # widest sensible compulsory stop (established recommendation)
SLIPPAGE = 1.0
GATE_KEEP = 0.40
LIQUID_HOURS = list(range(7, 21))    # 07:00-20:00 UTC London/NY window
OVERLAP_HOURS = list(range(12, 17))  # 12:00-16:00 UTC overlap

SCENARIOS = {
    "optimistic": CostParams(scenario="optimistic"),
    "base": CostParams(scenario="base"),
    "pessimistic": CostParams(scenario="pessimistic"),
    "base_no_commission": CostParams(scenario="base", include_commission=False),
}


def early_cut(f, col, keep):
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(1 - keep)) if len(s) else np.nan


def arm_conditions(f):
    """(label, cond, side) for the best cell and the ungated base."""
    cut_vei = early_cut(f, "vei_atr_z", GATE_KEEP)
    cut_rv30 = early_cut(f, "vol_pct", GATE_KEEP)
    gate = f.vei_atr_z.ge(cut_vei) & f.vol_pct.ge(cut_rv30)
    zl, zs = f.z.le(-BASE_K), f.z.ge(BASE_K)

    arms = []
    for label, g in [("best_cell", gate), ("ungated_base", True)]:
        long_s = zl & g if g is not True else zl
        short_s = zs & g if g is not True else zs
        cond = (long_s | short_s).fillna(False).to_numpy()
        side = np.where(long_s.fillna(False), 1.0,
                        np.where(short_s.fillna(False), -1.0, 0.0))
        arms.append((label, cond, side))
    return arms, {"cut_vei": cut_vei, "cut_rv30": cut_rv30}


def trades_for_arm(f, arrays, cond, side_all, delay):
    """Return a per-trade frame with gross pips, sigma, entry hour/era for one arm."""
    idx = select_events(f, cond)
    if len(idx) < 300:
        return None
    d, paths = extract(f, arrays, idx)
    side = side_all[idx]
    pp = shift_paths(paths, delay)
    sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
    pnl, st, _ = simulate(pp, side, STOP_K * sg, HORIZON, SLIPPAGE)

    entry_time = d.time + pd.to_timedelta(1 + delay, unit="m")
    return pd.DataFrame({
        "gross_pips": pnl,
        "sigma_pips": sg,
        "sdate": d.sdate.values,
        "era": d.era.values,
        "utc_hour": entry_time.dt.tz_convert("UTC").dt.hour.to_numpy(),
        "stopped": st,
    }).dropna(subset=["gross_pips", "sigma_pips"])


def net_metrics(t, cost_pips, years):
    """Gross and net summary (mean R beside mean pips) for a trade frame."""
    gross = metrics(t.gross_pips.values, t.sigma_pips.values, t.sdate.values, years)
    net_pips = t.gross_pips.values - cost_pips
    net = metrics(net_pips, t.sigma_pips.values, t.sdate.values, years)
    if "mean_pips" not in gross:
        return None
    return {
        "n": int(len(t)),
        "signals_per_year": len(t) / years,
        "gross_mean_pips": gross["mean_pips"],
        "gross_mean_R": gross["mean_R"],
        "gross_cluster_t": gross["cluster_t"],
        "breakeven_flat_pip": gross["mean_pips"],
        "mean_cost_pips": float(np.mean(cost_pips)),
        "net_mean_pips": net.get("mean_pips", np.nan),
        "net_mean_R": net.get("mean_R", np.nan),
        "net_cluster_t": net.get("cluster_t", np.nan),
        "net_annual_pips": (net.get("mean_pips", np.nan)) * len(t) / years,
    }


def analyse(pair):
    f = build_features(pair)
    arrays = ohlc_arrays(f)
    arms, cuts = arm_conditions(f)
    rows, hour_rows = [], []
    for label, cond, side_all in arms:
        for delay in (0, 1):
            t = trades_for_arm(f, arrays, cond, side_all, delay)
            if t is None:
                continue
            years = t.sdate.nunique() / 252
            hour = t.utc_hour.to_numpy()
            era = t.era.to_numpy()
            vr = t.sigma_pips.to_numpy() / np.median(t.sigma_pips.to_numpy())

            for sc, params in SCENARIOS.items():
                cost = np.asarray(round_trip_pips(pair, hour, era, vr, params), float)
                # overall + subsets
                for subset, mask in [
                    ("all", np.ones(len(t), bool)),
                    ("liquid_0720", np.isin(hour, LIQUID_HOURS)),
                    ("overlap_1216", np.isin(hour, OVERLAP_HOURS)),
                    ("early", era == "early"),
                    ("late", era == "late"),
                ]:
                    if mask.sum() < 200:
                        continue
                    m = net_metrics(t.loc[mask], cost[mask],
                                    t.loc[mask].sdate.nunique() / 252)
                    if m:
                        rows.append({"pair": pair, "arm": label, "delay": delay,
                                     "scenario": sc, "subset": subset, **m})

                # per-hour table, base scenario, delay 1 only (the honest arm)
                if sc == "base" and delay == 1:
                    tt = t.assign(cost_pips=cost,
                                  net_pips=t.gross_pips.values - cost)
                    for h, g in tt.groupby("utc_hour"):
                        hour_rows.append({
                            "pair": pair, "arm": label, "utc_hour": int(h),
                            "n": int(len(g)),
                            "gross_pips": float(g.gross_pips.mean()),
                            "cost_pips": float(g.cost_pips.mean()),
                            "net_pips": float(g.net_pips.mean()),
                            "net_R": float((g.net_pips / g.sigma_pips).mean()),
                        })
    return rows, hour_rows, {"pair": pair, **cuts}


def kill_test(df, hourdf):
    """Best cell, base scenario, delay 1: is any positive-net hour a real edge?"""
    verdict = {}
    for pair in PAIRS:
        sub = df[(df.pair == pair) & (df.arm == "best_cell") & (df.delay == 1)
                 & (df.scenario == "base") & (df.subset == "all")]
        liq = df[(df.pair == pair) & (df.arm == "best_cell") & (df.delay == 1)
                 & (df.scenario == "base") & (df.subset == "liquid_0720")]
        overall_net_R = float(sub.net_mean_R.iloc[0]) if len(sub) else np.nan
        liquid_net_R = float(liq.net_mean_R.iloc[0]) if len(liq) else np.nan
        h = hourdf[(hourdf.pair == pair) & (hourdf.arm == "best_cell")]
        pos = h[h.net_pips > 0]
        # hours with positive net whose gross also exceeds modelled cost = "real" hours
        real_pos = pos[pos.gross_pips > pos.cost_pips]
        verdict[pair] = {
            "overall_net_mean_R_delay1_base": overall_net_R,
            "liquid_0720_net_mean_R_delay1_base": liquid_net_R,
            "n_hours_positive_net": int(len(pos)),
            "n_hours_positive_net_and_gross_gt_cost": int(len(real_pos)),
            "real_positive_hours": sorted(int(x) for x in real_pos.utc_hour),
        }
    return verdict


def main():
    rows, hour_rows, cutrows = [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, h, c = analyse(pair)
        rows.extend(r)
        hour_rows.extend(h)
        cutrows.append(c)

    df = pd.DataFrame(rows)
    hourdf = pd.DataFrame(hour_rows)

    print("\n=== Gate cutpoints (early-era fitted) ===")
    print(pd.DataFrame(cutrows).round(4).to_string(index=False))

    print("\n=== 1. Overall net economics, delay 1, ALL hours (median across pairs) ===")
    o = df[(df.delay == 1) & (df.subset == "all")]
    print(o.groupby(["arm", "scenario"]).agg(
        per_year=("signals_per_year", "median"),
        gross_pips=("gross_mean_pips", "median"),
        gross_R=("gross_mean_R", "median"),
        breakeven_pip=("breakeven_flat_pip", "median"),
        mean_cost=("mean_cost_pips", "median"),
        net_pips=("net_mean_pips", "median"),
        net_R=("net_mean_R", "median"),
        net_t=("net_cluster_t", "median"),
    ).round(4).to_string())

    print("\n=== 2. LIQUID-hours (07:00-20:00 UTC), base scenario, delay 1, per pair ===")
    liq = df[(df.delay == 1) & (df.subset == "liquid_0720") & (df.scenario == "base")]
    print(liq.pivot_table(index="arm", columns="pair", values="net_mean_R").round(4).to_string())
    print("   overlap 12-16 UTC:")
    ov = df[(df.delay == 1) & (df.subset == "overlap_1216") & (df.scenario == "base")]
    print(ov.pivot_table(index="arm", columns="pair", values="net_mean_R").round(4).to_string())

    print("\n=== 3. Per-hour gross vs modelled cost, best cell, base scenario, delay 1 "
          "(median across pairs) ===")
    hh = hourdf[hourdf.arm == "best_cell"].groupby("utc_hour").agg(
        n=("n", "sum"), gross=("gross_pips", "median"),
        cost=("cost_pips", "median"), net=("net_pips", "median"),
        net_R=("net_R", "median")).round(3)
    print(hh.to_string())

    verdict = kill_test(df, hourdf)
    print("\n=== 4. KILL TEST (best cell, base scenario, delay 1) ===")
    for pair, v in verdict.items():
        print(f"   {pair}: overall net R {v['overall_net_mean_R_delay1_base']:+.4f} | "
              f"liquid net R {v['liquid_0720_net_mean_R_delay1_base']:+.4f} | "
              f"real positive hours {v['real_positive_hours']}")
    liq_pos = sum(1 for v in verdict.values()
                  if v["liquid_0720_net_mean_R_delay1_base"] > 0)
    print(f"   -> pairs net-positive in liquid hours (base, delay1): {liq_pos}/4")

    df.to_csv(ROOT / "cost_hour_economics_cells.csv", index=False)
    hourdf.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_COST_HOUR_ECONOMICS_SPEC.md",
            "cost_model": "_cost_model.py",
            "pairs": PAIRS, "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "gate_keep": GATE_KEEP, "liquid_hours": LIQUID_HOURS,
            "overlap_hours": OVERLAP_HOURS, "scenarios": list(SCENARIOS),
            "primary_metric": "net mean R per bet under the modelled round-trip cost",
        },
        "gate_cutpoints": cutrows,
        "kill_test": verdict,
        "cells": json.loads(df.to_json(orient="records")),
        "per_hour": json.loads(hourdf.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
