"""EXP-0006 -- Stage C axis 2: volatility regime (compression vs expansion) overlay.

Reproduce from the workspace root:
    python -u forex/exploration_4/_run_stage_c_vol.py

Contract: `experiments/hypotheses/HYP-0006.md`, frozen before this ran. The overlay is a
REGIME VETO on the frozen EXP-0004 stateful, guarded-anchor, delay-1 book: keep trades on one
side of a same-slot-normalized ambient-volatility cut, then RE-APPLY the one-position
non-overlap (Stage-B F1). Two symmetric arms are swept -- COMPRESSION (keep lowest vr_z) and
EXPANSION (keep highest vr_z) -- and BOTH are reported (reporting only the winner would be a
hidden two-sided test).

The central risk (LEARNINGS "depth near-sufficient statistic"): because |z_slot| =
|ret|/sigma_slot, a vol-regime veto can secretly select depth. So the decision is read as
EXCESS OVER THE EXP-0005 DEPTH BENCHMARK at matched count, never versus zero, and corr(vr_z,
|z_slot|) plus the kept-set mean |z_slot| are reported as the confound control.

The regime feature vr_z is the same-slot z-score of sigma_abs (the SLOW all-hours 28,800-min
window, deliberately NOT sigma_slot which is depth's denominator), built with the identical
causal `same_slot_moments` construction used for the entry.

Caveat: EXP-0004 is pending re-verification and tau/H are Stage-A P&L-selected candidates.
Stage C proceeds at the user's direction; results are conditional on the ruler holding.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent
EXPLORATION_1 = PROJECT.parent / "exploration_1"
for _p in (str(EXPLORATION_1), str(PROJECT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _run_stage_a as run                                       # noqa: E402
import _run_stage_b as stageb                                    # noqa: E402
import _run_stage_c_depth as depth                               # noqa: E402
import _stage_a_lib as lib                                       # noqa: E402
from _run_rsi_axis6_calendar import high_impact_times            # noqa: E402


CONFIG_PATH = PROJECT / "baseline_replication" / "configs" / "stage_c_vol.json"
ARTIFACT = PROJECT / "artifacts" / "runs" / "EXP-0006"
REPORTS = PROJECT / "reports"


def load_config() -> dict:
    c_add = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))                     # stage_c_vol
    b_add = json.loads((PROJECT / c_add["inherits"]).read_text(encoding="utf-8"))   # stage_b
    cfg = json.loads((PROJECT / b_add["inherits"]).read_text(encoding="utf-8"))     # stage_a base
    cfg.update({k: v for k, v in b_add.items() if k != "inherits"})
    cfg.update({k: v for k, v in c_add.items() if k != "inherits"})
    return cfg


# --------------------------------------------------------------------------- #
# The causal same-slot vol-regime feature and book reconstruction
# --------------------------------------------------------------------------- #

def signal_vr_z(frame: pd.DataFrame, cfg: dict) -> pd.Series:
    """vr_z per grain bar: same-slot z-score of sigma_abs (the slow ambient vol).

    Same construction as the entry's `same_slot_moments`, applied to the sigma_abs SERIES
    instead of returns: trailing 90 same-slot sessions, prior sessions only, 2/3 floor. Indexed
    by the bar's integer minute-position so it can be mapped onto signals by `signal_minute`.
    """
    ohlc = frame[["time", "open", "high", "low", "close"]]
    bars, _ = lib.build_grain_bars(ohlc, cfg["tau"], cfg["sigma_window_minutes"],
                                   cfg["sigma_min_fraction"])
    sig_abs = bars["sigma"]                                  # the all-hours 28,800-min sigma
    bars_for_slot = bars.copy()
    bars_for_slot["ret"] = sig_abs                           # feed the sigma series as the "ret"
    mu, sd = lib.same_slot_moments(bars_for_slot, cfg["tau"], cfg["slot_lookback_sessions"],
                                   cfg["slot_min_fraction"])
    vr_z = (sig_abs - mu) / sd.replace(0.0, np.nan)
    minute_pos = lib.minute_positions(pd.DatetimeIndex(bars.index))
    return pd.Series(vr_z.to_numpy(), index=minute_pos)


def eligible_book(cfg: dict) -> pd.DataFrame:
    """Frozen guarded delay-1 book-eligible trades (pre-non-overlap) with vr_z attached."""
    parts = []
    for pair in cfg["pairs"]:
        run.log(f"{pair}: reconstructing frozen book-eligible trades + vr_z")
        frame, *_ = run.load_minutes(pair, cfg)
        grid = lib.MinuteGrid(pd.DatetimeIndex(frame.time), frame.open, frame.high, frame.low)
        sig = stageb.build_signals(pair, frame, cfg, high_impact_times(pair))
        vrz_by_min = signal_vr_z(frame, cfg)
        sig["vr_z"] = sig.signal_minute.map(vrz_by_min)
        cons = sig.loc[~sig.news_veto & sig.era.ne("holdout"), "sigma_slot_pips"]
        med = float(np.median(cons)) if len(cons) else float("nan")
        tr, _ = stageb.simulate_book(sig, grid, cfg, med)
        tr = tr.loc[tr.delay.eq(cfg["overlay_arm_delay"])
                    & tr.treatment.eq(cfg["overlay_arm_treatment"])].reset_index(drop=True)
        key = (sig[["entry_minute_d1", "vr_z"]]
               .rename(columns={"entry_minute_d1": "entry_minute"}))
        tr = tr.merge(key, on="entry_minute", how="left")
        parts.append(tr)
        del frame, grid, sig, tr
    return pd.concat(parts, ignore_index=True)


def re_non_overlap(sub: pd.DataFrame) -> pd.DataFrame:
    """Greedy one-position-per-pair non-overlap on a kept subset (Rule 13 / Stage-B F1)."""
    if sub.empty:
        return sub
    s = sub.reset_index(drop=True)
    keep = np.zeros(len(s), bool)
    for _, idx in s.groupby("pair", observed=True, sort=False).groups.items():
        g = s.loc[idx].sort_values("entry_minute")
        k = lib.greedy_non_overlap(g.entry_minute.to_numpy(), g.exit_minute.to_numpy())
        keep[g.index.to_numpy()[k]] = True
    return s.loc[keep]


def book_after_regime(elig: pd.DataFrame, arm: str, vr_threshold: float) -> pd.DataFrame:
    """Keep one side of the vr_z cut, then re-enforce non-overlap.

    arm='compression' keeps vr_z <= threshold (low ambient vol);
    arm='expansion'   keeps vr_z >= threshold (high ambient vol).
    """
    v = elig.vr_z
    sub = elig.loc[v <= vr_threshold] if arm == "compression" else elig.loc[v >= vr_threshold]
    return re_non_overlap(sub)


# --------------------------------------------------------------------------- #
# Frontier per arm + depth-benchmark comparison at matched count
# --------------------------------------------------------------------------- #

def regime_frontier(elig: pd.DataFrame, cfg: dict, arm: str) -> pd.DataFrame:
    """(keep-fraction -> re-non-overlapped stateful book) curve for one arm, consumed history.

    The vr_z threshold at each keep-fraction is the quantile of the CONSUMED eligible vr_z
    distribution (frozen number, applied to both eras), so counts are dialled directly and the
    holdout is read against a consumed-defined cut.
    """
    cons_vr = elig.loc[elig.era.ne("holdout"), "vr_z"].dropna()
    fracs = np.round(np.arange(cfg["keep_fraction_min"],
                               cfg["keep_fraction_max"] + 1e-9, cfg["keep_fraction_step"]), 4)
    rows = []
    for f in fracs:
        q = float(f) if arm == "compression" else float(1.0 - f)
        thr = float(cons_vr.quantile(q))
        book = book_after_regime(elig, arm, thr)
        st = depth._pooled_stats(book, cfg, "consumed")
        if st is None:
            continue
        st["keep_fraction"] = float(f)
        st["vr_threshold"] = thr
        st["arm"] = arm
        rows.append(st)
    return pd.DataFrame(rows)


def regime_buckets(elig: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Base-book trades bucketed by vr_z quantile -- the marginal regime dose-response."""
    scen = cfg["primary_cost_scenario"]
    b = re_non_overlap(elig.loc[elig.vr_z.notna()])
    b = b.loc[b.era.ne("holdout")].copy()
    edges = np.array(b.vr_z.quantile(cfg["regime_quantile_buckets"]).to_numpy(), dtype=float)
    edges[0], edges[-1] = -np.inf, np.inf
    b["bucket"] = pd.cut(b.vr_z, bins=np.unique(edges), include_lowest=True)
    rows = []
    for bk, g in b.groupby("bucket", observed=True):
        gs = lib.cluster_stats(g.gross_R_slot.to_numpy(), g.utc_day.to_numpy())
        ns = lib.cluster_stats(g[f"net_R_slot_{scen}"].to_numpy(), g.utc_day.to_numpy())
        rows.append({"bucket": str(bk), "n": int(len(g)), "vr_z_mean": float(g.vr_z.mean()),
                     "abs_z_mean": float(g.abs_z.mean()),
                     "gross_R_slot": gs["mean"], "gross_ci_low": gs["ci_low"], "gross_ci_high": gs["ci_high"],
                     "net_R_slot": ns["mean"], "net_ci_low": ns["ci_low"], "net_ci_high": ns["ci_high"],
                     "gross_pips": float(g.gross_pips.mean()), "cost_pips": float(g[f"cost_pips_{scen}"].mean()),
                     "anchor_fill_rate": float((g.exit_kind == 1).mean()),
                     "sigma_slot_pips": float(g.sigma_slot_pips.mean()),
                     "sigma_abs_pips": float(g.sigma_abs_pips.mean())})
    return pd.DataFrame(rows)


