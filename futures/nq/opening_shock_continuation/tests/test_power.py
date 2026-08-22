"""Deterministic synthetic tests for the preregistered power utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from futures.nq.opening_shock_continuation.backtest_engine.metrics import hac_mean_se
from futures.nq.opening_shock_continuation.validation.baseline import zero_filled_sharpe
from futures.nq.opening_shock_continuation.validation.bootstrap import (
    stationary_bootstrap_indices,
)
from futures.nq.opening_shock_continuation.validation.power import (
    POWER_ERAS,
    apply_paired_donor_map,
    demean_paired_outcomes,
    minimum_detectable_effect,
    paired_stationary_bootstrap_donor_map,
    solve_side_aligned_injection,
)


def _mde_frame() -> pd.DataFrame:
    side = np.array([1, 0, -1, 0, 1, -1, 0, 1], dtype=int)
    dollars = np.array([20.0, 0.0, -10.0, 0.0, 15.0, -5.0, 0.0, 8.0])
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-02", periods=len(side)),
            "side": side,
            "trade": side != 0,
            "net_dollars": dollars,
            "net_points": dollars / 20.0,
            "net_bps": dollars / 10.0,
        }
    )


def test_mde_matches_249_hac_se_and_observed_trade_rate_conversions() -> None:
    daily = _mde_frame()
    result = minimum_detectable_effect(
        daily,
        point_value_dollars=20.0,
        hac_lags=2,
        tick_size_points=0.25,
    )
    trade_rate = 5.0 / 8.0
    arrays = {
        "dollars": daily["net_dollars"].to_numpy(),
        "points": daily["net_points"].to_numpy(),
        "bps": daily["net_bps"].to_numpy(),
    }
    assert result["eligible_sessions"] == 8
    assert result["trades"] == 5
    assert result["trade_rate"] == pytest.approx(trade_rate)
    for unit, values in arrays.items():
        expected_se = hac_mean_se(values, max_lag=2)
        assert result["hac_standard_error_daily"][unit] == pytest.approx(expected_se)
        assert result["mde_daily"][unit] == pytest.approx(2.49 * expected_se)
        assert result["mde_per_trade"][unit] == pytest.approx(2.49 * expected_se / trade_rate)
    assert result["mde_daily"]["ticks"] == pytest.approx(
        result["mde_daily"]["points"] / 0.25
    )
    assert result["mde_per_trade"]["ticks"] == pytest.approx(
        result["mde_per_trade"]["points"] / 0.25
    )


def test_mde_derives_after_fee_points_when_column_is_absent() -> None:
    daily = _mde_frame().drop(columns="net_points")
    derived = minimum_detectable_effect(daily, point_value_dollars=20.0, hac_lags=1)
    explicit = minimum_detectable_effect(_mde_frame(), point_value_dollars=20.0, hac_lags=1)
    assert derived["hac_standard_error_daily"] == pytest.approx(
        explicit["hac_standard_error_daily"]
    )
    assert derived["mde_daily"] == pytest.approx(explicit["mde_daily"])


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda frame: frame.assign(trade=frame["trade"].astype(int)), "explicit booleans"),
        (lambda frame: frame.assign(side=np.where(frame.index == 0, 0, frame["side"])), "side != 0"),
        (
            lambda frame: frame.assign(
                net_dollars=frame["net_dollars"].mask(frame.index == 0),
                net_points=frame["net_points"].mask(frame.index == 0),
            ),
            "finite",
        ),
        (
            lambda frame: frame.assign(
                net_dollars=np.where(frame.index == 1, 1.0, frame["net_dollars"]),
                net_points=np.where(frame.index == 1, 0.05, frame["net_points"]),
            ),
            "explicit zero",
        ),
        (lambda frame: frame.assign(net_points=frame["net_points"] + 0.01), "reconcile"),
        (lambda frame: frame.assign(date=np.where(frame.index == 1, frame.loc[0, "date"], frame["date"])), "unique"),
        (lambda frame: frame.assign(side=0, trade=False, net_dollars=0.0, net_points=0.0, net_bps=0.0), "trade rate is zero"),
    ],
)
def test_mde_rejects_nonfinite_nonzero_or_non_zero_filled_books(mutation, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        minimum_detectable_effect(
            mutation(_mde_frame()), point_value_dollars=20.0, hac_lags=2
        )


def _paired_inputs() -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    dates = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2023-01-03",
                "2023-01-04",
                "2023-01-05",
                "2023-01-06",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
                "2024-01-08",
            ]
        ),
        name="date",
    )
    nq = pd.Series([1.0, 3.0, 10.0, 14.0, 100.0, 104.0, -8.0, -2.0], index=dates)
    es = pd.Series([2.0, 6.0, 20.0, 22.0, 50.0, 58.0, -4.0, 2.0], index=dates)
    nq_side = pd.Series([1, 1, -1, -1, 1, 1, -1, -1], index=dates)
    es_side = pd.Series([1, 1, -1, -1, 1, 1, -1, -1], index=dates)
    return nq, es, nq_side, es_side


def test_paired_demeaning_is_within_year_joint_side_and_keeps_alignment() -> None:
    nq, es, nq_side, es_side = _paired_inputs()
    nq_before = nq.copy()
    es_before = es.copy()
    result = demean_paired_outcomes(nq, es, nq_side, es_side)
    assert result.index.equals(nq.index)
    assert result.columns.tolist() == ["nq_demeaned_points", "es_demeaned_points"]
    np.testing.assert_allclose(
        result["nq_demeaned_points"], [-1.0, 1.0, -2.0, 2.0, -2.0, 2.0, -3.0, 3.0]
    )
    np.testing.assert_allclose(
        result["es_demeaned_points"], [-2.0, 2.0, -1.0, 1.0, -4.0, 4.0, -3.0, 3.0]
    )
    audit = result.assign(
        year=result.index.year,
        nq_side=nq_side,
        es_side=es_side,
    )
    group_means = audit.groupby(["year", "nq_side", "es_side"])[
        ["nq_demeaned_points", "es_demeaned_points"]
    ].mean()
    np.testing.assert_allclose(group_means, 0.0, atol=1e-12)
    pdt.assert_series_equal(nq, nq_before)
    pdt.assert_series_equal(es, es_before)


@pytest.mark.parametrize(
    ("field", "mutation", "error"),
    [
        ("es", lambda value: value.iloc[::-1], "alignment"),
        ("nq", lambda value: value.rename(index={value.index[1]: value.index[0]}), "unique"),
        ("nq_side", lambda value: value.mask(value.index == value.index[0], 0.5), "-1, 0, or 1"),
        ("es", lambda value: value.mask(value.index == value.index[0]), "finite"),
    ],
)
def test_paired_demeaning_rejects_alignment_domain_and_finite_failures(
    field: str, mutation, error: str
) -> None:
    nq, es, nq_side, es_side = _paired_inputs()
    values = {"nq": nq, "es": es, "nq_side": nq_side, "es_side": es_side}
    values[field] = mutation(values[field])
    with pytest.raises((TypeError, ValueError), match=error):
        demean_paired_outcomes(
            values["nq"], values["es"], values["nq_side"], values["es_side"]
        )


def _injection_inputs(
    n_discovery: int = 12, n_a: int = 14, n_b: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    dates = pd.DatetimeIndex(
        np.concatenate(
            [
                pd.bdate_range("2018-11-01", periods=n_discovery).to_numpy(),
                pd.bdate_range("2020-01-02", periods=n_a).to_numpy(),
                pd.bdate_range("2024-01-02", periods=n_b).to_numpy(),
            ]
        ),
        name="date",
    )
    phase = np.arange(len(dates), dtype=float)
    outcomes = pd.Series(1.7 * np.sin(phase * 0.83) + 0.6 * np.cos(phase * 0.31), index=dates)
    side = pd.Series(np.resize(np.array([1, 0, -1, 1, 0, -1]), len(dates)), index=dates)
    eras = pd.Series(
        np.repeat(POWER_ERAS, [n_discovery, n_a, n_b]), index=dates, name="era"
    )
    return outcomes, side, eras


def test_side_aligned_injection_hits_exact_validation_sharpe_and_all_era_effect() -> None:
    outcomes, side, eras = _injection_inputs()
    solution = solve_side_aligned_injection(
        outcomes,
        side,
        eras,
        point_value_dollars=20.0,
        round_trip_cost_dollars=14.5,
        target_validation_sharpe=0.50,
    )
    assert solution.injection_points_per_selected_day >= 0.0
    assert solution.achieved_validation_sharpe == pytest.approx(0.50, abs=1e-10)
    assert solution.injected_unsigned_points.index.equals(outcomes.index)
    assert solution.zero_filled_net_dollars.index.equals(outcomes.index)

    change = solution.injected_unsigned_points - outcomes
    selected = side.ne(0)
    np.testing.assert_allclose(
        side.loc[selected] * change.loc[selected],
        solution.injection_points_per_selected_day,
    )
    np.testing.assert_array_equal(change.loc[~selected], np.zeros((~selected).sum()))
    np.testing.assert_array_equal(
        solution.zero_filled_net_dollars.loc[~selected], np.zeros((~selected).sum())
    )
    validation = eras.isin(["A", "B"])
    independently_scored = zero_filled_sharpe(
        solution.zero_filled_net_dollars.loc[validation].to_numpy()
    )
    assert independently_scored == pytest.approx(0.50, abs=1e-10)

    repeat = solve_side_aligned_injection(
        outcomes,
        side,
        eras,
        point_value_dollars=20.0,
        round_trip_cost_dollars=14.5,
        target_validation_sharpe=0.50,
    )
    assert repeat.injection_points_per_selected_day == solution.injection_points_per_selected_day
    pdt.assert_series_equal(repeat.injected_unsigned_points, solution.injected_unsigned_points)


def test_injection_fails_when_always_selected_positive_book_never_crosses_target() -> None:
    outcomes, side, eras = _injection_inputs()
    side.loc[:] = np.resize(np.array([1, -1]), len(side))
    outcomes.loc[:] = side.to_numpy() * (10.0 + 0.1 * np.sin(np.arange(len(side))))
    with pytest.raises(ValueError, match="no nonnegative injection can reach"):
        solve_side_aligned_injection(
            outcomes,
            side,
            eras,
            point_value_dollars=20.0,
            round_trip_cost_dollars=14.5,
            target_validation_sharpe=0.50,
        )


def test_injection_fails_when_sparse_trade_rate_cannot_reach_target() -> None:
    outcomes, side, eras = _injection_inputs(n_discovery=2, n_a=1_001, n_b=1_000)
    outcomes.loc[:] = 0.0
    side.loc[:] = 0
    side.loc[eras.eq("A").idxmax()] = 1
    with pytest.raises(ValueError, match="no nonnegative injection can reach"):
        solve_side_aligned_injection(
            outcomes,
            side,
            eras,
            point_value_dollars=1.0,
            round_trip_cost_dollars=1.0,
            target_validation_sharpe=0.50,
            max_injection_points=65_536.0,
        )


def _bootstrap_panel() -> tuple[pd.DataFrame, pd.Series]:
    dates = pd.DatetimeIndex(
        np.concatenate(
            [
                pd.bdate_range("2018-01-02", periods=5).to_numpy(),
                pd.bdate_range("2020-01-02", periods=4).to_numpy(),
                pd.bdate_range("2024-01-02", periods=6).to_numpy(),
            ]
        ),
        name="date",
    )
    nq = np.arange(len(dates), dtype=float)
    panel = pd.DataFrame(
        {
            "source_date": dates,
            "nq_unsigned": nq,
            "es_unsigned": 100.0 + 2.0 * nq,
            "pair_id": [f"pair-{value}" for value in nq.astype(int)],
        },
        index=dates,
    )
    eras = pd.Series(np.repeat(POWER_ERAS, [5, 4, 6]), index=dates, name="era")
    return panel, eras


def test_paired_stationary_map_matches_seeded_era_local_draws_and_applies_jointly() -> None:
    panel, eras = _bootstrap_panel()
    seed = 9182
    expected_block = 3.0
    mapping = paired_stationary_bootstrap_donor_map(
        eras,
        expected_block=expected_block,
        rng=np.random.default_rng(seed),
    )
    assert mapping.index.equals(panel.index)
    assert mapping.index.is_unique and mapping.index.is_monotonic_increasing
    np.testing.assert_array_equal(mapping["target_position"], np.arange(len(panel)))

    expected = np.empty(len(panel), dtype=int)
    expected_rng = np.random.default_rng(seed)
    era_values = eras.to_numpy()
    for label in POWER_ERAS:
        positions = np.flatnonzero(era_values == label)
        local = stationary_bootstrap_indices(
            len(positions), expected_block=expected_block, rng=expected_rng
        )
        expected[positions] = positions[local]
    np.testing.assert_array_equal(mapping["donor_position"], expected)
    assert mapping["donor_date"].tolist() == panel.index.take(expected).tolist()
    np.testing.assert_array_equal(era_values[expected], era_values)

    sampled = apply_paired_donor_map(panel, mapping)
    assert sampled.index.equals(panel.index)
    assert sampled["source_date"].tolist() == mapping["donor_date"].tolist()
    np.testing.assert_allclose(sampled["es_unsigned"], 100.0 + 2.0 * sampled["nq_unsigned"])
    expected_pairs = panel.iloc[expected]["pair_id"].to_numpy()
    np.testing.assert_array_equal(sampled["pair_id"], expected_pairs)


def test_paired_stationary_map_is_reproducible_and_seed_sensitive() -> None:
    _, eras = _bootstrap_panel()
    first = paired_stationary_bootstrap_donor_map(
        eras, expected_block=2.0, rng=np.random.default_rng(99)
    )
    repeat = paired_stationary_bootstrap_donor_map(
        eras, expected_block=2.0, rng=np.random.default_rng(99)
    )
    different = paired_stationary_bootstrap_donor_map(
        eras, expected_block=2.0, rng=np.random.default_rng(100)
    )
    pdt.assert_frame_equal(first, repeat)
    assert not first["donor_position"].equals(different["donor_position"])


def test_paired_stationary_map_and_application_reject_invalid_alignment() -> None:
    panel, eras = _bootstrap_panel()
    with pytest.raises(ValueError, match="exactly discovery, A, and B"):
        paired_stationary_bootstrap_donor_map(
            eras.replace("B", "A"), expected_block=2.0, rng=np.random.default_rng(1)
        )
    with pytest.raises(ValueError, match="chronological"):
        paired_stationary_bootstrap_donor_map(
            eras.iloc[::-1], expected_block=2.0, rng=np.random.default_rng(1)
        )
    with pytest.raises(ValueError, match="at least one"):
        paired_stationary_bootstrap_donor_map(
            eras, expected_block=0.5, rng=np.random.default_rng(1)
        )

    mapping = paired_stationary_bootstrap_donor_map(
        eras, expected_block=2.0, rng=np.random.default_rng(1)
    )
    bad_date = mapping.copy()
    bad_date.iloc[0, bad_date.columns.get_loc("donor_date")] = panel.index[-1]
    with pytest.raises(ValueError, match="do not reconcile"):
        apply_paired_donor_map(panel, bad_date)
    bad_position = mapping.copy()
    bad_position.iloc[0, bad_position.columns.get_loc("donor_position")] = len(panel)
    with pytest.raises(ValueError, match="out-of-range"):
        apply_paired_donor_map(panel, bad_position)
    crossed_era = mapping.copy()
    crossed_era.iloc[0, crossed_era.columns.get_loc("donor_position")] = len(
        eras.loc[eras.eq("discovery")]
    )
    crossed_era.iloc[0, crossed_era.columns.get_loc("donor_date")] = panel.index[
        int(crossed_era.iloc[0]["donor_position"])
    ]
    with pytest.raises(ValueError, match="crosses a discovery/A/B boundary"):
        apply_paired_donor_map(panel, crossed_era)
