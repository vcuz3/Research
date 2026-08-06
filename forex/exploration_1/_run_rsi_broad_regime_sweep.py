"""Run the frozen broad RSI regime sweep and create result tables/charts."""

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
from scipy.signal import lfilter
from scipy.stats import spearmanr


warnings.filterwarnings("ignore", category=FutureWarning)
ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data" / "clean"
OUT = ROOT / "rsi_broad_regime_sweep_results.json"
CHART_DIR = ROOT / "charts" / "rsi_broad_regime_sweep"
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
START = pd.Timestamp("2012-01-01", tz="UTC")
ERA_SPLIT = pd.Timestamp("2021-01-01", tz="UTC")
HOLDOUT = pd.Timestamp("2024-01-01", tz="UTC")
HORIZON = 30
PIP = 0.0001
MIN_BIN_N = 200
HYPOTHETICAL_COST_PIPS = 0.5
SESSIONS_PER_YEAR = 252


def sma_seeded_recursive(values, starts, ends, length, alpha):
    out = np.full(len(values), np.nan, float)
    for start, end in zip(starts, ends):
        x = values[start:end]
        if len(x) < length:
            continue
        seed = float(np.mean(x[:length]))
        k = start + length - 1
        out[k] = seed
        if len(x) > length:
            filtered, _ = lfilter([alpha], [1.0, -(1.0 - alpha)], x[length:], zi=[(1.0 - alpha) * seed])
            out[k + 1 : end] = filtered
    return out


def recursive_wilder(values, one_minute, length):
    starts = np.flatnonzero(~one_minute)
    ends = np.r_[starts[1:], len(values)]
    return sma_seeded_recursive(np.asarray(values, float), starts, ends, length, 1.0 / length)


def wilder_rsi(close, one_minute, length=14):
    starts = np.flatnonzero(~one_minute)
    ends = np.r_[starts[1:], len(close)]
    delta = np.diff(close, prepend=close[0])
    delta[starts] = 0
    gain = sma_seeded_recursive(np.clip(delta, 0, None), starts, ends, length, 1.0 / length)
    loss = sma_seeded_recursive(np.clip(-delta, 0, None), starts, ends, length, 1.0 / length)
    rs = np.divide(gain, loss, out=np.full_like(gain, np.nan), where=loss > 0)
    rsi = 100 - 100 / (1 + rs)
    rsi[(loss == 0) & (gain == 0)] = 50
    rsi[(loss == 0) & (gain > 0)] = 100
    return rsi


def exact_lag(series, time, minutes):
    return series.shift(minutes).where(time.shift(minutes).eq(time - pd.Timedelta(minutes=minutes)))


def exact_roll(series, time, window, operation="sum"):
    rolled = getattr(series.rolling(window, min_periods=window), operation)()
    return rolled.where(time.shift(window).eq(time - pd.Timedelta(minutes=window)))


def causal_slot_percentile(frame, column, lookback):
    min_obs = int(np.ceil(lookback * 2 / 3))

    def transform(series):
        rolling = series.rolling(lookback + 1, min_periods=min_obs + 1)
        rank = rolling.rank(method="average")
        count = rolling.count()
        return (rank - 1) / (count - 1)

    return frame.groupby("session_minute", sort=False)[column].transform(transform)


def causal_slot_z(frame, column, lookback):
    min_obs = int(np.ceil(lookback * 2 / 3))
    grouped = frame.groupby("session_minute", sort=False)[column]
    mean = grouped.transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).mean())
    std = grouped.transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).std(ddof=1))
    return (frame[column] - mean) / std.replace(0, np.nan)


def prior_slot_median(frame, column, lookback):
    min_obs = int(np.ceil(lookback * 2 / 3))
    return frame.groupby("session_minute", sort=False)[column].transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).median()
    )


