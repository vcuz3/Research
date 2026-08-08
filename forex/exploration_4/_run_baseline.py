"""Run the frozen exploration_4 FX mean-reversion baseline.

Reproduce from the workspace root:
    python -u forex/exploration_4/_run_baseline.py

The script writes the Rule 9a data-quality gate first, then the registered
EXP-0001 material-run artifacts and current reports. Fill, gap-through, adverse
bracket resolution, stop slippage, cost, and macro-calendar logic are imported
from the audited exploration_1 implementation.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parent
WORKSPACE = PROJECT.parents[1]
EXPLORATION_1 = PROJECT.parent / "exploration_1"
if str(EXPLORATION_1) not in sys.path:
    sys.path.insert(0, str(EXPLORATION_1))

from _bracket_engine import simulate_bracket  # noqa: E402
from _cost_model import CostParams, round_trip_pips  # noqa: E402
from _rsi_stop_engine import PIP, simulate  # noqa: E402
from _run_rsi_axis6_calendar import high_impact_times  # noqa: E402


CONFIG_PATH = PROJECT / "baseline_replication" / "configs" / "baseline.json"
ARTIFACT = PROJECT / "artifacts" / "runs" / "EXP-0001"
REPORTS = PROJECT / "reports"
DATA = PROJECT.parent / "data" / "clean"


def read_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def era_of(index: pd.DatetimeIndex) -> np.ndarray:
    year = index.year.to_numpy()
    return np.where(year >= 2024, "holdout", np.where(year >= 2021, "late", "early"))


def markdown_table(frame: pd.DataFrame, decimals: int = 4) -> str:
    if frame.empty:
        return "_No rows._"
    show = frame.copy()
    for col in show.select_dtypes(include=["number"]).columns:
        show[col] = show[col].round(decimals)
    try:
        return show.to_markdown(index=False)
    except ImportError:
        return "```text\n" + show.to_string(index=False) + "\n```"


def cluster_stats(values, clusters) -> dict:
    z = pd.DataFrame({"value": np.asarray(values, float), "cluster": clusters}).dropna()
    n = len(z)
    groups = z.cluster.nunique()
    if n < 2 or groups < 2:
        return {"n": n, "clusters": groups, "mean": np.nan, "se": np.nan,
                "t": np.nan, "ci_low": np.nan, "ci_high": np.nan}
    mean = float(z.value.mean())
    scores = (z.value - mean).groupby(z.cluster).sum()
    se = float(np.sqrt((groups / (groups - 1)) * np.square(scores).sum()) / n)
    return {"n": n, "clusters": groups, "mean": mean, "se": se,
            "t": mean / se if se > 0 else np.nan,
            "ci_low": mean - 1.96 * se, "ci_high": mean + 1.96 * se}


def nearest_news_minutes(entry_times: pd.DatetimeIndex, events: np.ndarray) -> np.ndarray:
    et = entry_times.to_numpy().astype("datetime64[m]")
    if len(events) == 0:
        return np.full(len(et), np.inf)
    pos = np.searchsorted(events, et, side="left")
    nxt = np.full(len(et), np.inf)
    valid = pos < len(events)
    nxt[valid] = (events[pos[valid]] - et[valid]) / np.timedelta64(1, "m")
    prv = np.full(len(et), np.inf)
    valid = pos > 0
    prv[valid] = (et[valid] - events[pos[valid] - 1]) / np.timedelta64(1, "m")
    return np.minimum(np.abs(nxt), np.abs(prv))


def load_and_build(pair: str, cfg: dict) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """Load 1-minute midpoint bars, emit DQ rows, and build the frozen 5m feature."""
    path = DATA / f"{pair}_1m_clean.parquet"
    raw = pd.read_parquet(path, columns=["ts_utc", "open", "high", "low", "close"])
    original_time = pd.to_datetime(raw.ts_utc, utc=True)
    raw_overall = {
        "pair": pair,
        "rows": len(raw),
        "start": str(original_time.min()),
        "end": str(original_time.max()),
        "duplicates": int(original_time.duplicated().sum()),
        "out_of_order": int((original_time.diff().dropna() < pd.Timedelta(0)).sum()),
        "volume_field": "absent",
    }
    raw = raw.assign(time=original_time).sort_values("time", kind="stable")
    raw = raw.drop_duplicates("time", keep="last").reset_index(drop=True)
    delta = raw.time.diff().dt.total_seconds().div(60)
    gap = delta.gt(1)
    raw["era"] = era_of(pd.DatetimeIndex(raw.time))
    raw["utc_hour"] = raw.time.dt.hour
    raw["gap_count"] = gap.astype(int)
    raw["missing_minutes"] = np.where(gap, delta - 1, 0)
    raw["short_gap_count"] = (gap & delta.le(180)).astype(int)
    raw["short_missing_minutes"] = np.where(gap & delta.le(180), delta - 1, 0)
    hour_rows = (raw.groupby(["era", "utc_hour"], observed=True)
                 .agg(raw_rows=("time", "size"), utc_dates=("time", lambda x: x.dt.date.nunique()),
                      gaps=("gap_count", "sum"), missing_minutes=("missing_minutes", "sum"),
                      short_gaps=("short_gap_count", "sum"),
                      short_missing_minutes=("short_missing_minutes", "sum"))
                 .reset_index())
    hour_rows.insert(0, "pair", pair)

    indexed = raw.set_index("time")[["open", "high", "low", "close"]]
    bars = indexed.resample(f"{cfg['bar_minutes']}min", origin="epoch", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), minute_count=("close", "count"))
    complete = bars.minute_count.eq(cfg["bar_minutes"])
    bars.loc[~complete, ["open", "high", "low", "close"]] = np.nan
    ret1 = bars.close.pct_change(fill_method=None)
    ret1 = ret1.where(complete & complete.shift(1, fill_value=False))
    min_periods = int(math.ceil(cfg["vol_window_bars"] * cfg["vol_min_fraction"]))
    bars["sigma_count"] = ret1.rolling(cfg["vol_window_bars"], min_periods=1).count()
    bars["sigma"] = ret1.rolling(cfg["vol_window_bars"], min_periods=min_periods).std(ddof=1)
    n = cfg["trailing_return_bars"]
    full_trail = complete.rolling(n + 1, min_periods=n + 1).sum().eq(n + 1)
    bars["r_trail"] = (bars.close / bars.close.shift(n) - 1).where(full_trail)
    bars["z"] = bars.r_trail / (bars.sigma * np.sqrt(n))
    bars["complete"] = complete
    bars["era"] = era_of(bars.index)
    bars["utc_hour"] = bars.index.hour
    bars["utc_day"] = bars.index.floor("D").tz_localize(None)
    ny = bars.index.tz_convert("America/New_York")
    bars["ny_minute"] = ny.hour * 60 + ny.minute

    decision = bars.index >= pd.Timestamp(cfg["start"])
    feat = pd.DataFrame(index=bars.index)
    feat["eligible_5m_bars"] = (decision & complete).astype(int)
    feat["incomplete_5m_bars"] = (decision & ~complete).astype(int)
    feat["sigma_underpop"] = (decision & complete & bars.sigma_count.lt(min_periods)).astype(int)
    feat["z_unavailable"] = (decision & complete & bars.z.isna()).astype(int)
    feat["era"] = bars.era
    feat["utc_hour"] = bars.utc_hour
    feat_rows = (feat.loc[decision].groupby(["era", "utc_hour"], observed=True)
                 .agg(eligible_5m_bars=("eligible_5m_bars", "sum"),
                      incomplete_5m_bars=("incomplete_5m_bars", "sum"),
                      sigma_underpop=("sigma_underpop", "sum"),
                      z_unavailable=("z_unavailable", "sum"))
                 .reset_index())
    feat_rows.insert(0, "pair", pair)
    raw_overall.update({
        "five_minute_bins": len(bars),
        "complete_five_minute_bars": int(complete.sum()),
        "incomplete_five_minute_bins": int((~complete).sum()),
        "vol_min_periods": min_periods,
    })
    return bars, [raw_overall], hour_rows.merge(feat_rows, on=["pair", "era", "utc_hour"], how="outer").to_dict("records")


def candidate_frame(pair: str, bars: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cond = bars.z.abs().ge(cfg["entry_k"]).fillna(False)
    contiguous = bars.complete & bars.complete.shift(1, fill_value=False)
    crossing = cond & ~(cond.shift(1, fill_value=False) & contiguous)
    signal_idx = np.flatnonzero(crossing.to_numpy() & (bars.index >= pd.Timestamp(cfg["start"])))
    signal_idx = signal_idx[signal_idx + 1 < len(bars)]
    entry_idx = signal_idx + 1
    entry_ok = bars.complete.to_numpy()[entry_idx]
    signal_idx, entry_idx = signal_idx[entry_ok], entry_idx[entry_ok]

    local_boundary = bars.ny_minute.to_numpy() == 17 * 60
    boundary_indices = np.flatnonzero(local_boundary)
    pos = np.searchsorted(boundary_indices, entry_idx, side="right")
    has_boundary = pos < len(boundary_indices)
    boundary_idx = np.full(len(entry_idx), -1, int)
    boundary_idx[has_boundary] = boundary_indices[pos[has_boundary]]
    boundary_bars = boundary_idx - entry_idx
    has_boundary &= (boundary_bars >= 1) & (boundary_bars <= 300)

    out = pd.DataFrame({
        "pair": pair,
        "signal_idx": signal_idx,
        "entry_idx": entry_idx,
        "boundary_idx": boundary_idx,
        "boundary_bars": boundary_bars,
        "has_boundary": has_boundary,
        "signal_time": bars.index[signal_idx],
        "entry_time": bars.index[entry_idx],
        "side": np.where(bars.z.to_numpy()[signal_idx] < 0, 1.0, -1.0),
        "z_signal": bars.z.to_numpy()[signal_idx],
        "r_trail_signal": bars.r_trail.to_numpy()[signal_idx],
        "sigma": bars.sigma.to_numpy()[signal_idx],
        "era": bars.era.to_numpy()[signal_idx],
        "utc_hour": bars.index[entry_idx].hour,
        "utc_day": bars.index[entry_idx].floor("D").tz_localize(None),
    })
    ev = high_impact_times(pair)
    out["news_distance_minutes"] = nearest_news_minutes(pd.DatetimeIndex(out.entry_time), ev)
    out["news_veto"] = out.news_distance_minutes.lt(cfg["news_blackout_minutes"])
    out["trade_id"] = pair + "_" + out.signal_time.dt.strftime("%Y%m%dT%H%M%SZ")
    return out


def simulate_candidate_batches(cand: pd.DataFrame, bars: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, int]:
    arrays = {name: bars[name].to_numpy(float) for name in ["open", "high", "low", "close"]}
    zall = bars.z.to_numpy(float)
    complete = bars.complete.to_numpy(bool)
    kept = []
    path_excluded = 0
    slip = cfg["stop_slippage_pips"]
    for start in range(0, len(cand), 4000):
        d = cand.iloc[start:start + 4000].copy()
        d = d.loc[d.has_boundary].copy()
        if d.empty:
            continue
        max_h = int(d.boundary_bars.max())
        offs = np.arange(max_h + 1)[None, :]
        take = d.entry_idx.to_numpy()[:, None] + offs
        need = offs <= d.boundary_bars.to_numpy()[:, None]
        valid = np.all(~need | complete[take], axis=1)
        path_excluded += int((~valid).sum())
        d = d.loc[valid].reset_index(drop=True)
        take = take[valid]
        need = need[valid]
        if d.empty:
            continue
        paths = {name: values[take] for name, values in arrays.items()}
        side = d.side.to_numpy(float)
        zpath = zall[take]
        live_for_target = np.arange(max_h + 1)[None, :] < d.boundary_bars.to_numpy()[:, None]
        target_hit = live_for_target & np.isfinite(zpath) & (side[:, None] * zpath >= 0)
        has_target = target_hit.any(axis=1)
        target_bar = np.where(has_target, target_hit.argmax(axis=1), -1)
        planned_exit = np.where(has_target, target_bar + 1, d.boundary_bars.to_numpy())
        entry = paths["open"][:, 0]
        sigma_pips = d.sigma.to_numpy() * entry / PIP
        risk_pips = cfg["stop_sigma"] * sigma_pips
        pnl, stopped, stop_bar = simulate(paths, side, risk_pips, planned_exit,
                                           slippage_pips=slip, pip=PIP)
        actual_exit = np.where(stopped, stop_bar, planned_exit)
        rows = np.arange(len(d))
        exit_px = entry + side * pnl * PIP
        d["entry_px"] = entry
        d["sigma_pips"] = sigma_pips
        d["risk_pips"] = risk_pips
        d["planned_exit_bars"] = planned_exit
        d["target_observed"] = has_target
        d["stopped"] = stopped
        d["stop_bar"] = stop_bar
        d["actual_exit_bars"] = actual_exit
        d["actual_exit_idx"] = d.entry_idx.to_numpy() + actual_exit
        d["exit_time"] = bars.index[d.actual_exit_idx.to_numpy()]
        d["exit_px"] = exit_px
        d["exit_kind"] = np.where(stopped, "stop", np.where(has_target, "reversion", "session_boundary"))
        d["gross_pips"] = pnl
        d["gross_R"] = pnl / risk_pips
        d["reward_risk_proxy"] = (np.abs(d.r_trail_signal.to_numpy()) * entry / PIP) / risk_pips
        kept.append(d)
    if not kept:
        return pd.DataFrame(), path_excluded
    return pd.concat(kept, ignore_index=True).sort_values("signal_time").reset_index(drop=True), path_excluded


def stateful_select(cand: pd.DataFrame, allow) -> np.ndarray:
    selected = np.zeros(len(cand), bool)
    last_exit = -1
    for i, row in cand.iterrows():
        if not bool(allow.iloc[i] if isinstance(allow, pd.Series) else allow[i]):
            continue
        if int(row.signal_idx) >= last_exit:
            selected[i] = True
            last_exit = int(row.actual_exit_idx)
    return selected


def add_costs(trades: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    for scenario in ["optimistic", "base", "pessimistic"]:
        for include_vol, suffix in [(True, "vol"), (False, "flatvol")]:
            cost = np.empty(len(trades), float)
            for pair, loc in trades.groupby("pair").groups.items():
                ii = np.asarray(list(loc), int)
                med = float(np.nanmedian(trades.loc[ii, "sigma_pips"]))
                vr = trades.loc[ii, "sigma_pips"].to_numpy() / med if med > 0 else 1.0
                cost_era = np.where(trades.loc[ii, "era"].eq("early"), "early", "late")
                params = CostParams(scenario=scenario, include_vol=include_vol)
                cost[ii] = round_trip_pips(pair, trades.loc[ii, "utc_hour"].to_numpy(),
                                            cost_era, vr, params)
            trades[f"cost_{scenario}_{suffix}_pips"] = cost
            trades[f"net_{scenario}_{suffix}_pips"] = trades.gross_pips - cost
            trades[f"net_{scenario}_{suffix}_R"] = trades[f"net_{scenario}_{suffix}_pips"] / trades.risk_pips
    return trades


def add_diagnostics(trades: pd.DataFrame, bars_by_pair: dict[str, pd.DataFrame], cfg: dict) -> pd.DataFrame:
    out = []
    for pair, d0 in trades.groupby("pair", sort=False):
        d = d0.copy()
        bars = bars_by_pair[pair]
        arrays = {name: bars[name].to_numpy(float) for name in ["open", "high", "low", "close"]}
        max_h = int(d.boundary_bars.max())
        take = d.entry_idx.to_numpy()[:, None] + np.arange(max_h + 1)[None, :]
        paths = {name: values[take] for name, values in arrays.items()}
        sym = np.empty(len(d), float)
        sym_kind = np.empty(len(d), int)
        for horizon in np.unique(d.boundary_bars.to_numpy()):
            loc = np.flatnonzero(d.boundary_bars.to_numpy() == horizon)
            p = {name: value[loc, :horizon + 1] for name, value in paths.items()}
            pnl, kind = simulate_bracket(p, d.side.to_numpy()[loc], d.risk_pips.to_numpy()[loc],
                                         d.risk_pips.to_numpy()[loc], int(horizon),
                                         slippage_pips=cfg["stop_slippage_pips"], pip=PIP)
            sym[loc], sym_kind[loc] = pnl, kind
        h = cfg["fixed_horizon_bars"]
        fp = {name: value[:, :h + 1] for name, value in paths.items()}
        fixed, fixed_stopped, _ = simulate(fp, d.side.to_numpy(), d.risk_pips.to_numpy(), h,
                                            slippage_pips=cfg["stop_slippage_pips"], pip=PIP)
        raw_forward = d.side.to_numpy() * (fp["open"][:, h] - fp["open"][:, 0]) / PIP
        d["symmetric_pips"] = sym
        d["symmetric_R"] = sym / d.risk_pips
        d["symmetric_kind"] = sym_kind
        d["fixed_pips"] = fixed
        d["fixed_R"] = fixed / d.risk_pips
        d["fixed_stopped"] = fixed_stopped
        d["raw_forward_pips"] = raw_forward
        d["raw_forward_R"] = raw_forward / d.risk_pips
        out.append(d)
    return pd.concat(out, ignore_index=True).sort_values(["entry_time", "pair"]).reset_index(drop=True)


def random_exit_null(trades: pd.DataFrame, bars_by_pair: dict[str, pd.DataFrame], cfg: dict) -> tuple[pd.DataFrame, dict]:
    hist = trades.loc[trades.era.ne("holdout")].reset_index(drop=True)
    rng = np.random.default_rng(cfg["random_seed"])
    observed = float(hist.gross_R.mean())
    draws = np.empty(cfg["random_exit_draws"], float)
    donor = {(p, h): g.planned_exit_bars.to_numpy(int)
             for (p, h), g in hist.groupby(["pair", "utc_hour"])}
    fallback = {p: g.planned_exit_bars.to_numpy(int) for p, g in hist.groupby("pair")}
    paths_open = {}
    stop_pnl = np.empty(len(hist), float)
    stop_bar = np.empty(len(hist), int)
    for pair, loc in hist.groupby("pair").groups.items():
        ii = np.asarray(list(loc), int)
        d = hist.loc[ii]
        bars = bars_by_pair[pair]
        max_h = int(d.boundary_bars.max())
        take = d.entry_idx.to_numpy()[:, None] + np.arange(max_h + 1)[None, :]
        p = {name: bars[name].to_numpy(float)[take] for name in ["open", "high", "low"]}
        pnl, stopped, sb = simulate(p, d.side.to_numpy(), d.risk_pips.to_numpy(),
                                    d.boundary_bars.to_numpy(),
                                    slippage_pips=cfg["stop_slippage_pips"], pip=PIP)
        stop_pnl[ii] = pnl
        stop_bar[ii] = np.where(stopped, sb, -1)
        paths_open[pair] = (ii, p["open"])
    for draw in range(cfg["random_exit_draws"]):
        pnl = np.empty(len(hist), float)
        for pair, (ii, opens) in paths_open.items():
            d = hist.loc[ii]
            sampled = np.empty(len(ii), int)
            for j, (_, row) in enumerate(d.iterrows()):
                pool = donor.get((pair, int(row.utc_hour)), fallback[pair])
                sampled[j] = int(rng.choice(pool))
            sampled = np.minimum(sampled, d.boundary_bars.to_numpy(int))
            stopped_first = (stop_bar[ii] >= 0) & (stop_bar[ii] < sampled)
            rows = np.arange(len(ii))
            time_pnl = d.side.to_numpy() * (opens[rows, sampled] - opens[:, 0]) / PIP
            pnl[ii] = np.where(stopped_first, stop_pnl[ii], time_pnl)
        draws[draw] = float(np.mean(pnl / hist.risk_pips.to_numpy()))
    frame = pd.DataFrame({"draw": np.arange(1, len(draws) + 1), "mean_gross_R": draws})
    result = {
        "observed_mean_gross_R": observed,
        "null_mean": float(draws.mean()),
        "null_sd": float(draws.std(ddof=1)),
        "null_q05": float(np.quantile(draws, 0.05)),
        "null_q95": float(np.quantile(draws, 0.95)),
        "one_sided_p": float((1 + np.sum(draws >= observed)) / (len(draws) + 1)),
        "passes": bool(observed > np.quantile(draws, 0.95)),
        "preserves": "pair/hour exit-duration distribution, paths, entries, stops, costs",
        "destroys": "alignment between each path and its reversion-exit time",
    }
    return frame, result


def metric_rows(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    outcomes = {
        "primary_gross_R": "gross_R",
        "primary_base_net_R": "net_base_vol_R",
        "symmetric_gross_R": "symmetric_R",
        "fixed_stop_gross_R": "fixed_R",
        "raw_forward_R": "raw_forward_R",
    }
    scopes = [("all", trades), ("consumed", trades.loc[trades.era.ne("holdout")])]
    scopes += [(era, trades.loc[trades.era.eq(era)]) for era in ["early", "late", "holdout"]]
    for scope, sd in scopes:
        for pair, g in [("POOLED", sd)] + list(sd.groupby("pair", sort=True)):
            for outcome, col in outcomes.items():
                s = cluster_stats(g[col], g.utc_day)
                block = g.groupby("utc_day")[col].agg(["mean", "count"])
                rows.append({"scope": scope, "pair": pair, "outcome": outcome, **s,
                             "session_mean_R": float(block["mean"].mean()) if len(block) else np.nan,
                             "corr_block_mean_count": float(block["mean"].corr(block["count"])) if len(block) > 2 else np.nan,
                             "hit_rate": float((g[col] > 0).mean()) if len(g) else np.nan})
    return pd.DataFrame(rows)


def cost_table(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (era, hour, pair), g in trades.groupby(["era", "utc_hour", "pair"], observed=True):
        for scenario in ["optimistic", "base", "pessimistic"]:
            for vol_term in ["vol", "flatvol"]:
                rows.append({
                    "era": era, "utc_hour": hour, "pair": pair, "scenario": scenario,
                    "vol_term": vol_term, "signals": len(g),
                    "gross_pips": float(g.gross_pips.mean()),
                    "cost_pips": float(g[f"cost_{scenario}_{vol_term}_pips"].mean()),
                    "net_pips": float(g[f"net_{scenario}_{vol_term}_pips"].mean()),
                    "net_R": float(g[f"net_{scenario}_{vol_term}_R"].mean()),
                    "breakeven_round_trip_pips": float(g.gross_pips.mean()),
                })
    return pd.DataFrame(rows)


def daily_marked(trades: pd.DataFrame, bars_by_pair: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for _, t in trades.iterrows():
        entry_time = pd.Timestamp(t.entry_time)
        exit_time = pd.Timestamp(t.exit_time)
        checkpoints = list(pd.date_range(entry_time.normalize() + pd.Timedelta(days=1),
                                         exit_time.normalize(), freq="D", tz="UTC"))
        prices = [float(t.entry_px)]
        times = [entry_time]
        bars = bars_by_pair[t.pair]
        for cp in checkpoints:
            if cp < exit_time and cp in bars.index and np.isfinite(bars.at[cp, "open"]):
                times.append(cp)
                prices.append(float(bars.at[cp, "open"]))
        times.append(exit_time)
        prices.append(float(t.exit_px))
        for j in range(1, len(prices)):
            day = (times[j] - pd.Timedelta(nanoseconds=1)).date() if times[j].hour == 0 and times[j].minute == 0 else times[j].date()
            gross_R = float(t.side * (prices[j] - prices[j - 1]) / PIP / t.risk_pips)
            rows.append({"date": pd.Timestamp(day), "pair": t.pair, "era": t.era,
                         "gross_R": gross_R, "net_R": gross_R})
        rows[-(len(prices) - 1)]["net_R"] -= float(t.cost_base_vol_pips / t.risk_pips)
    daily = pd.DataFrame(rows)
    return daily.groupby(["date", "era"], as_index=False)[["gross_R", "net_R"]].sum()


def sharpe_rows(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    scopes = [("all", daily), ("consumed", daily.loc[daily.era.ne("holdout")])]
    scopes += [(e, daily.loc[daily.era.eq(e)]) for e in ["early", "late", "holdout"]]
    for scope, z in scopes:
        if z.empty:
            continue
        all_days = pd.date_range(z.date.min(), z.date.max(), freq="B")
        series = z.set_index("date").net_R.reindex(all_days, fill_value=0.0)
        active = series.loc[series.ne(0)]
        hist_vol = series.rolling(20, min_periods=10).std().shift(1)
        target = float(hist_vol.median())
        lev = (target / hist_vol).clip(0.25, 4.0).fillna(1.0)
        targeted = series * lev
        def sh(x):
            sd = float(x.std(ddof=1))
            return float(np.sqrt(252) * x.mean() / sd) if len(x) > 1 and sd > 0 else np.nan
        rows.append({"scope": scope, "zero_day_sharpe": sh(series),
                     "trade_days_only_sharpe": sh(active), "vol_targeted_sharpe": sh(targeted),
                     "business_days": len(series), "active_days": len(active),
                     "worst_day_R": float(series.min()),
                     "max_drawdown_R": float((series.cumsum().cummax() - series.cumsum()).max())})
    return pd.DataFrame(rows)


def write_dq(overall: pd.DataFrame, detail: pd.DataFrame, path_exclusions: dict) -> None:
    overall.to_csv(ARTIFACT / "data_quality_overall.csv", index=False)
    detail.to_csv(ARTIFACT / "data_quality_by_hour.csv", index=False)
    dq = f"""# Data Quality Report — Rule 9a

