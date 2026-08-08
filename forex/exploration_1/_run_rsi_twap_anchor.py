"""Anchor swap: z from a SESSION-ANCHORED TWAP instead of the EMA(20).

User: instead of the z-score from an EMA, compute displacement against the
SESSION TWAP -- the time-weighted average price since the session open, the line
institutions reference when executing buys/sells (economic rationale). If
meaningful, run the null.

Anchor = cumulative mean of log price from the session open to the current minute
(equal-spaced 1-min bars => time-weighted). Displacement from a SESSION anchor
grows through the session (variance ~ elapsed time), so a fixed rolling-std
normalisation would turn a fixed z cut into a time-of-day selector (LEARNINGS
2026-07-27). It is therefore normalised by the causal SAME-SLOT (same
minute-of-session) trailing dispersion via `slot_z`, and the per-slot
selection-rate CV is reported to confirm the cut is not a clock. The EMA baseline
keeps its rolling-std normalisation (its displacement has no intraday scale
growth), so the normalisation differs by anchor BY NECESSITY; this is stated, not
hidden. The z->0 target exit becomes economically literal: exit when price
returns to the session TWAP.

Compared head-to-head with the EMA anchor on the baseline established this
session: 240-min hold, horizon-scaled 3R stop, event clock, non-overlap, delay 0
and 1, across the |z| depth frontier, under BOTH the time exit and the z->0
target exit. Then a side-permutation null on the TWAP arm (canonical reversion
null: shuffle trade sides, preserving the long/short count, re-execute on the
real paths with the real exit -- for the target exit the reversion clock is
recomputed per shuffled side). Real reversion should beat a null centred ~0.

Consumed history; 2024+ sealed. Screen (rule 26).

Reproduce:  python -u _run_rsi_twap_anchor.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from _rsi_stop_engine import (
    build_features,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    slot_z,
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
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_twap_anchor_results.json"
CSV = ROOT / "rsi_twap_anchor.csv"

NULL_DRAWS = 300
NULL_KS = [1.5, 2.5]           # depths at which the null is run
Z_WINDOW = 120


def add_twap_z(f):
    """z_twap: displacement from the SESSION TWAP, same-slot normalised.

    Session TWAP = cumulative mean of log price since the session open (causal,
    known at the decision close). Displacement normalised by the causal same-slot
    trailing dispersion (`slot_z`) so the intraday variance growth of a
    session-anchored displacement does not make a fixed z cut a clock.
    """
    logc = np.log(f.close.astype(float).to_numpy())
    g = pd.Series(logc, index=f.index).groupby(f.sdate.values)
    twap = g.cumsum().to_numpy() / (g.cumcount().to_numpy() + 1.0)
    f["disp_sess"] = logc - twap
    f["z_twap"] = slot_z(f, "disp_sess")
    return f


def run_anchor(f, arrays, zcol, k, delay):
    """One (anchor, depth, delay) cell under both exits. Returns rows + arrays."""
    z = f[zcol]
    long_s, short_s = z.le(-k), z.ge(k)
    cond = (long_s | short_s).fillna(False).to_numpy()
    side_all = np.where(long_s.fillna(False), 1.0,
                        np.where(short_s.fillna(False), -1.0, 0.0))
    idx = select_events(f, cond, horizon=HORIZON)
    if len(idx) < 200:
        return None
    d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
    side = side_all[idx]
    take = (idx[:, None] + 1) + np.arange(HORIZON + 1 + EXTRA)[None, :]
    zp_full = f[zcol].to_numpy()[take]
    rv_at = f.rv_30m.to_numpy()[idx]
    years = years_of(d)

    pp = shift_paths(paths, delay, horizon=HORIZON)
    zp = zp_full[:, delay:delay + HORIZON + 1]
    entry = pp["open"][:, 0]
    sgH = rv_at * SCALE * 1e4 * entry
    stop = STOP_K * sgH

    pnl_t, st_t, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)
    ex_idx, has = target_exit_idx(zp, side, HORIZON)
    pnl_g, st_g, _ = simulate(pp, side, stop, ex_idx, SLIPPAGE)

    rows = [
        {"anchor": zcol, "exit": "time", "k": k, "delay": delay,
         **metrics(pnl_t, sgH, d.sdate.values, years, st_t)},
        {"anchor": zcol, "exit": "target", "k": k, "delay": delay,
         **metrics(pnl_g, sgH, d.sdate.values, years, st_g),
         "median_hold_min": float(np.median(ex_idx[np.isfinite(pnl_g)]))},
    ]
    return rows, dict(pp=pp, zp=zp, side=side, stop=stop, sgH=sgH,
                      sdate=d.sdate.values, years=years)


def side_perm_null(cell, exit_name, draws, seed):
    """Shuffle trade sides (preserve L/S count), re-execute on real paths.

    For the target exit the reversion clock depends on side, so exit_idx is
    recomputed for each shuffled side vector -- otherwise the null would keep the
    real trades' exit timing.
    """
    rng = np.random.default_rng(seed)
    pp, zp, side = cell["pp"], cell["zp"], cell["side"]
    stop, sgH = cell["stop"], cell["sgH"]
    if exit_name == "time":
        real, _, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)
    else:
        ex, _ = target_exit_idx(zp, side, HORIZON)
        real, _, _ = simulate(pp, side, stop, ex, SLIPPAGE)
    real_R = float(np.nanmean(real / sgH))

    null_R = np.empty(draws)
    for j in range(draws):
        sp = rng.permutation(side)
        if exit_name == "time":
            pnl, _, _ = simulate(pp, sp, stop, HORIZON, SLIPPAGE)
        else:
            ex, _ = target_exit_idx(zp, sp, HORIZON)
            pnl, _, _ = simulate(pp, sp, stop, ex, SLIPPAGE)
        null_R[j] = np.nanmean(pnl / sgH)
    return {"real_R": real_R, "null_mean": float(null_R.mean()),
            "null_sd": float(null_R.std(ddof=1)),
            "frac_ge_real": float((null_R >= real_R).mean()),
            "z": float((real_R - null_R.mean()) / (null_R.std(ddof=1) + 1e-12))}


def main():
    rows, corr_rows, null_rows = [], [], []
    for pi, pair in enumerate(PAIRS):
        print(f"Building {pair} ...", flush=True)
        f = add_twap_z(build_features(pair))
        arrays = ohlc_arrays(f)

        m = f.z.notna() & f.z_twap.notna()
        rho = spearmanr(f.z[m], f.z_twap[m]).correlation
        # per-slot selection-rate CV of |z_twap| >= 1.5: high => acting as a clock
        fire = f.z_twap.abs().ge(1.5)
        rate = fire[f.z_twap.notna()].groupby(
            f.session_minute[f.z_twap.notna()]).mean()
        rate = rate[fire[f.z_twap.notna()].groupby(
            f.session_minute[f.z_twap.notna()]).size() >= 200]
        cv = float(rate.std() / rate.mean()) if rate.mean() else np.nan
        corr_rows.append({"pair": pair, "spearman_z_ema_twap": float(rho),
                          "slot_cv_fire_1.5": cv})

        cells = {}
        for zcol in ("z", "z_twap"):
            for k in Z_GRID:
                for delay in (0, 1):
                    res = run_anchor(f, arrays, zcol, k, delay)
                    if res is None:
                        continue
                    r, cellarrs = res
                    for row in r:
                        rows.append({"pair": pair, **row})
                    if zcol == "z_twap" and delay == 0 and k in NULL_KS:
                        cells[k] = cellarrs

        for k in NULL_KS:
            if k not in cells:
                continue
            for exit_name in ("time", "target"):
                res = side_perm_null(cells[k], exit_name, NULL_DRAWS,
                                     seed=1000 * pi + int(k * 10))
                null_rows.append({"pair": pair, "k": k, "exit": exit_name, **res})
                print(f"   NULL {pair} twap k={k} {exit_name:6s}: real {res['real_R']:+.4f} "
                      f"null {res['null_mean']:+.4f}+-{res['null_sd']:.4f} "
                      f"frac>=real {res['frac_ge_real']:.3f} z {res['z']:+.2f}", flush=True)

    df = pd.DataFrame(rows).dropna(subset=["mean_R"])

    print("\n=== Redundancy pre-screen: Spearman(z_ema, z_twap) ===")
    print(pd.DataFrame(corr_rows).round(4).to_string(index=False))

    for exit_name in ("time", "target"):
        print(f"\n=== Head-to-head EMA vs TWAP, {exit_name} exit, delay 0 "
              f"(median across pairs) ===")
        s = df[(df.exit == exit_name) & (df.delay == 0)]
        piv = s.pivot_table(index="k", columns="anchor",
                            values=["mean_pips", "mean_R", "cluster_t", "hit_rate"])
        piv = piv.reindex([k for k in Z_GRID if k in piv.index])
        print(piv.round(4).to_string())

    print("\n=== Delay-1 head-to-head mean_pips (median across pairs) ===")
    for exit_name in ("time", "target"):
        s = df[(df.exit == exit_name) & (df.delay == 1)]
        piv = s.pivot_table(index="k", columns="anchor", values="mean_pips")
        print(f"\n--- {exit_name} ---")
        print(piv.reindex([k for k in Z_GRID if k in piv.index]).round(4).to_string())

    print("\n=== Per-pair TWAP mean_R, target exit, delay 0 ===")
    p = df[(df.anchor == "z_twap") & (df.exit == "target") & (df.delay == 0)].pivot_table(
        index="k", columns="pair", values="mean_R")
    print(p.reindex([k for k in Z_GRID if k in p.index]).round(4).to_string())

    print("\n=== SIDE-PERMUTATION NULL on TWAP arm (delay 0) ===")
    ndf = pd.DataFrame(null_rows)
    if len(ndf):
        print(ndf.round(4).to_string(index=False))

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "anchor_test": "z from 20-min TWAP (SMA20) vs EMA20, matched COM 9.5",
            "horizon_min": HORIZON, "stop_R": STOP_K, "stop_sigma": "240-min",
            "slippage_pips": SLIPPAGE, "z_grid": Z_GRID, "pairs": PAIRS,
            "null": f"side-permutation, {NULL_DRAWS} draws, ks={NULL_KS}",
        },
        "spearman_ema_twap": corr_rows,
        "null": null_rows,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
