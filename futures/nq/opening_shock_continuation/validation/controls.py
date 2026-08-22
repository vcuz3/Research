"""Simultaneous deployment-control gate for the frozen opening-shock test.

The estimand is paired, zero-filled daily NQ dollars.  A single date donor is
therefore applied jointly to agreement and every control.  Validation eras A
and B are resampled independently so neither era can donate observations to the
other or change its weight in the combined mean.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .bootstrap import stationary_bootstrap_indices


@dataclass(frozen=True)
class SimultaneousControlGateResult:
    """Auditable output of the five-control simultaneous lower-bound gate."""

    control_names: tuple[str, ...]
    observed_differences: np.ndarray
    bootstrap_differences: np.ndarray
    max_centered_errors: np.ndarray
    critical_value: float
    lower_bounds: np.ndarray
    passes: bool
    draws: int
    expected_block: float
    seed: int

    def summary_frame(self) -> pd.DataFrame:
        """Return labeled observed effects and simultaneous lower bounds."""

        return pd.DataFrame(
            {
                "control": self.control_names,
                "observed_difference_dollars": self.observed_differences,
                "simultaneous_lower_bound_dollars": self.lower_bounds,
            }
        )


def _validated_inputs(
    agreement: pd.Series,
    controls: pd.DataFrame,
    eras: pd.Series,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[str, ...]]:
    if not isinstance(agreement, pd.Series):
        raise TypeError("agreement must be a pandas Series indexed by date")
    if not isinstance(controls, pd.DataFrame):
        raise TypeError("controls must be a pandas DataFrame indexed by date")
    if not isinstance(eras, pd.Series):
        raise TypeError("eras must be a pandas Series indexed by date")
    if controls.shape[1] != 5:
        raise ValueError("the frozen simultaneous family requires exactly five controls")
    if controls.columns.has_duplicates:
        raise ValueError("control names must be unique")
    if not agreement.index.equals(controls.index) or not agreement.index.equals(eras.index):
        raise ValueError("agreement, controls, and eras must have identical aligned indexes")
    if not isinstance(agreement.index, pd.DatetimeIndex):
        raise TypeError("daily inputs must use a DatetimeIndex")
    if agreement.index.has_duplicates:
        raise ValueError("daily input dates must be unique")
    if agreement.index.hasnans:
        raise ValueError("daily input dates must not contain NaT")
    if not agreement.index.is_monotonic_increasing:
        raise ValueError("daily input dates must be chronological")
    if len(agreement) == 0:
        raise ValueError("at least one daily observation is required")

    try:
        agreement_values = agreement.to_numpy(dtype=float)
        control_values = controls.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("agreement and controls must be numeric") from exc
    if not np.isfinite(agreement_values).all() or not np.isfinite(control_values).all():
        raise ValueError("agreement and every control observation must be finite and zero-filled")

    era_values = eras.to_numpy()
    if pd.isna(era_values).any():
        raise ValueError("era labels must be finite A/B values")
    era_values = era_values.astype(str)
    labels = set(era_values.tolist())
    if labels != {"A", "B"}:
        raise ValueError("era labels must contain exactly A and B")

    differences = agreement_values[:, None] - control_values
    if not np.isfinite(differences).all():
        raise ValueError("agreement-minus-control differences must be finite")
    return agreement_values, control_values, era_values, tuple(map(str, controls.columns))


def simultaneous_stationary_control_gate(
    agreement: pd.Series,
    controls: pd.DataFrame,
    eras: pd.Series,
    *,
    draws: int = 4_999,
    expected_block: float = 20.0,
    seed: int = 20260820,
    alpha: float = 0.05,
) -> SimultaneousControlGateResult:
    """Evaluate the frozen five-control simultaneous stationary-bootstrap gate.

    For comparison ``j``, ``Delta_j`` is the full validation-sample mean of
    ``agreement - control_j``.  Each bootstrap draw resamples dates jointly
    across all six series, with independent stationary donor sequences inside
    validation eras A and B.  If ``Delta*_b,j`` is a bootstrap estimate, the
    common critical value is the ``1-alpha`` quantile of
    ``max_j(Delta_j - Delta*_b,j)`` and every lower bound is ``Delta_j - c``.
    The gate passes only when the smallest simultaneous lower bound is strictly
    positive.
    """

    if not isinstance(draws, (int, np.integer)) or isinstance(draws, (bool, np.bool_)) or draws <= 0:
        raise ValueError("draws must be a positive integer")
    if not np.isfinite(expected_block) or expected_block < 1:
        raise ValueError("expected_block must be finite and at least one")
    if not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must lie strictly between zero and one")
    if not isinstance(seed, (int, np.integer)) or isinstance(seed, (bool, np.bool_)):
        raise ValueError("seed must be an integer")

    agreement_values, control_values, era_values, control_names = _validated_inputs(
        agreement, controls, eras
    )
    differences = agreement_values[:, None] - control_values
    observed = differences.mean(axis=0)
    if not np.isfinite(observed).all():
        raise ValueError("observed control differences must all be finite")

    positions = {
        label: np.flatnonzero(era_values == label)
        for label in ("A", "B")
    }
    rng = np.random.default_rng(int(seed))
    bootstrap = np.empty((int(draws), controls.shape[1]), dtype=float)
    for draw in range(int(draws)):
        donors: list[np.ndarray] = []
        for label in ("A", "B"):
            era_positions = positions[label]
            local_donors = stationary_bootstrap_indices(
                len(era_positions), expected_block=float(expected_block), rng=rng
            )
            donors.append(era_positions[local_donors])
        donor_positions = np.concatenate(donors)
        bootstrap[draw] = differences[donor_positions].mean(axis=0)

    if not np.isfinite(bootstrap).all():
        raise ValueError("every preregistered bootstrap draw must be finite")
    max_centered_errors = np.max(observed[None, :] - bootstrap, axis=1)
    if not np.isfinite(max_centered_errors).all():
        raise ValueError("every simultaneous centered-error draw must be finite")
    critical_value = float(np.quantile(max_centered_errors, 1.0 - float(alpha)))
    lower_bounds = observed - critical_value
    if not np.isfinite(critical_value) or not np.isfinite(lower_bounds).all():
        raise ValueError("simultaneous critical value and lower bounds must be finite")

    return SimultaneousControlGateResult(
        control_names=control_names,
        observed_differences=observed,
        bootstrap_differences=bootstrap,
        max_centered_errors=max_centered_errors,
        critical_value=critical_value,
        lower_bounds=lower_bounds,
        passes=bool(np.min(lower_bounds) > 0.0),
        draws=int(draws),
        expected_block=float(expected_block),
        seed=int(seed),
    )
