"""Axis 6, item 20 -- RISK-SENTIMENT / IMPLIED-VOL REGIME (VIX) conviction on the
SESSION-TWAP baseline.

Mechanism: external risk sentiment modulates FX mean-reversion. In risk-OFF
(elevated VIX) a USD dislocation is often a flight-to-quality / deleveraging TREND
that continues -> reverts LESS; in risk-ON it is positioning noise -> reverts. VIX
is a US-equity risk measure, EXTERNAL to the pair's own vol state, so it is a
different axis from the (already-redundant) own-pair vol regime (axis 2). Direction
is tested BOTH ways (the project's own finding is reversion stronger in HIGH own-vol,
but that is own-pair; risk-off external stress can point the other way).

CAUSALITY: VIX prints only during US cash hours (09:30-16:00 ET). Each FX decision
minute takes the MOST RECENT VIX close available strictly at or before it (as-of
backward join), so an Asia-hours FX decision uses the prior US-session VIX close --
never a future print. The regime feature is the TRAILING-STANDARDIZED VIX
(elevation vs its own trailing 60-session mean/sd), which is (a) causal and (b)
regime-relative, so a fixed cut is NOT a secular-era selector (VIX's raw level drifts
across 2011/2017/2020 regimes -- a fixed raw cut would just label eras, the
LEARNINGS-2026-08-03/04 fixed-threshold trap). Raw-level gates are ALSO run and their
per-slot / per-era behaviour reported as the control.

Scored IDENTICALLY to axes 1-3/6-18: EXCESS mean R over the |z_twap| depth frontier
at matched rate, both exits, delay 0/1, eras. Redundancy Spearman(|z_twap|, vix_z)
reported up front (is external risk orthogonal to own depth?).

Gates:
  vixz hi/lo   trailing-standardized VIX, early-era quantile cut (RELATIVE, regime)
               hi = risk-OFF elevated (thesis: reverts LESS -> WORSE fade)
               lo = risk-ON calm       (thesis: reverts MORE -> conviction candidate)
  vixraw hi/lo raw VIX level, early-era quantile cut (ABSOLUTE; era-selector control)

Consumed history; 2024+ sealed (FX frames end 2023-12; VIX rows past that unused).
Screen (rule 26); a survivor earns a claim-matched null next.

Reproduce:  python -u _run_rsi_axis6_risk.py
"""

from __future__ import annotations

import glob
import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import build_features, ohlc_arrays
from _run_rsi_exit_horizon import Z_GRID
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_axis2_volregime import (
    BASE_K,
    KEEPS,
    add_excess,
    early_q,
    run_arm,
    slot_cv,
)
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_axis6_risk_results.json"
CSV = ROOT / "rsi_axis6_risk.csv"

VIX_GLOB = str(ROOT.parent.parent / "futures" / "data" / "vix" / "*.csv")
VIX_TRAIL = 60          # trailing sessions for the standardized-VIX regime z


