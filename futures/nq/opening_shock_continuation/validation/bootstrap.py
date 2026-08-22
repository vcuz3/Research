"""Stationary-block resampling and simultaneous one-sided intervals."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def stationary_bootstrap_indices(
    n: int,
    *,
    expected_block: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Politis-Romano stationary bootstrap indices with circular wrapping."""

    if n <= 0:
        raise ValueError("n must be positive")
    if expected_block < 1:
        raise ValueError("expected block length must be at least one")
    restart_probability = 1.0 / float(expected_block)
    indices = np.empty(n, dtype=int)
    indices[0] = int(rng.integers(0, n))
    for position in range(1, n):
        if rng.random() < restart_probability:
            indices[position] = int(rng.integers(0, n))
        else:
            indices[position] = (indices[position - 1] + 1) % n
    return indices


def bootstrap_distribution(
    arrays: list[np.ndarray],
    statistic: Callable[..., float | np.ndarray],
    *,
    draws: int,
    expected_block: float,
    seed: int,
) -> np.ndarray:
    if not arrays:
        raise ValueError("at least one aligned array is required")
    n = len(arrays[0])
    if any(len(array) != n for array in arrays):
        raise ValueError("bootstrap arrays must align")
    rng = np.random.default_rng(seed)
    results = []
    for _ in range(draws):
        idx = stationary_bootstrap_indices(n, expected_block=expected_block, rng=rng)
        results.append(statistic(*(np.asarray(array)[idx] for array in arrays)))
    return np.asarray(results)


def one_sided_lower_bound(distribution: np.ndarray, alpha: float = 0.05) -> float:
    finite = np.asarray(distribution, dtype=float)
    finite = finite[np.isfinite(finite)]
    return float(np.quantile(finite, alpha)) if len(finite) else float("nan")


def simultaneous_lower_bounds(
    bootstrap_differences: np.ndarray,
    observed_differences: np.ndarray,
    *,
    alpha: float = 0.05,
) -> np.ndarray:
    """Max-t-free simultaneous percentile bounds via the worst centered error."""

    draws = np.asarray(bootstrap_differences, dtype=float)
    observed = np.asarray(observed_differences, dtype=float)
    if draws.ndim != 2 or draws.shape[1] != len(observed):
        raise ValueError("draw matrix must be draws x comparisons")
    centered_error = observed[None, :] - draws
    critical = float(np.quantile(np.nanmax(centered_error, axis=1), 1.0 - alpha))
    return observed - critical
