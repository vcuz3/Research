"""EXP-0003 -- Stage-A addendum: is the |z| cut a time-of-day selector?

Reproduce from the workspace root:
    python -u forex/exploration_4/_run_same_slot.py

Contract: `experiments/hypotheses/HYP-0003.md`, frozen before this ran. EXP-0002
measured z against an all-hours 28,800-minute sigma, which cannot see the intraday
volatility profile; the fixed |z| >= 2 cut therefore fired on 0.96% of decisions at
04:00 UTC and 10.11% at 14:00 (selection-rate CV 0.707). This run rebuilds the same
signal family against a causal SAME-SLOT sigma and answers the four questions in
HYP-0003 §4, whose decision rules were written before any result was seen.

Everything not under test is imported from `_run_stage_a` so the two runs cannot
drift: loading, coverage bookkeeping, forward outcomes, the paired entry-delay
control, the cost model, cell pooling and the cluster-robust estimator are the same
code. Only the sigma estimator and the threshold grid change.

Numbering: the run-book assigns EXP-0003 to Stage B, but the ledger requires
`EXP-\\d{4}` so this addendum takes EXP-0003 and Stage B becomes EXP-0004.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import _run_stage_a as run                                       # noqa: E402
import _stage_a_lib as lib                                       # noqa: E402
from _run_rsi_broad_regime_sweep import PIP                      # noqa: E402
from _run_rsi_axis6_calendar import high_impact_times            # noqa: E402


CONFIG_PATH = PROJECT / "baseline_replication" / "configs" / "same_slot.json"
ARTIFACT = PROJECT / "artifacts" / "runs" / "EXP-0003"
REPORTS = PROJECT / "reports"

GROUP = ["pair", "era", "session", "tau", "k", "arm"]


def load_config() -> dict:
    add = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg = json.loads((PROJECT / add["inherits"]).read_text(encoding="utf-8"))
    cfg.update({k: v for k, v in add.items() if k != "inherits"})
    cfg["common_sample_horizon_minutes"] = max(cfg["horizon_minutes"])
    return cfg


# --------------------------------------------------------------------------- #
# Signals for both arms
# --------------------------------------------------------------------------- #

def grain_arms(pair: str, frame: pd.DataFrame, cfg: dict):
    """Yield per-rung arrays for both sigma arms, on ONE common decision sample.

    Both arms are restricted to bars where BOTH sigma estimators are warmed up, so
    neither arm can look better merely by being defined on different rows (the slot
    estimator warms up ~90 sessions later than the all-hours one).
    """
    ohlc = frame[["time", "open", "high", "low", "close"]]
    for tau in cfg["grain_ladder_minutes"]:
        bars, _ = lib.build_grain_bars(ohlc, tau, cfg["sigma_window_minutes"],
                                       cfg["sigma_min_fraction"])
        bidx = pd.DatetimeIndex(bars.index)
        era = lib.era_of(bidx, run.naive_ts(cfg["era_split"]), run.naive_ts(cfg["holdout_start"]))
        sess = np.asarray(lib.SESSION_LABELS, dtype=object)[lib.session_codes(bidx, cfg["sessions"])]
        decision = np.asarray(bidx >= run.naive_ts(cfg["start"]))

        mu, sd = lib.same_slot_moments(bars, tau, cfg["slot_lookback_sessions"],
                                       cfg["slot_min_fraction"])
        bars["z_slot"] = (bars.ret - mu) / sd.replace(0.0, np.nan)
        usable = (decision & bars.complete.to_numpy(bool)
                  & bars.z.notna().to_numpy() & bars.z_slot.notna().to_numpy())
        yield tau, bars, bidx, era, sess, usable, sd


def crossing_counts(pair: str, frame: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """PASS 1 -- first-crossing counts over a fine k grid, for rate matching.

    Matching a selection rate needs a threshold that actually hits the target, so the
    grid is swept finely and the matched k is PICKED from it. Interpolating a frontier
    instead would clamp outside its range and silently become an extrapolation.
    """
    fine = np.round(np.arange(cfg["fine_k_min"], cfg["fine_k_max"] + 1e-9,
                              cfg["fine_k_step"]), 4)
    rows = []
    for tau, bars, _, era, _, usable, _ in grain_arms(pair, frame, cfg):
        common = pd.Series(usable, index=bars.index)
        consumed = usable & (era != "holdout")
        contig = bars.contiguous & common
        for arm, zcol in (("abs", "z"), ("slot", "z_slot")):
            z = bars[zcol].where(common)
            for k in fine:
                s = lib.first_crossing(z, common, contig, float(k))
                rows.append({"pair": pair, "tau": tau, "arm": arm, "k": float(k),
                             "crossings": int(consumed[s].sum()),
                             "eligible": int(consumed.sum())})
        del bars
    return pd.DataFrame(rows)


def choose_matched_k(counts: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Per grain, the slot-arm k whose pooled crossing rate best matches abs at k=2.0."""
    ref_arm, ref_k = cfg["reference_arm"], cfg["reference_k"]
    pooled = (counts.groupby(["tau", "arm", "k"], observed=True)
              .agg(crossings=("crossings", "sum"), eligible=("eligible", "sum")).reset_index())
    pooled["rate"] = pooled.crossings / pooled.eligible
    rows = []
    for tau, g in pooled.groupby("tau", observed=True):
        ref = g.query("arm == @ref_arm and k == @ref_k")
        if ref.empty:
            continue
        target = float(ref.rate.iloc[0])
        cand = g.loc[g.arm.eq("slot")].copy()
        cand["gap"] = (cand.rate - target).abs()
        best = cand.loc[cand.gap.idxmin()]
        rows.append({"tau": int(tau), "abs_k": ref_k, "target_rate_abs": target,
                     "slot_k": float(best.k), "slot_rate": float(best.rate),
                     "rate_gap_pct_of_target": float(best.gap / target * 100.0),
                     "slot_k_interior": bool(cfg["fine_k_min"] < best.k < cfg["fine_k_max"])})
    return pd.DataFrame(rows)


