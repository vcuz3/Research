"""Stage-B (EXP-0004) exit simulator: the reference book's anchor-retrace fill.

`_stage_a_lib` is deliberately fill-free ("Nothing in this module simulates a
fill"). Stage B needs a fill, so it lives here and is trade-level parity-tested in
`test_stage_b.py` against synthetic paths whose answers are known by hand -- the same
discipline `_bracket_engine` follows, because a fill artifact is the failure mode that
has cost this workspace the most (RULES.md §A, the NQ VWAP postmortem).

The book has NO STOP. Its only exit is an **anchor-retrace limit**: a resting order to
close the position when price returns to the anchor -- the close of the bar *before* the
signal bar, i.e. the level price displaced away from. For a down-displacement we are long
and the anchor sits ABOVE entry (a sell limit); for an up-displacement we are short and it
sits BELOW (a buy limit). By construction the anchor is on the favourable side, so a filled
anchor exit is a fixed positive P&L of ``|anchor - entry|``.

Three rules govern the fill, all conservative:

* **A touch is not a fill (Rule 4).** With midpoint OHLC and no volume there is no queue
  evidence, so the frozen book credits the limit only when the favourable extreme trades
  *through* the anchor by a **volatility-scaled guard** ``g*sigma`` (never a fixed tick --
  LEARNINGS §6). ``mode='touch'`` (guard 0) is the optimistic upper bound; ``mode='time'``
  ignores the anchor entirely and is the market-exit floor.
* **No unavailable price improvement (Rule 1).** A gap that opens beyond the anchor still
  fills at the anchor price, never the better open.
* **Adverse/degenerate cases are pre-filtered, and defended here too.** If the anchor is not
  strictly favourable at entry (price already retraced past it before we entered -- possible
  on a sharp snapback at delay-1), there is no valid limit to rest. The book excludes these as
  a causal no-entry (see ``anchor_favourable``); should any reach the simulator it holds them
  to the cap rather than booking a fabricated fill. This defensive branch is therefore
  unreachable for the frozen book but kept so the function is safe in isolation.

Path indexing matches the audited engines: ``paths[name]`` is ``(n, width)``, column m is
the minute ``entry + m``, entry price is ``open[:, 0]``, the position lives through bars
``0 .. cap-1``, and a market exit after ``cap`` minutes is ``open[:, cap]``. ``cap`` may be
a per-trade array so the Friday-flat force-close can shorten individual trades without
disturbing the rest.
"""

from __future__ import annotations

import numpy as np

from _run_rsi_broad_regime_sweep import PIP


def simulate_anchor_retrace(paths, side, entry_px, anchor_px, guard_px, cap,
                            mode: str = "guarded", pip: float = PIP):
    """Anchor-retrace P&L in pips with a market exit at ``cap``.

    Parameters
    ----------
    paths : dict with 'open','high','low' arrays, each (n, width). Column m is minute
        entry+m. ``open[:, 0]`` must equal ``entry_px`` (asserted by callers via the grid).
    side : +1 long / -1 short (n,).
    entry_px : entry price (n,); the reference for P&L.
    anchor_px : the limit-exit price (n,) -- the pre-displacement anchor.
    guard_px : trade-through guard in PRICE units (n,), ``g * sigma_price``. 0 in touch mode.
    cap : holding cap in bars/minutes (scalar or (n,)). Market exit price is ``open[:, cap]``.
    mode : 'guarded' (through by guard, fill at anchor), 'touch' (guard forced to 0),
        'time' (ignore the anchor; always the market exit at cap).

    Returns
    -------
    (pnl_pips, kind, exit_bar) : kind 1 = anchor limit, 0 = market/time exit; exit_bar is
        the 0-based bar the anchor triggered on (or ``cap`` for a market exit).
    """
    if mode not in ("guarded", "touch", "time"):
        raise ValueError(f"unknown mode {mode!r}")
    o, hi, lo = paths["open"], paths["high"], paths["low"]
    n, width = o.shape
    s = np.asarray(side, float)
    entry = np.asarray(entry_px, float)
    cap_arr = np.broadcast_to(np.asarray(cap), (n,)).astype(int)
    if cap_arr.max() >= width:
        raise ValueError(f"paths need > max(cap) columns; got width {width}, max cap {cap_arr.max()}")

    market_px = o[np.arange(n), cap_arr]
    market_pnl = s * (market_px - entry) / pip

    if mode == "time":
        return market_pnl, np.zeros(n, int), cap_arr

    anchor = np.asarray(anchor_px, float)
    guard = np.zeros(n) if mode == "touch" else np.asarray(guard_px, float)

    # Favourable distance from entry to the anchor. Must be strictly positive for a valid
    # resting limit; otherwise the anchor was already passed at entry -> ride to the cap.
    anchor_dist = s * (anchor - entry)                       # >0 normally, price units
    valid = anchor_dist > 0

    # The favourable extreme per bar, as displacement from entry in the favourable direction.
    fav = np.where(s[:, None] > 0, hi, lo)
    fav_disp = s[:, None] * (fav - entry[:, None])           # (n, width), price units

    # Trigger when the favourable extreme trades THROUGH the anchor by the guard, on a bar
    # the position is actually live (0 .. cap-1). trigger_level is distance-from-entry.
    trigger_level = (anchor_dist + guard)[:, None]
    live = (np.arange(width)[None, :] < cap_arr[:, None])
    through = live & valid[:, None] & (fav_disp >= trigger_level)

    filled = through.any(axis=1)
    exit_bar = np.where(filled, through.argmax(axis=1), cap_arr)

    # Fill at the anchor price exactly (never improved past it, Rule 1). A filled anchor
    # exit is the fixed favourable distance; unfilled trades take the market exit at cap.
    anchor_pnl = anchor_dist / pip                           # == s*(anchor-entry)/pip, >0
    pnl = np.where(filled, anchor_pnl, market_pnl)
    kind = np.where(filled, 1, 0)
    return pnl, kind, exit_bar


def anchor_favourable(side, entry_px, anchor_px):
    """True where the anchor is strictly on the favourable side of the entry.

    The book's thesis is a reversion TO the anchor, so the exit limit must rest on the
    favourable side of entry (a sell limit above a long, a buy limit below a short). If
    price has already retraced to or through the anchor by the (delayed) entry, the limit
    is marketable and the reversion premise is spent -- a causal **no-entry** condition,
    since both the entry price and the anchor are known at entry. The book drops these
    signals rather than resting a non-deployable limit or booking a fabricated fill; this
    is the prespecified handling for the case ``simulate_anchor_retrace`` otherwise treats
    defensively by holding to the cap.
    """
    s = np.asarray(side, float)
    return s * (np.asarray(anchor_px, float) - np.asarray(entry_px, float)) > 0


def friday_cap_minutes(ny_weekday, ny_minute, base_cap: int, friday_flat_ny_minute: int):
    """Per-trade holding cap, shortened so no trade is held across the Friday 16:55 NY flat.

    A trade entered on Friday (NY weekday 4) whose base window would cross the force-flat
    minute is capped at the minutes remaining to the flat; every other trade keeps the base
    cap. Entries at or after the flat on Friday get cap 0 and must be vetoed by the caller
    (they cannot be held at all).
    """
    wd = np.asarray(ny_weekday, int)
    m = np.asarray(ny_minute, int)
    cap = np.full(len(wd), int(base_cap), int)
    on_friday = wd == 4
    to_flat = friday_flat_ny_minute - m
    crosses = on_friday & (m + base_cap > friday_flat_ny_minute)
    cap[crosses] = np.clip(to_flat[crosses], 0, base_cap)
    return cap
