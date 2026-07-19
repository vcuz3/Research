"""Causal one-second first-touch exit engine for the Noise Area/VWAP strategy.

Entries remain close-decided and fill at the next one-minute open.  A stop level
is computed only from the previous completed one-minute bar and becomes active in
the following minute.  One-second OHLC then establishes the first touch.  The
kernel is compiled; Python never iterates over second rows.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from numba import njit


ONE_SECOND_PATH = (
    Path(__file__).resolve().parents[3]
    / "data" / "databento" / "NQ_ohlcv-1s_NQv0_20100606_20260717.parquet"
)


@njit(cache=True)
def simulate_session_1s(
    sec_ts, sec_open, sec_high, sec_low,
    minute_ts, minute_open, minute_close, minute_vwap, upper, lower,
    is_decision, refresh_every_bar,
):
    """Return fixed-size trade arrays and count for one RTH session.

    Touch fills are stop-market proxies: at the stop unless the first observed
    one-second open has already gapped through, in which case that open is used.
    Slippage and fees remain downstream costs so gross execution is auditable.
    """
    nmin = minute_ts.size
    # At most one closed trade per minute under a single-position policy.
    o_side = np.empty(nmin, np.int8)
    o_entry_ts = np.empty(nmin, np.int64)
    o_exit_ts = np.empty(nmin, np.int64)
    o_entry_px = np.empty(nmin, np.float64)
    o_exit_px = np.empty(nmin, np.float64)
    o_reason = np.empty(nmin, np.int8)  # 0 touch, 1 flip, 2 eod
    nt = 0

    pos = 0
    entry_ts = -1
    entry_px = np.nan
    stop = np.nan

    for j in range(1, nmin):
        p = j - 1  # the only information available at minute j
        want = 0
        if is_decision[p] and np.isfinite(upper[p]):
            c = minute_close[p]
            w = minute_vwap[p]
            if c > upper[p] and c > w:
                want = 1
            elif c < lower[p] and c < w:
                want = -1

        # Decision-bar reversals execute at the next minute open, as before.
        if pos != 0 and want == -pos:
            fpx = minute_open[j]
            o_side[nt] = pos
            o_entry_ts[nt] = entry_ts
            o_exit_ts[nt] = minute_ts[j]
            o_entry_px[nt] = entry_px
            o_exit_px[nt] = fpx
            o_reason[nt] = 1
            nt += 1
            pos = want
            entry_ts = minute_ts[j]
            entry_px = fpx
            stop = np.nan
        elif pos == 0 and want != 0:
            pos = want
            entry_ts = minute_ts[j]
            entry_px = minute_open[j]
            stop = np.nan

        # The completed prior bar refreshes the order for this minute.  In the
        # baseline control this happens only after a 30-minute decision bar.
        if pos != 0 and np.isfinite(upper[p]) and (refresh_every_bar or is_decision[p]):
            if pos == 1:
                stop = upper[p] if upper[p] > minute_vwap[p] else minute_vwap[p]
            else:
                stop = lower[p] if lower[p] < minute_vwap[p] else minute_vwap[p]

        if pos == 0 or not np.isfinite(stop):
            continue

        lo = np.searchsorted(sec_ts, minute_ts[j], side="left")
        if j + 1 < nmin:
            hi = np.searchsorted(sec_ts, minute_ts[j + 1], side="left")
        else:
            hi = sec_ts.size
        for k in range(lo, hi):
            hit = sec_low[k] <= stop if pos == 1 else sec_high[k] >= stop
            if hit:
                if pos == 1:
                    fpx = sec_open[k] if sec_open[k] < stop else stop
                else:
                    fpx = sec_open[k] if sec_open[k] > stop else stop
                o_side[nt] = pos
                o_entry_ts[nt] = entry_ts
                o_exit_ts[nt] = sec_ts[k]
                o_entry_px[nt] = entry_px
                o_exit_px[nt] = fpx
                o_reason[nt] = 0
                nt += 1
                pos = 0
                entry_ts = -1
                entry_px = np.nan
                stop = np.nan
                break

    if pos != 0:
        o_side[nt] = pos
        o_entry_ts[nt] = entry_ts
        o_exit_ts[nt] = minute_ts[-1] + 60_000_000_000
        o_entry_px[nt] = entry_px
        o_exit_px[nt] = minute_close[-1]
        o_reason[nt] = 2
        nt += 1

    return (o_side[:nt], o_entry_ts[:nt], o_exit_ts[:nt], o_entry_px[:nt],
            o_exit_px[:nt], o_reason[:nt])


def utc_rth_intervals(dates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized UTC nanosecond boundaries for 09:30--16:00 New York."""
    d = pd.DatetimeIndex(dates)
    starts = (d.tz_localize("America/New_York") + pd.Timedelta(hours=9, minutes=30))
    ends = (d.tz_localize("America/New_York") + pd.Timedelta(hours=16))
    return (starts.tz_convert("UTC").asi8, ends.tz_convert("UTC").asi8)


