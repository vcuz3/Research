"""Arm 3: cross-pair coherence as a regime filter, event clock, compulsory stop.

All four pairs are quoted against USD, so a USD repricing moves all four the same
way. The preregistered claim (RSI_COHERENCE_TIMEEXIT_SPEC.md) is that a
displacement SHARED with the other three pairs is a macro move that continues,
while a displacement SPECIFIC to one pair is the noise event this strategy fades.
That is the direct test of "gate the signal if we are entering a new trending
regime" using the only genuinely cross-sectional information in the dataset.

The feature excludes the own pair from the basket, so it cannot mechanically
restate |z|.

Controls, all declared before the run:
  1. a volatility-matched split (within vol quintile as well as within slot);
  2. a rate-matched own-pair-only control (tighten |z| to the same keep fraction);
  3. a re-pairing null: the other three pairs' state taken from a DIFFERENT date
     at the same slot and era, which destroys contemporaneous cross-information
     while preserving every leg's own dynamics and this pair's whole simulation.

Reproduce with:
    python -u _run_rsi_coherence_gate.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    COSTS,
    build_features,
    condition,
    expansion_cutpoint,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    slot_pct,
    unitfree_move,
    years_of,
)
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_coherence_gate_results.json"
CELL_CSV = ROOT / "rsi_coherence_cells.csv"
NULL_CSV = ROOT / "rsi_coherence_null.csv"

STOP_K = 2.0            # primary, declared in the spec
SLIPPAGE = 1.0          # primary
STOP_GRID = [1.0, 1.5, 2.0, 3.0, np.inf]
N_TERCILE = 3
N_QUINTILE = 5
NULL_DRAWS = 200
SEED = 20260804
KINDS = ["gated", "rsi3070"]


def bucket_by(series, k):
    """Equal-sized rank buckets 0..k-1; NaN stays NaN."""
    r = series.rank(method="first", pct=True)
    return (np.ceil(r * k) - 1).clip(0, k - 1).where(series.notna())


def add_coherence(frame, others_u, pair):
    """Cross-pair state on the FULL minute grid, own pair excluded.

    The same-slot percentile must be estimated from every minute at that time of
    day, not from the selected events: an event sample is scattered over 1440
    session minutes, so a 90-session same-slot window is almost never populated
    and the feature would survive on ~3% of signals -- and those survivors are
    themselves concentrated on the round-clock minutes this project has just
    finished removing.

    `frame.time` is tz-aware and must stay so: reindexing a tz-aware index with
    `.values` (tz-naive) silently matches nothing.
    """
    stamps = pd.DatetimeIndex(frame.time)
    o = pd.concat([others_u[q].reindex(stamps) for q in PAIRS if q != pair], axis=1)
    o.index = frame.index
    frame["n_others"] = o.notna().sum(axis=1).to_numpy()
    frame["others_u"] = o.mean(axis=1, skipna=False).to_numpy()   # require all three
    frame["coh"] = np.sign(frame.u) * frame.others_u
    frame["coh_pct"] = slot_pct(frame, "coh")
    return frame


def build_events(pair, others_u, kind):
    frame = add_coherence(build_features(pair), others_u, pair)
    grid_coverage = float(frame.coh_pct.notna().mean())
    cut = expansion_cutpoint(frame)
    cond, side_all = condition(frame, kind, cut)
    idx = select_events(frame, cond)
    arrays = ohlc_arrays(frame)
    d, paths = extract(frame, arrays, idx)
    d["side"] = side_all[idx]

    n_events = len(d)
    keep = d.coh_pct.notna().to_numpy()
    d2 = d.loc[keep].reset_index(drop=True)
    paths2 = {k: v[keep] for k, v in paths.items()}
    diag = {
        "pair": pair, "signal": kind,
        "crossings_admitted": int(n_events),
        "with_coherence": int(len(d2)),
        "coh_coverage": float(len(d2) / max(n_events, 1)),
        "coh_coverage_full_grid": grid_coverage,
        "expansion_cut_early_fitted": cut,
        "median_gap_between_entries_min": float(
            pd.Series(d2.time).diff().dt.total_seconds().div(60).median()),
        "phase30_top_share": float(d2.phase30.value_counts(normalize=True).max()),
        "phase30_share_at_29": float(d2.phase30.eq(29).mean()),
        "spearman_coh_absz": float(pd.Series(d2.coh_pct.values).corr(
            pd.Series(d2.z.abs().values), method="spearman")),
        "spearman_coh_volpct": float(pd.Series(d2.coh_pct.values).corr(
            pd.Series(d2.vol_pct.values), method="spearman")),
    }
    return d2, paths2, diag


def analyse(pair, d, paths):
    years = years_of(d)
    side = d.side.to_numpy()
    sd = d.sdate.values
    rows = []

    for delay in (0, 1):
        pp = shift_paths(paths, delay)
        sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
        for k_stop in STOP_GRID:
            slips = [0.0, SLIPPAGE] if np.isfinite(k_stop) else [0.0]
            for slip in slips:
                pnl, stopped, _ = simulate(pp, side, k_stop * sg, 30, slip)
                base = dict(pair=pair, delay=delay, stop_R=float(k_stop), slippage=slip)
                rows.append({**base, "split": "none", "cell": "ALL",
                             **metrics(pnl, sg, sd, years, stopped)})

                if k_stop != STOP_K or slip != SLIPPAGE:
                    continue

                ter = bucket_by(d.coh_pct, N_TERCILE)
                for c in range(N_TERCILE):
                    m = ter.eq(c).to_numpy()
                    rows.append({**base, "split": "coh_tercile", "cell": f"T{c + 1}",
                                 **metrics(pnl[m], sg[m], sd[m], years, stopped[m])})
                qui = bucket_by(d.coh_pct, N_QUINTILE)
                for c in range(N_QUINTILE):
                    m = qui.eq(c).to_numpy()
                    rows.append({**base, "split": "coh_quintile", "cell": f"Q{c + 1}",
                                 **metrics(pnl[m], sg[m], sd[m], years, stopped[m])})

                # volatility-matched: terciles formed WITHIN vol quintiles, so the
                # cells have identical volatility composition
                volq = bucket_by(d.vol_pct, N_QUINTILE)
                ter_v = pd.DataFrame({"coh_pct": d.coh_pct.values, "volq": volq.values}) \
                    .groupby("volq", observed=True)["coh_pct"] \
                    .transform(lambda s: bucket_by(s, N_TERCILE))
                for c in range(N_TERCILE):
                    m = ter_v.eq(c).to_numpy()
                    rows.append({**base, "split": "coh_tercile_volmatched",
                                 "cell": f"T{c + 1}",
                                 **metrics(pnl[m], sg[m], sd[m], years, stopped[m])})

                # rate-matched own-pair-only control
                absz = d.z.abs()
                m = absz.ge(absz.quantile(1 - 1.0 / N_TERCILE)).to_numpy()
                rows.append({**base, "split": "CTRL own |z| deepen", "cell": "kept",
                             **metrics(pnl[m], sg[m], sd[m], years, stopped[m])})

                for era in ["early", "late"]:
                    em = d.era.eq(era).to_numpy()
                    yrs = d.loc[em].sdate.nunique() / 252
                    rows.append({**base, "split": f"era_{era}", "cell": "ALL",
                                 **metrics(pnl[em], sg[em], sd[em], yrs, stopped[em])})
                    for c in range(N_TERCILE):
                        m = em & ter.eq(c).to_numpy()
                        rows.append({**base, "split": f"coh_tercile_{era}",
                                     "cell": f"T{c + 1}",
                                     **metrics(pnl[m], sg[m], sd[m], yrs, stopped[m])})
    return rows


def repairing_null(pair, d, paths, rng):
    """Donor-matched re-pairing: the other three pairs' state is taken from a
    different DATE at the same slot and era. Destroys contemporaneous cross-pair
    information; preserves each leg's marginal distribution and this pair's entire
    path, signal set and stop simulation."""
    sg = d.sigma_pips.to_numpy()
    pnl, _, _ = simulate(paths, d.side.to_numpy(), STOP_K * sg, 30, SLIPPAGE)
    r_real = pnl / sg

    def gap(bucket):
        return float(np.nanmean(r_real[bucket == 0]) - np.nanmean(r_real[bucket == 2]))

    real_causal = gap(bucket_by(d.coh_pct, N_TERCILE).to_numpy())

    # The null cannot use the 90-session causal percentile (its donor history is
    # scrambled), so both the null and the real value it is compared against use a
    # within-slot-hour rank of the raw coherence. Reported side by side.
    hour = (d.session_minute // 60).to_numpy()
    sign_own, others = np.sign(d.u.to_numpy()), d.others_u.to_numpy()

    def slot_bucket(vals):
        return pd.DataFrame({"v": vals, "h": hour}).groupby("h", observed=True)["v"] \
            .transform(lambda s: bucket_by(s, N_TERCILE)).to_numpy()

    real_matched = gap(slot_bucket(sign_own * others))

    groups = list(d.groupby([d.session_minute // 60, d.era], observed=True).indices.values())
    draws = np.empty(NULL_DRAWS)
    for t in range(NULL_DRAWS):
        perm = np.arange(len(d))
        for pos in groups:
            if len(pos) > 1:
                perm[pos] = pos[rng.permutation(len(pos))]
        draws[t] = gap(slot_bucket(sign_own * others[perm]))

    lo, hi = float(np.quantile(draws, 0.05)), float(np.quantile(draws, 0.95))
    return {
        "pair": pair,
        "real_gap_R_causal_pct": real_causal,
        "real_gap_R_slot_rank": real_matched,
        "null_mean": float(draws.mean()),
        "null_sd": float(draws.std(ddof=1)),
        "null_p05": lo, "null_p95": hi,
        "frac_null_ge_real": float((draws >= real_matched).mean()),
        "outside_central_90": bool(real_matched < lo or real_matched > hi),
        "draws": draws.tolist(),
    }


def main():
    rng = np.random.default_rng(SEED)
    print("Pass 1: unit-free moves for the cross-pair basket ...", flush=True)
    others_u = {p: unitfree_move(p) for p in PAIRS}

    all_rows, diags, nulls = [], [], []
    for kind in KINDS:
        for pair in PAIRS:
            print(f"Pass 2: {pair} / {kind} ...", flush=True)
            d, paths, diag = build_events(pair, others_u, kind)
            diags.append(diag)
            for r in analyse(pair, d, paths):
                all_rows.append({**r, "signal": kind})
            if kind == "gated":
                print(f"   re-pairing null {pair} ...", flush=True)
                nulls.append(repairing_null(pair, d, paths, rng))

    df = pd.DataFrame(all_rows).dropna(subset=["mean_pips"])

    print("\n=== Diagnostics: event clock, coverage, phase placebo, redundancy ===")
    print(pd.DataFrame(diags).round(4).to_string(index=False))

    print("\n=== 0. Rule-23: event-clock RSI 30/70, no stop, by era ===")
    print("   published all-phase first crossing: 0.397-0.418 early, 0.220-0.341 late "
          "(EURUSD/GBPUSD)")
    rep = df.loc[df.signal.eq("rsi3070") & ~np.isfinite(df.stop_R) & df.delay.eq(0)
                 & df.split.isin(["era_early", "era_late", "none"])]
    print(rep[["pair", "split", "signals", "signals_per_year", "mean_pips", "mean_R",
               "cluster_t"]].round(4).to_string(index=False))

    print("\n=== 1. Cost of the compulsory stop (median across pairs) ===")
    for kind in KINDS:
        s = df.loc[df.signal.eq(kind) & df.split.eq("none") & df.delay.eq(0)]
        print(f"\n-- {kind} --")
        print(s.groupby(["stop_R", "slippage"]).agg(
            per_year=("signals_per_year", "median"),
            stopped=("stopped_frac", "median"),
            mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"),
            risk_unit=("implied_risk_unit_pips", "median"),
            cluster_t=("cluster_t", "median"),
            sharpe=("per_signal_sharpe", "median"),
            worst_5pct=("worst_5pct_share", "median"),
            max_dd_R=("max_drawdown_R", "median"),
            net_05=("net_0.5_pips", "median"),
        ).round(3).to_string())

    print("\n=== 1b. One-minute entry delay at the primary stop (median across pairs) ===")
    s = df.loc[df.split.eq("none") & df.stop_R.eq(STOP_K) & df.slippage.eq(SLIPPAGE)]
    print(s.groupby(["signal", "delay"]).agg(
        mean_pips=("mean_pips", "median"), mean_R=("mean_R", "median"),
        cluster_t=("cluster_t", "median"), hit_rate=("hit_rate", "median"),
    ).round(3).to_string())

    prim = df.loc[df.stop_R.eq(STOP_K) & df.slippage.eq(SLIPPAGE)]
    print(f"\n=== 2. Coherence split at stop {STOP_K} R, {SLIPPAGE} pip slippage ===")
    print("   T1 = idiosyncratic (moves against the basket); T3 = broad USD move")
    for kind in KINDS:
        for split in ["coh_tercile", "coh_quintile", "coh_tercile_volmatched"]:
            s = prim.loc[prim.signal.eq(kind) & prim.split.eq(split) & prim.delay.eq(0)]
            if s.empty:
                continue
            print(f"\n-- {kind} / {split} (median across pairs) --")
            print(s.groupby("cell").agg(
                per_year=("signals_per_year", "median"),
                stopped=("stopped_frac", "median"),
                mean_pips=("mean_pips", "median"),
                mean_R=("mean_R", "median"),
                risk_unit=("implied_risk_unit_pips", "median"),
                cluster_t=("cluster_t", "median"),
                hit_rate=("hit_rate", "median"),
                worst_5pct=("worst_5pct_share", "median"),
            ).round(3).to_string())

    print("\n=== 3. KILL TEST (mean R, T1 minus T3) ===")
    verdict = {}
    for kind in KINDS:
        v = {}
        for delay in (0, 1):
            for split in ["coh_tercile", "coh_tercile_volmatched"]:
                s = prim.loc[prim.signal.eq(kind) & prim.split.eq(split) & prim.delay.eq(delay)]
                if s.empty:
                    continue
                w = s.pivot_table(index="pair", columns="cell", values="mean_R")
                p = s.pivot_table(index="pair", columns="cell", values="mean_pips")
                if not {"T1", "T3"} <= set(w.columns):
                    continue
                w["gap_R"] = w["T1"] - w["T3"]
                w["gap_pips"] = p["T1"] - p["T3"]
                v[f"{split}_delay{delay}"] = {
                    "median_gap_R": float(w["gap_R"].median()),
                    "pairs_positive": int((w["gap_R"] > 0).sum()),
                    "median_gap_pips": float(w["gap_pips"].median()),
                }
                if delay == 0:
                    print(f"\n-- {kind} / {split} per pair --")
                    print(w.round(4).to_string())
            ctl = prim.loc[prim.signal.eq(kind) & prim.split.eq("CTRL own |z| deepen")
                           & prim.delay.eq(delay)]
            t1 = prim.loc[prim.signal.eq(kind) & prim.split.eq("coh_tercile")
                          & prim.cell.eq("T1") & prim.delay.eq(delay)]
            if not ctl.empty and not t1.empty:
                m = t1.set_index("pair").mean_R - ctl.set_index("pair").mean_R
                v[f"vs_own_control_delay{delay}"] = {
                    "median": float(m.median()), "pairs_positive": int((m > 0).sum())}
        base = v.get("coh_tercile_delay0", {})
        vm = v.get("coh_tercile_volmatched_delay0", {})
        ctlv = v.get("vs_own_control_delay0", {})
        retain = (vm.get("median_gap_R", np.nan) / base["median_gap_R"]
                  if base.get("median_gap_R") else np.nan)
        v["volmatched_retention"] = float(retain)
        v["criteria"] = {
            "1 T1 beats T3 in >=3/4 and median gap >= +0.02 R":
                bool(base.get("pairs_positive", 0) >= 3
                     and base.get("median_gap_R", 0) >= 0.02),
            "2 >=50% retained under the volatility-matched split":
                bool(np.isfinite(retain) and retain >= 0.5),
            "3 beats the rate-matched own-|z| control in >=3/4":
                bool(ctlv.get("pairs_positive", 0) >= 3),
        }
        verdict[kind] = v
        print(f"\n-- {kind} verdict --")
        print(f"   plain gap        median {base.get('median_gap_R', float('nan')):+.4f} R, "
              f"{base.get('pairs_positive', 0)}/4 pairs")
        print(f"   vol-matched gap  median {vm.get('median_gap_R', float('nan')):+.4f} R "
              f"(retention {retain:.2f})")
        print(f"   vs own-|z| ctrl  median {ctlv.get('median', float('nan')):+.4f} R, "
              f"{ctlv.get('pairs_positive', 0)}/4 pairs")
        for k, ok in v["criteria"].items():
            print(f"   [{'PASS' if ok else 'FAIL'}] {k}")

    print(f"\n=== 4. Re-pairing null (gated, {NULL_DRAWS} donor-matched draws) ===")
    nd = pd.DataFrame([{k: x[k] for k in x if k != "draws"} for x in nulls])
    print(nd.round(4).to_string(index=False))
    crit4 = bool(nd.outside_central_90.sum() >= 3)
    print(f"   [{'PASS' if crit4 else 'FAIL'}] 4 real gap outside the null in >=3/4 pairs")

    print("\n=== 5. Era split, gated, primary stop ===")
    for era in ["early", "late"]:
        s = prim.loc[prim.signal.eq("gated") & prim.split.eq(f"coh_tercile_{era}")
                     & prim.delay.eq(0)]
        if s.empty:
            continue
        print(f"\n-- {era} --")
        print(s.groupby("cell").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), cluster_t=("cluster_t", "median"),
        ).round(3).to_string())

    df.to_csv(CELL_CSV, index=False)
    nd.to_csv(NULL_CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_COHERENCE_TIMEEXIT_SPEC.md (arm 3)",
            "pairs": PAIRS,
            "clock": "event: first minute the entry condition becomes true, non-overlapping",
            "stop_R_primary": STOP_K, "slippage_pips_primary": SLIPPAGE,
            "stop_grid": [float(x) for x in STOP_GRID],
            "null_draws": NULL_DRAWS, "seed": SEED, "costs_pips": COSTS,
            "feature": ("coh = sign(own 30-min unit-free move) x mean of the OTHER three "
                        "pairs' unit-free 30-min move, then a causal same-slot percentile "
                        "over 90 prior sessions"),
        },
        "diagnostics": diags,
        "verdicts": verdict,
        "null_criterion_passed": crit4,
        "nulls": nulls,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
