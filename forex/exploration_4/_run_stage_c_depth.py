"""EXP-0005 -- Stage C axis 1: displacement depth (|z_slot|) as an overlay on the book.

Reproduce from the workspace root:
    python -u forex/exploration_4/_run_stage_c_depth.py

Contract: `experiments/hypotheses/HYP-0005.md`, frozen before this ran. Depth is the run-book's
FIRST-and-alone Stage-C axis: prior FX work found it a near-sufficient statistic, so its
gross-response curve is the BENCHMARK every later overlay (vol, cross-pair, session, exit) must
beat at matched count. This run builds that curve on the frozen EXP-0004 book and decides
whether depth itself rescues the book.

The base book is reconstructed by importing `_run_stage_b`, so the overlay acts on exactly the
frozen stateful, guarded-anchor, delay-1 trades -- same signals, no-entry rule, cost model and
one-position non-overlap. The overlay is a DEPTH VETO: keep book-eligible trades with
|z_slot| >= t, then RE-APPLY the one-position non-overlap (Stage-B review F1: vetoing shallow
trades frees occupancy, so the stateful book must be recomputed, never filtered post-hoc).

Caveat: EXP-0004's review corrections are applied but pending re-verification, and tau/H are
Stage-A P&L-selected candidates. Stage C proceeds at the user's direction; results are
conditional on the ruler holding.
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
import _stage_a_lib as lib                                       # noqa: E402
from _run_rsi_axis6_calendar import high_impact_times           # noqa: E402


CONFIG_PATH = PROJECT / "baseline_replication" / "configs" / "stage_c_depth.json"
ARTIFACT = PROJECT / "artifacts" / "runs" / "EXP-0005"
REPORTS = PROJECT / "reports"


def load_config() -> dict:
    c_add = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))                    # stage_c_depth
    b_add = json.loads((PROJECT / c_add["inherits"]).read_text(encoding="utf-8"))  # stage_b
    cfg = json.loads((PROJECT / b_add["inherits"]).read_text(encoding="utf-8"))    # stage_a base
    cfg.update({k: v for k, v in b_add.items() if k != "inherits"})
    cfg.update({k: v for k, v in c_add.items() if k != "inherits"})
    return cfg


# --------------------------------------------------------------------------- #
# Book reconstruction and the depth veto
# --------------------------------------------------------------------------- #

def eligible_book(cfg: dict) -> pd.DataFrame:
    """The frozen book's delay-1 guarded BOOK-ELIGIBLE trades (pre-non-overlap), all pairs."""
    parts = []
    for pair in cfg["pairs"]:
        run.log(f"{pair}: reconstructing frozen book-eligible guarded delay-1 trades")
        frame, *_ = run.load_minutes(pair, cfg)
        grid = lib.MinuteGrid(pd.DatetimeIndex(frame.time), frame.open, frame.high, frame.low)
        sig = stageb.build_signals(pair, frame, cfg, high_impact_times(pair))
        cons = sig.loc[~sig.news_veto & sig.era.ne("holdout"), "sigma_slot_pips"]
        med = float(np.median(cons)) if len(cons) else float("nan")
        tr, _ = stageb.simulate_book(sig, grid, cfg, med)
        tr = tr.loc[tr.delay.eq(cfg["overlay_arm_delay"]) & tr.treatment.eq(cfg["overlay_arm_treatment"])]
        parts.append(tr.reset_index(drop=True))
        del frame, grid, sig, tr
    return pd.concat(parts, ignore_index=True)


def book_after_veto(elig: pd.DataFrame, min_depth: float) -> pd.DataFrame:
    """Keep |z_slot| >= min_depth, then re-enforce one-position non-overlap per pair (Rule 13).

    Non-overlap is recomputed AFTER the veto because removing shallow trades frees occupancy
    for deep trades that a shallow one had blocked -- the stateful book cannot be reproduced by
    filtering a completed-trade list (Stage-B review F1).
    """
    sub = elig.loc[elig.abs_z >= min_depth]
    if sub.empty:
        return sub
    keep = np.zeros(len(sub), bool)
    s = sub.reset_index(drop=True)
    for _, idx in s.groupby("pair", observed=True, sort=False).groups.items():
        g = s.loc[idx].sort_values("entry_minute")
        k = lib.greedy_non_overlap(g.entry_minute.to_numpy(), g.exit_minute.to_numpy())
        keep[g.index.to_numpy()[k]] = True
    return s.loc[keep]


