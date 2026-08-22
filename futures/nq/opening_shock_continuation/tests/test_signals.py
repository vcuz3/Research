"""Feature causality and frozen signal-definition tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from futures.nq.opening_shock_continuation.strategy.signals import (
    FrozenThresholds,
    add_features,
    base_signals,
    discovery_family_signals,
    fit_rate_matched_thresholds,
    rate_matched_threshold,
    signed,
)


def test_signed_maps_finite_values_and_missing_to_declared_domain() -> None:
    values = pd.Series([-2.0, -0.0, 0.0, 3.0, np.nan, np.inf, -np.inf, "bad"])
    assert signed(values).tolist() == [-1, 0, 0, 1, 0, 0, 0, 0]
    assert str(signed(values).dtype) == "int8"


def test_add_features_exact_returns_signs_and_rest_points(session_factory) -> None:
    sessions = session_factory(4)
    result = add_features(sessions, rolling_window=3, rolling_min_periods=2)
    np.testing.assert_allclose(result["gap_log"], np.log(sessions["o0930"] / sessions["prev_close"]))
    np.testing.assert_allclose(result["opening_log"], np.log(sessions["c0959"] / sessions["o0930"]))
    np.testing.assert_allclose(result["paper_r1_log"], np.log(sessions["c0959"] / sessions["prev_close"]))
    np.testing.assert_allclose(result["paper_r12_log"], np.log(sessions["c1529"] / sessions["o1500"]))
    np.testing.assert_allclose(result["paper_r13_log"], np.log(sessions["c1559"] / sessions["o1530"]))
    np.testing.assert_allclose(result["rest_points_1000"], sessions["c1559"] - sessions["o1000"])
    np.testing.assert_allclose(result["rest_points_1001"], sessions["c1559"] - sessions["o1001"])
    assert result["gap_sign"].tolist() == [1, -1, 1, -1]
    assert result["opening_sign"].tolist() == [1, -1, -1, 1]


def test_directional_clv_rewards_closing_near_directional_extreme(session_factory) -> None:
    sessions = session_factory(2)
    sessions.loc[0, ["o0930", "c0959", "low30", "high30"]] = [100.0, 108.0, 99.0, 109.0]
    sessions.loc[1, ["o0930", "c0959", "low30", "high30"]] = [108.0, 100.0, 99.0, 109.0]
    result = add_features(sessions, rolling_window=2, rolling_min_periods=1)
    assert result.loc[0, "directional_clv"] == pytest.approx(0.9)
    assert result.loc[1, "directional_clv"] == pytest.approx(0.9)


def test_rolling_normalizers_are_shifted_and_prefix_invariant(session_factory) -> None:
    sessions = session_factory(8)
    original = add_features(sessions, rolling_window=3, rolling_min_periods=2)

    expected_denominator = sessions.loc[:1, "volume30"].median()
    assert original.loc[2, "volume_rel"] == pytest.approx(sessions.loc[2, "volume30"] / expected_denominator)
    assert original.loc[:1, "volume_rel"].isna().all()

    future_changed = sessions.copy()
    future_changed.loc[6:, ["volume30", "rv30", "path30"]] *= 1_000_000.0
    changed = add_features(future_changed, rolling_window=3, rolling_min_periods=2)
    columns = [
        "magnitude_rel",
        "gap_magnitude_rel",
        "total_r1_magnitude_rel",
        "min_component_rel",
        "rv_rel",
        "volume_rel",
        "efficiency_rel",
        "clv_rel",
    ]
    pdt.assert_frame_equal(original.loc[:5, columns], changed.loc[:5, columns])

    appended = pd.concat([sessions, session_factory(2, start="2025-01-02")], ignore_index=True)
    with_future = add_features(appended, rolling_window=3, rolling_min_periods=2)
    pdt.assert_frame_equal(original[columns], with_future.loc[:7, columns].reset_index(drop=True))


def test_add_features_rejects_unsorted_dates_before_past_windows(session_factory) -> None:
    sessions = session_factory(6)
    shuffled = sessions.sample(frac=1.0, random_state=7)
    with pytest.raises(ValueError, match="chronological"):
        add_features(shuffled, rolling_window=3, rolling_min_periods=2)


def test_add_features_rejects_missing_and_nonpositive_price_inputs(session_factory) -> None:
    sessions = session_factory(3)
    with pytest.raises(ValueError, match="missing session columns"):
        add_features(sessions.drop(columns="prev_close"))

    bad = sessions.copy()
    bad.loc[0, "prev_close"] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        add_features(bad)

    bad_entry = sessions.copy()
    bad_entry.loc[0, "o1000"] = -1.0
    with pytest.raises(ValueError, match="strictly positive"):
        add_features(bad_entry)


def test_base_signals_exact_agreement_opposition_and_paper_zero_policy(session_factory) -> None:
    sessions = session_factory(4)
    # Rows: confirm long, confirm short, oppose short, oppose long.
    features = add_features(sessions, rolling_window=2, rolling_min_periods=1)
    signals = base_signals(features)
    assert signals["confirmed_gap"].tolist() == [1, -1, 0, 0]
    assert signals["mirror_gap_opposition"].tolist() == [0, 0, -1, 1]
    assert signals["selected_day_always_long"].tolist() == [1, 1, 0, 0]
    assert signals["overnight_only"].tolist() == [1, -1, 1, -1]

    features.loc[0, "paper_r1_log"] = 0.0
    features.loc[0, "paper_r12_log"] = 0.0
    zero_signals = base_signals(features)
    # The paper-faithful binary rule defines non-positive observations as short.
    assert zero_signals.loc[0, "paper_r1"] == -1
    assert zero_signals.loc[0, "paper_r1_r12_agree"] == -1


def test_rate_matched_threshold_is_observed_rank_not_interpolation() -> None:
    feature = pd.Series([9.0, 8.0, np.nan, 4.0, 1.0])
    assert rate_matched_threshold(feature, 2) == 8.0
    assert rate_matched_threshold(feature, 99) == 1.0
    assert np.isinf(rate_matched_threshold(feature, 0))


def test_fit_thresholds_and_discovery_family_use_frozen_values(session_factory) -> None:
    features = add_features(session_factory(10), rolling_window=3, rolling_min_periods=2)
    target = base_signals(features)["confirmed_gap"]
    frozen = fit_rate_matched_thresholds(features, target)
    assert isinstance(frozen, FrozenThresholds)
    assert set(frozen.as_dict()) == {
        "magnitude_rel",
        "gap_magnitude_rel",
        "total_r1_magnitude_rel",
        "min_component_rel",
        "rv_rel",
        "volume_rel",
        "efficiency_rel",
        "clv_rel",
    }

    es = -features["opening_sign"]
    family = discovery_family_signals(features, frozen, es_opening_sign=es)
    assert "confirmed_gap" in family
    assert "opening_magnitude_gate" in family
    assert "gap_plus_opening_magnitude" in family
    assert family["es_opening_confirmation"].eq(0).all()
    assert family["gap_plus_es_confirmation"].eq(0).all()
    assert family.apply(lambda column: column.isin([-1, 0, 1]).all()).all()
