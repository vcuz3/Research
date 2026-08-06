"""Do the high-conviction REGIME POCKETS clear the cost floor? (user follow-up)

The base/combined-gate cell greatest-hits at ~0.29 pip gross against a ~0.7-1.15
pip floor. But the project's strongest pockets are LOW-FREQUENCY, HIGH-GROSS vol
Q5 cells (the joint-vol Q5 was 214 signals/yr at 1.217 gross pips, delay 0, no
stop, fixed clock). Two reasons they might survive where the broad gate does not:

  1. A fixed per-lot COMMISSION is a smaller fraction of a bigger move. Selecting
     high-volatility states raises the risk unit sigma, and net R = grossR -
     cost/sigma, so a larger sigma shrinks the commission drag. (Rule 19 -- a
     mechanical flatter, but against a REAL fixed commission it is real money.)
  2. Fewer, higher-gross trades amortise the fixed cost better.

This re-runs the vol-regime pockets HONESTLY -- event clock, non-overlap, 3R
compulsory stop, one-minute delay -- under the modelled cost, tracking the risk
unit so the commission-fraction lever is visible. Gross pips are also reported
because the deployment question is net pips/R > 0, not R-excess over a frontier.

Reproduce:
    python -u _run_regime_pocket_economics.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _cost_model import CostParams, commission_pips, round_trip_pips
from _rsi_stop_engine import (
    BASE_K,
    HORIZON,
    build_features,
    exact_roll,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    slot_pct,
)
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "regime_pocket_economics_results.json"
CSV = ROOT / "regime_pocket_economics.csv"

STOP_K = 3.0
SLIPPAGE = 1.0
MIN_SIGNALS = 150
BASE = CostParams(scenario="base")
OPT = CostParams(scenario="optimistic")
NOCOMM = CostParams(scenario="base", include_commission=False)


def add_pocket_features(f):
    """rv_5m percentile and prior-30-minute range-break flags, on the full grid."""
    time = f.time
    one = time.diff().eq(pd.Timedelta(minutes=1))
    logc = pd.Series(np.log(f.close.astype(float)), index=f.index)
    ret1 = logc.diff().where(one)
    f["rv_5m"] = np.sqrt(exact_roll(ret1.pow(2), time, 5, "sum"))
    f["rv5_pct"] = slot_pct(f, "rv_5m")
    # ABSOLUTE risk unit in pips (not a same-slot percentile) -- the purest lever
    # for shrinking a FIXED commission as a fraction of the move.
    f["rv30_pips"] = f.rv_30m * 1e4 * f.close.astype(float)
    # prior 30-minute high/low (exact-contiguous, ending at the PREVIOUS bar)
    hi = f.high.astype(float)
    lo = f.low.astype(float)
    prior_hi = exact_roll(hi, time, 30, "max").shift(1)
    prior_lo = exact_roll(lo, time, 30, "min").shift(1)
    close = f.close.astype(float)
    f["break_up"] = (close > prior_hi).fillna(False)      # overbought close breaks up
    f["break_dn"] = (close < prior_lo).fillna(False)      # oversold close breaks down
    return f


def early_cut(f, col, keep):
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(1 - keep)) if len(s) else np.nan


def arms(f):
    """(label, cond, side) for the base and the regime pockets, gating z1.5."""
    zl, zs = f.z.le(-BASE_K), f.z.ge(BASE_K)
    out = []

    def add(label, gate_l, gate_s):
        long_s = zl & gate_l
        short_s = zs & gate_s
        cond = (long_s | short_s).fillna(False).to_numpy()
        side = np.where(long_s.fillna(False), 1.0,
                        np.where(short_s.fillna(False), -1.0, 0.0))
        out.append((label, cond, side))

    add("z1.5 base", True, True)
    for keep in (0.40, 0.20, 0.10, 0.05):
        cut = early_cut(f, "vol_pct", keep)
        g = f.vol_pct.ge(cut)
        add(f"rv30 top{int(keep*100)}", g, g)
    for keep in (0.20, 0.10):
        cut = early_cut(f, "rv5_pct", keep)
        g = f.rv5_pct.ge(cut)
        add(f"rv5 top{int(keep*100)}", g, g)
    for keep in (0.20, 0.10):
        cut = early_cut(f, "vei_atr_z", keep)
        g = f.vei_atr_z.ge(cut)
        add(f"vei top{int(keep*100)}", g, g)
    # absolute-sigma (big-pip-move) selection: maximise sigma to shrink comm/sigma
    for keep in (0.20, 0.10, 0.05):
        cut = early_cut(f, "rv30_pips", keep)
        g = f.rv30_pips.ge(cut)
        add(f"abs_sigma top{int(keep*100)}", g, g)
    # combined tiers (the confirmed regime family, made tighter)
    for keep in (0.40, 0.20, 0.10):
        cv = early_cut(f, "vei_atr_z", keep)
        cr = early_cut(f, "vol_pct", keep)
        g = f.vei_atr_z.ge(cv) & f.vol_pct.ge(cr)
        add(f"vei&rv30 top{int(keep*100)}", g, g)
    # range-break: extreme close breaks the prior 30-min range (side-specific)
    add("rangebreak", f.break_dn, f.break_up)
    add("rv30 top10 & rangebreak",
        f.vol_pct.ge(early_cut(f, "vol_pct", 0.10)) & f.break_dn,
        f.vol_pct.ge(early_cut(f, "vol_pct", 0.10)) & f.break_up)
    return out


def analyse(pair):
    f = add_pocket_features(build_features(pair))
    arrays = ohlc_arrays(f)
    rows = []
    for label, cond, side_all in arms(f):
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

            def netrow(params):
                c = np.asarray(round_trip_pips(pair, hour, era, vr, params), float)
                npips = pnl - c
                nm = metrics(npips, sg, d.sdate.values, years)
                return (float(np.mean(c[ok])), nm.get("mean_pips", np.nan),
                        nm.get("mean_R", np.nan), nm.get("cluster_t", np.nan))

            cb, nb_pips, nb_R, nb_t = netrow(BASE)
            co, no_pips, no_R, _ = netrow(OPT)
            cn, nn_pips, nn_R, _ = netrow(NOCOMM)
            rows.append({
                "pair": pair, "arm": label, "delay": delay,
                "signals_per_year": m["signals_per_year"],
                "gross_pips": m["mean_pips"], "gross_R": m["mean_R"],
                "risk_unit_pips": m["implied_risk_unit_pips"],
                "gross_cluster_t": m["cluster_t"], "hit_rate": m["hit_rate"],
                "stopped_frac": m.get("stopped_frac", np.nan),
                "cost_base": cb, "net_base_pips": nb_pips, "net_base_R": nb_R,
                "net_base_t": nb_t,
                "cost_opt": co, "net_opt_pips": no_pips, "net_opt_R": no_R,
                "cost_nocomm": cn, "net_nocomm_pips": nn_pips, "net_nocomm_R": nn_R,
                "commission_pips": commission_pips(pair),
            })
    return rows


def main():
    rows = []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        rows.extend(analyse(pair))
    df = pd.DataFrame(rows)
    d1 = df[df.delay == 1]

    order = ["z1.5 base", "rv30 top40", "rv30 top20", "rv30 top10", "rv30 top5",
             "rv5 top20", "rv5 top10", "vei top20", "vei top10",
             "abs_sigma top20", "abs_sigma top10", "abs_sigma top5",
             "vei&rv30 top40", "vei&rv30 top20", "vei&rv30 top10",
             "rangebreak", "rv30 top10 & rangebreak"]

    print("\n=== Regime pockets, HONEST engine (3R stop, delay 1), median across pairs ===")
    print("   commission floor ~0.70 pip; net includes spread+commission")
    g = d1.groupby("arm").agg(
        per_year=("signals_per_year", "median"),
        gross_pips=("gross_pips", "median"),
        risk_unit=("risk_unit_pips", "median"),
        gross_R=("gross_R", "median"),
        cost_base=("cost_base", "median"),
        net_base_pips=("net_base_pips", "median"),
        net_base_R=("net_base_R", "median"),
        net_base_t=("net_base_t", "median"),
        net_nocomm_pips=("net_nocomm_pips", "median"),
    ).reindex([a for a in order if a in d1.arm.unique()]).round(3)
    print(g.to_string())

    print("\n=== Net (base) mean R per pair, delay 1 ===")
    print(d1.pivot_table(index="arm", columns="pair", values="net_base_R")
          .reindex([a for a in order if a in d1.arm.unique()]).round(4).to_string())

    print("\n=== Arms net-POSITIVE (base cost, delay 1) ===")
    pos = g[g.net_base_pips > 0]
    if len(pos):
        for arm in pos.index:
            per_pair = d1[d1.arm == arm].set_index("pair").net_base_R
            npos = int((per_pair > 0).sum())
            print(f"   {arm:24s} net {pos.loc[arm,'net_base_pips']:+.3f} pip / "
                  f"{pos.loc[arm,'net_base_R']:+.4f} R  ({npos}/4 pairs), "
                  f"{pos.loc[arm,'per_year']:.0f}/yr, sigma {pos.loc[arm,'risk_unit']:.1f} pip")
    else:
        print("   NONE at base cost.")

    print("\n=== Delay-0 vs delay-1 gross (fragility check), median ===")
    piv = df.pivot_table(index="arm", columns="delay", values="gross_pips", aggfunc="median")
    piv = piv.reindex([a for a in order if a in piv.index]).round(3)
    piv["retain"] = (piv[1] / piv[0]).round(2)
    print(piv.to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "pairs": PAIRS, "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "commission_floor_pips": float(df.commission_pips.median()),
            "question": "do high-conviction vol-regime pockets clear the cost floor honestly",
        },
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
