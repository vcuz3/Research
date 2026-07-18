from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from futures.nq.noise_vwap.core.nulls import diffusivity, null_c_returns
from futures.nq.noise_vwap.scripts.studies import _null_c_frame


def _bars() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for day_i, date in enumerate(("2026-01-05", "2026-01-06")):
        previous_close = 100.0 + 20.0 * day_i
        for bar_i, (gap, body, volume) in enumerate(
            ((0.0, 1.0, 10), (0.25, -0.5, 20), (-0.75, 1.5, 30),
             (1.25, -1.0, 40), (-0.25, 0.75, 50))
        ):
            open_px = previous_close + gap if bar_i else previous_close
            close_px = open_px + body
            rows.append(
                {
                    "date": date,
                    "tod": 570 + bar_i,
                    "open": open_px,
                    "high": max(open_px, close_px) + 0.5 + bar_i * 0.1,
                    "low": min(open_px, close_px) - 0.25 - bar_i * 0.1,
                    "close": close_px,
                    "volume": volume,
                }
            )
            previous_close = close_px
    return pd.DataFrame(rows)


def _atoms(group: pd.DataFrame) -> list[tuple[float, ...]]:
    o = group["open"].to_numpy(float)
    c = group["close"].to_numpy(float)
    links = np.r_[0.0, o[1:] - c[:-1]]
    return sorted(
        zip(
            links,
            group["high"].to_numpy(float) - o,
            group["low"].to_numpy(float) - o,
            c - o,
            group["volume"].to_numpy(float),
        )
    )


class NullCReturnsTests(unittest.TestCase):
    def test_preserves_anchor_net_move_atoms_and_diffusivity(self) -> None:
        bars = _bars()
        real_diffusivity = diffusivity(bars)

        for seed in range(30):
            shuffled = null_c_returns(bars, seed)
            self.assertAlmostEqual(diffusivity(shuffled), real_diffusivity)

            for date, original in bars.groupby("date", sort=False):
                rebuilt = shuffled[shuffled["date"] == date]
                self.assertEqual(original.iloc[0]["open"], rebuilt.iloc[0]["open"])
                self.assertEqual(original.iloc[0]["close"], rebuilt.iloc[0]["close"])
                self.assertAlmostEqual(
                    original.iloc[-1]["close"] - original.iloc[0]["open"],
                    rebuilt.iloc[-1]["close"] - rebuilt.iloc[0]["open"],
                )
                self.assertEqual(_atoms(original), _atoms(rebuilt))

    def test_studies_null_preserves_net_move_and_atoms(self) -> None:
        bars = _bars().rename(columns={"date": "sdate", "tod": "mfo"})
        bars["is_rth"] = True

        for seed in range(30):
            shuffled = _null_c_frame(bars, seed)
            for date, original in bars.groupby("sdate", sort=False):
                rebuilt = shuffled[shuffled["sdate"] == date]
                self.assertEqual(original.iloc[0]["open"], rebuilt.iloc[0]["open"])
                self.assertEqual(original.iloc[0]["close"], rebuilt.iloc[0]["close"])
                self.assertAlmostEqual(
                    original.iloc[-1]["close"] - original.iloc[0]["open"],
                    rebuilt.iloc[-1]["close"] - rebuilt.iloc[0]["open"],
                )
                self.assertEqual(_atoms(original), _atoms(rebuilt))


if __name__ == "__main__":
    unittest.main()