def within_slot_ic(frame):
    z = frame[["session_minute", "rsi_14", "signed_return_bp"]].dropna().copy()
    if len(z) < MIN_BIN_N:
        return np.nan
    z["rsi_rank"] = z.groupby("session_minute").rsi_14.rank(pct=True)
    z["return_rank"] = z.groupby("session_minute").signed_return_bp.rank(pct=True)
    return z.rsi_rank.corr(z.return_rank)


def session_cluster_t(values, sessions):
    z = pd.DataFrame({"value": values, "session": sessions}).dropna()
    n = len(z)
    groups = z.session.nunique()
    if n < 2 or groups < 2:
        return np.nan
    mean = z.value.mean()
    scores = (z.value - mean).groupby(z.session).sum()
    se = np.sqrt((groups / (groups - 1)) * np.square(scores).sum()) / n
    return mean / se if se > 0 else np.nan


def bh_adjust(values):
    p = np.asarray(values, float)
    out = np.full(len(p), np.nan)
    valid = np.isfinite(p)
    if not valid.any():
        return out
    x = p[valid]
    order = np.argsort(x)
    ranked = x[order]
    q = ranked * len(x) / np.arange(1, len(x) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1].clip(0, 1)
    restored = np.empty(len(x))
    restored[order] = q
    out[valid] = restored
    return out