def iter_rth_seconds(path: Path, dates: np.ndarray):
    """Yield one session at a time from a column-pruned Parquet row-group scan.

    UTC interval search avoids timezone conversion on 142 million rows.  All row
    filtering and splitting is NumPy vectorized; the only Python loop is over
    Parquet row groups and complete sessions.
    """
    starts, ends = utc_rth_intervals(dates)
    pf = pq.ParquetFile(path)
    cols = ["ts_event", "open", "high", "low"]
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

    for rg in range(pf.metadata.num_row_groups):
        stats = pf.metadata.row_group(rg).column(0).statistics
        if stats is not None and stats.has_min_max:
            rg_min = pd.Timestamp(stats.min).value
            rg_max = pd.Timestamp(stats.max).value
            if rg_max < starts[0] or rg_min >= ends[-1]:
                continue
        tab = pf.read_row_group(rg, columns=cols)
        ts = tab["ts_event"].to_numpy(zero_copy_only=False).astype("datetime64[ns]").view("int64")
        code = np.searchsorted(starts, ts, side="right") - 1
        valid = code >= 0
        valid &= ts < ends[np.maximum(code, 0)]
        if not valid.any():
            continue
        idx = np.flatnonzero(valid)
        ts = ts[idx]
        code = code[idx]
        opn = tab["open"].to_numpy(zero_copy_only=False)[idx].astype(np.float64, copy=False)
        high = tab["high"].to_numpy(zero_copy_only=False)[idx].astype(np.float64, copy=False)
        low = tab["low"].to_numpy(zero_copy_only=False)[idx].astype(np.float64, copy=False)
        cuts = np.r_[0, np.flatnonzero(np.diff(code)) + 1, code.size]
        for a, b in zip(cuts[:-1], cuts[1:]):
            out = emit_or_carry(int(code[a]), (ts[a:b], opn[a:b], high[a:b], low[a:b]))
            if out is not None:
                yield out
    if carry is not None:
        yield carry_code, carry


def prepare_sessions(bars: pd.DataFrame, bands: pd.DataFrame):
    """Build compact minute arrays keyed by date; no row-wise pandas iteration."""
    bd = bands[["date", "tod", "upper", "lower"]]
    x = bars.merge(bd, on=["date", "tod"], how="left", validate="one_to_one")
    local = pd.DatetimeIndex(
        pd.to_datetime(x["date"]) + pd.to_timedelta(x["tod"], unit="m")
    ).tz_localize("America/New_York")
    x = x.assign(minute_ts=local.tz_convert("UTC").asi8, is_decision=x["tod"].isin(
        [570 + k - 1 for k in range(30, 391, 30)]))
    out = {}
    for date, g in x.groupby("date", sort=False):
        out[np.datetime64(date, "ns")] = (
            g["minute_ts"].to_numpy(np.int64),
            g["open"].to_numpy(np.float64),
            g["close"].to_numpy(np.float64),
            g["vwap"].to_numpy(np.float64),
            g["upper"].to_numpy(np.float64),
            g["lower"].to_numpy(np.float64),
            g["is_decision"].to_numpy(np.bool_),
        )
    return out


def run_streaming(path: Path, bars: pd.DataFrame, bands: pd.DataFrame,
                  refresh_every_bar: bool) -> tuple[pd.DataFrame, dict]:
    results, audit = run_streaming_both(path, bars, bands)
    key = "every_bar" if refresh_every_bar else "decision"
    return results[key], audit


def run_streaming_both(path: Path, bars: pd.DataFrame, bands: pd.DataFrame):
    """Scan the large Parquet file once and evaluate both refresh modes."""
    sessions = prepare_sessions(bars, bands)
    dates = np.array(sorted(sessions), dtype="datetime64[ns]")
    rows = {"decision": [], "every_bar": []}
    covered = []
    second_rows = 0
    reasons = np.array(["touch", "flip", "eod"])
    for code, sec in iter_rth_seconds(path, dates):
        date = dates[code]
        minute = sessions.get(date)
        if minute is None:
            continue
        second_rows += sec[0].size
        covered.append(date)
        for key, refresh in (("decision", False), ("every_bar", True)):
            result = simulate_session_1s(*sec, *minute, refresh)
            side, ets, xts, epx, xpx, reason = result
            if side.size:
                rows[key].append(pd.DataFrame({
                    "date": date, "side": side,
                    "entry_ts": pd.to_datetime(ets, utc=True),
                    "exit_ts": pd.to_datetime(xts, utc=True),
                    "entry_px": epx, "exit_px": xpx,
                    "points": (xpx - epx) * side,
                    "reason": reasons[reason],
                }))
    trades = {
        key: (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame())
        for key, parts in rows.items()
    }
    audit = {
        "eligible_sessions": len(dates),
        "covered_sessions": len(covered),
        "covered_dates": [str(pd.Timestamp(d).date()) for d in covered],
        "first_covered": str(pd.Timestamp(min(covered)).date()) if covered else None,
        "last_covered": str(pd.Timestamp(max(covered)).date()) if covered else None,
        "rth_second_rows": int(second_rows),
    }
    return trades, audit
