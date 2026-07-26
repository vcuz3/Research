from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from futures.nq.noise_vwap.core.nulls import diffusivity, null_c_returns
from futures.nq.noise_vwap.core.nulls_fast import (
    _block_permutation,
    null_c_returns_fast,
    remap_second_minute_blocks,
)
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
    def test_block_permutation_pins_open_and_preserves_block_order(self) -> None:
        rng = np.random.default_rng(123)
        perm = _block_permutation(17, 5, rng)
        self.assertEqual(perm[0], 0)
        self.assertEqual(sorted(perm.tolist()), list(range(17)))
        for a in range(1, 17, 5):
            source = np.arange(a, min(a + 5, 17))
            positions = np.flatnonzero(np.isin(perm, source))
            np.testing.assert_array_equal(np.diff(positions), np.ones(len(source) - 1))
            np.testing.assert_array_equal(perm[positions], source)

    def test_block_null_preserves_atoms_net_move_and_within_block_order(self) -> None:
        bars = _bars()
        for block_size in (2, 3):
            shuffled, perms = null_c_returns_fast(
                bars, 456, block_size=block_size, return_permutations=True)
            for date, original in bars.groupby("date", sort=False):
                rebuilt = shuffled[shuffled["date"] == date]
                self.assertEqual(_atoms(original), _atoms(rebuilt))
                self.assertAlmostEqual(
                    original.iloc[-1]["close"] - original.iloc[0]["open"],
                    rebuilt.iloc[-1]["close"] - rebuilt.iloc[0]["open"],
                )
                perm = perms[np.datetime64(date, "ns")]
                self.assertEqual(perm[0], 0)
                for a in range(1, len(perm), block_size):
                    source = np.arange(a, min(a + block_size, len(perm)))
                    positions = np.flatnonzero(np.isin(perm, source))
                    np.testing.assert_array_equal(
                        np.diff(positions), np.ones(len(source) - 1, dtype=np.int64))
                    np.testing.assert_array_equal(perm[positions], source)

    def test_fast_implementation_is_bit_exact_to_reference(self) -> None:
        bars = _bars()
        for seed in range(10):
            reference = null_c_returns(bars, seed)
            fast, perms = null_c_returns_fast(
                bars, seed, return_permutations=True)
            for col in ("open", "high", "low", "close", "volume", "vwap", "bar_i"):
                np.testing.assert_allclose(
                    fast[col].to_numpy(), reference[col].to_numpy(),
                    rtol=0.0, atol=0.0)
            self.assertEqual(len(perms), bars["date"].nunique())

    def test_second_block_remap_preserves_intraminute_paths(self) -> None:
        mts = np.array([0, 60, 120], dtype=np.int64) * 1_000_000_000
        # Two seconds per minute are enough to prove timestamp and displacement
        # relocation; source minute 0 remains pinned, as in Null C.
        sts = np.concatenate([m + np.array([0, 1_000_000_000]) for m in mts])
        mop = np.array([100.0, 110.0, 90.0])
        so = np.array([100.0, 101.0, 110.0, 109.0, 90.0, 92.0])
        sh, sl = so + 0.5, so - 0.25
        perm = np.array([0, 2, 1], dtype=np.int64)
        new_open = np.array([100.0, 102.0, 105.0])
        ots, oo, oh, ol = remap_second_minute_blocks(
            sts, so, sh, sl, mts, mop, new_open, perm)
        np.testing.assert_array_equal(
            ots, np.concatenate([m + np.array([0, 1_000_000_000]) for m in mts]))
        np.testing.assert_allclose(oo, [100, 101, 102, 104, 105, 104])
        np.testing.assert_allclose(oh - oo, 0.5)
        np.testing.assert_allclose(oo - ol, 0.25)

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
