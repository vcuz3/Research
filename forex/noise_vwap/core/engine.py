"""
Noise-Area + anchor intraday-momentum engine for FX, ported from
`futures/nq/noise_vwap/core/engine.py`.

Fills are honest (RULES.md section A):
  * decisions are taken on the CLOSE of a decision bar (Concretum clock);
  * every entry / exit / flip fills at the NEXT 1-minute bar's OPEN -- never the
    signal bar's own close, never at the band or stop level;
  * the forced flatten uses the LAST session bar's close;
  * because fills are always a later bar's open there is no intrabar high/low
    ordering to resolve (rule 3).

Signal, evaluated only at decision timestamps:
  * flat  & close > upper & (close > anchor)  -> long
  * flat  & close < lower & (close < anchor)  -> short
  * a reverse signal flips at the same decision bar
  * flat at session close

`stop_ref` is the axis this project exists to test, because FX has no volume and
therefore no VWAP (see `core/session.py`):
  "both"   long stop below max(upper, anchor); short above min(lower, anchor)
           -- the published rule with TWAP substituted for VWAP.
  "band"   long stop below `upper`; short above `lower`
           -- the user's "trail at the noise area" variant; uses NO anchor, so it
           is the only variant that is fully volume-free in both roles.
  "anchor" long stop below `anchor`; short above `anchor`
           -- the paper's flagship VWAP-touch exit, TWAP version.
  "none"   no stop at all: hold to the session close (or a flip).
           -- the EXIT-NEUTRAL arm. RULES.md rule 15 requires isolating the
           entry's contribution from the exit design, and a trailing stop is
           itself a payoff-shaping device; "none" removes the exit geometry
           entirely so what is left is the entry information plus costs.

`fade` re-executes the MIRROR of the signal (short an upper break, long a lower
break) through the whole engine. Rule 16: a mirror must be RE-RUN, never
obtained by multiplying realized P&L by -1 -- that shares the same fills and is
an algebraic identity, not a control.

Returns one row per closed trade with GROSS points (price units). Costs are
applied by the caller so gross and net stay separately inspectable (rule 20).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STOP_REFS = ("both", "band", "anchor", "none")


def simulate_session(bars: pd.DataFrame, band: pd.DataFrame, decision_mfos,
                     fill_mode: str = "next_open", require_gate: bool = True,
                     stop_ref: str = "both", exit_check: str = "every_bar",
                     force_dir: int = 0, fade: bool = False) -> list[dict]:
    """
    Simulate one session.

    bars: one date, columns mfo, open, close, twap, date (sorted by mfo).
    band: same date, columns mfo, upper, lower.
    force_dir: 0 = normal signal. +1/-1 = the always-long / always-short drift
               control (rule 18): enter at the first decision bar that has a
               band and hold to the session close, ignoring bands and anchor.
    fade: re-execute the mirror of the signal through the full engine.
    """
    if stop_ref not in STOP_REFS:
        raise ValueError(f"unknown stop_ref {stop_ref!r}")

    b = bars.sort_values("mfo").reset_index(drop=True)
    mfo = b["mfo"].to_numpy()
    opn = b["open"].to_numpy()
    close = b["close"].to_numpy()
    anchor = b["twap"].to_numpy()
    n = len(b)
    if n < 2:
        return []

    band_map = {int(r.mfo): (r.upper, r.lower) for r in band.itertuples()}
    decision_set = {int(m) for m in decision_mfos}
    the_date = b["date"].iloc[0]

    last_i = n - 1
    last_close = close[last_i]

    cadence = int(exit_check) if isinstance(exit_check, (int, np.integer)) else None
    check_set = ({int(m) for m in mfo if (int(m) + 1) % cadence == 0}
                 if cadence is not None else None)

    pos = 0
    entry_px = np.nan
    entry_mfo = None
    trades: list[dict] = []

    def fill_next_open(i: int):
        if fill_mode == "signal_close":
            return close[i], mfo[i]
        if i + 1 <= last_i:
            return opn[i + 1], mfo[i + 1]
        return None, None

    def close_trade(i, reason):
        nonlocal pos, entry_px, entry_mfo
        px, pm = fill_next_open(i)
        if px is None:
            return False
        trades.append(dict(date=the_date, side=pos, entry_mfo=entry_mfo,
                           exit_mfo=pm, entry_px=entry_px, exit_px=px,
                           points=(px - entry_px) * pos, reason=reason))
        pos, entry_px, entry_mfo = 0, np.nan, None
        return True

    for i in range(n):
        if i >= last_i:
            break
        m = int(mfo[i])
        bd = band_map.get(m)
        if bd is None:
            continue
        up, lo = bd
        c = close[i]
        a = anchor[i]
        is_decision = m in decision_set

        want = 0
        if is_decision:
            if force_dir:
                want = force_dir if pos == 0 else 0
            elif c > up and (not require_gate or c > a):
                want = 1
            elif c < lo and (not require_gate or c < a):
                want = -1
            if fade:
                want = -want

        if pos != 0 and not force_dir:
            if stop_ref == "both":
                stop = max(up, a) if pos == 1 else min(lo, a)
            elif stop_ref == "band":
                stop = up if pos == 1 else lo
            elif stop_ref == "anchor":
                stop = a
            else:
                stop = None
            hit = False if stop is None else ((c < stop) if pos == 1 else (c > stop))
            check_here = (is_decision or exit_check == "every_bar"
                          or (check_set is not None and m in check_set))
            flip = is_decision and (want == -pos)
            if (hit and check_here) or flip:
                if close_trade(i, "flip" if flip else "stop") and flip:
                    px, pm = fill_next_open(i)
                    pos, entry_px, entry_mfo = want, px, pm
                continue

        if pos == 0 and is_decision and want != 0:
            px, pm = fill_next_open(i)
            if px is not None:
                pos, entry_px, entry_mfo = want, px, pm

    if pos != 0:
        trades.append(dict(date=the_date, side=pos, entry_mfo=entry_mfo,
                           exit_mfo=int(mfo[last_i]), entry_px=entry_px,
                           exit_px=last_close,
                           points=(last_close - entry_px) * pos, reason="eod"))
    return trades


def run(bars: pd.DataFrame, bands: pd.DataFrame, decision_mfos,
        fill_mode: str = "next_open", require_gate: bool = True,
        stop_ref: str = "both", exit_check: str = "every_bar",
        force_dir: int = 0, fade: bool = False) -> pd.DataFrame:
    """Run every session of one pair. `bars`/`bands` are the full long frames."""
    band_by_date = {d: g for d, g in bands.groupby("date", sort=False)}
    out: list[dict] = []
    for d, g in bars.groupby("date", sort=False):
        bd = band_by_date.get(d)
        if bd is None or bd.empty:
            continue
        out.extend(simulate_session(g, bd, decision_mfos, fill_mode,
                                    require_gate, stop_ref, exit_check,
                                    force_dir, fade))
    cols = ["date", "side", "entry_mfo", "exit_mfo", "entry_px", "exit_px",
            "points", "reason"]
    return pd.DataFrame(out, columns=cols)