Generated by `python -u forex/exploration_4/_run_baseline.py` before result
interpretation. Source fields are midpoint OHLC only. Contrary to the plan's
wording, `volume` is **absent**, not present as `-1`; either way no volume or
bid/ask inference is possible.

## Overall source and resampling checks

{markdown_table(overall)}

The resampler is UTC/epoch anchored, left-closed 5-minute OHLC. A 5-minute bar is
tradable only when all five source minutes exist. Returns across incomplete bars
are null. Rolling volatility uses 100 time-aligned 5-minute bins with the frozen
90% floor (`min_periods=90`); unavailable features are counted below and dropped
causally. Weekend/holiday empty bins are therefore not allowed to borrow stale
Friday observations.

## Per-pair, era, and UTC-hour coverage

`missing_minutes` includes scheduled weekend closures. `short_*` restricts gaps
to at most 180 minutes and is the more useful unscheduled-gap diagnostic.

{markdown_table(detail, 2)}

## Path feasibility exclusions

Candidates need complete OHLC from next-bar entry through the next 17:00 New York
session-boundary event (at most 300 five-minute bars, allowing DST transitions).
Rows failing that causal price-availability gate were not credited with fills:

{markdown_table(pd.DataFrame([{"pair": p, "candidate_paths_excluded": n} for p, n in path_exclusions.items()]))}
"""
    (REPORTS / "DATA_QUALITY.md").write_text(dq, encoding="utf-8")
    (ARTIFACT / "DATA_QUALITY.md").write_text(dq, encoding="utf-8")


def kill_test(trades: pd.DataFrame, metrics: pd.DataFrame, null_result: dict, cfg: dict) -> dict:
    hist = trades.loc[trades.era.ne("holdout")]
    gross_pips = float(hist.gross_pips.mean())
    base_cost = float(hist.cost_base_vol_pips.mean())
    primary = metrics.query("scope == 'consumed' and pair == 'POOLED' and outcome == 'primary_base_net_R'").iloc[0]
    sym = metrics.query("scope == 'consumed' and pair == 'POOLED' and outcome == 'symmetric_gross_R'").iloc[0]
    fixed = metrics.query("scope == 'consumed' and pair == 'POOLED' and outcome == 'fixed_stop_gross_R'").iloc[0]
    win = float((hist.gross_pips > 0).mean())
    rr = float(hist.reward_risk_proxy.mean())
    break_even = 1.0 / (1.0 + rr)
    conditions = {
        "gross_le_base_cost": gross_pips <= base_cost,
        "win_rate_near_geometry_break_even": abs(win - break_even) <= cfg["break_even_win_tolerance"],
        "base_net_ci_includes_zero": not (float(primary.ci_low) > 0),
        "symmetric_diagnostic_fails": not (float(sym.ci_low) > 0),
        "fixed_horizon_diagnostic_fails": not (float(fixed.ci_low) > 0),
        "random_exit_null_fails": not bool(null_result["passes"]),
    }
    return {
        "verdict": "NO-GO" if any(conditions.values()) else "GO",
        "conditions": conditions,
        "gross_mean_pips": gross_pips,
        "base_cost_mean_pips": base_cost,
        "base_net_mean_R": float(primary["mean"]),
        "base_net_ci": [float(primary.ci_low), float(primary.ci_high)],
        "realized_win_rate": win,
        "reward_risk_proxy": rr,
        "geometry_break_even_win_rate": break_even,
        "win_rate_tolerance": cfg["break_even_win_tolerance"],
        "random_exit": null_result,
    }


def write_findings(trades, metrics, costs, sharpes, blackout, null_result, verdict, cfg):
    headline = metrics.query("pair == 'POOLED' and outcome in ['primary_gross_R','primary_base_net_R','symmetric_gross_R','fixed_stop_gross_R','raw_forward_R'] and scope in ['consumed','holdout']")
    cost_view = (costs.query("vol_term == 'vol'")
                 .groupby(["era", "scenario"], as_index=False)
                 .apply(lambda g: pd.Series({"signals": int(g.signals.sum()),
                                             "gross_pips": np.average(g.gross_pips, weights=g.signals),
                                             "cost_pips": np.average(g.cost_pips, weights=g.signals),
                                             "net_pips": np.average(g.net_pips, weights=g.signals)}), include_groups=False)
                 .reset_index(drop=True))
    pair_view = metrics.query("scope == 'consumed' and outcome == 'primary_base_net_R'")
    holdout = metrics.query("scope == 'holdout' and pair == 'POOLED' and outcome == 'primary_base_net_R'")
    findings = f"""# exploration_4 Findings — Frozen Mean-Reversion Baseline

