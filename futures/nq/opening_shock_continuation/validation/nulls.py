"""Path-preserving daily nulls for opening-strategy validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import beta


def year_stratified_circular_shift(
    values: pd.Series,
    dates: pd.Series,
    rng: np.random.Generator,
    *,
    forbid_identity: bool = True,
) -> pd.Series:
    """Circularly shift outcomes inside each calendar year.

    This retains each year's empirical outcome distribution and serial ordering,
    but breaks its date-by-date pairing with causal features.
    """

    if len(values) != len(dates):
        raise ValueError("values and dates must align")
    if isinstance(values, pd.Series) and isinstance(dates, pd.Series) and not values.index.equals(dates.index):
        raise ValueError("values and dates indexes must align")
    source = pd.Series(np.asarray(values), index=values.index if isinstance(values, pd.Series) else None)
    date_series = pd.to_datetime(pd.Series(np.asarray(dates), index=source.index))
    if date_series.duplicated().any() or not date_series.is_monotonic_increasing:
        raise ValueError("null dates must be unique and chronological")
    output = source.copy()
    for _, idx in date_series.groupby(date_series.dt.year).groups.items():
        locations = np.asarray(list(idx))
        n = len(locations)
        if n <= 1:
            continue
        low = 1 if forbid_identity else 0
        shift = int(rng.integers(low, n))
        output.loc[locations] = np.roll(source.loc[locations].to_numpy(), shift)
    return output


def stratified_permutation(
    values: pd.Series,
    strata: pd.Series,
    rng: np.random.Generator,
) -> pd.Series:
    """Permute labels independently inside declared strata."""

    if len(values) != len(strata):
        raise ValueError("values and strata must align")
    if isinstance(values, pd.Series) and isinstance(strata, pd.Series) and not values.index.equals(strata.index):
        raise ValueError("values and strata indexes must align")
    source = pd.Series(np.asarray(values), index=values.index if isinstance(values, pd.Series) else None)
    groups = pd.Series(np.asarray(strata), index=source.index)
    output = source.copy()
    for _, idx in groups.groupby(groups).groups.items():
        locations = np.asarray(list(idx))
        output.loc[locations] = rng.permutation(source.loc[locations].to_numpy())
    return output


def empirical_pvalue(observed: float, null_values: np.ndarray) -> float:
    finite = np.asarray(null_values, dtype=float)
    if not np.isfinite(observed):
        raise ValueError("observed null statistic must be finite")
    if finite.size == 0 or not np.isfinite(finite).all():
        raise ValueError("all preregistered null draws must be finite")
    return float((1 + np.sum(finite >= observed)) / (len(finite) + 1))


def conditional_paired_gap_permutation(
    nq_gap: np.ndarray,
    es_gap: np.ndarray,
    nq_open_side: np.ndarray,
    es_open_side: np.ndarray,
    dates: pd.Series,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Permute paired gaps within year x joint-opening-side strata."""

    arrays = [nq_gap, es_gap, nq_open_side, es_open_side, np.asarray(dates)]
    if len({len(array) for array in arrays}) != 1:
        raise ValueError("conditional-null inputs must align")
    n = len(nq_gap)
    donor = np.arange(n)
    date_series = pd.to_datetime(pd.Series(np.asarray(dates)))
    if date_series.duplicated().any() or not date_series.is_monotonic_increasing:
        raise ValueError("conditional-null dates must be unique and chronological")
    years = date_series.dt.year.to_numpy()
    strata = np.rec.fromarrays(
        [years, np.asarray(nq_open_side, dtype=int), np.asarray(es_open_side, dtype=int)],
        names="year,nq_side,es_side",
    )
    for label in np.unique(strata):
        idx = np.flatnonzero(strata == label)
        if len(idx) > 1:
            proposal = rng.permutation(idx)
            attempts = 0
            while np.array_equal(proposal, idx) and attempts < 100:
                proposal = rng.permutation(idx)
                attempts += 1
            if np.array_equal(proposal, idx):
                proposal = np.roll(idx, 1)
            donor[idx] = proposal
    if n > 1 and np.array_equal(donor, np.arange(n)):
        raise ValueError("conditional permutation produced a degenerate identity map")
    return np.asarray(nq_gap)[donor], np.asarray(es_gap)[donor], donor


def era_paired_circular_shift(
    nq_gap: np.ndarray,
    es_gap: np.ndarray,
    eras: np.ndarray,
    rng: np.random.Generator,
    *,
    dates: pd.Series | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rotate paired gap vectors by one nonzero offset inside each era."""

    if not (len(nq_gap) == len(es_gap) == len(eras)):
        raise ValueError("circular-null inputs must align")
    if dates is not None:
        date_series = pd.to_datetime(pd.Series(np.asarray(dates)))
        if len(date_series) != len(nq_gap) or date_series.duplicated().any() or not date_series.is_monotonic_increasing:
            raise ValueError("circular-null dates must align, be unique, and chronological")
    n = len(nq_gap)
    donor = np.arange(n)
    for label in np.unique(eras):
        idx = np.flatnonzero(np.asarray(eras) == label)
        if len(idx) > 1:
            shift = int(rng.integers(1, len(idx)))
            donor[idx] = np.roll(idx, shift)
    if n > 1 and np.array_equal(donor, np.arange(n)):
        raise ValueError("paired circular shift produced a degenerate identity map")
    return np.asarray(nq_gap)[donor], np.asarray(es_gap)[donor], donor


def monte_carlo_interval(
    exceedances: int,
    draws: int,
    *,
    z: float = 1.96,
) -> tuple[float, float]:
    """Wilson interval for the uncorrected exceedance probability."""

    if draws <= 0 or not 0 <= exceedances <= draws:
        raise ValueError("invalid Monte Carlo counts")
    proportion = exceedances / draws
    denominator = 1.0 + z * z / draws
    center = (proportion + z * z / (2.0 * draws)) / denominator
    radius = z * np.sqrt(proportion * (1 - proportion) / draws + z * z / (4 * draws * draws)) / denominator
    return float(max(0.0, center - radius)), float(min(1.0, center + radius))


def clopper_pearson_interval(
    exceedances: int,
    draws: int,
    *,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Exact two-sided binomial interval for Monte Carlo exceedance frequency."""

    if draws <= 0 or not 0 <= exceedances <= draws:
        raise ValueError("invalid Monte Carlo counts")
    lower = 0.0 if exceedances == 0 else float(beta.ppf(alpha / 2, exceedances, draws - exceedances + 1))
    upper = 1.0 if exceedances == draws else float(beta.ppf(1 - alpha / 2, exceedances + 1, draws - exceedances))
    return lower, upper
