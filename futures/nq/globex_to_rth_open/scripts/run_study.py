"""Run the NQ 18:00 ET to 09:30 ET baseline, filters, and sizing sweeps."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_engine.engine import CostModel, run_study  # noqa: E402
from strategy.features import (  # noqa: E402
    audit_nq_minutes, build_rth_daily, build_trade_candidates, file_sha256,
    load_nq_minutes, load_vix_daily,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=PROJECT_ROOT / "experiments" / "configs" / "study_v3.json")
    parser.add_argument("--output", type=Path, default=None,
                        help="Override the config output directory")
    return parser.parse_args()


def resolve_workspace_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def main() -> int:
    args = parse_args()
    config_path = args.config if args.config.is_absolute() else WORKSPACE_ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output = args.output or Path(config["output_dir"])
    output = output if output.is_absolute() else WORKSPACE_ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    nq_path = resolve_workspace_path(config["nq_data"])
    vix_path = resolve_workspace_path(config["vix_data"])
    ma_windows = config["ma_windows"]
    sizing = config["sizing"]

    nq = load_nq_minutes(nq_path)
    nq_quality, coverage_by_minute = audit_nq_minutes(nq)
    daily, daily_quality = build_rth_daily(
        nq, ma_windows, sizing["reference_lookback"], sizing["reference_min_obs"])
    vix, vix_quality = load_vix_daily(
        vix_path, sizing["reference_lookback"], sizing["reference_min_obs"])
    trades, trade_quality = build_trade_candidates(
        nq, daily, vix, ma_windows, config["max_feature_staleness_days"],
        sizing["reference_lookback"], sizing["reference_min_obs"])

    costs = CostModel(**config["costs"])
    summary = run_study(
        trades, ma_windows, config["vix_lower_bounds"], config["vix_upper_bounds"],
        config["sizing_modes"], costs, sizing["minimum_units"],
        sizing["maximum_units"], sizing["integer_contracts"])

    era_parts = []
    for era in config.get("eras", []):
        start = pd.Timestamp(era["start"])
        end = pd.Timestamp(era["end"])
        in_era = trades.loc[trades["trade_date"].between(start, end)].copy()
        part = run_study(
            in_era, ma_windows, config["vix_lower_bounds"], config["vix_upper_bounds"],
            config["sizing_modes"], costs, sizing["minimum_units"],
            sizing["maximum_units"], sizing["integer_contracts"])
        part.insert(0, "era", era["name"])
        era_parts.append(part)
    era_summary = pd.concat(era_parts, ignore_index=True) if era_parts else pd.DataFrame()

    summary.to_csv(output / "summary.csv", index=False)
    era_summary.to_csv(output / "era_summary.csv", index=False)
    trades.to_parquet(output / "trade_candidates.parquet", index=False)
    coverage_by_minute.to_csv(output / "coverage_by_minute.csv", index=False)
    quality = {"nq_minutes": nq_quality, "rth_daily": daily_quality,
               "vix_daily": vix_quality, "trade_construction": trade_quality}
    (output / "data_quality.json").write_text(
        json.dumps(quality, indent=2, default=str), encoding="utf-8")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "config": config,
        "inputs": {
            "nq": {"path": str(nq_path), "sha256": file_sha256(nq_path)},
            "vix": {"path": str(vix_path), "sha256": file_sha256(vix_path)},
        },
        "code": {
            "config_sha256": file_sha256(config_path),
            "runner_sha256": file_sha256(Path(__file__).resolve()),
            "features_sha256": file_sha256(PROJECT_ROOT / "strategy" / "features.py"),
            "engine_sha256": file_sha256(PROJECT_ROOT / "backtest_engine" / "engine.py"),
        },
        "outputs": ["summary.csv", "era_summary.csv", "trade_candidates.parquet",
                    "coverage_by_minute.csv", "data_quality.json"],
        "interpretation": "discovery sweep; historical data consumed; no sealed holdout",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    baseline = summary.loc[summary["family"].eq("baseline"), [
        "sizing", "trades", "mean_gross_points_per_contract", "mean_net_dollars",
        "mean_net_atr14_units", "net_sharpe", "net_hac5_t", "max_drawdown_dollars"]]
    print(f"Wrote study artifacts to {output}")
    print("\nBaseline by sizing mode")
    print(baseline.to_string(index=False))
    print("\nSweep rows:", len(summary), "candidate trades:", len(trades))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
