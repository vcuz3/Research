from __future__ import annotations

import pandas as pd

from download_nasdaq100_1m import reconstruct_periods


def test_reconstruct_periods_includes_removed_and_readded_ticker() -> None:
    current = pd.DataFrame({"ticker": ["A", "C"]})
    changes = pd.DataFrame(
        [
            {"date": "2020-02-01", "added": "C", "removed": "B"},
            {"date": "2020-03-01", "added": "B", "removed": "C"},
        ]
    )
    changes["date"] = pd.to_datetime(changes["date"])
    periods = reconstruct_periods(
        current,
        changes,
        start=pd.Timestamp("2020-01-01"),
        end=pd.Timestamp("2020-04-01"),
    )
    actual = {
        (row.ticker, row.member_from.date().isoformat(), row.member_to.date().isoformat())
        for row in periods.itertuples(index=False)
    }
    assert actual == {
        ("A", "2020-01-01", "2020-04-01"),
        ("B", "2020-01-01", "2020-02-01"),
        ("B", "2020-03-01", "2020-04-01"),
        ("C", "2020-02-01", "2020-03-01"),
    }


def test_same_ticker_corporate_replacement_keeps_interval_open() -> None:
    current = pd.DataFrame({"ticker": ["FOX"]})
    changes = pd.DataFrame(
        [{"date": "2020-02-01", "added": "FOX", "removed": "FOX"}]
    )
    changes["date"] = pd.to_datetime(changes["date"])
    periods = reconstruct_periods(
        current,
        changes,
        start=pd.Timestamp("2020-01-01"),
        end=pd.Timestamp("2020-04-01"),
    )
    assert periods[["ticker", "member_from", "member_to"]].to_dict("records") == [
        {
            "ticker": "FOX",
            "member_from": pd.Timestamp("2020-01-01"),
            "member_to": pd.Timestamp("2020-04-01"),
        }
    ]
