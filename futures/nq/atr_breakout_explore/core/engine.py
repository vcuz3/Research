"""
ATR counter-bar breakout engine (5-min RTH bars, one session at a time).

Strategy (symmetric long/short), per session, bar-by-bar state machine:

  Setup (prior-day info only):
    session_open = open of the first RTH 5-min bar (09:30).
    atr          = daily ATR(14), lagged one session (see data.daily_atr).
    up   = session_open + band * atr      (band default 0.5)
    down = session_open - band * atr
    timeout = 5 bars.

  Per bar t, in this order:
    1. EXIT first.  If in a position, exit when the bar CLOSE crosses back through
       session_open (the stop) or it is the last bar (EOD flat).
    2. PENDING ENTRY.  If a breakout is armed and we are waiting, enter on the first
       counter-move bar (a DOWN 5-min bar before going long, an UP bar before a
       short -- "wait for a pullback, don't chase").  If no counter-bar appears
       within `timeout` bars, force the entry.
    3. DETECT BREAKOUT.  If flat and not already waiting: close > up  -> arm long;
       close < down -> arm short.

  Only one position (or one armed breakout) at a time; after an exit we may re-arm
  and trade again the same session.

Decisions are taken on 5-min CLOSES.  Fills are mapped separately by `fill_mode`:
  * "next_open"  (default, workspace Rule 2): the signalled action fills at the
    NEXT bar's open.  EOD exits fill at the last bar's close (no next open).
  * "close":     ablation -- fills at the signal bar's close.

PnL per trade (return units) = dir * (exit_fill - entry_fill) / session_open.
Costs (return units), charged per trade:
  * spread/slippage: min(0.5 bps * fill_price, cap_ticks * tick) points PER SIDE,
    two sides, / session_open.
  * fixed fees: ($0.70 clearing + $1.00 commission) round-trip / (micro_point_value
    * session_open)  -- execution assumed in the MICRO contract (MNQ / MES).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D

BPS = 0.5e-4          # 0.5 bps / side
FIXED_FEES_RT = 1.70  # $0.70 clearing + $1.00 commission, round trip, per contract


def _step_bars(g, step_min):
    """Aggregate one session's 5-min bars onto a coarser execution grid.

    step_min=5 returns the frame unchanged; step_min=15 floors each 5-min bar's
    timestamp to the 15-min grid and re-aggregates OHLC. Decisions/fills then act on
    the coarser bar closes/opens -- the paper's 15-minute execution grid."""
    if step_min == 5:
        return (g["open"].to_numpy(), g["high"].to_numpy(),
                g["low"].to_numpy(), g["close"].to_numpy())
    et = pd.to_datetime(g["et"].to_numpy())
    grp = pd.Series(et).dt.floor(f"{step_min}min").to_numpy()
    gg = pd.DataFrame({"g": grp, "open": g["open"].to_numpy(), "high": g["high"].to_numpy(),
                       "low": g["low"].to_numpy(), "close": g["close"].to_numpy()})
    agg = gg.groupby("g", sort=True).agg(open=("open", "first"), high=("high", "max"),
                                         low=("low", "min"), close=("close", "last"))
    return (agg["open"].to_numpy(), agg["high"].to_numpy(),
            agg["low"].to_numpy(), agg["close"].to_numpy())


