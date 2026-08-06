"""Triple-barrier (vol-sized TP + vol-sized SL + timeout) fill simulator.

The single-barrier engine (`_rsi_stop_engine.simulate`) deliberately avoids a
target so there is no intrabar stop-versus-target ordering to resolve. This adds
the target back, which reintroduces exactly that ambiguity, so the fills follow
the workspace rules that bit hardest before:

  * RULE 3 (adverse resolution): if a single 1-minute bar touches BOTH the target
    and the stop, the order is unobservable, so the STOP is credited. A naive
    "target wins" here manufactured a fake edge on GC that vanished on 1-second
    bars (LEARNINGS 2026-07-19); adverse resolution is the conservative default.
  * RULE 5 (gap-through): a bar that OPENS beyond the stop fills at that open, not
    the stop level. A bar that opens beyond the target fills at the target (a
    resting limit is never improved past its own price).
  * Slippage is adverse and applies to the STOP only; the target is a passive
    limit and the timeout is a market exit at the bar open, matching the
    single-barrier engine's fixed-horizon exit.

Path indexing matches `_rsi_stop_engine`: column m is bar i+1+m, entry is
open(i+1) = O[:, 0], the position lives through bars 0 .. horizon-1, and a timeout
exits at O[:, horizon].
"""

from __future__ import annotations

import numpy as np

from _run_rsi_broad_regime_sweep import PIP


def simulate_bracket(paths, side, tp_dist, sl_dist, horizon, slippage_pips=0.0, pip=PIP):
    """P&L in pips for a vol-sized TP/SL bracket with a timeout at `horizon`.

    `tp_dist`, `sl_dist` are distances in PIPS (scalars or per-trade arrays), e.g.
    ``k_tp * sigma_pips``. The position lives through bars 0 .. horizon-1; if
    neither barrier is touched it exits at ``O[:, horizon]``.

    Returns (pnl_pips, kind) where kind is 0 = timeout, 1 = target, -1 = stop.
    """
    o, hi, lo = paths["open"], paths["high"], paths["low"]
    n, width = o.shape
    if width < int(horizon) + 1:
        raise ValueError(f"paths need >= horizon+1 columns; got {width} for horizon {horizon}")
    s = np.asarray(side, float)
    entry = o[:, 0]

    tp_px = entry + s * np.broadcast_to(np.asarray(tp_dist, float), (n,)) * pip
    sl_px = entry - s * np.broadcast_to(np.asarray(sl_dist, float), (n,)) * pip

    fav = np.where(s[:, None] > 0, hi, lo)   # favourable extreme (for the target)
    adv = np.where(s[:, None] > 0, lo, hi)   # adverse extreme (for the stop)

    live = np.arange(width)[None, :] < int(horizon)
    tp_hit = live & (s[:, None] * fav >= s[:, None] * tp_px[:, None])
    sl_hit = live & (s[:, None] * adv <= s[:, None] * sl_px[:, None])
    event = tp_hit | sl_hit

    any_event = event.any(axis=1)
    first = event.argmax(axis=1)                 # first touched bar (0 if none)
    rows = np.arange(n)
    # adverse tiebreak: if the stop is touched on the first event bar, it is a stop
    is_stop = any_event & sl_hit[rows, first]
    is_target = any_event & ~sl_hit[rows, first]
    is_timeout = ~any_event

    open_at = o[rows, np.clip(first, 0, width - 1)]
    gap_sl = s * open_at <= s * sl_px            # opened already through the stop
    sl_fill = np.where(gap_sl, open_at, sl_px) - s * slippage_pips * pip

    tp_fill = tp_px                              # limit never improved past its price
    timeout_px = o[rows, int(horizon)]

    px = np.where(is_stop, sl_fill, np.where(is_target, tp_fill, timeout_px))
    pnl = s * (px - entry) / pip
    kind = np.where(is_stop, -1, np.where(is_target, 1, 0))
    return pnl, kind
