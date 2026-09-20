"""Per-asset walk-forward optimisation with a hard, untested final holdout."""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_engine.engine import add_costs, simulate_asset
from strategy.signals import build_decision_bars, build_signals


ROOT = Path(__file__).resolve().parent
PARAMETERS = ["timeframe", "atr_period", "atr_percentile", "stop_atr", "target_atr"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="experiments/configs/walk_forward_grid.json")
    parser.add_argument("--output", default="artifacts/runs/EXP-0002")
    return parser.parse_args()


def load_pre_holdout(path: Path, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Predicate-filter at source and fail closed if any reserved row appears."""
    columns = ["ts_utc", "open", "high", "low", "close"]
    raw = pd.read_parquet(
        path, columns=columns,
        filters=[("ts_utc", "<", cutoff.to_pydatetime())],
    )
    raw["ts_utc"] = pd.to_datetime(raw["ts_utc"])
    if raw.empty or raw["ts_utc"].max() >= cutoff:
        raise AssertionError(f"holdout isolation failed for {path.name}")
    if raw["ts_utc"].duplicated().any() or not raw["ts_utc"].is_monotonic_increasing:
        raise ValueError(f"bad timestamp ordering in {path}")
    return raw.set_index("ts_utc")


def make_folds(config: dict, cutoff: pd.Timestamp) -> list[dict]:
    start = pd.Timestamp(config["walk_forward_start"])
    validation_start = start + pd.DateOffset(years=int(config["train_years"]))
    folds = []
    number = 1
    while validation_start < cutoff:
        natural_end = validation_start + pd.DateOffset(years=int(config["validation_years"]))
        validation_end = min(natural_end, cutoff)
        is_partial = validation_end < natural_end
        if is_partial and not config.get("allow_final_partial_validation", False):
            break
        folds.append({
            "fold": f"WF-{number:02d}",
            "train_start": validation_start - pd.DateOffset(years=int(config["train_years"])),
            "train_end": validation_start,
            "validation_start": validation_start,
            "validation_end": validation_end,
            "partial_validation": is_partial,
        })
        validation_start += pd.DateOffset(years=int(config["validation_years"]))
        number += 1
    return folds


def candidates(config: dict) -> list[dict]:
    result = []
    values = [config[name] for name in PARAMETERS]
    for combo in itertools.product(*values):
        candidate = dict(zip(PARAMETERS, combo))
        candidate["config_id"] = (
            f"tf{candidate['timeframe']}_a{candidate['atr_period']}_"
            f"p{candidate['atr_percentile']:.2f}_s{candidate['stop_atr']:.1f}_"
            f"t{candidate['target_atr']:.1f}"
        )
        result.append(candidate)
    return result


def period_metrics(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                   cost_pips: float, pip_size: float) -> dict[str, float | int]:
    exits = pd.to_datetime(trades["exit_time"])
    sample = trades[(exits >= start) & (exits < end) & trades["exit_reason"].ne("end_of_data")]
    sample = add_costs(sample, cost_pips, pip_size)
    if sample.empty:
        return {"trades": 0, "mean_net_r": np.nan, "mean_net_pips": np.nan,
                "daily_sharpe": np.nan, "total_net_r": 0.0, "max_drawdown_r": np.nan}
    dates = pd.to_datetime(sample["exit_time"]).dt.normalize()
    realised = sample.assign(date=dates).groupby("date")["net_r"].sum()
    calendar = pd.date_range(start.normalize(), (end - pd.Timedelta(days=1)).normalize(), freq="D")
    daily = realised.reindex(calendar, fill_value=0.0)
    std = daily.std(ddof=1)
    sharpe = np.sqrt(365.0) * daily.mean() / std if std > 0 else np.nan
    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    return {
        "trades": int(len(sample)),
        "mean_net_r": float(sample["net_r"].mean()),
        "mean_net_pips": float(sample["net_pips"].mean()),
        "daily_sharpe": float(sharpe),
        "total_net_r": float(sample["net_r"].sum()),
        "max_drawdown_r": float(drawdown.min()),
    }


def pooled_metrics(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    if trades.empty:
        return period_metrics(trades, start, end, 0.0, 0.0001)
    # Trades are already costed by their asset-specific bracket risk.
    exits = pd.to_datetime(trades["exit_time"])
    sample = trades[(exits >= start) & (exits < end)]
    dates = pd.to_datetime(sample["exit_time"]).dt.normalize()
    realised = sample.assign(date=dates).groupby("date")["net_r"].sum()
    calendar = pd.date_range(start.normalize(), (end - pd.Timedelta(days=1)).normalize(), freq="D")
    daily = realised.reindex(calendar, fill_value=0.0)
    std = daily.std(ddof=1)
    equity = daily.cumsum()
    return {
        "trades": int(len(sample)),
        "mean_net_r": float(sample["net_r"].mean()),
        "mean_net_pips": float(sample["net_pips"].mean()),
        "daily_sharpe": float(np.sqrt(365.0) * daily.mean() / std) if std > 0 else np.nan,
        "total_net_r": float(sample["net_r"].sum()),
        "max_drawdown_r": float((equity - equity.cummax()).min()),
    }


def build_feature_set(minute: pd.DataFrame, candidate: dict, config: dict) -> pd.DataFrame:
    bars, _ = build_decision_bars(minute, candidate["timeframe"], config["require_complete_candles"])
    return build_signals(
        bars, candidate["timeframe"], int(candidate["atr_period"]),
        float(candidate["atr_percentile"]), int(config["percentile_lookback"]),
        int(config["breakout_lookback"]),
    )


def simulate_candidate(asset: str, minute: pd.DataFrame, features: pd.DataFrame,
                       candidate: dict, config: dict) -> pd.DataFrame:
    return simulate_asset(
        asset, minute, features, float(candidate["stop_atr"]),
        float(candidate["target_atr"]), float(config["max_holding_hours"]),
        float(config["pip_size"]),
    )


def select_best(scores: pd.DataFrame, minimum_trades: int) -> pd.Series:
    valid = scores[scores["trades"] >= minimum_trades].dropna(subset=["daily_sharpe"])
    if valid.empty:
        raise RuntimeError("no candidate meets the minimum training sample")
    return valid.sort_values(
        ["daily_sharpe", "mean_net_r", "config_id"],
        ascending=[False, False, True], kind="stable").iloc[0]


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    (output / "config_used.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    grid = candidates(config)
    if len(grid) != 243:
        raise AssertionError(f"expected frozen 243-candidate grid, got {len(grid)}")
    score_rows = []
    holdout_audit = {}
    minutes_by_asset: dict[str, pd.DataFrame] = {}
    folds_by_asset: dict[str, list[dict]] = {}

    for asset in config["assets"]:
        cutoff = pd.Timestamp(config["holdout_start"][asset])
        path = (ROOT / config["data_pattern"].format(asset=asset)).resolve()
        minute = load_pre_holdout(path, cutoff)
        minutes_by_asset[asset] = minute
        folds = make_folds(config, cutoff)
        folds_by_asset[asset] = folds
        holdout_audit[asset] = {
            "holdout_start": str(cutoff),
            "maximum_loaded_timestamp": str(minute.index.max()),
            "loaded_rows": int(len(minute)),
            "assertion": "maximum_loaded_timestamp < holdout_start",
            "holdout_outcomes_evaluated": False,
        }
        final_start = cutoff - pd.DateOffset(years=int(config["train_years"]))
        print(f"{asset}: {len(minute):,} pre-holdout rows, {len(folds)} folds", flush=True)

        for timeframe in config["timeframe"]:
            bars, _ = build_decision_bars(minute, timeframe, config["require_complete_candles"])
            for atr_period in config["atr_period"]:
                for percentile in config["atr_percentile"]:
                    feature_candidate = {
                        "timeframe": timeframe, "atr_period": atr_period,
                        "atr_percentile": percentile,
                    }
                    features = build_signals(
                        bars, timeframe, atr_period, percentile,
                        config["percentile_lookback"], config["breakout_lookback"])
                    for stop_atr, target_atr in itertools.product(config["stop_atr"], config["target_atr"]):
                        candidate = {**feature_candidate, "stop_atr": stop_atr, "target_atr": target_atr}
                        candidate["config_id"] = (
                            f"tf{timeframe}_a{atr_period}_p{percentile:.2f}_"
                            f"s{stop_atr:.1f}_t{target_atr:.1f}"
                        )
                        trades = simulate_candidate(asset, minute, features, candidate, config)
                        for fold in folds:
                            m = period_metrics(
                                trades, fold["train_start"], fold["train_end"],
                                config["selection_cost_pips"], config["pip_size"])
                            score_rows.append({
                                "asset": asset, "selection_period": fold["fold"],
                                "train_start": fold["train_start"], "train_end": fold["train_end"],
                                **candidate, **m,
                            })
                        m = period_metrics(trades, final_start, cutoff,
                                           config["selection_cost_pips"], config["pip_size"])
                        score_rows.append({
                            "asset": asset, "selection_period": "FINAL_FIT",
                            "train_start": final_start, "train_end": cutoff,
                            **candidate, **m,
                        })
                    print(f"  {timeframe} ATR={atr_period} pct={percentile:.2f} complete", flush=True)

    scores = pd.DataFrame(score_rows)
    scores.to_csv(output / "candidate_training_scores.csv", index=False)
    selections = []
    final_locked = {"holdout_evaluated": False, "parameters": {}}
    for asset in config["assets"]:
        for fold in folds_by_asset[asset]:
            chosen = select_best(
                scores[(scores["asset"] == asset) & (scores["selection_period"] == fold["fold"])],
                config["minimum_training_trades"])
            selections.append({**fold, **chosen.to_dict()})
        chosen = select_best(
            scores[(scores["asset"] == asset) & (scores["selection_period"] == "FINAL_FIT")],
            config["minimum_training_trades"])
        final_locked["parameters"][asset] = {
            **{name: chosen[name].item() if hasattr(chosen[name], "item") else chosen[name]
               for name in PARAMETERS},
            "config_id": chosen["config_id"],
            "training_daily_sharpe": float(chosen["daily_sharpe"]),
            "training_mean_net_r": float(chosen["mean_net_r"]),
            "training_trades": int(chosen["trades"]),
            "holdout_start": config["holdout_start"][asset],
            "holdout_evaluated": False,
        }

    selection_df = pd.DataFrame(selections)
    selected_oos = []
    baseline_oos = []
    baseline = {"timeframe": "30min", "atr_period": 14, "atr_percentile": 0.15,
                "stop_atr": 1.5, "target_atr": 1.5, "config_id": "BASELINE"}
    validation_rows = []
    for asset in config["assets"]:
        minute = minutes_by_asset[asset]
        feature_cache: dict[tuple, pd.DataFrame] = {}
        trade_cache: dict[str, pd.DataFrame] = {}
        asset_selections = selection_df[selection_df["asset"] == asset]
        configs_to_run = [baseline] + [row.to_dict() for _, row in asset_selections.iterrows()]
        for candidate in configs_to_run:
            cid = candidate["config_id"]
            if cid in trade_cache:
                continue
            feature_key = (candidate["timeframe"], int(candidate["atr_period"]),
                           float(candidate["atr_percentile"]))
            if feature_key not in feature_cache:
                feature_cache[feature_key] = build_feature_set(minute, candidate, config)
            trade_cache[cid] = simulate_candidate(asset, minute, feature_cache[feature_key], candidate, config)

        for _, row in asset_selections.iterrows():
            start, end = pd.Timestamp(row["validation_start"]), pd.Timestamp(row["validation_end"])
            chosen_trades = trade_cache[row["config_id"]]
            exits = pd.to_datetime(chosen_trades["exit_time"])
            sample = chosen_trades[(exits >= start) & (exits < end) &
                                   chosen_trades["exit_reason"].ne("end_of_data")]
            sample = add_costs(sample, config["selection_cost_pips"], config["pip_size"])
            sample["fold"] = row["fold"]
            sample["selected_config_id"] = row["config_id"]
            selected_oos.append(sample)
            chosen_metrics = period_metrics(chosen_trades, start, end,
                                            config["selection_cost_pips"], config["pip_size"])

            base_trades = trade_cache["BASELINE"]
            base_exits = pd.to_datetime(base_trades["exit_time"])
            base_sample = base_trades[(base_exits >= start) & (base_exits < end) &
                                      base_trades["exit_reason"].ne("end_of_data")]
            base_sample = add_costs(base_sample, config["selection_cost_pips"], config["pip_size"])
            base_sample["fold"] = row["fold"]
            baseline_oos.append(base_sample)
            base_metrics = period_metrics(base_trades, start, end,
                                          config["selection_cost_pips"], config["pip_size"])
            validation_rows.append({
                "asset": asset, "fold": row["fold"], "validation_start": start,
                "validation_end": end, "selected_config_id": row["config_id"],
                **{name: row[name] for name in PARAMETERS},
                **{f"selected_{k}": v for k, v in chosen_metrics.items()},
                **{f"baseline_{k}": v for k, v in base_metrics.items()},
            })

    selected_oos_df = pd.concat(selected_oos, ignore_index=True)
    baseline_oos_df = pd.concat(baseline_oos, ignore_index=True)
    cutoff = min(pd.Timestamp(v) for v in config["holdout_start"].values())
    if (pd.to_datetime(selected_oos_df["exit_time"]) >= cutoff).any():
        raise AssertionError("selected validation leaked into holdout")
    selected_oos_df.to_csv(output / "walk_forward_oos_trades.csv", index=False)
    pd.DataFrame(validation_rows).to_csv(output / "walk_forward_selections.csv", index=False)

    summary_rows = []
    validation_start = min(f["validation_start"] for f in folds_by_asset[config["assets"][0]])
    for asset in [*config["assets"], "POOLED"]:
        selected = selected_oos_df if asset == "POOLED" else selected_oos_df[selected_oos_df["asset"] == asset]
        base = baseline_oos_df if asset == "POOLED" else baseline_oos_df[baseline_oos_df["asset"] == asset]
        sm = pooled_metrics(selected, validation_start, cutoff)
        bm = pooled_metrics(base, validation_start, cutoff)
        summary_rows.append({
            "asset": asset, **{f"selected_{k}": v for k, v in sm.items()},
            **{f"baseline_{k}": v for k, v in bm.items()},
            "sharpe_delta": sm["daily_sharpe"] - bm["daily_sharpe"],
        })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(output / "walk_forward_summary.csv", index=False)
    (output / "final_locked_parameters.json").write_text(
        json.dumps(final_locked, indent=2, default=str) + "\n", encoding="utf-8")
    (output / "holdout_audit.json").write_text(
        json.dumps(holdout_audit, indent=2) + "\n", encoding="utf-8")

    pooled = summary[summary["asset"] == "POOLED"].iloc[0]
    positive_assets = int((summary[summary["asset"] != "POOLED"]["selected_mean_net_r"] > 0).sum())
    passed = (pooled["selected_daily_sharpe"] > 0 and pooled["sharpe_delta"] >= 0.10
              and positive_assets >= 3)
    final_lines = [f"- {a}: `{p['config_id']}`" for a, p in final_locked["parameters"].items()]
    table_lines = []
    for row in summary.itertuples():
        table_lines.append(
            f"| {row.asset} | {row.selected_trades} | {row.selected_mean_net_r:+.4f} | "
            f"{row.selected_daily_sharpe:+.3f} | {row.baseline_daily_sharpe:+.3f} | {row.sharpe_delta:+.3f} |"
        )
    review = f"""# EXP-0002 Walk-forward optimisation

## Verdict

**{'PASS' if passed else 'NO-GO'} under the frozen walk-forward kill test.**
Across stitched validation windows, the selected policy has pooled daily Sharpe
{pooled['selected_daily_sharpe']:+.3f} versus {pooled['baseline_daily_sharpe']:+.3f}
for the static baseline (delta {pooled['sharpe_delta']:+.3f}); {positive_assets}/4
assets have positive mean net R after 0.5 pip round-trip cost.

| Asset | Validation trades | Mean net R | Selected Sharpe | Baseline Sharpe | Delta |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(table_lines)}

## Locked parameters for the untested optimisation holdout

{chr(10).join(final_lines)}

The reserved interval begins 2024-07-18 UTC for every pair. It was not loaded,
scored, or used in parameter selection by this run. `holdout_audit.json` records
the fail-closed timestamp assertions. Do not add holdout results to this run.

## Interpretation

- The search covered 243 configurations per asset. Each validation fold was
  evaluated only after selection on its preceding rolling five-year training window.
- The final partial validation ends at the holdout boundary; it is labelled in
  `walk_forward_selections.csv`.
- The baseline had already inspected the reserved dates in EXP-0001, so this is
  an optimisation holdout, not a clean thesis-level historical holdout.
- Midpoint execution and a fixed 0.5-pip charge remain approximations. The clock
  selector and claim-matched null remain unresolved.
- Independent review is pending.
"""
    (output / "review.md").write_text(review, encoding="utf-8")
    print(summary.to_string(index=False), flush=True)
    print("\nFinal locked parameters (holdout not evaluated):", flush=True)
    print(json.dumps(final_locked["parameters"], indent=2, default=str), flush=True)
    print(f"\nVerdict: {'PASS' if passed else 'NO-GO'}", flush=True)


if __name__ == "__main__":
    main()
