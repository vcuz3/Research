"""Data loading, CME FX session construction, and the sealed holdout split.

Instruments
-----------
6E  EUR/USD futures, 125,000 EUR notional.
6B  GBP/USD futures,  62,500 GBP notional.

Both are Databento ``GLBX.MDP3`` ``ohlcv-1m`` volume-ranked continuous front
contracts (``6E.v.0`` / ``6B.v.0``), UNADJUSTED, 2010-06-07 .. 2026-07-27.

Why futures and not spot for a VWAP study
-----------------------------------------
`forex/noise_vwap` established that IBKR cash-FX bars carry NO size at all
(`volume == -1` on 100% of 22.0M rows), so every VWAP there degenerates to a
TWAP.  CME FX futures publish real, exchange-reported, centrally-cleared volume.
That makes them the only venue in this workspace where "is the VOLUME weighting
in VWAP load-bearing on FX?" is even a well-posed question.

Session
-------
CME FX Globex runs Sunday 18:00 ET through Friday 17:00 ET with a daily 60-minute
maintenance halt at 17:00-18:00 ET.  This is confirmed in the archive: ET
minute-of-day 1020..1079 (17:00-17:59) is empty on essentially every date, the
last minute of a session is 1019 (16:59) and the first is 1080 (18:00).

    sdate = date(t_ET + 6h)          # the CME trade date
    mfo   = (minute_of_day_ET - 1080) mod 1440      # 0 .. 1379

`mfo` is derived from the ET WALL CLOCK, never from the bar index, so a missing
minute shifts nothing (a lesson carried over from the FX spot port, where
minutes-from-open would have moved the decision grid onto :14/:44).

Contract economics (rule 19)
----------------------------
Everything is reported in PIPS, defined as 0.0001 of the quote for both
contracts.  Dollars per pip are NOT the same and the 6E TICK CHANGED MID-SAMPLE:

    6B   1 pip = 0.0001 = 1 tick = $6.25          (whole sample)
    6E   1 pip = 0.0001 = 1 tick = $12.50         (2010 .. 2015)
    6E   1 pip = 0.0001 = 2 ticks = $12.50        (2016 .. ), tick halved to
                                                  0.00005 = $6.25

So a cost model quoted in TICKS is silently a 2x different cost model before and
after 2016-01 on 6E.  `tick_size(product, year)` returns the point size actually
in force; costs are always built from it rather than assumed.

Holdout (sealed)
----------------
Trade dates whose YEAR is in {2024, 2025, 2026} are the holdout and are removed
by `load_bars` unless `scope="holdout"` is passed explicitly.  Exploration runs
on 2010-06 .. 2023-12.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "databento"

PRODUCTS = ("6E", "6B")

# 6J is not in PRODUCTS: it was added for the HYP-0005 liquidity-vs-clock test
# (EXP-0005) and is not part of the original two-product study, so it must be
# requested explicitly rather than swept up by a bare `for p in PRODUCTS`.
PRODUCTS_EXT = ("6E", "6B", "6J")

# The full CME FX panel, added for the HYP-0007 home-market test (EXP-0007).
PRODUCTS_PANEL = ("6E", "6B", "6J", "6A", "6C", "6N", "6S")

FILES = {
    "6E": "6E_ohlcv-1m_6Ev0_20100606_20260728.parquet",
    "6B": "6B_ohlcv-1m_6Bv0_20100606_20260728.parquet",
    "6J": "6J_ohlcv-1m_6Jv0_20100606_20260728.parquet",
    "6A": "6A_ohlcv-1m_6Av0_20100606_20260728.parquet",
    "6C": "6C_ohlcv-1m_6Cv0_20100606_20260728.parquet",
    "6N": "6N_ohlcv-1m_6Nv0_20100606_20260728.parquet",
    "6S": "6S_ohlcv-1m_6Sv0_20100606_20260728.parquet",
}

# Session geometry, ET minute-of-day.
SESSION_OPEN_MOD = 18 * 60          # 18:00 ET
SESSION_MINUTES = 1380              # 18:00 -> 16:59 ET inclusive

HOLDOUT_YEARS = (2024, 2025, 2026)

PIP = 1e-4                          # reporting unit for 6E and 6B

# Reporting unit per product, in QUOTE units.  6E and 6B quote dollars per unit
# of foreign currency near 1, so the market convention 0.0001 is both natural and
# worth $12.50 / $6.25 on their notionals.  6J quotes dollars per YEN, near
# 0.0091, where 0.0001 would be an ~11-big-figure move -- absurd as a reporting
# unit.  Its unit is set to 1e-6, chosen because 12,500,000 JPY * 1e-6 = $12.50,
# i.e. EXACTLY the dollar value of a 6E pip and exactly one pre-2015 6J tick.
#
# Note this is NOT the conventional USD/JPY "pip" of 0.01 yen: the futures quote
# is the RECIPROCAL of the spot convention, so a 0.01-yen move maps to a
# price-level-dependent number of quote units (~8.3e-8 at USDJPY 110) and cannot
# be a fixed reporting unit at all.  Cross-product magnitudes are therefore
# compared in dollars and in risk-equalised (dispersion-normalised) units, never
# by putting two different products' "pips" side by side.
#
# 6A/6C/6N/6S all quote dollars per unit of foreign currency near 1, so the
# conventional 1e-4 applies to them exactly as it does to 6E and 6B.  6J remains
# the only product needing a different unit.
_PIP_SIZE = {"6E": 1e-4, "6B": 1e-4, "6J": 1e-6,
             "6A": 1e-4, "6C": 1e-4, "6N": 1e-4, "6S": 1e-4}

# Notional and dollar value of one reporting unit.
CONTRACT = {
    "6E": {"notional": 125_000.0, "usd_per_pip": 12.50, "name": "EUR/USD future"},
    "6B": {"notional": 62_500.0, "usd_per_pip": 6.25, "name": "GBP/USD future"},
    "6J": {"notional": 12_500_000.0, "usd_per_pip": 12.50, "name": "JPY/USD future"},
    "6A": {"notional": 100_000.0, "usd_per_pip": 10.00, "name": "AUD/USD future"},
    "6C": {"notional": 100_000.0, "usd_per_pip": 10.00, "name": "CAD/USD future"},
    "6N": {"notional": 100_000.0, "usd_per_pip": 10.00, "name": "NZD/USD future"},
    "6S": {"notional": 125_000.0, "usd_per_pip": 12.50, "name": "CHF/USD future"},
}

# Minimum price increment actually in force, VERIFIED against the price grid in
# the archive rather than assumed (rule 19).  6E outright ticks halved in 2016.
# 6J's halved mid-2015: the fraction of closes on the 1e-6 grid is >=0.9998 every
# month through 2015-05, 0.842 in 2015-06 and ~0.51 from 2015-07 onward, so 2015
# is a TRANSITION year and is assigned the finer tick (the less conservative
# choice for a cost floor, and flagged wherever a 6J cost is quoted).
# Every one of these except 6B halved mid-sample, at FIVE DIFFERENT dates, so a
# cost quoted in ticks is wrong on six of seven products somewhere in the sample.
_TICK_ERAS = {
    "6E": ((0, 2015, 1e-4), (2016, 9999, 5e-5)),
    "6B": ((0, 9999, 1e-4),),
    "6J": ((0, 2014, 1e-6), (2015, 9999, 5e-7)),
    "6C": ((0, 2015, 1e-4), (2016, 9999, 5e-5)),
    "6A": ((0, 2019, 1e-4), (2020, 9999, 5e-5)),
    "6N": ((0, 2020, 1e-4), (2021, 9999, 5e-5)),
    "6S": ((0, 2021, 1e-4), (2022, 9999, 5e-5)),
}


def pip_size(product: str) -> float:
    """Quote units per reporting unit for `product`. See `_PIP_SIZE`."""
    return _PIP_SIZE[product]


def tick_size(product: str, year: int) -> float:
    """Minimum price increment for `product` during calendar `year`."""
    for lo, hi, t in _TICK_ERAS[product]:
        if lo <= year <= hi:
            return t
    raise KeyError(f"no tick era for {product} {year}")


def usd_per_pip(product: str) -> float:
    return CONTRACT[product]["usd_per_pip"]


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LoadReport:
    """What `load_bars` did, so a caller can report it rather than discover it."""
    product: str
    scope: str
    raw_rows: int
    rows: int
    sessions: int
    roll_sessions_flagged: int
    short_sessions_flagged: int
    first_date: object
    last_date: object


def _read_raw(product: str) -> pd.DataFrame:
    path = DATA_DIR / FILES[product]
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(
        path, columns=["ts_event", "open", "high", "low", "close", "volume",
                       "instrument_id", "symbol"]
    )
    return df


def add_session_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Attach `et`, `sdate`, `mfo` from the UTC `ts_event`."""
    et = df["ts_event"].dt.tz_convert("America/New_York")
    mod = et.dt.hour * 60 + et.dt.minute
    out = df.copy()
    out["et"] = et
    out["mod"] = mod.astype(np.int32)
    out["sdate"] = (et + pd.Timedelta(hours=6)).dt.normalize().dt.tz_localize(None)
    out["mfo"] = ((mod - SESSION_OPEN_MOD) % 1440).astype(np.int32)
    return out


