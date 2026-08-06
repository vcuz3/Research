"""Canonical RV-level RSI regimes by scheduled and first-crossing clocks."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm

from _run_rsi_broad_regime_sweep import (
    DATA,
    HOLDOUT,
    PAIRS,
    ROOT,
    SESSIONS_PER_YEAR,
    causal_slot_percentile,
    exact_roll,
    session_cluster_t,
    wilder_rsi,
)


warnings.filterwarnings("ignore", category=FutureWarning)
OUT = ROOT / "rsi_rv_clock_regime_results.json"
METRICS_CSV = ROOT / "rsi_rv_clock_regime_metrics.csv"
SUMMARY_CSV = ROOT / "rsi_rv_clock_regime_summary.csv"
REGRESSION_CSV = ROOT / "rsi_rv_clock_regime_phase_regressions.csv"
IC_CSV = ROOT / "rsi_rv_clock_regime_scheduled_ic.csv"
CHART_DIR = ROOT / "charts" / "rsi_rv_clock_regime"
START = pd.Timestamp("2012-01-01", tz="UTC")
ERA_SPLIT = pd.Timestamp("2021-01-01", tz="UTC")
PIP = 0.0001
COOLDOWN_MIN = 30
FEATURES = ["rv_5m_pct_90d", "rv_30m_pct_90d"]
CLOCKS = ["scheduled_state", "first_crossing_all", "first_crossing_phase29", "scheduled_fresh"]
DELAYS = [0, 1]


def cooldown_positions(positions, times, minutes=COOLDOWN_MIN):
    accepted, last = [], None
    tol = pd.Timedelta(minutes=minutes)
    for pos in positions:
        now = times.iloc[pos]
        if last is None or now - last >= tol:
            accepted.append(pos)
            last = now
    return np.asarray(accepted, dtype=int)


def endpoint(open_, time, delay):
    start = 1 + delay
    end = start + 30
    entry = open_.shift(-start)
    exit_ = open_.shift(-end)
    exact = time.shift(-start).eq(time + pd.Timedelta(minutes=start)) & time.shift(-end).eq(
        time + pd.Timedelta(minutes=end)
    )
    return ((exit_ - entry) / PIP).where(exact)


def fixed_bins(values, cuts):
    values = np.asarray(values, float)
    out = np.full(len(values), np.nan)
    valid = np.isfinite(values)
    out[valid] = np.digitize(values[valid], cuts, right=True) + 1
    return out


def metrics(frame, all_sessions, pnl_col):
    z = frame.loc[frame[pnl_col].notna()].copy()
    if z.empty:
        return {"signals": 0}
    pnl = z[pnl_col]
    daily = pnl.groupby(z.sdate).sum().reindex(all_sessions, fill_value=0.0)
    daily_net = (pnl - 0.5).groupby(z.sdate).sum().reindex(all_sessions, fill_value=0.0)
    sd, nsd = daily.std(ddof=1), daily_net.std(ddof=1)
    cumulative = daily.cumsum()
    return {
        "signals": len(z),
        "signals_per_year": len(z) / max(len(all_sessions) / SESSIONS_PER_YEAR, 1 / SESSIONS_PER_YEAR),
        "mean_gross_pips": pnl.mean(),
        "mean_net_05_pips": pnl.mean() - 0.5,
        "cluster_t": session_cluster_t(pnl, z.sdate),
        "hit_rate": pnl.gt(0).mean(),
        "session_sharpe": np.sqrt(SESSIONS_PER_YEAR) * daily.mean() / sd if sd > 0 else np.nan,
        "net_05_session_sharpe": np.sqrt(SESSIONS_PER_YEAR) * daily_net.mean() / nsd if nsd > 0 else np.nan,
        "max_drawdown_pips": (cumulative - cumulative.cummax()).min(),
        "p05_pips": pnl.quantile(0.05),
        "p50_pips": pnl.median(),
        "p95_pips": pnl.quantile(0.95),
    }


def within_slot_ic(frame, target):
    z = frame[["session_minute", "rsi", target]].dropna().copy()
    if len(z) < 200:
        return np.nan
    r = z.groupby("session_minute").rsi.rank(pct=True)
    y = z.groupby("session_minute")[target].rank(pct=True)
    return r.corr(y)


def phase_regression(frame, feature, pnl_col):
    z = frame[["sdate", "year", "phase", feature, pnl_col]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(z) < 500 or z.sdate.nunique() < 30:
        return {"n": len(z)}
    z["regime"] = z[feature] - 0.5
    phase = pd.get_dummies(z.phase.astype(int), prefix="phase", drop_first=True, dtype=float)
    years = pd.get_dummies(z.year.astype(int), prefix="year", drop_first=True, dtype=float)
    X = pd.concat([pd.DataFrame({"const": 1.0, "regime": z.regime}, index=z.index), phase, years], axis=1)
    fit = sm.OLS(z[pnl_col].to_numpy(), X).fit(cov_type="cluster", cov_kwds={"groups": z.sdate})
    return {"n": int(fit.nobs), "sessions": int(z.sdate.nunique()),
            "regime_beta_pips": fit.params.regime, "regime_t": fit.tvalues.regime,
            "regime_p": fit.pvalues.regime, "r2": fit.rsquared}


def build_pair(pair):
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "open", "close"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    assert raw.time.max() < HOLDOUT
    dt = raw.time.diff()
    one = dt.eq(pd.Timedelta(minutes=1)).to_numpy()
    logc = pd.Series(np.log(raw.close.astype(float)), index=raw.index)
    ret1 = logc.diff().where(one)
    rsi = wilder_rsi(raw.close.to_numpy(float), one, 14)
    rv5 = np.sqrt(exact_roll(ret1.pow(2), raw.time, 5, "sum"))
    rv30 = np.sqrt(exact_roll(ret1.pow(2), raw.time, 30, "sum"))

    ny = raw.time.dt.tz_convert("America/New_York")
    ny_min = ny.dt.hour * 60 + ny.dt.minute
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    sdate = ny_date + pd.to_timedelta((ny_min >= 17 * 60).astype(int), unit="D")
    session_minute = ((ny_min - 17 * 60) % 1440).astype("int16")
    panel = pd.DataFrame({"time": raw.time, "sdate": sdate, "session_minute": session_minute,
                          "phase": ny_min.mod(30).astype("int8"), "rsi": rsi,
                          "rv_5m_raw": rv5, "rv_30m_raw": rv30})
    panel["year"] = panel.time.dt.year
    panel["era"] = np.where(panel.time < ERA_SPLIT, "early_exploration", "late_exploration")
    panel["side"] = np.select([panel.rsi <= 30, panel.rsi >= 70], [1.0, -1.0], default=0.0)
    side = panel.side.to_numpy()
    new_run = np.r_[True, side[1:] != side[:-1]] | (~one)
    start_idx = np.maximum.accumulate(np.where(new_run, np.arange(len(side)), 0))
    panel["tau"] = np.arange(len(side)) - start_idx
    panel["one_minute"] = one
    for delay in DELAYS:
        panel[f"pnl_d{delay}"] = panel.side * endpoint(raw.open.astype(float), raw.time, delay)
        panel[f"target_d{delay}"] = endpoint(raw.open.astype(float), raw.time, delay)

    extreme = side != 0
    scheduled = extreme & panel.phase.eq(29).to_numpy()
    crossed = extreme & panel.tau.eq(0).to_numpy() & one
    accepted = cooldown_positions(np.flatnonzero(crossed), panel.time)
    crossing = np.zeros(len(panel), dtype=bool); crossing[accepted] = True
    masks = {
        "scheduled_state": scheduled,
        "first_crossing_all": crossing,
        "first_crossing_phase29": crossing & panel.phase.eq(29).to_numpy(),
        "scheduled_fresh": scheduled & panel.tau.eq(0).to_numpy(),
    }
    panel = panel.loc[panel.time.ge(START)].reset_index(drop=True)
    # Masks were built before the start filter; align through timestamps.
    mask_frame = pd.DataFrame({"time": raw.time, **masks})
    panel = panel.merge(mask_frame, on="time", how="left", validate="one_to_one")
    # Match the broad sweep exactly: the normalization history begins at START,
    # even when the clean source contains earlier rows used only to warm RSI/RV.
    print(f"  ranking minute-level RV features for {pair} ...", flush=True)
    panel["rv_5m_pct_90d"] = causal_slot_percentile(panel, "rv_5m_raw", 90)
    panel["rv_30m_pct_90d"] = causal_slot_percentile(panel, "rv_30m_raw", 90)
    quality = {"pair": pair, "raw_rows": len(raw), "first": raw.time.min(), "last": raw.time.max(),
               "duplicates": int(raw.time.duplicated().sum()), "out_of_order": int((dt.dropna() <= pd.Timedelta(0)).sum()),
               "gaps_gt_1m": int(dt.gt(pd.Timedelta(minutes=1)).sum()),
               **{f"{clock}_signals": int(panel[clock].sum()) for clock in CLOCKS},
               **{f"{feature}_coverage": panel[feature].notna().mean() for feature in FEATURES}}
    return panel, quality


def analyze(panel, pair):
    metric_rows, summary_rows, regression_rows, ic_rows, cut_rows = [], [], [], [], []
    # Match the broad sweep: cutpoints use every early scheduled decision,
    # independent of whether RSI is extreme.
    early_scheduled = panel.era.eq("early_exploration") & panel.phase.eq(29)
    for feature in FEATURES:
        cuts = panel.loc[early_scheduled, feature].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
        panel[f"{feature}_bin"] = fixed_bins(panel[feature], cuts)
        cut_rows.append({"pair": pair, "feature": feature, "cuts": cuts.tolist()})
        for era, era_group in panel.groupby("era"):
            sessions = pd.Index(sorted(era_group.sdate.unique()))
            scheduled_all = era_group.loc[era_group.phase.eq(29)]
            for delay in DELAYS:
                target = f"target_d{delay}"
                for q in range(1, 6):
                    z = scheduled_all.loc[scheduled_all[f"{feature}_bin"].eq(q)]
                    ic_rows.append({"pair": pair, "era": era, "feature": feature, "delay": delay,
                                    "quintile": q, "n": len(z), "within_slot_ic": within_slot_ic(z, target)})
                for clock in CLOCKS:
                    events = era_group.loc[era_group[clock]]
                    for q in range(1, 6):
                        z = events.loc[events[f"{feature}_bin"].eq(q)]
                        metric_rows.append({"pair": pair, "era": era, "clock": clock, "feature": feature,
                                            "delay": delay, "quintile": q,
                                            **metrics(z, sessions, f"pnl_d{delay}")})
                    if clock == "first_crossing_all":
                        regression_rows.append({"pair": pair, "era": era, "feature": feature, "delay": delay}
                                               | phase_regression(events, feature, f"pnl_d{delay}"))
    metric = pd.DataFrame(metric_rows)
    for keys, group in metric.groupby(["pair", "era", "clock", "feature", "delay"]):
        q1 = group.loc[group.quintile.eq(1)].iloc[0]; q5 = group.loc[group.quintile.eq(5)].iloc[0]
        summary_rows.append(dict(zip(["pair", "era", "clock", "feature", "delay"], keys)) | {
            "q1_signals": q1.signals, "q5_signals": q5.signals,
            "q1_gross_pips": q1.mean_gross_pips, "q5_gross_pips": q5.mean_gross_pips,
            "q5_minus_q1_gross_pips": q5.mean_gross_pips - q1.mean_gross_pips,
            "q1_hit_rate": q1.hit_rate, "q5_hit_rate": q5.hit_rate,
            "q1_session_sharpe": q1.session_sharpe, "q5_session_sharpe": q5.session_sharpe,
            "q5_net_05_pips": q5.mean_net_05_pips, "q5_net_05_sharpe": q5.net_05_session_sharpe,
        })
    return metric_rows, summary_rows, regression_rows, ic_rows, cut_rows


def create_charts(metrics, summary):
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    z = metrics.loc[metrics.clock.isin(["scheduled_state", "first_crossing_all"])].copy()
    agg = z.groupby(["feature", "clock", "delay", "quintile"], as_index=False).mean_gross_pips.median()
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    for row, feature in enumerate(FEATURES):
        for col, delay in enumerate(DELAYS):
            ax = axes[row, col]
            for clock, g in agg.loc[agg.feature.eq(feature) & agg.delay.eq(delay)].groupby("clock"):
                ax.plot(g.quintile, g.mean_gross_pips, marker="o", label=clock.replace("_", " "))
            ax.axhline(0, color="0.2", lw=1)
            ax.set_title(f"{feature.replace('_pct_90d','')} — delay {delay}m")
            ax.set_xlabel("RV regime quintile")
            ax.set_ylabel("Median gross pips/signal")
            ax.set_xticks(range(1, 6))
    axes[0, 0].legend()
    fig.tight_layout()
    fig.savefig(CHART_DIR / "scheduled_vs_crossing_regime_curves.png", dpi=180)
    plt.close(fig)

    s = summary.loc[summary.clock.isin(["scheduled_state", "first_crossing_all"])]
    agg = s.groupby(["feature", "clock", "delay"], as_index=False).agg(
        uplift=("q5_minus_q1_gross_pips", "median"), positive=("q5_minus_q1_gross_pips", lambda x: int((x > 0).sum()))
    )
    agg["label"] = agg.clock.str.replace("_", " ") + " | d" + agg.delay.astype(str)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, feature in zip(axes, FEATURES):
        g = agg.loc[agg.feature.eq(feature)]
        bars = ax.barh(g.label, g.uplift)
        ax.axvline(0, color="0.2", lw=1)
        ax.set_title(feature.replace("_pct_90d", ""))
        ax.set_xlabel("Median Q5-Q1 gross pips/signal")
        for bar, votes in zip(bars, g.positive):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2, f" {votes}/8", va="center")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "regime_uplift_and_stability.png", dpi=180)
    plt.close(fig)

    q5 = metrics.loc[
        metrics.quintile.eq(5)
        & metrics.clock.isin(["scheduled_state", "first_crossing_phase29", "scheduled_fresh"])
    ].copy()
    q5 = q5.groupby(["feature", "clock", "delay"], as_index=False).mean_gross_pips.median()
    q5["clock"] = pd.Categorical(
        q5.clock,
        ["scheduled_state", "first_crossing_phase29", "scheduled_fresh"],
        ordered=True,
    )
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, feature in zip(axes, FEATURES):
        g = q5.loc[q5.feature.eq(feature)].sort_values(["delay", "clock"])
        labels = [f"{str(c).replace('_', ' ')} | d{d}" for c, d in zip(g.clock, g.delay)]
        ax.barh(labels, g.mean_gross_pips)
        ax.axvline(0.5, color="0.25", lw=1, linestyle="--", label="0.5-pip cost")
        ax.set_title(feature.replace("_pct_90d", ""))
        ax.set_xlabel("Median Q5 gross pips/signal")
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(CHART_DIR / "phase_matched_q5_and_delay.png", dpi=180)
    plt.close(fig)


def main():
    all_metrics, all_summaries, all_regressions, all_ic, all_cuts, quality = [], [], [], [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        panel, q = build_pair(pair); quality.append(q)
        result = analyze(panel, pair)
        for destination, values in zip([all_metrics, all_summaries, all_regressions, all_ic, all_cuts], result):
            destination.extend(values)
        print(f"  scheduled={q['scheduled_state_signals']:,}; crossings={q['first_crossing_all_signals']:,}", flush=True)
    metric = pd.DataFrame(all_metrics); summary = pd.DataFrame(all_summaries)
    regressions = pd.DataFrame(all_regressions); ic = pd.DataFrame(all_ic)
    create_charts(metric, summary)
    payload = {"metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "pairs": PAIRS,
                            "start": START.isoformat(), "era_split": ERA_SPLIT.isoformat(),
                            "holdout_start": HOLDOUT.isoformat(), "timezone": "America/New_York",
                            "features": FEATURES, "clocks": CLOCKS, "delays": DELAYS},
               "quality": json.loads(pd.DataFrame(quality).to_json(orient="records", date_format="iso")),
               "cutpoints": all_cuts,
               "metrics": json.loads(metric.to_json(orient="records")),
               "summaries": json.loads(summary.to_json(orient="records")),
               "phase_regressions": json.loads(regressions.to_json(orient="records")),
               "scheduled_ic": json.loads(ic.to_json(orient="records")),
               "charts": [str(p.relative_to(ROOT)) for p in sorted(CHART_DIR.glob("*.png"))]}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    metric.to_csv(METRICS_CSV, index=False); summary.to_csv(SUMMARY_CSV, index=False)
    regressions.to_csv(REGRESSION_CSV, index=False); ic.to_csv(IC_CSV, index=False)
    print("\nStability summary:")
    print(summary.groupby(["feature", "clock", "delay"]).q5_minus_q1_gross_pips.agg(
        median="median", positive=lambda x: int((x > 0).sum())).round(4).to_string())
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
