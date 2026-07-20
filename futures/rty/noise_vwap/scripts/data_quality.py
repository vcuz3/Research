"""
Data-quality gate for the RTY Noise-Area + VWAP baseline (RULES.md rule 9a).

Runs at the data-load / feature-construction stage and REPORTS what it finds, so
a coverage defect can never again hide inside the band construction. Emits, for the
RTH 1-min RTY data and the same-time-of-day noise band:

  * session and bar coverage, date range, roll-boundary check;
  * duplicate / out-of-order / gap diagnostics on the RTH timeline;
  * per-decision-minute RAW coverage (fraction of sessions that have that minute);
  * per-decision-minute BAND coverage under the STRICT (all-`lookback`) rule vs the
    relaxed `BAND_MIN_FRAC` rule now in core.data, and how many decision points the
    relaxation recovers -- the exact silent-deletion this gate exists to surface.

Reproduce the report:  python -m futures.rty.noise_vwap.scripts.data_quality RTY 90
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import (load_rth, noise_bands, BAND_MIN_FRAC, RTH_START, RTH_END,
                         PATHS)
from ..core.engine import DECISION_TODS


def _strict_band_rows(bars: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """The OLD construction: require ALL `lookback` prior sessions at a minute
    (min_periods == lookback). Used only to quantify what the relaxation recovers."""
    opens = bars[bars["tod"] == RTH_START].set_index("date")["open"]
    last = bars.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
    dates = bars["date"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)
    cm = bars.pivot_table(index="date", columns="tod", values="close", aggfunc="last").reindex(dates)
    o0 = opens.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()
    sigma = move.shift(1).rolling(lookback, min_periods=lookback).mean()
    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["date", "tod", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="date").merge(
        prior_close.rename("prior_close"), on="date")
    return long.dropna(subset=["rth_open", "prior_close", "sigma"])


def hhmm(t: int) -> str:
    return f"{t // 60:02d}:{t % 60:02d}"


def main() -> None:
    inst = sys.argv[1] if len(sys.argv) > 1 else "RTY"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90

    raw = pd.read_parquet(PATHS[inst])
    bars = load_rth(inst)
    ndays = bars["date"].nunique()
    issues: list[str] = []

    print(f"=== DATA-QUALITY GATE: {inst} lookback={lookback} (rule 9a) ===")
    print(f"raw rows={len(raw)} | RTH bars={len(bars)} | sessions={ndays} "
          f"| {bars['date'].min().date()} -> {bars['date'].max().date()}")

    # --- timeline integrity ---------------------------------------------------
    dup = int(bars.duplicated(subset=["date", "tod"]).sum())
    ooo = int((bars.sort_values("et").groupby("date")["tod"].diff() < 0).sum())
    if dup:
        issues.append(f"{dup} duplicate (date,tod) rows")
    if ooo:
        issues.append(f"{ooo} out-of-order bars within a session")
    print(f"\n[timeline] duplicate (date,tod)={dup} | out-of-order within day={ooo}")

    # roll boundaries inside a session (contract economics, rule 11)
    if "symbol" in bars.columns:
        nsym = bars.groupby("date")["symbol"].nunique()
        roll_in_session = int((nsym > 1).sum())
        if roll_in_session:
            issues.append(f"{roll_in_session} sessions span a contract roll")
        print(f"[roll] sessions spanning >1 symbol={roll_in_session}")

    # --- per-session RTH minute completeness ----------------------------------
    full = RTH_END - RTH_START  # 390 minutes in a full RTH session
    per_day = bars.groupby("date")["tod"].nunique()
    missing_per_day = (full - per_day)
    print(f"\n[completeness] full RTH minutes={full} | median present={int(per_day.median())} "
          f"| sessions with >=1 missing minute={int((missing_per_day > 0).sum())} "
          f"({100 * (missing_per_day > 0).mean():.1f}%)")
    print(f"               missing-minute per session: mean={missing_per_day.mean():.2f} "
          f"max={int(missing_per_day.max())}")

    # --- decision-minute coverage + band recovery -----------------------------
    dset = sorted(DECISION_TODS)
    cov = bars.groupby("tod")["date"].nunique() / ndays
    relaxed = noise_bands(bars, lookback).groupby("tod").size()
    strict = _strict_band_rows(bars, lookback).groupby("tod").size()

    print(f"\n[decision-minute band coverage]  strict=all-{lookback}  "
          f"relaxed>=ceil({BAND_MIN_FRAC:.2f}*{lookback})={int(np.ceil(BAND_MIN_FRAC*lookback))}")
    print(f"{'tod':>5} {'time':>6} {'raw_cov':>8} {'strict':>8} {'relaxed':>8} {'recovered':>10}")
    total_rec = 0
    for t in dset:
        s = int(strict.get(t, 0)); r = int(relaxed.get(t, 0)); rec = r - s
        total_rec += rec
        flag = "  <== silent-drop" if s / ndays < 0.95 else ""
        print(f"{t:>5} {hhmm(t):>6} {100*cov.get(t,0):>7.1f}% "
              f"{100*s/ndays:>7.1f}% {100*r/ndays:>7.1f}% {rec:>+10d}{flag}")
    print(f"{'':>5} {'TOTAL':>6} {'':>8} {'':>8} {'':>8} {total_rec:>+10d} decision points recovered")

    worst = min(dset, key=lambda t: strict.get(t, 0) / ndays)
    if strict.get(worst, 0) / ndays < 0.95:
        issues.append(
            f"strict band nulls {100*(1-strict.get(worst,0)/ndays):.0f}% of {hhmm(worst)} "
            f"decisions despite {100*cov.get(worst,0):.1f}% raw coverage; relaxed rule recovers "
            f"{total_rec} decision points total")

    # --- verdict --------------------------------------------------------------
    print("\n=== ISSUES ===")
    if issues:
        for i in issues:
            print(f"  * {i}")
    else:
        print("  none")


if __name__ == "__main__":
    main()
