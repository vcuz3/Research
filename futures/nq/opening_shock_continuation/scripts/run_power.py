"""Run the frozen complete-pipeline power gate for HYP-0002.

The registered entry point requires the prior economic and validation artifacts
so the frozen rejection hierarchy is enforced before any data are loaded. All
draw counts, thresholds, costs, dates, and RNG streams come from the frozen
configuration. Pure helpers accept already-loaded frames so the orchestration
can be exercised on synthetic data without touching historical files.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from ..backtest_engine.data import INSTRUMENT_SPECS
from ..backtest_engine.engine import run_fixed_schedule
from ..strategy.signals import opening_feature_frame, opening_signals
from ..validation.nulls import clopper_pearson_interval, empirical_pvalue
from ..validation.pipeline import SelectionResult, candidate_net_pnl, null_draw, select_and_score
from ..validation.power import (
    InjectionSolution,
    apply_paired_donor_map,
    demean_paired_outcomes,
    minimum_detectable_effect,
    paired_stationary_bootstrap_donor_map,
    solve_side_aligned_injection,
)
from .common import (
    MAIN_CONFIG,
    candidate_id_map,
    common_session_feature_frames,
    cost_profile,
    independent_session_feature_frames,
    load_json,
    write_json,
)


FROZEN_PRIMARY_CANDIDATE_ID = "C004"
FROZEN_PRIMARY_CANDIDATE = "confirmed_gap"
NULL_KINDS = ("conditional", "circular")
FROZEN_ECONOMIC_GATE_NAMES = {
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
FROZEN_POWER_CONTRACT = {
    "conditional_permutation_null_draws": 4_999,
    "circular_shift_null_draws": 4_999,
    "power_outer_draws": 200,
    "power_inner_null_draws": 499,
    "power_required_rejections": 160,
    "positive_control_target_zero_filled_net_sharpe": 0.50,
    "power_full_conditional_seed": 20_260_821,
    "power_full_circular_seed": 20_260_822,
    "power_outer_seed": 20_260_823,
}
FROZEN_SEED_DERIVATION = (
    "numpy.random.SeedSequence([power_outer_seed, one_based_trial_number, stream_id])"
)
FROZEN_STREAM_IDS = {"donor": 0, "conditional": 1, "circular": 2}


@dataclass(frozen=True)
class PreparedPowerTemplate:
    records: pd.DataFrame
    eras: pd.Series
    injection: InjectionSolution
    raw_audit: dict[str, object]


@dataclass(frozen=True)
class MaterializedPowerSample:
    sessions: pd.DataFrame
    nq_features: pd.DataFrame
    es_features: pd.DataFrame
    eras: pd.Series
    source_dates: pd.Series

    @property
    def discovery_mask(self) -> np.ndarray:
        return self.eras.eq("discovery").to_numpy(dtype=bool)

    @property
    def validation_mask(self) -> np.ndarray:
        return self.eras.isin(["A", "B"]).to_numpy(dtype=bool)


def _validate_registered_config(config: dict[str, Any]) -> None:
    """Reject drift in any registered power count, seed, or stream rule."""

    for key, expected in FROZEN_POWER_CONTRACT.items():
        if key not in config or config[key] != expected:
            raise ValueError(
                f"registered power config drift for {key}: {config.get(key)!r} != {expected!r}"
            )
    if config.get("power_trial_seed_derivation") != FROZEN_SEED_DERIVATION:
        raise ValueError("registered power trial seed derivation has drifted")
    if config.get("power_trial_stream_ids") != FROZEN_STREAM_IDS:
        raise ValueError("registered power trial stream IDs have drifted")
    if config.get("primary_instrument") != "NQ" or config.get("sibling_instrument") != "ES":
        raise ValueError("registered power instruments must remain NQ/ES")
    if config.get("family_selection_statistic") != "primary_cost_zero_day_daily_sharpe":
        raise ValueError("registered discovery statistic has drifted")
    if (
        config.get("selective_null_statistic")
        != "combined_2019_2026_NQ_primary_cost_zero_filled_daily_sharpe"
    ):
        raise ValueError("registered validation statistic has drifted")


def _upstream_gate_decision(
    economic_result: dict[str, Any], validation_result: dict[str, Any]
) -> dict[str, object]:
    """Validate and apply the frozen economic -> components -> power hierarchy."""

    economic_gates = economic_result.get("preliminary_economic_gates")
    economic_pass = economic_result.get("preliminary_pass")
    if not isinstance(economic_gates, dict) or not isinstance(economic_pass, bool):
        raise ValueError("economic result is missing the frozen gate payload")
    if set(economic_gates) != FROZEN_ECONOMIC_GATE_NAMES:
        raise ValueError("economic result gate family differs from the frozen hierarchy")
    if any(not isinstance(value, bool) for value in economic_gates.values()):
        raise ValueError("economic result gates must be explicit booleans")
    reconciled_economic_pass = all(value is True for value in economic_gates.values())
    if economic_pass != reconciled_economic_pass:
        raise ValueError("economic result pass flag does not reconcile to its gates")
    if not economic_pass:
        return {
            "proceed": False,
            "status": "REJECT",
            "reason": "one or more frozen primary economic/cost/era/side/ES gates failed",
            "economic_gates": economic_gates,
            "validation_components": "NOT_CONSUMED_AFTER_ECONOMIC_REJECTION",
        }

    validation_status = validation_result.get("status")
    if validation_status == "REJECT":
        return {
            "proceed": False,
            "status": "REJECT",
            "reason": "one or more frozen selective-null or simultaneous-control gates failed",
            "economic_gates": economic_gates,
            "validation_status": validation_status,
            "selective_null_gate_passes": validation_result.get(
                "selective_null_gate_passes"
            ),
            "simultaneous_control_gate_passes": validation_result.get(
                "simultaneous_control_gate_passes"
            ),
        }
    if validation_status == "INCONCLUSIVE":
        return {
            "proceed": False,
            "status": "INCONCLUSIVE",
            "reason": "upstream validation machinery was inconclusive",
            "economic_gates": economic_gates,
            "validation_status": validation_status,
        }
    if validation_status != "COMPONENT_PASS_PENDING_POWER":
        raise ValueError("validation result has no recognized frozen hierarchy status")

    selective_flag = validation_result.get("selective_null_gate_passes")
    control_flag = validation_result.get("simultaneous_control_gate_passes")
    if not isinstance(selective_flag, bool) or not isinstance(control_flag, bool):
        raise ValueError("validation component flags must be explicit booleans")
    nulls = validation_result.get("selective_nulls")
    controls = validation_result.get("simultaneous_controls")
    if not isinstance(nulls, dict) or set(nulls) != set(NULL_KINDS):
        raise ValueError("validation result must contain exactly both frozen null families")
    nested_null_passes: list[bool] = []
    for kind in NULL_KINDS:
        payload = nulls[kind]
        if not isinstance(payload, dict) or not isinstance(payload.get("passes_0_05"), bool):
            raise ValueError(f"validation {kind} null is missing an explicit pass flag")
        nested_null_passes.append(payload["passes_0_05"])
    if not isinstance(controls, dict) or not isinstance(controls.get("passes"), bool):
        raise ValueError("validation controls are missing an explicit pass flag")
    if selective_flag != all(nested_null_passes):
        raise ValueError("validation selective-null summary does not reconcile")
    if control_flag != controls["passes"]:
        raise ValueError("validation simultaneous-control summary does not reconcile")
    if not selective_flag or not control_flag:
        return {
            "proceed": False,
            "status": "REJECT",
            "reason": "one or more frozen selective-null or simultaneous-control gates failed",
            "economic_gates": economic_gates,
            "validation_status": validation_status,
            "selective_null_gate_passes": selective_flag,
            "simultaneous_control_gate_passes": control_flag,
        }
    if validation_result.get("power_gate") != "PENDING_SEPARATE_REGISTERED_RUN":
        raise ValueError("validation result is not awaiting the registered power gate")
    if validation_result.get("full_hypothesis_go") is not False:
        raise ValueError("validation result prematurely claims full hypothesis GO")
    return {
        "proceed": True,
        "status": "COMPONENT_PASS_PENDING_POWER",
        "economic_gates": economic_gates,
        "selective_null_gate_passes": True,
        "simultaneous_control_gate_passes": True,
    }


def _chronological_dates(frame: pd.DataFrame, *, name: str) -> pd.DatetimeIndex:
    if "date" not in frame:
        raise ValueError(f"{name} is missing date")
    dates = pd.DatetimeIndex(pd.to_datetime(frame["date"], errors="coerce"), name="date")
    if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError(f"{name} dates must be finite, unique, and chronological")
    return dates


def _power_eras(dates: pd.DatetimeIndex, config: dict[str, Any]) -> pd.Series:
    """Assign every in-scope target date to exactly one frozen power era."""

    definitions = (
        ("discovery", config["discovery_start"], config["discovery_end"]),
        ("A", config["validation_start"], config["validation_end"]),
        ("B", config["validation_b_start"], config["validation_b_end"]),
    )
    labels = np.full(len(dates), "", dtype=object)
    assigned = np.zeros(len(dates), dtype=int)
    for label, start, end in definitions:
        mask = (dates >= pd.Timestamp(str(start))) & (dates <= pd.Timestamp(str(end)))
        labels[mask] = label
        assigned += mask.astype(int)
    if not np.equal(assigned, 1).all():
        raise ValueError("every power date must belong to exactly one of discovery/A/B")
    result = pd.Series(labels, index=dates, name="era", dtype="string")
    if set(result.astype(str)) != {"discovery", "A", "B"}:
        raise ValueError("power panel must contain nonempty discovery, A, and B eras")
    return result


def _scope_common_sessions(
    sessions: dict[str, pd.DataFrame], config: dict[str, Any]
) -> tuple[dict[str, pd.DataFrame], pd.Series]:
    if set(sessions) != {"NQ", "ES"}:
        raise ValueError("power requires exactly the common NQ and ES session panels")
    nq_dates = _chronological_dates(sessions["NQ"], name="NQ common sessions")
    es_dates = _chronological_dates(sessions["ES"], name="ES common sessions")
    if not nq_dates.equals(es_dates):
        raise ValueError("power requires identical common NQ/ES dates")
    start = pd.Timestamp(str(config["discovery_start"]))
    end = pd.Timestamp(str(config["validation_b_end"]))
    keep = (nq_dates >= start) & (nq_dates <= end)
    if not keep.any():
        raise ValueError("registered power date scope is empty")
    scoped = {
        instrument: frame.loc[keep].reset_index(drop=True).copy()
        for instrument, frame in sessions.items()
    }
    dates = _chronological_dates(scoped["NQ"], name="scoped common sessions")
    if dates[0] != start or dates[-1] != end:
        raise ValueError("common power panel does not span the exact frozen endpoints")
    if not dates.equals(_chronological_dates(scoped["ES"], name="scoped ES sessions")):
        raise AssertionError("scoping changed paired NQ/ES alignment")
    return scoped, _power_eras(dates, config)


def _audit_actual_execution_panels(
    sessions: dict[str, pd.DataFrame], config: dict[str, Any]
) -> dict[str, object]:
    """Verify all source endpoints and contract chains before outcomes are altered."""

    audit: dict[str, object] = {}
    for instrument in ("NQ", "ES"):
        frame = sessions[instrument]
        all_rows = pd.Series(np.ones(len(frame), dtype=np.int8), index=frame.index)
        checked = run_fixed_schedule(
            frame,
            all_rows,
            instrument=instrument,
            entry_column=str(config["entry_column"]),
            exit_column=str(config["exit_column"]),
            decision_time_et=str(config["signal_available_time_et"]),
            entry_time_et=str(config["entry_order_active_time_et"]),
            exit_time_et=str(config["scheduled_exit_order_active_time_et"]),
            costs=cost_profile(config),
            strategy_name="power_source_endpoint_audit",
        )
        if not checked["trade"].all() or len(checked) != len(frame):
            raise AssertionError("source endpoint audit did not check every paired record")
        audit[instrument] = {
            "sessions": int(len(frame)),
            "first_date": pd.Timestamp(frame["date"].iloc[0]),
            "last_date": pd.Timestamp(frame["date"].iloc[-1]),
            "maximum_entry_latency_seconds": float(checked["entry_latency_seconds"].max()),
            "maximum_exit_latency_seconds": float(checked["exit_latency_seconds"].max()),
            "all_feature_and_fill_symbols_same_contract": True,
            "decision_entry_exit_clocks_causal": True,
        }
    return audit


def _prefixed_session_frame(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    dates = _chronological_dates(frame, name=f"{prefix} session panel")
    values = frame.drop(columns="date").copy()
    values.index = dates
    return values.add_prefix(f"{prefix}__")


def _prepare_power_template(
    common_sessions: dict[str, pd.DataFrame], config: dict[str, Any]
) -> PreparedPowerTemplate:
    """Demean paired raw outcomes and solve the single frozen NQ injection."""

    sessions, eras = _scope_common_sessions(common_sessions, config)
    raw_audit = _audit_actual_execution_panels(sessions, config)
    rolling = {
        "rolling_window": int(config["rolling_control_window"]),
        "rolling_min_periods": int(config["rolling_control_min_periods"]),
    }
    features = {
        instrument: opening_feature_frame(frame, **rolling)
        for instrument, frame in sessions.items()
    }
    dates = eras.index
    entry_column = str(config["entry_column"])
    exit_column = str(config["exit_column"])
    unsigned: dict[str, pd.Series] = {}
    opening_side: dict[str, pd.Series] = {}
    for instrument in ("NQ", "ES"):
        move = (
            pd.to_numeric(sessions[instrument][exit_column], errors="coerce")
            - pd.to_numeric(sessions[instrument][entry_column], errors="coerce")
        )
        unsigned[instrument] = pd.Series(move.to_numpy(dtype=float), index=dates)
        opening_side[instrument] = pd.Series(
            features[instrument]["opening_sign"].to_numpy(dtype=np.int8), index=dates
        )
    demeaned = demean_paired_outcomes(
        unsigned["NQ"], unsigned["ES"], opening_side["NQ"], opening_side["ES"]
    )
    injection_side = pd.Series(
        opening_signals(features["NQ"])[FROZEN_PRIMARY_CANDIDATE].to_numpy(dtype=np.int8),
        index=dates,
        name="injection_side",
    )
    nq_spec = INSTRUMENT_SPECS["NQ"]
    round_trip_cost = (
        2.0
        * float(config["primary_cost"]["slippage_ticks_per_side"])
        * nq_spec.tick_size
        * nq_spec.multiplier
        + float(config["primary_cost"]["round_trip_fees_usd"])
    )
    injection = solve_side_aligned_injection(
        demeaned["nq_demeaned_points"],
        injection_side,
        eras,
        point_value_dollars=nq_spec.multiplier,
        round_trip_cost_dollars=round_trip_cost,
        target_validation_sharpe=float(
            config["positive_control_target_zero_filled_net_sharpe"]
        ),
    )
    records = pd.concat(
        [
            _prefixed_session_frame(sessions["NQ"], "nq"),
            _prefixed_session_frame(sessions["ES"], "es"),
        ],
        axis=1,
    )
    records["source_date"] = dates
    records["era"] = eras.to_numpy(dtype=str)
    records["nq_unsigned_points"] = unsigned["NQ"].to_numpy()
    records["es_unsigned_points"] = unsigned["ES"].to_numpy()
    records["nq_demeaned_points"] = demeaned["nq_demeaned_points"].to_numpy()
    records["es_demeaned_points"] = demeaned["es_demeaned_points"].to_numpy()
    records["nq_injected_points"] = injection.injected_unsigned_points.to_numpy()
    records["injection_side"] = injection_side.to_numpy()
    records["nq_opening_side"] = opening_side["NQ"].to_numpy()
    records["es_opening_side"] = opening_side["ES"].to_numpy()
    if not records.index.equals(dates) or records.isna().all(axis=1).any():
        raise AssertionError("prepared paired records lost exact source alignment")
    return PreparedPowerTemplate(records, eras, injection, raw_audit)


def _unprefix_sessions(sampled: pd.DataFrame, prefix: str) -> pd.DataFrame:
    marker = f"{prefix}__"
    columns = [column for column in sampled if column.startswith(marker)]
    if not columns:
        raise ValueError(f"paired power records contain no {prefix.upper()} session columns")
    result = sampled[columns].copy()
    result.columns = [column[len(marker) :] for column in columns]
    return result.reset_index(drop=True)


def _materialize_power_sample(
    prepared: PreparedPowerTemplate,
    config: dict[str, Any],
    donor_map: pd.DataFrame | None = None,
) -> MaterializedPowerSample:
    """Materialize artificial outcomes and recompute all causal rolling features."""

    sampled = (
        prepared.records.copy()
        if donor_map is None
        else apply_paired_donor_map(prepared.records, donor_map)
    )
    target_dates = prepared.records.index
    if not sampled.index.equals(target_dates):
        raise AssertionError("materialized power sample changed target-date order")
    if not np.array_equal(sampled["era"].astype(str), prepared.eras.astype(str)):
        raise AssertionError("outer donor map changed a discovery/A/B label")
    frames = {instrument: _unprefix_sessions(sampled, instrument.lower()) for instrument in ("NQ", "ES")}
    for frame in frames.values():
        frame["date"] = target_dates.to_numpy()
    entry_column = str(config["entry_column"])
    exit_column = str(config["exit_column"])
    frames["NQ"][exit_column] = (
        pd.to_numeric(frames["NQ"][entry_column], errors="coerce").to_numpy(dtype=float)
        + pd.to_numeric(sampled["nq_injected_points"], errors="coerce").to_numpy(dtype=float)
    )
    frames["ES"][exit_column] = (
        pd.to_numeric(frames["ES"][entry_column], errors="coerce").to_numpy(dtype=float)
        + pd.to_numeric(sampled["es_demeaned_points"], errors="coerce").to_numpy(dtype=float)
    )
    for instrument, frame in frames.items():
        prices = frame[[entry_column, exit_column]].apply(pd.to_numeric, errors="coerce")
        if not np.isfinite(prices.to_numpy(dtype=float)).all() or not prices.gt(0).all().all():
            raise ValueError(f"materialized {instrument} artificial execution prices are invalid")
    rolling = {
        "rolling_window": int(config["rolling_control_window"]),
        "rolling_min_periods": int(config["rolling_control_min_periods"]),
    }
    features = {
        instrument: opening_feature_frame(frame, **rolling)
        for instrument, frame in frames.items()
    }
    recomputed_side = opening_signals(features["NQ"])[FROZEN_PRIMARY_CANDIDATE]
    expected_side = pd.to_numeric(sampled["injection_side"], errors="coerce").reset_index(drop=True)
    if not np.array_equal(recomputed_side.to_numpy(), expected_side.to_numpy()):
        raise AssertionError("resampling broke side alignment of the injected C004 effect")
    source_dates = pd.Series(
        pd.to_datetime(sampled["source_date"]).to_numpy(),
        index=target_dates,
        name="source_date",
    )
    return MaterializedPowerSample(
        sessions=frames["NQ"],
        nq_features=features["NQ"],
        es_features=features["ES"],
        eras=prepared.eras,
        source_dates=source_dates,
    )


def _selection_payload(result: SelectionResult) -> dict[str, object]:
    return {
        "candidate_id": result.candidate_id,
        "candidate": result.candidate,
        "discovery_statistic": result.discovery_statistic,
        "discovery_trades": result.discovery_trades,
        "validation_statistic": result.validation_statistic,
        "validation_trades": result.validation_trades,
        "thresholds": result.thresholds.as_dict(),
    }


def _select_sample(
    sample: MaterializedPowerSample,
    candidate_ids: dict[str, str],
    config: dict[str, Any],
) -> SelectionResult:
    return select_and_score(
        sample.sessions,
        sample.nq_features,
        sample.es_features,
        sample.discovery_mask,
        sample.validation_mask,
        candidate_ids,
        entry_column=str(config["entry_column"]),
        exit_column=str(config["exit_column"]),
        slippage_ticks_per_side=float(config["primary_cost"]["slippage_ticks_per_side"]),
        round_trip_fees_usd=float(config["primary_cost"]["round_trip_fees_usd"]),
    )


def _trial_stream(
    config: dict[str, Any], trial: int, stream: Literal["donor", "conditional", "circular"]
) -> tuple[np.random.Generator, dict[str, int]]:
    """Construct an order-independent frozen outer-trial RNG and fingerprint."""

    if not 1 <= trial <= int(config["power_outer_draws"]):
        raise ValueError("outer power trial number is outside the frozen range")
    stream_id = int(config["power_trial_stream_ids"][stream])
    entropy = [int(config["power_outer_seed"]), int(trial), stream_id]
    seed_sequence = np.random.SeedSequence(entropy)
    fingerprint = int(seed_sequence.generate_state(1, dtype=np.uint64)[0])
    return np.random.default_rng(seed_sequence), {
        "power_outer_seed": entropy[0],
        "trial": entropy[1],
        "stream_id": entropy[2],
        "seedsequence_uint64_fingerprint": fingerprint,
    }


def _run_null_family(
    kind: Literal["conditional", "circular"],
    *,
    sample: MaterializedPowerSample,
    observed_statistic: float,
    candidate_ids: dict[str, str],
    config: dict[str, Any],
    draws: int,
    rng: np.random.Generator,
    rng_label: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run one complete-pipeline null family with no invalid-draw filtering."""

    if kind not in NULL_KINDS or draws < 2:
        raise ValueError("null kind or draw count is invalid")
    rows: list[dict[str, object]] = []
    selections: Counter[str] = Counter()
    for draw_number in range(1, draws + 1):
        result, donor = null_draw(
            kind,
            sample.sessions,
            sample.nq_features,
            sample.es_features,
            sample.discovery_mask,
            sample.validation_mask,
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
            raise AssertionError("identity draw reached the registered power null")
        selections[result.candidate_id] += 1
        row: dict[str, object] = {
            "draw": draw_number,
            "null": kind,
            "candidate_id": result.candidate_id,
            "candidate": result.candidate,
            "discovery_statistic": result.discovery_statistic,
            "discovery_trades": result.discovery_trades,
            "validation_statistic": result.validation_statistic,
            "validation_trades": result.validation_trades,
            "donor_fixed_points": int(np.sum(donor == np.arange(len(donor)))),
            "rng_label": rng_label,
        }
        row.update(
            {f"threshold_{name}": value for name, value in result.thresholds.as_dict().items()}
        )
        rows.append(row)
    table = pd.DataFrame(rows)
    values = pd.to_numeric(table["validation_statistic"], errors="coerce").to_numpy(dtype=float)
    if len(values) != draws or not np.isfinite(values).all():
        raise AssertionError("every registered power null draw must be present and finite")
    standard_deviation = float(np.std(values, ddof=1))
    if not np.isfinite(standard_deviation) or standard_deviation <= 0:
        raise AssertionError("registered power null distribution has zero/invalid variance")
    exceedances = int(np.sum(values >= observed_statistic))
    p_value = empirical_pvalue(observed_statistic, values)
    interval = clopper_pearson_interval(exceedances, draws)
    diagnostics: dict[str, object] = {
        "draws": int(draws),
        "invalid_draws": 0,
        "identity_draws": 0,
        "rng_label": rng_label,
        "observed_statistic": float(observed_statistic),
        "exceedances": exceedances,
        "p_value": p_value,
        "passes_0_05": bool(p_value <= 0.05),
        "clopper_pearson_exceedance_interval": list(interval),
        "mean": float(np.mean(values)),
        "standard_deviation": standard_deviation,
        "median": float(np.median(values)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "candidate_selection_frequencies": {
            candidate_id: int(selections.get(candidate_id, 0))
            for candidate_id in sorted(candidate_ids.values())
        },
    }
    return table, diagnostics


def _reconcile_full_template(
    sample: MaterializedPowerSample,
    prepared: PreparedPowerTemplate,
    config: dict[str, Any],
) -> None:
    c004 = opening_signals(sample.nq_features)[FROZEN_PRIMARY_CANDIDATE].to_frame()
    pnl = candidate_net_pnl(
        sample.sessions,
        c004,
        instrument="NQ",
        entry_column=str(config["entry_column"]),
        exit_column=str(config["exit_column"]),
        slippage_ticks_per_side=float(config["primary_cost"]["slippage_ticks_per_side"]),
        round_trip_fees_usd=float(config["primary_cost"]["round_trip_fees_usd"]),
    )[:, 0]
    expected = prepared.injection.zero_filled_net_dollars.to_numpy(dtype=float)
    if not np.allclose(pnl, expected, rtol=0.0, atol=1e-8):
        raise AssertionError("full-template pipeline P&L does not reconcile to solved injection")


def _compute_independent_nq_mde(config: dict[str, Any]) -> dict[str, object]:
    """Compute the frozen MDE on the actual independent-NQ primary book."""

    sessions, _ = independent_session_feature_frames(
        config,
        required_clocks=(str(config["entry_column"]), str(config["exit_column"])),
        strict_full_session=False,
    )
    nq = sessions["NQ"]
    dates = _chronological_dates(nq, name="independent NQ sessions")
    keep = (dates >= pd.Timestamp(str(config["discovery_start"]))) & (
        dates <= pd.Timestamp(str(config["validation_b_end"]))
    )
    nq = nq.loc[keep].reset_index(drop=True).copy()
    features = opening_feature_frame(
        nq,
        rolling_window=int(config["rolling_control_window"]),
        rolling_min_periods=int(config["rolling_control_min_periods"]),
    )
    side = opening_signals(features)[FROZEN_PRIMARY_CANDIDATE]
    daily = run_fixed_schedule(
        nq,
        side,
        instrument="NQ",
        entry_column=str(config["entry_column"]),
        exit_column=str(config["exit_column"]),
        decision_time_et=str(config["signal_available_time_et"]),
        entry_time_et=str(config["entry_order_active_time_et"]),
        exit_time_et=str(config["scheduled_exit_order_active_time_et"]),
        costs=cost_profile(config),
        strategy_name=FROZEN_PRIMARY_CANDIDATE,
    )
    validation = pd.to_datetime(daily["date"]).between(
        pd.Timestamp(str(config["validation_start"])),
        pd.Timestamp(str(config["validation_b_end"])),
        inclusive="both",
    )
    result = minimum_detectable_effect(
        daily.loc[validation].reset_index(drop=True),
        point_value_dollars=INSTRUMENT_SPECS["NQ"].multiplier,
        hac_lags=int(config["hac_lags"]),
        mde_multiplier=2.49,
        tick_size_points=INSTRUMENT_SPECS["NQ"].tick_size,
    )
    return {
        "calendar": "independent primary NQ eligible sessions",
        "candidate_id": FROZEN_PRIMARY_CANDIDATE_ID,
        "candidate": FROZEN_PRIMARY_CANDIDATE,
        "cost": config["primary_cost"],
        "validation_start": str(config["validation_start"]),
        "validation_end": str(config["validation_b_end"]),
        **result,
    }


def _template_daily_table(prepared: PreparedPowerTemplate) -> pd.DataFrame:
    columns = [
        "source_date",
        "era",
        "nq_unsigned_points",
        "es_unsigned_points",
        "nq_demeaned_points",
        "es_demeaned_points",
        "nq_injected_points",
        "injection_side",
        "nq_opening_side",
        "es_opening_side",
    ]
    table = prepared.records[columns].copy().reset_index(names="date")
    table["nq_injected_net_dollars"] = prepared.injection.zero_filled_net_dollars.to_numpy()
    return table


def _seed_plan(config: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "stage": "full_template",
            "outer_trial": pd.NA,
            "stream": "conditional",
            "integer_seed": int(config["power_full_conditional_seed"]),
            "power_outer_seed": pd.NA,
            "stream_id": pd.NA,
            "seedsequence_uint64_fingerprint": pd.NA,
        },
        {
            "stage": "full_template",
            "outer_trial": pd.NA,
            "stream": "circular",
            "integer_seed": int(config["power_full_circular_seed"]),
            "power_outer_seed": pd.NA,
            "stream_id": pd.NA,
            "seedsequence_uint64_fingerprint": pd.NA,
        },
    ]
    for trial in range(1, int(config["power_outer_draws"]) + 1):
        for stream in ("donor", "conditional", "circular"):
            _, audit = _trial_stream(config, trial, stream)
            rows.append(
                {
                    "stage": "outer_trial",
                    "outer_trial": trial,
                    "stream": stream,
                    "integer_seed": pd.NA,
                    **audit,
                }
            )
    return pd.DataFrame(rows)


def _selection_frequency_table(
    candidate_ids: dict[str, str],
    *,
    full_nulls: pd.DataFrame | None = None,
    outer_trials: pd.DataFrame | None = None,
    inner_nulls: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    candidates = sorted(candidate_ids.values())

    def append_group(scope: str, null_kind: str, values: pd.Series) -> None:
        counts = values.value_counts()
        denominator = int(len(values))
        for candidate_id in candidates:
            count = int(counts.get(candidate_id, 0))
            rows.append(
                {
                    "scope": scope,
                    "null": null_kind,
                    "candidate_id": candidate_id,
                    "count": count,
                    "denominator": denominator,
                    "frequency": float(count / denominator) if denominator else float("nan"),
                }
            )

    if full_nulls is not None:
        for kind in NULL_KINDS:
            append_group(
                "full_template_null",
                kind,
                full_nulls.loc[full_nulls["null"].eq(kind), "candidate_id"],
            )
    if outer_trials is not None:
        append_group("outer_observed", "none", outer_trials["selected_candidate_id"])
    if inner_nulls is not None:
        for kind in NULL_KINDS:
            append_group(
                "outer_inner_null",
                kind,
                inner_nulls.loc[inner_nulls["null"].eq(kind), "candidate_id"],
            )
    return pd.DataFrame(rows)


def _persist_outer_artifacts(
    output_dir: Path,
    candidate_ids: dict[str, str],
    full_nulls: pd.DataFrame,
    outer_rows: list[dict[str, object]],
    inner_tables: list[pd.DataFrame],
    donor_tables: list[pd.DataFrame],
) -> None:
    outer = pd.DataFrame(outer_rows)
    inner = pd.concat(inner_tables, ignore_index=True) if inner_tables else pd.DataFrame()
    donors = pd.concat(donor_tables, ignore_index=True) if donor_tables else pd.DataFrame()
    outer.to_csv(output_dir / "power_outer_trials.csv", index=False)
    if not inner.empty:
        inner.to_csv(
            output_dir / "power_inner_null_draws.csv.gz", index=False, compression="gzip"
        )
    if not donors.empty:
        donors.to_csv(
            output_dir / "power_outer_donor_maps.csv.gz", index=False, compression="gzip"
        )
    _selection_frequency_table(
        candidate_ids,
        full_nulls=full_nulls,
        outer_trials=outer if not outer.empty else None,
        inner_nulls=inner if not inner.empty else None,
    ).to_csv(output_dir / "power_selection_frequencies.csv", index=False)


def run_registered_power(
    output_dir: Path,
    config: dict[str, Any],
    economic_result: dict[str, Any],
    validation_result: dict[str, Any],
) -> dict[str, object]:
    """Execute the full registered gate; intended to be called only by ``main``."""

    _validate_registered_config(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    upstream = _upstream_gate_decision(economic_result, validation_result)
    if not upstream["proceed"]:
        result = {
            key: value for key, value in upstream.items() if key != "proceed"
        }
        result.update(
            {
                "power_gate": "NOT_RUN_BY_FROZEN_HIERARCHY",
                "power_gate_passes": False,
                "full_hypothesis_go": False,
            }
        )
        write_json(output_dir / "power_result.json", result)
        return result
    candidate_ids = candidate_id_map()
    if candidate_ids.get(FROZEN_PRIMARY_CANDIDATE) != FROZEN_PRIMARY_CANDIDATE_ID:
        raise ValueError("frozen manifest no longer maps confirmed_gap to C004")

    # The loader is deliberately confined to this registered entry point. Pure
    # tests call the preparation/materialization helpers with synthetic frames.
    common_sessions, _ = common_session_feature_frames(config)
    prepared = _prepare_power_template(common_sessions, config)
    _template_daily_table(prepared).to_csv(
        output_dir / "power_template_daily.csv.gz", index=False, compression="gzip"
    )
    mde = _compute_independent_nq_mde(config)
    write_json(output_dir / "power_mde.json", mde)
    _seed_plan(config).to_csv(output_dir / "power_seed_plan.csv", index=False)

    full_sample = _materialize_power_sample(prepared, config)
    _reconcile_full_template(full_sample, prepared, config)
    full_selection = _select_sample(full_sample, candidate_ids, config)
    target = float(config["positive_control_target_zero_filled_net_sharpe"])
    if full_selection.candidate_id != FROZEN_PRIMARY_CANDIDATE_ID:
        result = {
            "status": "INCONCLUSIVE",
            "reason": "full injected template did not select frozen C004",
            "power_gate_passes": False,
            "full_hypothesis_go": False,
            "upstream_hierarchy": {
                key: value for key, value in upstream.items() if key != "proceed"
            },
            "full_template_selection": _selection_payload(full_selection),
            "injection_points_per_selected_day": prepared.injection.injection_points_per_selected_day,
            "raw_execution_audit": prepared.raw_audit,
            "mde": mde,
        }
        write_json(output_dir / "power_result.json", result)
        return result
    if not np.isclose(full_selection.validation_statistic, target, rtol=0.0, atol=1e-10):
        raise AssertionError("full injected template did not preserve the solved target Sharpe")

    full_tables: list[pd.DataFrame] = []
    full_nulls: dict[str, object] = {}
    for kind, seed_key, draw_key in (
        ("conditional", "power_full_conditional_seed", "conditional_permutation_null_draws"),
        ("circular", "power_full_circular_seed", "circular_shift_null_draws"),
    ):
        seed = int(config[seed_key])
        table, diagnostics = _run_null_family(
            kind,
            sample=full_sample,
            observed_statistic=full_selection.validation_statistic,
            candidate_ids=candidate_ids,
            config=config,
            draws=int(config[draw_key]),
            rng=np.random.default_rng(seed),
            rng_label=f"integer_seed:{seed}",
        )
        table.insert(0, "scope", "full_template")
        full_tables.append(table)
        full_nulls[kind] = diagnostics
    full_draws = pd.concat(full_tables, ignore_index=True)
    full_draws.to_csv(
        output_dir / "power_full_template_null_draws.csv.gz",
        index=False,
        compression="gzip",
    )
    _selection_frequency_table(candidate_ids, full_nulls=full_draws).to_csv(
        output_dir / "power_selection_frequencies.csv", index=False
    )
    full_pass = all(bool(full_nulls[kind]["passes_0_05"]) for kind in NULL_KINDS)
    common_payload: dict[str, object] = {
        "historical_status": "power machinery only; does not create a clean holdout",
        "upstream_hierarchy": {
            key: value for key, value in upstream.items() if key != "proceed"
        },
        "registered_contract": {
            **FROZEN_POWER_CONTRACT,
            "power_trial_seed_derivation": FROZEN_SEED_DERIVATION,
            "power_trial_stream_ids": FROZEN_STREAM_IDS,
            "stationary_bootstrap_expected_block": config[
                "stationary_bootstrap_expected_block"
            ],
        },
        "injection": {
            "points_per_selected_day": prepared.injection.injection_points_per_selected_day,
            "target_validation_sharpe": prepared.injection.target_validation_sharpe,
            "achieved_validation_sharpe": prepared.injection.achieved_validation_sharpe,
            "validation_sessions": prepared.injection.validation_sessions,
            "validation_trades": prepared.injection.validation_trades,
            "applied_in_all_eras": True,
        },
        "raw_execution_audit": prepared.raw_audit,
        "full_template_selection": _selection_payload(full_selection),
        "full_template_nulls": full_nulls,
        "full_template_passes": full_pass,
        "mde": mde,
    }
    if not full_pass:
        result = {
            "status": "INCONCLUSIVE",
            "reason": "full 4,999-draw injected template failed one or both null gates",
            "power_gate_passes": False,
            "full_hypothesis_go": False,
            **common_payload,
        }
        write_json(output_dir / "power_result.json", result)
        return result

    outer_rows: list[dict[str, object]] = []
    inner_tables: list[pd.DataFrame] = []
    donor_tables: list[pd.DataFrame] = []
    successes = 0
    for trial in range(1, int(config["power_outer_draws"]) + 1):
        try:
            donor_rng, donor_audit = _trial_stream(config, trial, "donor")
            donor_map = paired_stationary_bootstrap_donor_map(
                prepared.eras,
                expected_block=float(config["stationary_bootstrap_expected_block"]),
                rng=donor_rng,
            )
            donor_artifact = donor_map.reset_index()
            donor_artifact.insert(0, "outer_trial", trial)
            donor_artifact.insert(
                1,
                "seedsequence_uint64_fingerprint",
                donor_audit["seedsequence_uint64_fingerprint"],
            )
            donor_tables.append(donor_artifact)
            sample = _materialize_power_sample(prepared, config, donor_map)
            selected = _select_sample(sample, candidate_ids, config)
            trial_nulls: dict[str, dict[str, object]] = {}
            for kind in NULL_KINDS:
                null_rng, null_audit = _trial_stream(config, trial, kind)
                table, diagnostics = _run_null_family(
                    kind,
                    sample=sample,
                    observed_statistic=selected.validation_statistic,
                    candidate_ids=candidate_ids,
                    config=config,
                    draws=int(config["power_inner_null_draws"]),
                    rng=null_rng,
                    rng_label=(
                        f"SeedSequence:[{config['power_outer_seed']},{trial},"
                        f"{null_audit['stream_id']}]"
                    ),
                )
                table.insert(0, "outer_trial", trial)
                table.insert(
                    1,
                    "seedsequence_uint64_fingerprint",
                    null_audit["seedsequence_uint64_fingerprint"],
                )
                inner_tables.append(table)
                trial_nulls[kind] = diagnostics
            success = bool(
                selected.candidate_id == FROZEN_PRIMARY_CANDIDATE_ID
                and all(trial_nulls[kind]["passes_0_05"] for kind in NULL_KINDS)
            )
            successes += int(success)
            outer_rows.append(
                {
                    "outer_trial": trial,
                    "selected_candidate_id": selected.candidate_id,
                    "selected_candidate": selected.candidate,
                    "discovery_statistic": selected.discovery_statistic,
                    "discovery_trades": selected.discovery_trades,
                    "validation_statistic": selected.validation_statistic,
                    "validation_trades": selected.validation_trades,
                    "conditional_exceedances": trial_nulls["conditional"]["exceedances"],
                    "conditional_p_value": trial_nulls["conditional"]["p_value"],
                    "conditional_passes": trial_nulls["conditional"]["passes_0_05"],
                    "circular_exceedances": trial_nulls["circular"]["exceedances"],
                    "circular_p_value": trial_nulls["circular"]["p_value"],
                    "circular_passes": trial_nulls["circular"]["passes_0_05"],
                    "success": success,
                    "donor_seedsequence_uint64_fingerprint": donor_audit[
                        "seedsequence_uint64_fingerprint"
                    ],
                }
            )
        except Exception as exc:
            _persist_outer_artifacts(
                output_dir,
                candidate_ids,
                full_draws,
                outer_rows,
                inner_tables,
                donor_tables,
            )
            result = {
                "status": "INCONCLUSIVE",
                "reason": "outer power trial was invalid; zero invalid trials are required",
                "invalid_trials": 1,
                "failed_outer_trial": trial,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "completed_outer_trials": len(outer_rows),
                "successes_so_far": successes,
                "power_gate_passes": False,
                "full_hypothesis_go": False,
                **common_payload,
            }
            write_json(output_dir / "power_result.json", result)
            return result

    _persist_outer_artifacts(
        output_dir,
        candidate_ids,
        full_draws,
        outer_rows,
        inner_tables,
        donor_tables,
    )
    outer_draws = int(config["power_outer_draws"])
    required = int(config["power_required_rejections"])
    power_pass = successes >= required
    result = {
        "status": "PASS" if power_pass else "INCONCLUSIVE",
        "reason": (
            "registered full-template and outer power gates passed"
            if power_pass
            else "fewer than the registered 160 of 200 outer trials succeeded"
        ),
        "power_gate_passes": power_pass,
        "full_hypothesis_go": power_pass,
        "outer_trials": outer_draws,
        "invalid_trials": 0,
        "successes": successes,
        "required_successes": required,
        "estimated_power": float(successes / outer_draws),
        "clopper_pearson_success_interval": list(
            clopper_pearson_interval(successes, outer_draws)
        ),
        **common_payload,
    }
    write_json(output_dir / "power_result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--economic-result", required=True, type=Path)
    parser.add_argument("--validation-result", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run_registered_power(
            args.output_dir,
            load_json(MAIN_CONFIG),
            load_json(args.economic_result),
            load_json(args.validation_result),
        )
    except Exception as exc:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            args.output_dir / "power_result.json",
            {
                "status": "INCONCLUSIVE",
                "reason": "registered power machinery failed before a valid gate result",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "power_gate_passes": False,
                "full_hypothesis_go": False,
            },
        )
        raise SystemExit(2) from None
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
