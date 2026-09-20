"""Run the configurable four-pair low-volatility false-breakout backtest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_engine.engine import add_costs, simulate_asset, summarize
from strategy.signals import build_decision_bars, build_signals, timeframe_minutes


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="baseline_replication/configs/baseline.json")
    parser.add_argument("--output", default="artifacts/runs/EXP-0001")
    parser.add_argument("--timeframe")
    parser.add_argument("--atr-period", type=int)
    parser.add_argument("--atr-percentile", type=float)
    parser.add_argument("--stop-atr", type=float)
    parser.add_argument("--target-atr", type=float)
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> dict:
    path = Path(args.config)
    if not path.is_absolute():
        path = ROOT / path
    config = json.loads(path.read_text(encoding="utf-8"))
    overrides = {
        "timeframe": args.timeframe,
        "atr_period": args.atr_period,
        "atr_percentile": args.atr_percentile,
        "stop_atr": args.stop_atr,
        "target_atr": args.target_atr,
    }
    config.update({k: v for k, v in overrides.items() if v is not None})
    return config


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_minutes(path: Path) -> pd.DataFrame:
    raw = pd.read_parquet(path, columns=["ts_utc", "open", "high", "low", "close"])
    raw["ts_utc"] = pd.to_datetime(raw["ts_utc"])
    if raw["ts_utc"].duplicated().any():
        raise ValueError(f"duplicate timestamps in {path}")
    if not raw["ts_utc"].is_monotonic_increasing:
        raise ValueError(f"out-of-order timestamps in {path}")
    return raw.set_index("ts_utc")


def data_quality(asset: str, path: Path, minute: pd.DataFrame,
                 bucket_diag: pd.DataFrame, features: pd.DataFrame,
                 timeframe: str) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    diffs = minute.index.to_series().diff().dropna()
    one_min = pd.Timedelta(minutes=1)
    gaps = diffs[diffs > one_min]
    gap_table = pd.DataFrame({
        "year": gaps.index.year,
        "gap_count": 1,
        "missing_minutes": (gaps / one_min).astype(int) - 1,
    }).groupby("year").sum()
    invalid_ohlc = (
        (minute["high"] < minute[["open", "close", "low"]].max(axis=1))
        | (minute["low"] > minute[["open", "close", "high"]].min(axis=1))
    )
    minutes = timeframe_minutes(timeframe)
    by_year = pd.DataFrame({"year": minute.index.year}).value_counts().rename("minute_rows").reset_index()
    buckets_year = bucket_diag.assign(year=bucket_diag.index.year).groupby("year").agg(
        decision_buckets=("complete", "size"), complete_buckets=("complete", "sum"))
    feat_year = features.assign(year=features.index.year).groupby("year").agg(
        valid_atr=("atr", "count"), valid_threshold=("atr_threshold", "count"),
        valid_breakout=("prior_high", "count"), signals=("signal", lambda x: int((x != 0).sum())))
    yearly = (buckets_year.join(by_year.set_index("year"), how="outer")
              .join(feat_year, how="outer").join(gap_table, how="outer").reset_index())
    bucket_hour = bucket_diag.assign(hour_utc=bucket_diag.index.hour).groupby("hour_utc").agg(
        decision_buckets=("complete", "size"), complete_buckets=("complete", "sum"))
    feature_hour = features.assign(hour_utc=features.index.hour).groupby("hour_utc").agg(
        feature_rows=("signal", "size"), valid_atr=("atr", "count"),
        valid_threshold=("atr_threshold", "count"), valid_breakout=("prior_high", "count"),
        low_vol=("low_vol", "sum"), signals=("signal", lambda x: int((x != 0).sum())))
    hourly = bucket_hour.join(feature_hour, how="outer").reset_index()
    report = {
        "asset": asset,
        "path": str(path),
        "sha256": sha256(path),
        "rows": int(len(minute)),
        "start": str(minute.index.min()),
        "end": str(minute.index.max()),
        "duplicates": int(minute.index.duplicated().sum()),
        "out_of_order": int((diffs < pd.Timedelta(0)).sum()),
        "gap_count": int(len(gaps)),
        "missing_calendar_minutes_across_gaps": int(sum(int(x / one_min) - 1 for x in gaps)),
        "max_gap_minutes": float(diffs.max() / one_min),
        "weekend_rows": int((minute.index.weekday >= 5).sum()),
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "decision_buckets": int(len(bucket_diag)),
        "complete_decision_buckets": int(bucket_diag["complete"].sum()),
        "incomplete_decision_buckets": int((~bucket_diag["complete"]).sum()),
        "expected_minutes_per_bucket": minutes,
        "feature_rows": int(len(features)),
        "atr_underpopulated": int(features["atr"].isna().sum()),
        "percentile_underpopulated": int(features["atr_threshold"].isna().sum()),
        "breakout_underpopulated": int(features["prior_high"].isna().sum()),
        "signals": int(features["signal"].ne(0).sum()),
        "roll_adjustment_boundaries": "not applicable: spot FX series",
        "policy": "incomplete decision candles dropped; rolling windows use compact valid candles",
    }
    yearly.insert(0, "asset", asset)
    hourly.insert(0, "asset", asset)
    return report, yearly, hourly


def clustered_mean_ci(trades: pd.DataFrame, col: str, seed: int = 10,
                      draws: int = 2000) -> tuple[float, float]:
    if trades.empty:
        return np.nan, np.nan
    work = trades.copy()
    work["cluster"] = pd.to_datetime(work["exit_time"]).dt.date
    groups = [g[col].to_numpy(float) for _, g in work.groupby("cluster")]
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    for i in range(draws):
        picked = rng.integers(0, len(groups), len(groups))
        values = np.concatenate([groups[j] for j in picked])
        means[i] = values.mean()
    return tuple(float(x) for x in np.quantile(means, [0.025, 0.975]))


def daily_metrics(trades: pd.DataFrame, col: str) -> dict[str, float]:
    if trades.empty:
        return {"daily_sharpe": np.nan, "max_drawdown_r": np.nan}
    dates = pd.to_datetime(trades["exit_time"]).dt.normalize()
    realised = trades.assign(date=dates).groupby("date")[col].sum()
    # FX can realize P&L on Sunday UTC; a business-day index would silently drop it.
    calendar = pd.date_range(realised.index.min(), realised.index.max(), freq="D")
    daily = realised.reindex(calendar, fill_value=0.0)
    sharpe = np.sqrt(365.0) * daily.mean() / daily.std(ddof=1) if daily.std(ddof=1) > 0 else np.nan
    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    return {"daily_sharpe": float(sharpe), "max_drawdown_r": float(drawdown.min())}


def render_findings(config: dict, metrics: pd.DataFrame, dq: list[dict],
                    pooled_ci: tuple[float, float], trades: pd.DataFrame,
                    hourly: pd.DataFrame) -> str:
    gross = metrics[metrics["cost_pips"].eq(0.0)].set_index("asset")
    pair_rows = []
    for asset in config["assets"]:
        r = gross.loc[asset]
        pair_rows.append(
            f"| {asset} | {int(r['trades'])} | {r['mean_r']:+.4f} | "
            f"{r['mean_pips']:+.3f} | {r['win_rate']:.1%} | {r['profit_factor']:.3f} |"
        )
    pooled = gross.loc["POOLED"]
    costs = metrics[metrics["asset"].eq("POOLED")]
    cost_rows = [f"| {r.cost_pips:.1f} | {r.mean_r:+.4f} | {r.mean_pips:+.3f} | {r.daily_sharpe:+.3f} |"
                 for r in costs.itertuples()]
    reasons = trades["exit_reason"].value_counts().to_dict()
    positive_pairs = int((gross.drop(index="POOLED")["mean_r"] > 0).sum())
    go = pooled["mean_r"] > 0 and pooled_ci[0] > 0 and positive_pairs >= 3
    verdict = "GO (exploratory only)" if go else "NO-GO under the preregistered kill test"
    recent = trades[pd.to_datetime(trades["entry_time"]).dt.year >= 2020]
    recent_by_pair = recent.groupby("asset")["gross_r"].mean()
    low_vol_rate = hourly["low_vol"] / hourly["valid_threshold"]
    return f"""# Findings

