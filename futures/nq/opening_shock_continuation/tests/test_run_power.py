"""Synthetic orchestration tests for the registered HYP-0002 power runner."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futures.nq.opening_shock_continuation.scripts.common import (
    MAIN_CONFIG,
    candidate_id_map,
    load_json,
)
from futures.nq.opening_shock_continuation.scripts.run_power import (
    FROZEN_PRIMARY_CANDIDATE,
    _materialize_power_sample,
    _prepare_power_template,
    _reconcile_full_template,
    _run_null_family,
    _select_sample,
    _trial_stream,
    _upstream_gate_decision,
    _validate_registered_config,
    run_registered_power,
)
from futures.nq.opening_shock_continuation.strategy.signals import opening_signals
from futures.nq.opening_shock_continuation.validation.power import (
    paired_stationary_bootstrap_donor_map,
)


def _synthetic_config(dates_by_era: tuple[pd.DatetimeIndex, ...]) -> dict[str, object]:
    discovery, era_a, era_b = dates_by_era
    return {
        "discovery_start": str(discovery[0].date()),
        "discovery_end": str(discovery[-1].date()),
        "validation_start": str(era_a[0].date()),
        "validation_end": str(era_a[-1].date()),
        "validation_b_start": str(era_b[0].date()),
        "validation_b_end": str(era_b[-1].date()),
        "entry_column": "entry_100001",
        "exit_column": "exit_155959",
        "signal_available_time_et": "10:00:00",
        "entry_order_active_time_et": "10:00:01",
        "scheduled_exit_order_active_time_et": "15:59:59",
        "primary_cost": {
            "slippage_ticks_per_side": 1.0,
            "round_trip_fees_usd": 4.5,
        },
        "rolling_control_window": 12,
        "rolling_control_min_periods": 6,
        "positive_control_target_zero_filled_net_sharpe": 0.5,
        "stationary_bootstrap_expected_block": 4,
        "power_outer_draws": 200,
        "power_outer_seed": 20260823,
        "power_trial_stream_ids": {
            "donor": 0,
            "conditional": 1,
            "circular": 2,
        },
    }


def _timestamp(dates: pd.DatetimeIndex, clock: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(
        [
            pd.Timestamp(f"{date.date()} {clock}", tz="America/New_York").tz_convert("UTC")
            for date in dates
        ]
    )


def _session_frame(
    dates: pd.DatetimeIndex,
    *,
    instrument: str,
    anchor: float,
    phase_offset: int,
) -> pd.DataFrame:
    n = len(dates)
    phase = np.arange(n) + phase_offset
    opening_side = np.where(phase % 4 < 2, 1.0, -1.0)
    opening_log = opening_side * (0.0012 + 0.00015 * (1.0 + np.sin(phase / 7.0)))
    gap_side = np.where(phase % 5 < 3, opening_side, -opening_side)
    gap_log = gap_side * (0.0009 + 0.0001 * (1.0 + np.cos(phase / 9.0)))
    prev_close = anchor + 0.8 * phase
    o0930 = prev_close * np.exp(gap_log)
    c0959 = o0930 * np.exp(opening_log)
    entry = c0959 + 0.05 * np.sin(phase / 3.0)
    confirmed = np.where(gap_side == opening_side, opening_side, 0.0)
    # Start C004 below the positive target so the registered nonnegative
    # side-aligned injection has a unique crossing to solve.
    move = -confirmed * (2.0 + 0.3 * np.sin(phase / 5.0))
    move += 1.1 * np.sin(phase * np.sqrt(2.0)) + 0.35 * np.cos(phase / 4.0)
    symbol = f"{instrument}TEST"
    return pd.DataFrame(
        {
            "date": dates,
            "instrument": instrument,
            "prev_close": prev_close,
            "o0930": o0930,
            "c0959": c0959,
            "high30": np.maximum(o0930, c0959) + 2.0,
            "low30": np.minimum(o0930, c0959) - 2.0,
            "volume30": 20_000.0 + 29.0 * phase + 300.0 * np.sin(phase / 8.0),
            "rv30": 0.003 + 0.0002 * (1.0 + np.cos(phase / 6.0)),
            "path30": np.abs(opening_log) + 0.006 + 0.0005 * np.sin(phase / 11.0),
            "entry_100001": entry,
            "exit_155959": entry + move,
            "entry_100001_ts": _timestamp(dates, "10:00:01"),
            "exit_155959_ts": _timestamp(dates, "15:59:59"),
            "prev_symbol": symbol,
            "sym0930": symbol,
            "sym0959": symbol,
            "sym_entry_100001": symbol,
            "sym_exit_155959": symbol,
        }
    )


def _synthetic_panels() -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    eras = (
        pd.bdate_range("2021-01-04", periods=45),
        pd.bdate_range("2022-01-03", periods=45),
        pd.bdate_range("2023-01-03", periods=45),
    )
    dates = pd.DatetimeIndex(np.concatenate([era.to_numpy() for era in eras]))
    config = _synthetic_config(eras)
    return {
        "NQ": _session_frame(dates, instrument="NQ", anchor=12_000.0, phase_offset=0),
        "ES": _session_frame(dates, instrument="ES", anchor=4_000.0, phase_offset=3),
    }, config


def test_registered_config_freezes_explicit_power_rng_contract() -> None:
    config = load_json(MAIN_CONFIG)
    _validate_registered_config(config)
    changed = dict(config)
    changed["power_outer_seed"] = int(config["power_outer_seed"]) + 1
    with pytest.raises(ValueError, match="power_outer_seed"):
        _validate_registered_config(changed)


def test_trial_rng_is_exact_order_independent_and_stream_distinct() -> None:
    _, config = _synthetic_panels()
    first, first_audit = _trial_stream(config, 7, "conditional")
    repeat, repeat_audit = _trial_stream(config, 7, "conditional")
    other, other_audit = _trial_stream(config, 7, "circular")
    np.testing.assert_array_equal(first.integers(0, 2**31, 8), repeat.integers(0, 2**31, 8))
    assert first_audit == repeat_audit
    assert first_audit["stream_id"] == 1
    assert other_audit["stream_id"] == 2
    assert first_audit["seedsequence_uint64_fingerprint"] != other_audit[
        "seedsequence_uint64_fingerprint"
    ]
    assert not np.array_equal(
        np.random.default_rng(
            np.random.SeedSequence([20260823, 7, 1])
        ).integers(0, 2**31, 8),
        other.integers(0, 2**31, 8),
    )


def _passing_upstream_results() -> tuple[dict[str, object], dict[str, object]]:
    economic = {
        "preliminary_economic_gates": {
            "net_sharpe_at_least_0_50": True,
            "era_a_net_mean_positive": True,
            "era_b_net_mean_positive": True,
            "two_tick_net_mean_positive": True,
            "ten_oh_one_net_mean_positive": True,
            "nq_long_gross_mean_positive": True,
            "nq_short_gross_mean_positive": True,
            "es_gross_mean_positive": True,
            "es_agreement_minus_opposition_positive": True,
        },
        "preliminary_pass": True,
    }
    validation = {
        "status": "COMPONENT_PASS_PENDING_POWER",
        "selective_nulls": {
            "conditional": {"passes_0_05": True},
            "circular": {"passes_0_05": True},
        },
        "simultaneous_controls": {"passes": True},
        "selective_null_gate_passes": True,
        "simultaneous_control_gate_passes": True,
        "power_gate": "PENDING_SEPARATE_REGISTERED_RUN",
        "full_hypothesis_go": False,
    }
    return economic, validation


def test_upstream_hierarchy_reconciles_exact_frozen_gate_payloads() -> None:
    economic, validation = _passing_upstream_results()
    assert _upstream_gate_decision(economic, validation)["proceed"] is True

    failed_economic = {
        **economic,
        "preliminary_economic_gates": {
            **economic["preliminary_economic_gates"],
            "two_tick_net_mean_positive": False,
        },
        "preliminary_pass": False,
    }
    rejected = _upstream_gate_decision(failed_economic, validation)
    assert rejected["proceed"] is False
    assert rejected["status"] == "REJECT"

    malformed = {
        **economic,
        "preliminary_economic_gates": {
            **economic["preliminary_economic_gates"],
            "unregistered_gate": True,
        },
    }
    with pytest.raises(ValueError, match="gate family"):
        _upstream_gate_decision(malformed, validation)

    rejected_validation = {"status": "REJECT"}
    component_rejection = _upstream_gate_decision(economic, rejected_validation)
    assert component_rejection["status"] == "REJECT"
    assert component_rejection["proceed"] is False


def test_failed_upstream_gate_stops_before_any_historical_loader(
    tmp_path, monkeypatch
) -> None:
    economic, validation = _passing_upstream_results()
    economic["preliminary_economic_gates"]["era_a_net_mean_positive"] = False
    economic["preliminary_pass"] = False

    def forbidden_loader(_config):
        raise AssertionError("historical loader must not run after upstream rejection")

    monkeypatch.setattr(
        "futures.nq.opening_shock_continuation.scripts.run_power.common_session_feature_frames",
        forbidden_loader,
    )
    result = run_registered_power(
        tmp_path, load_json(MAIN_CONFIG), economic, validation
    )
    assert result["status"] == "REJECT"
    assert result["power_gate"] == "NOT_RUN_BY_FROZEN_HIERARCHY"
    assert result["full_hypothesis_go"] is False
    assert (tmp_path / "power_result.json").exists()


def test_synthetic_panel_preparation_resample_and_both_complete_nulls() -> None:
    panels, config = _synthetic_panels()
    prepared = _prepare_power_template(panels, config)
    assert prepared.injection.achieved_validation_sharpe == pytest.approx(0.5, abs=1e-10)
    assert set(prepared.eras.astype(str)) == {"discovery", "A", "B"}
    assert prepared.raw_audit["NQ"]["all_feature_and_fill_symbols_same_contract"]
    assert prepared.raw_audit["ES"]["decision_entry_exit_clocks_causal"]

    identity = _materialize_power_sample(prepared, config)
    _reconcile_full_template(identity, prepared, config)
    np.testing.assert_array_equal(
        opening_signals(identity.nq_features)[FROZEN_PRIMARY_CANDIDATE],
        prepared.records["injection_side"],
    )
    selected = _select_sample(identity, candidate_id_map(), config)
    assert np.isfinite([selected.discovery_statistic, selected.validation_statistic]).all()

    donor_rng, _ = _trial_stream(config, 3, "donor")
    donor = paired_stationary_bootstrap_donor_map(
        prepared.eras,
        expected_block=float(config["stationary_bootstrap_expected_block"]),
        rng=donor_rng,
    )
    sample = _materialize_power_sample(prepared, config, donor)
    donor_positions = donor["donor_position"].to_numpy(dtype=int)
    np.testing.assert_array_equal(
        sample.source_dates.to_numpy(), prepared.records.index.take(donor_positions).to_numpy()
    )
    np.testing.assert_array_equal(
        prepared.eras.to_numpy()[donor_positions], prepared.eras.to_numpy()
    )
    observed = _select_sample(sample, candidate_id_map(), config)
    for kind in ("conditional", "circular"):
        rng, audit = _trial_stream(config, 3, kind)
        draws, diagnostics = _run_null_family(
            kind,
            sample=sample,
            observed_statistic=observed.validation_statistic,
            candidate_ids=candidate_id_map(),
            config=config,
            draws=4,
            rng=rng,
            rng_label=str(audit),
        )
        assert len(draws) == 4
        assert draws["validation_statistic"].map(np.isfinite).all()
        assert diagnostics["invalid_draws"] == 0
        assert diagnostics["identity_draws"] == 0
        assert 0.0 < diagnostics["p_value"] <= 1.0
