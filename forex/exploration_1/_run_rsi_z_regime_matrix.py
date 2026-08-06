"""Trigger redundancy (RSI on top of z) and the regime filters not yet applied.

Two questions, one machinery, both declared in RSI_Z_REGIME_MATRIX_SPEC.md.

A. Is requiring RSI *and* z anything more than requiring a deeper z? Measured before
   the run, Spearman(z, RSI14) = 0.9684 and P(z<=-1.5 | RSI<=30) = 0.821, so the
   prior is "no". The test is whether the conjunction sits ON the |z| frontier.

B. `RSI_COHERENCE_TIMEEXIT_REPORT.md` applied only one of this project's three
   documented regime survivors (the ATR expansion gate). The RV-percentile family
   passed its own frozen clock/delay kill test and has never been run on an event
   clock. This adds it.

Every arm changes its own signal count, and depth alone is already known to raise
profit per signal here, so every arm is scored as EXCESS over the |z| >= k frontier
interpolated to that arm's own signals/year. An arm on the frontier added nothing
but selectivity.

Reproduce with:
    python -u _run_rsi_z_regime_matrix.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    BASE_K,
    COSTS,
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
    years_of,
)
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_z_regime_matrix_results.json"
CSV = ROOT / "rsi_z_regime_matrix.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
Z_GRID = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
RSI_GRID = [35, 30, 25, 20, 15]
GATE_KEEP = 0.40


def add_extra_features(f):
    """rv_5m and the two RV percentiles, on the FULL minute grid."""
    time = f.time
    one = time.diff().eq(pd.Timedelta(minutes=1))
    ret1 = pd.Series(np.log(f.close.astype(float)), index=f.index).diff().where(one)
    f["rv_5m"] = np.sqrt(exact_roll(ret1.pow(2), time, 5, "sum"))
    f["rv5_pct"] = slot_pct(f, "rv_5m")
    f["rv30_pct"] = f.vol_pct          # already the causal same-slot RV(30) percentile
    return f


def early_cut(f, col, keep):
    """Gate cutpoint fitted on the early era only, applied unchanged to the late."""
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(1 - keep)) if len(s) else np.nan


def rules(f):
    """(label, boolean condition at every minute, side array) for every arm."""
    z, rsi = f.z, f.rsi_14
    zl, zs = {}, {}
    for k in Z_GRID:
        zl[k], zs[k] = z.le(-k), z.ge(k)
    rl, rs = {}, {}
    for t in RSI_GRID:
        rl[t], rs[t] = rsi.le(t), rsi.ge(100 - t)

    cuts = {
        "vei": early_cut(f, "vei_atr_z", GATE_KEEP),
        "rv30_40": early_cut(f, "rv30_pct", GATE_KEEP),
        "rv5_40": early_cut(f, "rv5_pct", GATE_KEEP),
        "rv30_20": early_cut(f, "rv30_pct", 0.20),
    }
    g_vei = f.vei_atr_z.ge(cuts["vei"])
    g_rv30 = f.rv30_pct.ge(cuts["rv30_40"])
    g_rv5 = f.rv5_pct.ge(cuts["rv5_40"])
    g_rv30d = f.rv30_pct.ge(cuts["rv30_20"])

    out = []

    def add(label, family, long_s, short_s, extra=None):
        long_c = long_s if extra is None else (long_s & extra)
        short_c = short_s if extra is None else (short_s & extra)
        cond = (long_c | short_c).fillna(False).to_numpy()
        side = np.where(long_c.fillna(False), 1.0,
                        np.where(short_c.fillna(False), -1.0, 0.0))
        out.append((label, family, cond, side))

    for k in Z_GRID:
        add(f"z {k}", "frontier |z|", zl[k], zs[k])
    for t in RSI_GRID:
        add(f"rsi {t}/{100 - t}", "A trigger", rl[t], rs[t])
    add("z 1.5 AND rsi 30/70", "A trigger", zl[1.5] & rl[30], zs[1.5] & rs[30])
    add("z 1.5 AND rsi 25/75", "A trigger", zl[1.5] & rl[25], zs[1.5] & rs[25])
    add("z 2.0 AND rsi 30/70", "A trigger", zl[2.0] & rl[30], zs[2.0] & rs[30])

    b_l, b_s = zl[BASE_K], zs[BASE_K]
    add("z1.5 + ATR expansion 40", "B regime", b_l, b_s, g_vei)
    add("z1.5 + rv30 pct 40", "B regime", b_l, b_s, g_rv30)
    add("z1.5 + rv5 pct 40", "B regime", b_l, b_s, g_rv5)
    add("z1.5 + rv30 pct 20", "B regime", b_l, b_s, g_rv30d)
    add("z1.5 + ATR40 + rv30_40", "B regime", b_l, b_s, g_vei & g_rv30)
    return out, cuts


def analyse(pair):
    f = add_extra_features(build_features(pair))
    arrays = ohlc_arrays(f)
    arms, cuts = rules(f)
    rows = []
    for label, family, cond, side_all in arms:
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
            if delay == 0:
                for era in ["early", "late"]:
                    m = d.era.eq(era).to_numpy()
                    yrs = d.loc[m].sdate.nunique() / 252
                    rows.append({**base, "era": era,
                                 **metrics(pnl[m], sg[m], d.sdate.values[m], yrs, st[m])})
    return rows, {"pair": pair, **{f"cut_{k}": v for k, v in cuts.items()}}


def add_excess(df):
    """Excess mean R over the |z| frontier interpolated to the arm's own rate."""
    df = df.copy()
    df["excess_R"] = np.nan
    df["frontier_R"] = np.nan
    for (pair, delay, era), grp in df.groupby(["pair", "delay", "era"], observed=True):
        fr = grp.loc[grp.family.eq("frontier |z|")].sort_values("signals_per_year")
        if len(fr) < 3:
            continue
        x, y = np.log(fr.signals_per_year.values), fr.mean_R.values
        interp = np.interp(np.log(grp.signals_per_year.values), x, y)
        df.loc[grp.index, "frontier_R"] = interp
        df.loc[grp.index, "excess_R"] = grp.mean_R.values - interp
    return df


