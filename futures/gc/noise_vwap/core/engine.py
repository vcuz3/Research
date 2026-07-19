"""
Intraday-momentum "Noise Area + VWAP" trading engine (Zarattini / Quantitativo).

One row per closed trade. Fills are HONEST (CLAUDE.md rule A):
  * Decisions are taken on the CLOSE of a decision bar (Concretum clock: :59/:29).
  * Every entry / exit / flip fills at the NEXT 1-min bar's OPEN. Never the
    signal bar's close, never at the band/stop level (that would be time travel
    for a market order, rule 1/2).
  * Forced flatten uses the LAST RTH bar's close (market-on-close proxy).
  * Because we only ever fill at a subsequent bar's open, there is no intrabar
    high/low ambiguity to resolve for the fill itself (rule 3).

Signal (trend-following), evaluated only at decision timestamps. The DEFAULTS below
are the faithful published (Concretum) config, established by the forensic review
(FORENSIC.md): the Concretum decision clock and the VWAP entry gate. An earlier
implementation used the `:00/:30` clock and no VWAP gate; that was an off-by-one
bug worth ~0.2-0.4 Sharpe and is retained only via explicit args for the ablation.
  * flat  & close > upper & close > vwap  -> go long   (require_vwap default ON)
  * flat  & close < lower & close < vwap  -> go short
  * long  & close < max(upper, vwap)      -> exit long
  * short & close > min(lower, vwap)      -> exit short
  * a reverse signal flips (exit + enter opposite) at the same decision bar.
  * flat at RTH close.

The engine returns per-trade points BEFORE costs; costs are applied by the caller
so gross and net are both visible (rule 20).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Faithful published "Concretum" decision clock: min_from_open % 30 == 0 with
# 09:30 counted as minute 1 -> decisions at 09:59, 10:29, ..., 15:59 ET, with
# exposure applied from the next bar. (tod = 570 + (minute - 1).)
DECISION_TODS = [570 + k - 1 for k in range(30, 391, 30)]  # 599,629,...,959
# Legacy :00/:30 clock (10:00..15:30) -- the off-by-one bug; kept for the ablation.
DECISION_TODS_HH30 = [h * 60 + m for h in range(10, 16) for m in (0, 30)]  # 600..930


def simulate_session(bars: pd.DataFrame, band: pd.DataFrame,
                     decision_tods=DECISION_TODS, fill_mode="next_open",
                     require_vwap=True, exit_check="decision") -> list[dict]:
    """
    Simulate one RTH session.

    bars: rows for one date, sorted by tod, with columns
          tod, open, high, low, close, vwap  (1-min bars, 09:30..15:59).
    band: rows for the same date with tod, upper, lower  (defined at decision
          tods once the lookback history exists).
    fill_mode:
        "next_open"    -- HONEST: fill at the next bar's open (rule 1/2).
        "signal_close" -- AGGRESSIVE: fill at the decision bar's OWN close, i.e.
                          trade at the price that generated the signal. This is
                          the same-bar fill the paper's source code uses; it is a
                          look-ahead on the fill and is provided ONLY to quantify
                          how much of the headline it manufactures (rule 2).
    """
    b = bars.sort_values("tod").reset_index(drop=True)
    tod = b["tod"].to_numpy()
    opn = b["open"].to_numpy()
    close = b["close"].to_numpy()
    vwap = b["vwap"].to_numpy()
    n = len(b)

    # tod -> row index
    idx = {int(t): i for i, t in enumerate(tod)}
    band_map = {int(r.tod): (r.upper, r.lower) for r in band.itertuples()}

    last_i = n - 1
    last_close = close[last_i]

    pos = 0           # +1 long, -1 short, 0 flat
    entry_px = np.nan
    entry_tod = None
    trades: list[dict] = []

    def fill_next_open(i: int):
        """Fill price/tod for a decision at bar i. Honest = next bar open."""
        if fill_mode == "signal_close":
            return close[i], tod[i]
        if i + 1 <= last_i:
            return opn[i + 1], tod[i + 1]
        return None, None

    decision_set = {int(t) for t in decision_tods}
    the_date = b["date"].iloc[0]

    def close_trade(i, reason):
        """Fill the exit at the next bar open; returns False if unfillable."""
        nonlocal pos, entry_px, entry_tod
        px, ptod = fill_next_open(i)
        if px is None:
            return False
        trades.append(dict(date=the_date, side=pos, entry_tod=entry_tod,
                           exit_tod=ptod, entry_px=entry_px, exit_px=px,
                           points=(px - entry_px) * pos, reason=reason))
        pos, entry_px, entry_tod = 0, np.nan, None
        return True

    # iterate every bar; entries/flips only at decision tods; stop exits at
    # decision tods always, and at EVERY bar if exit_check=="every_bar".
    for i in range(n):
        if i >= last_i:
            break
        t = int(tod[i])
        is_decision = t in decision_set and t in band_map
        band = band_map.get(t)
        if band is None:
            continue
        up, lo = band
        c = close[i]
        w = vwap[i]

        want = 0
        if is_decision:
            if c > up and (not require_vwap or c > w):
                want = 1
            elif c < lo and (not require_vwap or c < w):
                want = -1

        if pos != 0:
            stop = max(up, w) if pos == 1 else min(lo, w)
            hit = (c < stop) if pos == 1 else (c > stop)
            check_here = is_decision or exit_check == "every_bar"
            flip = is_decision and (want == -pos)
            if (hit and check_here) or flip:
                if close_trade(i, "flip" if flip else "stop") and flip:
                    px, ptod = fill_next_open(i)
                    pos, entry_px, entry_tod = want, px, ptod
                continue

        if pos == 0 and is_decision and want != 0:
            px, ptod = fill_next_open(i)
            if px is not None:
                pos, entry_px, entry_tod = want, px, ptod

    # forced flatten at RTH close
    if pos != 0:
        pts = (last_close - entry_px) * pos
        trades.append(dict(date=b["date"].iloc[0], side=pos,
                           entry_tod=entry_tod, exit_tod=int(tod[last_i]),
                           entry_px=entry_px, exit_px=last_close, points=pts,
                           reason="eod"))
    return trades


def run(bars: pd.DataFrame, bands: pd.DataFrame,
        decision_tods=DECISION_TODS, fill_mode="next_open",
        require_vwap=True, exit_check="decision") -> pd.DataFrame:
    """Run all sessions. bars/bands are the full long frames for one instrument."""
    band_by_date = {d: g for d, g in bands.groupby("date", sort=False)}
    out: list[dict] = []
    for d, g in bars.groupby("date", sort=False):
        bd = band_by_date.get(d)
        if bd is None or bd.empty:
            continue
        out.extend(simulate_session(g, bd, decision_tods, fill_mode,
                                    require_vwap, exit_check))
    return pd.DataFrame(out)
