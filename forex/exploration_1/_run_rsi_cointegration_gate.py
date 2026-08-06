"""Cross-pair cointegration / relative-value conditioner screen for the |z| >= 1.5 fade.

Frozen in RSI_COINTEGRATION_GATE_SPEC.md. Gates the fade on the PARTNER pair's
contemporaneous displacement (EUR<->GBP, AUD<->NZD): at a P extreme, did the partner
diverge (relative value stretched -> extra reversion pull) or confirm (shared-USD move)?
The feature uses only the partner's move, so it cannot restate P's own |z| -- the trap the
dead coherence gate was built to avoid (LEARNINGS 2026-08-04). Both directions run; the
kill test decides. Engine identical to the confirmed regime matrix.

Screen only. SUPPORTED iff median excess >= +0.005 R AND >= 3/4 pairs at delay 1, delay 0
not contradicting. Survivor -> step-2 null; none -> NO-GO.

Reproduce:
    python -u _run_rsi_cointegration_gate.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    BASE_K,
    HORIZON,
    Z_WINDOW,
    build_features,
    exact_roll,
    extract,
    load_minutes,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    years_of,
)
from _run_rsi_z_regime_matrix import Z_GRID
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_cointegration_gate_results.json"
CSV = ROOT / "rsi_cointegration_gate.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
KEEPS = [0.40, 0.20, 0.10]
PARTNER = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD",
           "AUDUSD": "NZDUSD", "NZDUSD": "AUDUSD"}


def pair_z(pair):
    """Lightweight causal displacement z indexed by tz-aware timestamp (partner join)."""
    raw = load_minutes(pair)
    time = raw.time
    logc = pd.Series(np.log(raw.close.astype(float)), index=raw.index)
    disp = logc - logc.ewm(span=20, adjust=False).mean()
    z = disp / exact_roll(disp, time, Z_WINDOW, "std").replace(0, np.nan)
    return pd.Series(z.to_numpy(), index=pd.DatetimeIndex(raw.time))


def sig_cut(f, col, keep, hi):
    """Quantile of `col` over EARLY-era |z|>=1.5 signal rows."""
    s = f.loc[f.era.eq("early") & f.z.abs().ge(BASE_K), col].dropna()
    if not len(s):
        return np.nan
    return float(s.quantile(1 - keep if hi else keep))


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
        ah = f["xalign"].ge(sig_cut(f, "xalign", keep, hi=True))
        al = f["xalign"].le(sig_cut(f, "xalign", keep, hi=False))
        add(f"diverge_hi {int(keep*100)}", "diverge", zl & ah, zs & ah)
        add(f"diverge_lo {int(keep*100)}", "diverge", zl & al, zs & al)

    for keep in KEEPS:
        calm = f["partner_absz"].le(sig_cut(f, "partner_absz", keep, hi=False))
        extr = f["partner_absz"].ge(sig_cut(f, "partner_absz", keep, hi=True))
        add(f"partner_calm {int(keep*100)}", "partner_absz", zl & calm, zs & calm)
        add(f"partner_extreme {int(keep*100)}", "partner_absz", zl & extr, zs & extr)
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


def analyse(pair, zbank):
    f = build_features(pair)
    f["z_partner"] = f["time"].map(zbank[PARTNER[pair]])
    long_sig, short_sig = f.z.le(-BASE_K), f.z.ge(BASE_K)
    f["xalign"] = np.where(long_sig, f.z_partner,
                           np.where(short_sig, -f.z_partner, np.nan))
    f["partner_absz"] = f.z_partner.abs()

    arrays = ohlc_arrays(f)
    fx1, fy1 = frontier_of(f, arrays, 1)
    fx0, fy0 = frontier_of(f, arrays, 0)
    rows = []
    for label, family, cond, side in build_arms(f):
        for delay, fx, fy in [(1, fx1, fy1), (0, fx0, fy0)]:
            m = evaluate(f, arrays, cond, side, delay, fx, fy)
            if m is not None:
                rows.append({"pair": pair, "arm": label, "family": family,
                             "delay": delay, **m})

    sig = f.z.abs().ge(BASE_K).fillna(False)
    d = f.iloc[select_events(f, sig.to_numpy())]
    cov = {era: {"n": int(d.era.eq(era).sum()),
                 "z_partner_defined": float(d.loc[d.era.eq(era), "z_partner"].notna().mean())}
           for era in ["early", "late"]}
    corr = {"z_vs_z_partner_all": float(f.z.corr(f.z_partner, method="spearman")),
            "z_vs_z_partner_signalrows": float(f.loc[sig].z.corr(
                f.loc[sig].z_partner, method="spearman"))}
    return rows, cov, corr


def main():
    print("Pre-building partner z-banks ...", flush=True)
    zbank = {p: pair_z(p) for p in PAIRS}

    rows, covs, corrs = [], {}, {}
    for pair in PAIRS:
        print(f"Building {pair} (partner {PARTNER[pair]}) ...", flush=True)
        r, c, cc = analyse(pair, zbank)
        rows.extend(r)
        covs[pair] = c
        corrs[pair] = cc

    df = pd.DataFrame(rows)
    d1 = df.loc[df.delay.eq(1)]
    d0 = df.loc[df.delay.eq(0)]

    print("\n=== 0. z_partner coverage among base |z|>=1.5 signals (rule 9a) ===")
    for pair, c in covs.items():
        for era, r in c.items():
            print(f"   {pair} {era:5s}: n={r['n']:6d}  z_partner defined {r['z_partner_defined']:.4f}")

    print("\n=== 1. How much do the two pairs share? Spearman(z, z_partner) ===")
    for pair, cc in corrs.items():
        print(f"   {pair} (partner {PARTNER[pair]}): all rows {cc['z_vs_z_partner_all']:+.3f}  "
              f"signal rows {cc['z_vs_z_partner_signalrows']:+.3f}")

    print("\n=== 2. |z| frontier (median across pairs), delay 1 ===")
    fr = d1.loc[d1.family.eq("frontier |z|")]
    print(fr.groupby("arm").agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
        cluster_t=("cluster_t", "median"),
    ).reindex([f"z {k}" for k in Z_GRID]).round(3).to_string())

    print("\n=== 3. Gate arms: excess over the frontier at matched rate (delay 1) ===")
    g = d1.loc[~d1.family.eq("frontier |z|")]
    print(g.groupby("arm").agg(
        family=("family", "first"),
        per_year=("signals_per_year", "median"), gross_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), excess_R=("excess_R", "median"),
        risk_unit=("implied_risk_unit_pips", "median"), cluster_t=("cluster_t", "median"),
    ).sort_values("excess_R", ascending=False).round(4).to_string())

    print("\n=== 4. DIRECTIONAL KILL: diverge_hi vs diverge_lo (median excess R, delay 1) ===")
    for keep in KEEPS:
        hi = g.loc[g.arm.eq(f"diverge_hi {int(keep*100)}"), "excess_R"].median()
        lo = g.loc[g.arm.eq(f"diverge_lo {int(keep*100)}"), "excess_R"].median()
        who = "DIVERGE helps" if hi > lo else "CONFIRM (lo) helps"
        print(f"   keep {int(keep*100):>2}%: diverge_hi {hi:+.4f}  diverge_lo {lo:+.4f}  -> {who}")

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

    print("\n=== 6. Per-pair excess R, diverge gates (delay 1) — read per block ===")
    key = [f"diverge_hi {int(k*100)}" for k in KEEPS] + \
          [f"diverge_lo {int(k*100)}" for k in KEEPS]
    p = g.loc[g.arm.isin(key)].pivot_table(index="arm", columns="pair", values="excess_R")
    print(p.reindex([k for k in key if k in p.index]).round(4).to_string())

    any_sup = any(v["status"].startswith("SUPPORTED") for v in verdict.values())
    print(f"\n   >>> Any arm SUPPORTED at delay 1: {any_sup}")
    print("   " + ("-> a survivor exists: run step-2 null + redundancy" if any_sup
                   else "-> NO-GO: cross-pair relative value does not condition the fade"))

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_COINTEGRATION_GATE_SPEC.md", "pairs": PAIRS,
            "partner": PARTNER, "stop_R": STOP_K, "slippage_pips": SLIPPAGE, "keeps": KEEPS,
            "primary_metric": "excess mean R over the |z| frontier, delay 1",
        },
        "coverage": covs, "share_correlation": corrs, "verdicts": verdict,
        "any_supported": bool(any_sup),
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
