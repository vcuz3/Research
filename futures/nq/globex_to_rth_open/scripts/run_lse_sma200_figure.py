"""Run the SMA200-gated, 10%-vol-targeted overnight leg on the LSE tiles."""
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
from strategy.lse import build_lse_sma_candidates, load_lse_minutes  # noqa: E402


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=PROJECT_ROOT / "experiments" / "configs" / "lse_sma200_vol_target.json")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def _apply_gate(sized: pd.DataFrame, gate: pd.Series) -> pd.DataFrame:
    result = sized.copy()
    result["active"] = gate.fillna(False).astype(bool)
    result["effective_leverage"] = result["leverage"].where(result["active"], 0.0)
    for column in ("gross_strategy_return", "net_strategy_return", "strategy_cost_return"):
        result[column] = result[column].where(result["active"], 0.0)
    return result


def _diagnostic_row(name: str, frame: pd.DataFrame, annualization: int) -> dict:
    result = summarize_return_period(frame, annualization)
    return {"diagnostic": name, **result}


def _gross_as_net(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["net_strategy_return"] = result["gross_strategy_return"]
    return result


def _fixed_one_x(sized: pd.DataFrame, gate: pd.Series) -> pd.DataFrame:
    result = sized.copy()
    result["leverage"] = 1.0
    result["gross_strategy_return"] = result["gross_leg_return"]
    result["net_strategy_return"] = result["net_leg_return"]
    result["strategy_cost_return"] = result["unlevered_cost_return"]
    return _apply_gate(result, gate)


def _close_to_close_vol_arm(sized: pd.DataFrame, spec: VolTargetSpec, gate: pd.Series) -> pd.DataFrame:
    result = sized.copy()
    daily_return = result["rth_close_return"]
    estimate = daily_return.shift(spec.lag_days).rolling(
        spec.lookback_days, min_periods=spec.lookback_days).std(ddof=1) * np.sqrt(
            spec.annualization_days)
    result["annualized_vol_estimate"] = estimate
    result["leverage_uncapped"] = spec.target_annual_vol / estimate
    result["leverage"] = result["leverage_uncapped"].clip(0.0, spec.leverage_cap)
    result["gross_strategy_return"] = result["leverage"] * result["gross_leg_return"]
    result["net_strategy_return"] = result["leverage"] * result["net_leg_return"]
    result["strategy_cost_return"] = result["leverage"] * result["unlevered_cost_return"]
    result = result.loc[result["leverage"].notna()].copy()
    return _apply_gate(result, gate.loc[result.index])


def main() -> int:
    args = parse_args()
    config_path = resolve(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    paths = [resolve(value) for value in config["lse_files"]]
    output = resolve(args.output or config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)

    minutes, source_quality, coverage = load_lse_minutes(paths)
    candidates, daily_features, candidate_quality = build_lse_sma_candidates(
        minutes, sma_days=config["sma_days"],
        max_feature_staleness_days=config["max_feature_staleness_days"])
    spec = VolTargetSpec(**config["vol_target"])
    sized, vol_quality = build_vol_targeted_leg(candidates, spec)
    sma_column = f"sma_{config['sma_days']}"
    post_warmup = sized.loc[sized["sma_available"]].copy()
    entry_gate = post_warmup["entry_price"] > post_warmup[sma_column]
    portfolio = _apply_gate(post_warmup, entry_gate)

    yearly = yearly_performance(portfolio, spec.annualization_days)
    overall = summarize_return_period(portfolio, spec.annualization_days)
    overall["annualized_compound_return"] = (
        (1.0 + overall["net_compound_return"]) **
        (spec.annualization_days / overall["observations"]) - 1.0)
    expected = config["expected_full_sample_sharpe"]
    overall["expected_sharpe"] = expected
    overall["sharpe_difference"] = overall["net_sharpe"] - expected
    overall["outside_tolerance"] = (
        abs(overall["sharpe_difference"]) > config["expected_sharpe_tolerance"])

    # Prespecified attribution arms. All use the same post-SMA warm-up sample.
    close_gate = post_warmup["sma_gate_close"].fillna(False)
    all_gate = pd.Series(True, index=post_warmup.index)
    diagnostic_frames = {
        "primary_entry_gate_net_zero_days": portfolio,
        "entry_gate_gross_zero_days": _gross_as_net(portfolio),
        "entry_gate_net_active_days_only": portfolio.loc[portfolio["active"]].copy(),
        "prior_rth_close_gate_net_zero_days": _apply_gate(post_warmup, close_gate),
        "no_sma_net_post200": _apply_gate(post_warmup, all_gate),
        "entry_gate_net_fixed_1x": _fixed_one_x(post_warmup, entry_gate),
    }
    cc_arm = _close_to_close_vol_arm(post_warmup, spec, entry_gate)
    diagnostic_frames["entry_gate_net_close_to_close_vol"] = cc_arm
    diagnostics = pd.DataFrame([
        _diagnostic_row(name, frame, spec.annualization_days)
        for name, frame in diagnostic_frames.items()])

    portfolio.to_parquet(output / "daily_returns.parquet", index=False)
    yearly.to_csv(output / "yearly_performance.csv", index=False)
    diagnostics.to_csv(output / "diagnostics.csv", index=False)
    daily_features.to_parquet(output / "daily_features.parquet", index=False)
    coverage.to_csv(output / "coverage_by_minute.csv", index=False)
    quality = {"source": source_quality, "candidates": candidate_quality,
               "vol_target": vol_quality}
    (output / "data_quality.json").write_text(
        json.dumps(quality, indent=2, default=str), encoding="utf-8")
    (output / "summary.json").write_text(
        json.dumps(overall, indent=2, default=str), encoding="utf-8")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "inputs": {str(path): file_sha256(path) for path in paths},
        "code": {
            "config_sha256": file_sha256(config_path),
            "runner_sha256": file_sha256(Path(__file__).resolve()),
            "lse_sha256": file_sha256(PROJECT_ROOT / "strategy" / "lse.py"),
            "vol_target_sha256": file_sha256(
                PROJECT_ROOT / "backtest_engine" / "vol_target.py"),
        },
        "outputs": ["daily_returns.parquet", "yearly_performance.csv", "diagnostics.csv",
                    "daily_features.parquet", "coverage_by_minute.csv",
                    "data_quality.json", "summary.json"],
        "holdout": "consumed: expected Sharpe 0.99 supplied before run",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    display = yearly[["year", "observations", "trades", "net_compound_return",
                      "annualized_net_vol", "net_sharpe", "max_drawdown",
                      "average_leverage"]].copy()
    for column in ("net_compound_return", "annualized_net_vol", "max_drawdown"):
        display[column] *= 100
    print(f"Wrote LSE SMA{config['sma_days']} reproduction to {output}")
    print(display.to_string(index=False, formatters={
        "net_compound_return": "{:.2f}%".format,
        "annualized_net_vol": "{:.2f}%".format,
        "net_sharpe": "{:.3f}".format,
        "max_drawdown": "{:.2f}%".format,
        "average_leverage": "{:.3f}x".format,
    }))
    print("\nFull-sample Sharpe:", round(overall["net_sharpe"], 4),
          "expected:", expected, "difference:", round(overall["sharpe_difference"], 4))
    print("\nDiagnostics")
    print(diagnostics[["diagnostic", "observations", "trades", "net_sharpe",
                       "annualized_net_vol", "max_drawdown"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

