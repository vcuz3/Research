"""Run the frozen selective nulls and simultaneous deployment controls.

This entry point is intentionally separate from the economic backtest.  It
reconstructs the entire bounded discovery family on real data and on every
null draw, then evaluates the five prespecified deployment controls on one
identical NQ validation calendar.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ..backtest_engine.engine import run_fixed_schedule
from ..strategy.signals import (
    discovery_family_signals,
    fit_rate_matched_thresholds,
    opening_signals,
)
from ..validation.controls import simultaneous_stationary_control_gate
from ..validation.nulls import clopper_pearson_interval, empirical_pvalue
from ..validation.pipeline import null_draw, select_and_score
from .common import (
    MAIN_CONFIG,
    candidate_id_map,
    common_session_feature_frames,
    cost_profile,
    date_mask,
    independent_session_feature_frames,
    load_json,
    write_json,
)


FROZEN_PRIMARY_CANDIDATE_ID = "C004"
FROZEN_PRIMARY_CANDIDATE = "confirmed_gap"
CONTROL_COLUMNS = {
    "opposition": "mirror_gap_opposition",
    "selected_date_always_long": "selected_day_always_long",
    "opening_magnitude_deployable": "opening_magnitude_gate",
    "total_r1_magnitude_deployable": "total_r1_magnitude_gate",
    "min_component_deployable": "min_component_gate",
}
ECONOMIC_GATE_NAMES = {
    "net_sharpe_at_least_0_50",
    "era_a_net_mean_positive",
    "era_b_net_mean_positive",
    "two_tick_net_mean_positive",
    "ten_oh_one_net_mean_positive",
    "nq_long_gross_mean_positive",
    "nq_short_gross_mean_positive",
    "es_gross_mean_positive",
    "es_agreement_minus_opposition_positive",
}


def _selection_payload(result: object) -> dict[str, object]:
    return {
        "candidate_id": result.candidate_id,
        "candidate": result.candidate,
        "discovery_statistic": result.discovery_statistic,
        "discovery_trades": result.discovery_trades,
        "validation_statistic": result.validation_statistic,
        "validation_trades": result.validation_trades,
        "thresholds": result.thresholds.as_dict(),
    }


def _run_null_family(
    kind: str,
    *,
    sessions: pd.DataFrame,
    nq_features: pd.DataFrame,
    es_features: pd.DataFrame,
    discovery_mask: np.ndarray,
    validation_mask: np.ndarray,
    candidate_ids: dict[str, str],
    config: dict[str, object],
) -> tuple[pd.DataFrame, dict[str, object]]:
    draws = int(
        config[
            "conditional_permutation_null_draws"
            if kind == "conditional"
            else "circular_shift_null_draws"
        ]
    )
    rng = np.random.default_rng(int(config["random_seed"]))
    rows: list[dict[str, object]] = []
    selections: Counter[str] = Counter()
    for draw_number in range(1, draws + 1):
        result, donor = null_draw(
            kind,
            sessions,
            nq_features,
            es_features,
            discovery_mask,
            validation_mask,
            candidate_ids,
            rng,
            entry_column=str(config["entry_column"]),
            exit_column=str(config["exit_column"]),
            slippage_ticks_per_side=float(config["primary_cost"]["slippage_ticks_per_side"]),
            round_trip_fees_usd=float(config["primary_cost"]["round_trip_fees_usd"]),
            rolling_window=int(config["rolling_control_window"]),
            rolling_min_periods=int(config["rolling_control_min_periods"]),
        )
        if np.array_equal(donor, np.arange(len(donor))):
            raise AssertionError("identity null draw reached the validation runner")
        selections[result.candidate_id] += 1
        rows.append(
            {
                "draw": draw_number,
                "null": kind,
                "candidate_id": result.candidate_id,
                "candidate": result.candidate,
                "discovery_statistic": result.discovery_statistic,
                "discovery_trades": result.discovery_trades,
                "validation_statistic": result.validation_statistic,
                "validation_trades": result.validation_trades,
                "donor_fixed_points": int(np.sum(donor == np.arange(len(donor)))),
            }
        )
    table = pd.DataFrame(rows)
    values = table["validation_statistic"].to_numpy(dtype=float)
    if len(values) != draws or not np.isfinite(values).all():
        raise AssertionError("every frozen null draw must be present and finite")
    if float(np.std(values, ddof=1)) <= 0:
        raise AssertionError("frozen null distribution has zero variance")
    diagnostics = {
        "draws": draws,
        "invalid_draws": 0,
        "identity_draws": 0,
        "mean": float(np.mean(values)),
        "standard_deviation": float(np.std(values, ddof=1)),
        "median": float(np.median(values)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "candidate_selection_frequencies": {
            candidate_id: int(selections.get(candidate_id, 0))
            for candidate_id in sorted(candidate_ids.values())
        },
        "donor_invariants": {
            "same_paired_NQ_ES_donor_map": True,
            "gap_vector_multisets_preserved_within_frozen_strata": True,
            "conditional_year_side_counts_preserved": kind == "conditional",
            "nonidentity_required": True,
        },
    }
    return table, diagnostics


def _control_gate(
    config: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    sessions, features = independent_session_feature_frames(config)
    nq_sessions = sessions["NQ"]
    nq_features = features["NQ"]
    discovery = date_mask(nq_features, str(config["discovery_start"]), str(config["discovery_end"]))
    validation = date_mask(nq_features, str(config["validation_start"]), str(config["validation_b_end"]))
    base = opening_signals(nq_features)
    thresholds = fit_rate_matched_thresholds(
        nq_features.loc[discovery].reset_index(drop=True),
        base.loc[discovery, FROZEN_PRIMARY_CANDIDATE].reset_index(drop=True),
    )
    family = discovery_family_signals(nq_features, thresholds)
    signal_map = {
        FROZEN_PRIMARY_CANDIDATE: base[FROZEN_PRIMARY_CANDIDATE],
        **{
            output_name: (
                base[source_name] if source_name in base else family[source_name]
            )
            for output_name, source_name in CONTROL_COLUMNS.items()
        },
    }
    daily: dict[str, pd.DataFrame] = {}
    for name, side in signal_map.items():
        daily[name] = run_fixed_schedule(
            nq_sessions,
            side,
            instrument="NQ",
            entry_column=str(config["entry_column"]),
            exit_column=str(config["exit_column"]),
            decision_time_et=str(config["signal_available_time_et"]),
            entry_time_et=str(config["entry_order_active_time_et"]),
            exit_time_et=str(config["scheduled_exit_order_active_time_et"]),
            costs=cost_profile(config),
            strategy_name=name,
        )

    dates = pd.DatetimeIndex(pd.to_datetime(nq_sessions.loc[validation, "date"]))
    agreement = pd.Series(
        daily[FROZEN_PRIMARY_CANDIDATE].loc[validation, "net_dollars"].to_numpy(dtype=float),
        index=dates,
        name=FROZEN_PRIMARY_CANDIDATE,
    )
    controls = pd.DataFrame(
        {
            name: trades.loc[validation, "net_dollars"].to_numpy(dtype=float)
            for name, trades in daily.items()
            if name != FROZEN_PRIMARY_CANDIDATE
        },
        index=dates,
    )
    if tuple(controls.columns) != tuple(CONTROL_COLUMNS):
        raise AssertionError("runtime control family differs from frozen family")
    boundary = pd.Timestamp(str(config["validation_b_start"]))
    eras = pd.Series(np.where(dates < boundary, "A", "B"), index=dates, name="era")
    gate = simultaneous_stationary_control_gate(
        agreement,
        controls,
        eras,
        draws=int(config["stationary_bootstrap_draws"]),
        expected_block=float(config["stationary_bootstrap_expected_block"]),
        seed=int(config["random_seed"]),
    )
    daily_table = pd.concat(
        [agreement, controls, eras], axis=1
    ).reset_index(names="date")
    draw_table = pd.DataFrame(
        gate.bootstrap_differences,
        columns=gate.control_names,
    )
    draw_table.insert(0, "draw", np.arange(1, gate.draws + 1))
    result = {
        "draws": gate.draws,
        "expected_block": gate.expected_block,
        "seed": gate.seed,
        "critical_value_dollars": gate.critical_value,
        "minimum_lower_bound_dollars": float(np.min(gate.lower_bounds)),
        "passes": gate.passes,
        "thresholds": thresholds.as_dict(),
        "comparisons": gate.summary_frame().to_dict(orient="records"),
    }
    return daily_table, draw_table, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--economic-result", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    config = load_json(MAIN_CONFIG)
    economic = load_json(args.economic_result)
    economic_gates = economic.get("preliminary_economic_gates")
    economic_pass = economic.get("preliminary_pass")
    if not isinstance(economic_gates, dict) or not isinstance(economic_pass, bool):
        raise ValueError("economic result is missing the frozen gate payload")
    if set(economic_gates) != ECONOMIC_GATE_NAMES:
        raise ValueError("economic result gate family differs from the frozen hierarchy")
    if any(not isinstance(value, bool) for value in economic_gates.values()):
        raise ValueError("economic result gates must be explicit booleans")
    if economic_pass != all(value is True for value in economic_gates.values()):
        raise ValueError("economic result pass flag does not reconcile to its gates")
    if not economic_pass:
        write_json(
            args.output_dir / "validation_result.json",
            {
                "status": "REJECT",
                "reason": "one or more frozen primary economic/cost/era/side/ES gates failed",
                "economic_gates": economic_gates,
                "selective_nulls": "NOT_RUN_BY_FROZEN_HIERARCHY",
                "simultaneous_controls": "NOT_RUN_BY_FROZEN_HIERARCHY",
                "power_gate": "NOT_RUN_BY_FROZEN_HIERARCHY",
                "full_hypothesis_go": False,
            },
        )
        return

    sessions, features = common_session_feature_frames(config)
    discovery = date_mask(
        features["NQ"], str(config["discovery_start"]), str(config["discovery_end"])
    ).to_numpy()
    validation = date_mask(
        features["NQ"], str(config["validation_start"]), str(config["validation_b_end"])
    ).to_numpy()
    candidate_ids = candidate_id_map()
    observed = select_and_score(
        sessions["NQ"],
        features["NQ"],
        features["ES"],
        discovery,
        validation,
        candidate_ids,
        entry_column=str(config["entry_column"]),
        exit_column=str(config["exit_column"]),
        slippage_ticks_per_side=float(config["primary_cost"]["slippage_ticks_per_side"]),
        round_trip_fees_usd=float(config["primary_cost"]["round_trip_fees_usd"]),
    )
    observed_payload = _selection_payload(observed)
    if observed.candidate_id != FROZEN_PRIMARY_CANDIDATE_ID:
        write_json(
            args.output_dir / "validation_result.json",
            {
                "status": "INCONCLUSIVE",
                "reason": "real reconstructed discovery pipeline did not select frozen C004",
                "observed_selection": observed_payload,
                "historical_status": "globally consumed; selective inference is diagnostic",
            },
        )
        return

    null_tables: list[pd.DataFrame] = []
    null_results: dict[str, object] = {}
    try:
        for kind in ("conditional", "circular"):
            table, diagnostics = _run_null_family(
                kind,
                sessions=sessions["NQ"],
                nq_features=features["NQ"],
                es_features=features["ES"],
                discovery_mask=discovery,
                validation_mask=validation,
                candidate_ids=candidate_ids,
                config=config,
            )
            values = table["validation_statistic"].to_numpy(dtype=float)
            exceedances = int(np.sum(values >= observed.validation_statistic))
            p_value = empirical_pvalue(observed.validation_statistic, values)
            interval = clopper_pearson_interval(exceedances, len(values))
            diagnostics.update(
                {
                    "observed_statistic": observed.validation_statistic,
                    "exceedances": exceedances,
                    "p_value": p_value,
                    "clopper_pearson_exceedance_interval": list(interval),
                    "passes_0_05": p_value <= 0.05,
                }
            )
            null_results[kind] = diagnostics
            null_tables.append(table)

        control_daily, control_draws, control_result = _control_gate(config)
    except Exception as exc:
        write_json(
            args.output_dir / "validation_result.json",
            {
                "status": "INCONCLUSIVE",
                "reason": "selective-null or simultaneous-control machinery failure",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "observed_selection": observed_payload,
                "completed_null_components": null_results,
            },
        )
        raise
    pd.concat(null_tables, ignore_index=True).to_csv(
        args.output_dir / "selective_null_draws.csv.gz", index=False, compression="gzip"
    )
    control_daily.to_csv(args.output_dir / "control_validation_daily.csv.gz", index=False, compression="gzip")
    control_draws.to_csv(args.output_dir / "control_bootstrap_draws.csv.gz", index=False, compression="gzip")

    selective_pass = all(bool(null_results[kind]["passes_0_05"]) for kind in null_results)
    component_pass = selective_pass and bool(control_result["passes"])
    write_json(
        args.output_dir / "validation_result.json",
        {
            "status": "COMPONENT_PASS_PENDING_POWER" if component_pass else "REJECT",
            "historical_status": "globally consumed; selective inference is diagnostic",
            "observed_selection": observed_payload,
            "selective_nulls": null_results,
            "simultaneous_controls": control_result,
            "selective_null_gate_passes": selective_pass,
            "simultaneous_control_gate_passes": bool(control_result["passes"]),
            "power_gate": "PENDING_SEPARATE_REGISTERED_RUN",
            "full_hypothesis_go": False,
        },
    )


if __name__ == "__main__":
    main()