def load_vix_daily():
    """Concatenate the CBOE VIX intraday CSVs -> one causal DAILY close series (UTC).

    Uses each US session's LAST print as that day's close; returns a Series indexed
    by the UTC timestamp of that close (the moment the value becomes known)."""
    frames = []
    for fp in glob.glob(VIX_GLOB):
        d = pd.read_csv(fp, usecols=["time", "close"])
        frames.append(d)
    v = pd.concat(frames, ignore_index=True)
    v["ts"] = pd.to_datetime(v.time, utc=True)
    v = v.dropna(subset=["ts", "close"]).drop_duplicates("ts").sort_values("ts")
    v["day"] = v.ts.dt.tz_convert("America/New_York").dt.date
    last = v.groupby("day").tail(1).copy()            # last print each US day = close
    s = pd.Series(last.close.to_numpy(), index=last.ts.to_numpy())   # known-at ts (UTC)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def add_vix(f, vix_close):
    """As-of backward join: each FX minute gets the most recent VIX close <= its time."""
    vt = vix_close.index.values.astype("datetime64[ns]")
    vv = vix_close.to_numpy(dtype=float)
    # trailing-standardized regime z on the DAILY closes (causal, own history)
    vs = pd.Series(vv)
    mu = vs.rolling(VIX_TRAIL, min_periods=VIX_TRAIL // 2).mean()
    sd = vs.rolling(VIX_TRAIL, min_periods=VIX_TRAIL // 2).std()
    vz = ((vs - mu) / sd).to_numpy()

    ft = f.time.to_numpy().astype("datetime64[ns]")
    pos = np.searchsorted(vt, ft, side="right") - 1   # last close strictly <= ft
    ok = pos >= 0
    lvl = np.full(len(ft), np.nan)
    zz = np.full(len(ft), np.nan)
    lvl[ok] = vv[pos[ok]]
    zz[ok] = vz[pos[ok]]
    f["vix_raw"] = lvl
    f["vix_z"] = zz
    return f


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

    for col, tag in [("vix_z", "vixz"), ("vix_raw", "vixraw")]:
        for keep in KEEPS:
            q_hi = early_q(f, col, 1 - keep)
            q_lo = early_q(f, col, keep)
            g_hi = f[col].ge(q_hi)
            g_lo = f[col].le(q_lo)
            add(f"{tag} hi {int(keep*100)}", "risk", base & g_hi, "hi")
            add(f"{tag} lo {int(keep*100)}", "risk", base & g_lo, "lo")
            if keep == 0.20:
                cvs[f"{tag}_hi"] = slot_cv(f, base, g_hi)
                cvs[f"{tag}_lo"] = slot_cv(f, base, g_lo)
    return arms, base.to_numpy()


def redundancy(f, base_np, col):
    m = base_np & f.z_twap.notna().to_numpy() & np.isfinite(f[col].to_numpy())
    a = f.z_twap.abs().to_numpy()[m]
    b = f[col].to_numpy()[m]
    if len(a) < 100:
        return np.nan
    return float(np.corrcoef(pd.Series(a).rank(), pd.Series(b).rank())[0, 1])


def era_share_hi(f, base_np, col, keep=0.20):
    """Fraction of the top-keep (elevated) gated trades that fall in the LATE era --
    diagnoses whether a raw-level cut is really an era label."""
    q = early_q(f, col, 1 - keep)
    g = base_np & f.z_twap.notna().to_numpy() & f[col].ge(q).to_numpy()
    if g.sum() == 0:
        return np.nan
    return float(f.era.eq("late").to_numpy()[g].mean())


def analyse(pair, vix_close):
    f = add_vix(add_twap_z(build_features(pair)), vix_close)
    cov = float(np.isfinite(f.vix_z.to_numpy()).mean())
    arrays = ohlc_arrays(f)
    arms, base_np = build_arms(f)
    zp_col = f.z_twap.to_numpy()
    rows = []
    for label, family, cond, side_all, direction in arms:
        for r in run_arm(f, arrays, cond, side_all, zp_col):
            rows.append({"pair": pair, "arm": label, "family": family,
                         "direction": direction, **r})
    diag = {"pair": pair, "vix_z_coverage": cov,
            "spearman_absz_vixz": redundancy(f, base_np, "vix_z"),
            "spearman_absz_vixraw": redundancy(f, base_np, "vix_raw"),
            "late_share_vixz_hi": era_share_hi(f, base_np, "vix_z"),
            "late_share_vixraw_hi": era_share_hi(f, base_np, "vix_raw")}
    return rows, diag


def main():
    print("Loading VIX daily closes ...", flush=True)
    vix = load_vix_daily()
    print(f"   VIX closes {len(vix):,}  span {vix.index.min()} .. {vix.index.max()}",
          flush=True)

    rows, diags = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, dg = analyse(pair, vix)
        rows.extend(r)
        diags.append(dg)
    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_R"]))

    print("\n=== Redundancy with depth + VIX diagnostics ===")
    print("   (late_share ~0.5 = balanced; >>0.5 on the RAW cut = era-selector tell)")
    print(pd.DataFrame(diags).round(4).to_string(index=False))

    for exit_name in ("time", "target"):
        m0 = df[(df.exit == exit_name) & (df.delay == 0) & (df.era == "all")]
        print(f"\n=== |z_twap| frontier, {exit_name} exit, d0 (median) ===")
        fr = m0[m0.family.eq("frontier |z|")]
        print(fr.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), t=("cluster_t", "median"),
        ).reindex([f"z {k}" for k in Z_GRID]).round(4).to_string())

        print(f"\n=== Risk-regime gates on |z_twap|>=1.5, {exit_name} exit, d0 (median) ===")
        s = m0[m0.family.eq("risk")]
        print(s.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), excess_R=("excess_R", "median"),
            t=("cluster_t", "median"), clamped=("clamped", "max"),
        ).round(4).to_string())

    print("\n=== SCREEN (time exit): excess>=+0.005 R, >=3/4 pairs, delay1+late ===")
    verdict = {}
    for arm, grp in df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
                       & df.family.eq("risk")].groupby("arm"):
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
        print(f"   {arm:14s} excess {med:+.4f} R  {npos}/4  | d1 {md1:+.4f} "
              f"| late {mlate:+.4f}  -> {status}")

    print("\n=== Per-pair excess (time exit, d0): all risk arms ===")
    p = df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
           & df.family.eq("risk")].pivot_table(
               index="arm", columns="pair", values="excess_R")
    print(p.round(4).to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "axis": "6 (macro/external state), item 20 (risk-sentiment / VIX regime)",
            "baseline": "session-TWAP z_twap, horizon-scaled 3R stop, 240m hold",
            "primary_metric": "excess mean R over the |z_twap| frontier at matched rate",
            "vix_source": VIX_GLOB, "vix_trailing_sessions": VIX_TRAIL,
            "pairs": PAIRS, "z_grid": Z_GRID, "keeps": KEEPS, "base_k": BASE_K,
        },
        "diagnostics": diags, "verdicts": verdict,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
