"""Axis 6, item 20 (v2) -- RISK-SENTIMENT regime via ABSOLUTE HYSTERESIS + VOL-OF-VIX.

User (2026-08-07) challenged the trailing-standardized VIX z of the first item-20 run
("elevation vs its own recent level") and proposed a simpler, more literal regime:

  HYSTERESIS (Schmitt trigger): VIX closes >= 25  -> risk-OFF;
                                VIX closes <= 20  -> risk-ON;
                                in the 20-25 dead-band -> HOLD the previous state.
  The dead-band stops the regime flip-flopping when VIX hovers at one threshold.

  VOL-OF-VIX: trailing realized volatility of the VIX series itself (std of daily VIX
  log-changes) -- "is the fear gauge itself unstable", a second-moment risk regime.

This asks a DIFFERENT question from the trailing-z version: not "is risk spiking vs
lately" but "are we in a genuine risk-off STATE." Absolute risk-off is era-CLUSTERED
(2011-12, 2015-16, 2018Q4, 2020, 2022), so the run reports the number of distinct
risk-off EPISODES and the risk-off day/trade share -- few independent episodes = low
effective power, the caveat that governs how much any risk-off result can be trusted.

Both features are causal: hysteresis and trailing vol-of-VIX use only VIX closes up to
each point, as-of BACKWARD joined to each FX minute (Asia decisions use the prior US
close). Reversion is read BOTH as the intuitive per-regime mean_R AND as excess over
the |z_twap| depth frontier at matched rate (the disciplined bar the other axes used).
Standard baseline (news blackout is an orthogonal ~20% cut, not applied here for
comparability with the first item-20 run). Consumed history; 2024+ sealed.

Reproduce:  python -u _run_rsi_axis6_regime.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import build_features, ohlc_arrays
from _run_rsi_exit_horizon import Z_GRID
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_axis2_volregime import (
    BASE_K, KEEPS, add_excess, early_q, run_arm, slot_cv,
)
from _run_rsi_axis6_risk import load_vix_daily
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_axis6_regime_results.json"
CSV = ROOT / "rsi_axis6_regime.csv"

HI, LO = 25.0, 20.0          # hysteresis thresholds
VVIX_TRAIL = 20              # trailing sessions for vol-of-VIX


def hysteresis_state(vix_close):
    """Causal Schmitt-trigger risk-off flag on the daily VIX closes."""
    v = vix_close.to_numpy(dtype=float)
    off = np.zeros(len(v), dtype=bool)
    state = False
    for i, x in enumerate(v):
        if x >= HI:
            state = True
        elif x <= LO:
            state = False
        off[i] = state
    return off


def vol_of_vix(vix_close):
    """Trailing std of daily VIX log-changes (causal)."""
    lr = np.log(vix_close.to_numpy(dtype=float))
    dlr = pd.Series(np.r_[np.nan, np.diff(lr)])
    return dlr.rolling(VVIX_TRAIL, min_periods=VVIX_TRAIL // 2).std().to_numpy()


def episodes(off):
    """Number of distinct risk-off episodes (on->off transitions)."""
    return int(((~off[:-1]) & off[1:]).sum()) + int(off[0])


def add_regime(f, vix_close):
    vt = vix_close.index.values.astype("datetime64[ns]")
    off = hysteresis_state(vix_close)
    vvix = vol_of_vix(vix_close)
    ft = f.time.to_numpy().astype("datetime64[ns]")
    pos = np.searchsorted(vt, ft, side="right") - 1
    ok = pos >= 0
    rf = np.zeros(len(ft), dtype=bool)
    vv = np.full(len(ft), np.nan)
    rf[ok] = off[pos[ok]]
    vv[ok] = vvix[pos[ok]]
    f["risk_off"] = rf
    f["vvix"] = vv
    f["_vix_ok"] = ok
    return f, off


def build_arms(f):
    z = f.z_twap
    zl, zs = z.le(-BASE_K), z.ge(BASE_K)
    base = (zl | zs).fillna(False)
    arms, cvs = [], {}

    def add(label, family, cond, direction=""):
        cond = cond.fillna(False)
        arms.append((label, family, cond.to_numpy(),
                     np.where(cond & zl.fillna(False), 1.0,
                              np.where(cond & zs.fillna(False), -1.0, 0.0)),
                     direction))

    for k in Z_GRID:
        add(f"z {k}", "frontier |z|", f.z_twap.le(-k) | f.z_twap.ge(k))

    okv = pd.Series(f._vix_ok.to_numpy(), index=f.index)
    add("risk_on", "hysteresis", base & okv & (~f.risk_off), "on")
    add("risk_off", "hysteresis", base & okv & f.risk_off, "off")

    for keep in KEEPS:
        q_hi = early_q(f, "vvix", 1 - keep)
        q_lo = early_q(f, "vvix", keep)
        add(f"vvix hi {int(keep*100)}", "volvix", base & f.vvix.ge(q_hi), "hi")
        add(f"vvix lo {int(keep*100)}", "volvix", base & f.vvix.le(q_lo), "lo")
        if keep == 0.20:
            cvs["vvix_hi"] = slot_cv(f, base, f.vvix.ge(q_hi))
    return arms, base.to_numpy()


def analyse(pair, vix_close):
    f, off = add_regime(add_twap_z(build_features(pair)), vix_close)
    arrays = ohlc_arrays(f)
    arms, base_np = build_arms(f)
    zp_col = f.z_twap.to_numpy()
    rows = []
    for label, family, cond, side_all, direction in arms:
        for r in run_arm(f, arrays, cond, side_all, zp_col):
            rows.append({"pair": pair, "arm": label, "family": family,
                         "direction": direction, **r})
    bm = base_np & f.z_twap.notna().to_numpy() & f._vix_ok.to_numpy()
    diag = {"pair": pair,
            "risk_off_trade_share": float(f.risk_off.to_numpy()[bm].mean()),
            "risk_off_day_share": float(off.mean()),
            "n_risk_off_episodes": episodes(off),
            "vvix_median": float(np.nanmedian(f.vvix.to_numpy()))}
    return rows, diag


def main():
    print("Loading VIX daily closes ...", flush=True)
    vix = load_vix_daily()
    off = hysteresis_state(vix)
    print(f"   VIX closes {len(vix):,}; risk-off day share {off.mean():.3f}; "
          f"distinct risk-off episodes {episodes(off)}", flush=True)

    rows, diags = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, dg = analyse(pair, vix)
        rows.extend(r)
        diags.append(dg)
    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_R"]))

    print("\n=== Regime power diagnostics (few episodes = low effective power) ===")
    print(pd.DataFrame(diags).round(4).to_string(index=False))

    for exit_name in ("time", "target"):
        m0 = df[(df.exit == exit_name) & (df.delay == 0) & (df.era == "all")]
        print(f"\n=== |z_twap| frontier, {exit_name} exit, d0 (median) ===")
        fr = m0[m0.family.eq("frontier |z|")]
        print(fr.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_R=("mean_R", "median"),
            t=("cluster_t", "median"),
        ).reindex([f"z {k}" for k in Z_GRID]).round(4).to_string())

        print(f"\n=== HYSTERESIS regime split, {exit_name} exit, d0 (per pair) ===")
        h = m0[m0.family.eq("hysteresis")]
        print(h.pivot_table(index="pair", columns="arm",
                            values="mean_R").round(4).to_string())
        print(f"   -- excess over |z| frontier (median across pairs):")
        print(h.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_R=("mean_R", "median"),
            excess_R=("excess_R", "median"), t=("cluster_t", "median"),
            clamped=("clamped", "max")).round(4).to_string())

        print(f"\n=== VOL-OF-VIX gates, {exit_name} exit, d0 (median) ===")
        vv = m0[m0.family.eq("volvix")]
        print(vv.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_R=("mean_R", "median"),
            excess_R=("excess_R", "median"), t=("cluster_t", "median"),
            clamped=("clamped", "max")).round(4).to_string())

    print("\n=== SCREEN (time exit): excess>=+0.005 R, >=3/4 pairs, delay1+late ===")
    verdict = {}
    sub = df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
             & df.family.isin(["hysteresis", "volvix"])]
    for arm, grp in sub.groupby("arm"):
        w = grp.set_index("pair").excess_R
        med, npos = float(w.median()), int((w >= 0.005).sum())
        d1 = df[(df.arm == arm) & (df.exit == "time") & (df.delay == 1) & (df.era == "all")]
        late = df[(df.arm == arm) & (df.exit == "time") & (df.delay == 0) & (df.era == "late")]
        md1 = float(d1.excess_R.median()) if len(d1) else np.nan
        mlate = float(late.excess_R.median()) if len(late) else np.nan
        clamped = bool(grp.clamped.max())
        if med >= 0.005 and npos >= 3 and not clamped:
            status = "SUPPORTED" if (md1 > 0 and mlate > 0) else "fragile"
        elif med <= -0.005:
            status = "REJECTED (worse than frontier)"
        else:
            status = "REJECTED (dial)"
        if clamped and "REJECTED" not in status:
            status += " [CLAMPED]"
        verdict[arm] = {"median_excess_R": med, "pairs_ge_0.005": npos,
                        "delay1": md1, "late": mlate, "status": status,
                        "per_pair": {k: float(v) for k, v in w.items()}}
        print(f"   {arm:12s} excess {med:+.4f} R  {npos}/4  | d1 {md1:+.4f} "
              f"| late {mlate:+.4f}  -> {status}")

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "axis": "6 item 20 v2 (risk regime: absolute hysteresis 25/20 + vol-of-VIX)",
            "hysteresis_hi": HI, "hysteresis_lo": LO, "vvix_trailing": VVIX_TRAIL,
            "baseline": "session-TWAP z_twap, horizon-scaled 3R stop, 240m hold",
            "pairs": PAIRS, "z_grid": Z_GRID, "keeps": KEEPS, "base_k": BASE_K,
        },
        "diagnostics": diags, "verdicts": verdict,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
