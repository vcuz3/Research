"""Reproduce the 10% annualized vol-targeted NQ overnight leg by year."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from backtest_engine.vol_target import (  # noqa: E402
    VolTargetSpec, build_vol_targeted_leg, summarize_return_period, yearly_performance,
)
from strategy.features import file_sha256  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=PROJECT_ROOT / "experiments" / "configs" / "figure_vol_target_10pct.json")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def main() -> int:
    args = parse_args()
    config_path = resolve(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    candidates_path = resolve(config["trade_candidates"])
    output = resolve(args.output or config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)

    candidates = pd.read_parquet(candidates_path)
    spec = VolTargetSpec(**config["vol_target"])
    daily, quality = build_vol_targeted_leg(candidates, spec)
    yearly = yearly_performance(daily, spec.annualization_days)
    overall = summarize_return_period(daily, spec.annualization_days)
    overall["annualized_compound_return"] = (
        (1.0 + overall["net_compound_return"]) ** (spec.annualization_days / len(daily)) - 1.0)

    daily.to_parquet(output / "daily_returns.parquet", index=False)
    yearly.to_csv(output / "yearly_performance.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps({"overall": overall, "quality": quality}, indent=2, default=str),
        encoding="utf-8")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": (
            "unfiltered leg; vol estimated from prior gross leg returns; all history consumed"),
        "config": config,
        "inputs": {"trade_candidates": {"path": str(candidates_path),
                                             "sha256": file_sha256(candidates_path)}},
        "code": {
            "config_sha256": file_sha256(config_path),
            "runner_sha256": file_sha256(Path(__file__).resolve()),
            "vol_target_sha256": file_sha256(
                PROJECT_ROOT / "backtest_engine" / "vol_target.py"),
        },
        "outputs": ["daily_returns.parquet", "yearly_performance.csv", "summary.json"],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    display = yearly[["year", "trades", "net_compound_return", "annualized_net_vol",
                      "net_sharpe", "max_drawdown", "average_leverage"]].copy()
    for column in ("net_compound_return", "annualized_net_vol", "max_drawdown"):
        display[column] = 100 * display[column]
    print(f"Wrote figure reproduction to {output}")
    print(display.to_string(index=False, formatters={
        "net_compound_return": "{:.2f}%".format,
        "annualized_net_vol": "{:.2f}%".format,
        "max_drawdown": "{:.2f}%".format,
        "net_sharpe": "{:.3f}".format,
        "average_leverage": "{:.3f}x".format,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