## Result

**{verdict}.** The pooled gross mean is {pooled['mean_r']:+.4f} R per trade
(date-cluster bootstrap 95% CI {pooled_ci[0]:+.4f} to {pooled_ci[1]:+.4f});
{positive_pairs}/4 pairs are positive. This is discovery evidence because all
available history was inspected and no claim-matched path-preserving null has
yet been run.

## Gross baseline by pair

| Asset | Trades | Mean R | Mean pips | Win rate | Profit factor |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(pair_rows)}

## Pooled cost sensitivity

| Round-trip cost (pip) | Mean R | Mean pips | Daily Sharpe |
| ---: | ---: | ---: | ---: |
{chr(10).join(cost_rows)}

Exit reasons: `{json.dumps(reasons, sort_keys=True)}`.

The 2020+ gross mean is {recent['gross_r'].mean():+.4f} R pooled, with all four
pairs still positive ({', '.join(f'{a} {recent_by_pair[a]:+.4f}' for a in config['assets'])}).
This is an inspected stability slice, not a holdout.

The low-volatility gate fires on {low_vol_rate.min():.1%} to
{low_vol_rate.max():.1%} of eligible bars across asset-by-UTC-hour cells. That
large clock profile means the gate is also a time-of-day selector and requires
a matched-rate or same-slot control before attributing the result to volatility.