def load_bars(product: str, scope: str = "explore",
              min_session_bars: int = 400,
              drop_roll_sessions: bool = True,
              ) -> tuple[pd.DataFrame, LoadReport]:
    """Load 1-minute bars with session columns.

    scope
        ``"explore"``  trade dates before 2024 (the default; the holdout is sealed)
        ``"holdout"``  trade dates in 2024-2026 -- pass explicitly and only once
        ``"all"``      everything, for data-quality reporting only

    Sessions whose bars span more than one `instrument_id` (a contract roll landing
    inside the session) are dropped when `drop_roll_sessions`, because a
    session-anchored VWAP computed across a roll averages two different contracts.
    Very short sessions (holiday half-days and the 2010 first partial session) are
    dropped at `min_session_bars`; both counts are returned rather than hidden.
    """
    if scope not in {"explore", "holdout", "all"}:
        raise ValueError(scope)
    raw = _read_raw(product)
    df = add_session_columns(raw)
    raw_rows = len(df)

    # Bars inside the maintenance halt should not exist; assert rather than assume.
    halt = (df["mod"] >= 17 * 60) & (df["mod"] < 18 * 60)
    if halt.mean() > 1e-4:
        raise AssertionError(f"{product}: {halt.mean():.4%} of bars inside 17:00-18:00 ET halt")
    df = df.loc[~halt].copy()

    year = df["sdate"].dt.year
    if scope == "explore":
        df = df.loc[~year.isin(HOLDOUT_YEARS)].copy()
    elif scope == "holdout":
        df = df.loc[year.isin(HOLDOUT_YEARS)].copy()

    per = df.groupby("sdate").agg(bars=("close", "size"),
                                  ninst=("instrument_id", "nunique"))
    roll_sessions = per.index[per["ninst"] > 1]
    short_sessions = per.index[per["bars"] < min_session_bars]
    bad = set(short_sessions)
    if drop_roll_sessions:
        bad |= set(roll_sessions)
    if bad:
        df = df.loc[~df["sdate"].isin(bad)].copy()

    df = df.sort_values(["sdate", "mfo"], kind="mergesort").reset_index(drop=True)
    df["volume"] = df["volume"].astype(np.float64)
    rep = LoadReport(
        product=product, scope=scope, raw_rows=raw_rows, rows=len(df),
        sessions=int(df["sdate"].nunique()),
        roll_sessions_flagged=int(len(roll_sessions)),
        short_sessions_flagged=int(len(short_sessions)),
        first_date=df["sdate"].min(), last_date=df["sdate"].max(),
    )
    return df, rep


