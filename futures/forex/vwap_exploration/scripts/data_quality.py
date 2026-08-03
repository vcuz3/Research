"""Rule-9a data-quality gate for the 6E/6B Databento archives.

Reports, per product and per era, everything a downstream feature could silently
depend on: bar coverage by session and by time of day, missing minutes, duplicate
and out-of-order timestamps, zero-volume bars, roll boundaries, and -- for the
windowed same-slot scale -- how often the window is under-populated and what the
construction does when it is.

Run:  python -m futures.forex.vwap_exploration.scripts.data_quality
Out:  reports/DATA_QUALITY.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import vwap as V

OUT = Path(__file__).resolve().parents[1] / "reports" / "DATA_QUALITY.txt"


def _p(lines, s=""):
    print(s)
    lines.append(s)


def report(product: str, lines: list[str]) -> None:
    _p(lines, "=" * 78)
    _p(lines, f"{product}  ({D.CONTRACT[product]['name']}, "
              f"{D.CONTRACT[product]['notional']:,.0f} notional, "
              f"${D.usd_per_pip(product):.2f} per pip)")
    _p(lines, "=" * 78)

    raw = D.add_session_columns(D._read_raw(product))
    _p(lines, f"raw rows                     {len(raw):,}")
    _p(lines, f"raw span (ET)                {raw['et'].min()}  ->  {raw['et'].max()}")

    dup = raw.duplicated(subset=["ts_event"]).sum()
    ooo = (raw["ts_event"].diff().dt.total_seconds() < 0).sum()
    _p(lines, f"duplicate timestamps         {dup:,}")
    _p(lines, f"out-of-order timestamps      {ooo:,}")
    halt = ((raw["mod"] >= 17 * 60) & (raw["mod"] < 18 * 60)).sum()
    _p(lines, f"bars inside 17:00-17:59 ET   {halt:,}  "
              f"({halt / len(raw):.6%})   [maintenance halt; expected ~0]")
    zv = (raw["volume"] == 0).sum()
    _p(lines, f"zero-volume bars             {zv:,}  ({zv / len(raw):.3%})")
    _p(lines, f"negative/NaN volume          {int((raw['volume'] < 0).sum() + raw['volume'].isna().sum()):,}"
              "   [spot FX archives are -1 on 100% of rows; futures must be 0]")
    bad_ohlc = ((raw["high"] < raw["low"]) | (raw["close"] > raw["high"])
                | (raw["close"] < raw["low"]) | (raw["open"] > raw["high"])
                | (raw["open"] < raw["low"])).sum()
    _p(lines, f"OHLC ordering violations     {bad_ohlc:,}")

    # ---- rolls -----------------------------------------------------------
    per = raw.groupby("sdate").agg(bars=("close", "size"),
                                   ninst=("instrument_id", "nunique"))
    _p(lines, "")
    _p(lines, f"trade dates                  {len(per):,}")
    _p(lines, f"  with >1 instrument_id      {int((per['ninst'] > 1).sum()):,}  "
              f"({(per['ninst'] > 1).mean():.2%})  [DROPPED: a session-anchored VWAP "
              "across a roll averages two contracts]")
    _p(lines, f"  with <400 bars             {int((per['bars'] < 400).sum()):,}  "
              "[DROPPED: holiday half-days / partial first session]")
    _p(lines, f"bars per session  min/p05/median/max   "
              f"{per['bars'].min()} / {per['bars'].quantile(.05):.0f} / "
              f"{per['bars'].median():.0f} / {per['bars'].max()}   "
              f"[a full session is {D.SESSION_MINUTES}]")

    # ---- loaded (explore scope) -----------------------------------------
    bars, rep = D.load_bars(product, scope="explore")
    _p(lines, "")
    _p(lines, f"EXPLORE scope (holdout {D.HOLDOUT_YEARS} sealed)")
    _p(lines, f"  rows                       {rep.rows:,}   "
              f"({rep.rows / rep.raw_rows:.2%} of raw)")
    _p(lines, f"  sessions                   {rep.sessions:,}")
    _p(lines, f"  span                       {rep.first_date.date()} -> {rep.last_date.date()}")
    hbars, hrep = D.load_bars(product, scope="holdout")
    _p(lines, f"  holdout sessions withheld  {hrep.sessions:,} "
              f"({hrep.first_date.date()} -> {hrep.last_date.date()})")

    # ---- coverage by time of day ----------------------------------------
    n_sess = bars["sdate"].nunique()
    cov = bars.groupby("mfo").size() / n_sess
    full = pd.Series(np.nan, index=np.arange(D.SESSION_MINUTES))
    full.loc[cov.index] = cov.to_numpy()
    _p(lines, "")
    _p(lines, "minute coverage by ET hour (share of sessions with a bar at that minute)")
    _p(lines, "   hour   mean    min     share of minutes <95%     median volume/bar")
    hr = ((np.arange(D.SESSION_MINUTES) + D.SESSION_OPEN_MOD) % 1440) // 60
    volm = bars.groupby("mfo")["volume"].median()
    for h in sorted(set(hr)):
        sel = hr == h
        c = full[sel]
        vm = volm.reindex(np.arange(D.SESSION_MINUTES)[sel]).median()
        _p(lines, f"   {h:02d}:00  {c.mean():.3f}  {c.min():.3f}   "
                  f"{(c < 0.95).mean():16.1%}   {vm:>10.0f}")

    # is a low-coverage minute a market fact or a download artifact?
    low = full[full < 0.95]
    if len(low):
        minute_of_hour = ((low.index + D.SESSION_OPEN_MOD) % 60)
        vc = pd.Series(minute_of_hour).value_counts()
        _p(lines, f"   {len(low)} minutes below 95% coverage; top minute-of-hour: "
                  f"{dict(vc.head(3))}")
        _p(lines, "   [a spike concentrated on one minute-of-hour is a download "
                  "chunk artifact, not liquidity -- see forex/noise_vwap]")

    # ---- windowed feature: under-population of the same-slot scale --------
    b = V.add_deviations(V.add_anchors(bars), anchors=("vwap",))
    z = b["dev_vwap_z"]
    _p(lines, "")
    _p(lines, f"same-slot scale (lookback {V.SLOT_LOOKBACK} sessions, "
              f"min_periods = ceil({V.SLOT_MIN_FRAC:.3f} * lookback) "
              f"= {int(np.ceil(V.SLOT_MIN_FRAC * V.SLOT_LOOKBACK))})")
    _p(lines, f"  decision points with a defined z   {int(z.notna().sum()):,} / {len(b):,}"
              f"  ({z.notna().mean():.2%})")
    lost = b.loc[z.isna()]
    _p(lines, f"  lost to the warm-up (first sessions) {int(lost['sdate'].nunique())} sessions")
    _p(lines, "  loss by ET hour   [rule 9a: the PASS signal is a UNIFORM loss; a loss "
              "that tracks time-of-day liquidity is a hidden filter]")
    lb = b.assign(bad=z.isna()).groupby(((b["mfo"] + D.SESSION_OPEN_MOD) % 1440) // 60)["bad"].mean()
    _p(lines, "   " + "  ".join(f"{h:02d}h={v:.3f}" for h, v in lb.items()))
    _p(lines, f"  loss spread across hours: max-min = {lb.max() - lb.min():.4f}")

    # ---- era table -------------------------------------------------------
    _p(lines, "")
    _p(lines, "per-year coverage and economics")
    _p(lines, "   year  sessions   bars/sess   median vol/bar   tick      $/tick")
    for y, g in bars.groupby(bars["sdate"].dt.year):
        ts = D.tick_size(product, int(y))
        _p(lines, f"   {y}     {g['sdate'].nunique():5d}      {len(g) / g['sdate'].nunique():7.1f}"
                  f"   {g['volume'].median():12.0f}   {ts:.5f}   "
                  f"{ts / 1e-4 * D.usd_per_pip(product):7.2f}")
    _p(lines, "")


def main() -> int:
    lines: list[str] = []
    for p in D.PRODUCTS:
        report(p, lines)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
