"""Run the registered New York rollover-blackout diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from backtest_engine.engine import build_event_returns, summarize_events
from data_loader import PAIR_PATHS, load_triangle_data
from strategy.triangle import apply_signal_blackout, build_triangle_features


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clock_table(features: pd.DataFrame, arm: str, timeframe: int) -> pd.DataFrame:
    index = features.index.tz_localize("UTC").tz_convert("America/New_York")
    ready = features["zscore"].notna()
    signal = features["direction"].ne(0)
    clock = pd.DataFrame(
        {
            "ny_hour": index.hour,
            "ny_minute": index.minute,
            "ready": ready.to_numpy(),
            "signal": signal.to_numpy(),
        }
    )
    result = (
        clock.groupby(["ny_hour", "ny_minute"], as_index=False)
        .agg(opportunities=("ready", "sum"), signals=("signal", "sum"))
    )
    result["signal_rate"] = result["signals"] / result["opportunities"]
    result.insert(0, "arm", arm)
    result.insert(0, "timeframe_minutes", timeframe)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path
    output = Path(args.output_dir)
    if not output.is_absolute():
        output = project_root / output
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    all_results: list[pd.DataFrame] = []
    all_events: list[pd.DataFrame] = []
    all_clocks: list[pd.DataFrame] = []
    signal_rows: list[dict[str, object]] = []
    quality_rows: list[pd.DataFrame] = []
    coverage_rows: list[pd.DataFrame] = []
    alignment_rows: list[pd.DataFrame] = []

    for timeframe_config in config["timeframes"]:
        timeframe = int(timeframe_config["minutes"])
        lookback = int(timeframe_config["zscore_lookback_bars"])
        triangle = load_triangle_data(
            project_root,
            config["start"],
            config["end"],
            timeframe,
        )
        panel = triangle.panel
        baseline = build_triangle_features(
            panel,
            zscore_lookback_bars=lookback,
            entry_z=float(config["entry_z"]),
            basis_mode=config["basis_mode"],
            signal_mode=config["signal_mode"],
        )
        blackout_features, blackout_mask = apply_signal_blackout(
            baseline,
            timezone=config["blackout"]["timezone"],
            start_time=config["blackout"]["start_time"],
            end_time=config["blackout"]["end_time"],
        )
        removed = baseline["direction"].ne(0) & blackout_mask

        for arm, features in (("baseline", baseline), ("blackout", blackout_features)):
            signal_rows.append(
                {
                    "timeframe_minutes": timeframe,
                    "lookback_bars": lookback,
                    "lookback_hours": timeframe * lookback / 60,
                    "arm": arm,
                    "ready_bars": int(features["zscore"].notna().sum()),
                    "signals": int(features["direction"].ne(0).sum()),
                    "signals_removed_by_blackout": int(removed.sum()) if arm == "blackout" else 0,
                }
            )
            all_clocks.append(_clock_table(features, arm, timeframe))
            for delay in config["entry_delay_bars"]:
                for horizon_minutes in config["horizon_minutes"]:
                    if horizon_minutes % timeframe:
                        raise ValueError(f"{horizon_minutes} is not divisible by {timeframe}")
                    horizon_bars = horizon_minutes // timeframe
                    events = build_event_returns(
                        panel,
                        features,
                        horizon_bars=horizon_bars,
                        timeframe_minutes=timeframe,
                        entry_delay_bars=int(delay),
                        round_trip_cost_bps_per_leg=float(config["round_trip_cost_bps_per_leg"]),
                        non_overlapping=bool(config["non_overlapping"]),
                    )
                    events.insert(0, "horizon_minutes", horizon_minutes)
                    events["entry_delay_bars"] = delay
                    events.insert(0, "arm", arm)
                    events.insert(0, "timeframe_minutes", timeframe)
                    all_events.append(events)
                    summary = summarize_events(events)
                    summary.insert(0, "horizon_minutes", horizon_minutes)
                    summary.insert(0, "entry_delay_bars", delay)
                    summary.insert(0, "arm", arm)
                    summary.insert(0, "timeframe_minutes", timeframe)
                    all_results.append(summary)

        quality = triangle.raw_quality.copy()
        quality.insert(0, "timeframe_minutes", timeframe)
        quality_rows.append(quality)
        coverage = triangle.bar_coverage.copy()
        coverage.insert(0, "timeframe_minutes", timeframe)
        coverage_rows.append(coverage)
        alignment = triangle.alignment.rename_axis("metric").reset_index(name="value")
        alignment.insert(0, "timeframe_minutes", timeframe)
        alignment_rows.append(alignment)

    results = pd.concat(all_results, ignore_index=True)
    events = pd.concat(all_events, ignore_index=True)
    signals = pd.DataFrame(signal_rows)
    clocks = pd.concat(all_clocks, ignore_index=True)
    events["year"] = pd.to_datetime(events["decision_ts"]).dt.year
    yearly = (
        events.groupby(
            ["timeframe_minutes", "arm", "entry_delay_bars", "horizon_minutes", "year"],
            as_index=False,
        )
        .agg(
            trades=("residual_gross", "size"),
            residual_gross_mean_bps=("residual_gross", lambda x: x.mean() * 10_000),
            residual_net_mean_bps=("residual_net", lambda x: x.mean() * 10_000),
            audusd_gross_mean_bps=("audusd_gross", lambda x: x.mean() * 10_000),
            audusd_net_mean_bps=("audusd_net", lambda x: x.mean() * 10_000),
        )
    )
    results.to_csv(output / "results.csv", index=False)
    events.to_csv(output / "events.csv", index=False)
    yearly.to_csv(output / "yearly_results.csv", index=False)
    signals.to_csv(output / "signal_summary.csv", index=False)
    clocks.to_csv(output / "signal_clock_ny.csv", index=False)
    pd.concat(quality_rows, ignore_index=True).to_csv(output / "raw_quality.csv", index=False)
    pd.concat(coverage_rows, ignore_index=True).to_csv(output / "bar_coverage.csv", index=False)
    pd.concat(alignment_rows, ignore_index=True).to_csv(output / "alignment.csv", index=False)

    data_root = project_root.parent / "data"
    fingerprints = {}
    for pair, (relative_path, _) in PAIR_PATHS.items():
        path = data_root / relative_path
        fingerprints[pair.upper()] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    manifest = {
        "config": config,
        "data_fingerprints": fingerprints,
        "result_rows": len(results),
        "event_rows": len(events),
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    comparison = results.loc[results["model"].isin(["residual_gross", "residual_net"])].copy()
    primary_yearly = yearly.loc[
        (yearly["timeframe_minutes"] == 15)
        & (yearly["entry_delay_bars"] == 1)
        & (yearly["horizon_minutes"] == 30)
    ]
    report = [
        "# New York rollover blackout diagnostic",
        "",
        f"Blackout: {config['blackout']['start_time']}--{config['blackout']['end_time']} "
        f"{config['blackout']['timezone']} (inclusive).",
        "",
        "The baseline and blackout arms rerun the complete non-overlap event engine; the blackout is not applied after trades are formed.",
        "",
        "## Signal counts",
        "",
        "```text",
        signals.to_string(index=False),
        "```",
        "",
        "## Residual results",
        "",
        "```text",
        comparison.to_string(index=False, float_format=lambda value: f"{value:.4f}"),
        "```",
        "",
        "## Primary result by year",
        "",
        "```text",
        primary_yearly.to_string(index=False, float_format=lambda value: f"{value:.4f}"),
        "```",
        "",
        "Midpoint returns do not establish executable triangular arbitrage; modeled costs are sensitivities rather than observed spreads.",
    ]
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
