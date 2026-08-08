"""Horizon-scaled exits for the long (240-min) hold, and the |z|-depth frontier.

Follow-up to the Axis-1 run, which showed (a) signal-strength filters add no
conviction over |z| depth and (b) the naked 240-min base looked flat/negative --
but with a stop fixed at 3 x the 30-MINUTE sigma applied to a 4-HOUR hold, which
truncates 35-48% of trades. This fixes the exit two ways and then asks what a
more extreme |z| entry does.

1a  TIME exit + HORIZON-SCALED stop.
    Risk unit is the 240-min sigma = rv_30m * sqrt(240/30) ~= 2.83 * rv_30m, so a
    3R stop is 3 units of the move actually available over the hold. mean_R is
    normalised by that same sigma => "fraction of the natural 4h move".

1b  TARGET exit (mean reversion complete) + horizon-scaled safety stop.
    Exit at the first bar after entry where z crosses back through 0 (price back
    to the EMA anchor = the fade thesis played out), capped at the 240-min
    timeout, stop as in 1a. Causal: reversion observed at a bar CLOSE exits at
    the NEXT open.

Then sweep |z| in {1.5 .. 4.0} under both exits (median across the four pairs and
per-pair for the deepest cells) to report what taking more extreme entries does.

Event clock, non-overlap (cooldown = 240), 1-pip adverse slippage, delay 0 and 1.
Consumed history; 2024+ sealed. Screen (rule 26), no null here.

Reproduce:  python -u _run_rsi_exit_horizon.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    COSTS,
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

OUT = ROOT / "rsi_exit_horizon_results.json"
CSV = ROOT / "rsi_exit_horizon.csv"

HORIZON = 240
STOP_K = 3.0
SLIPPAGE = 1.0
EXTRA = 1
SCALE = np.sqrt(HORIZON / 30.0)                 # 30-min sigma -> 240-min sigma
Z_GRID = [1.5, 1.75, 2.0, 2.25, 2.5, 3.0, 3.5, 4.0]


def target_exit_idx(zp, side, horizon):
    """First bar the fade reverts to the anchor (z through 0), else the timeout.

    zp: (n, width) z along the held path; side: (n,). Reversion for a long
    (entered z<0) is z>=0; for a short (entered z>0) is z<=0; both are
    side*z >= 0. Reversion observed at held bar m exits at the next open (m+1).
    """
    s = np.asarray(side, float)[:, None]
    rev = (s * zp[:, :horizon] >= 0) & np.isfinite(zp[:, :horizon])
    has = rev.any(axis=1)
    first = np.where(has, rev.argmax(axis=1), horizon - 1)
    exit_idx = np.minimum(np.where(has, first + 1, horizon), horizon).astype(int)
    return exit_idx, has


def run_pair(pair):
    f = build_features(pair)
    arrays = ohlc_arrays(f)
    zarr = f.z.to_numpy()
    rv30 = f.rv_30m.to_numpy()
    rows = []
    for k in Z_GRID:
        long_s = f.z.le(-k)
        short_s = f.z.ge(k)
        cond = (long_s | short_s).fillna(False).to_numpy()
        side_all = np.where(long_s.fillna(False), 1.0,
                            np.where(short_s.fillna(False), -1.0, 0.0))
        idx = select_events(f, cond, horizon=HORIZON)
        if len(idx) < 200:
            continue
        d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
        side = side_all[idx]
        take = (idx[:, None] + 1) + np.arange(HORIZON + 1 + EXTRA)[None, :]
        zp_full = zarr[take]
        rv_at = rv30[idx]
        years = years_of(d)

        for delay in (0, 1):
            pp = shift_paths(paths, delay, horizon=HORIZON)
            zp = zp_full[:, delay:delay + HORIZON + 1]
            entry = pp["open"][:, 0]
            sgH = rv_at * SCALE * 1e4 * entry          # 240-min sigma in pips
            stop = STOP_K * sgH

            # 1a: fixed 240-min time exit
            pnl_t, st_t, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)
            rows.append({"pair": pair, "exit": "time", "k": k, "delay": delay,
                         **metrics(pnl_t, sgH, d.sdate.values, years, st_t)})

            # 1b: mean-reversion target exit
            ex_idx, has = target_exit_idx(zp, side, HORIZON)
            pnl_g, st_g, _ = simulate(pp, side, stop, ex_idx, SLIPPAGE)
            ok = np.isfinite(pnl_g)
            m = metrics(pnl_g, sgH, d.sdate.values, years, st_g)
            m.update({
                "pair": pair, "exit": "target", "k": k, "delay": delay,
                "target_hit_frac": float((has & ~st_g & ok).sum() / max(ok.sum(), 1)),
                "timeout_frac": float((~has & ~st_g & ok).sum() / max(ok.sum(), 1)),
                "mean_hold_min": float(np.mean(ex_idx[ok])),
                "median_hold_min": float(np.median(ex_idx[ok])),
            })
            rows.append(m)
    return rows


def show(df, exit_name, delay):
    s = df[(df.exit == exit_name) & (df.delay == delay)]
    g = s.groupby("k").agg(
        per_year=("signals_per_year", "median"),
        mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"),
        hit=("hit_rate", "median"),
        stopped=("stopped_frac", "median"),
        cluster_t=("cluster_t", "median"),
        net02=("net_0.2_pips", "median"),
        net05=("net_0.5_pips", "median"),
    )
    if exit_name == "target":
        extra = s.groupby("k").agg(
            tgt=("target_hit_frac", "median"),
            timeout=("timeout_frac", "median"),
            hold=("median_hold_min", "median"),
        )
        g = g.join(extra)
    return g.reindex([k for k in Z_GRID if k in g.index]).round(4)


def main():
    rows = []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        rows.extend(run_pair(pair))
    df = pd.DataFrame(rows).dropna(subset=["mean_R"])

    print("\n########## 1a  TIME exit + horizon-scaled 3R stop ##########")
    print("\n--- delay 0 (median across pairs) ---")
    print(show(df, "time", 0).to_string())
    print("\n--- delay 1 (median across pairs) ---")
    print(show(df, "time", 1).to_string())

    print("\n########## 1b  TARGET exit (z->0) + horizon-scaled 3R stop ##########")
    print("\n--- delay 0 (median across pairs) ---")
    print(show(df, "target", 0).to_string())
    print("\n--- delay 1 (median across pairs) ---")
    print(show(df, "target", 1).to_string())

    print("\n########## Per-pair mean_R at deep |z| (delay 0) ##########")
    for exit_name in ("time", "target"):
        print(f"\n--- {exit_name} exit ---")
        p = df[(df.exit == exit_name) & (df.delay == 0)].pivot_table(
            index="k", columns="pair", values="mean_R")
        print(p.reindex([k for k in Z_GRID if k in p.index]).round(4).to_string())

    print("\n########## Per-pair mean_pips at deep |z| (delay 0, time exit) ##########")
    p = df[(df.exit == "time") & (df.delay == 0)].pivot_table(
        index="k", columns="pair", values="mean_pips")
    print(p.reindex([k for k in Z_GRID if k in p.index]).round(4).to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "horizon_min": HORIZON, "stop_R": STOP_K, "stop_sigma": "240-min",
            "slippage_pips": SLIPPAGE, "z_grid": Z_GRID, "pairs": PAIRS,
            "costs_pips": COSTS,
            "notes": "1a time exit + hscaled stop; 1b z->0 target exit + hscaled stop",
        },
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