def interaction_fit(frame, regime):
    cols = ["sdate", "session_minute", "year", "rsi_14", "signed_return_bp", regime]
    z = frame[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(z) < 1000 or z.sdate.nunique() < 30:
        return {"n": len(z)}
    z["rsi_rank"] = z.groupby("session_minute").rsi_14.rank(pct=True) - 0.5
    z["return_rank"] = z.groupby("session_minute").signed_return_bp.rank(pct=True) - 0.5
    z["regime_rank"] = z.groupby("session_minute")[regime].rank(pct=True) - 0.5
    z["interaction"] = z.rsi_rank * z.regime_rank
    years = pd.get_dummies(z.year.astype(int), prefix="year", drop_first=True, dtype=float)
    X = pd.concat(
        [
            pd.DataFrame(
                {
                    "const": 1.0,
                    "rsi_rank": z.rsi_rank,
                    "regime_rank": z.regime_rank,
                    "interaction": z.interaction,
                },
                index=z.index,
            ),
            years,
        ],
        axis=1,
    )
    fit = sm.OLS(z.return_rank.to_numpy(), X).fit(cov_type="cluster", cov_kwds={"groups": z.sdate})
    return {
        "n": int(fit.nobs),
        "sessions": int(z.sdate.nunique()),
        "interaction_beta": fit.params["interaction"],
        "interaction_t": fit.tvalues["interaction"],
        "interaction_p": fit.pvalues["interaction"],
        "r2": fit.rsquared,
    }


def pnl_metrics(frame, all_sessions):
    signals = frame.loc[(frame.rsi_14 <= 30) | (frame.rsi_14 >= 70)].copy()
    if signals.empty:
        return {"signals": 0}
    signals["side"] = np.where(signals.rsi_14 <= 30, 1.0, -1.0)
    signals["gross_pips"] = signals.side * signals.terminal_return_pips
    signals["net_05_pips"] = signals.gross_pips - HYPOTHETICAL_COST_PIPS
    signals["mfe_side_pips"] = np.where(signals.side > 0, signals.long_mfe_pips, signals.long_mae_pips)
    signals["mae_side_pips"] = np.where(signals.side > 0, signals.long_mae_pips, signals.long_mfe_pips)
    daily = signals.groupby("sdate").gross_pips.sum().reindex(all_sessions, fill_value=0.0)
    daily_net = signals.groupby("sdate").net_05_pips.sum().reindex(all_sessions, fill_value=0.0)
    sharpe = np.sqrt(SESSIONS_PER_YEAR) * daily.mean() / daily.std(ddof=1) if daily.std(ddof=1) > 0 else np.nan
    net_sharpe = np.sqrt(SESSIONS_PER_YEAR) * daily_net.mean() / daily_net.std(ddof=1) if daily_net.std(ddof=1) > 0 else np.nan
    cumulative = daily.cumsum()
    drawdown = cumulative - cumulative.cummax()
    years = max(len(all_sessions) / SESSIONS_PER_YEAR, 1 / SESSIONS_PER_YEAR)
    mfe = signals.mfe_side_pips.mean()
    mae = signals.mae_side_pips.mean()
    return {
        "signals": len(signals),
        "signals_per_year": len(signals) / years,
        "mean_gross_pips": signals.gross_pips.mean(),
        "cluster_t": session_cluster_t(signals.gross_pips, signals.sdate),
        "hit_rate": signals.gross_pips.gt(0).mean(),
        "p05_pips": signals.gross_pips.quantile(0.05),
        "p50_pips": signals.gross_pips.median(),
        "p95_pips": signals.gross_pips.quantile(0.95),
        "session_sharpe": sharpe,
        "max_drawdown_pips": drawdown.min(),
        "mean_net_05_pips": signals.net_05_pips.mean(),
        "net_05_session_sharpe": net_sharpe,
        "mean_mfe_pips": mfe,
        "mean_mae_pips": mae,
        "mfe_mae_ratio": mfe / mae if mae > 0 else np.nan,
        "long_share": signals.side.gt(0).mean(),
    }


def build_pair(pair):
    path = DATA / f"{pair}_1m_clean.parquet"
    raw = pd.read_parquet(
        path,
        columns=["ts_utc", "open", "high", "low", "close"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    assert raw.time.max() < HOLDOUT
    dt = raw.time.diff()
    one = dt.eq(pd.Timedelta(minutes=1)).to_numpy()
    close = raw.close.to_numpy(float)
    logc = pd.Series(np.log(close), index=raw.index)
    ret1 = logc.diff().where(one)
    absret = ret1.abs()

    ny = raw.time.dt.tz_convert("America/New_York")
    ny_min = ny.dt.hour * 60 + ny.dt.minute
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    raw["sdate"] = ny_date + pd.to_timedelta((ny_min >= 17 * 60).astype(int), unit="D")
    raw["session_minute"] = ((ny_min - 17 * 60) % 1440).astype("int16")
    raw["ny_hour"] = ny.dt.hour.astype("int8")

    prev_close = np.r_[np.nan, close[:-1]]
    tr = np.maximum.reduce(
        [
            raw.high.to_numpy(float) - raw.low.to_numpy(float),
            np.abs(raw.high.to_numpy(float) - prev_close),
            np.abs(raw.low.to_numpy(float) - prev_close),
        ]
    )
    tr[~one] = (raw.high - raw.low).to_numpy(float)[~one]
    atr = {length: recursive_wilder(tr, one, length) for length in [5, 10, 25, 50, 100]}
    rsi = wilder_rsi(close, one, 14)

    rv = {}
    rv2 = {}
    for window in [5, 10, 15, 25, 30, 50, 60, 100, 240]:
        rv2[window] = exact_roll(ret1.pow(2), raw.time, window, "sum")
        rv[window] = np.sqrt(rv2[window])

    trend = {}
    for window in [15, 60, 240]:
        endpoint = logc - exact_lag(logc, raw.time, window)
        travelled = exact_roll(absret, raw.time, window, "sum")
        trend[f"efficiency_{window}m_raw"] = endpoint.abs() / travelled.replace(0, np.nan)
        trend[f"variance_ratio_{window}m_raw"] = endpoint.pow(2) / rv2[window].replace(0, np.nan)
        corr = ret1.rolling(window, min_periods=window).corr(ret1.shift(1))
        trend[f"autocorr_{window}m_raw"] = corr.where(raw.time.shift(window).eq(raw.time - pd.Timedelta(minutes=window)))

    entry = raw.open.shift(-1).astype(float)
    exit_ = raw.open.shift(-(HORIZON + 1)).astype(float)
    exact_target = raw.time.shift(-1).eq(raw.time + pd.Timedelta(minutes=1)) & raw.time.shift(-(HORIZON + 1)).eq(
        raw.time + pd.Timedelta(minutes=HORIZON + 1)
    )
    target_bp = (1e4 * np.log(exit_ / entry)).where(exact_target)
    target_pips = ((exit_ - entry) / PIP).where(exact_target)
    open_ret = np.log(raw.open.astype(float)).diff().where(one)
    forward_rv = (1e4 * np.sqrt(open_ret.pow(2).rolling(HORIZON, min_periods=HORIZON).sum().shift(-(HORIZON + 1)))).where(
        exact_target
    )
    high = raw.high.astype(float).shift(-1).iloc[::-1].rolling(HORIZON, min_periods=HORIZON).max().iloc[::-1]
    low = raw.low.astype(float).shift(-1).iloc[::-1].rolling(HORIZON, min_periods=HORIZON).min().iloc[::-1]
    high = pd.concat([high, entry, exit_], axis=1).max(axis=1).where(exact_target)
    low = pd.concat([low, entry, exit_], axis=1).min(axis=1).where(exact_target)

    decision = ny_min.mod(30).eq(29).to_numpy()
    pos = np.flatnonzero(decision & raw.time.ge(START).to_numpy() & raw.time.lt(HOLDOUT).to_numpy())
    take = lambda x: pd.Series(x, index=raw.index).iloc[pos].to_numpy()
    d = pd.DataFrame(
        {
            "pair": pair,
            "ts_utc": raw.time.iloc[pos].to_numpy(),
            "sdate": raw.sdate.iloc[pos].to_numpy(),
            "session_minute": raw.session_minute.iloc[pos].to_numpy(),
            "ny_hour": raw.ny_hour.iloc[pos].to_numpy(),
            "rsi_14": rsi[pos],
            "signed_return_bp": target_bp.iloc[pos].to_numpy(),
            "terminal_return_pips": target_pips.iloc[pos].to_numpy(),
            "forward_rv_30m_bp": forward_rv.iloc[pos].to_numpy(),
            "long_mfe_pips": ((high - entry) / PIP).iloc[pos].to_numpy(),
            "long_mae_pips": ((entry - low) / PIP).iloc[pos].to_numpy(),
        }
    )
    d["year"] = pd.to_datetime(d.ts_utc, utc=True).dt.year
    d["era"] = np.where(pd.to_datetime(d.ts_utc, utc=True) < ERA_SPLIT, "early_exploration", "late_exploration")
    d["vei_25_100_raw"] = atr[25][pos] / atr[100][pos]
    d["vei_10_50_raw"] = atr[10][pos] / atr[50][pos]
    d["vei_5_25_raw"] = atr[5][pos] / atr[25][pos]
    d["rv_ratio_5_30_raw"] = take(rv[5] / pd.Series(rv[30]).replace(0, np.nan))
    d["rv_ratio_10_50_raw"] = take(rv[10] / pd.Series(rv[50]).replace(0, np.nan))
    d["rv_ratio_25_100_raw"] = take(rv[25] / pd.Series(rv[100]).replace(0, np.nan))
    d["rv_30m_raw"] = take(rv[30])
    for name, values in trend.items():
        d[name] = take(values)
    d = d.sort_values("ts_utc").reset_index(drop=True)

    metadata = []
    for base in ["vei_25_100", "vei_10_50", "vei_5_25", "rv_ratio_5_30", "rv_ratio_10_50", "rv_ratio_25_100"]:
        family = "VEI acceleration" if base.startswith("vei") else "RV-ratio acceleration"
        for lookback in [30, 90]:
            name = f"{base}_pct_{lookback}d"
            d[name] = causal_slot_percentile(d, f"{base}_raw", lookback)
            metadata.append({"regime": name, "family": family, "base": base, "transform": "percentile", "memory_days": lookback})
    for lookback in [30, 90]:
        pct_name = f"rv_30m_pct_{lookback}d"
        z_name = f"rv_30m_z_{lookback}d"
        med_name = f"slot_fwd_rv_median_{lookback}d"
        d[pct_name] = causal_slot_percentile(d, "rv_30m_raw", lookback)
        d[z_name] = causal_slot_z(d, "rv_30m_raw", lookback)
        d[med_name] = prior_slot_median(d, "forward_rv_30m_bp", lookback)
        metadata.extend(
            [
                {"regime": pct_name, "family": "RV level ranking", "base": "rv_30m", "transform": "percentile", "memory_days": lookback},
                {"regime": z_name, "family": "RV level ranking", "base": "rv_30m", "transform": "z_score", "memory_days": lookback},
                {"regime": med_name, "family": "Slot forward-RV forecast", "base": "slot_fwd_rv_median", "transform": "median", "memory_days": lookback},
            ]
        )
    for measure in ["efficiency", "variance_ratio", "autocorr"]:
        for window in [15, 60, 240]:
            raw_name = f"{measure}_{window}m_raw"
            name = f"trend_{measure}_{window}m_pct_90d"
            d[name] = causal_slot_percentile(d, raw_name, 90)
            metadata.append(
                {
                    "regime": name,
                    "family": "Trend vs chop",
                    "base": measure,
                    "transform": "percentile",
                    "memory_days": 90,
                    "timeframe_min": window,
                }
            )

    quality = {
        "pair": pair,
        "rows": len(raw),
        "first": raw.time.min(),
        "last": raw.time.max(),
        "duplicates": int(raw.time.duplicated().sum()),
        "out_of_order": int((dt.dropna() <= pd.Timedelta(0)).sum()),
        "gaps_gt_1m": int(dt.gt(pd.Timedelta(minutes=1)).sum()),
        "decision_rows": len(d),
        "target_coverage": d.signed_return_bp.notna().mean(),
        "signal_rows": int(((d.rsi_14 <= 30) | (d.rsi_14 >= 70)).sum()),
    }
    return d, metadata, quality


def analyze_pair(panel, metadata):
    pair = panel.pair.iloc[0]
    metric_rows = []
    interaction_rows = []
    cutpoint_rows = []
    hourly_rows = []
    canonical = "vei_10_50_pct_90d"
    for item in metadata:
        regime = item["regime"]
        early = panel.loc[panel.era.eq("early_exploration"), regime].replace([np.inf, -np.inf], np.nan).dropna()
        cuts = np.unique(early.quantile([0.2, 0.4, 0.6, 0.8]).to_numpy())
        if len(cuts) != 4:
            continue
        cutpoint_rows.append({"pair": pair, "regime": regime, **{f"cut_{i+1}": value for i, value in enumerate(cuts)}})
        for era, group in panel.groupby("era"):
            values = group[regime].to_numpy(float)
            bins = np.digitize(values, cuts, right=True) + 1
            all_sessions = pd.Index(sorted(group.sdate.unique()))
            for bin_index in range(1, 6):
                z = group.loc[np.isfinite(values) & (bins == bin_index)]
                row = {
                    "pair": pair,
                    "era": era,
                    "regime": regime,
                    "bin": bin_index,
                    "n": len(z),
                    "pooled_ic": z.rsi_14.corr(z.signed_return_bp, method="spearman") if len(z) >= MIN_BIN_N else np.nan,
                    "within_slot_ic": within_slot_ic(z),
                }
                row.update(pnl_metrics(z, all_sessions))
                metric_rows.append(row)
            interaction_rows.append({"pair": pair, "era": era, "regime": regime} | interaction_fit(group, regime))

    canonical_cuts = next(r for r in cutpoint_rows if r["regime"] == canonical)
    cuts = np.array([canonical_cuts[f"cut_{i}"] for i in range(1, 5)])
    panel = panel.copy()
    panel["canonical_bin"] = np.digitize(panel[canonical].to_numpy(float), cuts, right=True) + 1
    for era, group in panel.groupby("era"):
        for hour, hour_group in group.groupby("ny_hour"):
            for label, z in [
                ("all", hour_group),
                ("vei_q1", hour_group.loc[hour_group.canonical_bin.eq(1)]),
                ("vei_q5", hour_group.loc[hour_group.canonical_bin.eq(5)]),
            ]:
                hourly_rows.append(
                    {
                        "pair": pair,
                        "era": era,
                        "ny_hour": int(hour),
                        "sample": label,
                        "n": len(z),
                        "within_slot_ic": within_slot_ic(z),
                        "mean_gross_pips": pnl_metrics(z, pd.Index(sorted(group.sdate.unique()))).get("mean_gross_pips", np.nan),
                    }
                )
    return metric_rows, interaction_rows, cutpoint_rows, hourly_rows


def create_charts(metrics, summaries, stability, metadata, hourly):
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    cell_order = [f"{p[:3]}-{e}" for p in PAIRS for e in ["early", "late"]]
    label_map = {row.regime: row.short_label for row in metadata.itertuples()}

    heat = summaries.copy()
    heat["cell"] = heat.pair.str[:3] + "-" + heat.era.map({"early_exploration": "early", "late_exploration": "late"})
    matrix = heat.pivot(index="regime", columns="cell", values="strength_q5_minus_q1").reindex(columns=cell_order)
    matrix.index = [label_map.get(x, x) for x in matrix.index]
    fig_h = max(10, 0.35 * len(matrix) + 2)
    fig, ax = plt.subplots(figsize=(12, fig_h))
    sns.heatmap(matrix, center=0, cmap="vlag_r", annot=True, fmt=".02f", linewidths=0.25, ax=ax, cbar_kws={"label": "Q5-Q1 RSI IC strength"})
    ax.set_title("RSI strengthening by regime quintile and pair/era")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "ic_robustness_heatmap.png", dpi=170)
    plt.close(fig)

    mem = stability.merge(metadata, on="regime")
    mem = mem.loc[mem.memory_days.isin([30, 90]) & mem.family.ne("Trend vs chop")].copy()
    mem["comparison"] = mem["base"].astype(str) + " | " + mem["transform"].astype(str)
    pairs = []
    for key, group in mem.groupby(["family", "comparison"]):
        if set(group.memory_days) >= {30, 90}:
            a = group.loc[group.memory_days.eq(30)].iloc[0]
            b = group.loc[group.memory_days.eq(90)].iloc[0]
            pairs.append({"family": key[0], "comparison": key[1], "effect_30": a.median_strength_q5_minus_q1, "effect_90": b.median_strength_q5_minus_q1})
    comp = pd.DataFrame(pairs).sort_values(["family", "comparison"])
    fig, ax = plt.subplots(figsize=(11, max(7, 0.45 * len(comp) + 2)))
    y = np.arange(len(comp))
    for i, row in comp.reset_index(drop=True).iterrows():
        ax.plot([row.effect_30, row.effect_90], [i, i], color="0.7", lw=2)
    ax.scatter(comp.effect_30, y, label="30 sessions", marker="o", s=55)
    ax.scatter(comp.effect_90, y, label="90 sessions", marker="s", s=55)
    ax.axvline(0, color="0.2", lw=1)
    ax.set_yticks(y, comp.comparison)
    ax.set_xlabel("Median Q5-Q1 RSI IC strength across 8 pair/era cells")
    ax.set_title("Short versus long normalization memory")
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHART_DIR / "memory_30_vs_90.png", dpi=170)
    plt.close(fig)

    selected = [
        "vei_10_50_pct_30d",
        "vei_10_50_pct_90d",
        "rv_ratio_10_50_pct_30d",
        "rv_ratio_10_50_pct_90d",
        "rv_30m_pct_90d",
        "rv_30m_z_90d",
        "slot_fwd_rv_median_90d",
        "trend_efficiency_15m_pct_90d",
        "trend_efficiency_60m_pct_90d",
        "trend_efficiency_240m_pct_90d",
    ]
    curve = metrics.loc[metrics.regime.isin(selected)].copy()
    curve["strength"] = -curve.within_slot_ic
    curve = curve.groupby(["regime", "bin"], as_index=False).strength.median()
    fig, axes = plt.subplots(2, 5, figsize=(17, 8), sharex=True)
    for ax, regime in zip(axes.flat, selected):
        z = curve.loc[curve.regime.eq(regime)]
        ax.plot(z.bin, z.strength, marker="o")
        ax.set_title(label_map.get(regime, regime), fontsize=10)
        ax.set_xticks(range(1, 6))
        ax.set_xlabel("Regime quintile")
        ax.set_ylabel("|RSI signed IC|")
    fig.suptitle("Median RSI predictive strength across regime quintiles", y=1.01)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "ic_quintile_curves.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    pnl = summaries.copy()
    pnl["cell"] = pnl.pair.str[:3] + "-" + pnl.era.map({"early_exploration": "early", "late_exploration": "late"})
    pnl_matrix = pnl.pivot(index="regime", columns="cell", values="gross_pips_q5_minus_q1").reindex(columns=cell_order)
    pnl_matrix.index = [label_map.get(x, x) for x in pnl_matrix.index]
    fig, ax = plt.subplots(figsize=(12, fig_h))
    sns.heatmap(pnl_matrix, center=0, cmap="vlag", annot=True, fmt=".02f", linewidths=0.25, ax=ax, cbar_kws={"label": "Q5-Q1 gross pips/signal"})
    ax.set_title("Fixed RSI 30/70 gross payoff uplift by regime")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "pnl_uplift_heatmap.png", dpi=170)
    plt.close(fig)

    h = hourly.copy()
    h["strength"] = -h.within_slot_ic
    h = h.groupby(["ny_hour", "sample"], as_index=False).strength.median()
    fig, ax = plt.subplots(figsize=(12, 6))
    for label, group in h.groupby("sample"):
        ax.plot(group.ny_hour, group.strength, marker="o", label=label.replace("_", " "))
    ax.axvspan(16.5, 17.5, color="0.5", alpha=0.12, label="NY rollover hour")
    ax.set_xticks(range(24))
    ax.set_xlabel("New York hour")
    ax.set_ylabel("Median |RSI signed IC|")
    ax.set_title("RSI IC by New York hour and VEI(10/50) regime")
    ax.legend(ncol=4)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "new_york_hourly_ic.png", dpi=170)
    plt.close(fig)