def _run_session(o, h, l, c, session_open, up, down, timeout, immediate=False):
    """State machine on one session's bars. Returns list of
    (entry_bar, exit_bar, dir, exit_reason). Decisions on closes only.

    immediate=False: user's spec -- arm on the breakout close, then wait for a
    counter-move bar (pullback) before entering, forcing entry after `timeout` bars.
    immediate=True: paper baseline -- enter immediately at the breakout (no pullback
    overlay); the breakout bar itself is the entry signal."""
    n = len(c)
    trades = []
    state = "FLAT"           # FLAT | WAIT | POS
    direction = 0
    wait = 0
    entry_bar = -1
    for t in range(n):
        is_last = (t == n - 1)
        # 1. EXIT first
        if state == "POS":
            stop = (direction == 1 and c[t] < session_open) or \
                   (direction == -1 and c[t] > session_open)
            if stop or is_last:
                trades.append((entry_bar, t, direction,
                               "stop" if stop else "eod"))
                state = "FLAT"
                direction = 0
        # 2. PENDING ENTRY
        if state == "WAIT":
            wait += 1
            bar_dir = np.sign(c[t] - o[t])
            counter = (direction == 1 and bar_dir < 0) or \
                      (direction == -1 and bar_dir > 0)
            if (counter or wait >= timeout) and not is_last:
                # cannot open a position on the last bar (nothing to hold / fill)
                state = "POS"
                entry_bar = t
        # 3. DETECT BREAKOUT
        if state == "FLAT" and not is_last:
            armed = 1 if c[t] > up else (-1 if c[t] < down else 0)
            if armed != 0:
                if immediate:
                    state, direction, entry_bar = "POS", armed, t
                else:
                    state, direction, wait = "WAIT", armed, 0
    return trades


def _fill_price(o, c, bar, is_exit, reason, n, fill_mode):
    if fill_mode == "close":
        return c[bar]
    # next_open
    if is_exit and reason == "eod":
        return c[bar]          # EOD exit: last bar close, no next open
    if bar + 1 < n:
        return o[bar + 1]
    return c[bar]              # no next bar -> fall back to close


def backtest(inst: str, band: float = 0.5, timeout: int = 5,
             cap_ticks: float = 2.0, fill_mode: str = "next_open",
             atr_n: int = 14, step_min: int = 5, immediate: bool = False):
    """Run the strategy on one instrument. Returns (trades_df, daily_series).

    step_min: execution grid in minutes (5 = spec, 15 = user's requested variant).
    immediate: enter at the breakout without the counter-bar pullback (paper baseline).
    """
    bars = D.load_5m_rth(inst)
    atr = D.daily_atr(bars, atr_n)
    tick = D.TICK[inst]
    micro_pv = D.MICRO_POINT_VALUE[inst]

    rows = []
    for date, g in bars.groupby("date", sort=True):
        a = atr.get(date, np.nan)
        if not np.isfinite(a):
            continue
        g = g.sort_values("bar_i")
        o, h, l, c = _step_bars(g, step_min)
        n = len(c)
        session_open = o[0]
        up = session_open + band * a
        down = session_open - band * a
        trades = _run_session(o, h, l, c, session_open, up, down, timeout, immediate)
        for (eb, xb, d, reason) in trades:
            entry = _fill_price(o, c, eb, False, "entry", n, fill_mode)
            exit_ = _fill_price(o, c, xb, True, reason, n, fill_mode)
            gross = d * (exit_ - entry) / session_open
            sp_e = min(BPS * entry, cap_ticks * tick)
            sp_x = min(BPS * exit_, cap_ticks * tick)
            spread_cost = (sp_e + sp_x) / session_open
            fee_cost = FIXED_FEES_RT / (micro_pv * session_open)
            cost = spread_cost + fee_cost
            rows.append(dict(date=date, inst=inst, dir=d, entry_bar=eb,
                             exit_bar=xb, reason=reason, entry=entry, exit=exit_,
                             session_open=session_open, atr=a,
                             gross=gross, cost=cost, net=gross - cost))
    trades_df = pd.DataFrame(rows)

    # daily series over ALL usable sessions (0 on no-trade days)
    all_dates = pd.Index(sorted(d for d in bars["date"].unique()
                                if np.isfinite(atr.get(d, np.nan))), name="date")
    if len(trades_df):
        daily = trades_df.groupby("date")["net"].sum().reindex(all_dates).fillna(0.0)
    else:
        daily = pd.Series(0.0, index=all_dates)
    daily.name = "ret"
    return trades_df, daily