def build_arms(pair: str, frame: pd.DataFrame, cfg: dict, news,
               matched: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """PASS 2 -- full signals at the reporting grid plus each rung's rate-matched k."""
    mk = matched.set_index("tau").slot_k.to_dict()
    sig_parts, rate_parts = [], []

    for tau, bars, bidx, era, sess, usable, sd in grain_arms(pair, frame, cfg):
        rate_parts.append(pd.DataFrame({
            "pair": pair, "tau": tau, "era": era[usable], "utc_hour": bidx.hour[usable],
            "session": sess[usable], "eligible": 1,
        }).groupby(["pair", "tau", "era", "utc_hour", "session"], observed=True)
          .eligible.sum().reset_index())

        closes, opens = bars.close.to_numpy(float), bars.open.to_numpy(float)
        sig_abs = bars.sigma.to_numpy(float)
        sig_slot = sd.to_numpy(float)
        complete = bars.complete.to_numpy(bool)
        bar_minutes = lib.minute_positions(bidx)
        common = pd.Series(usable, index=bars.index)
        contig = bars.contiguous & common

        for arm, zcol, sig_arr in (("abs", "z", sig_abs), ("slot", "z_slot", sig_slot)):
            ks = list(cfg["entry_k_grid"])
            if arm == "slot" and tau in mk:
                ks.append(float(mk[tau]))
            z = bars[zcol].where(common)
            for k in sorted(set(round(float(x), 4) for x in ks)):
                s = lib.first_crossing(z, common, contig, k)
                s = s[s + 1 < len(bars)]
                ok = (complete[s + 1] & np.isfinite(sig_arr[s]) & (sig_arr[s] > 0)
                      & np.isfinite(sig_abs[s]) & (sig_abs[s] > 0))
                s = s[ok]
                if len(s) == 0:
                    continue
                e = s + 1
                d = pd.DataFrame({
                    "pair": pair, "tau": tau, "k": k, "arm": arm,
                    "entry_bar": e, "signal_time": bidx[s], "entry_time": bidx[e],
                    "entry_minute": bar_minutes[e], "era": era[e], "session": sess[e],
                    "utc_hour": bidx[e].hour, "utc_day": bidx[e].floor("D"),
                    "z_signal": bars[zcol].to_numpy()[s],
                    "sigma": sig_arr[s], "sigma_abs": sig_abs[s],
                    "anchor_price": closes[s - 1], "entry_price": opens[e],
                })
                d["side"] = np.where(d.z_signal < 0, 1.0, -1.0)
                sig_parts.append(d)
        del bars

    signals = pd.concat(sig_parts, ignore_index=True)
    sidx = pd.DatetimeIndex(signals.entry_time)
    ny = sidx.tz_localize("UTC").tz_convert("America/New_York")
    signals["ny_weekday"] = ny.weekday.to_numpy()
    signals["ny_minute"] = ny.hour.to_numpy() * 60 + ny.minute.to_numpy()
    signals["sigma_pips"] = signals.sigma * signals.entry_price / PIP
    signals["news_distance_minutes"] = run.nearest_event_minutes(sidx, news)
    signals["news_veto"] = signals.news_distance_minutes < cfg["news_blackout_minutes"]
    return signals, pd.concat(rate_parts, ignore_index=True)


# --------------------------------------------------------------------------- #
# Q1: firing rate uniformity
# --------------------------------------------------------------------------- #

def firing_rates(signals: pd.DataFrame, eligible: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Selection rate per UTC hour, per arm and threshold, on the common sample."""
    live = signals.loc[~signals.news_veto & signals.era.ne("holdout")]
    fired = (live.groupby(["tau", "k", "arm", "utc_hour"], observed=True)
             .size().rename("signals").reset_index())
    elig = (eligible.loc[eligible.era.ne("holdout")]
            .groupby(["tau", "utc_hour"], observed=True).eligible.sum().reset_index())
    out = fired.merge(elig, on=["tau", "utc_hour"], how="right")
    out["signals"] = out.signals.fillna(0.0)
    out["fire_rate"] = out.signals / out.eligible.replace(0, np.nan)
    return out


def rate_cv(rates: pd.DataFrame) -> pd.DataFrame:
    """Cross-hour coefficient of variation of the selection rate -- the pass signal."""
    g = (rates.dropna(subset=["fire_rate", "k", "arm"])
         .groupby(["tau", "k", "arm"], observed=True)
         .agg(mean_rate=("fire_rate", "mean"), sd_rate=("fire_rate", "std"),
              min_rate=("fire_rate", "min"), max_rate=("fire_rate", "max"),
              hours=("fire_rate", "size"), signals=("signals", "sum")).reset_index())
    g["cv"] = g.sd_rate / g.mean_rate
    g["max_over_min"] = g.max_rate / g.min_rate.replace(0, np.nan)
    return g


# --------------------------------------------------------------------------- #
# Outcome surface
# --------------------------------------------------------------------------- #

def surface(signals: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Per-signal mean R by cell, for both arms, both entry delays, both horizons."""
    live = ~signals.news_veto.to_numpy()
    keep = ["pair", "era", "session", "tau", "k", "arm", "utc_day", "z_signal"]
    rows = []
    for delay in cfg["entry_delay_bars"]:
        for h in cfg["horizon_minutes"]:
            m = live & signals[f"complete_d{delay}_{h}"].to_numpy(bool)
            if not m.any():
                continue
            base = signals.loc[m, keep].copy()
            base["gross_R_own"] = signals.loc[m, f"gross_R_d{delay}_{h}"].to_numpy()
            base["gross_pips"] = signals.loc[m, f"gross_pips_d{delay}_{h}"].to_numpy()
            base["gross_R_abs"] = (base.gross_pips.to_numpy() * PIP
                                   / (signals.loc[m, "sigma_abs"].to_numpy()
                                      * signals.loc[m, "entry_price"].to_numpy()))
            base["cost_pips_base"] = signals.loc[m, "cost_pips_base"].to_numpy()
            parts = []
            for f in run.cell_frames(base):
                stat = run.cluster_summary(f, GROUP, "gross_R_abs").rename(
                    columns={"mean": "gross_R_abs", "se": "gross_R_abs_se",
                             "t": "gross_R_abs_t", "ci_low": "gross_R_abs_ci_low",
                             "ci_high": "gross_R_abs_ci_high"})
                aux = (f.groupby(GROUP, observed=True)
                       .agg(gross_R_own=("gross_R_own", "mean"),
                            gross_pips=("gross_pips", "mean"),
                            cost_pips_base=("cost_pips_base", "mean"),
                            abs_z=("z_signal", lambda s: s.abs().mean())).reset_index())
                parts.append(stat.merge(aux, on=GROUP, how="left"))
            o = pd.concat(parts, ignore_index=True)
            o["horizon_minutes"] = h
            o["entry_delay_bars"] = delay
            rows.append(o)
    return pd.concat(rows, ignore_index=True)


# --------------------------------------------------------------------------- #
# Decision rules (HYP-0003 §4), applied mechanically
# --------------------------------------------------------------------------- #

def cluster_diff_means(y: np.ndarray, group: np.ndarray, cluster: np.ndarray,
                       a: str, b: str) -> dict:
    """UTC-day-clustered CI for the difference in mean(y) between two groups a and b.

    Stage-A repair F3: the addendum's original session test compared a gap against the
    SUM of two marginal CI half-widths, which is neither a CI for the difference nor
    aware of the covariance between the two session estimators when they share a UTC
    day. This is the proper contrast: influence functions per cluster, subtracted within
    the cluster so same-day covariance is captured, then a one-way cluster-robust SE.

        mean_a = S_a/N_a ; psi_g(mean_a) = (sum_{i in g,a}(y_i - mean_a)) / N_a
        diff = mean_a - mean_b ; psi_g(diff) = psi_g(mean_a) - psi_g(mean_b)
        Var(diff) = (G/(G-1)) * sum_g psi_g(diff)^2
    """
    ma = group == a
    mb = group == b
    ya, yb = y[ma], y[mb]
    if len(ya) == 0 or len(yb) == 0:
        return {"a": a, "b": b, "diff": np.nan, "se": np.nan, "ci_low": np.nan,
                "ci_high": np.nan, "n_a": int(len(ya)), "n_b": int(len(yb)), "clusters": 0}
    mean_a, mean_b = ya.mean(), yb.mean()
    na, nb = len(ya), len(yb)
    # per-cluster influence contributions
    ca, cb = cluster[ma], cluster[mb]
    codes, _ = pd.factorize(np.concatenate([ca, cb]))
    ga = codes[:na]
    gb = codes[na:]
    G = codes.max() + 1
    psi_a = np.bincount(ga, weights=(ya - mean_a), minlength=G) / na
    psi_b = np.bincount(gb, weights=(yb - mean_b), minlength=G) / nb
    psi = psi_a - psi_b
    var = (G / (G - 1.0)) * np.square(psi).sum() if G > 1 else np.nan
    se = float(np.sqrt(var)) if np.isfinite(var) and var > 0 else np.nan
    diff = mean_a - mean_b
    return {"a": a, "b": b, "diff": float(diff), "se": float(se),
            "ci_low": float(diff - 1.96 * se), "ci_high": float(diff + 1.96 * se),
            "n_a": int(na), "n_b": int(nb), "clusters": int(G)}


def session_contrast(signals: pd.DataFrame, match: pd.DataFrame, cfg: dict,
                     tau: int = 5, horizon: int = 240) -> dict:
    """Proper UTC-day-clustered off/asia − london contrasts (F3), both arms.

    Recomputes the per-signal gross_R_abs on the τ=5, delay-1, H=240 slot cell at the
    rate-matched k (and the abs cell at the reference k) on consumed history, then runs
    the clustered difference test. This is the test that would be needed to UPGRADE the
    clock-artifact attribution from provisional; reported here so the retraction rests on
    a difference CI, not the sum-of-half-widths heuristic.
    """
    mk = match.set_index("tau")
    k_slot = float(mk.loc[tau, "slot_k"])
    k_abs = float(cfg["reference_k"])
    gp = signals[f"gross_pips_d1_{horizon}"].to_numpy()
    comp = signals[f"complete_d1_{horizon}"].to_numpy(bool)
    r_abs = gp * PIP / (signals.sigma_abs.to_numpy() * signals.entry_price.to_numpy())
    base = pd.DataFrame({
        "arm": signals.arm.to_numpy(), "k": signals.k.to_numpy(),
        "tau": signals.tau.to_numpy(), "session": signals.session.to_numpy(),
        "utc_day": signals.utc_day.to_numpy(), "era": signals.era.to_numpy(),
        "news_veto": signals.news_veto.to_numpy(), "complete": comp, "r_abs": r_abs})
    base = base[(base.tau == tau) & base.complete & ~base.news_veto
                & base.era.ne("holdout")].dropna(subset=["r_abs"])
    out = {"tau": tau, "horizon_minutes": horizon,
           "note": "UTC-day-clustered CI for the difference in mean gross_R_abs; "
                   "captures same-day covariance, unlike the sum-of-half-widths screen"}
    for arm, k in (("slot", k_slot), ("abs", k_abs)):
        d = base[(base.arm == arm) & (base.k == k)]
        y = d.r_abs.to_numpy()
        g = d.session.to_numpy()
        c = d.utc_day.to_numpy()
        out[arm] = {pair: cluster_diff_means(y, g, c, a, "london")
                    for pair, a in (("off_minus_london", "off"),
                                    ("asia_minus_london", "asia"))}
    return out


def decide(cv: pd.DataFrame, match: pd.DataFrame, surf: pd.DataFrame, cfg: dict) -> dict:
    tau_ref = 5
    out = {"rule": "HYP-0003 §4", "reference_arm": cfg["reference_arm"],
           "reference_k": cfg["reference_k"], "cv_pass_threshold": cfg["cv_pass_threshold"]}

    mk = match.set_index("tau")
    out["matched_k_by_tau"] = match.to_dict("records")

    # ---- Q1: does the fix work? -------------------------------------------- #
    ref_k = cfg["reference_k"]
    abs_cv = float(cv.query("tau == @tau_ref and arm == 'abs' and k == @ref_k").cv.iloc[0])
    slot_k = float(mk.loc[tau_ref, "slot_k"])
    slot_cv = float(cv.query("tau == @tau_ref and arm == 'slot' and k == @slot_k").cv.iloc[0])
    out["Q1_firing_rate"] = {
        "abs_cv": abs_cv, "slot_cv": slot_cv,
        "pass": bool(slot_cv < cfg["cv_pass_threshold"]),
        "verdict": ("normaliser works; Q2/Q3 interpretable" if slot_cv < cfg["cv_pass_threshold"]
                    else "normaliser FAILED; Q2/Q3 are not interpretable")}

    # ---- Q2: was the session localisation real? ---------------------------- #
    def cell(arm, k, session, tau=tau_ref, delay=1, h=240):
        q = surf.query("pair == 'POOLED' and era == 'consumed' and arm == @arm and k == @k "
                       "and tau == @tau and session == @session and entry_delay_bars == @delay "
                       "and horizon_minutes == @h")
        if q.empty:
            return None
        r = q.iloc[0]
        return {"n": int(r.n), "gross_R_abs": float(r.gross_R_abs),
                "ci_low": float(r.gross_R_abs_ci_low), "ci_high": float(r.gross_R_abs_ci_high),
                "half_width": float(r.gross_R_abs_ci_high - r.gross_R_abs) }

    q2 = {}
    for arm, k in (("abs", ref_k), ("slot", slot_k)):
        cells = {s: cell(arm, k, s) for s in ("off", "asia", "london")}
        gaps = {}
        for thin in ("off", "asia"):
            a, b = cells.get(thin), cells.get("london")
            if a and b:
                gaps[thin] = {"gap": a["gross_R_abs"] - b["gross_R_abs"],
                              "combined_half_width": a["half_width"] + b["half_width"],
                              "exceeds": bool(a["gross_R_abs"] - b["gross_R_abs"]
                                              > a["half_width"] + b["half_width"])}
        q2[arm] = {"k": k, "cells": cells, "vs_london": gaps,
                   "localisation_survives": bool(any(g["exceeds"] for g in gaps.values()))}
    q2["outcome"] = ("thin-hours localisation SURVIVES the same-slot normalisation"
                     if q2["slot"]["localisation_survives"] else
                     "thin-hours localisation is NOT ESTABLISHED under the same-slot "
                     "normalisation: the EXP-0002 session breakdown is retracted as an "
                     "actionable prior. The clock-artifact ATTRIBUTION is PROVISIONAL "
                     "(this screen compares a gap to the sum of two marginal half-widths, "
                     "not a difference CI; see the clustered contrast for the proper test)")
    q2["matching_departure"] = ("HYP-0003 §4 specifies matching at a per-hour firing rate; "
                                "choose_matched_k matches ONE pooled crossing rate across "
                                "all hours (matched total count). Sensible, but a declared "
                                "departure from the frozen contract, not 'no departures'.")
    out["Q2_session_localisation"] = q2

    # ---- Q3: does the grain choice survive? -------------------------------- #
    # Two rankings (Stage-A repair F4). PRIMARY: at the preregistered horizon H*=240
    # (HYP-0003 §4), so no horizon is searched. AUX: best-over-{60,240}, which IS a
    # two-horizon search and is labelled as such -- it can only flatter a grain by
    # picking its better horizon, so it is a robustness read, never the decision.
    fixed_h = int(max(cfg["horizon_minutes"]))   # 240, the frozen H*

    def rank_at(horizon):
        order = []
        for tau in cfg["grain_ladder_minutes"]:
            if tau not in mk.index:
                continue
            k = float(mk.loc[tau, "slot_k"])
            q = surf.query("pair == 'POOLED' and era == 'consumed' and session == 'all' and "
                           "arm == 'slot' and k == @k and tau == @tau and entry_delay_bars == 1")
            if horizon is not None:
                q = q.query("horizon_minutes == @horizon")
            if q.empty:
                continue
            best = q.loc[q.gross_R_abs.idxmax()]
            order.append({"tau": int(tau), "k": k, "gross_R_abs": float(best.gross_R_abs),
                          "horizon_minutes": int(best.horizon_minutes), "n": int(best.n),
                          "ci_low": float(best.gross_R_abs_ci_low),
                          "ci_high": float(best.gross_R_abs_ci_high)})
        ranked = sorted(order, key=lambda r: -r["gross_R_abs"])
        top = ranked[0]["tau"] if ranked else None
        return order, [r["tau"] for r in ranked], top

    order, ranking, top = rank_at(fixed_h)                    # PRIMARY: fixed H*=240
    order_search, ranking_search, top_search = rank_at(None)  # AUX: best-of-horizon
    out["Q3_grain"] = {
        "primary_horizon_minutes": fixed_h,
        "ranking": ranking, "detail": order, "top_tau": top,
        "tau5_confirmed": bool(top == 5),
        "search_ranking": ranking_search, "search_detail": order_search,
        "search_top_tau": top_search,
        "search_note": ("AUX ONLY -- best-over-horizon {60,240} is a two-horizon "
                        "search that can only flatter a grain; the decision uses the "
                        f"fixed preregistered H*={fixed_h} ranking above"),
        "verdict": (f"tau*=5 CONFIRMED under same-slot normalisation at fixed H*={fixed_h}"
                    if top == 5 else
                    f"tau*=5 RE-OPENED: same-slot normalisation ranks tau={top} first at "
                    f"fixed H*={fixed_h}; Stage B may not freeze a grain until resolved")}

    # ---- Q4: does normalising destroy the information? --------------------- #
    def pooled(arm, k, delay=1, tau=tau_ref):
        q = surf.query("pair == 'POOLED' and era == 'consumed' and session == 'all' and "
                       "arm == @arm and k == @k and tau == @tau and entry_delay_bars == @delay")
        if q.empty:
            return None
        r = q.loc[q.gross_R_abs.idxmax()]
        return {"n": int(r.n), "horizon_minutes": int(r.horizon_minutes),
                "gross_R_abs": float(r.gross_R_abs), "gross_pips": float(r.gross_pips),
                "cost_pips_base": float(r.cost_pips_base),
                "ci_low": float(r.gross_R_abs_ci_low), "ci_high": float(r.gross_R_abs_ci_high)}
    a, b = pooled("abs", ref_k), pooled("slot", slot_k)
    out["Q4_information"] = {
        "abs": a, "slot": b,
        "slot_minus_abs_R": (b["gross_R_abs"] - a["gross_R_abs"]) if a and b else None,
        "note": ("compared at matched firing rate on the common decision sample; "
                 "gross_R_abs uses the SAME (absolute sigma) risk unit for both arms")}
    return out


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def main() -> None:
    cfg = load_config()
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    # ---- PASS 1: crossing counts on a fine k grid, to match the selection rate ---- #
    count_parts = []
    for pair in cfg["pairs"]:
        run.log(f"{pair}: pass 1 -- crossing counts over the fine k grid")
        frame, _, _, _ = run.load_minutes(pair, cfg)
        count_parts.append(crossing_counts(pair, frame, cfg))
        del frame
    counts = pd.concat(count_parts, ignore_index=True)
    match = choose_matched_k(counts, cfg)
    run.log("matched k: " + ", ".join(f"tau={r.tau}:k={r.slot_k:g} "
                                      f"({r.rate_gap_pct_of_target:.2f}% off)"
                                      for r in match.itertuples()))

    # ---- PASS 2: full signals at the reporting grid plus each matched k ---------- #
    sig_parts, rate_parts = [], []
    for pair in cfg["pairs"]:
        run.log(f"{pair}: pass 2 -- signals and forward outcomes")
        frame, _, _, _ = run.load_minutes(pair, cfg)
        grid = lib.MinuteGrid(pd.DatetimeIndex(frame.time), frame.open, frame.high, frame.low)
        signals, rates = build_arms(pair, frame, cfg, high_impact_times(pair), match)
        rate_parts.append(rates)
        run.log(f"{pair}: {len(signals):,} signals")
        sig_parts.append(run.attach_forward_outcomes(signals, grid, {}, cfg))
        del frame, grid

    signals = pd.concat(sig_parts, ignore_index=True)
    del sig_parts
    eligible = pd.concat(rate_parts, ignore_index=True)
    run.log(f"total signals: {len(signals):,}")
    signals = run.attach_costs(signals, cfg)

    run.log("Q1: firing-rate uniformity")
    rates = firing_rates(signals, eligible, cfg)
    cv = rate_cv(rates)

    # achieved POST-VETO rates, so match quality is auditable rather than assumed
    ach = cv.merge(match[["tau", "slot_k"]], on="tau", how="left")
    achieved = []
    for r in match.itertuples():
        aa = ach.query("tau == @r.tau and arm == 'abs' and k == @r.abs_k")
        ss = ach.query("tau == @r.tau and arm == 'slot' and k == @r.slot_k")
        if aa.empty or ss.empty:
            continue
        ra, rs = float(aa.mean_rate.iloc[0]), float(ss.mean_rate.iloc[0])
        achieved.append({"tau": int(r.tau), "achieved_rate_abs": ra, "achieved_rate_slot": rs,
                         "achieved_gap_pct": abs(rs - ra) / ra * 100.0})
    match = match.merge(pd.DataFrame(achieved), on="tau", how="left")

    run.log("outcome surface (both arms, both delays)")
    surf = surface(signals, cfg)

    run.log("applying the frozen decision rules")
    verdict = decide(cv, match, surf, cfg)

    run.log("F3: UTC-day-clustered session-difference contrast")
    cc = session_contrast(signals, match, cfg)
    verdict["Q2_session_localisation"]["clustered_contrast"] = cc

    def _clears(d):
        return np.isfinite(d["ci_low"]) and np.isfinite(d["ci_high"]) and \
            (d["ci_low"] > 0 or d["ci_high"] < 0)
    off_s = cc["slot"]["off_minus_london"]
    asia_s = cc["slot"]["asia_minus_london"]
    verdict["Q2_session_localisation"]["clustered_conclusion"] = (
        f"Proper UTC-day-clustered difference (slot arm): off−london "
        f"{off_s['diff']:+.3f} CI[{off_s['ci_low']:+.3f},{off_s['ci_high']:+.3f}] "
        f"({'excludes' if _clears(off_s) else 'includes'} 0); asia−london "
        f"{asia_s['diff']:+.3f} CI[{asia_s['ci_low']:+.3f},{asia_s['ci_high']:+.3f}] "
        f"({'excludes' if _clears(asia_s) else 'includes'} 0). "
        "Normalising SHRINKS both gaps versus the confounded abs arm (off "
        f"{cc['abs']['off_minus_london']['diff']:+.3f}→{off_s['diff']:+.3f}, asia "
        f"{cc['abs']['asia_minus_london']['diff']:+.3f}→{asia_s['diff']:+.3f}), so the "
        "clock explained most of off's apparent localisation and part of asia's. "
        "What remains is a MARGINAL asia gap on INSPECTED history, one of several "
        "contrasts, without the arm-by-session interaction Codex asked for. Verdict: "
        "off−london not established; asia−london provisional and NOT actionable yet — "
        "it is the motivation for the axis-4 session test (full pipeline), not a prior "
        "to fold into an overlay now.")

    run.log("writing artifacts")
    (ARTIFACT / "verdict.json").write_text(json.dumps(verdict, indent=2, default=str), encoding="utf-8")
    (ARTIFACT / "run_manifest.json").write_text(json.dumps({
        "experiment_id": "EXP-0003", "stage": "A-addendum",
        "hypothesis": "experiments/hypotheses/HYP-0003.md", "config": cfg,
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "signals_total": int(len(signals)),
        "reuses": "forex/exploration_4/_run_stage_a.py (loading, forward outcomes, costs, "
                  "cell pooling, cluster-robust estimator) and _stage_a_lib.py",
    }, indent=2), encoding="utf-8")
    for name, obj in (("firing_rates_by_hour", rates), ("firing_rate_cv", cv),
                      ("matched_k", match), ("surface", surf), ("eligible_bars", eligible),
                      ("crossing_counts", counts)):
        obj.to_csv(ARTIFACT / f"{name}.csv", index=False)

    write_report(cfg, rates, cv, match, surf, verdict)
    run.log("done: " + verdict["Q3_grain"]["verdict"])


def write_report(cfg, rates, cv, match, surf, verdict) -> None:
    tt = lib.to_text_table
    slot_k = verdict["matched_k_by_tau"]
    mk = {int(r["tau"]): float(r["slot_k"]) for r in slot_k}
    k5 = mk.get(5)

    ref_k = cfg["reference_k"]
    hr = (rates.query("tau == 5 and ((arm == 'abs' and k == @ref_k) or "
                      "(arm == 'slot' and k == @k5))")
          .pivot_table(index="utc_hour", columns="arm", values="fire_rate").reset_index())
    hr.columns = ["utc_hour"] + [f"fire_rate_{c}" for c in hr.columns[1:]]
    for c in hr.columns[1:]:
        hr[c] = hr[c] * 100.0

    cvt = cv.query("(arm == 'abs' and k == @ref_k) or arm == 'slot'")[
        ["tau", "arm", "k", "signals", "mean_rate", "min_rate", "max_rate", "cv", "max_over_min"]
    ].sort_values(["tau", "arm", "k"])

    sess = surf.query("pair == 'POOLED' and era == 'consumed' and tau == 5 and "
                      "entry_delay_bars == 1 and horizon_minutes == 240 and "
                      "((arm == 'abs' and k == @ref_k) or (arm == 'slot' and k == @k5))")[
        ["session", "arm", "n", "gross_R_abs", "gross_R_abs_ci_low", "gross_R_abs_ci_high",
         "gross_R_abs_t", "gross_pips"]].sort_values(["session", "arm"])

    grain = pd.DataFrame(verdict["Q3_grain"]["detail"])
    grain_search = pd.DataFrame(verdict["Q3_grain"]["search_detail"])
    q4 = verdict["Q4_information"]

    ladder = surf.query("pair == 'POOLED' and era == 'consumed' and session == 'all' and "
                        "entry_delay_bars == 1")
    ladder = ladder.loc[ladder.apply(lambda r: (r["arm"] == "abs" and r["k"] == ref_k)
                                     or (r["arm"] == "slot" and r["k"] == mk.get(int(r["tau"]))), axis=1)][
        ["tau", "arm", "k", "horizon_minutes", "n", "gross_R_abs", "gross_R_abs_t",
         "gross_pips", "cost_pips_base"]].sort_values(["tau", "horizon_minutes", "arm"])

    q1, q2, q3 = verdict["Q1_firing_rate"], verdict["Q2_session_localisation"], verdict["Q3_grain"]
    text = f"""# Same-Slot Addendum — Stage A (EXP-0003)

Contract: `experiments/hypotheses/HYP-0003.md`, frozen before this run. Reproduce with
`python -u forex/exploration_4/_run_same_slot.py`.

**Numbering:** the run-book assigns EXP-0003 to Stage B; the ledger requires
`EXP-\\d{{4}}`, so this addendum is EXP-0003 and **Stage B becomes EXP-0004**.

**Honest label (Stage-A repair F1):** this addendum re-runs the grain/threshold
selection on the SAME inspected 2012–2023 outcomes with a new normaliser. It is a
confound test and a reconstruction, **not independent confirmation**. τ\\*=5 / H\\*=240
remain **consumed-history, gross-P&L-selected candidates**; "confirmed under the
same-slot arm" below means the selection is stable to removing the clock confound, not
that it cleared a fresh holdout. Any inferential claim on the selected maximum needs a
full-pipeline null that repeats the selection. Only future data is a clean holdout now.

## Why

EXP-0002 measured `z = ret_τ / σ_τ` against an all-hours 28,800-minute σ. That window
cannot see the intraday volatility profile — median σ moves only 3.156→3.179 pips across
all 24 UTC hours at τ=5 — while actual bar sizes move a great deal. The fixed `|z| ≥ 2`
cut therefore fired on **0.96%** of decisions at 04:00 UTC and **10.11%** at 14:00
(**CV 0.707**). That is a threshold acting as a time-of-day selector.

Both arms are built on **one common decision sample** (bars where *both* σ estimators are
warmed up), so neither arm can look better merely by being defined on different rows.
Thresholds are **matched by picking a swept `k`**, never by interpolating a frontier —
`np.interp` clamps, which would silently turn a matched-rate comparison into an
extrapolation.

`gross_R_abs` is the cross-arm yardstick: mean R with **R = absolute σ_τ for both arms**.
Each arm's own-σ R is also carried in `surface.csv`, but own-R figures are not comparable
across arms.

---

## Q1 — Does the normaliser work?

Selection rate by UTC hour at τ=5, `abs` at k={cfg['reference_k']} vs `slot` at
k={k5} (rate-matched), consumed history, percent of eligible decisions:

{tt(hr, 3)}

Cross-hour CV by grain and threshold:

{tt(cvt, 4)}

**abs CV = {q1['abs_cv']:.3f} → slot CV = {q1['slot_cv']:.3f}**
(pass threshold {cfg['cv_pass_threshold']}). **{q1['verdict']}**

## Q2 — Was the thin-hours localisation real, or was it the clock?

τ=5, H=240, **delay-1 arm**, at matched firing rate. The pre-committed rule: the
localisation survives only if `off` or `asia` still exceeds `london` by more than the
sum of the two cells' 95% CI half-widths.

{tt(sess, 4)}

```json
{json.dumps({k: v for k, v in q2.items() if k != 'clustered_contrast'}, indent=2, default=str)}
```

**{q2['outcome']}**

### Proper UTC-day-clustered difference contrast (F3)

The screen above compares a session gap to the **sum of two marginal CI half-widths** —
a deliberately conservative heuristic, not a confidence interval for the difference, and
blind to the covariance between two session estimators that share a UTC day. The correct
test is a UTC-day-clustered CI on the difference itself (`off − london`, `asia − london`),
influence functions subtracted within each cluster. Both arms shown; the `slot` arm is the
decision arm.

```json
{json.dumps(q2.get('clustered_contrast', {}), indent=2, default=str)}
```

**{q2.get('clustered_conclusion', '')}**

The sum-of-half-widths screen (above) is strictly more conservative than this difference CI;
where the two disagree, the difference CI is the correct test. It clears zero for `asia` and
not for `off`, so the clean "both retracted" reading from the screen is too strong. The
economics are unchanged either way: gross stays ~3× under cost, and a thin-hour like `asia`
carries a mechanical R_slot lift (its σ_slot is small), so a positive `asia` R gap is exactly
what the busy/thin-hour σ structure predicts and is not by itself evidence of tradable edge.

**Departure from the frozen contract:** {q2['matching_departure']}

## Q3 — Does the grain choice survive?

**Primary ranking: fixed preregistered horizon H\\*={q3['primary_horizon_minutes']}** (HYP-0003 §4).
Ladder ranked by `gross_R_abs`, `slot` arm, delay-1, each rung at its own rate-matched
`k`, **no horizon searched**:

{tt(grain, 4)}

**{q3['verdict']}**

*Robustness only (not the decision):* the same ladder ranked by the **best of horizons
{{60, 240}}** — a two-horizon search that can only flatter a grain by picking its better
horizon. It ranks {q3['search_ranking']} with top τ={q3['search_top_tau']}. This is
reported for transparency; the grain decision rests on the fixed-H\\* table above.

{tt(grain_search, 4)}

### Full ladder, both arms side by side (delay-1, rate-matched)

{tt(ladder, 4)}

## Q4 — Does normalising destroy the information?

Compared at matched firing rate, same risk unit, delay-1, τ=5:

```json
{json.dumps(q4, indent=2, default=str)}
```

Read `gross_pips` against `cost_pips_base`: the breakeven round-trip pip is the number
that decides deployability, and renormalising a threshold cannot move a ~0.4-pip gross
edge past a ~1.2-pip round trip.

## Limitations

- UTC slots do not track DST, so a slot's meaning shifts by an hour twice a year against
  London and New York local time, blending two adjacent hours' volatility for part of the
  year. Documented, not corrected.
- The slot estimator warms up ~90 sessions later than the all-hours one. Handled by the
  common-sample construction rather than by ignoring it.
- 2024+ remains sealed; nothing here reads it.
"""
    (REPORTS / "SAME_SLOT_ADDENDUM.md").write_text(text, encoding="utf-8")
    (ARTIFACT / "SAME_SLOT_ADDENDUM.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
