"""Rule-9a coverage gate for HYP-0001; intentionally runs before any P&L."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..strategy.features import (
    DECISION_START,
    EXPECTED_5M_SLOTS,
    build_same_slot_features,
    load_canonical_rth_5m,
)


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[2]
DEFAULT_CONFIG = PROJECT / "experiments" / "configs" / "hyp_0001.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_declared_5m(path: Path) -> dict:
    frame = pd.read_parquet(path)
    dt = pd.to_datetime(frame["dt"])
    timezone = getattr(dt.dt, "tz", None)
    return {
        "path": path.as_posix(),
        "sha256": sha256(path),
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "timestamp_dtype": str(frame["dt"].dtype),
        "timezone": str(timezone) if timezone is not None else None,
        "timezone_aware": bool(timezone is not None),
        "first_timestamp": str(dt.min()),
        "last_timestamp": str(dt.max()),
        "duplicate_timestamps": int(dt.duplicated().sum()),
        "out_of_order_transitions": int((dt.diff().dropna() < pd.Timedelta(0)).sum()),
        "contract_pass": bool(timezone is not None),
        "contract_failure": None if timezone is not None else (
            "HYP-0001 declares this timestamp UTC, but the parquet column is timezone-naive."
        ),
    }


def assign_era(dates: pd.Series, eras: list[dict]) -> pd.Series:
    output = pd.Series("unassigned", index=dates.index, dtype="string")
    for era in eras:
        start, end = pd.Timestamp(era["start"]), pd.Timestamp(era["end"])
        output.loc[(dates >= start) & (dates <= end)] = era["name"]
    return output


def firing_cv(group: pd.DataFrame) -> float:
    rates = group.groupby("tod")["fired"].mean()
    mean = rates.mean()
    return float(rates.std(ddof=1) / mean) if mean > 0 and len(rates) > 1 else np.nan


def coverage_matched_firing_cv(group: pd.DataFrame) -> float:
    by_slot = group.groupby("tod").agg(fires=("fired", "sum"), eligible=("eligible", "sum"))
    by_slot = by_slot[by_slot["eligible"] > 0]
    rates = by_slot["fires"] / by_slot["eligible"]
    mean = rates.mean()
    return float(rates.std(ddof=1) / mean) if mean > 0 and len(rates) > 1 else np.nan


def markdown_report(result: dict, summary: pd.DataFrame) -> str:
    declared = result["declared_5m_audit"]
    canonical = result["canonical_5m_audit"]
    maxima = summary[["window", "required_sign_count", "max_same_sign_count", "eligible_decisions", "decision_rows"]]
    if result["gate_pass"]:
        outcome = [
            "The user-amended 40%-of-W same-sign floor is feasible on every preregistered window. The Rule-9a gate passes on the audited canonical one-minute archive resampled to five-minute RTH bars.",
            "",
            "The legacy five-minute file remains a data-contract warning because its timestamp is timezone-naive. It is not used for signals; the effective source is the timezone-aware archive already audited by `nq.noise_vwap`.",
        ]
    else:
        outcome = [
            "The amended feature gate remains infeasible in at least one preregistered window. Per the frozen build order, P&L remains blocked.",
        ]
    lines = [
        "# HYP-0001 Data Quality and Feature-Coverage Gate",
        "",
        f"- Experiment: `{result['experiment_id']}`",
        f"- Gate verdict: **{result['gate_verdict']}**",
        "- Scope: Rule-9a data and feature construction only; no prices, fills, or P&L were scored.",
        "",
        "## Outcome",
        "",
        *outcome,
        "",
        "## Declared data contract",
        "",
        f"- File: `{declared['path']}`",
        f"- Rows: {declared['rows']:,}; timestamps: {declared['first_timestamp']} to {declared['last_timestamp']}",
        f"- Timestamp dtype: `{declared['timestamp_dtype']}`; timezone-aware: `{declared['timezone_aware']}`",
        f"- Duplicate timestamps: {declared['duplicate_timestamps']}; out-of-order transitions: {declared['out_of_order_transitions']}",
        f"- Contract status: **{'PASS' if declared['contract_pass'] else 'FAIL'}** — {declared['contract_failure'] or 'none'}",
        "",
        "## Effective audited source",
        "",
        "Five-minute RTH bars are derived from the audited timezone-aware `NQ_1m_clean.parquet`, as recorded in the pre-run user amendment. The legacy file is audited above but never used for signals.",
        "",
        f"- Eligible sessions: {canonical['eligible_sessions']:,} ({canonical['eligible_start']} to {canonical['eligible_end']})",
        f"- Five-minute rows: {canonical['five_minute_rows']:,}; expected-slot misses: {canonical['five_minute_missing_expected_slots']}",
        f"- Bars/session: {canonical['five_minute_min_bars_per_session']} to {canonical['five_minute_max_bars_per_session']}",
        f"- Raw duplicate timestamps: {canonical['raw_duplicate_timestamps']}; raw out-of-order transitions: {canonical['raw_out_of_order_transitions']}",
        f"- One-minute within-session gap transitions: {canonical['rth_one_minute_gap_transitions']}",
        f"- RTH roll rows: {canonical['rth_roll_rows']}; multi-symbol RTH sessions: {canonical['rth_multi_symbol_sessions']}",
        "",
        "## Feature gate",
        "",
        "| W sessions | Required same-sign | Observed maximum | Eligible composite decisions | Coverage |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in maxima.itertuples(index=False):
        lines.append(
            f"| {row.window} | {row.required_sign_count} | {row.max_same_sign_count} | {row.eligible_decisions} | {row.eligible_decisions / row.decision_rows:.1%} |"
        )
    lines += [
        "",
        "The first six decision slots (10:00–10:25 ET) cannot populate the 60-minute RTH horizon and are therefore dropped and counted. The headline clock-placebo CV is coverage-matched: fires divided by eligible decisions for slots with eligible observations. The unconditional all-slot CV is retained as a diagnostic so this structural warm-up is not hidden.",
        "",
        "## Reproduction",
        "",
        f"`{result['run_command']}`",
        "",
        "Detailed evidence is in the immutable run directory: `data_audit.json`, `feature_summary.csv`, `sign_counts_by_window_horizon_era_slot.csv`, `decision_coverage_by_window_era_slot.csv`, and `bar_coverage_by_era_slot.csv`.",
        "",
    ]
    return "\n".join(lines)


def run(config_path: Path, experiment_id: str) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    artifact = PROJECT / "artifacts" / "runs" / experiment_id
    if not artifact.exists():
        raise FileNotFoundError(f"register {experiment_id} before running: {artifact}")
    declared_path = WORKSPACE / config["declared_5m_path"]
    declared = inspect_declared_5m(declared_path)
    bars, canonical = load_canonical_rth_5m(
        "NQ", config["minimum_1m_bars_per_session"]
    )
    canonical_path = WORKSPACE / config["canonical_1m_paths"]["NQ"]
    canonical["source_sha256"] = sha256(canonical_path)
    bars["era"] = assign_era(bars["date"], config["eras"])

    sessions_by_era = bars[["date", "era"]].drop_duplicates().groupby("era").size()
    bar_coverage_rows = []
    for (era, tod), group in bars.groupby(["era", "tod"], sort=True):
        bar_coverage_rows.append({
            "era": era,
            "tod": int(tod),
            "time_et": f"{int(tod)//60:02d}:{int(tod)%60:02d}",
            "observed_sessions": int(group["date"].nunique()),
            "era_sessions": int(sessions_by_era.loc[era]),
            "coverage_rate": float(group["date"].nunique() / sessions_by_era.loc[era]),
        })
    bar_coverage = pd.DataFrame(bar_coverage_rows)

    summaries, sign_rows, decision_rows = [], [], []
    horizons = tuple(config["momentum_horizons_minutes"])
    weights = tuple(config["horizon_weights"])
    q_entry = float(config["entry_threshold"])
    for window in config["rank_windows_sessions"]:
        features = build_same_slot_features(
            bars,
            int(window),
            float(config["same_sign_coverage_fraction"]),
            float(config["primary_vol_blend_alpha"]),
            horizons,
            weights,
        )
        features["era"] = assign_era(features["date"], config["eras"])
        features["eligible"] = features["long_eligible"] | features["short_eligible"]
        features["fired"] = (
            features["score_long"].ge(q_entry) | features["score_short"].ge(q_entry)
        )
        max_sign_count = 0
        for horizon in horizons:
            positive = features[f"positive_count_{horizon}m"]
            negative = features[f"negative_count_{horizon}m"]
            max_sign_count = max(max_sign_count, int(positive.max()), int(negative.max()))
            for (era, tod), group in features.groupby(["era", "tod"], sort=True):
                current = group[f"normalized_{horizon}m"]
                same_side = np.where(
                    current > 0,
                    group[f"positive_count_{horizon}m"],
                    np.where(current < 0, group[f"negative_count_{horizon}m"], np.nan),
                )
                finite = np.asarray(same_side, dtype=float)
                finite = finite[np.isfinite(finite)]
                sign_rows.append({
                    "window": int(window),
                    "required_sign_count": int(np.ceil(window * config["same_sign_coverage_fraction"])),
                    "horizon_minutes": int(horizon),
                    "era": era,
                    "tod": int(tod),
                    "time_et": f"{int(tod)//60:02d}:{int(tod)%60:02d}",
                    "decision_rows": int(len(group)),
                    "same_sign_count_p50": float(np.nanpercentile(finite, 50)) if len(finite) else np.nan,
                    "same_sign_count_p90": float(np.nanpercentile(finite, 90)) if len(finite) else np.nan,
                    "same_sign_count_max": int(np.nanmax(finite)) if len(finite) else 0,
                    "rank_available": int(group[f"rank_{horizon}m"].notna().sum()),
                })
        for (era, tod), group in features.groupby(["era", "tod"], sort=True):
            decision_rows.append({
                "window": int(window),
                "era": era,
                "tod": int(tod),
                "time_et": f"{int(tod)//60:02d}:{int(tod)%60:02d}",
                "decisions": int(len(group)),
                "long_eligible": int(group["long_eligible"].sum()),
                "short_eligible": int(group["short_eligible"].sum()),
                "any_eligible": int(group["eligible"].sum()),
                "fires": int(group["fired"].sum()),
                "fire_rate": float(group["fired"].mean()),
            })
        era_cvs = features.groupby("era", sort=True).apply(firing_cv, include_groups=False)
        matched_era_cvs = features.groupby("era", sort=True).apply(
            coverage_matched_firing_cv, include_groups=False
        )
        summaries.append({
            "window": int(window),
            "required_sign_count": int(np.ceil(window * config["same_sign_coverage_fraction"])),
            "max_same_sign_count": int(max_sign_count),
            "decision_rows": int(len(features)),
            "eligible_decisions": int(features["eligible"].sum()),
            "fired_decisions": int(features["fired"].sum()),
            "fire_rate": float(features["fired"].mean()),
            "era_firing_cv_finite_count": int(np.isfinite(era_cvs).sum()),
            "era_firing_cv_max": float(era_cvs.max()) if np.isfinite(era_cvs).any() else np.nan,
            "coverage_matched_era_firing_cv_max": (
                float(matched_era_cvs.max()) if np.isfinite(matched_era_cvs).any() else np.nan
            ),
        })

    feature_summary = pd.DataFrame(summaries)
    sign_counts = pd.DataFrame(sign_rows)
    decision_coverage = pd.DataFrame(decision_rows)
    canonical_pass = bool(
        canonical["source_timezone_aware"]
        and canonical["raw_duplicate_timestamps"] == 0
        and canonical["raw_out_of_order_transitions"] == 0
        and canonical["five_minute_duplicate_date_slots"] == 0
        and canonical["five_minute_out_of_order_transitions"] == 0
        and canonical["rth_multi_symbol_sessions"] == 0
    )
    gate_pass = bool(canonical_pass and feature_summary["eligible_decisions"].gt(0).all())
    run_command = (
        "python -m futures.nq.percentile_rank_momentum.validation.coverage_report "
        f"--experiment-id {experiment_id}"
    )
    result = {
        "experiment_id": experiment_id,
        "gate_verdict": "PASS" if gate_pass else "FAIL — STOP BEFORE P&L",
        "gate_pass": gate_pass,
        "declared_5m_audit": declared,
        "canonical_5m_audit": canonical,
        "decision_start_et": "10:00",
        "windows": list(config["rank_windows_sessions"]),
        "same_sign_coverage_fraction": config["same_sign_coverage_fraction"],
        "run_command": run_command,
        "pnl_run": False,
        "reason": (
            "Amended 40% same-sign coverage is feasible on the audited canonical resample."
            if gate_pass
            else "At least one data-integrity or amended feature-coverage condition failed."
        ),
    }
    (artifact / "data_audit.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    feature_summary.to_csv(artifact / "feature_summary.csv", index=False)
    sign_counts.to_csv(artifact / "sign_counts_by_window_horizon_era_slot.csv", index=False)
    decision_coverage.to_csv(artifact / "decision_coverage_by_window_era_slot.csv", index=False)
    bar_coverage.to_csv(artifact / "bar_coverage_by_era_slot.csv", index=False)
    report = markdown_report(result, feature_summary)
    (artifact / "DATA_QUALITY.md").write_text(report, encoding="utf-8")
    (PROJECT / "reports" / "DATA_QUALITY.md").write_text(report, encoding="utf-8")
    print(feature_summary.to_string(index=False))
    print(json.dumps({"gate_verdict": result["gate_verdict"], "reason": result["reason"]}, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--experiment-id", default="EXP-0001")
    args = parser.parse_args()
    run(args.config.resolve(), args.experiment_id)


if __name__ == "__main__":
    main()
