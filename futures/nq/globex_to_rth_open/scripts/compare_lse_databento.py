"""Compare LSE and Databento under an identical SMA200 vol-target specification."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_engine.vol_target import (  # noqa: E402
    VolTargetSpec, build_vol_targeted_leg, summarize_return_period, yearly_performance,
)
from strategy.features import file_sha256  # noqa: E402


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=PROJECT_ROOT / "experiments" / "configs" / "compare_lse_databento.json")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def apply_gate(sized: pd.DataFrame, gate: pd.Series) -> pd.DataFrame:
    result = sized.copy()
    result["active"] = gate.fillna(False).astype(bool)
    result["effective_leverage"] = result["leverage"].where(result["active"], 0.0)
    for column in ("gross_strategy_return", "net_strategy_return", "strategy_cost_return"):
        result[column] = result[column].where(result["active"], 0.0)
    return result


def prefix_metrics(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    keep = ["year", "observations", "trades", "net_compound_return",
            "annualized_net_vol", "net_sharpe", "max_drawdown", "average_leverage"]
    selected = frame[[column for column in keep if column in frame]].copy()
    return selected.rename(columns={column: f"{prefix}_{column}" for column in selected if column != "year"})


def frame_from_returns(base: pd.DataFrame, returns: pd.Series, leverage: pd.Series,
                       active: pd.Series) -> pd.DataFrame:
    result = pd.DataFrame({
        "trade_date": base["trade_date"],
        "net_strategy_return": returns,
        "gross_strategy_return": returns,
        "leverage": leverage,
        "effective_leverage": leverage.where(active, 0.0),
        "annualized_vol_estimate": base["annualized_vol_estimate_lse"],
        "active": active,
    })
    return result


def main() -> int:
    args = parse_args()
    config_path = resolve(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    paths = {name: resolve(config[name]) for name in (
        "databento_candidates", "databento_unfiltered_yearly", "lse_daily_returns")}
    output = resolve(args.output or config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    spec = VolTargetSpec(**config["vol_target"])

    db_candidates = pd.read_parquet(paths["databento_candidates"])
    db_sized, db_quality = build_vol_targeted_leg(db_candidates, spec)
    sma_column = f"sma_{config['sma_days']}"
    db_post = db_sized.loc[db_sized[sma_column].notna()].copy()
    db = apply_gate(db_post, db_post["entry_price"] > db_post[sma_column])
    lse = pd.read_parquet(paths["lse_daily_returns"]).sort_values("trade_date").copy()
    for frame in (db, lse):
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])

    db_yearly = yearly_performance(db, spec.annualization_days)
    lse_yearly = yearly_performance(lse, spec.annualization_days)
    old_db = pd.read_csv(paths["databento_unfiltered_yearly"])
    side_by_side = prefix_metrics(lse_yearly, "lse_sma200").merge(
        prefix_metrics(db_yearly, "databento_sma200"), on="year", how="outer")
    old_keep = old_db[["year", "net_compound_return", "net_sharpe", "trades"]].rename(columns={
        "net_compound_return": "databento_old_unfiltered_net_compound_return",
        "net_sharpe": "databento_old_unfiltered_net_sharpe",
        "trades": "databento_old_unfiltered_trades",
    })
    side_by_side = side_by_side.merge(old_keep, on="year", how="outer").sort_values("year")
    side_by_side["sma200_return_difference_lse_minus_db"] = (
        side_by_side["lse_sma200_net_compound_return"] -
        side_by_side["databento_sma200_net_compound_return"])

    merge_columns = ["trade_date", "entry_price", "exit_price", "gross_leg_return",
                     "net_leg_return", "annualized_vol_estimate", "leverage", "active",
                     "net_strategy_return", sma_column]
    common = lse[merge_columns].merge(
        db[merge_columns], on="trade_date", how="inner", suffixes=("_lse", "_db"))
    common["year"] = common["trade_date"].dt.year
    lse_active = common["active_lse"].astype(bool)
    db_active = common["active_db"].astype(bool)
    common["db_return_lse_controls"] = np.where(
        lse_active, common["leverage_lse"] * common["net_leg_return_db"], 0.0)
    common["lse_return_lse_controls"] = common["net_strategy_return_lse"]
    common["db_own_return"] = common["net_strategy_return_db"]
    common["gross_leg_return_difference_bps"] = (
        (common["gross_leg_return_lse"] - common["gross_leg_return_db"]) * 1e4)
    common["roll_mismatch_suspect"] = (
        common["gross_leg_return_difference_bps"].abs() >=
        config["roll_mismatch_diagnostic_threshold_bps"])

    common_rows = []
    diagnostic_rows = []
    for year, group in common.groupby("year", sort=True):
        active_lse = group["active_lse"].astype(bool)
        active_db = group["active_db"].astype(bool)
        lse_frame = frame_from_returns(
            group, group["lse_return_lse_controls"], group["leverage_lse"], active_lse)
        db_controlled = frame_from_returns(
            group, group["db_return_lse_controls"], group["leverage_lse"], active_lse)
        db_own = frame_from_returns(
            group, group["db_own_return"], group["leverage_db"], active_db)
        summaries = [summarize_return_period(frame, spec.annualization_days)
                     for frame in (lse_frame, db_own, db_controlled)]
        clean = group.loc[~group["roll_mismatch_suspect"]].copy()
        clean_lse_active = clean["active_lse"].astype(bool)
        clean_db_active = clean["active_db"].astype(bool)
        clean_lse = frame_from_returns(
            clean, clean["net_strategy_return_lse"], clean["leverage_lse"], clean_lse_active)
        clean_db = frame_from_returns(
            clean, clean["net_strategy_return_db"], clean["leverage_db"], clean_db_active)
        clean_summaries = [summarize_return_period(frame, spec.annualization_days)
                           for frame in (clean_lse, clean_db)]
        common_rows.append({
            "year": int(year), "common_observations": len(group),
            "roll_mismatch_suspects": int(group["roll_mismatch_suspect"].sum()),
            "lse_trades": int(active_lse.sum()), "databento_trades": int(active_db.sum()),
            "lse_net_compound_return": summaries[0]["net_compound_return"],
            "lse_net_sharpe": summaries[0]["net_sharpe"],
            "databento_own_net_compound_return": summaries[1]["net_compound_return"],
            "databento_own_net_sharpe": summaries[1]["net_sharpe"],
            "databento_lse_controls_net_compound_return": summaries[2]["net_compound_return"],
            "databento_lse_controls_net_sharpe": summaries[2]["net_sharpe"],
            "total_return_gap_lse_minus_db_own": (
                summaries[0]["net_compound_return"] - summaries[1]["net_compound_return"]),
            "source_return_effect_lse_minus_db_lse_controls": (
                summaries[0]["net_compound_return"] - summaries[2]["net_compound_return"]),
            "db_signal_sizing_effect_own_minus_lse_controls": (
                summaries[1]["net_compound_return"] - summaries[2]["net_compound_return"]),
            "lse_net_compound_return_excluding_roll_mismatch": (
                clean_summaries[0]["net_compound_return"]),
            "databento_net_compound_return_excluding_roll_mismatch": (
                clean_summaries[1]["net_compound_return"]),
            "return_gap_excluding_roll_mismatch": (
                clean_summaries[0]["net_compound_return"] -
                clean_summaries[1]["net_compound_return"]),
        })
        gross_difference = group["gross_leg_return_lse"] - group["gross_leg_return_db"]
        diagnostic_rows.append({
            "year": int(year), "common_observations": len(group),
            "gross_leg_return_correlation": group["gross_leg_return_lse"].corr(
                group["gross_leg_return_db"]),
            "gross_leg_return_mae_bps": float(gross_difference.abs().mean() * 1e4),
            "gross_leg_return_exact_count": int(np.isclose(
                group["gross_leg_return_lse"], group["gross_leg_return_db"],
                rtol=0.0, atol=1e-12).sum()),
            "gate_disagreement_count": int((active_lse != active_db).sum()),
            "gate_disagreement_rate": float((active_lse != active_db).mean()),
            "leverage_mae": float((group["leverage_lse"] - group["leverage_db"]).abs().mean()),
            "entry_price_mae_points": float(
                (group["entry_price_lse"] - group["entry_price_db"]).abs().mean()),
            "exit_price_mae_points": float(
                (group["exit_price_lse"] - group["exit_price_db"]).abs().mean()),
        })
    common_yearly = pd.DataFrame(common_rows)
    common_diagnostics = pd.DataFrame(diagnostic_rows)
    roll_suspects = common.loc[common["roll_mismatch_suspect"], [
        "trade_date", "entry_price_lse", "exit_price_lse", "entry_price_db",
        "exit_price_db", "gross_leg_return_lse", "gross_leg_return_db",
        "gross_leg_return_difference_bps", "active_lse", "leverage_lse",
        "net_strategy_return_lse", "net_strategy_return_db"]].copy()

    db_dates = set(db["trade_date"])
    lse_dates = set(lse["trade_date"])
    union = pd.DataFrame({"trade_date": sorted(db_dates | lse_dates)})
    union["year"] = union["trade_date"].dt.year
    union["in_lse"] = union["trade_date"].isin(lse_dates)
    union["in_databento"] = union["trade_date"].isin(db_dates)
    coverage = union.groupby("year", as_index=False).agg(
        lse_observations=("in_lse", "sum"), databento_observations=("in_databento", "sum"))
    coverage["common_observations"] = union.loc[
        union["in_lse"] & union["in_databento"]].groupby("year").size().reindex(
            coverage["year"], fill_value=0).to_numpy()
    coverage["lse_only"] = coverage["lse_observations"] - coverage["common_observations"]
    coverage["databento_only"] = coverage["databento_observations"] - coverage["common_observations"]

    overall_frames = {
        "lse_own_history": lse,
        "databento_own_history": db,
        "lse_common_dates": frame_from_returns(
            common, common["lse_return_lse_controls"], common["leverage_lse"], lse_active),
        "databento_common_dates_own_controls": frame_from_returns(
            common, common["db_own_return"], common["leverage_db"], db_active),
        "databento_common_dates_lse_controls": frame_from_returns(
            common, common["db_return_lse_controls"], common["leverage_lse"], lse_active),
    }
    clean_common = common.loc[~common["roll_mismatch_suspect"]].copy()
    clean_lse_active = clean_common["active_lse"].astype(bool)
    clean_db_active = clean_common["active_db"].astype(bool)
    overall_frames["lse_common_dates_excluding_roll_mismatch"] = frame_from_returns(
        clean_common, clean_common["net_strategy_return_lse"],
        clean_common["leverage_lse"], clean_lse_active)
    overall_frames["databento_common_dates_excluding_roll_mismatch"] = frame_from_returns(
        clean_common, clean_common["net_strategy_return_db"],
        clean_common["leverage_db"], clean_db_active)
    overall = {name: summarize_return_period(frame, spec.annualization_days)
               for name, frame in overall_frames.items()}

    db.to_parquet(output / "databento_sma200_daily_returns.parquet", index=False)
    common.to_parquet(output / "common_date_reconciliation.parquet", index=False)
    side_by_side.to_csv(output / "yearly_side_by_side.csv", index=False)
    common_yearly.to_csv(output / "common_date_yearly_attribution.csv", index=False)
    common_diagnostics.to_csv(output / "common_date_diagnostics.csv", index=False)
    roll_suspects.to_csv(output / "roll_mismatch_suspects.csv", index=False)
    coverage.to_csv(output / "coverage_by_year.csv", index=False)
    (output / "summary.json").write_text(json.dumps(overall, indent=2, default=str), encoding="utf-8")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "config": config,
        "inputs": {name: file_sha256(path) for name, path in paths.items()},
        "code": {"runner_sha256": file_sha256(Path(__file__).resolve()),
                 "vol_target_sha256": file_sha256(PROJECT_ROOT / "backtest_engine" / "vol_target.py"),
                 "config_sha256": file_sha256(config_path)},
        "outputs": ["databento_sma200_daily_returns.parquet", "common_date_reconciliation.parquet",
                    "yearly_side_by_side.csv", "common_date_yearly_attribution.csv",
                    "common_date_diagnostics.csv", "roll_mismatch_suspects.csv",
                    "coverage_by_year.csv", "summary.json"],
        "databento_vol_target_quality": db_quality,
        "holdout": "consumed: diagnostic comparison of already-consumed histories",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    display = side_by_side.loc[side_by_side["year"].between(2017, 2026), [
        "year", "lse_sma200_net_compound_return", "databento_sma200_net_compound_return",
        "databento_old_unfiltered_net_compound_return",
        "sma200_return_difference_lse_minus_db"]].copy()
    for column in display.columns[1:]:
        display[column] *= 100
    print(display.to_string(index=False, float_format=lambda value: f"{value:.2f}%"))
    print("\nCommon-date diagnostics")
    print(common_diagnostics.to_string(index=False, float_format=lambda value: f"{value:.6f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
