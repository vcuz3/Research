"""GO/NO-GO economics on the user's REAL account costs (240m abs_sigma reversion).

User-supplied costs (target account): AUDUSD ~0.3 pip average spread, NZDUSD ~0.5
pip, $5 commission round trip (= 0.5 pip at $10/pip on a standard lot). GBPUSD spread
not supplied -> assumed 0.6 pip and flagged.

The abs_sigma pocket trades the HIGHEST-volatility minutes, where the real spread is
usually wider than the pair's daily AVERAGE, so the average is optimistic here. The
spread is therefore stressed x1.0 / x1.5 / x2.0. Two fill modes:
  * taker  -- pay the full spread + commission
  * passive -- a resting limit at the extreme EARNS the spread, so cost = commission
    only (0.5 pip). An upper bound; real passive entry suffers non-fill/adverse
    selection (RULE 4), untestable without bid/ask, so this brackets the truth with
    the taker as the lower bound.

Reversion confirmed real vs a drift null on AUD/NZD (`horizon_null_results.json`);
EURUSD excluded (inverts to momentum). Consumed history; 2024+ sealed (screen).

Reproduce:
    python -u _run_final_economics.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    build_features,
    drawdown_R,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    session_cluster_t,
    shift_paths,
    simulate,
)
from _run_horizon_bracket import STOP_K, SLIPPAGE, pocket
from _run_regime_pocket_economics import add_pocket_features
from _run_rsi_broad_regime_sweep import SESSIONS_PER_YEAR, ROOT

OUT = ROOT / "final_economics_results.json"
CSV = ROOT / "final_economics.csv"

PAIRS = ["AUDUSD", "NZDUSD", "GBPUSD"]        # EUR excluded (momentum inversion)
SPREAD = {"AUDUSD": 0.3, "NZDUSD": 0.5, "GBPUSD": 0.6}   # GBP assumed, flagged
COMMISSION_RT = 0.5                            # $5 round trip / $10 per pip
HORIZONS = [180, 240, 300]
SPREAD_MULTS = [1.0, 1.5, 2.0]


def daily_sharpe(net_pips, sg, sdate):
    ok = np.isfinite(net_pips)
    r = (net_pips[ok] / sg[ok])
    daily = pd.Series(r).groupby(pd.Series(sdate)[ok].values).sum()
    if daily.std(ddof=1) == 0 or len(daily) < 2:
        return np.nan, np.nan, np.nan
    ann = daily.mean() / daily.std(ddof=1) * np.sqrt(SESSIONS_PER_YEAR)
    return float(ann), float(daily.min()), float(drawdown_R(r))


def analyse(pair):
    f = add_pocket_features(build_features(pair))
    arrays = ohlc_arrays(f)
    cond, side_all = pocket(f)
    rows = []
    for H in HORIZONS:
        idx = select_events(f, cond, horizon=H)
        if len(idx) < 150:
            continue
        d, paths = extract(f, arrays, idx, horizon=H)
        side = side_all[idx]
        years = d.sdate.nunique() / SESSIONS_PER_YEAR
        for delay in (0, 1):
            pp = shift_paths(paths, delay, horizon=H)
            sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
            pnl, st, _ = simulate(pp, side, STOP_K * sg, H, SLIPPAGE)
            ok = np.isfinite(pnl)
            gross = float(np.mean(pnl[ok]))
            n = int(ok.sum())
            for mult in SPREAD_MULTS:
                for mode in ("taker", "passive"):
                    spr = SPREAD[pair] * mult
                    cost = (spr + COMMISSION_RT) if mode == "taker" else COMMISSION_RT
                    net = pnl - cost
                    net_mean = float(np.mean(net[ok]))
                    net_R = float(np.mean(net[ok] / sg[ok]))
                    t = float(session_cluster_t(pd.Series(net[ok]),
                                                pd.Series(d.sdate.values)[ok]))
                    sh, worst_day, dd = daily_sharpe(net, sg, d.sdate.values)
                    rows.append({
                        "pair": pair, "horizon": H, "delay": delay,
                        "spread_mult": mult, "fill": mode,
                        "signals_per_year": n / years,
                        "gross_pips": gross, "rt_cost": cost,
                        "net_pips": net_mean, "net_R": net_R, "net_cluster_t": t,
                        "hit_rate": float((net[ok] > 0).mean()),
                        "annual_net_pips": net_mean * n / years,
                        "daily_sharpe": sh, "worst_day_R": worst_day, "max_dd_R": dd,
                        "stopped_frac": float(np.asarray(st, bool)[ok].mean()),
                    })
    return rows


def main():
    rows = []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        rows.extend(analyse(pair))
    df = pd.DataFrame(rows)

    print("\n=== 240m hold, delay 1, TAKER (pay spread+commission) ===")
    t = df[(df.horizon == 240) & (df.delay == 1) & (df.fill == "taker")]
    print(t.set_index(["pair", "spread_mult"])[
        ["signals_per_year", "gross_pips", "rt_cost", "net_pips", "net_R",
         "net_cluster_t", "annual_net_pips", "daily_sharpe", "worst_day_R"]
    ].round(3).to_string())

    print("\n=== 240m hold, delay 1, PASSIVE entry (earn spread; cost=commission only) ===")
    p = df[(df.horizon == 240) & (df.delay == 1) & (df.fill == "passive")]
    print(p.set_index(["pair", "spread_mult"])[
        ["gross_pips", "rt_cost", "net_pips", "net_R", "net_cluster_t",
         "annual_net_pips", "daily_sharpe"]
    ].round(3).to_string())

    print("\n=== Horizon robustness (AUD/NZD, delay 1, taker, spread x1.5) ===")
    r = df[(df.delay == 1) & (df.fill == "taker") & (df.spread_mult == 1.5)
           & (df.pair.isin(["AUDUSD", "NZDUSD"]))]
    print(r.set_index(["pair", "horizon"])[
        ["gross_pips", "net_pips", "net_R", "net_cluster_t", "annual_net_pips"]
    ].round(3).to_string())

    print("\n=== Delay 0 vs 1 (AUD/NZD, 240m, taker, spread x1.5) ===")
    dd = df[(df.horizon == 240) & (df.fill == "taker") & (df.spread_mult == 1.5)
            & (df.pair.isin(["AUDUSD", "NZDUSD"]))]
    print(dd.set_index(["pair", "delay"])[["gross_pips", "net_pips", "net_R"]].round(3).to_string())

    print("\n=== GO/NO-GO summary (240m, delay 1, taker) ===")
    for pair in ["AUDUSD", "NZDUSD"]:
        for mult in SPREAD_MULTS:
            row = t[(t.pair == pair) & (t.spread_mult == mult)]
            if len(row):
                r0 = row.iloc[0]
                verdict = "GO" if r0.net_pips > 0 and r0.net_cluster_t > 2 else \
                          ("marginal" if r0.net_pips > 0 else "NO-GO")
                print(f"   {pair} spread x{mult}: net {r0.net_pips:+.3f} pip/trade, "
                      f"{r0.net_R:+.4f} R, t {r0.net_cluster_t:+.2f}, "
                      f"{r0.annual_net_pips:+.0f} pips/yr -> {verdict}")

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "pairs": PAIRS, "spread_pips": SPREAD, "commission_rt_pips": COMMISSION_RT,
            "stop_R": STOP_K, "slippage_pips": SLIPPAGE, "horizons": HORIZONS,
            "spread_mults": SPREAD_MULTS,
            "note": "abs_sigma pocket trades high-vol minutes; average spread is optimistic, hence the stress",
        },
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
