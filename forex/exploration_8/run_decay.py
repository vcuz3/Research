"""Run the registered minute-level decay diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backtest_engine.decay import paired_minute_decay, summarize_decay
from data_loader import PAIR_PATHS, load_triangle_data
from strategy.triangle import build_triangle_features


ROOT = Path(__file__).resolve().parent


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    config_path = (ROOT / args.config).resolve()
    output = (ROOT / args.output_dir).resolve()
    if ROOT not in output.parents:
        raise ValueError("output directory must be inside the project")
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    triangle = load_triangle_data(
        ROOT,
        config["start"],
        config["end"],
        config["signal_timeframe_minutes"],
        include_minute_panel=True,
    )
    if triangle.minute_panel is None:
        raise AssertionError("minute panel was not loaded")
    features = build_triangle_features(
        triangle.panel,
        config["zscore_lookback_bars"],
        config["entry_z"],
        config["basis_mode"],
        config["signal_mode"],
    )
    signals = (
        features.loc[features.direction.ne(0), ["direction", "zscore"]]
        .rename_axis("decision_ts")
        .reset_index()
    )
    events, coverage = paired_minute_decay(
        triangle.minute_panel,
        signals,
        config["delays_minutes"],
        config["holding_minutes"],
        config["round_trip_cost_bps_per_leg"],
    )
    observed_days = pd.DatetimeIndex(triangle.minute_panel.index.floor("D").unique()).sort_values()
    summary, deterioration = summarize_decay(events, observed_days)

    events["year"] = pd.to_datetime(events.decision_ts).dt.year
    events["utc_hour"] = pd.to_datetime(events.decision_ts).dt.hour
    annual = (
        events.groupby(["delay_minutes", "year"], observed=True)
        .agg(
            signals=("residual_gross", "size"),
            residual_gross_mean_bps=("residual_gross", lambda x: x.mean() * 10_000),
            residual_net_mean_bps=("residual_net", lambda x: x.mean() * 10_000),
            audusd_gross_mean_bps=("audusd_gross", lambda x: x.mean() * 10_000),
            audusd_net_mean_bps=("audusd_net", lambda x: x.mean() * 10_000),
        )
        .reset_index()
    )
    hourly = (
        events.groupby(["delay_minutes", "utc_hour"], observed=True)
        .agg(
            signals=("residual_gross", "size"),
            residual_gross_mean_bps=("residual_gross", lambda x: x.mean() * 10_000),
            residual_net_mean_bps=("residual_net", lambda x: x.mean() * 10_000),
        )
        .reset_index()
    )
    clock = signals.assign(utc_hour=pd.to_datetime(signals.decision_ts).dt.hour).groupby("utc_hour").size().rename("signals").reset_index()

    data_root = ROOT.parent / "data"
    inputs = {}
    for pair, (relative, _) in PAIR_PATHS.items():
        path = data_root / relative
        inputs[pair] = {"path": str(path), "bytes": path.stat().st_size, "sha256": file_sha256(path)}
    manifest = {
        "run_id": "EXP-0001",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "candidate_signals": int(len(signals)),
        "paired_signals": int(coverage.paired_signals.iloc[0]),
        "aligned_signal_bars": int(len(triangle.panel)),
        "aligned_minute_rows": int(len(triangle.minute_panel)),
        "inputs": inputs,
        "known_limitations": [
            "Midpoint archives are not synchronized executable bid/ask quotes.",
            "Cost is an assumption, not measured from the source archives.",
            "Delay-zero and delay-30 endpoints were inspected before registration.",
        ],
    }

    events.to_csv(output / "events.csv", index=False)
    coverage.to_csv(output / "coverage.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    deterioration.to_csv(output / "paired_deterioration.csv", index=False)
    annual.to_csv(output / "annual.csv", index=False)
    hourly.to_csv(output / "hourly.csv", index=False)
    clock.to_csv(output / "signal_clock.csv", index=False)
    triangle.raw_quality.to_csv(output / "raw_quality.csv", index=False)
    triangle.bar_coverage.to_csv(output / "bar_coverage.csv", index=False)
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")

    residual = summary.loc[(summary.model == "residual") & (summary.accounting == "net")]
    five = residual.loc[residual.delay_minutes.eq(5)].iloc[0]
    gross = summary.loc[(summary.model == "residual") & (summary.accounting == "gross")].set_index("delay_minutes")
    retention = float(gross.loc[5, "mean_bps"] / gross.loc[0, "mean_bps"])
    verdict = "KILL" if five.mean_bps <= 0 or retention < 0.5 else "SURVIVES"
    report = (
        "# EXP-0001 minute-level decay\n\n"
        f"Paired signals: {manifest['paired_signals']:,} of {manifest['candidate_signals']:,}\n\n"
        f"Five-minute residual net: {five.mean_bps:.4f} bp; gross retention versus delay zero: {retention:.3f}.\n\n"
        f"Prespecified verdict: **{verdict}**.\n"
    )
    (output / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