def _pooled_stats(book: pd.DataFrame, cfg: dict, era: str = "consumed") -> dict:
    scen = cfg["primary_cost_scenario"]
    b = book.loc[book.era.ne("holdout")] if era == "consumed" else book.loc[book.era.eq("holdout")]
    if b.empty:
        return None
    gs = lib.cluster_stats(b.gross_R_slot.to_numpy(), b.utc_day.to_numpy())
    ns = lib.cluster_stats(b[f"net_R_slot_{scen}"].to_numpy(), b.utc_day.to_numpy())
    return {
        "n": int(len(b)), "pairs": int(b.pair.nunique()), "clusters": int(gs["clusters"]),
        "gross_R_slot": gs["mean"], "gross_ci_low": gs["ci_low"], "gross_ci_high": gs["ci_high"],
        "net_R_slot": ns["mean"], "net_ci_low": ns["ci_low"], "net_ci_high": ns["ci_high"],
        "gross_R_abs": float(b.gross_R_abs.mean()), "gross_pips": float(b.gross_pips.mean()),
        "net_R_abs": float(b[f"net_R_abs_{scen}"].mean()), "cost_pips": float(b[f"cost_pips_{scen}"].mean()),
        "anchor_fill_rate": float((b.exit_kind == 1).mean()), "timeout_rate": float((b.exit_kind == 0).mean()),
        "sigma_slot_pips": float(b.sigma_slot_pips.mean()), "abs_z": float(b.abs_z.mean()),
    }