def attach_depth_excess(frontier: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    """For each regime point, read the depth benchmark at the NEAREST matched count (never
    interpolate -- np.interp clamps) and compute the gross/net excess over it."""
    if frontier.empty or bench.empty:
        return frontier
    bn = bench.n.to_numpy()
    out = frontier.copy()
    idx = [int(np.argmin(np.abs(bn - n))) for n in out.n.to_numpy()]
    out["bench_n"] = bench.n.to_numpy()[idx]
    out["bench_gross_R_slot"] = bench.gross_R_slot.to_numpy()[idx]
    out["bench_net_R_slot"] = bench.net_R_slot.to_numpy()[idx]
    out["excess_gross_R_slot"] = out.gross_R_slot - out.bench_gross_R_slot
    out["excess_net_R_slot"] = out.net_R_slot - out.bench_net_R_slot
    return out


# --------------------------------------------------------------------------- #
# Gated permutation null (only if the primary metric clears)
# --------------------------------------------------------------------------- #

def regime_permutation_null(elig: pd.DataFrame, cfg: dict, arm: str, real_max_net: float) -> dict:
    """Permute vr_z within (era, sigma_slot-quintile) strata; distribution of the selected-max
    net over the reproduced frontier for the decision arm. Only called if the primary clears."""
    rng = np.random.default_rng(cfg["null_seed"])
    cons = elig.loc[elig.era.ne("holdout") & elig.vr_z.notna()].copy()
    cons["sq"] = cons.groupby("era", observed=True).sigma_slot_pips.transform(
        lambda s: pd.qcut(s, 5, labels=False, duplicates="drop"))
    fracs = np.round(np.arange(cfg["keep_fraction_min"],
                               cfg["keep_fraction_max"] + 1e-9, cfg["keep_fraction_step"]), 4)
    scen = cfg["primary_cost_scenario"]
    maxima = []
    for _ in range(int(cfg["null_permutations"])):
        perm = cons.copy()
        perm["vr_z"] = (cons.groupby(["era", "sq"], observed=True).vr_z
                        .transform(lambda s: rng.permutation(s.to_numpy())))
        vr_cons = perm.vr_z
        best = -np.inf
        for f in fracs:
            q = float(f) if arm == "compression" else float(1.0 - f)
            thr = float(vr_cons.quantile(q))
            book = book_after_regime(perm, arm, thr)
            if len(book) < cfg["deployable_min_trades"]:
                continue
            m = lib.cluster_stats(book[f"net_R_slot_{scen}"].to_numpy(),
                                  book.utc_day.to_numpy())["mean"]
            best = max(best, m)
        maxima.append(best)
    maxima = np.array([m for m in maxima if np.isfinite(m)])
    return {"arm": arm, "permutations": int(len(maxima)),
            "null_max_mean": float(maxima.mean()) if len(maxima) else float("nan"),
            "null_max_q95": float(np.quantile(maxima, 0.95)) if len(maxima) else float("nan"),
            "real_selected_max_net": float(real_max_net),
            "one_sided_p": float((maxima >= real_max_net).mean()) if len(maxima) else float("nan"),
            "passes": bool((maxima >= real_max_net).mean() < 0.05) if len(maxima) else False}


# --------------------------------------------------------------------------- #
# Verdict + orchestration
# --------------------------------------------------------------------------- #

def _arm_best(frontier: pd.DataFrame, cfg: dict) -> dict | None:
    dep = frontier.loc[frontier.n >= cfg["deployable_min_trades"]]
    if dep.empty:
        return None
    b = dep.loc[dep.net_R_slot.idxmax()]
    return {
        "arm": str(b.arm), "keep_fraction": float(b.keep_fraction), "vr_threshold": float(b.vr_threshold),
        "n": int(b.n), "net_R_slot": float(b.net_R_slot), "net_ci": [float(b.net_ci_low), float(b.net_ci_high)],
        "gross_R_slot": float(b.gross_R_slot), "gross_pips": float(b.gross_pips), "cost_pips": float(b.cost_pips),
        "abs_z": float(b.abs_z), "bench_net_R_slot": float(b.bench_net_R_slot),
        "excess_net_R_slot": float(b.excess_net_R_slot), "excess_gross_R_slot": float(b.excess_gross_R_slot),
        "net_clears_zero": bool(b.net_ci_low > 0),
        "beats_depth_net": bool(b.excess_net_R_slot > 0),
    }


def make_verdict(fronts: dict, buckets, base, corr_vz, deepest_hold, null_result, cfg: dict) -> dict:
    arms = {arm: _arm_best(fr, cfg) for arm, fr in fronts.items()}
    accepted = False
    decision_arm = None
    for arm, best in arms.items():
        if best and best["net_clears_zero"] and best["beats_depth_net"]:
            accepted = True
            decision_arm = arm
    # gross-ordering read: does either arm's excess_gross rise as it concentrates the regime?
    out = {
        "experiment": "EXP-0006", "stage": "C", "axis": "volatility_regime",
        "base_book_full": base,
        "corr_vrz_absz_consumed": corr_vz,
        "arms_best_deployable": arms,
        "null_gated": {"spent": bool(accepted), "reason": (
            "primary cleared (net CI>0 AND beats depth at matched count) -> permutation null run"
            if accepted else
            "primary did NOT clear on either arm (net<=0 or fails to beat depth at matched "
            "count) -> null unnecessary (gate-nullc-on-success-metric)"), "result": null_result},
        "sealed_holdout": deepest_hold,
    }
    reasons = []
    for arm, best in arms.items():
        if best is None:
            reasons.append(f"{arm}: no deployable cut")
        else:
            reasons.append(
                f"{arm}: best net {best['net_R_slot']:+.3f} R_slot CI"
                f"[{best['net_ci'][0]:+.3f},{best['net_ci'][1]:+.3f}] "
                f"(clears0={best['net_clears_zero']}), excess vs depth net "
                f"{best['excess_net_R_slot']:+.3f} (beats={best['beats_depth_net']})")
    out["verdict"] = {
        "vol_regime_accepted_as_rescue": bool(accepted),
        "decision_arm": decision_arm,
        "summary": (
            (f"VOL REGIME ACCEPTED via {decision_arm}: net CI>0 at deployable count AND beats the "
             "depth benchmark at matched count"
             + (" and clears the null." if (null_result or {}).get("passes") else
                " but FAILED the permutation null.") if accepted else
             "VOL REGIME REJECTED as a rescue: on both arms, net R_slot never clears zero at a "
             "deployable count and/or fails to beat the EXP-0005 depth benchmark at matched "
             "count (i.e. any gross ordering is consistent with re-selecting depth). "
             + " | ".join(reasons))),
    }
    return out


def main() -> None:
    cfg = load_config()
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    elig = eligible_book(cfg)
    have = elig.vr_z.notna()
    run.log(f"book-eligible guarded delay-1 trades: {len(elig):,} "
            f"({int(elig.era.ne('holdout').sum()):,} consumed); vr_z available on "
            f"{int(have.sum()):,} ({have.mean()*100:.1f}%)")

    bench = pd.read_csv(PROJECT / cfg["depth_benchmark_csv"])
    base = depth._pooled_stats(re_non_overlap(elig.loc[elig.vr_z.notna()]), cfg, "consumed")

    cons = elig.loc[elig.era.ne("holdout") & elig.vr_z.notna()]
    corr_vz = float(np.corrcoef(cons.vr_z.to_numpy(), cons.abs_z.to_numpy())[0, 1])
    run.log(f"confound: corr(vr_z, |z_slot|) consumed = {corr_vz:+.4f}")

    fronts = {}
    for arm in ("compression", "expansion"):
        run.log(f"{arm} frontier (re-non-overlapped per keep-fraction)")
        fr = regime_frontier(elig, cfg, arm)
        fr = attach_depth_excess(fr, bench)
        fronts[arm] = fr
    buckets = regime_buckets(elig, cfg)

    # primary gate per arm
    def clears(fr):
        dep = fr.loc[fr.n >= cfg["deployable_min_trades"]]
        if dep.empty:
            return False, float("-inf"), None
        b = dep.loc[dep.net_R_slot.idxmax()]
        return bool(b.net_ci_low > 0 and b.excess_net_R_slot > 0), float(dep.net_R_slot.max()), str(b.arm)

    null_result = None
    decision_arm = None
    for arm, fr in fronts.items():
        ok, mx, _ = clears(fr)
        if ok:
            decision_arm = arm
            run.log(f"primary cleared on {arm} -> spending the gated permutation null")
            null_result = regime_permutation_null(elig, cfg, arm, mx)
            break
    if decision_arm is None:
        run.log("primary did not clear on either arm -> null gated out")

    # holdout: read the argmax-net deployable cut of the decision arm (or the compression arm's
    # argmax if no decision) once, using the consumed-defined threshold
    read_arm = decision_arm or "compression"
    dep = fronts[read_arm].loc[fronts[read_arm].n >= cfg["deployable_min_trades"]]
    deepest_hold = None
    if not dep.empty:
        row = dep.loc[dep.net_R_slot.idxmax()]
        book_h = book_after_regime(elig, read_arm, float(row.vr_threshold))
        deepest_hold = depth._pooled_stats(book_h, cfg, "holdout")
        if deepest_hold is not None:
            deepest_hold.update({"arm": read_arm, "keep_fraction": float(row.keep_fraction),
                                 "vr_threshold": float(row.vr_threshold)})

    verdict = make_verdict(fronts, buckets, base, corr_vz, deepest_hold, null_result, cfg)

    run.log("writing artifacts")
    (ARTIFACT / "verdict.json").write_text(json.dumps(verdict, indent=2, default=str), encoding="utf-8")
    (ARTIFACT / "run_manifest.json").write_text(json.dumps({
        "experiment_id": "EXP-0006", "stage": "C", "axis": "volatility_regime",
        "hypothesis": "experiments/hypotheses/HYP-0006.md", "config": cfg,
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "reuses": "_run_stage_b (frozen book), _run_stage_c_depth (_pooled_stats, benchmark), _stage_a_lib",
        "eligible_trades": int(len(elig)), "vr_z_available": int(have.sum()),
        "caveat": "EXP-0004 pending re-verify; tau/H are Stage-A P&L-selected candidates",
    }, indent=2), encoding="utf-8")
    for arm, fr in fronts.items():
        fr.to_csv(ARTIFACT / f"regime_frontier_{arm}.csv", index=False)
    buckets.to_csv(ARTIFACT / "regime_buckets.csv", index=False)

    write_report(cfg, fronts, buckets, base, corr_vz, deepest_hold, verdict)
    run.log("done: " + verdict["verdict"]["summary"][:120])


def write_report(cfg, fronts, buckets, base, corr_vz, deepest_hold, verdict) -> None:
    tt = lib.to_text_table
    cols = ["keep_fraction", "n", "abs_z", "gross_R_slot", "gross_pips", "cost_pips",
            "net_R_slot", "net_ci_low", "net_ci_high", "bench_net_R_slot", "excess_net_R_slot",
            "excess_gross_R_slot"]
    v = verdict["verdict"]
    arms = verdict["arms_best_deployable"]
    bshow = buckets[["bucket", "n", "vr_z_mean", "abs_z_mean", "gross_R_slot", "gross_pips",
                     "cost_pips", "net_R_slot", "net_ci_low", "net_ci_high", "sigma_abs_pips",
                     "sigma_slot_pips"]]

    def arm_line(arm):
        b = arms.get(arm)
        if b is None:
            return f"- **{arm}:** no deployable cut."
        return (f"- **{arm}:** best net {b['net_R_slot']:+.4f} R_slot "
                f"CI[{b['net_ci'][0]:+.4f},{b['net_ci'][1]:+.4f}] at keep={b['keep_fraction']:.2f} "
                f"(n={b['n']:,}, mean |z_slot|={b['abs_z']:.3f}); depth benchmark net "
                f"{b['bench_net_R_slot']:+.4f} at matched count -> **excess {b['excess_net_R_slot']:+.4f}** "
                f"(clears0={b['net_clears_zero']}, beats-depth={b['beats_depth_net']}).")

    hold = deepest_hold
    text = f"""# Stage C axis 2 — Volatility regime (compression vs expansion) overlay (EXP-0006)

Contract: `experiments/hypotheses/HYP-0006.md`, frozen before this run. Reproduce:
`python -u forex/exploration_4/_run_stage_c_vol.py`.

**Caveat:** the base ruler EXP-0004 has review corrections applied but *pending
re-verification*, and τ=5/H=240 are Stage-A consumed-history P&L-selected candidates. Stage C
proceeds at the user's direction; this result is conditional on the ruler holding.

The overlay is a **regime veto** on the frozen stateful, guarded, delay-1 book. The regime
feature `vr_z` is the **same-slot z-score of `sigma_abs`** (the slow all-hours 28,800-min
volatility — deliberately not `sigma_slot`, which is depth's denominator). Two symmetric arms
are swept and both reported: **compression** (keep lowest `vr_z`) and **expansion** (keep
highest `vr_z`), each re-non-overlapped after the veto (Stage-B F1). The decision is **excess
over the EXP-0005 depth benchmark at matched count**, not versus zero.

## Depth confound (the central control)

- **corr(vr_z, |z_slot|) on consumed eligible trades = {corr_vz:+.4f}.** A regime veto that
  changes the kept set's mean |z_slot| is (partly) a depth cut in disguise; the "excess over
  depth at matched count" columns below are the quantitative version of this control.
- Base book (all vr_z-available trades, re-non-overlapped): n={base['n']:,},
  gross {base['gross_R_slot']:+.4f} R_slot, net {base['net_R_slot']:+.4f} R_slot.

## Compression arm frontier (consumed)

{tt(fronts['compression'][cols], 4)}

## Expansion arm frontier (consumed)

{tt(fronts['expansion'][cols], 4)}

Full grids: `artifacts/runs/EXP-0006/regime_frontier_{{compression,expansion}}.csv`.
`excess_net_R_slot` = this arm's net minus the depth benchmark's net at the nearest matched
count (read from the swept `depth_frontier.csv`, never interpolated). A **positive** excess is
the only way a regime beats simply ranking by depth.

## Regime dose-response buckets (marginal, base book, by vr_z quantile)

{tt(bshow, 4)}

Read `abs_z_mean` across buckets: if it trends with `vr_z`, the regime is entangled with depth.

## Decision

{arm_line('compression')}
{arm_line('expansion')}

- Gated null: **{verdict['null_gated']['reason']}**.
{("- Null (%s): real selected-max net %.4f vs null-max mean %.4f (q95 %.4f), p=%.3f, passes=%s." % (verdict['null_gated']['result']['arm'], verdict['null_gated']['result']['real_selected_max_net'], verdict['null_gated']['result']['null_max_mean'], verdict['null_gated']['result']['null_max_q95'], verdict['null_gated']['result']['one_sided_p'], verdict['null_gated']['result']['passes'])) if verdict['null_gated']['result'] else ""}

## Sealed holdout (2024+), opened once

{("Read arm=%s keep=%.2f: net %.4f R_slot, gross %.3f pips, n=%d." % (hold['arm'], hold['keep_fraction'], hold['net_R_slot'], hold['gross_pips'], hold['n'])) if hold else "No deployable cut to read."}

## Verdict

**{v['summary']}**

Interpretation: this is the expected outcome under the honest prior (run-book §7) if it
rejects — the ambient-vol regime does not separate capturable from un-capturable reversion
beyond what depth already does, and the ~1.25-pip modelled cost dwarfs any gross ordering. If
a regime "helped", the confound control above is where to look first.

## Limitations

- `vr_z` is built on `sigma_abs`; a regime measured on a shorter ambient window is a distinct,
  untested feature. Cost is modelled (no bid/ask); the guarded fill is a model.
- The keep-fraction cut uses the consumed vr_z sample quantile (a two-sided sample statistic);
  the holdout applies the consumed-frozen threshold.
- Conditional on EXP-0004 re-verification and the Stage-A repairs.
"""
    (REPORTS / "STAGE_C_VOL.md").write_text(text, encoding="utf-8")
    (ARTIFACT / "STAGE_C_VOL.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
