"""
Core (Stage-1) execution engine for the VWAP-EMA bracket, SSRN-6650958.

Signals arrive on the 15m clock (strategy.signals); entry is at the NEXT 15m bar
open (rule 2). Each open trade is then managed with THREE exits:

  1. Initial hard stop  SL = L_signal -/+ 0.5*ATR14  (defines 1R). An INTRABAR
     catastrophic stop, resolved on 1-SECOND bars (rule 3: if a bar reaches both
     the stop and the 3R target, the STOP wins; gap-through fills at the 1s open,
     rule 5). Stays fixed in Stage-1 (the EMA50 close-trail does the trailing).
  2. Fixed target       entry +/- 3R, intrabar (1s), stop-first on ties.
  3. EMA close-trail     EMA50 until floating profit reaches 2.5R, then EMA20.
     Exit iff a 15m candle CLOSES beyond the active EMA on the adverse side.
     Intrabar EMA wicks are ignored. Checked
     only at each 15m bar CLOSE, so it fires only after the intrabar 1s scan of
     that bar found no stop/target -- the correct temporal order.

Forced flat at the last RTH bar (16:00 ET close). One position at a time; signals
occurring while in a position are dropped (not queued). New entries stop after
three consecutive net losing trades or cumulative net P&L <= -3R in a session.

Section 4.3's VWAP milestone is not executed: the entry rule already requires a
long above VWAP / short below VWAP, while the milestone describes a later
favourable approach *to* VWAP. No causal price direction or executable partial
fill is defined. This source contradiction is recorded in PAPER_SPEC.md rather
than silently inventing a rule.

When a session has no usable 1s stream (see core.data.MIN_1S_BARS) the intrabar
step falls back to that 15m bar's OHLC with the same adverse (stop-first) rule;
the fallback rate is reported by scripts/data_quality.py and per run.

Output: one row per closed trade with GROSS points (costs applied by the caller,
rule 20): date, side, entry_tsec, exit_tsec, entry_px, exit_px, stop_px,
target_px, points, risk_pts, reason, used_1s.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import RTH_START_SEC, BAR_SEC, N_BARS

_LAST_BAR_START = RTH_START_SEC + (N_BARS - 1) * BAR_SEC   # 15:45 ET bar start


def _intrabar(side: int, stop: float, target: float, sess1s,
              bar_start: int, o15: float, h15: float, l15: float):
    """Resolve stop/target WITHIN one 15m bar. Returns (reason, fill_px,
    exit_tsec, used_1s) or None if neither level is reached. reason in
    {'stop','target'}. Adverse (stop-first) on ties (rule 3); gap-through fills at
    the first tradable open (rule 5)."""
    if sess1s is not None:
        tsec, op, hi, lo = sess1s
        a = np.searchsorted(tsec, bar_start, side="left")
        b = np.searchsorted(tsec, bar_start + BAR_SEC, side="left")
        if b > a:
            oo = op[a:b]; hh = hi[a:b]; ll = lo[a:b]
            tt = tsec[a:b]
            if side == 1:
                s_mask = ll <= stop; t_mask = hh >= target
            else:
                s_mask = hh >= stop; t_mask = ll <= target
            si = int(np.argmax(s_mask)) if s_mask.any() else 10**9
            ti = int(np.argmax(t_mask)) if t_mask.any() else 10**9
            if si == 10**9 and ti == 10**9:
                return None
            if si <= ti:                     # stop first (tie -> stop)
                op_i = oo[si]
                if side == 1:
                    fpx = op_i if op_i < stop else stop
                else:
                    fpx = op_i if op_i > stop else stop
                return ("stop", float(fpx), int(tt[si]), True)
            op_i = oo[ti]
            if side == 1:
                fpx = op_i if op_i > target else target
            else:
                fpx = op_i if op_i < target else target
            return ("target", float(fpx), int(tt[ti]), True)
        # else: no 1s bars inside this 15m bar -> fall through to 15m OHLC
    # ---- 15m-OHLC fallback (adverse, gap-aware on the 15m open) ----
    if side == 1:
        s_hit = l15 <= stop; t_hit = h15 >= target
    else:
        s_hit = h15 >= stop; t_hit = l15 <= target
    if s_hit:
        if side == 1:
            fpx = o15 if o15 < stop else stop
        else:
            fpx = o15 if o15 > stop else stop
        return ("stop", float(fpx), int(bar_start), False)
    if t_hit:
        if side == 1:
            fpx = o15 if o15 > target else target
        else:
            fpx = o15 if o15 < target else target
        return ("target", float(fpx), int(bar_start), False)
    return None


def run(bars15: pd.DataFrame, s1s: dict, cost_R: float = 0.24) -> pd.DataFrame:
    """Simulate the VWAP-EMA bracket over every session in `bars15` (output of
    strategy.signals.add_signals). `s1s` = core.data.load_1s_index()."""
    cols = ["date", "tsec", "open", "high", "low", "close", "ema50", "ema20",
            "sig_side", "sig_ref", "sig_atr", "sess_bar"]
    g = bars15.groupby("date", sort=True)
    out = []
    for date, day in g:
        d = day.sort_values("tsec")
        tsec = d["tsec"].to_numpy(np.int64)
        op = d["open"].to_numpy(np.float64); hi = d["high"].to_numpy(np.float64)
        lo = d["low"].to_numpy(np.float64); cl = d["close"].to_numpy(np.float64)
        ema50 = d["ema50"].to_numpy(np.float64)
        ema20 = d["ema20"].to_numpy(np.float64)
        sig = d["sig_side"].to_numpy(np.int64)
        sref = d["sig_ref"].to_numpy(np.float64)
        satr = d["sig_atr"].to_numpy(np.float64)
        n = len(d)
        sess1s = s1s.get(np.datetime64(date, "ns"))

        pos = 0
        entry_px = stop_px = target_px = risk = np.nan
        side = 0; entry_tsec = -1; used_any_1s = False; tight20 = False
        loss_streak = 0; day_net_R = 0.0; halted = False

        j = 0
        while j < n:
            # --- open a new position at this bar's open if flat and prev bar signaled
            if pos == 0:
                if j >= 1 and sig[j - 1] != 0 and np.isfinite(satr[j - 1]):
                    if halted or ("entry_blocked" in d and bool(d["entry_blocked"].iloc[j])):
                        j += 1
                        continue
                    side = int(sig[j - 1])
                    entry_px = op[j]
                    if side == 1:
                        stop_px = sref[j - 1] - 0.5 * satr[j - 1]
                    else:
                        stop_px = sref[j - 1] + 0.5 * satr[j - 1]
                    risk = abs(entry_px - stop_px)
                    if not (risk > 0):
                        pos = 0; j += 1; continue
                    target_px = entry_px + side * 3.0 * risk
                    pos = side; entry_tsec = int(tsec[j]); used_any_1s = False
                    tight20 = False
                else:
                    j += 1
                    continue

            # --- manage the open position on bar j ---
            res = _intrabar(side, stop_px, target_px, sess1s, int(tsec[j]),
                            op[j], hi[j], lo[j])
            if res is not None:
                reason, fpx, xtsec, u1s = res
                used_any_1s = used_any_1s or u1s
                gross_R = (fpx - entry_px) * side / risk
                net_R = gross_R - cost_R
                day_net_R += net_R
                loss_streak = loss_streak + 1 if net_R < 0 else 0
                halted = loss_streak >= 3 or day_net_R <= -3.0
                out.append((date, side, entry_tsec, xtsec, entry_px, fpx,
                            stop_px, target_px, (fpx - entry_px) * side, risk,
                            gross_R, reason, used_any_1s, tight20))
                pos = 0; j += 1
                continue

            # no target/stop: reaching +2.5R switches the close trail to EMA20.
            if side == 1 and hi[j] >= entry_px + 2.5 * risk:
                tight20 = True
            elif side == -1 and lo[j] <= entry_px - 2.5 * risk:
                tight20 = True
            active_ema = ema20[j] if tight20 else ema50[j]
            trail_hit = (cl[j] < active_ema) if side == 1 else (cl[j] > active_ema)
            forced = (j == n - 1)  # actual last available bar, including holidays
            if trail_hit or forced:
                reason = ("trail20" if tight20 else "trail50") if trail_hit else "eod"
                gross_R = (cl[j] - entry_px) * side / risk
                net_R = gross_R - cost_R
                day_net_R += net_R
                loss_streak = loss_streak + 1 if net_R < 0 else 0
                halted = loss_streak >= 3 or day_net_R <= -3.0
                out.append((date, side, entry_tsec, int(tsec[j]), entry_px, cl[j],
                            stop_px, target_px, (cl[j] - entry_px) * side, risk,
                            gross_R, reason, used_any_1s, tight20))
                pos = 0; j += 1
                continue

            j += 1   # carry the position to the next bar

    return pd.DataFrame(out, columns=[
        "date", "side", "entry_tsec", "exit_tsec", "entry_px", "exit_px",
        "stop_px", "target_px", "points", "risk_pts", "gross_R", "reason",
        "used_1s", "ema20_tightened"])
