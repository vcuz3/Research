"""
Data-quality gate for the NQ/ES Noise-Area + VWAP baseline, focused on the
CONTINUOUS (every-bar) stop (RULES.md rule 9a).

core/data.py builds the noise band with `rolling(lookback, min_periods=lookback)`
(strict: EVERY one of the prior `lookback` sessions must have a bar at that exact
minute, or the band is null for that (date,tod)). On GC this silently deleted up
to 28% of late-day decisions (see futures/gc/noise_vwap/reports/DATA_QUALITY.md).
NQ is liquid enough that it "barely bites" -- this gate quantifies exactly how
much, and does it for the surface the CONTINUOUS stop actually touches.

Why the continuous stop widens the 9a surface: engine.simulate_session looks up
`band_map.get(t)` and `continue`s when it is None (engine.py:108-110). With
exit_check="every_bar" the stop is checked at EVERY RTH minute a position is open,
so a strict-nulled band at ANY intermediate minute silently SKIPS the stop check
there -- the position rides unprotected to the next minute with a valid band. The
relevant coverage is therefore all RTH minutes 599..958, not just the 12 decision
tods.

This gate REPORTS (it does not change core.data). It emits, per minute:
  * raw coverage (fraction of sessions with a bar at that minute);
  * strict band coverage (current NQ rule) vs a relaxed ceil(0.9*lookback) rule;
  * decision points nulled at entry tods, and exit-check bars nulled for the
    continuous stop, and how many each the relaxed rule would recover.

Reproduce:  python -m futures.nq.noise_vwap.scripts.data_quality NQ 90
"""
from __future__ import annotations

import sys
import math
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, RTH_START, RTH_END, PATHS
from ..core.engine import DECISION_TODS

BAND_MIN_FRAC = 0.90   # the relaxed rule this gate compares against (not yet in core)


def _band_rows(bars: pd.DataFrame, lookback: int, min_periods: int) -> pd.DataFrame:
    """noise_bands' sigma construction with a configurable min_periods, so we can
    compare the STRICT (all-lookback) rule against a relaxed fractional one."""
    opens = bars[bars["tod"] == RTH_START].set_index("date")["open"]
    last = bars.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
    dates = bars["date"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)
    cm = bars.pivot_table(index="date", columns="tod", values="close",
                          aggfunc="last").reindex(dates)
    o0 = opens.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()
    sigma = move.shift(1).rolling(lookback, min_periods=min_periods).mean()
    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["date", "tod", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="date").merge(
        prior_close.rename("prior_close"), on="date")
    return long.dropna(subset=["rth_open", "prior_close", "sigma"])


def hhmm(t: int) -> str:
    return f"{t // 60:02d}:{t % 60:02d}"


