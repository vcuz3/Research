"""Data layer for the cross-asset macro exploration (DXY / GC / ES / NQ).

Everything here is a *measurement* frame: one row per RTH 1-minute bar, or one row
per (session, decision-slot). Nothing trades.

Three jobs:

1. ``load_1m`` -- read a Databento v0 continuous 1-minute file into a uniform
   ``ts_utc | open | high | low | close | volume | instrument_id | is_roll`` frame.
   The v0 continuous series splices contracts, so the bar at a contract change
   carries a fake ~35 bp jump (measured: median |r| at a 6E roll is 3.6e-3 versus
   7.3e-5 off-roll, ~49x). Every return this module produces is NaN on a roll bar
   (rule 11).

2. ``build_dollar_index`` -- a synthetic, causal DXY from the CME FX futures legs.
   ICE's index is the geometric basket

       DXY = 50.14348112 * EURUSD^-0.576 * USDJPY^+0.136 * GBPUSD^-0.119
                         * USDCAD^+0.091 * USDSEK^+0.042 * USDCHF^+0.036

   Every CME leg (6E, 6J, 6B, 6C, 6S) is quoted as *USD per unit of foreign
   currency*, so USDJPY = 1/6J and USDCAD = 1/6C. Substituting, EVERY leg enters
   log DXY with a NEGATIVE coefficient:

       log DXY = const - SUM_i w_i * log(F_i)

   SEK has no CME contract, so the available weights are renormalised to sum to 1.
   The weights are PUBLISHED and FIXED, never fitted -- a PCA "dollar factor"
   estimated on the full sample would be a two-sided statistic (rule 8).

3. ``rth_panel`` -- align any set of instruments onto the equity RTH 09:30-16:00 ET
   1-minute grid, which is the clock every study in this workspace uses and the
   window where gold's tradable behaviour is known to live.

Alignment policy (this is a data-quality decision, not an implementation detail --
rule 9a). Each instrument is reindexed onto the common RTH minute grid and
forward-filled up to ``FFILL_LIMIT`` minutes. Forward-filling is unavoidable when
combining five FX legs of unequal liquidity, but it induces *stale prices*, which
mechanically manufacture positive autocorrelation and fake cross-asset lead-lag.
``coverage_report`` therefore counts every filled minute per leg, per era and per
time of day, and any lead-lag claim in this project must be re-run on the
EUR-only proxy (the thickest leg) as a staleness control.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]           # .../futures/nq/claude_exploration_1
DB = ROOT.parents[1] / "data" / "databento"          # Research/futures/data/databento

# Databento v0 (volume-rank-0) continuous 1-minute files.
RAW: dict[str, str] = {
    "NQ": "NQ_ohlcv-1m_NQv0_20110801_20260715.parquet",
    "ES": "ES_ohlcv-1m_ESv0_20110801_20260715.parquet",
    "GC": "GC_ohlcv-1m_GCv0_20110801_20260717.parquet",
    "6E": "6E_ohlcv-1m_6Ev0_20100606_20260728.parquet",
    "6J": "6J_ohlcv-1m_6Jv0_20100606_20260728.parquet",
    "6B": "6B_ohlcv-1m_6Bv0_20100606_20260728.parquet",
    "6C": "6C_ohlcv-1m_6Cv0_20100606_20260728.parquet",
    "6S": "6S_ohlcv-1m_6Sv0_20100606_20260728.parquet",
}

# ICE DXY weights, keyed by the CME leg that prices the pair.
DXY_WEIGHTS: dict[str, float] = {
    "6E": 0.576,   # EUR
    "6J": 0.136,   # JPY
    "6B": 0.119,   # GBP
    "6C": 0.091,   # CAD
    "6S": 0.036,   # CHF
}                  # SEK 0.042 has no CME contract.

# PRIMARY basket = the four thick legs. CHF carries only 3.6% of the index but its
# CME contract is by far the thinnest (median 17 lots/RTH-minute vs 130 for 6E), and
# including it more than DOUBLES the share of forward-filled minutes (10.47% -> 4.70%
# when dropped) while changing the 30-minute dollar return almost not at all
# (corr 0.9992). Staleness manufactures autocorrelation and fake lead-lag, which are
# exactly the effects this project measures, so the thin leg is a pure liability.
# ``DXY_LEGS_5`` and ``DXY_LEGS_EUR`` exist as preregistered sensitivity arms.
DXY_LEGS = ("6E", "6J", "6B", "6C")
DXY_LEGS_5 = ("6E", "6J", "6B", "6C", "6S")
DXY_LEGS_EUR = ("6E",)

RTH_START = 9 * 60 + 30      # 09:30 ET, minutes from midnight
RTH_END = 16 * 60            # 16:00 ET (exclusive)
RTH_MINUTES = RTH_END - RTH_START      # 390
MIN_BARS = 350               # near-complete equity sessions only
FFILL_LIMIT = 5              # minutes a stale quote may be carried

# Databento-flagged degraded equity sessions; identical list to vei_exploration and
# hurst_explore so cross-project comparisons run on the same calendar.
DEGRADED = {
    "2014-06-11", "2014-06-12", "2014-06-13", "2017-11-13", "2018-10-21",
    "2019-01-15", "2019-02-22", "2020-02-27", "2020-02-28", "2020-06-30",
    "2020-07-01", "2021-12-05", "2022-01-02", "2025-09-17", "2025-09-24",
    "2025-11-28",
}
_DEGRADED = {pd.Timestamp(d) for d in DEGRADED}


# --------------------------------------------------------------------------- #
# raw loading
# --------------------------------------------------------------------------- #
def load_1m(sym: str) -> pd.DataFrame:
    """Full-24h 1-minute bars for one instrument, indexed by tz-aware UTC minute.

    ``is_roll`` marks the first bar of a new contract. Duplicated minutes keep the
    last observation; non-positive or missing OHLC rows are dropped (defensive --
    Databento is already clean).
    """
    df = pd.read_parquet(
        DB / RAW[sym],
        columns=["ts_event", "instrument_id", "open", "high", "low", "close", "volume"],
    )
    df = df.rename(columns={"ts_event": "ts_utc"})
    if df["ts_utc"].dt.tz is None:
        df["ts_utc"] = df["ts_utc"].dt.tz_localize("UTC")
    ohlc = ["open", "high", "low", "close"]
    bad = df[ohlc].isna().any(axis=1) | (df[ohlc] <= 0).any(axis=1)
    df = df[~bad]
    df = df.drop_duplicates(subset=["ts_utc"], keep="last").sort_values("ts_utc")
    df = df.set_index("ts_utc")
    df["is_roll"] = df["instrument_id"].ne(df["instrument_id"].shift(1))
    df.iloc[0, df.columns.get_loc("is_roll")] = True
    return df


def log_return(df: pd.DataFrame) -> pd.Series:
    """Bar-to-bar log return with roll bars set to NaN (rule 11).

    NaN rather than 0 so a caller that chains returns has to make the splice policy
    explicit rather than inheriting a silent zero.
    """
    r = np.log(df["close"]).diff()
    return r.mask(df["is_roll"].to_numpy(bool))


def continuous_log_level(df: pd.DataFrame) -> pd.Series:
    """Roll-adjusted log price level: cumulative sum of non-roll log returns.

    Equivalent to multiplicative back-adjustment, anchored so the first bar equals
    the raw log close. Only DIFFERENCES of this series are ever used, so the anchor
    is immaterial; what matters is that no roll jump survives into a return.
    """
    r = log_return(df).fillna(0.0)
    return float(np.log(df["close"].iloc[0])) + r.cumsum()


# --------------------------------------------------------------------------- #
# RTH grid
# --------------------------------------------------------------------------- #
def _rth_index(df: pd.DataFrame) -> pd.DataFrame:
    """Attach ET session date / time-of-day / minutes-from-open, RTH rows only."""
    et = df.index.tz_convert("America/New_York")
    tod = et.hour * 60 + et.minute
    m = (tod >= RTH_START) & (tod < RTH_END)
    out = df[m].copy()
    out["sdate"] = et[m].normalize().tz_localize(None)
    out["mfo"] = (tod[m] - RTH_START).astype(int)
    return out


def equity_sessions(anchor: str = "ES") -> pd.DatetimeIndex:
    """The session calendar: near-complete, non-degraded equity RTH sessions.

    The equity clock is the anchor for the whole project. Gold and the dollar trade
    around it, but every decision in this project is made at an equity RTH minute,
    so the anchor's own coverage defines what a valid session is.
    """
    b = _rth_index(load_1m(anchor))
    n = b.groupby("sdate").size()
    keep = n.index[(n >= MIN_BARS) & (~n.index.isin(_DEGRADED))]
    return pd.DatetimeIndex(sorted(keep))


def _grid(sessions: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """The common RTH minute grid (UTC) for the given ET session dates."""
    et = pd.DatetimeIndex(
        np.repeat(sessions.values, RTH_MINUTES)
    ) + pd.to_timedelta(
        np.tile(np.arange(RTH_START, RTH_END), len(sessions)), unit="m"
    )
    return et.tz_localize("America/New_York", nonexistent="shift_forward",
                          ambiguous=True).tz_convert("UTC")


# --------------------------------------------------------------------------- #
# synthetic dollar index
# --------------------------------------------------------------------------- #
def build_dollar_index(grid: pd.DatetimeIndex, legs=DXY_LEGS,
                       ffill_limit: int = FFILL_LIMIT
                       ) -> tuple[pd.Series, pd.DataFrame]:
    """Causal synthetic log-DXY on ``grid``, plus a per-leg fill diagnostic.

    ``log DXY = -SUM_i w_i * log(F_i)`` with published ICE weights renormalised over
    the supplied legs. Each leg's roll-adjusted log level is reindexed onto the grid
    and forward-filled at most ``ffill_limit`` minutes; a minute where any leg is
    still missing yields NaN, so the index never mixes different staleness policies
    across legs.

    Returns ``(log_dxy, fills)`` where ``fills`` is a boolean frame -- True where
    that leg's value at that minute came from a forward fill rather than a bar.
    """
    w = np.array([DXY_WEIGHTS[l] for l in legs], dtype=float)
    w = w / w.sum()
    lvl = pd.DataFrame(index=grid, dtype=float)
    fills = pd.DataFrame(index=grid, dtype=bool)
    for leg, wi in zip(legs, w):
        s = continuous_log_level(load_1m(leg))
        s = s[~s.index.duplicated(keep="last")]
        exact = s.reindex(grid)
        filled = s.reindex(grid, method="ffill", limit=ffill_limit)
        lvl[leg] = filled * (-wi)
        fills[leg] = exact.isna() & filled.notna()
    log_dxy = lvl.sum(axis=1, skipna=False)
    log_dxy.name = "log_dxy"
    return log_dxy, fills


# --------------------------------------------------------------------------- #
# the aligned panel
# --------------------------------------------------------------------------- #
def rth_panel(instruments=("ES", "NQ", "GC"), legs=DXY_LEGS,
              ffill_limit: int = FFILL_LIMIT, anchor: str = "ES"
              ) -> tuple[pd.DataFrame, dict]:
    """One row per (session, RTH minute) with roll-adjusted log levels for each
    instrument plus the synthetic log dollar index.

    Columns: ``sdate``, ``mfo``, ``lp_<INST>`` (roll-adjusted log price),
    ``vol_<INST>`` (bar volume), ``log_dxy``, ``stale_dxy`` (any leg forward-filled
    at this minute), ``stale_<INST>``.

    The second return value is a coverage dictionary for the rule-9a report.
    """
    sessions = equity_sessions(anchor)
    grid = _grid(sessions)
    out = pd.DataFrame(index=grid)
    et = grid.tz_convert("America/New_York")
    out["sdate"] = et.normalize().tz_localize(None)
    out["mfo"] = (et.hour * 60 + et.minute - RTH_START).astype(int)

    cov: dict[str, object] = {"n_sessions": len(sessions), "n_grid_minutes": len(grid)}
    for inst in instruments:
        df = load_1m(inst)
        s = continuous_log_level(df)
        s = s[~s.index.duplicated(keep="last")]
        exact = s.reindex(grid)
        out[f"lp_{inst}"] = s.reindex(grid, method="ffill", limit=ffill_limit)
        out[f"stale_{inst}"] = exact.isna() & out[f"lp_{inst}"].notna()
        v = df["volume"].astype(float)
        v = v[~v.index.duplicated(keep="last")]
        out[f"vol_{inst}"] = v.reindex(grid).fillna(0.0)
        cov[f"missing_{inst}"] = int(exact.isna().sum())
        cov[f"stale_{inst}"] = int(out[f"stale_{inst}"].sum())
        cov[f"unfilled_{inst}"] = int(out[f"lp_{inst}"].isna().sum())

    log_dxy, fills = build_dollar_index(grid, legs=legs, ffill_limit=ffill_limit)
    out["log_dxy"] = log_dxy
    out["stale_dxy"] = fills.any(axis=1)
    for leg in legs:
        cov[f"stale_{leg}"] = int(fills[leg].sum())
    cov["unfilled_dxy"] = int(log_dxy.isna().sum())
    cov["legs"] = list(legs)
    cov["ffill_limit"] = ffill_limit
    return out.reset_index(drop=True), cov


def coverage_report(panel: pd.DataFrame, cov: dict) -> str:
    """Rule-9a data-quality text: coverage, staleness and rolls per era and slot.

    A silently forward-filled or dropped minute is a reportable finding, not an
    implementation detail. Staleness is broken out by time of day because the FX
    legs thin out at different hours than the equity legs do, and by era because
    electronic liquidity in 6B/6C/6S changed materially over the sample.
    """
    L: list[str] = []
    n = len(panel)
    L.append("=== rule 9a: coverage / staleness / integrity ===")
    L.append(f"sessions={cov['n_sessions']}  grid minutes={n:,}  "
             f"legs={cov['legs']}  ffill_limit={cov['ffill_limit']}m")
    L.append("")
    L.append(f"{'series':<10}{'missing bars':>14}{'stale (ffill)':>15}"
             f"{'still NaN':>11}{'stale %':>9}")
    for k in [c[3:] for c in panel.columns if c.startswith("lp_")]:
        L.append(f"{k:<10}{cov[f'missing_{k}']:>14,}{cov[f'stale_{k}']:>15,}"
                 f"{cov[f'unfilled_{k}']:>11,}{100*cov[f'stale_{k}']/n:>8.2f}%")
    for leg in cov["legs"]:
        L.append(f"{leg:<10}{'-':>14}{cov[f'stale_{leg}']:>15,}{'-':>11}"
                 f"{100*cov[f'stale_{leg}']/n:>8.2f}%")
    L.append(f"{'DXY':<10}{'-':>14}{int(panel['stale_dxy'].sum()):>15,}"
             f"{cov['unfilled_dxy']:>11,}{100*panel['stale_dxy'].mean():>8.2f}%")
    L.append("")

    yr = panel["sdate"].dt.year
    L.append("stale-minute share by era (any DXY leg / each instrument):")
    cols = ["stale_dxy"] + [c for c in panel.columns if c.startswith("stale_")
                            and c != "stale_dxy"]
    L.append("  " + f"{'year':<6}" + "".join(f"{c[6:]:>10}" for c in cols)
             + f"{'rows':>9}")
    for y, g in panel.groupby(yr):
        L.append("  " + f"{y:<6}" + "".join(f"{100*g[c].mean():>9.1f}%" for c in cols)
                 + f"{len(g):>9,}")
    L.append("")

    L.append("stale-minute share by 30-min block (pooled over sessions):")
    blk = (panel["mfo"] // 30) * 30
    L.append("  " + f"{'mfo':<6}" + "".join(f"{c[6:]:>10}" for c in cols)
             + f"{'rows':>9}")
    for b, g in panel.groupby(blk):
        L.append("  " + f"{b:<6}" + "".join(f"{100*g[c].mean():>9.1f}%" for c in cols)
                 + f"{len(g):>9,}")
    return "\n".join(L)
