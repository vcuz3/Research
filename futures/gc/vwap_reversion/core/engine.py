"""
VWAP standard-deviation-band MEAN-REVERSION (fade) engine for GC, 1-min bars.

Strategy (baseline):
  * Track only inside the entry window (default 10:00..15:00 ET) of the RTH
    session (09:30..16:00 ET).
  * Entry is a resting LIMIT at the kb-sigma VWAP band:
      - a bar whose HIGH reaches vwap + kb*sigma  -> SELL (short) filled at that
        band price (fade the up-move back toward VWAP);
      - a bar whose LOW  reaches vwap - kb*sigma   -> BUY (long) at the band.
    VWAP and sigma are FROZEN at the entry bar. Target = frozen VWAP; stop =
    vwap ± ks*sigma (frozen). With kb=2, ks=3 the reward is 2*sigma and the risk
    is 1*sigma -> a fixed 2:1 reward:risk bracket.
  * One position at a time; after an exit, no new entry for `min_gap` minutes.
  * Flat at the RTH close (last bar), exit at that bar's close.

Fill feasibility (CLAUDE.md rule A; the VWAP-band family has manufactured false
edges here before -- see nq/vwap_std_breakout_1/REVIEW.md). This engine is a
LIMIT-fade, not a stop-breakout, so:
  * ENTRY is a passive limit resting at the band BEFORE price reaches it. A bar
    that trades to the band fills the limit AT the band price (rule 1 satisfied:
    the order existed and the credited price was attainable). Optimism that
    remains is QUEUE priority (rule 4): a touch is modelled as a fill. We assert
    the touch and stress it with a strict trade-THROUGH variant (require the
    extreme to pierce the band by `touch_buf_pt`).
  * EXITS are bracket limits/stops. Intrabar path between a bar's high and low is
    unknown, so path ambiguity is resolved ADVERSELY (rule 3): if a bar can reach
    BOTH the stop and the target, the STOP is taken.
  * SAME-BAR: on the entry bar only an adverse STOP may trigger; a same-bar TARGET
    win is NOT credited (that would assume a favourable intrabar path we cannot
    prove). A target requires a strictly later bar. This is the conservative
    default; `entry_bar_target=True` relaxes it for a sensitivity check.

Output: one row per closed trade, points BEFORE costs (costs applied by the
caller so gross and net are both visible, rule 20).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

_REASON = np.array(["stop", "target", "eod"])


@njit(cache=True)
def _sim_all(offsets, frel_s, lastc_s,
             tsec, opn, high, low, close, vwap, sigma,
             kb, ks, entry_start, entry_end, min_gap,
             touch_buf, entry_bar_target,
             o_sess, o_side, o_etod, o_xtod, o_epx, o_xpx, o_tgt, o_stp,
             o_pts, o_risk, o_reason, o_samebar):
    """One native call for the whole backtest. Returns trade count nt; caller
    slices outputs to [:nt]. `risk` is the frozen 1R distance (points) so the
    caller can express P&L in R as well as points."""
    nsess = offsets.shape[0] - 1
    cap = o_sess.shape[0]
    nt = 0
    for s in range(nsess):
        # defensive: a session cannot produce more than a few dozen trades; stop
        # before any chance of writing past the pre-allocated output (numba does
        # not bounds-check). cap is sized with generous slack in run().
        if nt + 64 >= cap:
            break
        start = offsets[s]
        end = offsets[s + 1]
        n = end - start
        if n == 0:
            continue
        frel = frel_s[s]         # local index of last RTH bar (forced-flat bar)
        lastc = lastc_s[s]

        pos = 0
        entry_px = np.nan
        target_px = np.nan
        stop_px = np.nan
        risk = np.nan
        entry_tod = -1
        last_exit_tod = -100000   # allow the first entry with no prior exit

        for j in range(n):
            i = start + j
            t = tsec[i]

            # ---------------- manage an open position (any bar) ----------------
            if pos != 0:
                if j >= frel:
                    # forced flat at the RTH close
                    fpx = lastc
                    o_sess[nt] = s
                    o_side[nt] = pos
                    o_etod[nt] = entry_tod
                    o_xtod[nt] = t
                    o_epx[nt] = entry_px
                    o_xpx[nt] = fpx
                    o_tgt[nt] = target_px
                    o_stp[nt] = stop_px
                    o_pts[nt] = (fpx - entry_px) * pos
                    o_risk[nt] = risk
                    o_reason[nt] = 2
                    o_samebar[nt] = 0
                    nt += 1
                    pos = 0
                    last_exit_tod = t
                    continue

                if pos == -1:
                    stop_hit = high[i] >= stop_px
                    target_hit = low[i] <= target_px
                else:
                    stop_hit = low[i] <= stop_px
                    target_hit = high[i] >= target_px

                # gap-aware fills (rule 5): if the bar OPENED past the level, the
                # first tradable price is the open, not the stale level. For a stop
                # that is adverse (worse); for a target limit it is favourable.
                oi = opn[i]
                if stop_hit:                       # adverse first (rule 3)
                    if pos == -1:
                        fpx = oi if oi > stop_px else stop_px
                    else:
                        fpx = oi if oi < stop_px else stop_px
                    reason = 0
                elif target_hit:
                    if pos == -1:
                        fpx = oi if oi < target_px else target_px
                    else:
                        fpx = oi if oi > target_px else target_px
                    reason = 1
                else:
                    fpx = np.nan
                    reason = -1

                if reason >= 0:
                    o_sess[nt] = s
                    o_side[nt] = pos
                    o_etod[nt] = entry_tod
                    o_xtod[nt] = t
                    o_epx[nt] = entry_px
                    o_xpx[nt] = fpx
                    o_tgt[nt] = target_px
                    o_stp[nt] = stop_px
                    o_pts[nt] = (fpx - entry_px) * pos
                    o_risk[nt] = risk
                    o_reason[nt] = reason
                    o_samebar[nt] = 0
                    nt += 1
                    pos = 0
                    last_exit_tod = t
                continue   # never also enter on a bar we managed/exited

            # ---------------- look for a fresh entry ----------------
            if j >= frel:
                continue
            if t < entry_start or t >= entry_end:
                continue
            if t < last_exit_tod + min_gap:
                continue
            sg = sigma[i]
            if not np.isfinite(sg) or sg <= 0.0:
                continue
            w = vwap[i]
            up = w + kb * sg
            lo = w - kb * sg

            side = 0
            epx = np.nan
            oi = opn[i]
            if high[i] >= up + touch_buf:          # short fade the upper band
                side = -1
                epx = oi if oi > up else up        # gap-aware limit fill (rule 5)
            elif low[i] <= lo - touch_buf:         # long fade the lower band
                side = 1
                epx = oi if oi < lo else lo

            if side == 0:
                continue

            tgt = w
            if side == -1:
                stp = w + ks * sg
            else:
                stp = w - ks * sg
            rsk = abs(epx - stp)

            # same-bar resolution: adverse STOP only (target needs a later bar)
            same_stop = (high[i] >= stp) if side == -1 else (low[i] <= stp)
            same_tgt = False
            if entry_bar_target and not same_stop:
                same_tgt = (low[i] <= tgt) if side == -1 else (high[i] >= tgt)

            if same_stop or same_tgt:
                if same_stop:
                    fpx = oi if ((side == -1 and oi > stp) or (side == 1 and oi < stp)) else stp
                else:
                    fpx = oi if ((side == -1 and oi < tgt) or (side == 1 and oi > tgt)) else tgt
                o_sess[nt] = s
                o_side[nt] = side
                o_etod[nt] = t
                o_xtod[nt] = t
                o_epx[nt] = epx
                o_xpx[nt] = fpx
                o_tgt[nt] = tgt
                o_stp[nt] = stp
                o_pts[nt] = (fpx - epx) * side
                o_risk[nt] = rsk
                o_reason[nt] = 0 if same_stop else 1
                o_samebar[nt] = 1
                nt += 1
                last_exit_tod = t
                continue

            # open the position; managed from the NEXT bar
            pos = side
            entry_px = epx
            target_px = tgt
            stop_px = stp
            risk = rsk
            entry_tod = t

        # end-of-session safety flat (if still open past frel handling)
        if pos != 0:
            o_sess[nt] = s
            o_side[nt] = pos
            o_etod[nt] = entry_tod
            o_xtod[nt] = tsec[start + frel]
            o_epx[nt] = entry_px
            o_xpx[nt] = lastc
            o_tgt[nt] = target_px
            o_stp[nt] = stop_px
            o_pts[nt] = (lastc - entry_px) * pos
            o_risk[nt] = risk
            o_reason[nt] = 2
            o_samebar[nt] = 0
            nt += 1

    return nt


def run(bars: pd.DataFrame, kb: float = 2.0, ks: float = 3.0,
        entry_start: int = 36000, entry_end: int = 54000, min_gap: int = 900,
        touch_buf_pt: float = 0.0, entry_bar_target: bool = False) -> pd.DataFrame:
    """
    Simulate the VWAP-band fade over all sessions in `bars` (output of
    core.data.load_rth / load_rth_1s). Returns one row per closed trade.

    The engine is resolution-agnostic: it keys time on `tsec` (seconds from ET
    midnight), so the SAME kernel runs on 1-minute or 1-second bars. All windows
    are in SECONDS.

    kb           entry band multiple (touch vwap ± kb*sigma).
    ks           stop band multiple (stop at vwap ± ks*sigma). ks>kb.
                 reward=kb*sigma, risk=(ks-kb)*sigma -> RR = kb/(ks-kb).
    entry_start/entry_end  entry (tracking) window in SECONDS [start,end).
                 default 36000..54000 = 10:00..15:00 ET.
    min_gap      seconds to wait after an exit before a new entry (default 900=15m).
    touch_buf_pt strict trade-through guard (points): require the extreme to
                 pierce the band by this much before the limit is deemed filled
                 (queue-conservative sensitivity, rule 4). 0 = touch-fills.
    entry_bar_target  if True, allow a same-entry-bar TARGET win (optimistic);
                 default False = only an adverse same-bar stop is credited.
    """
    # Precondition: `bars` is time-sorted (load_rth/load_rth_1s sort by `et`, which
    # is exactly (date, tsec) order). We rely on that instead of re-sorting a ~40M
    # row frame (a full copy) at 1s. Guarded below.
    b = bars
    codes, uniq_dates = pd.factorize(b["date"], sort=False)
    tod = b["tsec"].to_numpy(np.int64)
    # cheap monotonic-within-session check without another sort
    _dsw = np.diff(codes)
    if np.any(_dsw < 0):
        b = bars.sort_values(["date", "tsec"]).reset_index(drop=True)
        codes, uniq_dates = pd.factorize(b["date"], sort=False)
        tod = b["tsec"].to_numpy(np.int64)
    opn = b["open"].to_numpy(np.float64)
    high = b["high"].to_numpy(np.float64)
    low = b["low"].to_numpy(np.float64)
    close = b["close"].to_numpy(np.float64)
    vwap = b["vwap"].to_numpy(np.float64)
    sigma = b["sigma"].to_numpy(np.float64)
    N = len(b)

    nsess = len(uniq_dates)
    sizes = np.bincount(codes, minlength=nsess)
    offsets = np.empty(nsess + 1, np.int64)
    offsets[0] = 0
    offsets[1:] = np.cumsum(sizes)

    # last-bar (forced-flat) index and close per session
    frel_s = (sizes - 1).astype(np.int64)
    lastc_s = close[offsets[:-1] + frel_s]

    # trades are gated to one-at-a-time with a min-gap, so the count is bounded by
    # sessions * (window / min_gap) plus slack -- vastly less than N at 1s (where a
    # per-bar output array would be ~40M rows * 12 * 8B ~ 3.8 GB). Cap accordingly.
    cap = min(N, max(4096, nsess * 64))
    o_sess = np.empty(cap, np.int64)
    o_side = np.empty(cap, np.int64)
    o_etod = np.empty(cap, np.int64)
    o_xtod = np.empty(cap, np.int64)
    o_epx = np.empty(cap, np.float64)
    o_xpx = np.empty(cap, np.float64)
    o_tgt = np.empty(cap, np.float64)
    o_stp = np.empty(cap, np.float64)
    o_pts = np.empty(cap, np.float64)
    o_risk = np.empty(cap, np.float64)
    o_reason = np.empty(cap, np.int64)
    o_samebar = np.empty(cap, np.int64)

    nt = _sim_all(
        offsets, frel_s, lastc_s,
        tod, opn, high, low, close, vwap, sigma,
        float(kb), float(ks), int(entry_start), int(entry_end), int(min_gap),
        float(touch_buf_pt), bool(entry_bar_target),
        o_sess, o_side, o_etod, o_xtod, o_epx, o_xpx, o_tgt, o_stp,
        o_pts, o_risk, o_reason, o_samebar)

    if nt == 0:
        return pd.DataFrame(columns=["date", "side", "entry_tsec", "exit_tsec",
                                     "entry_px", "exit_px", "target_px", "stop_px",
                                     "points", "risk_pts", "reason", "same_bar"])

    return pd.DataFrame({
        "date": uniq_dates[o_sess[:nt]],
        "side": o_side[:nt],
        "entry_tsec": o_etod[:nt],
        "exit_tsec": o_xtod[:nt],
        "entry_px": o_epx[:nt],
        "exit_px": o_xpx[:nt],
        "target_px": o_tgt[:nt],
        "stop_px": o_stp[:nt],
        "points": o_pts[:nt],
        "risk_pts": o_risk[:nt],
        "reason": _REASON[o_reason[:nt]],
        "same_bar": o_samebar[:nt].astype(bool),
    })
