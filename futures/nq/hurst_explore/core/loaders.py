"""Data loaders for the Hurst-exploration study (self-contained).

Two price sources, both RTH 09:30--16:00 ET:
  * 1-minute clean bars for NQ AND ES  (../data/{NQ,ES}_1m_clean.parquet)
  * 1-second OHLCV for NQ ONLY         (futures/data/databento/NQ_ohlcv-1s...)
    ES 1s is not in the archive, so every 1s result is NQ-only; ES is the 1m
    cross-market check.

Rule 9a: the 1s reader returns a per-session data-quality record (grid fill
rate, real vs forward-filled seconds, by time-of-day) because the 1s tape is
sparse -- only seconds that traded carry a bar -- and forward-filling to a
regular grid injects artificial zero-returns whose density is itself a finding
about the microstructure Hurst floor.  Nothing here trades.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
NQ_DATA = ROOT.parents[0] / "data"                 # futures/nq/data
ONE_MIN = {"NQ": NQ_DATA / "NQ_1m_clean.parquet",
           "ES": NQ_DATA / "ES_1m_clean.parquet"}
ONE_SEC_NQ = (ROOT.parents[1] / "data" / "databento"
              / "NQ_ohlcv-1s_NQv0_20100606_20260717.parquet")

RTH_START_SEC = (9 * 60 + 30) * 60     # 09:30:00 ET, seconds from midnight
RTH_END_SEC = 16 * 60 * 60             # 16:00:00 ET (exclusive)
RTH_SECONDS = RTH_END_SEC - RTH_START_SEC   # 23400
MIN_BARS_1M = 350
EXPECTED_BARS_1M = 390

# Databento-flagged degraded-quality days (exclude before trusting a path).
DEGRADED = {
    "2014-06-11", "2014-06-12", "2014-06-13", "2017-11-13", "2018-10-21",
    "2019-01-15", "2019-02-22", "2020-02-27", "2020-02-28", "2020-06-30",
    "2020-07-01", "2021-12-05", "2022-01-02", "2025-09-17", "2025-09-24",
    "2025-11-28",
}
_DEGRADED = {pd.Timestamp(d) for d in DEGRADED}


# --------------------------------------------------------------------------- #
# 1-minute RTH loader (NQ + ES)
# --------------------------------------------------------------------------- #
def load_1m_rth(inst: str) -> pd.DataFrame:
    """One row per RTH 1-min bar: sdate, tod, mfo(0..389), close, volume.

    `sdate` is the ET calendar date; `mfo` = minutes from 09:30.  Near-complete
    sessions only (>=350 bars).  Degraded days dropped.
    """
    df = pd.read_parquet(ONE_MIN[inst], columns=["ts_utc", "open", "high",
                                                 "low", "close", "volume"])
    et = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    tod = et.dt.hour * 60 + et.dt.minute
    m = (tod >= 9 * 60 + 30) & (tod < 16 * 60)
    df = df[m].copy()
    df["sdate"] = et[m].dt.normalize().dt.tz_localize(None).values
    df["tod"] = tod[m].values
    df["mfo"] = (df["tod"] - (9 * 60 + 30)).astype(int)
    df = df[~df["sdate"].isin(_DEGRADED)]
    n = df.groupby("sdate")["close"].transform("size")
    df = df[n >= MIN_BARS_1M]
    return df.sort_values(["sdate", "mfo"]).reset_index(drop=True)


def data_quality_1m(inst: str) -> pd.DataFrame:
    """One Rule-9a record per retained session.

    Hurst estimators assume an evenly spaced path.  ``complete_grid`` therefore
    requires each minute slot 0..389 exactly once; merely having >=350 rows is
    not sufficient for an estimator input.
    """
    df = load_1m_rth(inst)
    rows = []
    expected = np.arange(EXPECTED_BARS_1M)
    for sd, g in df.groupby("sdate", sort=True):
        mfo = g["mfo"].to_numpy(int)
        unique = np.unique(mfo)
        missing = np.setdiff1d(expected, unique, assume_unique=True)
        rows.append({
            "sdate": sd,
            "n_rows": int(len(g)),
            "n_unique_slots": int(len(unique)),
            "duplicate_slots": int(len(mfo) - len(unique)),
            "missing_slots": int(len(missing)),
            "internal_gaps": int(np.sum(np.diff(unique) > 1)),
            "first_mfo": int(unique[0]),
            "last_mfo": int(unique[-1]),
            "complete_grid": bool(np.array_equal(unique, expected)),
        })
    return pd.DataFrame(rows)


def sessions_1m(inst: str, complete_only: bool = True):
    """Yield evenly spaced RTH paths, excluding incomplete grids by default."""
    df = load_1m_rth(inst)
    for sd, g in df.groupby("sdate", sort=True):
        g = g.sort_values("mfo")
        mfo = g["mfo"].to_numpy(int)
        if complete_only and not np.array_equal(mfo, np.arange(EXPECTED_BARS_1M)):
            continue
        yield sd, np.log(g["close"].to_numpy(float)), mfo


# --------------------------------------------------------------------------- #
# 1-second RTH streaming loader (NQ only)
# --------------------------------------------------------------------------- #
def _utc_bounds(dates: np.ndarray):
    d = pd.DatetimeIndex(dates)
    start = (d.tz_localize("America/New_York") + pd.Timedelta(hours=9, minutes=30))
    end = (d.tz_localize("America/New_York") + pd.Timedelta(hours=16))
    return start.tz_convert("UTC").asi8, end.tz_convert("UTC").asi8


def _rth_dates_1s() -> np.ndarray:
    """RTH session dates present in the 1m NQ file (the eligible universe)."""
    df = load_1m_rth("NQ")
    return np.sort(df["sdate"].unique().astype("datetime64[ns]"))


def iter_1s_rth(dates: np.ndarray):
    """Yield (sdate, sec_of_session, close, volume) per RTH session from the 1s
    archive.  `sec_of_session` = integer seconds since 09:30:00 ET in [0,23400).

    Row-group pruning + fully vectorized interval assignment; the only Python
    loops are over Parquet row groups and complete sessions.  A session can be
    split across row groups, so a carry buffer stitches the trailing partial.
    """
    dates = np.asarray(dates, dtype="datetime64[ns]")
    starts, ends = _utc_bounds(dates)
    pf = pq.ParquetFile(ONE_SEC_NQ)
    cols = ["ts_event", "close", "volume"]
    carry_code = -1
    carry = None

    def emit_or_carry(code, arrays):
        nonlocal carry_code, carry
        if carry is None:
            carry_code, carry = code, arrays
            return None
        if code == carry_code:
            carry = tuple(np.concatenate((a, b)) for a, b in zip(carry, arrays))
            return None
        out = (carry_code, carry)
        carry_code, carry = code, arrays
        return out

    def unpack(code, arrays):
        ts, close, vol = arrays
        sd = dates[code]
        sec = ((ts - starts[code]) // 1_000_000_000).astype(int)
        return sd, sec, close, vol

    for rg in range(pf.metadata.num_row_groups):
        stats = pf.metadata.row_group(rg).column(0).statistics
        if stats is not None and stats.has_min_max:
            rg_min = pd.Timestamp(stats.min).value
            rg_max = pd.Timestamp(stats.max).value
            if rg_max < starts[0] or rg_min >= ends[-1]:
                continue
        tab = pf.read_row_group(rg, columns=cols)
        ts = (tab["ts_event"].to_numpy(zero_copy_only=False)
              .astype("datetime64[ns]").view("int64"))
        code = np.searchsorted(starts, ts, side="right") - 1
        valid = (code >= 0)
        valid &= ts < ends[np.maximum(code, 0)]
        if not valid.any():
            continue
        idx = np.flatnonzero(valid)
        ts, code = ts[idx], code[idx]
        close = tab["close"].to_numpy(zero_copy_only=False)[idx].astype(float)
        vol = tab["volume"].to_numpy(zero_copy_only=False)[idx].astype(float)
        cuts = np.r_[0, np.flatnonzero(np.diff(code)) + 1, code.size]
        for a, b in zip(cuts[:-1], cuts[1:]):
            out = emit_or_carry(int(code[a]), (ts[a:b], close[a:b], vol[a:b]))
            if out is not None:
                yield unpack(*out)
    if carry is not None:
        yield unpack(carry_code, carry)


def grid_1s(sec: np.ndarray, close: np.ndarray):
    """Place sparse 1s closes onto the regular [0,23400) second grid and
    forward-fill.  Returns (log_close_grid, real_mask, fill_rate).

    `real_mask[i]` is True where second i carried an actual bar.  Leading
    seconds before the first trade are back-filled from the first close.
    """
    grid = np.full(RTH_SECONDS, np.nan)
    sec = np.clip(sec, 0, RTH_SECONDS - 1)
    # last bar wins within a second (bars are time-ordered already)
    grid[sec] = close
    real = np.isfinite(grid)
    # forward-fill then back-fill the leading gap
    idx = np.where(real, np.arange(RTH_SECONDS), 0)
    np.maximum.accumulate(idx, out=idx)
    grid = grid[idx]
    if not real[0]:                      # back-fill leading NaNs
        first = np.argmax(real)
        grid[:first] = grid[first]
    return np.log(grid), real, float(real.mean())
