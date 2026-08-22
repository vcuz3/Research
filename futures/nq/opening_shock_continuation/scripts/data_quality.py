"""Registered source, calendar, roll, and one-second execution audit."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ..backtest_engine.data import (
    CONDITION_PATH,
    DATA_PATHS,
    ONE_SECOND_PATHS,
    execution_sessions,
    file_sha256,
    one_second_execution,
    one_second_raw_quality,
    raw_quality,
    session_funnel,
    session_summary,
)
from ..backtest_engine.metrics import era_label
from ..strategy.signals import opening_feature_frame
from .common import MAIN_CONFIG, load_json, write_json


ACTIVATION_CLOCKS = {
    "entry_100000": "10:00:00",
    "entry_100001": "10:00:01",
    "entry_100002": "10:00:02",
    "entry_100005": "10:00:05",
    "entry_100030": "10:00:30",
    "entry_100100": "10:01:00",
    "entry_153000": "15:30:00",
    "entry_153001": "15:30:01",
    "exit_155958": "15:59:58",
    "exit_155959": "15:59:59",
    "exit_160000": "16:00:00",
}

ROLLING_NORMALIZERS = (
    "magnitude_rel",
    "gap_magnitude_rel",
    "total_r1_magnitude_rel",
    "min_component_rel",
    "rv_rel",
    "volume_rel",
    "efficiency_rel",
    "clv_rel",
)


def _delay_seconds(frame: pd.DataFrame, label: str, clock: str) -> pd.Series:
    timestamp = pd.to_datetime(frame[f"{label}_ts"], utc=True).dt.tz_convert("America/New_York")
    activation = pd.to_datetime(frame["date"].dt.strftime("%Y-%m-%d") + f" {clock}").dt.tz_localize(
        "America/New_York"
    )
    return (timestamp - activation).dt.total_seconds()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = load_json(MAIN_CONFIG)

    report: dict[str, object] = {"instruments": {}, "fingerprints": {}}
    executions: dict[str, pd.DataFrame] = {}
    timing_rows = []
    coverage_rows = []
    session_qa_rows = []
    for instrument in ("NQ", "ES"):
        quality = raw_quality(instrument)
        second_quality = one_second_raw_quality(instrument)
        funnel = session_funnel(instrument)
        summary = session_summary(instrument)
        summary_audit = summary.copy()
        summary_audit.insert(0, "era", era_label(summary_audit["date"]).to_numpy())
        session_qa_columns = (
            "instrument",
            "date",
            "era",
            "condition",
            "n_bars",
            "n_unique_bars",
            "first_tod",
            "last_tod",
            "max_gap_seconds",
            "rth_roll_rows",
            "n_rth_symbols",
            "n_opening_bars",
            "n_unique_opening_bars",
            "first_opening_tod",
            "last_opening_tod",
            "max_opening_gap_seconds",
            "n_opening_symbols",
            "expected_session",
            "scheduled_full_session",
            "prev_expected_date",
            "prior_calendar_contiguous",
            "prev_endpoint_present",
            "available",
            "prev_available",
            "prev_symbol",
            "sym0930",
            "sym0959",
            "sym1000",
            "sym1530",
            "sym1559",
            "opening_same_contract",
            "same_contract",
            "complete",
            "causal_opening_complete",
            "causal_candidate",
            "causal_measurement_available",
            "eligible",
        )
        missing_audit_columns = sorted(set(session_qa_columns) - set(summary_audit.columns))
        if missing_audit_columns:
            raise AssertionError(f"session QA schema missing columns: {missing_audit_columns}")
        session_qa_rows.append(summary_audit.loc[:, session_qa_columns])
        one_second = one_second_execution(instrument)
        execution = execution_sessions(instrument)
        strict_execution = execution_sessions(instrument, strict_full_session=True)
        executions[instrument] = execution
        opening_features = opening_feature_frame(
            execution,
            rolling_window=int(config["rolling_control_window"]),
            rolling_min_periods=int(config["rolling_control_min_periods"]),
        )
        feature_eras = era_label(opening_features["date"])
        for era in (
            "discovery_2011_2018",
            "validation_2019_2022",
            "validation_b_2023_2026",
        ):
            era_mask = feature_eras.eq(era)
            row: dict[str, object] = {
                "instrument": instrument,
                "era": era,
                "eligible_sessions": int(era_mask.sum()),
            }
            finite_all = np.ones(int(era_mask.sum()), dtype=bool)
            for column in ROLLING_NORMALIZERS:
                values = pd.to_numeric(opening_features.loc[era_mask, column], errors="coerce").to_numpy(dtype=float)
                finite = np.isfinite(values)
                finite_all &= finite
                row[f"{column}_finite"] = int(finite.sum())
                row[f"{column}_nan_gate_fail"] = int((~finite).sum())
            row["all_eight_normalizers_finite"] = int(finite_all.sum())
            row["any_normalizer_nan_gate_fail"] = int((~finite_all).sum())
            coverage_rows.append(row)
        boundary_equal = int((execution["c0959"] == execution["o1000"]).sum())
        entry_contained = execution["entry_100001"].between(execution["l1000"], execution["h1000"])
        exit_contained = execution["exit_155959"].between(execution["l1559"], execution["h1559"])
        exit_et = pd.to_datetime(execution["exit_155959_ts"], utc=True).dt.tz_convert("America/New_York")
        exit_before_close = exit_et.dt.time < pd.Timestamp("16:00:00").time()
        instrument_timing = {}
        timing_eras = era_label(one_second["date"])
        for label, clock in ACTIVATION_CLOCKS.items():
            delays = _delay_seconds(one_second, label, clock)
            for era in (
                "all",
                "discovery_2011_2018",
                "validation_2019_2022",
                "validation_b_2023_2026",
            ):
                era_mask = np.ones(len(one_second), dtype=bool) if era == "all" else timing_eras.eq(era).to_numpy()
                era_delays = delays.loc[era_mask]
                present = era_delays.dropna()
                row = {
                    "instrument": instrument,
                    "activation": label,
                    "era": era,
                    "candidate_sessions": int(era_mask.sum()),
                    "sessions": int(present.size),
                    "missing_sessions": int(era_delays.isna().sum()),
                    "min_delay_seconds": float(present.min()) if not present.empty else None,
                    "median_delay_seconds": float(present.median()) if not present.empty else None,
                    "max_delay_seconds": float(present.max()) if not present.empty else None,
                }
                timing_rows.append(row)
                if era == "all":
                    instrument_timing[label] = row
            if (delays.dropna() < 0).any():
                raise AssertionError(f"{instrument} {label} contains pre-activation fill")
        report["instruments"][instrument] = {
            "raw_quality": quality,
            "one_second_raw_quality": second_quality,
            "session_funnel": funnel,
            "one_second_rows": int(len(one_second)),
            "execution_eligible_sessions": int(len(execution)),
            "strict_390_execution_sessions": int(len(strict_execution)),
            "causal_candidates": int(summary["causal_candidate"].sum()),
            "causal_measurement_available": int(summary["causal_measurement_available"].sum()),
            "known_early_close_exclusions": int((summary["expected_session"] & ~summary["scheduled_full_session"]).sum()),
            "condition_exclusions_after_causal_gate": int((summary["causal_candidate"] & ~(summary["available"] & summary["prev_available"])).sum()),
            "c0959_equals_o1000_sessions": boundary_equal,
            "c0959_equals_o1000_fraction": float(boundary_equal / len(execution)),
            "timing": instrument_timing,
            "primary_entry_inside_1000_minute_range": int(entry_contained.sum()),
            "primary_exit_inside_1559_minute_range": int(exit_contained.sum()),
            "primary_exit_strictly_before_1600": int(exit_before_close.sum()),
        }
        for invariant in (
            "null_rows",
            "nonpositive_price_rows",
            "invalid_ohlc_rows",
            "nonpositive_volume_rows",
            "out_of_order_or_duplicate_rows",
        ):
            if int(quality[invariant]) != 0:
                raise AssertionError(f"{instrument} source invariant failed: {invariant}")
            if int(second_quality[invariant]) != 0:
                raise AssertionError(f"{instrument} one-second invariant failed: {invariant}")
        if not entry_contained.all() or not exit_contained.all() or not exit_before_close.all():
            raise AssertionError(f"{instrument} one-second/one-minute containment or exit-window failure")

    common_dates = sorted(set(executions["NQ"]["date"]) & set(executions["ES"]["date"]))
    report["common_execution_sessions"] = int(len(common_dates))
    report["common_first_date"] = common_dates[0]
    report["common_last_date"] = common_dates[-1]
    report["fingerprints"] = {
        "condition_calendar": file_sha256(CONDITION_PATH),
        **{f"{name}_1m": file_sha256(path) for name, path in DATA_PATHS.items()},
        **{f"{name}_1s": file_sha256(path) for name, path in ONE_SECOND_PATHS.items()},
    }

    pd.DataFrame(timing_rows).to_csv(args.output_dir / "execution_timing.csv", index=False)
    pd.concat(session_qa_rows, ignore_index=True).to_csv(
        args.output_dir / "session_quality_by_date.csv.gz",
        index=False,
        compression="gzip",
    )
    pd.DataFrame(
        [{"instrument": name, **report["instruments"][name]["session_funnel"]} for name in ("NQ", "ES")]
    ).to_csv(args.output_dir / "session_funnel.csv", index=False)
    pd.DataFrame(coverage_rows).to_csv(args.output_dir / "feature_coverage.csv", index=False)
    report["rolling_feature_coverage"] = coverage_rows
    report["rolling_feature_window"] = int(config["rolling_control_window"])
    report["rolling_feature_min_periods"] = int(config["rolling_control_min_periods"])
    report["rolling_nan_policy"] = "every nonfinite normalized candidate gate fails; no row is silently dropped"
    write_json(args.output_dir / "data_quality.json", report)


if __name__ == "__main__":
    main()
