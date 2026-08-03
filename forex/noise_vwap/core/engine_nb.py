"""
Numba kernel for `core/engine.py`. Same rules, same fills, ~2 orders of
magnitude faster, which is what makes the 40-draw full-pipeline Null C feasible.

The pattern is the workspace's standard one: vectorised pandas preprocessing
(align the bands onto the bars once, flag decision and stop-check bars once),
then a single `@njit` scalar loop over session offsets. `tests/test_parity.py`
asserts TRADE-LEVEL equality with the reference engine on real data -- aggregate
agreement is not enough to catch an off-by-one.

`core/engine.py` remains the readable reference and the definition of the rules;
this file must never diverge from it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from .engine import STOP_REFS

_STOP_CODE = {"both": 0, "band": 1, "anchor": 2, "none": 3}


@njit(cache=True)
def _kernel(sess_start, sess_end, mfo, opn, close, anchor, upper, lower,
            has_band, is_decision, is_check, stop_code, require_gate,
            force_dir, fade, max_trades):
    out_sess = np.empty(max_trades, np.int64)
    out_side = np.empty(max_trades, np.int64)
    out_emfo = np.empty(max_trades, np.int64)
    out_xmfo = np.empty(max_trades, np.int64)
    out_epx = np.empty(max_trades, np.float64)
    out_xpx = np.empty(max_trades, np.float64)
    out_reason = np.empty(max_trades, np.int64)   # 0 stop, 1 flip, 2 eod
    k = 0

    for s in range(len(sess_start)):
        lo_i = sess_start[s]
        hi_i = sess_end[s]          # exclusive
        n = hi_i - lo_i
        if n < 2:
            continue
        last_i = hi_i - 1

        pos = 0
        entry_px = 0.0
        entry_mfo = -1

        for i in range(lo_i, last_i):
            if not has_band[i]:
                continue
            up = upper[i]
            lw = lower[i]
            c = close[i]
            a = anchor[i]
            dec = is_decision[i]

            want = 0
            if dec:
                if force_dir != 0:
                    if pos == 0:
                        want = force_dir
                else:
                    if c > up and ((not require_gate) or c > a):
                        want = 1
                    elif c < lw and ((not require_gate) or c < a):
                        want = -1
                    if fade:
                        want = -want

            if pos != 0 and force_dir == 0:
                hit = False
                if stop_code != 3:
                    if stop_code == 0:
                        stop = up if up > a else a
                        if pos == -1:
                            stop = lw if lw < a else a
                    elif stop_code == 1:
                        stop = up if pos == 1 else lw
                    else:
                        stop = a
                    hit = (c < stop) if pos == 1 else (c > stop)
                flip = dec and (want == -pos)
                if (hit and is_check[i]) or flip:
                    px = opn[i + 1]
                    out_sess[k] = s
                    out_side[k] = pos
                    out_emfo[k] = entry_mfo
                    out_xmfo[k] = mfo[i + 1]
                    out_epx[k] = entry_px
                    out_xpx[k] = px
                    out_reason[k] = 1 if flip else 0
                    k += 1
                    pos = 0
                    entry_px = 0.0
                    entry_mfo = -1
                    if flip:
                        pos = want
                        entry_px = px
                        entry_mfo = mfo[i + 1]
                    continue

            if pos == 0 and dec and want != 0:
                pos = want
                entry_px = opn[i + 1]
                entry_mfo = mfo[i + 1]

        if pos != 0:
            out_sess[k] = s
            out_side[k] = pos
            out_emfo[k] = entry_mfo
            out_xmfo[k] = mfo[last_i]
            out_epx[k] = entry_px
            out_xpx[k] = close[last_i]
            out_reason[k] = 2
            k += 1

    return (out_sess[:k], out_side[:k], out_emfo[:k], out_xmfo[:k],
            out_epx[:k], out_xpx[:k], out_reason[:k])


def _prepare(bars: pd.DataFrame, bands: pd.DataFrame, decision_mfos,
             exit_check):
    b = bars.sort_values(["date", "mfo"]).reset_index(drop=True)
    bd = bands[["date", "mfo", "upper", "lower"]]
    m = b.merge(bd, on=["date", "mfo"], how="left", sort=False)

    upper = m["upper"].to_numpy(np.float64)
    lower = m["lower"].to_numpy(np.float64)
    has_band = np.isfinite(upper) & np.isfinite(lower)
    upper = np.nan_to_num(upper, nan=0.0)
    lower = np.nan_to_num(lower, nan=0.0)

    mfo = m["mfo"].to_numpy(np.int64)
    dec = np.isin(mfo, np.asarray(sorted(decision_mfos), dtype=np.int64))

    if exit_check == "every_bar":
        chk = np.ones(len(m), bool)
    elif exit_check == "decision":
        chk = dec.copy()
    else:
        cad = int(exit_check)
        chk = ((mfo + 1) % cad == 0) | dec

    dates = m["date"].to_numpy()
    edges = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1]])
    starts = edges
    ends = np.r_[edges[1:], len(m)]
    sess_dates = dates[starts]
    return m, mfo, starts, ends, sess_dates, upper, lower, has_band, dec, chk


def run(bars: pd.DataFrame, bands: pd.DataFrame, decision_mfos,
        fill_mode: str = "next_open", require_gate: bool = True,
        stop_ref: str = "both", exit_check: str = "every_bar",
        force_dir: int = 0, fade: bool = False) -> pd.DataFrame:
    """Numba-backed drop-in for `core.engine.run` (next-open fills only)."""
    if fill_mode != "next_open":
        raise NotImplementedError("engine_nb implements the honest next_open fill only")
    if stop_ref not in STOP_REFS:
        raise ValueError(f"unknown stop_ref {stop_ref!r}")

    m, mfo, starts, ends, sess_dates, upper, lower, has_band, dec, chk = \
        _prepare(bars, bands, decision_mfos, exit_check)

    res = _kernel(starts, ends, mfo,
                  m["open"].to_numpy(np.float64), m["close"].to_numpy(np.float64),
                  m["twap"].to_numpy(np.float64), upper, lower,
                  has_band, dec, chk, _STOP_CODE[stop_ref],
                  bool(require_gate), int(force_dir), bool(fade), len(m))
    si, side, emfo, xmfo, epx, xpx, reason = res
    names = np.array(["stop", "flip", "eod"])
    out = pd.DataFrame(dict(
        date=sess_dates[si], side=side, entry_mfo=emfo, exit_mfo=xmfo,
        entry_px=epx, exit_px=xpx, points=(xpx - epx) * side,
        reason=names[reason]))
    return out[["date", "side", "entry_mfo", "exit_mfo", "entry_px", "exit_px",
                "points", "reason"]]
