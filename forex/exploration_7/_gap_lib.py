"""Weekend-gap study library: loading, break detection, event construction.

Design notes (see RUNBOOK.md for the preregistration):

* Every price archive in `forex/data/` is normalised to a tz-naive UTC
  `datetime64[us]` index. Storage units differ across sources (LEARNINGS: a
  hard-coded ns divisor is correct on one archive and 1000x wrong on another),
  so conversion is done with `pd.Timedelta` arithmetic only, never `astype`.
* The weekend break is *detected* from the data, not hard-coded to a clock.
  The spot-FX reopen moves with US DST and with holidays, and a hard-coded
  21:00 UTC boundary misfiles a large minority of weeks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

# pip size in price units. JPY crosses quote to 0.01, everything else to 0.0001.
PIP = {
    "EURUSD": 1e-4, "AUDUSD": 1e-4, "GBPUSD": 1e-4, "NZDUSD": 1e-4,
    "USDJPY": 1e-2, "AUDJPY": 1e-2, "NZDJPY": 1e-2, "EURJPY": 1e-2,
    "GBPJPY": 1e-2,
}

# source file per pair; three different vintages/formats live under data/
SOURCES = {
    "EURUSD": ("parquet", "clean/EURUSD_1m_clean.parquet", "ts_utc"),
    "AUDUSD": ("parquet", "clean/AUDUSD_1m_clean.parquet", "ts_utc"),
    "GBPUSD": ("parquet", "clean/GBPUSD_1m_clean.parquet", "ts_utc"),
    "NZDUSD": ("parquet", "clean/NZDUSD_1m_clean.parquet", "ts_utc"),
    "USDJPY": ("parquet", "USDJPY_1m.parquet", "ts"),
    "NZDJPY": ("parquet", "NZDJPY_1m.parquet", "ts"),
    "EURJPY": ("parquet", "EURJPY_1m.parquet", "ts"),
    "AUDJPY": ("csv", "audjpy_intraday_1min.csv", "time"),
    "GBPJPY": ("csv", "gbpjpy_intraday_1min.csv", "time"),
}

PAIRS = list(SOURCES)


def load_pair(pair: str) -> pd.DataFrame:
    """Return 1-minute OHLC indexed by tz-naive UTC minute, deduped and sorted."""
    kind, rel, tscol = SOURCES[pair]
    path = DATA / rel
    cols = ["open", "high", "low", "close"]
    if kind == "parquet":
        df = pd.read_parquet(path, columns=[tscol] + cols)
    else:
        df = pd.read_csv(path, usecols=[tscol] + cols)
        df[tscol] = pd.to_datetime(df[tscol], utc=True, format="mixed")

    ts = df[tscol]
    if isinstance(ts.dtype, pd.DatetimeTZDtype):
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    df = df.drop(columns=[tscol])
    df.index = pd.DatetimeIndex(ts.values).as_unit("us")
    df.index.name = "ts"

    df = df.astype("float64")
    df = df[~df.index.duplicated(keep="first")].sort_index()
    # every archive here is whole-minute; assert rather than assume
    off = (df.index.view("int64") % (60 * 1_000_000))
    assert (off == 0).all(), f"{pair}: non-whole-minute timestamps present"
    return df


def find_breaks(idx: pd.DatetimeIndex, min_hours: float) -> pd.DataFrame:
    """All trading interruptions of at least `min_hours`.

    Returns one row per break with the last bar before and first bar after.
    """
    prev = idx[:-1]
    nxt = idx[1:]
    dt_h = (nxt - prev).total_seconds() / 3600.0
    m = dt_h >= min_hours
    return pd.DataFrame(
        {"t_prev": prev[m], "t_next": nxt[m], "break_hours": dt_h[m]}
    )


def weekend_breaks(idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Weekend breaks: the interruption that spans Saturday.

    Spot FX is closed roughly Fri 21-22:00 UTC to Sun 21-22:00 UTC, and the
    exact boundary moves with US DST. Rather than pin a clock, take every
    break of >= 24h whose span covers a Saturday. Holiday-extended weekends
    are kept and flagged by `break_hours`.
    """
    br = find_breaks(idx, min_hours=24.0)
    if br.empty:
        return br
    spans_sat = (br["t_prev"].dt.dayofweek == 4) | (br["t_next"].dt.dayofweek == 0)
    # ordinary case: Friday close -> Sunday open (dow 4 -> 6)
    covers_sat = br.apply(
        lambda r: any(
            (r["t_prev"] + pd.Timedelta(days=k)).dayofweek == 5
            and r["t_prev"] + pd.Timedelta(days=k) < r["t_next"]
            for k in range(0, int(r["break_hours"] // 24) + 2)
        ),
        axis=1,
    )
    br = br[covers_sat | spans_sat].reset_index(drop=True)
    br["weekend"] = br["t_prev"].dt.normalize()
    return br


CALENDAR_REF = "EURUSD"


def session_calendar(ref_idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Canonical weekly session boundaries, derived from one clean archive.

    Why this exists: three of the nine archives (USDJPY, NZDJPY, EURJPY) are a
    padded vintage that carries synthetic round-the-clock bars through
    2021-2023 weekends, so their own break structure cannot locate the true
    Friday close or Sunday reopen. The clean archives (the four USD majors and
    AUDJPY) all agree on the boundary to the minute, so one calendar is taken
    from the reference pair and imposed on every pair. This also removes a
    confound: without it, pairs would be compared on different weekend windows.
    """
    br = weekend_breaks(ref_idx)
    return pd.DataFrame({
        "week_close": br["t_prev"].values,   # last tradable minute of the week
        "week_open": br["t_next"].values,    # first tradable minute of the next
        "break_hours": br["break_hours"].values,
    })


def build_events(pair: str, df: pd.DataFrame, horizons_min: list[int],
                 entry_delays_min: list[int], calendar: pd.DataFrame,
                 vol_lookback_weeks: int = 26, tol_min: int = 60,
                 ) -> pd.DataFrame:
    """One row per weekend gap.

    Conventions
    -----------
    * `gap` is measured from the last Friday CLOSE to the first post-break
      OPEN. Both prices are observable the instant the market reopens.
    * Entry happens at the OPEN of a later bar (`entry_delay` minutes after
      the reopen). Entering at the reopen open itself would trade on the same
      print that defines the gap.
    * Forward returns run from the entry price to the CLOSE at `horizon`
      minutes past the reopen, using only bars that exist (spot FX has
      intra-week gaps); the realised elapsed time is recorded.
    * `sigma` is the trailing standard deviation of THIS pair's own past
      weekend gaps (strictly prior weekends only), so `z` is scale-free and
      causal. A fixed pip threshold would be a volatility-regime selector.
    """
    idx = df.index
    n = len(idx)
    o = df["open"].to_numpy()
    c = df["close"].to_numpy()

    # Snap the canonical boundaries onto this pair's own bars.
    wk_close = pd.DatetimeIndex(calendar["week_close"].values)
    wk_open = pd.DatetimeIndex(calendar["week_open"].values)
    p_close = idx.get_indexer(wk_close, method="ffill")   # last bar at/ before
    p_open = idx.get_indexer(wk_open, method="bfill")     # first bar at/ after

    lag_close = (idx[np.clip(p_close, 0, n - 1)] - wk_close).total_seconds().to_numpy() / 60.0
    lag_open = (idx[np.clip(p_open, 0, n - 1)] - wk_open).total_seconds().to_numpy() / 60.0
    ok = (p_close >= 0) & (p_open >= 0) & (p_open < n)
    ok &= np.abs(np.nan_to_num(lag_close, nan=1e9)) <= tol_min
    ok &= np.abs(np.nan_to_num(lag_open, nan=1e9)) <= tol_min

    pc = np.clip(p_close, 0, n - 1)
    po = np.clip(p_open, 0, n - 1)
    fri_close = np.where(ok, c[pc], np.nan)
    reopen = np.where(ok, o[po], np.nan)
    gap_ret = np.log(reopen / fri_close)

    ev = pd.DataFrame({
        "pair": pair,
        "weekend": wk_close.normalize(),
        "t_fri": idx[pc], "t_open": idx[po],
        "boundary_ok": ok,
        "lag_close_min": lag_close, "lag_open_min": lag_open,
        "break_hours": calendar["break_hours"].values,
        "fri_close": fri_close,
        "reopen": reopen,
        "gap_pips": (reopen - fri_close) / PIP[pair],
        "gap_ret": gap_ret,
    })
    # Keep only weekends whose boundary landed on real bars of THIS pair;
    # the causal sigma window is then built over consecutive kept weekends.
    ev = ev[ev["boundary_ok"]].reset_index(drop=True)
    br = pd.DataFrame({"t_next": ev["t_open"]})

    # causal scale: trailing SD of prior weekend gap returns (shifted by 1)
    ev["sigma_ret"] = (
        ev["gap_ret"].shift(1).rolling(vol_lookback_weeks,
                                       min_periods=max(8, vol_lookback_weeks // 3)).std()
    )
    ev["z"] = ev["gap_ret"] / ev["sigma_ret"]

    # entry prices at each delay, and forward closes at each horizon.
    # Lags are computed by subtracting DatetimeIndex objects (exact at any
    # storage unit); an int64 divisor here would be unit-dependent and this
    # study spans archives stored in different units.
    t_open = pd.DatetimeIndex(br["t_next"].values)

    def _lag_minutes(pos: np.ndarray, tgt: pd.DatetimeIndex) -> np.ndarray:
        got = idx[np.clip(pos, 0, n - 1)]
        return (got - tgt).total_seconds().to_numpy() / 60.0

    for d in entry_delays_min:
        tgt = t_open + pd.Timedelta(minutes=d)
        p = idx.get_indexer(tgt, method="bfill")
        lag = _lag_minutes(p, tgt)
        # refuse an entry that lands more than 60 min past its target
        ok = (p >= 0) & (p < n) & (lag <= 60)
        ev[f"entry_{d}"] = np.where(ok, o[np.clip(p, 0, n - 1)], np.nan)
        ev[f"entry_lag_{d}"] = np.where(p >= 0, lag, np.nan)

    for h in horizons_min:
        tgt = t_open + pd.Timedelta(minutes=h)
        p = idx.get_indexer(tgt, method="ffill")
        lag = _lag_minutes(p, tgt)
        # exit must not be stale by more than 1 day (holiday truncation)
        ok = (p >= 0) & (np.abs(lag) <= 1440)
        ev[f"exit_{h}"] = np.where(ok, c[np.clip(p, 0, n - 1)], np.nan)
        ev[f"exit_lag_{h}"] = np.where(p >= 0, lag, np.nan)

    return ev


def fade_returns(ev: pd.DataFrame, delay: int, horizon: int) -> pd.Series:
    """Signed return of the FADE trade, in units of the pair's own gap sigma.

    Fade = trade against the gap: short after an up-gap, long after a
    down-gap. Expressed in sigma units so pairs and eras are comparable
    (a pip mean across regimes is a volatility selector, not an effect).
    """
    entry = ev[f"entry_{delay}"]
    exit_ = ev[f"exit_{horizon}"]
    side = -np.sign(ev["gap_ret"])
    raw = side * np.log(exit_ / entry)
    return raw / ev["sigma_ret"]