# --------------------------------------------------------------------------- #
# liquidity blocks (structural, not fitted)
# --------------------------------------------------------------------------- #
# ET wall-clock blocks used to stratify every result.  These are the standard FX
# trading-centre windows, declared before any measurement:
#   asia    18:00-02:59 ET   Tokyo/Sydney
#   ldn_am  03:00-07:59 ET   London morning, before NY
#   overlap 08:00-11:59 ET   London afternoon + NY morning (includes the 11:00 ET
#                            WM/Reuters 16:00-London fix)
#   ny_pm   12:00-16:59 ET   after the London close
BLOCKS = (
    ("asia", 18 * 60, 3 * 60),
    ("ldn_am", 3 * 60, 8 * 60),
    ("overlap", 8 * 60, 12 * 60),
    ("ny_pm", 12 * 60, 17 * 60),
)

# The WM/Reuters 16:00 London fix in ET.  London is 5h ahead of New York for all
# but a few shoulder days a year, so 11:00 ET is the fix minute on essentially
# every session in the sample.
FIX_MOD = 11 * 60


def block_of_mod(mod: np.ndarray) -> np.ndarray:
    """Map ET minute-of-day to a liquidity block label."""
    mod = np.asarray(mod)
    out = np.empty(mod.shape, dtype=object)
    out[:] = "asia"
    for name, start, end in BLOCKS:
        if start < end:
            m = (mod >= start) & (mod < end)
        else:                                   # wraps midnight
            m = (mod >= start) | (mod < end)
        out[m] = name
    return out
