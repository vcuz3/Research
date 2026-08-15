"""EXP-0004 -- Stage B: freeze ONE honest same-slot z-fade reference book.

Reproduce from the workspace root:
    python -u forex/exploration_4/_run_stage_b.py

Contract: `experiments/hypotheses/HYP-0004.md` and `artifacts/runs/EXP-0004/KILL_TEST.md`,
both frozen before this ran. This is the RULER Stage C's overlays are measured against.
Every entry/feature/grain parameter is INHERITED from Stage A, where tau=5 / H=240 were
selected on consumed-history gross P&L (Stage-A review finding 1); they are a frozen
consumed-history candidate, NOT an untuned or confirmed choice. Stage B adds no new P&L
tuning: the exit, guard, vetoes and estimand are fixed by fiat.

Corrections applied after Codex's independent review (`artifacts/runs/EXP-0004/review.md`
= review response; `independent_review_codex.md` = the review):
  * F1 the book estimand is now the STATEFUL one-position-per-pair set (greedy non-overlap
    applied before every book-labelled metric); the all-signal per-signal mean is kept only
    as a labelled diagnostic.
  * F2 signals whose anchor is already crossed at the (delayed) entry are a causal NO-ENTRY
    (`_stage_b_lib.anchor_favourable`), not held to the cap.
  * F2/cost the cost vol-ratio median is computed from the CONSUMED era only, so the sealed
    2024+ holdout no longer leaks into pre-2024 cost/net columns.
  * F4 a rerunnable Rule-9a exclusion funnel is emitted (news / no-entry / zero-cap /
    incomplete-path / Friday-shortened / non-overlap), by pair, era and UTC hour.
  * F3/minor the touch and time arms are DIAGNOSTIC COMPARATORS, not payoff bounds; a CI
    containing zero means positive reversion is NOT ESTABLISHED (not "absent"); a negative
    gross means a rebate, not a nonnegative breakeven round trip.

The anchor-retrace fill lives in `_stage_b_lib.simulate_anchor_retrace` (parity-tested in
`test_stage_b.py`); loading, same-slot moments, first-crossing, the cluster-robust estimand,
cell pooling and the cost model are imported from the audited Stage-A / exploration_1 code.
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
import _stage_a_lib as lib                                       # noqa: E402
import _stage_b_lib as sb                                        # noqa: E402
from _cost_model import CostParams, round_trip_pips              # noqa: E402
from _run_rsi_axis6_calendar import high_impact_times            # noqa: E402
from _run_rsi_broad_regime_sweep import PIP                      # noqa: E402


CONFIG_PATH = PROJECT / "baseline_replication" / "configs" / "stage_b.json"
ARTIFACT = PROJECT / "artifacts" / "runs" / "EXP-0004"
REPORTS = PROJECT / "reports"

GROUP = ["pair", "era", "session", "delay", "treatment"]
ERA_TO_COST_ERA = run.ERA_TO_COST_ERA


def load_config() -> dict:
    add = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg = json.loads((PROJECT / add["inherits"]).read_text(encoding="utf-8"))
    cfg.update({k: v for k, v in add.items() if k != "inherits"})
    return cfg


# --------------------------------------------------------------------------- #
# Signals: tau=5, same-slot z, first crossing at k=2.0
# --------------------------------------------------------------------------- #

def build_signals(pair: str, frame: pd.DataFrame, cfg: dict, news: np.ndarray) -> pd.DataFrame:
    """One row per first-crossing signal, carrying both entry arms' anchors and prices.

    The decision sample is the bars where the same-slot moments are warmed up and the bar is
    complete; the signal is the first crossing of ``|z_slot| >= k`` on that sample. Anchor,
    sigma_slot and sigma_abs are read at the SIGNAL bar (causal); entry prices/times are read
    at the delay-0 and delay-1 entry bars.
    """
    tau, k = cfg["tau"], cfg["entry_k"]
    ohlc = frame[["time", "open", "high", "low", "close"]]
    bars, meta = lib.build_grain_bars(ohlc, tau, cfg["sigma_window_minutes"], cfg["sigma_min_fraction"])
    bidx = pd.DatetimeIndex(bars.index)
    era = lib.era_of(bidx, run.naive_ts(cfg["era_split"]), run.naive_ts(cfg["holdout_start"]))
    sess = np.asarray(lib.SESSION_LABELS, dtype=object)[lib.session_codes(bidx, cfg["sessions"])]
    decision = np.asarray(bidx >= run.naive_ts(cfg["start"]))

    mu, sd = lib.same_slot_moments(bars, tau, cfg["slot_lookback_sessions"], cfg["slot_min_fraction"])
    z_slot = (bars.ret - mu) / sd.replace(0.0, np.nan)
    usable = pd.Series(decision & bars.complete.to_numpy(bool)
                       & bars.sigma.notna().to_numpy() & sd.notna().to_numpy()
                       & z_slot.notna().to_numpy(), index=bars.index)
    contig = bars.contiguous & usable

    s = lib.first_crossing(z_slot.where(usable), usable, contig, float(k))
    s = s[(s - 1 >= 0) & (s + 2 < len(bars))]
    if len(s) == 0:
        return pd.DataFrame()

    closes, opens = bars.close.to_numpy(float), bars.open.to_numpy(float)
    complete = bars.complete.to_numpy(bool)
    sig_abs = bars.sigma.to_numpy(float)
    sig_slot = sd.to_numpy(float)
    bar_minutes = lib.minute_positions(bidx)

    ok = complete[s + 1] & complete[s + 2] & np.isfinite(sig_abs[s]) & (sig_abs[s] > 0) \
        & np.isfinite(sig_slot[s]) & (sig_slot[s] > 0)
    s = s[ok]
    if len(s) == 0:
        return pd.DataFrame()

    d = pd.DataFrame({
        "pair": pair, "tau": tau, "k": k,
        "signal_time": bidx[s], "signal_minute": bar_minutes[s],
        "anchor_price": closes[s - 1],
        "sigma_abs": sig_abs[s], "sigma_slot": sig_slot[s],
        "z_signal": z_slot.to_numpy()[s],
        "era": era[s + 1], "session": sess[s + 1], "utc_day": bidx[s + 1].floor("D"),
    })
    d["side"] = np.where(d.z_signal < 0, 1.0, -1.0)
    for delay in cfg["entry_delay_bars"]:
        e = s + 1 + delay
        ny = pd.DatetimeIndex(bidx[e]).tz_localize("UTC").tz_convert("America/New_York")
        d[f"entry_minute_d{delay}"] = bar_minutes[e]
        d[f"entry_price_d{delay}"] = opens[e]
        d[f"entry_utc_hour_d{delay}"] = bidx[e].hour
        d[f"ny_weekday_d{delay}"] = ny.weekday.to_numpy()
        d[f"ny_minute_d{delay}"] = ny.hour.to_numpy() * 60 + ny.minute.to_numpy()

    d["sigma_slot_pips"] = d.sigma_slot * d.entry_price_d0 / PIP
    d["sigma_abs_pips"] = d.sigma_abs * d.entry_price_d0 / PIP
    d["news_distance_minutes"] = run.nearest_event_minutes(pd.DatetimeIndex(d.signal_time), news)
    d["news_veto"] = d.news_distance_minutes < cfg["news_blackout_minutes"]
    return d


# --------------------------------------------------------------------------- #
# Book simulation with the causal no-entry filter and an exclusion funnel
# --------------------------------------------------------------------------- #

def simulate_book(sig: pd.DataFrame, grid: lib.MinuteGrid, cfg: dict,
                  consumed_median_slot_pips: float):
    """Per-signal x delay x treatment trades, plus a Rule-9a exclusion funnel.

    Order of the causal funnel (all conditions known at or before entry): news veto ->
    Friday zero-cap -> already-crossed anchor no-entry -> incomplete forward path ->
    book-eligible (of which some are Friday-shortened). Non-overlap is applied later, on the
    pooled trades, so its reduction is reported separately.
    """
    cap0 = int(cfg["holding_cap_minutes"])
    g = float(cfg["anchor_guard_sigma"])
    flat = int(cfg["friday_flat_ny_minute"])
    pair = sig.pair.iloc[0]

    base = sig.reset_index(drop=True)
    anchor = base.anchor_price.to_numpy(float)
    side = base.side.to_numpy(float)
    sig_slot = base.sigma_slot.to_numpy(float)
    sig_abs = base.sigma_abs.to_numpy(float)
    era = base.era.to_numpy()
    post_veto = ~base.news_veto.to_numpy(bool)

    trade_parts, excl_parts = [], []
    for delay in cfg["entry_delay_bars"]:
        entry_min = base[f"entry_minute_d{delay}"].to_numpy(np.int64)
        entry_px = base[f"entry_price_d{delay}"].to_numpy(float)
        hour = base[f"entry_utc_hour_d{delay}"].to_numpy()
        cap = sb.friday_cap_minutes(base[f"ny_weekday_d{delay}"].to_numpy(),
                                    base[f"ny_minute_d{delay}"].to_numpy(), cap0, flat)
        off = grid.offsets(entry_min)
        fav = sb.anchor_favourable(side, entry_px, anchor)

        zero_cap = post_veto & (cap <= 0)
        avail = post_veto & (cap > 0)
        no_entry = avail & ~fav
        entered = avail & fav
        path_ok = np.zeros(len(base), bool)
        path_ok[entered] = grid.path_complete_span(off[entered], off[entered] + cap[entered])
        incomplete = entered & ~path_ok
        eligible = entered & path_ok
        friday_short = eligible & (cap < cap0)

        # -- exclusion funnel by (era, utc_hour) ------------------------------ #
        ex = pd.DataFrame({
            "pair": pair, "delay": delay, "era": era, "utc_hour": hour,
            "signals_pre_veto": 1, "news_vetoed": (~post_veto).astype(int),
            "zero_cap_friday": zero_cap.astype(int), "no_entry_already_crossed": no_entry.astype(int),
            "incomplete_path": incomplete.astype(int), "book_eligible": eligible.astype(int),
            "friday_shortened": friday_short.astype(int),
        }).groupby(["pair", "delay", "era", "utc_hour"], observed=True).sum().reset_index()
        excl_parts.append(ex)

        idx = np.flatnonzero(eligible)
        if len(idx) == 0:
            continue
        guard_px = g * sig_slot[idx] * entry_px[idx]
        cost_era = base.era.map(ERA_TO_COST_ERA).to_numpy()[idx]
        vol_ratio = np.where(consumed_median_slot_pips > 0,
                             base.sigma_slot_pips.to_numpy()[idx] / consumed_median_slot_pips, 1.0)
        cost_pips = {scen: round_trip_pips(pair, hour[idx], cost_era, vol_ratio,
                                           CostParams(scenario=scen)) for scen in cfg["cost_scenarios"]}

        for treatment in cfg["exit_treatments"]:
            pnl = np.full(len(idx), np.nan)
            kind = np.zeros(len(idx), int)
            exitbar = np.zeros(len(idx), int)
            batch = max(200, int(2_000_000 / (cap0 + 1)))
            for a in range(0, len(idx), batch):
                sl = slice(a, min(a + batch, len(idx)))
                rows = idx[sl]
                paths = grid.extract_paths(off[rows], cap0)
                p, kd, xb = sb.simulate_anchor_retrace(
                    paths, side[rows], entry_px[rows], anchor[rows], guard_px[sl],
                    cap[rows], mode=treatment, pip=PIP)
                pnl[sl], kind[sl], exitbar[sl] = p, kd, xb
                del paths
            t = base.iloc[idx][["pair", "era", "session", "tau", "k", "utc_day",
                                "z_signal", "sigma_slot_pips", "sigma_abs_pips"]].copy()
            t["delay"] = delay
            t["treatment"] = treatment
            t["entry_minute"] = entry_min[idx]
            t["cap_minutes"] = cap[idx]
            t["exit_minute"] = entry_min[idx] + exitbar
            t["exit_kind"] = kind
            t["gross_pips"] = pnl
            t["gross_R_slot"] = pnl * PIP / (sig_slot[idx] * entry_px[idx])
            t["gross_R_abs"] = pnl * PIP / (sig_abs[idx] * entry_px[idx])
            t["abs_z"] = np.abs(base.z_signal.to_numpy()[idx])
            for scen in cfg["cost_scenarios"]:
                cr_slot = cost_pips[scen] * PIP / (sig_slot[idx] * entry_px[idx])
                cr_abs = cost_pips[scen] * PIP / (sig_abs[idx] * entry_px[idx])
                t[f"cost_pips_{scen}"] = cost_pips[scen]
                t[f"net_R_slot_{scen}"] = t.gross_R_slot - cr_slot
                t[f"net_R_abs_{scen}"] = t.gross_R_abs - cr_abs
            trade_parts.append(t)

    trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    excl = pd.concat(excl_parts, ignore_index=True) if excl_parts else pd.DataFrame()
    return trades, excl


def apply_non_overlap(trades: pd.DataFrame) -> pd.DataFrame:
    """Mark the stateful one-position-per-pair book (Rule 13), per delay and treatment.

    Occupancy is enforced greedily forward in time within each (pair, delay, treatment) over
    the full timeline (causal). Because exit times differ by treatment, each treatment gets
    its own surviving set -- which is exactly why an overlay cannot be reproduced by filtering
    a fixed completed-trade list, and must be re-run through this machinery in Stage C.
    """
    trades = trades.reset_index(drop=True)
    keep = np.zeros(len(trades), bool)
    for _, gidx in trades.groupby(["pair", "delay", "treatment"], observed=True, sort=False).groups.items():
        g = trades.loc[gidx].sort_values("entry_minute")
        k = lib.greedy_non_overlap(g.entry_minute.to_numpy(), g.exit_minute.to_numpy())
        keep[g.index.to_numpy()[k]] = True
    trades["in_book"] = keep
    return trades


# --------------------------------------------------------------------------- #
# Aggregation (stateful book primary; all-signal diagnostic)
# --------------------------------------------------------------------------- #

def _surface_over(frame: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    scen = cfg["primary_cost_scenario"]
    parts = []
    for f in run.cell_frames(frame):
        gs = run.cluster_summary(f, GROUP, "gross_R_slot").rename(columns={
            "mean": "gross_R_slot", "se": "gross_R_slot_se", "t": "gross_R_slot_t",
            "ci_low": "gross_R_slot_ci_low", "ci_high": "gross_R_slot_ci_high"})
        ga = run.cluster_summary(f, GROUP, "gross_R_abs").rename(columns={
            "mean": "gross_R_abs", "se": "gross_R_abs_se", "t": "gross_R_abs_t",
            "ci_low": "gross_R_abs_ci_low", "ci_high": "gross_R_abs_ci_high"})[
            GROUP + ["gross_R_abs", "gross_R_abs_ci_low", "gross_R_abs_ci_high"]]
        ns = run.cluster_summary(f, GROUP, f"net_R_slot_{scen}").rename(columns={
            "mean": "net_R_slot", "se": "net_R_slot_se", "t": "net_R_slot_t",
            "ci_low": "net_R_slot_ci_low", "ci_high": "net_R_slot_ci_high"})[
            GROUP + ["net_R_slot", "net_R_slot_ci_low", "net_R_slot_ci_high"]]
        aux = (f.assign(_tp=(f.exit_kind == 1).astype(float), _to=(f.exit_kind == 0).astype(float),
                        _win=(f.gross_pips > 0).astype(float),
                        _hold=(f.exit_minute - f.entry_minute).astype(float))
               .groupby(GROUP, observed=True)
               .agg(gross_pips=("gross_pips", "mean"), cost_pips_base=(f"cost_pips_{scen}", "mean"),
                    net_R_abs=(f"net_R_abs_{scen}", "mean"), anchor_fill_rate=("_tp", "mean"),
                    timeout_rate=("_to", "mean"), win_rate=("_win", "mean"),
                    mean_hold_min=("_hold", "mean"), abs_z=("abs_z", "mean"),
                    sigma_slot_pips=("sigma_slot_pips", "mean")).reset_index())
        parts.append(gs.merge(ga, on=GROUP, how="left").merge(ns, on=GROUP, how="left")
                     .merge(aux, on=GROUP, how="left"))
    surf = pd.concat(parts, ignore_index=True)
    surf["breakeven_or_rebate_pips"] = surf.gross_pips     # >=0 breakeven cost; <0 = rebate to zero
    return surf


def book_surface(trades: pd.DataFrame, cfg: dict):
    """Stateful one-position book surface (primary) and the all-signal diagnostic surface."""
    stateful = _surface_over(trades.loc[trades.in_book], cfg)
    stateful["book"] = "stateful_one_position"
    allsig = _surface_over(trades, cfg)
    allsig["book"] = "all_signals_diagnostic"
    return stateful, allsig


def cost_curve(trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Pooled net R_slot by cost scenario for the primary STATEFUL arm (delay-1, guarded)."""
    d = trades.loc[trades.in_book & trades.delay.eq(cfg["primary_entry_delay_bars"])
                   & trades.treatment.eq(cfg["primary_exit_treatment"])
                   & trades.era.ne("holdout")].assign(pair="POOLED", era="consumed", session="all")
    rows = []
    for scen in cfg["cost_scenarios"]:
        st = run.cluster_summary(d, ["pair", "era", "session"], f"net_R_slot_{scen}")
        r = st.iloc[0]
        rows.append({"scenario": scen, "n": int(r.n), "net_R_slot": float(r["mean"]),
                     "ci_low": float(r.ci_low), "ci_high": float(r.ci_high),
                     "mean_cost_pips": float(d[f"cost_pips_{scen}"].mean()),
                     "mean_gross_pips": float(d.gross_pips.mean())})
    return pd.DataFrame(rows)


