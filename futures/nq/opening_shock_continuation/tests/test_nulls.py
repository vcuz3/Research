"""Invariant tests for claim-matched daily null helpers."""

from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd
import pytest

from futures.nq.opening_shock_continuation.validation.nulls import (
    conditional_paired_gap_permutation,
    era_paired_circular_shift,
    empirical_pvalue,
    stratified_permutation,
    year_stratified_circular_shift,
)


def _multiset(values: pd.Series) -> Counter:
    return Counter(values.tolist())


def test_year_shift_preserves_each_year_multiset_and_forbids_identity() -> None:
    dates = pd.Series(pd.to_datetime(["2023-01-03", "2023-01-04", "2023-01-05", "2024-01-02", "2024-01-03"]))
    values = pd.Series([10, 11, 12, 20, 21], index=[5, 7, 9, 20, 30])
    dates.index = values.index
    shifted = year_stratified_circular_shift(values, dates, np.random.default_rng(123))
    assert shifted.index.equals(values.index)
    for year in (2023, 2024):
        mask = dates.dt.year.eq(year)
        assert _multiset(shifted.loc[mask]) == _multiset(values.loc[mask])
        assert not shifted.loc[mask].equals(values.loc[mask])


def test_year_shift_is_a_rotation_not_an_unstructured_shuffle() -> None:
    dates = pd.Series(pd.date_range("2024-01-02", periods=6, freq="D"))
    values = pd.Series(np.arange(6))
    shifted = year_stratified_circular_shift(values, dates, np.random.default_rng(42))
    doubled = values.tolist() * 2
    start = doubled.index(int(shifted.iloc[0]))
    assert shifted.tolist() == doubled[start : start + len(values)]


def test_year_shift_singleton_is_unchanged_and_length_mismatch_rejected() -> None:
    value = pd.Series([9.0])
    date = pd.Series(pd.to_datetime(["2024-01-02"]))
    assert year_stratified_circular_shift(value, date, np.random.default_rng(1)).equals(value)
    with pytest.raises(ValueError, match="align"):
        year_stratified_circular_shift(pd.Series([1, 2]), date, np.random.default_rng(1))


def test_stratified_permutation_preserves_values_within_every_stratum() -> None:
    values = pd.Series([1, 2, 3, 10, 20, 30], index=[11, 12, 13, 21, 22, 23])
    strata = pd.Series(["a", "a", "a", "b", "b", "b"], index=values.index)
    permuted = stratified_permutation(values, strata, np.random.default_rng(7))
    assert permuted.index.equals(values.index)
    for label in ("a", "b"):
        mask = strata.eq(label)
        assert _multiset(permuted.loc[mask]) == _multiset(values.loc[mask])
    with pytest.raises(ValueError, match="align"):
        stratified_permutation(values, strata.iloc[:-1], np.random.default_rng(7))


def test_null_helpers_are_seed_reproducible() -> None:
    dates = pd.Series(pd.date_range("2024-01-02", periods=10, freq="D"))
    values = pd.Series(np.arange(10))
    a = year_stratified_circular_shift(values, dates, np.random.default_rng(99))
    b = year_stratified_circular_shift(values, dates, np.random.default_rng(99))
    pd.testing.assert_series_equal(a, b)

    strata = pd.Series(np.resize(np.array(["x", "y"]), 10))
    a_perm = stratified_permutation(values, strata, np.random.default_rng(99))
    b_perm = stratified_permutation(values, strata, np.random.default_rng(99))
    pd.testing.assert_series_equal(a_perm, b_perm)


def test_empirical_pvalue_uses_plus_one_and_rejects_nonfinite_draws() -> None:
    assert empirical_pvalue(2.0, np.array([1.0, 2.0, 3.0])) == pytest.approx(0.75)
    assert empirical_pvalue(99.0, np.arange(19, dtype=float)) == pytest.approx(1.0 / 20.0)
    with pytest.raises(ValueError, match="observed"):
        empirical_pvalue(np.nan, np.arange(5, dtype=float))
    with pytest.raises(ValueError, match="all preregistered"):
        empirical_pvalue(1.0, np.array([np.nan, np.inf]))


def test_conditional_paired_gap_permutation_preserves_pairs_strata_and_counts() -> None:
    dates = pd.Series(pd.to_datetime([f"2023-01-{day:02d}" for day in range(2, 10)]))
    nq_open = np.array([1, 1, -1, -1, 1, 1, -1, -1])
    es_open = np.array([1, 1, -1, -1, 1, 1, -1, -1])
    nq_gap = np.array([0.01, -0.02, 0.03, -0.04, -0.05, 0.06, -0.07, 0.08])
    es_gap = nq_gap * 2 + 0.001
    nq_null, es_null, donor = conditional_paired_gap_permutation(
        nq_gap, es_gap, nq_open, es_open, dates, np.random.default_rng(123)
    )
    assert not np.array_equal(donor, np.arange(len(donor)))
    np.testing.assert_allclose(nq_null, nq_gap[donor])
    np.testing.assert_allclose(es_null, es_gap[donor])
    np.testing.assert_array_equal(nq_open, nq_open[donor])
    np.testing.assert_array_equal(es_open, es_open[donor])
    before = np.sign(nq_gap) == nq_open
    after = np.sign(nq_null) == nq_open
    assert before.sum() == after.sum()


def test_yearwise_paired_circular_shift_uses_one_common_nonzero_offset() -> None:
    dates = pd.Series(pd.to_datetime(["2023-01-02", "2023-01-03", "2023-01-04", "2024-01-02", "2024-01-03", "2024-01-04"]))
    years = dates.dt.year.to_numpy()
    nq = np.arange(6, dtype=float)
    es = 100 + nq
    nq_null, es_null, donor = era_paired_circular_shift(
        nq, es, years, np.random.default_rng(9), dates=dates
    )
    assert not np.array_equal(donor, np.arange(6))
    np.testing.assert_allclose(nq_null, nq[donor])
    np.testing.assert_allclose(es_null, es[donor])
    for year in np.unique(years):
        idx = np.flatnonzero(years == year)
        assert not np.array_equal(donor[idx], idx)
