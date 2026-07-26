"""
Add the ENTRY-BAR STOP LEVEL and its distance to an existing enriched trade parquet.

Motivation (user, sizing study): the baseline continuous_stop exit is the band/VWAP
trail with stop_ref="both" -- `max(upper, vwap)` for a long, `min(lower, vwap)` for a
short (core/engine2.py:307). None of the existing 33 columns record that level, so
there is no way to ask "at entry, how far is price from the exit condition?" and use
it as the per-trade risk unit for position sizing.

Adds exactly three columns, leaving all existing columns bit-identical:

  stop_px_entry  -- the stop_ref="both" level evaluated on the ENTRY (fill) bar, i.e.
                    the first bar at which the stop is live (rule 3). Uses the same
                    band_map/vwap arrays and the same have_band -> VWAP-only fallback
                    as the engine.
  stop_dist_pt   -- side * (entry_px - stop_px_entry). Positive = the stop sits
                    favourably away from the fill; <= 0 means the level was already
                    through the next-open fill price.
  stop_dist_atr  -- stop_dist_pt / atr_pts (rule 19 units).

IMPORTANT: the engine recomputes the stop on EVERY bar from the *current* band and
*current* VWAP, and the break-even latch / ratchet / init-stop overlays can tighten it
further. This column is therefore the INITIAL distance at the fill, not a frozen
bracket and not the distance that actually produced the exit.

Rule 23: the script re-runs the engine, reproduces the source parquet's 33 columns
exactly (assert_frame_equal), and only then appends. Idempotent -- re-running
recomputes from the reproduced frame rather than stacking.

Run:  python -u -m futures.nq.noise_vwap.scripts.add_entry_stop_distance
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from ..core import session as S
from ..core import engine2 as E
from .studies import get_session
from .wfo_data import enrich_trades, LOOKBACK

OUT = Path(__file__).resolve().parents[1] / "outputs"

# name -> the E.run kwargs that produced it (must match scripts/tp_equity.py)
TARGETS = {
    "trades_baseline_continuous.parquet": dict(exit_check="every_bar"),
    "trades_tp1.0_50.parquet":            dict(exit_check="every_bar", tp_atr=1.0, tp_frac=0.5),
    "trades_tp0.75_67.parquet":           dict(exit_check="every_bar", tp_atr=0.75, tp_frac=0.67),
}
NEW_COLS = ["stop_px_entry", "stop_dist_pt", "stop_dist_atr"]


def entry_stop_levels(bars: pd.DataFrame, bands: pd.DataFrame,
                      trades: pd.DataFrame) -> pd.DataFrame:
    """stop_ref='both' level on each trade's ENTRY bar, mirroring engine2:301-309."""
    bar_by_date: dict = {}
    for d, g in bars.sort_values("mfo").groupby("sdate", sort=False):
        bar_by_date[d] = dict(mfo=g["mfo"].to_numpy(),
                              vwap=g["vwap"].to_numpy(float))
    band_by = {(int(pd.Timestamp(r.sdate).value), int(r.mfo)): (r.upper, r.lower)
               for r in bands.itertuples()}

    lv = np.full(len(trades), np.nan)
    for i, tr in enumerate(trades.itertuples()):
        bd = bar_by_date.get(tr.date)
        if bd is None:
            continue
        e_pos = int(np.searchsorted(bd["mfo"], tr.entry_mfo))
        if e_pos >= len(bd["mfo"]) or bd["mfo"][e_pos] != tr.entry_mfo:
            continue
        w = bd["vwap"][e_pos]
        up, lo = band_by.get((int(pd.Timestamp(tr.date).value), int(tr.entry_mfo)),
                             (np.nan, np.nan))
        # engine2:295-309 -- no band at this mfo => the stop degrades to VWAP only.
        if np.isfinite(up):
            lv[i] = max(up, w) if tr.side == 1 else min(lo, w)
        else:
            lv[i] = w
    return lv


def main():
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    max_mfo = int(bars["mfo"].max())
    dm = S.decision_mfos(30, max_mfo)

    n_mfo = bars["mfo"].nunique()
    n_band_mfo = bands["mfo"].nunique()
    print(f"bars mfos={n_mfo}  band mfos={n_band_mfo}  decision mfos={len(dm)}")

    for fname, kw in TARGETS.items():
        path = OUT / fname
        if not path.exists():
            print(f"SKIP {fname} (missing)")
            continue
        old = pd.read_parquet(path)
        base_cols = [c for c in old.columns if c not in NEW_COLS]

        raw = E.run(bars, bands, dm, **kw)
        new = enrich_trades(bars, bands, raw)

        # rule 23: reproduce before modifying
        assert_frame_equal(new[base_cols].reset_index(drop=True),
                           old[base_cols].reset_index(drop=True),
                           check_dtype=True)

        lv = entry_stop_levels(bars, bands, new)
        out = old[base_cols].copy()
        out["stop_px_entry"] = lv
        out["stop_dist_pt"] = out["side"] * (out["entry_px"] - out["stop_px_entry"])
        out["stop_dist_atr"] = out["stop_dist_pt"] / out["atr_pts"]

        assert list(out.columns) == base_cols + NEW_COLS
        assert_frame_equal(out[base_cols], old[base_cols], check_dtype=True)
        out.to_parquet(path, index=False)

        d = out["stop_dist_pt"]
        r = out["stop_dist_atr"]
        print(f"\n{fname}: {len(out)} rows, +{len(NEW_COLS)} cols "
              f"({len(base_cols)} preserved, verified identical)")
        print(f"  stop_dist_pt   nan={int(d.isna().sum())}  "
              f"<=0: {float((d <= 0).mean()):.3%}")
        print("  stop_dist_pt  q: " + "  ".join(
            f"p{int(q*100)}={d.quantile(q):.1f}" for q in (.05, .25, .5, .75, .95)))
        print("  stop_dist_atr q: " + "  ".join(
            f"p{int(q*100)}={r.quantile(q):.3f}" for q in (.05, .25, .5, .75, .95)))
        los = out[out["net_points"] < 0]
        print(f"  loser |net|/stop_dist_pt median="
              f"{float((los['net_points'].abs() / los['stop_dist_pt']).median()):.3f}")


if __name__ == "__main__":
    main()