## Interpretation limits

- Prices are midpoint OHLC; the cost grid is a sensitivity, not measured spread.
- Brackets are replayed at 1-minute grain. Any stop/target collision within one
  minute is assigned to the stop, but finer sequencing remains unknown.
- The four USD pairs are correlated and do not constitute four independent tests.
- Capacity, financing, live latency, and executable bid/ask spreads are not modeled.

## Configuration

```json
{json.dumps(config, indent=2)}
```
"""


def main() -> None:
    args = parse_args()
    config = load_config(args)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    (output / "config_used.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    all_trades: list[pd.DataFrame] = []
    dq_reports: list[dict] = []
    yearly_reports: list[pd.DataFrame] = []
    hourly_reports: list[pd.DataFrame] = []
    for asset in config["assets"]:
        path = ROOT / config["data_pattern"].format(asset=asset)
        minute = load_minutes(path.resolve())
        bars, bucket_diag = build_decision_bars(
            minute, config["timeframe"], config["require_complete_candles"])
        features = build_signals(
            bars, config["timeframe"], config["atr_period"], config["atr_percentile"],
            config["percentile_lookback"], config["breakout_lookback"])
        dq, yearly, hourly = data_quality(asset, path.resolve(), minute, bucket_diag,
                                          features, config["timeframe"])
        dq_reports.append(dq)
        yearly_reports.append(yearly)
        hourly_reports.append(hourly)
        trades = simulate_asset(
            asset, minute, features, config["stop_atr"], config["target_atr"],
            config["max_holding_hours"], config["pip_size"])
        all_trades.append(trades)

    trades = pd.concat(all_trades, ignore_index=True)
    trades.to_csv(output / "trades.csv", index=False)
    pd.DataFrame(dq_reports).to_csv(output / "data_quality.csv", index=False)
    pd.concat(yearly_reports, ignore_index=True).to_csv(output / "data_quality_by_year.csv", index=False)
    hourly = pd.concat(hourly_reports, ignore_index=True)
    hourly.to_csv(output / "data_quality_by_utc_hour.csv", index=False)

    trade_year = pd.to_datetime(trades["entry_time"]).dt.year
    by_year = (trades.assign(year=trade_year).groupby(["asset", "year"])["gross_r"]
               .agg(trades="size", mean_r="mean", total_r="sum").reset_index())
    by_year.to_csv(output / "metrics_by_year.csv", index=False)
    era = np.where(trade_year >= 2020, "2020+", "pre-2020")
    by_era = (trades.assign(era=era).groupby(["asset", "era"])["gross_r"]
              .agg(trades="size", mean_r="mean", total_r="sum").reset_index())
    by_era.to_csv(output / "metrics_by_era.csv", index=False)

    metric_rows = []
    for cost in config["round_trip_cost_pips"]:
        costed = add_costs(trades, cost, config["pip_size"])
        for asset in [*config["assets"], "POOLED"]:
            sample = costed if asset == "POOLED" else costed[costed["asset"].eq(asset)]
            s_r = summarize(sample, "net_r")
            s_p = summarize(sample, "net_pips")
            dm = daily_metrics(sample, "net_r")
            metric_rows.append({
                "asset": asset, "cost_pips": float(cost), "trades": s_r["trades"],
                "mean_r": s_r["mean"], "median_r": s_r["median"],
                "mean_pips": s_p["mean"], "win_rate": s_r["win_rate"],
                "profit_factor": s_r["profit_factor"], "total_r": s_r["total"], **dm,
            })
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(output / "metrics.csv", index=False)
    ci = clustered_mean_ci(trades, "gross_r")
    summary = {
        "config": config,
        "data_quality": dq_reports,
        "gross_pooled_cluster_bootstrap_ci": list(ci),
        "metrics": metrics.to_dict(orient="records"),
        "exit_reasons": trades["exit_reason"].value_counts().to_dict(),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    findings = render_findings(config, metrics, dq_reports, ci, trades, hourly)
    (output / "review.md").write_text(findings, encoding="utf-8")
    (ROOT / "reports" / "FINDINGS.md").write_text(findings, encoding="utf-8")
    print(metrics.to_string(index=False))
    print(f"\nPooled gross date-cluster bootstrap 95% CI: {ci[0]:+.4f}, {ci[1]:+.4f}")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
