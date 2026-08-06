"""Workstream B / D3: does signal DEPTH push gross pips above the cost floor?

Workstream A showed the strategy is a ~0.29 pip gross edge against a ~0.7-1.4 pip
round-trip cost floor whose dominant term (per-lot commission, ~0.70 pip) is depth-
independent. Deeper `|z|` pays more pips per signal (the frontier is monotone), so
the pivotal question is whether any usable depth clears the commission floor. This
sweeps `|z|` deep and reports GROSS pips per trade (not just R) against the modelled
cost, with the flat breakeven pip.

If the gross ceiling stays below the ~0.70 pip commission at every usable frequency,
no net-positive per-trade configuration exists on this cost structure, and
Workstreams C (challenge sim) and D4/D5 are moot for a taker.

Reproduce:
    python -u _run_depth_cost.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _cost_model import CostParams, commission_pips, round_trip_pips
from _rsi_stop_engine import (
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

OUT = ROOT / "depth_cost_results.json"
CSV = ROOT / "depth_cost.csv"

STOP_K = 3.0
SLIPPAGE = 1.0
Z_GRID = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
MIN_SIGNALS = 100
BASE = CostParams(scenario="base")
OPT = CostParams(scenario="optimistic")


def zonly_cond(f, k):
    long_s, short_s = f.z.le(-k), f.z.ge(k)
    cond = (long_s | short_s).fillna(False).to_numpy()
    side = np.where(long_s.fillna(False), 1.0, np.where(short_s.fillna(False), -1.0, 0.0))
    return cond, side


def analyse(pair):
    f = build_features(pair)
    arrays = ohlc_arrays(f)
    rows = []
    for k in Z_GRID:
        cond, side_all = zonly_cond(f, k)
        idx = select_events(f, cond)
        if len(idx) < MIN_SIGNALS:
            continue
        d, paths = extract(f, arrays, idx)
        side = side_all[idx]
        for delay in (0, 1):
            pp = shift_paths(paths, delay)
            sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
            pnl, st, _ = simulate(pp, side, STOP_K * sg, HORIZON, SLIPPAGE)
            years = d.sdate.nunique() / 252
            m = metrics(pnl, sg, d.sdate.values, years, st)
            if "mean_pips" not in m:
                continue
            hour = (d.time + pd.to_timedelta(1 + delay, unit="m")).dt.tz_convert("UTC").dt.hour.to_numpy()
            era = d.era.to_numpy()
            vr = sg / np.median(sg)
            ok = np.isfinite(pnl)
            cost_base = float(np.mean(round_trip_pips(pair, hour, era, vr, BASE)[ok]))
            cost_opt = float(np.mean(round_trip_pips(pair, hour, era, vr, OPT)[ok]))
            rows.append({
                "pair": pair, "z": k, "delay": delay,
                "signals_per_year": m["signals_per_year"],
                "gross_pips": m["mean_pips"], "gross_R": m["mean_R"],
                "risk_unit_pips": m["implied_risk_unit_pips"],
                "gross_cluster_t": m["cluster_t"], "hit_rate": m["hit_rate"],
                "mean_cost_base": cost_base, "mean_cost_opt": cost_opt,
                "net_base_pips": m["mean_pips"] - cost_base,
                "net_opt_pips": m["mean_pips"] - cost_opt,
                "commission_pips": commission_pips(pair),
            })
    return rows


def main():
    rows = []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        rows.extend(analyse(pair))
    df = pd.DataFrame(rows)

    print("\n=== Depth sweep, ungated |z|, delay 1, median across pairs ===")
    print("   (commission floor ~0.70 pip; net_base includes spread+commission)")
    d1 = df[df.delay == 1]
    print(d1.groupby("z").agg(
        per_year=("signals_per_year", "median"),
        gross_pips=("gross_pips", "median"),
        gross_R=("gross_R", "median"),
        risk_unit=("risk_unit_pips", "median"),
        cost_base=("mean_cost_base", "median"),
        net_base=("net_base_pips", "median"),
        net_opt=("net_opt_pips", "median"),
        gross_t=("gross_cluster_t", "median"),
    ).round(3).to_string())

    ceil = d1.groupby("z").gross_pips.median().max()
    zbest = d1.groupby("z").gross_pips.median().idxmax()
    comm = float(df.commission_pips.median())
    print(f"\n   Gross ceiling across depths: {ceil:.3f} pip at z={zbest} "
          f"(delay 1, median). Commission floor alone: {comm:.3f} pip.")
    print(f"   Gross clears commission floor: {'YES' if ceil > comm else 'NO'}")
    print(f"   Any depth net-positive under base cost (median): "
          f"{'YES' if (d1.groupby('z').net_base_pips.median() > 0).any() else 'NO'}")
    print(f"   Any depth net-positive under optimistic cost (median): "
          f"{'YES' if (d1.groupby('z').net_opt_pips.median() > 0).any() else 'NO'}")

    print("\n=== Per pair, deepest usable cells (delay 1) ===")
    print(d1.pivot_table(index="z", columns="pair", values="gross_pips").round(3).to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "pairs": PAIRS, "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "z_grid": Z_GRID, "commission_floor_pips": comm,
            "gross_ceiling_pips": float(ceil), "gross_ceiling_z": float(zbest),
            "primary_question": "does any depth push gross pips above the commission floor",
        },
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
