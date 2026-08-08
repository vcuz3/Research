"""Axis 6, item 18 -- ECONOMIC-CALENDAR PROXIMITY conviction on the SESSION-TWAP baseline.

Axis 6 is macro / external state: conditioners built from something OUTSIDE the
price/vol state, the only lever family left after axes 1-3 (strength, vol regime,
cross-pair divergence) all proved redundant with |z_twap| depth.

Item 18: time-to-nearest scheduled HIGH-impact release as a continuous conviction
variable. Mechanism: a deep session-TWAP dislocation that fires NEAR a scheduled
high-impact release is event-driven -- it carries information and may continue (or
its "reversion" is really post-news drift), so it should revert LESS. A dislocation
FAR from any release is pure liquidity/positioning noise -> reverts MORE. So fade
only when calendar-quiet; veto near news.

CAUSALITY: uses only the release TIMING and the scheduled IMPACT tag, both known in
advance (the calendar is published ahead). It never touches the surprise/actual
VALUES, which is why the events file's uniform `historical_snapshot_not_vintage_
verified` status (a caveat on VALUES, not timing) does not bite here. The `pair`
column in fx_macro_events already maps each event to the affected pairs (a USD
release hits all four; an AUD release hits AUDUSD), so a per-pair High-impact
timestamp set is the right event universe.

Scored IDENTICALLY to axes 1-3: every gate is EXCESS mean R over the |z_twap| >= k
depth frontier interpolated in log(signals/year) to the gate's own rate -- a gate
must BEAT simply going deeper on z_twap, not merely cut trade count. Both exits
(time, target), delay 0 and 1, early/late eras. Because axis 3 turned out redundant
with depth, this run reports UP FRONT: (a) Spearman(|z_twap|, proximity) -- is the
calendar feature orthogonal to depth? and (b) per-slot selection-rate CV +
illiquid-hour tilt -- is "far from news" just reselecting the Asia/late-NY hours
(the wide-spread states from the spread-economics finding)?

Gates:
  prox hi/lo  quantile cut (early-era) on minutes-to-nearest-High -- RELATIVE
              hi = FARTHEST from news (calendar-quiet, the conviction thesis)
              lo = NEAREST to news (event-driven, should be WORSE)
  blackout W  keep trades with prox >= W minutes (outside a +-W window) -- ABSOLUTE
              fixed-window news veto; W in {15, 30, 60}; slot-CV high by design.

Consumed history; 2024+ sealed (the FX frames end 2023-12; event timestamps past
that only inform the forward-looking "time to next release", never any price).
Screen (rule 26); a survivor earns a claim-matched null next.

Reproduce:  python -u _run_rsi_axis6_calendar.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    build_features,
    ohlc_arrays,
)
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

OUT = ROOT / "rsi_axis6_calendar_results.json"
CSV = ROOT / "rsi_axis6_calendar.csv"

EVENTS = ROOT.parent / "data" / "macro" / "fx_macro_events.parquet"
BLACKOUTS = [15, 30, 60]          # +-minute veto windows around High-impact releases
PROX_CAP = 720.0                  # cap minutes-to-nearest at 12h (beyond that = "quiet")


def high_impact_times(pair):
    """Distinct sorted UTC timestamps of HIGH-impact scheduled events for `pair`."""
    m = pd.read_parquet(EVENTS, columns=["pair", "ts_utc", "impact"])
    t = m.loc[m.pair.eq(pair) & m.impact.eq("High"), "ts_utc"].dropna()
    return np.sort(t.drop_duplicates().to_numpy().astype("datetime64[m]"))


def add_calendar(f, ev_times):
    """prox_hi = minutes to the NEAREST high-impact event (min of to-next, since-last)."""
    ft = f.time.to_numpy().astype("datetime64[m]")
    ev = ev_times
    if len(ev) == 0:
        f["prox_hi"] = PROX_CAP
        return f
    pos = np.searchsorted(ev, ft, side="left")           # ev[pos] is first >= ft
    to_next = np.full(len(ft), np.inf)
    ok = pos < len(ev)
    to_next[ok] = (ev[pos[ok]] - ft[ok]) / np.timedelta64(1, "m")
    since_last = np.full(len(ft), np.inf)
    okp = pos > 0
    since_last[okp] = (ft[okp] - ev[pos[okp] - 1]) / np.timedelta64(1, "m")
    prox = np.minimum(to_next, since_last)
    f["prox_hi"] = np.clip(prox, 0, PROX_CAP)
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

    # RELATIVE proximity gates (early-era quantile cut on minutes-to-nearest-High)
    for keep in KEEPS:
        q_hi = early_q(f, "prox_hi", 1 - keep)     # farthest keep-fraction
        q_lo = early_q(f, "prox_hi", keep)         # nearest keep-fraction
        g_hi = f.prox_hi.ge(q_hi)
        g_lo = f.prox_hi.le(q_lo)
        add(f"prox hi {int(keep*100)}", "calendar", base & g_hi, "hi")
        add(f"prox lo {int(keep*100)}", "calendar", base & g_lo, "lo")
        if keep == 0.20:
            cvs["prox_hi"] = slot_cv(f, base, g_hi)
            cvs["prox_lo"] = slot_cv(f, base, g_lo)

    # ABSOLUTE blackout vetoes: keep trades OUTSIDE a +-W window around any High event
    for w in BLACKOUTS:
        g = f.prox_hi.ge(w)
        add(f"blackout {w}", "calendar", base & g, "hi")
        cvs[f"blackout_{w}"] = slot_cv(f, base, g)

    return arms, base.to_numpy(), zl, zs


def redundancy(f, base_np):
    """Spearman(|z_twap|, prox_hi) on base rows -- is proximity orthogonal to depth?"""
    m = base_np & f.z_twap.notna().to_numpy() & np.isfinite(f.prox_hi.to_numpy())
    a = f.z_twap.abs().to_numpy()[m]
    b = f.prox_hi.to_numpy()[m]
    if len(a) < 100:
        return np.nan
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def illiquid_tilt(f, base_np, cond_np):
    """Illiquid-hour (21:00-06:00 UTC) share of gated trades vs base."""
    hr = f.time.dt.hour.to_numpy()
    illiq = (hr >= 21) | (hr < 6)
    b = base_np & f.z_twap.notna().to_numpy()
    g = cond_np & b
    if g.sum() == 0 or b.sum() == 0:
        return np.nan, np.nan
    return float(illiq[g].mean()), float(illiq[g].mean() / illiq[b].mean())


def analyse(pair):
    f = add_calendar(add_twap_z(build_features(pair)), high_impact_times(pair))
    arrays = ohlc_arrays(f)
    arms, base_np, zl, zs = build_arms(f)
    zp_col = f.z_twap.to_numpy()
    rows = []
    for label, family, cond, side_all, direction in arms:
        for r in run_arm(f, arrays, cond, side_all, zp_col):
            rows.append({"pair": pair, "arm": label, "family": family,
                         "direction": direction, **r})
    # diagnostics
    diag = {"pair": pair,
            "n_high_events": int(len(high_impact_times(pair))),
            "spearman_absz_prox": redundancy(f, base_np),
            "median_prox_hi_min": float(np.nanmedian(f.prox_hi.to_numpy())),
            "base_illiq_share": None}
    hr = f.time.dt.hour.to_numpy()
    illiq = (hr >= 21) | (hr < 6)
    bm = base_np & f.z_twap.notna().to_numpy()
    diag["base_illiq_share"] = float(illiq[bm].mean())
    for label, family, cond, side_all, direction in arms:
        if family == "calendar":
            sh, tilt = illiquid_tilt(f, base_np, cond)
            diag[f"illiqtilt::{label}"] = tilt
    return rows, diag


def main():
    rows, diags = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, dg = analyse(pair)
        rows.extend(r)
        diags.append(dg)
    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_R"]))

    print("\n=== Redundancy with depth + calendar diagnostics ===")
    dd = pd.DataFrame(diags)
    show = ["pair", "n_high_events", "spearman_absz_prox", "median_prox_hi_min",
            "base_illiq_share"]
    print(dd[show].round(4).to_string(index=False))
    print("\n=== Illiquid-hour TILT of gated trades vs base (>1 = more Asia/late-NY) ===")
    tilt_cols = [c for c in dd.columns if c.startswith("illiqtilt::")]
    tt = dd[["pair"] + tilt_cols].copy()
    tt.columns = ["pair"] + [c.split("::", 1)[1] for c in tilt_cols]
    print(tt.round(2).to_string(index=False))

    for exit_name in ("time", "target"):
        m0 = df[(df.exit == exit_name) & (df.delay == 0) & (df.era == "all")]
        print(f"\n=== |z_twap| frontier, {exit_name} exit, d0 (median) ===")
        fr = m0[m0.family.eq("frontier |z|")]
        print(fr.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), t=("cluster_t", "median"),
        ).reindex([f"z {k}" for k in Z_GRID]).round(4).to_string())

        print(f"\n=== Calendar gates on |z_twap|>=1.5, {exit_name} exit, d0 (median) ===")
        s = m0[m0.family.eq("calendar")]
        print(s.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), excess_R=("excess_R", "median"),
            t=("cluster_t", "median"), clamped=("clamped", "max"),
        ).round(4).to_string())

    print("\n=== SCREEN (time exit): excess>=+0.005 R, >=3/4 pairs, delay1+late ===")
    verdict = {}
    for arm, grp in df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
                       & df.family.eq("calendar")].groupby("arm"):
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

    print("\n=== Per-pair excess (time exit, d0): all calendar arms ===")
    p = df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
           & df.family.eq("calendar")].pivot_table(
               index="arm", columns="pair", values="excess_R")
    print(p.round(4).to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "axis": "6 (macro/external state), item 18 (economic-calendar proximity)",
            "baseline": "session-TWAP z_twap, horizon-scaled 3R stop, 240m hold",
            "primary_metric": "excess mean R over the |z_twap| frontier at matched rate",
            "events_file": str(EVENTS), "impact": "High only, timing+tag only (no values)",
            "pairs": PAIRS, "z_grid": Z_GRID, "keeps": KEEPS, "base_k": BASE_K,
            "blackouts_min": BLACKOUTS, "prox_cap_min": PROX_CAP,
        },
        "diagnostics": diags, "verdicts": verdict,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
