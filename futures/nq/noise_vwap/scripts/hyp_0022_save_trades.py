"""EXP-0032: dump per-trade rows for the analysed variants to one parquet.

Combines the deployed close-confirmed continuous stop (1m engine) with the 1s
first-touch ATR-buffer variants, each tagged by ``variant``, into
artifacts/runs/EXP-0032/trades.parquet.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands
from ..core.engine import run as run_1m
from ..core.atr_buffer import ONE_SECOND_PATH, run_streaming_atr, intraday_atr

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0032"


def main():
    bars = load_rth("NQ")
    bands = noise_bands(bars, 90)
    eligible = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    bars_e = bars[bars["date"].isin(eligible)].copy()

    c = float(1.5 * np.nanmedian(intraday_atr(bars_e, [20])["atr_20"].to_numpy()))
    specs = [("N20_k1.5", 20, 1.5), ("fixed_matched", "const1", c),
             ("k0_first_touch", 5, 0.0)]
    print(f"Scanning 1s for {len(specs)} buffered variants (fixed c={c:.3f} pts) ...")
    tr, _ = run_streaming_atr(ONE_SECOND_PATH, bars_e, bands, specs)

    cc = run_1m(bars_e, bands, exit_check="every_bar")

    parts = []
    cc = cc.assign(variant="close_confirmed_1m", resolution="1m")
    parts.append(cc)
    for nm, _, _ in specs:
        parts.append(tr[nm].assign(variant=nm, resolution="1s"))
    out = pd.concat(parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["variant", "date"]).reset_index(drop=True)

    path = OUT / "trades.parquet"
    out.to_parquet(path, index=False)
    print(f"\nwrote {path}  ({len(out):,} rows, {out['variant'].nunique()} variants)")
    print(out.groupby("variant").agg(
        trades=("points", "size"), gross_pts=("points", "sum"),
        mean_pt=("points", "mean")).round(3).to_string())
    print("\ncolumns:", list(out.columns))


if __name__ == "__main__":
    main()