## Verdict: **{verdict['verdict']}**

This was one pre-specified baseline, not a sweep. The headline is per-signal
base-cost net R with UTC-day clustered uncertainty. Costs are modeled because
the midpoint archive has neither bid/ask nor volume; the breakeven round-trip is
therefore reported rather than presented as a measured spread.

Kill-test conditions (`true` means the NO-GO condition fired):

```json
{json.dumps(verdict['conditions'], indent=2)}
```

## Headline and mandatory entry diagnostics

{markdown_table(headline[["scope", "outcome", "n", "clusters", "mean", "se", "t", "ci_low", "ci_high", "hit_rate"]])}

The symmetric bracket uses the same session-boundary event as the main book,
with target and stop both at 1.5 frozen sigma. The fixed-horizon arm uses six
5-minute bars and retains the compulsory stop. `raw_forward_R` additionally shows
the unstopped next-open-to-next-open return. A diagnostic only passes the frozen
kill rule when its consumed-history 95% clustered CI is strictly above zero.

## Matched-rate random-exit control

The null preserves each pair/hour exit-duration distribution, identical entries,
price paths, compulsory stop and costs, while randomly re-pairing exit durations
to destroy alignment between path and reversion timing. It used
{cfg['random_exit_draws']:,} seeded draws.

```json
{json.dumps(null_result, indent=2)}
```

