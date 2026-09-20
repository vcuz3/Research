import numpy as np
import pandas as pd

from futures.nq.percentile_rank_momentum.strategy.features import (
    add_vol_normalized_momentum,
    causal_sign_split_rank,
)


def test_sign_split_rank_uses_only_prior_session_window_and_sign():
    values = np.array([1.0, -100.0, 2.0, 3.0, 4.0])
    got = causal_sign_split_rank(values, window=3, minimum_fraction=1 / 3)
    assert np.isnan(got["rank"][0])
    assert np.isnan(got["rank"][1])
    assert np.isnan(got["rank"][2])  # fewer than three prior sessions
    assert got["rank"][3] == 1.0  # compares 3 only with positive 1 and 2
    assert got["rank"][4] == 1.0  # oldest positive 1 has rolled out


def test_missing_value_consumes_a_session_in_the_fixed_window():
    values = np.array([1.0, np.nan, 2.0, 3.0])
    got = causal_sign_split_rank(values, window=3, minimum_fraction=2 / 3)
    assert got["history_count"][3] == 3
    assert got["positive_count"][3] == 2
    assert got["rank"][3] == 1.0


def test_future_mutation_cannot_change_past_rank():
    values = np.array([1.0, 2.0, -3.0, 4.0, 5.0])
    first = causal_sign_split_rank(values, window=3, minimum_fraction=1 / 3)["rank"]
    values[-1] = -999.0
    second = causal_sign_split_rank(values, window=3, minimum_fraction=1 / 3)["rank"]
    np.testing.assert_allclose(first[:-1], second[:-1], equal_nan=True)


def test_exact_point_nine_same_sign_floor_rejects_balanced_history():
    values = np.tile(np.array([1.0, -1.0]), 40)
    got = causal_sign_split_rank(values, window=60, minimum_fraction=0.9)
    assert np.isnan(got["rank"]).all()
    assert got["required_sign_count"][0] == 54


def test_opening_vol_uses_six_opening_bar_returns_and_prior_day_only():
    rows = []
    for date, scale in [(pd.Timestamp("2024-01-02"), 1.0), (pd.Timestamp("2024-01-03"), 2.0)]:
        price = 100.0
        for j, tod in enumerate(range(570, 605, 5)):
            opening = price
            price *= np.exp(scale * 0.001)
            rows.append({"date": date, "tod": tod, "open": opening, "close": price})
    bars = pd.DataFrame(rows)
    got = add_vol_normalized_momentum(bars, alpha=0.5, horizons_minutes=(15,))
    first_sigma = got.loc[got["date"] == pd.Timestamp("2024-01-02"), "sigma_day"]
    assert first_sigma.isna().all()
    day_two = got.loc[got["date"] == pd.Timestamp("2024-01-03"), "sigma_day"]
    expected = np.sqrt(0.5 * 7 * (0.001 ** 2) + 0.5 * 6 * (0.002 ** 2))
    np.testing.assert_allclose(day_two, expected)