def main():
    all_metrics = []
    all_interactions = []
    all_cutpoints = []
    all_hourly = []
    qualities = []
    metadata = None
    for pair in PAIRS:
        print(f"Building and analyzing {pair} ...", flush=True)
        panel, pair_metadata, quality = build_pair(pair)
        if metadata is None:
            metadata = pair_metadata
        else:
            assert [x["regime"] for x in metadata] == [x["regime"] for x in pair_metadata]
        metrics, interactions, cutpoints, hourly = analyze_pair(panel, pair_metadata)
        all_metrics.extend(metrics)
        all_interactions.extend(interactions)
        all_cutpoints.extend(cutpoints)
        all_hourly.extend(hourly)
        qualities.append(quality)
        print(f"  {len(panel):,} decisions; {quality['signal_rows']:,} RSI extreme rows", flush=True)

    metrics = pd.DataFrame(all_metrics)
    interactions = pd.DataFrame(all_interactions)
    interactions["interaction_q"] = np.nan
    for _, idx in interactions.groupby(["pair", "era"]).groups.items():
        interactions.loc[idx, "interaction_q"] = bh_adjust(interactions.loc[idx, "interaction_p"])

    summary_rows = []
    for keys, group in metrics.groupby(["pair", "era", "regime"]):
        q1 = group.loc[group.bin.eq(1)].iloc[0]
        q5 = group.loc[group.bin.eq(5)].iloc[0]
        strengths = -group.sort_values("bin").within_slot_ic.to_numpy()
        summary_rows.append(
            dict(zip(["pair", "era", "regime"], keys))
            | {
                "q1_ic": q1.within_slot_ic,
                "q5_ic": q5.within_slot_ic,
                "strength_q5_minus_q1": (-q5.within_slot_ic) - (-q1.within_slot_ic),
                "bin_strength_monotonic_rho": spearmanr(np.arange(1, 6), strengths).statistic,
                "q1_mean_gross_pips": q1.mean_gross_pips,
                "q5_mean_gross_pips": q5.mean_gross_pips,
                "gross_pips_q5_minus_q1": q5.mean_gross_pips - q1.mean_gross_pips,
                "q1_hit_rate": q1.hit_rate,
                "q5_hit_rate": q5.hit_rate,
                "q1_session_sharpe": q1.session_sharpe,
                "q5_session_sharpe": q5.session_sharpe,
                "q1_net_05_mean_pips": q1.mean_net_05_pips,
                "q5_net_05_mean_pips": q5.mean_net_05_pips,
            }
        )
    summaries = pd.DataFrame(summary_rows).merge(
        interactions[["pair", "era", "regime", "interaction_beta", "interaction_t", "interaction_p", "interaction_q"]],
        on=["pair", "era", "regime"],
        how="left",
    )
    stability_rows = []
    for regime, group in summaries.groupby("regime"):
        stability_rows.append(
            {
                "regime": regime,
                "cells": len(group),
                "q5_stronger_cells": int(group.strength_q5_minus_q1.gt(0).sum()),
                "strengthening_interaction_cells": int(group.interaction_beta.lt(0).sum()),
                "positive_pnl_uplift_cells": int(group.gross_pips_q5_minus_q1.gt(0).sum()),
                "median_strength_q5_minus_q1": group.strength_q5_minus_q1.median(),
                "median_interaction_beta": group.interaction_beta.median(),
                "median_abs_interaction_t": group.interaction_t.abs().median(),
                "median_gross_pips_q5_minus_q1": group.gross_pips_q5_minus_q1.median(),
                "min_interaction_q": group.interaction_q.min(),
                "max_interaction_q": group.interaction_q.max(),
            }
        )
    stability = pd.DataFrame(stability_rows).sort_values(
        ["q5_stronger_cells", "strengthening_interaction_cells", "median_abs_interaction_t"], ascending=False
    )
    metadata_frame = pd.DataFrame(metadata)
    metadata_frame["short_label"] = metadata_frame.regime.str.replace("_pct_", " p", regex=False).str.replace("_z_", " z", regex=False).str.replace("_median_", " med", regex=False).str.replace("trend_", "", regex=False).str.replace("_pct_90d", " p90", regex=False).str.replace("_", " ", regex=False)
    hourly = pd.DataFrame(all_hourly)

    create_charts(metrics, summaries, stability, metadata_frame, hourly)
    payload = {
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "start": START.isoformat(),
            "holdout_start": HOLDOUT.isoformat(),
            "pairs": PAIRS,
            "horizon_min": HORIZON,
            "timezone": "America/New_York",
            "hypothetical_cost_pips": HYPOTHETICAL_COST_PIPS,
        },
        "regime_definitions": json.loads(metadata_frame.to_json(orient="records")),
        "quality": json.loads(pd.DataFrame(qualities).to_json(orient="records", date_format="iso")),
        "cutpoints": all_cutpoints,
        "metrics": json.loads(metrics.to_json(orient="records")),
        "interactions": json.loads(interactions.to_json(orient="records")),
        "summaries": json.loads(summaries.to_json(orient="records")),
        "stability": json.loads(stability.to_json(orient="records")),
        "hourly": json.loads(hourly.to_json(orient="records")),
        "charts": [str(p.relative_to(ROOT)) for p in sorted(CHART_DIR.glob("*.png"))],
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    stability.to_csv(ROOT / "rsi_broad_regime_sweep_stability.csv", index=False)
    summaries.to_csv(ROOT / "rsi_broad_regime_sweep_summaries.csv", index=False)
    print("\nTop stability rows:")
    print(stability.head(20).round(4).to_string(index=False))
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