def main():
    rows, cutrows = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, c = analyse(pair)
        rows.extend(r)
        cutrows.append(c)

    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_pips"]))
    main0 = df.loc[df.delay.eq(0) & df.era.eq("all")]

    print("\n=== Early-era-fitted gate cutpoints ===")
    print(pd.DataFrame(cutrows).round(4).to_string(index=False))

    print("\n=== 1. The |z| reference frontier (median across pairs), stop 2R + 1 pip ===")
    fr = main0.loc[main0.family.eq("frontier |z|")]
    print(fr.groupby("arm").agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
        cluster_t=("cluster_t", "median"), hit=("hit_rate", "median"),
        stopped=("stopped_frac", "median"),
    ).reindex([f"z {k}" for k in Z_GRID]).round(3).to_string())

    for fam, title in [("A trigger", "2. Trigger redundancy: is RSI anything but a deeper z?"),
                       ("B regime", "3. Regime filters, on the fixed |z| >= 1.5 base")]:
        print(f"\n=== {title} ===")
        s = main0.loc[main0.family.eq(fam)]
        print(s.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), frontier_R=("frontier_R", "median"),
            excess_R=("excess_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
            cluster_t=("cluster_t", "median"), hit=("hit_rate", "median"),
        ).round(4).to_string())

    print("\n=== 4. KILL TEST: excess over the frontier at matched rate ===")
    print("   SUPPORTED >= +0.005 R median AND >=3/4 pairs; dial if within +/-0.005")
    verdict = {}
    for arm, grp in main0.loc[~main0.family.eq("frontier |z|")].groupby("arm"):
        w = grp.set_index("pair").excess_R
        med, npos = float(w.median()), int((w >= 0.005).sum())
        d1 = df.loc[df.arm.eq(arm) & df.delay.eq(1) & df.era.eq("all")]
        late = df.loc[df.arm.eq(arm) & df.delay.eq(0) & df.era.eq("late")]
        med_d1 = float(d1.excess_R.median()) if len(d1) else np.nan
        med_late = float(late.excess_R.median()) if len(late) else np.nan
        if med >= 0.005 and npos >= 3:
            status = "SUPPORTED"
            if not (med_d1 > 0 and med_late > 0):
                status = "supported-but-fragile"
        elif med <= -0.005:
            status = "REJECTED (worse than frontier)"
        else:
            status = "REJECTED (selectivity dial)"
        verdict[arm] = {"median_excess_R": med, "pairs_ge_0.005": npos,
                        "median_excess_delay1": med_d1,
                        "median_excess_late": med_late, "status": status,
                        "per_pair": {k: float(v) for k, v in w.items()}}
        print(f"   {arm:26s} excess {med:+.4f} R  {npos}/4  "
              f"| delay1 {med_d1:+.4f} | late {med_late:+.4f}  -> {status}")

    print("\n=== 5. Per-pair excess, key arms ===")
    key = ["rsi 30/70", "z 1.5 AND rsi 30/70", "z1.5 + ATR expansion 40",
           "z1.5 + rv30 pct 40", "z1.5 + rv5 pct 40", "z1.5 + ATR40 + rv30_40"]
    p = main0.loc[main0.arm.isin(key)].pivot_table(index="arm", columns="pair",
                                                   values="excess_R")
    print(p.reindex([k for k in key if k in p.index]).round(4).to_string())

    print("\n=== 6. Era split of the regime arms (median across pairs) ===")
    e = df.loc[df.delay.eq(0) & df.era.isin(["early", "late"]) & df.family.eq("B regime")]
    print(e.groupby(["arm", "era"]).agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), excess_R=("excess_R", "median"),
        cluster_t=("cluster_t", "median"),
    ).round(4).to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_Z_REGIME_MATRIX_SPEC.md",
            "pairs": PAIRS, "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "z_grid": Z_GRID, "rsi_grid": RSI_GRID, "gate_keep": GATE_KEEP,
            "costs_pips": COSTS,
            "primary_metric": ("mean R excess over the |z| frontier linearly "
                               "interpolated in log signals/year to the arm's own rate"),
        },
        "gate_cutpoints": cutrows,
        "verdicts": verdict,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