## Cost economics by era

{markdown_table(cost_view)}

The full 24-hour table, including the expensive 21:00 UTC rollover and the
with/without-volatility cost sweep, is `artifacts/runs/EXP-0001/cost_by_era_hour.csv`.
For a constant round-trip pip charge, each cell's breakeven is its gross mean
pips. Modeled commission alone is 0.7 pip round trip for all four quote-USD pairs.

## Per-pair consumed-history result

{markdown_table(pair_view[["pair", "n", "mean", "se", "t", "ci_low", "ci_high", "hit_rate", "session_mean_R", "corr_block_mean_count"]])}

`session_mean_R` is shown only as the requested warning diagnostic. It is not the
estimand. `corr_block_mean_count` quantifies the dependence that makes retrospective
session averaging unsafe.

## News blackout accounting

{markdown_table(blackout)}

Stateful non-overlap was re-run for the unvetoed and vetoed books; the comparison
is not a post-hoc filter of completed trades.

## Portfolio risk and the three Sharpes

{markdown_table(sharpes)}

Daily P&L is marked across UTC midnights and summed across pairs. `zero_day_sharpe`
includes zero-P&L business days; `trade_days_only_sharpe` excludes them;
`vol_targeted_sharpe` uses a causal trailing-20-business-day volatility estimate,
median target and leverage clipped to 0.25–4.0. All use 252-day annualization.

