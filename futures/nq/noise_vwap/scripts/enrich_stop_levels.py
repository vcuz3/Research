"""
Post-hoc annotation of the five EXP-0023 trade tapes with the noise-band / VWAP
stop references at entry and exit. PURELY DERIVED: it re-loads the SAME session
bars and 90-session noise bands the engine used (core.session), looks them up on
(date, mfo), and adds columns. It does NOT re-run the engine, change any P&L, or
touch the audited fill/accounting path -- the tapes' own numbers are unchanged.

For each trade it records, at BOTH the entry fill bar (entry_mfo) and the exit
bar (exit_mfo):
  * <e>_vwap     -- session VWAP at that bar.
  * <e>_band     -- the side-relevant noise-area edge: UPPER for longs, LOWER for
                    shorts (the edge the every-bar stop watches).
  * <e>_stop_ref -- the engine's actual continuous stop reference:
                    max(upper, vwap) for longs, min(lower, vwap) for shorts.
This is the level the every-bar band/VWAP stop compares the bar CLOSE against
(engine2.simulate_session, stop_ref="both").

Derived helper for CFD fixed-%-risk sizing (the reason for this enrichment):
  * entry_stop_pts = (entry_px - entry_stop_ref) * side
      the signed distance in index POINTS from the fill to the native stop
      reference at the entry bar. Positive = stop is adverse (below a long /
      above a short), i.e. the risk-per-unit the native trail would carry from
      entry. Negative = the fill printed on the wrong side of the current
      band/VWAP (the close, not this open, is what the engine actually stops on),
      so the native trail would not yet be adverse.

This is the raw material for choosing a FIXED entry stop (e.g. a multiple of the
band/VWAP distance, or an ATR floor) before position scaling -- it does not itself
pick a stop.

Run:
  python -m futures.nq.noise_vwap.scripts.enrich_stop_levels          # write *_enriched.parquet
  python -m futures.nq.noise_vwap.scripts.enrich_stop_levels inplace  # overwrite the originals
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0023"
LOOKBACK = 90

TAPES = [
    "trades_1_tp0.75_67.parquet",
    "trades_2_tp1.0_50.parquet",
    "trades_3_tp0.75_67_flat45.parquet",
    "trades_4_tp0.75_67_gaprvol.parquet",
    "trades_5_tp0.75_67_flat45_gaprvol.parquet",
]


def build_lookups():
    """Rebuild the exact bars/bands the EXP-0023 tapes were generated from."""
    bars = S.load_session("NQ", "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    vwap = bars.set_index(["sdate", "mfo"])["vwap"]
    band = bands.set_index(["sdate", "mfo"])[["upper", "lower"]]
    return vwap, band


def annotate(tr: pd.DataFrame, vwap: pd.Series, band: pd.DataFrame) -> pd.DataFrame:
    t = tr.copy()
    t["date"] = pd.to_datetime(t["date"])
    side = t["side"].to_numpy()

    def at(mfo_col: str, tag: str):
        idx = pd.MultiIndex.from_arrays(
            [t["date"].to_numpy(), t[mfo_col].astype(int).to_numpy()])
        v = vwap.reindex(idx).to_numpy()
        b = band.reindex(idx)
        up, lo = b["upper"].to_numpy(), b["lower"].to_numpy()
        edge = np.where(side == 1, up, lo)
        ref = np.where(side == 1, np.maximum(up, v), np.minimum(lo, v))
        # Mirror the engine: where the same-time-of-day band is undefined at this
        # exact mfo (strict rolling min_periods, rule 9a), the stop falls back to
        # VWAP only (engine2 have_band is False -> base = vwap).
        ref = np.where(np.isnan(edge), v, ref)
        t[f"{tag}_vwap"] = v
        t[f"{tag}_band"] = edge
        t[f"{tag}_stop_ref"] = ref

    at("entry_mfo", "entry")
    at("exit_mfo", "exit")
    t["entry_stop_pts"] = (t["entry_px"] - t["entry_stop_ref"]) * side
    return t


def main(inplace: bool = False):
    vwap, band = build_lookups()
    for fname in TAPES:
        fp = OUT / fname
        tr = pd.read_parquet(fp)
        t = annotate(tr, vwap, band)
        n_nan = int(t[["entry_vwap", "entry_band", "exit_vwap", "exit_band"]]
                    .isna().any(axis=1).sum())
        out_fp = fp if inplace else fp.with_name(fp.stem + "_enriched.parquet")
        t.to_parquet(out_fp, index=False)
        med = t["entry_stop_pts"].median()
        print(f"{fname:<40} n={len(t):>5} nan_rows={n_nan:>3} "
              f"median entry_stop_pts={med:+.2f} -> {out_fp.name}")


if __name__ == "__main__":
    main(inplace=(len(sys.argv) > 1 and sys.argv[1] == "inplace"))
