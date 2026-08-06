"""Arm 4: time-based non-reversion exit, event clock, compulsory stop.

The worst 1% of trades remove 52-79% of gross P&L
(`RSI_MEAN_REVERSION_PROGRAMME_REPORT.md`). A trade that has not begun to revert
some minutes after entry is the observable early state of that tail. The
preregistered claim is that exiting it early cuts the left tail more cheaply than
the compulsory stop does, because it acts before the adverse excursion completes.

Rule, causal: at elapsed minute N, observe close(i+N) and exit at open(i+1+N) if
the non-reversion condition holds; otherwise hold to open(i+31). The compulsory
stop stays live throughout and takes precedence if it triggers first.

The three degenerate controls are declared decisive in the spec:
  1. a matched-rate TIGHTER STOP -- if it ties, the finding is "this is a stop",
     not "time carries information", and the arm is REJECTED;
  2. a matched-rate RANDOM-TIME exit -- separates information from exposure;
  3. an unconditional exit at N for every trade -- the horizon-sweep degenerate.

Reproduce with:
    python -u _run_rsi_time_exit.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    COSTS,
    HORIZON,
    PIP,
    build_features,
    condition,
    expansion_cutpoint,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    years_of,
)
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_time_exit_results.json"
CELL_CSV = ROOT / "rsi_time_exit_cells.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
N_GRID = [5, 10, 15, 20]
N_PRIMARY = 10
COND_PRIMARY = "pnl<=0"
RANDOM_DRAWS = 50
SEED = 20260804
KINDS = ["gated", "rsi3070"]


def mae_R(paths, side, sigma, bars=HORIZON):
    """Maximum adverse excursion over the full holding window, in risk units."""
    o, hi, lo = paths["open"], paths["high"], paths["low"]
    entry = o[:, 0]
    s = np.asarray(side, float)
    worst = np.where(s[:, None] > 0, lo[:, :bars], hi[:, :bars])
    extreme = np.where(s > 0, worst.min(axis=1), worst.max(axis=1))
    return s * (entry - extreme) / PIP / sigma


def build_events(pair, kind):
    frame = build_features(pair)
    cut = expansion_cutpoint(frame)
    cond, side_all = condition(frame, kind, cut)
    idx = select_events(frame, cond)
    d, paths = extract(frame, ohlc_arrays(frame), idx)
    d["side"] = side_all[idx]
    diag = {
        "pair": pair, "signal": kind, "events": int(len(d)),
        "expansion_cut_early_fitted": cut,
        "phase30_share_at_29": float(d.phase30.eq(29).mean()),
        "median_sigma_pips": float(d.sigma_pips.median()),
    }
    return d, paths, diag


def analyse(pair, d, paths, rng):
    years = years_of(d)
    side = d.side.to_numpy()
    sd = d.sdate.values
    n = len(d)
    rows = []

    for delay in (0, 1):
        pp = shift_paths(paths, delay)
        sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
        stop_dist = STOP_K * sg
        entry = pp["open"][:, 0]
        adverse = mae_R(pp, side, sg)

        def emit(label, pnl, stopped, exit_idx, **extra):
            early = (np.asarray(exit_idx) < HORIZON) | stopped
            rows.append({
                "pair": pair, "delay": delay, "arm": label,
                "early_exit_frac": float(np.mean(early)),
                **extra,
                **metrics(pnl, sg, sd, years, stopped),
            })

        # --- baseline: compulsory stop, hold to 30 ---
        base_pnl, base_st, _ = simulate(pp, side, stop_dist, HORIZON, SLIPPAGE)
        emit("base hold 30", base_pnl, base_st, np.full(n, HORIZON), N=np.nan, cond="")

        for N in N_GRID:
            # position P&L to the last observable close before the exit
            cur = side * (pp["close"][:, N - 1] - entry) / PIP
            for cname, flag in [("pnl<=0", cur <= 0),
                                ("pnl<=-0.25R", cur <= -0.25 * sg)]:
                ex = np.where(flag, N, HORIZON)
                pnl, st, _ = simulate(pp, side, stop_dist, ex, SLIPPAGE)
                emit(f"time exit N={N} {cname}", pnl, st, ex, N=N, cond=cname,
                     triggered_frac=float(flag.mean()))

                if not (N == N_PRIMARY and cname == COND_PRIMARY):
                    continue

                # --- control 1: matched-rate tighter stop ---
                target = float(np.mean((ex < HORIZON) | st))
                k_prime = float(np.quantile(adverse, 1 - target))
                p1, s1, _ = simulate(pp, side, k_prime * sg, HORIZON, SLIPPAGE)
                emit(f"CTRL1 stop {k_prime:.2f}R matched", p1, s1,
                     np.full(n, HORIZON), N=N, cond=cname, k_prime=k_prime,
                     target_rate=target)

                # --- control 2: matched-rate random-time exit ---
                f = float(flag.mean())
                acc = []
                for _ in range(RANDOM_DRAWS):
                    pick = rng.random(n) < f
                    exr = np.where(pick, N, HORIZON)
                    pr, sr, _ = simulate(pp, side, stop_dist, exr, SLIPPAGE)
                    acc.append((pr.mean(), (pr / sg).mean()))
                acc = np.array(acc)
                rows.append({
                    "pair": pair, "delay": delay,
                    "arm": f"CTRL2 random-time N={N} matched", "N": N, "cond": cname,
                    "early_exit_frac": f, "signals": n, "signals_per_year": n / years,
                    "mean_pips": float(acc[:, 0].mean()),
                    "mean_R": float(acc[:, 1].mean()),
                    "mean_pips_sd_across_draws": float(acc[:, 0].std(ddof=1)),
                })

                # --- control 3: unconditional exit at N ---
                p3, s3, _ = simulate(pp, side, stop_dist, N, SLIPPAGE)
                emit(f"CTRL3 unconditional exit N={N}", p3, s3, np.full(n, N),
                     N=N, cond=cname)

        # --- era split of the primary cell ---
        cur = side * (pp["close"][:, N_PRIMARY - 1] - entry) / PIP
        ex = np.where(cur <= 0, N_PRIMARY, HORIZON)
        pnl, st, _ = simulate(pp, side, stop_dist, ex, SLIPPAGE)
        for era in ["early", "late"]:
            m = d.era.eq(era).to_numpy()
            yrs = d.loc[m].sdate.nunique() / 252
            rows.append({"pair": pair, "delay": delay, "arm": "base hold 30", "era": era,
                         **metrics(base_pnl[m], sg[m], sd[m], yrs, base_st[m])})
            rows.append({"pair": pair, "delay": delay, "era": era,
                         "arm": f"time exit N={N_PRIMARY} {COND_PRIMARY}",
                         **metrics(pnl[m], sg[m], sd[m], yrs, st[m])})
    return rows


def main():
    rng = np.random.default_rng(SEED)
    all_rows, diags = [], []
    for kind in KINDS:
        for pair in PAIRS:
            print(f"Building {pair} / {kind} ...", flush=True)
            d, paths, diag = build_events(pair, kind)
            diags.append(diag)
            for r in analyse(pair, d, paths, rng):
                all_rows.append({**r, "signal": kind})

    df = pd.DataFrame(all_rows)
    main_df = df.loc[df.era.isna()] if "era" in df else df
    era_df = df.loc[df.era.notna()] if "era" in df else pd.DataFrame()

    print("\n=== Diagnostics ===")
    print(pd.DataFrame(diags).round(4).to_string(index=False))

    print("\n=== 1. Dose-response: exit at N if not reverted (median across pairs) ===")
    for kind in KINDS:
        s = main_df.loc[main_df.signal.eq(kind) & main_df.delay.eq(0)
                        & ~main_df.arm.str.startswith("CTRL2")]
        print(f"\n-- {kind} --")
        print(s.groupby("arm").agg(
            triggered=("triggered_frac", "median"),
            early_exit=("early_exit_frac", "median"),
            stopped=("stopped_frac", "median"),
            mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"),
            risk_unit=("implied_risk_unit_pips", "median"),
            cluster_t=("cluster_t", "median"),
            hit_rate=("hit_rate", "median"),
            worst_1pct=("worst_1pct_share", "median"),
            worst_5pct=("worst_5pct_share", "median"),
            max_dd_R=("max_drawdown_R", "median"),
            net_05=("net_0.5_pips", "median"),
        ).round(3).to_string())

    print("\n=== 2. KILL TEST at the primary cell "
          f"(N={N_PRIMARY}, {COND_PRIMARY}), mean R ===")
    verdict = {}
    prim_arm = f"time exit N={N_PRIMARY} {COND_PRIMARY}"
    for kind in KINDS:
        v = {}
        for delay in (0, 1):
            s = main_df.loc[main_df.signal.eq(kind) & main_df.delay.eq(delay)]
            w = s.pivot_table(index="pair", columns="arm", values="mean_R")
            p = s.pivot_table(index="pair", columns="arm", values="mean_pips")
            ctl1 = [c for c in w.columns if c.startswith("CTRL1")]
            ctl2 = [c for c in w.columns if c.startswith("CTRL2")]
            ctl3 = [c for c in w.columns if c.startswith("CTRL3")]
            if prim_arm not in w.columns or not ctl1:
                continue
            # CTRL1 differs per pair (matched k'), so collapse across its columns
            c1 = w[ctl1].mean(axis=1)
            c2 = w[ctl2].mean(axis=1) if ctl2 else pd.Series(np.nan, index=w.index)
            c3 = w[ctl3].mean(axis=1) if ctl3 else pd.Series(np.nan, index=w.index)
            tab = pd.DataFrame({
                "base": w["base hold 30"], "time_exit": w[prim_arm],
                "CTRL1_stop": c1, "CTRL2_random": c2, "CTRL3_uncond": c3})
            tab["vs_base"] = tab.time_exit - tab.base
            tab["vs_CTRL1"] = tab.time_exit - tab.CTRL1_stop
            tab["vs_CTRL2"] = tab.time_exit - tab.CTRL2_random
            tab["vs_base_pips"] = p[prim_arm] - p["base hold 30"]
            if delay == 0:
                print(f"\n-- {kind}, per pair (mean R) --")
                print(tab.round(4).to_string())
            v[f"delay{delay}"] = {
                "median_vs_base": float(tab.vs_base.median()),
                "pairs_beat_base": int((tab.vs_base > 0).sum()),
                "median_vs_CTRL1": float(tab.vs_CTRL1.median()),
                "pairs_beat_CTRL1": int((tab.vs_CTRL1 > 0).sum()),
                "median_vs_CTRL2": float(tab.vs_CTRL2.median()),
                "pairs_beat_CTRL2": int((tab.vs_CTRL2 > 0).sum()),
                "median_vs_base_pips": float(tab.vs_base_pips.median()),
            }
        d0 = v.get("delay0", {})
        v["criteria"] = {
            "1 beats hold-to-30 in >=3/4 by >= +0.02 R":
                bool(d0.get("pairs_beat_base", 0) >= 3
                     and d0.get("median_vs_base", 0) >= 0.02),
            "2 beats the matched-rate tighter STOP in >=3/4":
                bool(d0.get("pairs_beat_CTRL1", 0) >= 3),
            "3 beats the matched-rate RANDOM-time exit in >=3/4":
                bool(d0.get("pairs_beat_CTRL2", 0) >= 3),
        }
        verdict[kind] = v
        print(f"\n-- {kind} verdict --")
        for lab, key in [("vs hold-to-30", "median_vs_base"),
                         ("vs matched stop", "median_vs_CTRL1"),
                         ("vs random time", "median_vs_CTRL2")]:
            print(f"   {lab:18s} median {d0.get(key, float('nan')):+.4f} R, "
                  f"{d0.get(key.replace('median_vs_', 'pairs_beat_'), 0)}/4 pairs")
        for k, ok in v["criteria"].items():
            print(f"   [{'PASS' if ok else 'FAIL'}] {k}")

    print("\n=== 3. One-minute entry delay, primary cell (median across pairs) ===")
    s = main_df.loc[main_df.arm.isin(["base hold 30", prim_arm])]
    print(s.groupby(["signal", "arm", "delay"]).agg(
        mean_pips=("mean_pips", "median"), mean_R=("mean_R", "median"),
        cluster_t=("cluster_t", "median"),
    ).round(3).to_string())

    if len(era_df):
        print("\n=== 4. Era split, primary cell (median across pairs) ===")
        print(era_df.loc[era_df.delay.eq(0)].groupby(["signal", "arm", "era"]).agg(
            mean_pips=("mean_pips", "median"), mean_R=("mean_R", "median"),
            cluster_t=("cluster_t", "median"), max_dd_R=("max_drawdown_R", "median"),
        ).round(3).to_string())

    df.to_csv(CELL_CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_COHERENCE_TIMEEXIT_SPEC.md (arm 4)",
            "pairs": PAIRS,
            "clock": "event: first minute the entry condition becomes true, non-overlapping",
            "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "N_grid": N_GRID, "N_primary": N_PRIMARY, "cond_primary": COND_PRIMARY,
            "random_draws": RANDOM_DRAWS, "seed": SEED, "costs_pips": COSTS,
        },
        "diagnostics": diags,
        "verdicts": verdict,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