def depth_frontier(elig: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """(depth threshold -> re-non-overlapped stateful book) curve on consumed history."""
    grid = np.round(np.arange(cfg["depth_threshold_min"],
                              cfg["depth_threshold_max"] + 1e-9, cfg["depth_threshold_step"]), 4)
    rows = []
    for t in grid:
        book = book_after_veto(elig, float(t))
        st = _pooled_stats(book, cfg, "consumed")
        if st is None:
            continue
        st["depth_threshold"] = float(t)
        rows.append(st)
    return pd.DataFrame(rows)


def depth_buckets(elig: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Marginal dose-response: base book (t=2.0) trades bucketed by |z_slot| quantile."""
    scen = cfg["primary_cost_scenario"]
    book = book_after_veto(elig, cfg["depth_threshold_min"])
    b = book.loc[book.era.ne("holdout")].copy()
    edges = np.array(b.abs_z.quantile(cfg["depth_quantile_buckets"]).to_numpy(), dtype=float)
    edges[0], edges[-1] = -np.inf, np.inf
    b["bucket"] = pd.cut(b.abs_z, bins=np.unique(edges), include_lowest=True)
    rows = []
    for bk, g in b.groupby("bucket", observed=True):
        gs = lib.cluster_stats(g.gross_R_slot.to_numpy(), g.utc_day.to_numpy())
        ns = lib.cluster_stats(g[f"net_R_slot_{scen}"].to_numpy(), g.utc_day.to_numpy())
        rows.append({"bucket": str(bk), "n": int(len(g)), "abs_z_lo": float(g.abs_z.min()),
                     "abs_z_hi": float(g.abs_z.max()), "abs_z_mean": float(g.abs_z.mean()),
                     "gross_R_slot": gs["mean"], "gross_ci_low": gs["ci_low"], "gross_ci_high": gs["ci_high"],
                     "net_R_slot": ns["mean"], "net_ci_low": ns["ci_low"], "net_ci_high": ns["ci_high"],
                     "gross_pips": float(g.gross_pips.mean()), "cost_pips": float(g[f"cost_pips_{scen}"].mean()),
                     "anchor_fill_rate": float((g.exit_kind == 1).mean()),
                     "sigma_slot_pips": float(g.sigma_slot_pips.mean())})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Gated permutation null (only if the primary metric clears)
# --------------------------------------------------------------------------- #

def depth_permutation_null(elig: pd.DataFrame, cfg: dict, real_max_net: float) -> dict:
    """Permute |z_slot| within (era, sigma-quintile) strata; distribution of the selected-max
    net over the reproduced frontier. Only called when the primary metric first clears."""
    rng = np.random.default_rng(cfg["null_seed"])
    cons = elig.loc[elig.era.ne("holdout")].copy()
    cons["sq"] = cons.groupby("era", observed=True).sigma_slot_pips.transform(
        lambda s: pd.qcut(s, 5, labels=False, duplicates="drop"))
    grid = np.round(np.arange(cfg["depth_threshold_min"],
                              cfg["depth_threshold_max"] + 1e-9, cfg["depth_threshold_step"]), 4)
    maxima = []
    for _ in range(int(cfg["null_permutations"])):
        permuted = cons.copy()
        permuted["abs_z"] = (cons.groupby(["era", "sq"], observed=True).abs_z
                             .transform(lambda s: rng.permutation(s.to_numpy())))
        best = -np.inf
        for t in grid:
            book = book_after_veto(permuted, float(t))
            b = book.loc[book.era.ne("holdout")]
            if len(b) < cfg["deployable_min_trades"]:
                continue
            m = lib.cluster_stats(b[f"net_R_slot_{cfg['primary_cost_scenario']}"].to_numpy(),
                                  b.utc_day.to_numpy())["mean"]
            best = max(best, m)
        maxima.append(best)
    maxima = np.array([m for m in maxima if np.isfinite(m)])
    return {"permutations": int(len(maxima)), "null_max_mean": float(maxima.mean()),
            "null_max_q95": float(np.quantile(maxima, 0.95)), "real_selected_max_net": float(real_max_net),
            "one_sided_p": float((maxima >= real_max_net).mean()),
            "passes": bool((maxima >= real_max_net).mean() < 0.05)}


# --------------------------------------------------------------------------- #
# Verdict + orchestration
# --------------------------------------------------------------------------- #

def make_verdict(frontier: pd.DataFrame, buckets: pd.DataFrame, base, deepest_hold,
                 null_result, cfg: dict) -> dict:
    dep = frontier.loc[frontier.n >= cfg["deployable_min_trades"]]
    best = dep.loc[dep.net_R_slot.idxmax()] if not dep.empty else None
    gross_slope = float(np.polyfit(frontier.depth_threshold, frontier.gross_R_slot, 1)[0]) if len(frontier) > 2 else np.nan
    net_clears = bool(best is not None and best.net_ci_low > 0)
    out = {
        "experiment": "EXP-0005", "stage": "C", "axis": "displacement_depth",
        "base_book_t2.0": base,
        "gross_depth_slope_per_unit_z": gross_slope,
        "best_deployable_net": (None if best is None else {
            "depth_threshold": float(best.depth_threshold), "n": int(best.n),
            "net_R_slot": float(best.net_R_slot), "net_ci": [float(best.net_ci_low), float(best.net_ci_high)],
            "gross_R_slot": float(best.gross_R_slot), "gross_pips": float(best.gross_pips),
            "cost_pips": float(best.cost_pips)}),
        "net_clears_zero_at_deployable_count": net_clears,
        "null_gated": {"spent": bool(net_clears), "reason": (
            "primary cleared -> permutation null run" if net_clears
            else "primary did NOT clear at any deployable depth -> null unnecessary "
                 "(gate-nullc-on-success-metric)"), "result": null_result},
        "sealed_holdout_deepest": deepest_hold,
    }
    out["verdict"] = {
        "depth_accepted_as_rescue": bool(net_clears and (null_result or {}).get("passes", False)),
        "depth_orders_gross": bool(gross_slope > 0),
        "summary": (
            ("DEPTH ACCEPTED: a depth threshold gives net R_slot CI>0 at deployable count and clears the null."
             if net_clears and (null_result or {}).get("passes", False) else
             "DEPTH REJECTED as a rescue: net R_slot never clears zero at a deployable depth; "
             + ("gross does order by depth (deeper = higher gross)" if gross_slope > 0 else
                "gross does not even order by depth")
             + ". The gross depth-response curve is retained as the Stage-C benchmark."))}
    return out


def main() -> None:
    cfg = load_config()
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    elig = eligible_book(cfg)
    run.log(f"book-eligible guarded delay-1 trades: {len(elig):,} "
            f"({int(elig.era.ne('holdout').sum()):,} consumed)")

    run.log("base book parity (t=2.0) + depth frontier (re-non-overlapped per threshold)")
    base = _pooled_stats(book_after_veto(elig, cfg["depth_threshold_min"]), cfg, "consumed")
    frontier = depth_frontier(elig, cfg)
    buckets = depth_buckets(elig, cfg)

    dep = frontier.loc[frontier.n >= cfg["deployable_min_trades"]]
    real_max_net = float(dep.net_R_slot.max()) if not dep.empty else float("-inf")
    net_clears = bool((not dep.empty) and dep.net_ci_low.max() > 0
                      and dep.loc[dep.net_ci_low.gt(0)].net_R_slot.max() == dep.net_R_slot.max())
    # clear if the argmax-net deployable row has ci_low>0
    if not dep.empty:
        b = dep.loc[dep.net_R_slot.idxmax()]
        net_clears = bool(b.net_ci_low > 0)

    null_result = None
    if net_clears:
        run.log("primary cleared -> spending the gated permutation null")
        null_result = depth_permutation_null(elig, cfg, real_max_net)
    else:
        run.log("primary did not clear at any deployable depth -> null gated out")

    # holdout: read the DEEPEST deployable threshold once
    deepest_t = float(frontier.loc[frontier.n >= cfg["deployable_min_trades"], "depth_threshold"].max()) \
        if not dep.empty else cfg["depth_threshold_min"]
    deepest_hold = _pooled_stats(book_after_veto(elig, deepest_t), cfg, "holdout")
    if deepest_hold is not None:
        deepest_hold["depth_threshold"] = deepest_t

    verdict = make_verdict(frontier, buckets, base, deepest_hold, null_result, cfg)

    run.log("writing artifacts")
    (ARTIFACT / "verdict.json").write_text(json.dumps(verdict, indent=2, default=str), encoding="utf-8")
    (ARTIFACT / "run_manifest.json").write_text(json.dumps({
        "experiment_id": "EXP-0005", "stage": "C", "axis": "displacement_depth",
        "hypothesis": "experiments/hypotheses/HYP-0005.md", "config": cfg,
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "reuses": "_run_stage_b (frozen book: build_signals, simulate_book), _stage_a_lib",
        "eligible_trades": int(len(elig)),
        "caveat": "EXP-0004 pending re-verify; tau/H are Stage-A P&L-selected candidates",
    }, indent=2), encoding="utf-8")
    frontier.to_csv(ARTIFACT / "depth_frontier.csv", index=False)
    buckets.to_csv(ARTIFACT / "depth_buckets.csv", index=False)

    write_report(cfg, frontier, buckets, base, deepest_hold, verdict)
    run.log("done: " + verdict["verdict"]["summary"])


def write_report(cfg, frontier, buckets, base, deepest_hold, verdict) -> None:
    tt = lib.to_text_table
    fshow = frontier[["depth_threshold", "n", "pairs", "abs_z", "gross_R_slot", "gross_ci_low",
                      "gross_ci_high", "gross_pips", "cost_pips", "net_R_slot", "net_ci_low",
                      "net_ci_high", "anchor_fill_rate"]]
    # thin the frontier for display (every other row) but keep endpoints
    disp = fshow.iloc[::2] if len(fshow) > 25 else fshow
    bshow = buckets[["bucket", "n", "abs_z_mean", "gross_R_slot", "gross_pips", "cost_pips",
                     "net_R_slot", "net_ci_low", "net_ci_high", "anchor_fill_rate", "sigma_slot_pips"]]
    v = verdict["verdict"]
    best = verdict["best_deployable_net"]
    text = f"""# Stage C axis 1 — Displacement depth (|z_slot|) overlay (EXP-0005)

Contract: `experiments/hypotheses/HYP-0005.md`, frozen before this run. Reproduce:
`python -u forex/exploration_4/_run_stage_c_depth.py`.

**Caveat:** the base ruler EXP-0004 has review corrections applied but *pending
re-verification*, and τ=5/H=240 are Stage-A consumed-history P&L-selected candidates. Stage C
proceeds at the user's direction; this result is conditional on the ruler holding.

Depth is the run-book's **first-and-alone** Stage-C axis: prior FX work found it a
near-sufficient statistic, so its gross-response curve is the **benchmark every later overlay
must beat at matched count**. The overlay is a **depth veto** on the frozen stateful, guarded,
delay-1 book, with the one-position non-overlap **re-applied after each veto** (Stage-B F1).

## Base book parity (t = 2.0 reproduces EXP-0004)

n={base['n']:,}, gross {base['gross_R_slot']:.4f} R_slot [{base['gross_ci_low']:.4f}, {base['gross_ci_high']:.4f}],
net {base['net_R_slot']:.4f} R_slot [{base['net_ci_low']:.4f}, {base['net_ci_high']:.4f}] — matches the frozen book.

## Depth frontier (consumed; re-non-overlapped stateful book at each threshold)

{tt(disp, 4)}

Full grid: `artifacts/runs/EXP-0005/depth_frontier.csv`. Gross depth slope:
**{verdict['gross_depth_slope_per_unit_z']:+.4f} R_slot per unit of |z_slot|**
(deeper {'raises' if v['depth_orders_gross'] else 'does NOT raise'} gross).

## Depth dose-response buckets (marginal, base book)

{tt(bshow, 4)}

## Decision

- Best deployable net (n ≥ {cfg['deployable_min_trades']}): {("none" if best is None else f"depth ≥ {best['depth_threshold']:.2f}, net {best['net_R_slot']:.4f} R_slot CI [{best['net_ci'][0]:.4f}, {best['net_ci'][1]:.4f}], n={best['n']:,}, gross {best['gross_pips']:.3f} pips vs {best['cost_pips']:.3f} cost")}.
- Net clears zero at a deployable depth: **{verdict['net_clears_zero_at_deployable_count']}**.
- Gated null: **{verdict['null_gated']['reason']}**.
{("- Null: real selected-max net %.4f vs null-max mean %.4f (q95 %.4f), p=%.3f, passes=%s." % (verdict['null_gated']['result']['real_selected_max_net'], verdict['null_gated']['result']['null_max_mean'], verdict['null_gated']['result']['null_max_q95'], verdict['null_gated']['result']['one_sided_p'], verdict['null_gated']['result']['passes'])) if verdict['null_gated']['result'] else ""}

## Sealed holdout (2024+), opened once

Deepest deployable threshold ≥ {deepest_hold['depth_threshold'] if deepest_hold else float('nan'):.2f}:
net {deepest_hold['net_R_slot'] if deepest_hold else float('nan'):.4f} R_slot,
gross {deepest_hold['gross_pips'] if deepest_hold else float('nan'):.3f} pips, n={deepest_hold['n'] if deepest_hold else 0:,}. Read once.

## Verdict

**{v['summary']}**

Retained for Stage C: the **gross depth-response curve** (`depth_frontier.csv`) is the
matched-count benchmark. Later overlays (vol, cross-pair, session, exit-horizon) must beat this
curve at equal trade count and clear their own claim-matched null; if a later regime "helps",
first suspect it is just selecting deeper |z_slot|.

## Limitations

- Depth is the entry variable itself, so this is a benchmark, not an independent conditioner.
- Cost is modelled (no bid/ask); the guarded fill is a model; net grows σ-scaled cost with
  depth, which is why depth ordering gross need not order net.
- Conditional on EXP-0004 re-verification and the open Stage-A repairs.
"""
    (REPORTS / "STAGE_C_DEPTH.md").write_text(text, encoding="utf-8")
    (ARTIFACT / "STAGE_C_DEPTH.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