def book_sharpes(trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Three Sharpes on the stateful one-position book, primary arm, gross and net (Rule 13)."""
    d = trades.loc[trades.in_book & trades.delay.eq(cfg["primary_entry_delay_bars"])
                   & trades.treatment.eq(cfg["primary_exit_treatment"])]
    scen = cfg["primary_cost_scenario"]
    rows = []
    for era in ("consumed", "holdout"):
        book = (d.loc[d.era.ne("holdout")] if era == "consumed" else d.loc[d.era.eq("holdout")]).copy()
        if book.empty:
            continue
        book["net_R_slot"] = book[f"net_R_slot_{scen}"]
        days = pd.DatetimeIndex(pd.date_range(book.utc_day.min(), book.utc_day.max(), freq="D"))
        for label, col in (("gross", "gross_R_slot"), ("net", "net_R_slot")):
            s = lib.three_sharpes(book.groupby("utc_day", observed=True)[col].sum(), days)
            s.update({"era": era, "basis": label, "trades": int(len(book)),
                      "mean_R_slot": float(book[col].mean())})
            rows.append(s)
    return pd.DataFrame(rows)


def overlap_reduction(trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Book-eligible vs stateful-book trade counts, per pair/delay/treatment (F1 accounting)."""
    g = (trades.assign(_book=trades.in_book.astype(int))
         .groupby(["pair", "delay", "treatment"], observed=True)
         .agg(eligible=("in_book", "size"), book_trades=("_book", "sum")).reset_index())
    g["occupancy_drop_pct"] = (1 - g.book_trades / g.eligible) * 100.0
    return g


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #

def _cell(surf, delay, treatment, session="all", era="consumed"):
    q = surf.query("pair == 'POOLED' and era == @era and session == @session "
                   "and delay == @delay and treatment == @treatment")
    if q.empty:
        return None
    r = q.iloc[0]
    return {
        "n": int(r.n), "gross_R_slot": float(r.gross_R_slot),
        "gross_R_slot_ci": [float(r.gross_R_slot_ci_low), float(r.gross_R_slot_ci_high)],
        "gross_R_abs": float(r.gross_R_abs),
        "gross_pips": float(r.gross_pips), "cost_pips_base": float(r.cost_pips_base),
        "net_R_slot": float(r.net_R_slot),
        "net_R_slot_ci": [float(r.net_R_slot_ci_low), float(r.net_R_slot_ci_high)],
        "net_R_abs": float(r.net_R_abs), "win_rate": float(r.win_rate),
        "anchor_fill_rate": float(r.anchor_fill_rate), "timeout_rate": float(r.timeout_rate),
        "mean_hold_min": float(r.mean_hold_min), "abs_z": float(r.abs_z),
    }


def make_verdict(surf, allsig, cost, sharpes, redux, cfg, funnel) -> dict:
    dP, tP = cfg["primary_entry_delay_bars"], cfg["primary_exit_treatment"]
    primary = _cell(surf, dP, tP)
    diag = _cell(allsig, dP, tP)
    out = {
        "experiment": "EXP-0004", "stage": "B",
        "estimand": "stateful one-position-per-pair book (greedy non-overlap); all-signal per-signal is a diagnostic",
        "inherited_params_note": "tau=5/H=240 are Stage-A consumed-history P&L-selected candidates, not untuned/confirmed (Stage-A review F1)",
        "book": {"tau": cfg["tau"], "entry": f"|z_slot| >= {cfg['entry_k']}, first crossing",
                 "entry_fill": "delay-1 (two bars after signal)", "hold_cap_min": cfg["holding_cap_minutes"],
                 "exit": f"guarded anchor-retrace, g={cfg['anchor_guard_sigma']} sigma_slot",
                 "diagnostic_exits": "touch-fill (g=0) and time-exit comparators (NOT payoff bounds)",
                 "stop": "none", "no_entry_rule": "reject if anchor already crossed at entry (causal)",
                 "vetoes": "news +/-30min; Friday 16:55 NY flat"},
        "exclusion_funnel_pooled": funnel,
        "primary_arm_stateful": {"delay": dP, "treatment": tP, "cell": primary},
        "all_signal_diagnostic": {"delay": dP, "treatment": tP, "cell": diag},
        "gross_first_stateful": {
            "note": "positive gross reversion is ESTABLISHED only if the CI excludes zero on the positive side.",
            "delay1_guarded": _cell(surf, 1, "guarded"),
            "delay1_touch_diagnostic": _cell(surf, 1, "touch"),
            "delay1_time_comparator": _cell(surf, 1, "time"),
            "delay0_guarded_diagnostic": _cell(surf, 0, "guarded"),
        },
        "cost_curve_primary": cost.to_dict("records"),
        "three_sharpes_primary": sharpes.to_dict("records"),
        "overlap_reduction": redux.to_dict("records"),
    }
    hold = _cell(surf, dP, tP, era="holdout")
    out["sealed_holdout_2024plus"] = {"note": "opened once; delay-1 guarded, pooled, stateful", "cell": hold}
    if primary:
        be = primary["gross_pips"]
        cost_base = primary["cost_pips_base"]
        established = primary["gross_R_slot_ci"][0] > 0
        out["verdict"] = {
            "gross_reversion_established": bool(established),
            "gross_pips": be,
            "rebate_to_zero_pips": (None if be >= 0 else round(-be, 4)),
            "modelled_base_round_trip_pips": cost_base,
            "gross_covers_cost": bool(be >= cost_base),
            "net_ci_excludes_zero_positive": bool(primary["net_R_slot_ci"][0] > 0),
            "summary": ("reference book frozen (stateful one-position); "
                        + ("positive gross reversion ESTABLISHED" if established
                           else "positive gross reversion NOT established (CI includes 0)")
                        + "; NET " + ("clears zero -- escalate" if primary["net_R_slot_ci"][0] > 0
                                      else "negative")
                        + (f"; gross {be:.3f} pips vs {cost_base:.3f} modelled cost"
                           + ("" if be >= 0 else f" (gross negative: a {-be:.3f}-pip rebate would be needed to reach zero)"))
                        + ".")}
    return out


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def main() -> None:
    cfg = load_config()
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    trade_parts, excl_parts = [], []
    for pair in cfg["pairs"]:
        run.log(f"{pair}: building tau={cfg['tau']} same-slot signals at k={cfg['entry_k']}")
        frame, *_ = run.load_minutes(pair, cfg)
        grid = lib.MinuteGrid(pd.DatetimeIndex(frame.time), frame.open, frame.high, frame.low)
        sig = build_signals(pair, frame, cfg, high_impact_times(pair))
        if sig.empty:
            del frame, grid
            continue
        # CONSUMED-only median for the cost vol-ratio: the sealed 2024+ holdout must not leak
        # into pre-2024 cost normalisation (Stage-A review F2).
        cons = sig.loc[~sig.news_veto & sig.era.ne("holdout"), "sigma_slot_pips"]
        med = float(np.median(cons)) if len(cons) else float("nan")
        run.log(f"{pair}: {len(sig):,} signals ({int(sig.news_veto.sum()):,} news-vetoed); simulating book")
        tr, ex = simulate_book(sig, grid, cfg, med)
        trade_parts.append(tr)
        excl_parts.append(ex)
        del frame, grid, sig

    trades = pd.concat(trade_parts, ignore_index=True)
    excl = pd.concat(excl_parts, ignore_index=True)
    del trade_parts
    run.log(f"total trade rows (signal x delay x treatment): {len(trades):,}")

    run.log("applying the stateful one-position non-overlap (Rule 13, F1)")
    trades = apply_non_overlap(trades)
    run.log("aggregating stateful book surface + all-signal diagnostic (both units)")
    surf, allsig = book_surface(trades, cfg)
    cost = cost_curve(trades, cfg)
    sharpes = book_sharpes(trades, cfg)
    redux = overlap_reduction(trades, cfg)

    funnel = {c: int(excl[c].sum()) for c in
              ["signals_pre_veto", "news_vetoed", "zero_cap_friday", "no_entry_already_crossed",
               "incomplete_path", "book_eligible", "friday_shortened"]
              if c in excl.columns}
    funnel_primary = {c: int(excl.loc[excl.delay.eq(cfg["primary_entry_delay_bars"]), c].sum())
                      for c in funnel}

    run.log("verdict")
    verdict = make_verdict(surf, allsig, cost, sharpes, redux, cfg, funnel_primary)

    run.log("writing artifacts")
    (ARTIFACT / "verdict.json").write_text(json.dumps(verdict, indent=2, default=str), encoding="utf-8")
    (ARTIFACT / "run_manifest.json").write_text(json.dumps({
        "experiment_id": "EXP-0004", "stage": "B",
        "hypothesis": "experiments/hypotheses/HYP-0004.md",
        "kill_test": "artifacts/runs/EXP-0004/KILL_TEST.md",
        "review_corrections": "F1 stateful estimand; F2 no-entry + consumed-median cost; F3/minor language; F4 coverage funnel",
        "config": cfg, "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "funnel_all_delays": funnel, "funnel_primary_delay": funnel_primary,
        "trade_rows": int(len(trades)),
        "imported_from_exploration_1": ["_cost_model.round_trip_pips",
                                        "_run_rsi_axis6_calendar.high_impact_times",
                                        "_run_rsi_broad_regime_sweep.PIP"],
        "exit_simulator": "forex/exploration_4/_stage_b_lib.simulate_anchor_retrace (test_stage_b.py)",
    }, indent=2), encoding="utf-8")
    for name, obj in (("book_surface_stateful", surf), ("book_surface_all_signals", allsig),
                      ("cost_curve", cost), ("three_sharpes", sharpes),
                      ("overlap_reduction", redux), ("exclusion_funnel", excl)):
        obj.to_csv(ARTIFACT / f"{name}.csv", index=False)
    keep = [c for c in trades.columns if c not in ("z_signal",)]
    trades[keep].to_parquet(ARTIFACT / "trades.parquet", index=False)

    write_report(cfg, surf, allsig, cost, sharpes, redux, excl, verdict)
    run.log("done: " + verdict.get("verdict", {}).get("summary", "(no primary cell)"))


def write_report(cfg, surf, allsig, cost, sharpes, redux, excl, verdict) -> None:
    tt = lib.to_text_table
    dP, tP = cfg["primary_entry_delay_bars"], cfg["primary_exit_treatment"]

    gross = surf.query("pair == 'POOLED' and era == 'consumed' and session == 'all'")[
        ["delay", "treatment", "n", "gross_R_slot", "gross_R_slot_ci_low", "gross_R_slot_ci_high",
         "gross_R_abs", "gross_pips", "cost_pips_base", "anchor_fill_rate", "timeout_rate",
         "win_rate", "mean_hold_min"]].sort_values(["delay", "treatment"])

    net = surf.query("pair == 'POOLED' and session == 'all' and delay == @dP and treatment == @tP")[
        ["era", "n", "gross_R_slot", "gross_pips", "cost_pips_base", "net_R_slot",
         "net_R_slot_ci_low", "net_R_slot_ci_high", "net_R_abs"]].sort_values("era")

    bypair = surf.query("era == 'consumed' and session == 'all' and delay == @dP and treatment == @tP "
                        "and pair != 'POOLED'")[
        ["pair", "n", "gross_R_slot", "gross_R_slot_ci_low", "gross_R_slot_ci_high",
         "gross_R_abs", "gross_pips", "net_R_slot"]].sort_values("pair")

    bysess = surf.query("pair == 'POOLED' and era == 'consumed' and delay == @dP and treatment == @tP "
                        "and session != 'all'")[
        ["session", "n", "gross_R_slot", "gross_R_abs", "gross_pips", "cost_pips_base",
         "net_R_slot", "net_R_abs"]].sort_values("session")

    shp = sharpes[["era", "basis", "trades", "mean_R_slot", "sharpe_zero_day",
                   "sharpe_trade_days", "sharpe_vol_targeted"]]
    red = redux.loc[redux.delay.eq(dP)][["pair", "treatment", "eligible", "book_trades", "occupancy_drop_pct"]]
    fun = (excl.groupby("delay", observed=True)[
        ["signals_pre_veto", "news_vetoed", "zero_cap_friday", "no_entry_already_crossed",
         "incomplete_path", "book_eligible", "friday_shortened"]].sum().reset_index())
    fun_hour = (excl.loc[excl.delay.eq(dP)].groupby("utc_hour", observed=True)[
        ["signals_pre_veto", "news_vetoed", "no_entry_already_crossed", "incomplete_path",
         "book_eligible"]].sum().reset_index())

    v = verdict["verdict"]
    prim = verdict["primary_arm_stateful"]["cell"]
    diag = verdict["all_signal_diagnostic"]["cell"]
    hold = verdict["sealed_holdout_2024plus"]["cell"]
    rebate = "" if v["rebate_to_zero_pips"] is None else f" (gross is negative: a {v['rebate_to_zero_pips']:.3f}-pip rebate would be needed to reach zero)"

    text = f"""# Stage B — Frozen Reference Book (EXP-0004)

Contract: `experiments/hypotheses/HYP-0004.md` and `artifacts/runs/EXP-0004/KILL_TEST.md`
(frozen before the run). Reproduce: `python -u forex/exploration_4/_run_stage_b.py`;
tests `python -m pytest forex/exploration_4/test_stage_b.py -q`.

**This version incorporates the corrections from Codex's independent review**
(`artifacts/runs/EXP-0004/independent_review_codex.md`); the point-by-point response is in
`artifacts/runs/EXP-0004/review.md`. The book is the **ruler** Stage C's overlays are measured
against; whether it is GO or NO-GO is not the point (Rule 25).

## The frozen book

- τ=5 same-slot z `(ret_5−μ_slot)/σ_slot` (90 prior sessions, `min_periods=60`, prior only).
- Entry: fade **|z_slot| ≥ {cfg['entry_k']}**, first crossing; fill **delay-1** (two bars
  after the signal bar); delay-0 is a diagnostic.
- **No-entry rule (causal):** reject signals whose anchor is already crossed at entry.
- Exit (frozen): **guarded anchor-retrace** — limit at the anchor, credited only on a
  **{cfg['anchor_guard_sigma']}·σ_slot trade-through**, filled at the anchor price. **No stop.**
- Vetoes: news ±30 min; force-flat Friday 16:55 NY.
- **Estimand: the stateful one-position-per-pair book** (greedy non-overlap, Rule 13). The
  all-signal per-signal mean is reported only as a **diagnostic**.
- **Inherited grain is not confirmed:** τ=5 / H=240 were selected on Stage-A *consumed-history
  gross P&L* (Stage-A review F1). They are a frozen candidate, not an untuned or confirmed
  choice; Stage B adds no new P&L tuning.
- Units: `R_slot` (σ_slot, the sizing unit) headline; `R_abs` yardstick; pips physical.

> **On the exit comparators:** the `touch` and `time` arms are **diagnostics, not payoff
> bounds** — `touch` maximises the *chance of an anchor fill*, not P&L, and a missed fill can
> outperform a fill if price keeps going. Guarded gross sits *below* both here, so neither
> brackets it. No floor/ceiling language is used.

## 1. Coverage funnel (Rule 9a) — how signals become book trades

Per delay (both entry arms), pooled over pairs and eras:

{tt(fun, 0)}

Primary-arm (delay-1) book-eligibility by UTC hour (the post-news path loss is not
hour-neutral):

{tt(fun_hour, 0)}

Full per-pair/era/hour funnel: `artifacts/runs/EXP-0004/exclusion_funnel.csv`. Non-overlap
(one-position) then reduces book-eligible to executed trades:

{tt(red, 2)}

## 2. Gross first — does the bare entry revert? (stateful book, pooled, consumed)

All exit arms, both entry arms; `gross_R_slot` is per-signal mean over the **non-overlap
book** with a UTC-day cluster-robust CI. Positive reversion is **established only if the CI
excludes zero on the positive side**.

{tt(gross, 4)}

**Primary arm (delay-1, guarded, stateful):** gross **{prim['gross_R_slot']:.4f} R_slot**
CI [{prim['gross_R_slot_ci'][0]:.4f}, {prim['gross_R_slot_ci'][1]:.4f}];
**{prim['gross_R_abs']:.4f} R_abs**; **{prim['gross_pips']:.3f} pips**. Anchor-fill rate
{prim['anchor_fill_rate']:.3f}, timeout {prim['timeout_rate']:.3f}, mean hold
{prim['mean_hold_min']:.1f} min, mean |z| {prim['abs_z']:.2f}, n={prim['n']:,}.

Positive gross reversion established at delay-1: **{v['gross_reversion_established']}**.
(All-signal diagnostic, same arm: gross {diag['gross_R_slot']:.4f} R_slot, n={diag['n']:,} —
larger n, but not the deployable one-position estimand.)

## 3. Cost and net (primary stateful arm)

Gross **{v['gross_pips']:.3f} pips** vs modelled base round trip **{v['modelled_base_round_trip_pips']:.3f}**
pips; gross covers cost: **{v['gross_covers_cost']}**{rebate}.

{tt(cost, 4)}

Net by era (both units):

{tt(net, 4)}

Net CI excludes zero on the positive side: **{v['net_ci_excludes_zero_positive']}**.

## 4. Per pair (consumed, primary stateful arm)

{tt(bypair, 4)}

## 5. Per session (consumed, primary stateful arm) — descriptive only

EXP-0003 retracted the thin-hours localisation, and same-slot sizing makes net tilt toward
busy hours **structurally** (σ_slot ~2.2× larger at 21:00 than 13:00). Descriptive only; **no
session overlay is built on it in Stage B**.

{tt(bysess, 4)}

## 6. Three Sharpes (stateful one-position book, primary arm)

{tt(shp, 3)}

## 7. Sealed holdout (2024+), opened once

Delay-1 guarded, pooled, stateful: gross **{hold['gross_R_slot'] if hold else float('nan'):.4f} R_slot**
CI [{hold['gross_R_slot_ci'][0] if hold else float('nan'):.4f}, {hold['gross_R_slot_ci'][1] if hold else float('nan'):.4f}],
{hold['gross_pips'] if hold else float('nan'):.3f} gross pips, net
**{hold['net_R_slot'] if hold else float('nan'):.4f} R_slot**. Reported once; informed no frozen choice.

## Verdict

**{v['summary']}**

The book is frozen and registered as the Stage-C ruler. A negative reference book is a valid
ruler (Rule 25): overlays are scored as excess over THIS stateful book at matched count, and —
because an overlay changes exits and therefore occupancy — each overlay must be re-run through
the same non-overlap machinery, never by filtering a completed-trade list.

## Limitations

- Midpoint OHLC only — no bid/ask. Cost is a modelled curve; the guarded-anchor fill is a
  **model**. The `time` comparator needs no fill assumption and is itself far below cost.
- The guard g={cfg['anchor_guard_sigma']}σ_slot is a frozen fiat choice, not optimised.
- τ=5/H=240 are consumed-history P&L-selected (Stage-A review F1); a selection-aware null
  would be needed for any inferential claim about the selected maximum.
- UTC slots do not track DST. 2024+ read once, at the end.
"""
    (REPORTS / "STAGE_B_REFERENCE_BOOK.md").write_text(text, encoding="utf-8")
    (ARTIFACT / "STAGE_B_REFERENCE_BOOK.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
