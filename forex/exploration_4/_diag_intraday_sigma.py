"""Intraday sigma profile and what it does to cost in the SIZING unit.

Computed for the Stage-A -> Stage-B handoff (RUNBOOK §4.3). Same-slot normalisation
makes the ENTRY clock-neutral but makes the COST clock-DEPENDENT in R terms, because
sigma_slot tracks the intraday profile while the modelled round trip is roughly flat
in pips. A gross figure in R_slot against a cost in pips is not a net result.

    python -u forex/exploration_4/_diag_intraday_sigma.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT.parent / "exploration_1"))

from _run_rsi_broad_regime_sweep import PIP  # noqa: E402

DATA = PROJECT.parent / "data" / "clean"
OUT = PROJECT / "artifacts" / "runs" / "EXP-0003" / "intraday_sigma_profile.csv"
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
TAU, ROUND_TRIP_PIPS, SIGMA_ABS_PIPS = 5, 1.2, 3.17


def main() -> None:
    cols = []
    for pair in PAIRS:
        d = pd.read_parquet(DATA / f"{pair}_1m_clean.parquet", columns=["ts_utc", "close"])
        s = d.set_index(pd.DatetimeIndex(d.ts_utc)).close
        bars = s.resample(f"{TAU}min", origin="epoch", label="left", closed="left").agg(["last", "count"])
        bars = bars.where(bars["count"].eq(TAU))              # complete bars only
        ret = bars["last"].pct_change(fill_method=None)
        ret = ret[(ret.index >= pd.Timestamp("2012-01-01")) & (ret.index < pd.Timestamp("2024-01-01"))]
        px = bars["last"].reindex(ret.index)
        cols.append((ret * px / PIP).groupby(ret.index.hour).std().rename(pair))

    t = pd.concat(cols, axis=1)
    t.index.name = "utc_hour"
    t["mean_sigma_slot_pips"] = t[PAIRS].mean(axis=1)
    t["cost_in_R_slot"] = ROUND_TRIP_PIPS / t.mean_sigma_slot_pips
    t["cost_in_R_abs"] = ROUND_TRIP_PIPS / SIGMA_ABS_PIPS
    t.round(4).to_csv(OUT)

    lo, hi = t.mean_sigma_slot_pips.min(), t.mean_sigma_slot_pips.max()
    c = t.cost_in_R_slot
    print(t[["mean_sigma_slot_pips", "cost_in_R_slot", "cost_in_R_abs"]].round(3).to_string())
    print(f"\nsigma_slot {lo:.2f}-{hi:.2f} pips ({hi / lo:.1f}x); "
          f"a {ROUND_TRIP_PIPS} pip round trip costs {c.min():.3f}-{c.max():.3f} R_slot "
          f"({c.max() / c.min():.1f}x) vs a flat {t.cost_in_R_abs.iloc[0]:.3f} R_abs")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
