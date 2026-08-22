"""End-to-end synthetic coverage for the frozen 23-candidate null pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd

from futures.nq.opening_shock_continuation.scripts.common import candidate_id_map
from futures.nq.opening_shock_continuation.strategy.signals import (
    discovery_family_signals,
    fit_rate_matched_thresholds,
    opening_feature_frame,
    opening_signals,
    replace_gap_features,
)
from futures.nq.opening_shock_continuation.validation.nulls import (
    conditional_paired_gap_permutation,
    era_paired_circular_shift,
)
from futures.nq.opening_shock_continuation.validation.pipeline import (
    null_draw,
    select_and_score,
)


def _feature_sessions(
    dates: pd.DatetimeIndex,
    *,
    instrument: str,
    anchor: float,
    gap_log: np.ndarray,
    opening_log: np.ndarray,
) -> pd.DataFrame:
    n = len(dates)
    prev_close = anchor + 0.75 * np.arange(n)
    o0930 = prev_close * np.exp(gap_log)
    c0959 = o0930 * np.exp(opening_log)
    return pd.DataFrame(
        {
            "date": dates,
            "instrument": instrument,
            "prev_close": prev_close,
            "o0930": o0930,
            "c0959": c0959,
            "high30": np.maximum(o0930, c0959) + 2.0,
            "low30": np.minimum(o0930, c0959) - 2.0,
            "volume30": 20_000.0 + 37.0 * np.arange(n) + 500.0 * np.sin(np.arange(n) / 7.0),
            "rv30": 0.004 + 0.0003 * (1.0 + np.cos(np.arange(n) / 5.0)),
            "path30": np.abs(opening_log) + 0.008 + 0.001 * (1.0 + np.sin(np.arange(n) / 9.0)),
        }
    )


def test_full_candidate_selection_and_both_paired_null_pipelines() -> None:
    dates = pd.bdate_range("2022-09-01", periods=160)
    phase = np.arange(len(dates))
    opening_side = np.where(phase % 4 < 2, 1.0, -1.0)
    opening_log = opening_side * (0.0015 + 0.0002 * (1.0 + np.sin(phase / 11.0)))
    gap_side = np.where(phase % 7 < 4, opening_side, -opening_side)
    nq_gap = gap_side * (0.0010 + 0.00015 * (1.0 + np.cos(phase / 13.0)))
    es_gap_side = np.where(phase % 5 < 3, opening_side, -opening_side)
    es_gap = es_gap_side * (0.0007 + 0.0001 * (1.0 + np.sin(phase / 8.0)))

    nq_raw = _feature_sessions(
        dates,
        instrument="NQ",
        anchor=12_000.0,
        gap_log=nq_gap,
        opening_log=opening_log,
    )
    es_raw = _feature_sessions(
        dates,
        instrument="ES",
        anchor=4_000.0,
        gap_log=es_gap,
        opening_log=0.7 * opening_log,
    )
    rolling_window, rolling_min_periods = 8, 5
    nq_features = opening_feature_frame(
        nq_raw, rolling_window=rolling_window, rolling_min_periods=rolling_min_periods
    )
    es_features = opening_feature_frame(
        es_raw, rolling_window=rolling_window, rolling_min_periods=rolling_min_periods
    )

    confirmed = opening_signals(nq_features)["confirmed_gap"].to_numpy(dtype=float)
    noise = 0.35 * np.sin(phase * np.sqrt(2.0)) + 0.20 * np.cos(phase / 3.0)
    point_move = confirmed * (4.0 + 0.4 * np.sin(phase / 6.0)) + noise
    sessions = pd.DataFrame(
        {
            "date": dates,
            "entry": 12_000.0 + phase,
            "exit": 12_000.0 + phase + point_move,
        }
    )
    discovery = (dates.year == 2022)
    validation = (dates.year == 2023)
    candidate_ids = candidate_id_map()
    assert len(candidate_ids) == 23

    observed = select_and_score(
        sessions,
        nq_features,
        es_features,
        discovery,
        validation,
        candidate_ids,
        entry_column="entry",
        exit_column="exit",
        slippage_ticks_per_side=1.0,
        round_trip_fees_usd=4.5,
    )
    assert observed.candidate_id == "C004"
    assert observed.candidate == "confirmed_gap"
    assert np.isfinite(
        [observed.discovery_statistic, observed.validation_statistic]
    ).all()

    for kind, seed in (("conditional", 4101), ("circular", 4102)):
        expected_rng = np.random.default_rng(seed)
        if kind == "conditional":
            nq_null, es_null, expected_donor = conditional_paired_gap_permutation(
                nq_features["gap_log"].to_numpy(),
                es_features["gap_log"].to_numpy(),
                nq_features["opening_sign"].to_numpy(),
                es_features["opening_sign"].to_numpy(),
                nq_features["date"],
                expected_rng,
            )
        else:
            nq_null, es_null, expected_donor = era_paired_circular_shift(
                nq_features["gap_log"].to_numpy(),
                es_features["gap_log"].to_numpy(),
                pd.to_datetime(nq_features["date"]).dt.year.to_numpy(),
                expected_rng,
                dates=nq_features["date"],
            )
        result, donor = null_draw(
            kind,
            sessions,
            nq_features,
            es_features,
            discovery,
            validation,
            candidate_ids,
            np.random.default_rng(seed),
            entry_column="entry",
            exit_column="exit",
            slippage_ticks_per_side=1.0,
            round_trip_fees_usd=4.5,
            rolling_window=rolling_window,
            rolling_min_periods=rolling_min_periods,
        )
        np.testing.assert_array_equal(donor, expected_donor)
        assert not np.array_equal(donor, np.arange(len(donor)))
        np.testing.assert_array_equal(nq_null, nq_features["gap_log"].to_numpy()[donor])
        np.testing.assert_array_equal(es_null, es_features["gap_log"].to_numpy()[donor])
        np.testing.assert_array_equal(np.sort(donor), np.arange(len(donor)))
        years = pd.to_datetime(nq_features["date"]).dt.year.to_numpy()
        np.testing.assert_array_equal(years, years[donor])
        if kind == "conditional":
            np.testing.assert_array_equal(
                nq_features["opening_sign"].to_numpy(),
                nq_features["opening_sign"].to_numpy()[donor],
            )
            np.testing.assert_array_equal(
                es_features["opening_sign"].to_numpy(),
                es_features["opening_sign"].to_numpy()[donor],
            )

        nq_replaced = replace_gap_features(
            nq_features,
            nq_null,
            rolling_window=rolling_window,
            rolling_min_periods=rolling_min_periods,
        )
        es_replaced = replace_gap_features(
            es_features,
            es_null,
            rolling_window=rolling_window,
            rolling_min_periods=rolling_min_periods,
        )
        expected_thresholds = fit_rate_matched_thresholds(
            nq_replaced.loc[discovery].reset_index(drop=True),
            opening_signals(nq_replaced).loc[discovery, "confirmed_gap"].reset_index(drop=True),
        )
        assert result.thresholds.as_dict() == expected_thresholds.as_dict()
        family = discovery_family_signals(
            nq_replaced,
            result.thresholds,
            es_opening_sign=es_replaced["opening_sign"],
        )
        assert family.shape[1] == 23
        assert set(family.columns) == set(candidate_ids)
        assert result.candidate_id in set(candidate_ids.values())
        assert np.isfinite(
            [result.discovery_statistic, result.validation_statistic]
        ).all()