## Sealed 2024+ holdout — opened once at final reporting

{markdown_table(holdout[["n", "clusters", "mean", "se", "t", "ci_low", "ci_high", "hit_rate"]])}

The holdout is reported separately and does not rescue a historical kill-test
failure. All available 2024-01-01 through the source end are included.

## Scope boundary

No regimes, alternative thresholds, clocks, anchors, pair features, or model
layers were tested. Independent review remains pending; this builder run must not
be treated as deployment approval even if the mechanical verdict were GO.
"""
    (REPORTS / "FINDINGS.md").write_text(findings, encoding="utf-8")
    (ARTIFACT / "FINDINGS.md").write_text(findings, encoding="utf-8")


def main() -> None:
    cfg = read_config()
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    bars_by_pair = {}
    dq_overall, dq_detail, path_exclusions = [], [], {}
    candidates = []
    for pair in cfg["pairs"]:
        print(f"[{pair}] loading, resampling, and building features", flush=True)
        bars, overall, detail = load_and_build(pair, cfg)
        bars_by_pair[pair] = bars
        dq_overall.extend(overall)
        dq_detail.extend(detail)
        cand = candidate_frame(pair, bars, cfg)
        sim, excluded = simulate_candidate_batches(cand, bars, cfg)
        path_exclusions[pair] = excluded + int((~cand.has_boundary).sum())
        if sim.empty:
            raise RuntimeError(f"No feasible candidates for {pair}")
        unvetoed = stateful_select(sim, pd.Series(True, index=sim.index))
        vetoed = stateful_select(sim, ~sim.news_veto)
        sim["selected_unvetoed"] = unvetoed
        sim["selected_headline"] = vetoed
        candidates.append(sim)
        print(f"[{pair}] {len(sim):,} feasible crossings; {vetoed.sum():,} headline trades", flush=True)

    overall_df = pd.DataFrame(dq_overall)
    detail_df = pd.DataFrame(dq_detail).sort_values(["pair", "era", "utc_hour"])
    write_dq(overall_df, detail_df, path_exclusions)
    print("Rule 9a report written; proceeding to result interpretation", flush=True)

    all_candidates = pd.concat(candidates, ignore_index=True)
    all_candidates.to_parquet(ARTIFACT / "candidate_events.parquet", index=False)
    trades = all_candidates.loc[all_candidates.selected_headline].copy().reset_index(drop=True)
    trades = add_costs(trades)
    trades = add_diagnostics(trades, bars_by_pair, cfg)
    null_draws, null_result = random_exit_null(trades, bars_by_pair, cfg)
    metrics = metric_rows(trades)
    costs = cost_table(trades)
    daily = daily_marked(trades, bars_by_pair)
    sharpes = sharpe_rows(daily)

    blackout_rows = []
    for pair, g in all_candidates.groupby("pair"):
        blackout_rows.append({"pair": pair, "feasible_crossings": len(g),
                              "near_news_crossings": int(g.news_veto.sum()),
                              "unvetoed_book_trades": int(g.selected_unvetoed.sum()),
                              "headline_book_trades": int(g.selected_headline.sum()),
                              "book_trade_delta": int(g.selected_unvetoed.sum() - g.selected_headline.sum())})
    blackout = pd.DataFrame(blackout_rows)
    verdict = kill_test(trades, metrics, null_result, cfg)

    trades.to_parquet(ARTIFACT / "trades.parquet", index=False)
    metrics.to_csv(ARTIFACT / "metrics.csv", index=False)
    costs.to_csv(ARTIFACT / "cost_by_era_hour.csv", index=False)
    daily.to_csv(ARTIFACT / "daily_marked_R.csv", index=False)
    sharpes.to_csv(ARTIFACT / "sharpes.csv", index=False)
    blackout.to_csv(ARTIFACT / "blackout_summary.csv", index=False)
    null_draws.to_csv(ARTIFACT / "random_exit_draws.csv", index=False)
    (ARTIFACT / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    (ARTIFACT / "run_config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    write_findings(trades, metrics, costs, sharpes, blackout, null_result, verdict, cfg)
    print(json.dumps({"trades": len(trades), "verdict": verdict["verdict"],
                      "base_net_mean_R": verdict["base_net_mean_R"],
                      "base_net_ci": verdict["base_net_ci"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
