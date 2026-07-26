"""Intraday-ATR stop-buffer exit engine (HYP-0022, EXP-0032).

Replaces the arbitrary 1m close-confirmation wick filter with an explicit,
volatility-scaled tolerance: exit on the first ONE-SECOND touch of

    stop(t) = max(upper, vwap) - k * ATR_N(t)      (long; + for shorts)

where ``ATR_N`` is a CAUSAL rolling mean of 1-minute True Range over the last
``N`` completed minutes.  The stop floats (recomputed every minute from the
completed prior bar, no ratchet), matching the current continuous stop.  Entries
are unchanged.  ``k = 0`` reduces to the EXP-0031 first-touch band stop.

The audited ``core/first_touch.py`` kernel is deliberately left untouched; this
module reuses only its one-pass Parquet scanner (``iter_rth_seconds``).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

from .first_touch import ONE_SECOND_PATH, iter_rth_seconds

# tod 570 == 09:30 == minute-from-open 1; first decision (entry) at tod 599 == mfo 30.
FIRST_ENTRY_MFO = 30


def intraday_atr(bars: pd.DataFrame, Ns) -> pd.DataFrame:
    """Add a causal intraday ATR column ``atr_{N}`` for each N (True-Range mean).

    TR_t = max(high-low, |high - prev_close|, |low - prior_close|) within the
    session; the first bar uses high-low.  ATR_N is a same-session rolling mean
    with ``min_periods = N`` (finite only once N completed bars exist).  The
    value at bar p uses bars [p-N+1 .. p], all completed by the end of minute p,
    so it is causal when consumed to arm the stop for minute p+1.
    """
    b = bars.sort_values(["date", "tod"]).reset_index(drop=True)
    pc = b.groupby("date", sort=False)["close"].shift(1)
    tr = np.maximum(b["high"] - b["low"],
                    np.maximum((b["high"] - pc).abs(), (b["low"] - pc).abs()))
    tr = tr.where(pc.notna(), b["high"] - b["low"])
    b["_tr"] = tr
    g = b.groupby("date", sort=False)["_tr"]
    for N in Ns:
        b[f"atr_{int(N)}"] = g.transform(
            lambda s, n=int(N): s.rolling(n, min_periods=n).mean())
    return b.drop(columns="_tr")


def prepare_sessions_atr(bars: pd.DataFrame, bands: pd.DataFrame, Ns):
    """Compact per-date minute arrays plus one ATR array per N and a constant-1.

    Returns ``{date: (minute_ts, open, close, vwap, upper, lower, is_decision,
    {key: atr_array})}`` where keys are the ints in ``Ns`` plus ``"const1"``
    (ones, for a fixed-point matched-width control).
    """
    Ns = [int(n) for n in Ns]
    bx = intraday_atr(bars, Ns)
    bd = bands[["date", "tod", "upper", "lower"]]
    x = bx.merge(bd, on=["date", "tod"], how="left", validate="one_to_one")
    local = pd.DatetimeIndex(
        pd.to_datetime(x["date"]) + pd.to_timedelta(x["tod"], unit="m")
    ).tz_localize("America/New_York")
    decision_tods = [570 + k - 1 for k in range(30, 391, 30)]
    x = x.assign(minute_ts=local.tz_convert("UTC").asi8,
                 is_decision=x["tod"].isin(decision_tods))
    out = {}
    for date, g in x.groupby("date", sort=False):
        atr_by = {N: g[f"atr_{N}"].to_numpy(np.float64) for N in Ns}
        atr_by["const1"] = np.ones(len(g), np.float64)
        out[np.datetime64(date, "ns")] = (
            g["minute_ts"].to_numpy(np.int64),
            g["open"].to_numpy(np.float64),
            g["high"].to_numpy(np.float64),
            g["low"].to_numpy(np.float64),
            g["close"].to_numpy(np.float64),
            g["vwap"].to_numpy(np.float64),
            g["upper"].to_numpy(np.float64),
            g["lower"].to_numpy(np.float64),
            g["is_decision"].to_numpy(np.bool_),
            atr_by,
        )
    return out


@njit(cache=True)
def simulate_session_atr(
    sec_ts, sec_open, sec_high, sec_low,
    minute_ts, minute_open, minute_close, minute_vwap, upper, lower,
    atr, is_decision, refresh_every_bar, k_buf, latency=0,
):
    """First-touch exits against a floating ``band - k*ATR`` stop for one session.

    Identical to ``first_touch.simulate_session_1s`` (trigger=0) except the stop
    is pushed ``k_buf * atr[p]`` away from the band/VWAP level.  ``k_buf == 0``
    reproduces the first-touch band stop bit-exactly.
    """
    nmin = minute_ts.size
    o_side = np.empty(nmin, np.int8)
    o_entry_ts = np.empty(nmin, np.int64)
    o_exit_ts = np.empty(nmin, np.int64)
    o_entry_px = np.empty(nmin, np.float64)
    o_exit_px = np.empty(nmin, np.float64)
    o_reason = np.empty(nmin, np.int8)  # 0 touch, 1 flip, 2 eod
    o_stop = np.empty(nmin, np.float64)  # stop level at exit (for width auditing)
    nt = 0

    pos = 0
    entry_ts = -1
    entry_px = np.nan
    stop = np.nan

    for j in range(1, nmin):
        p = j - 1
        want = 0
        if is_decision[p] and np.isfinite(upper[p]):
            c = minute_close[p]
            w = minute_vwap[p]
            if c > upper[p] and c > w:
                want = 1
            elif c < lower[p] and c < w:
                want = -1

        if pos != 0 and want == -pos:
            fpx = minute_open[j]
            o_side[nt] = pos
            o_entry_ts[nt] = entry_ts
            o_exit_ts[nt] = minute_ts[j]
            o_entry_px[nt] = entry_px
            o_exit_px[nt] = fpx
            o_reason[nt] = 1
            o_stop[nt] = np.nan
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

        if pos != 0 and np.isfinite(upper[p]) and (refresh_every_bar or is_decision[p]):
            a = atr[p]
            buf = k_buf * a if np.isfinite(a) else 0.0
            if pos == 1:
                base = upper[p] if upper[p] > minute_vwap[p] else minute_vwap[p]
                stop = base - buf
            else:
                base = lower[p] if lower[p] < minute_vwap[p] else minute_vwap[p]
                stop = base + buf

        if pos == 0 or not np.isfinite(stop):
            continue

        lo = np.searchsorted(sec_ts, minute_ts[j], side="left")
        if j + 1 < nmin:
            hi = np.searchsorted(sec_ts, minute_ts[j + 1], side="left")
        else:
            hi = sec_ts.size
        for kk in range(lo, hi):
            hit = sec_low[kk] <= stop if pos == 1 else sec_high[kk] >= stop
            if hit:
                fk = kk + latency
                if fk >= sec_ts.size:
                    fk = sec_ts.size - 1
                if pos == 1:
                    fpx = sec_open[fk] if sec_open[fk] < stop else stop
                else:
                    fpx = sec_open[fk] if sec_open[fk] > stop else stop
                o_side[nt] = pos
                o_entry_ts[nt] = entry_ts
                o_exit_ts[nt] = sec_ts[fk]
                o_entry_px[nt] = entry_px
                o_exit_px[nt] = fpx
                o_reason[nt] = 0
                o_stop[nt] = stop
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
        o_stop[nt] = np.nan
        nt += 1

    return (o_side[:nt], o_entry_ts[:nt], o_exit_ts[:nt], o_entry_px[:nt],
            o_exit_px[:nt], o_reason[:nt], o_stop[:nt])


def run_streaming_atr(path: Path, bars: pd.DataFrame, bands: pd.DataFrame, specs,
                      refresh_every_bar: bool = True):
    """One Parquet scan; each spec ``(name, atr_key, k)`` is a buffered variant.

    ``atr_key`` is an int N (an intraday ATR lookback prepared in
    ``prepare_sessions_atr``) or ``"const1"`` (fixed-point buffer of ``k`` points).
    Returns ``{name: trades_frame}`` and a coverage audit.
    """
    specs = [(str(nm), key, float(k)) for nm, key, k in specs]
    Ns = sorted({key for _, key, _ in specs if key != "const1"})
    sessions = prepare_sessions_atr(bars, bands, Ns)
    dates = np.array(sorted(sessions), dtype="datetime64[ns]")
    rows = {nm: [] for nm, _, _ in specs}
    covered = []
    second_rows = 0
    reasons = np.array(["touch", "flip", "eod"])
    for code, sec in iter_rth_seconds(path, dates):
        date = dates[code]
        s = sessions.get(date)
        if s is None:
            continue
        (mts, mopen, mhigh, mlow, mclose, mvwap, mup, mlo, mdec, atr_by) = s
        second_rows += sec[0].size
        covered.append(date)
        for nm, key, k in specs:
            atr = atr_by[key]
            side, ets, xts, epx, xpx, reason, stoplv = simulate_session_atr(
                *sec, mts, mopen, mclose, mvwap, mup, mlo, atr, mdec,
                refresh_every_bar, k)
            if side.size:
                rows[nm].append(pd.DataFrame({
                    "date": date, "side": side,
                    "entry_ts": pd.to_datetime(ets, utc=True),
                    "exit_ts": pd.to_datetime(xts, utc=True),
                    "entry_px": epx, "exit_px": xpx,
                    "points": (xpx - epx) * side,
                    "reason": reasons[reason], "stop_level": stoplv,
                }))
    trades = {
        nm: (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame())
        for nm, parts in rows.items()
    }
    audit = {
        "eligible_sessions": len(dates),
        "covered_sessions": len(covered),
        "covered_dates": [str(pd.Timestamp(d).date()) for d in covered],
        "rth_second_rows": int(second_rows),
        "specs": [(nm, key, k) for nm, key, k in specs],
        "refresh_every_bar": bool(refresh_every_bar),
    }
    return trades, audit


def run_1m_atr(bars: pd.DataFrame, bands: pd.DataFrame, specs,
               refresh_every_bar: bool = True) -> dict:
    """Buffered first-touch exits resolved on the 1-MINUTE bars themselves.

    Feeds each session's 1-min bars to ``simulate_session_atr`` as their own
    "seconds", so the touch test is the 1-min bar's high/low.  No 1s file is
    read -- used for the Null-C reruns (``core/nulls.py`` shuffles 1m bars) and
    for ES, which has no 1s history.  Returns ``{name: trades_frame}``.
    """
    specs = [(str(nm), key, float(k)) for nm, key, k in specs]
    Ns = sorted({key for _, key, _ in specs if key != "const1"})
    sessions = prepare_sessions_atr(bars, bands, Ns)
    rows = {nm: [] for nm, _, _ in specs}
    reasons = np.array(["touch", "flip", "eod"])
    for date, s in sessions.items():
        (mts, mopen, mhigh, mlow, mclose, mvwap, mup, mlo, mdec, atr_by) = s
        for nm, key, k in specs:
            atr = atr_by[key]
            side, ets, xts, epx, xpx, reason, stoplv = simulate_session_atr(
                mts, mopen, mhigh, mlow,
                mts, mopen, mclose, mvwap, mup, mlo, atr, mdec,
                refresh_every_bar, k)
            if side.size:
                rows[nm].append(pd.DataFrame({
                    "date": date, "side": side,
                    "entry_ts": pd.to_datetime(ets, utc=True),
                    "exit_ts": pd.to_datetime(xts, utc=True),
                    "entry_px": epx, "exit_px": xpx,
                    "points": (xpx - epx) * side,
                    "reason": reasons[reason], "stop_level": stoplv,
                }))
    return {nm: (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame())
            for nm, parts in rows.items()}
