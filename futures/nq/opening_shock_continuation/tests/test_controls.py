"""Synthetic tests for the frozen five-control simultaneous bootstrap gate."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futures.nq.opening_shock_continuation.validation.bootstrap import (
    stationary_bootstrap_indices,
)
from futures.nq.opening_shock_continuation.validation.controls import (
    simultaneous_stationary_control_gate,
)


def _inputs(n_a: int = 12, n_b: int = 10) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
    dates = pd.bdate_range("2023-01-03", periods=n_a + n_b)
    phase = np.arange(n_a + n_b, dtype=float)
    agreement = pd.Series(10.0 + np.sin(phase / 2.0), index=dates, name="agreement")
    controls = pd.DataFrame(
        {
            "opposition": agreement.to_numpy() - 4.0 + 0.20 * np.cos(phase),
            "always_long": agreement.to_numpy() - 3.5 + 0.15 * np.sin(phase),
            "opening_magnitude": agreement.to_numpy() - 3.0 + 0.10 * np.cos(phase / 2.0),
            "total_magnitude": agreement.to_numpy() - 2.5 + 0.10 * np.sin(phase / 3.0),
            "min_component": agreement.to_numpy() - 2.0 + 0.05 * np.cos(phase / 4.0),
        },
        index=dates,
    )
    eras = pd.Series(np.repeat(["A", "B"], [n_a, n_b]), index=dates, name="era")
    return agreement, controls, eras


def test_gate_matches_frozen_formula_and_stratified_joint_donors() -> None:
    agreement, controls, eras = _inputs(n_a=7, n_b=6)
    draws = 31
    expected_block = 3.0
    seed = 9182
    result = simultaneous_stationary_control_gate(
        agreement,
        controls,
        eras,
        draws=draws,
        expected_block=expected_block,
        seed=seed,
    )

    differences = agreement.to_numpy()[:, None] - controls.to_numpy()
    observed = differences.mean(axis=0)
    expected_draws = np.empty((draws, 5))
    rng = np.random.default_rng(seed)
    for draw in range(draws):
        donors = []
        for label in ("A", "B"):
            positions = np.flatnonzero(eras.to_numpy() == label)
            local = stationary_bootstrap_indices(
                len(positions), expected_block=expected_block, rng=rng
            )
            donors.append(positions[local])
        expected_draws[draw] = differences[np.concatenate(donors)].mean(axis=0)
    expected_errors = np.max(observed[None, :] - expected_draws, axis=1)
    expected_critical = np.quantile(expected_errors, 0.95)

    np.testing.assert_allclose(result.observed_differences, observed)
    np.testing.assert_allclose(result.bootstrap_differences, expected_draws)
    np.testing.assert_allclose(result.max_centered_errors, expected_errors)
    assert result.critical_value == pytest.approx(expected_critical)
    np.testing.assert_allclose(result.lower_bounds, observed - expected_critical)
    assert result.passes == bool(np.min(observed - expected_critical) > 0)


def test_joint_resampling_preserves_an_identical_control_difference() -> None:
    agreement, controls, eras = _inputs()
    controls["opposition"] = agreement
    result = simultaneous_stationary_control_gate(
        agreement, controls, eras, draws=53, expected_block=4, seed=11
    )
    np.testing.assert_array_equal(result.bootstrap_differences[:, 0], np.zeros(53))
    assert result.observed_differences[0] == 0.0
    assert result.lower_bounds[0] <= 0.0
    assert not result.passes


def test_separate_era_resampling_keeps_era_sizes_and_weights_fixed() -> None:
    agreement, controls, eras = _inputs(n_a=8, n_b=3)
    for column, offset in zip(controls.columns, np.arange(1.0, 6.0), strict=True):
        # Within each era the paired difference is constant but differs by era.
        controls.loc[eras.eq("A"), column] = agreement.loc[eras.eq("A")] - offset
        controls.loc[eras.eq("B"), column] = agreement.loc[eras.eq("B")] - 2.0 * offset
    result = simultaneous_stationary_control_gate(
        agreement, controls, eras, draws=41, expected_block=20, seed=7
    )
    expected = (8.0 * np.arange(1.0, 6.0) + 3.0 * 2.0 * np.arange(1.0, 6.0)) / 11.0
    np.testing.assert_allclose(result.observed_differences, expected)
    np.testing.assert_allclose(result.bootstrap_differences, np.tile(expected, (41, 1)))


def test_strong_uniform_effect_passes_and_summary_is_labeled() -> None:
    agreement, controls, eras = _inputs()
    result = simultaneous_stationary_control_gate(
        agreement, controls, eras, draws=99, expected_block=5, seed=123
    )
    assert result.passes
    assert np.min(result.lower_bounds) > 0
    summary = result.summary_frame()
    assert summary["control"].tolist() == controls.columns.tolist()
    np.testing.assert_allclose(
        summary["simultaneous_lower_bound_dollars"], result.lower_bounds
    )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda a, c, e: (a, c.iloc[:, :4], e), "exactly five"),
        (lambda a, c, e: (a, c.rename(columns={c.columns[1]: c.columns[0]}), e), "unique"),
        (lambda a, c, e: (a.iloc[::-1], c, e), "aligned"),
        (lambda a, c, e: (a.rename(index={a.index[1]: a.index[0]}), c.rename(index={c.index[1]: c.index[0]}), e.rename(index={e.index[1]: e.index[0]})), "unique"),
        (lambda a, c, e: (a.sort_index(ascending=False), c.sort_index(ascending=False), e.sort_index(ascending=False)), "chronological"),
        (lambda a, c, e: (a.mask(a.index == a.index[0]), c, e), "finite"),
        (lambda a, c, e: (a, c.assign(**{c.columns[0]: np.nan}), e), "finite"),
        (lambda a, c, e: (a, c, e.mask(e.index == e.index[0])), "era labels"),
        (lambda a, c, e: (a, c, e.replace("B", "A")), "exactly A and B"),
    ],
)
def test_input_validation_rejects_unusable_panels(mutation, error: str) -> None:
    agreement, controls, eras = _inputs()
    bad_agreement, bad_controls, bad_eras = mutation(agreement, controls, eras)
    with pytest.raises((TypeError, ValueError), match=error):
        simultaneous_stationary_control_gate(
            bad_agreement, bad_controls, bad_eras, draws=9, expected_block=3, seed=1
        )


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"draws": 0}, "positive integer"),
        ({"draws": 1.5}, "positive integer"),
        ({"expected_block": 0.5}, "at least one"),
        ({"expected_block": np.inf}, "finite"),
        ({"alpha": 0.0}, "strictly between"),
        ({"seed": 1.2}, "integer"),
    ],
)
def test_bootstrap_parameter_validation(kwargs: dict, error: str) -> None:
    agreement, controls, eras = _inputs()
    with pytest.raises(ValueError, match=error):
        simultaneous_stationary_control_gate(agreement, controls, eras, **kwargs)


def test_seed_is_reproducible_and_different_seed_changes_draws() -> None:
    agreement, controls, eras = _inputs()
    first = simultaneous_stationary_control_gate(
        agreement, controls, eras, draws=37, expected_block=3, seed=99
    )
    repeat = simultaneous_stationary_control_gate(
        agreement, controls, eras, draws=37, expected_block=3, seed=99
    )
    different = simultaneous_stationary_control_gate(
        agreement, controls, eras, draws=37, expected_block=3, seed=100
    )
    np.testing.assert_array_equal(first.bootstrap_differences, repeat.bootstrap_differences)
    assert not np.array_equal(first.bootstrap_differences, different.bootstrap_differences)