def main() -> None:
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    relaxed_mp = math.ceil(BAND_MIN_FRAC * lookback)

    raw = pd.read_parquet(PATHS[inst])
    bars = load_rth(inst)
    ndays = bars["date"].nunique()
    issues: list[str] = []

    print(f"=== DATA-QUALITY GATE: {inst} lookback={lookback} continuous stop (rule 9a) ===")
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

    # --- band coverage: strict (current) vs relaxed ---------------------------
    cov = bars.groupby("tod")["date"].nunique() / ndays           # raw per-minute
    strict = _band_rows(bars, lookback, lookback).groupby("tod").size()
    relaxed = _band_rows(bars, lookback, relaxed_mp).groupby("tod").size()

    # The continuous stop is checked at every RTH minute a position can be open:
    # from the first decision (599) up to the last-but-one bar (958). All of these
    # minutes need a band or the every-bar stop is silently skipped there.
    first_dec = min(DECISION_TODS)
    exit_minutes = sorted(t for t in cov.index if first_dec <= t <= RTH_END - 2)

    # aggregate silent-null counts over the whole continuous-stop surface
    strict_bandcells = int(_band_rows(bars, lookback, lookback)
                           .query("@first_dec <= tod <= @RTH_END - 2").shape[0])
    relaxed_bandcells = int(_band_rows(bars, lookback, relaxed_mp)
                            .query("@first_dec <= tod <= @RTH_END - 2").shape[0])
    # potential cells = sessions that actually have a bar at each exit minute,
    # counted only where the lookback history exists (band could be defined)
    exit_raw_cells = int(bars[(bars["tod"] >= first_dec) &
                              (bars["tod"] <= RTH_END - 2)].shape[0])

    print(f"\n[continuous-stop band coverage]  strict=all-{lookback}  "
          f"relaxed>=ceil({BAND_MIN_FRAC:.2f}*{lookback})={relaxed_mp}")
    print(f"  exit-check minutes {hhmm(first_dec)}..{hhmm(RTH_END-2)} "
          f"({len(exit_minutes)} distinct minutes)")
    print(f"  band cells present  strict={strict_bandcells}  relaxed={relaxed_bandcells}  "
          f"recovered={relaxed_bandcells - strict_bandcells}")

    # per-minute table for the ENTRY decision tods (entries), where a null band
    # deletes a whole potential trade (the GC failure mode).
    print(f"\n[entry decision-tod coverage]")
    print(f"{'tod':>5} {'time':>6} {'raw_cov':>8} {'strict':>8} {'relaxed':>8} {'recovered':>10}")
    tot_entry_rec = 0
    for t in DECISION_TODS:
        s = int(strict.get(t, 0)); r = int(relaxed.get(t, 0)); rec = r - s
        tot_entry_rec += rec
        flag = "  <== silent-drop" if s / ndays < 0.95 else ""
        print(f"{t:>5} {hhmm(t):>6} {100*cov.get(t,0):>7.1f}% "
              f"{100*s/ndays:>7.1f}% {100*r/ndays:>7.1f}% {rec:>+10d}{flag}")
    print(f"{'':>5} {'TOTAL':>6} {'':>8} {'':>8} {'':>8} {tot_entry_rec:>+10d} entry decisions recovered")

    # worst intermediate (non-decision) exit minute -- the continuous-stop-only risk
    inter = [t for t in exit_minutes if t not in set(DECISION_TODS)]
    if inter:
        worst = min(inter, key=lambda t: strict.get(t, 0) / ndays)
        ws = strict.get(worst, 0) / ndays
        print(f"\n[worst intermediate exit minute] {hhmm(worst)}: raw {100*cov.get(worst,0):.1f}% "
              f"strict-band {100*ws:.1f}% relaxed-band {100*relaxed.get(worst,0)/ndays:.1f}%")

    # Two very different causes of a missing strict band on the exit surface:
    #   (a) WARM-UP: the first ~lookback sessions have no band at ANY minute. But
    #       entries also need a band, so no position is open then -> nothing is
    #       actually skipped. This is not a defect, just unusable early history.
    #   (b) TRAILING-WINDOW GAP: history exists (relaxed band present) but a single
    #       missing minute in the trailing strict window nulls the strict band.
    #       THIS is the real silent skip -- a live trailing position rides that bar
    #       without an every-bar stop check. It equals the strict->relaxed recovery.
    coarse_skip = exit_raw_cells - strict_bandcells        # includes warm-up (upper bound)
    gap_skip = relaxed_bandcells - strict_bandcells        # genuine live-trading skip
    print(f"\n[continuous-stop skipped checks] over {hhmm(first_dec)}..{hhmm(RTH_END-2)}:")
    print(f"  genuine gap-nulls (history exists, strict window has a hole): {gap_skip} "
          f"bar-minutes = {100*gap_skip/max(relaxed_bandcells,1):.2f}% of live band cells")
    print(f"  incl. warm-up (no band yet, no position open -> not a real skip): "
          f"{coarse_skip} ({100*coarse_skip/max(exit_raw_cells,1):.2f}%, upper bound)")

    # --- verdict --------------------------------------------------------------
    worst_dec = min(DECISION_TODS, key=lambda t: strict.get(t, 0) / ndays)
    # measure the entry-decision bite ABOVE the shared warm-up floor (uniform across
    # tods): a genuinely bitten tod sits materially below its peers.
    strict_frac = {t: strict.get(t, 0) / ndays for t in DECISION_TODS}
    floor = max(strict_frac.values())                      # best tod ~ warm-up-only
    worst_extra = floor - strict_frac[worst_dec]           # gap bite beyond warm-up
    if worst_extra > 0.01:
        issues.append(
            f"strict band nulls an EXTRA {100*worst_extra:.1f}% of {hhmm(worst_dec)} entry "
            f"decisions beyond the {100*(1-floor):.1f}% warm-up floor (trailing-window gaps); "
            f"relaxed rule recovers {tot_entry_rec} entry decisions and levels coverage")
    if gap_skip / max(relaxed_bandcells, 1) > 0.01:
        issues.append(
            f"continuous stop skips its every-bar check on {100*gap_skip/relaxed_bandcells:.2f}% "
            f"of live band cells (strict-window gaps null the band), concentrated at lunch")

    print("\n=== ISSUES ===")
    if issues:
        for i in issues:
            print(f"  * {i}")
    else:
        print("  none material (strict min_periods barely bites on NQ liquidity)")


if __name__ == "__main__":
    main()
