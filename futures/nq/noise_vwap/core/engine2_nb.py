"""
Numba/NumPy port of core.engine2. **Bit-for-bit** identical trade output to the
pandas engine (validated in scripts/bench_engine.py::parity), but the bar-by-bar
session loop runs in a single `@njit` kernel over the WHOLE dataset instead of a
Python loop per session.

Design (why it is fast, and why it stays honest):

  * pandas is kept for I/O and the vectorizable preprocessing ONLY: band lookup,
    within-session forward-fill, the decision-clock mask and the entry gate. None
    of that is bar-sequential, so it costs one vectorized pass over the frame.
  * the sequential part -- the thing that MUST be a scalar loop because each bar's
    action depends on the running position/stop/partial state -- is compiled once
    and then runs over flat float64/int64 arrays with zero pandas per-bar overhead.
  * sessions are laid out contiguously (sorted by sdate-appearance then mfo) and the
    kernel walks them via an `offsets` index, so there is ONE Python->native call
    for the entire backtest, not one per day.

The engine reads only close/open/vwap/is_rth/atr/ema -- exactly like engine2, which
never touches high/low (all decisions are close-based, all fills are open/close).
That is what makes an array port exact rather than approximate: there is no intrabar
high/low path to model, so nothing about fill feasibility changes (rule 1/2/3 hold
identically -- fills are still next-open or the aggressive signal-close, chosen by
`fill_mode`, and the kernel physically cannot read a price it could not have known).

Public API mirrors engine2.run 1:1 so it is a drop-in: `from ..core import engine2_nb
as E` and every scripts/* call works unchanged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

# integer codes for the string knobs (numba wants no python str compares in the loop)
_FILL = {"next_open": 0, "signal_close": 1}
_EXIT = {"decision": 0, "every_bar": 1}
_ENTRY = {"clock": 0, "threshold": 1, "delay": 2}
_STOPREF = {"both": 0, "vwap": 1, "band": 2}
_REASON = np.array(["stop", "flip", "eod"])


@njit(cache=True)
def _sim_all(offsets, flat_rel, atr_s, last_close_s,
             mfo, opn, close, vwap, ema, is_decision, allow,
             direct_up, direct_lo, ff_up, ff_lo,
             fill_mode, exit_check, entry_mode, stop_ref,
             require_vwap, trend_gate,
             entry_buf_atr, entry_persist, entry_delay,
             stop_buf_atr, tp_atr, tp_frac, be_atr,
             trail_step_atr, trail_start_atr,
             o_sess, o_side, o_emfo, o_xmfo, o_epx, o_xpx, o_pts, o_reason, o_tpf):
    """One native call for the whole backtest. Returns the trade count `nt`; the
    caller slices the pre-allocated output arrays to [:nt]. Every branch mirrors
    engine2.simulate_session line for line."""
    nsess = offsets.shape[0] - 1
    nt = 0
    for s in range(nsess):
        start = offsets[s]
        end = offsets[s + 1]
        n = end - start
        if n == 0:
            continue
        frel = flat_rel[s]                 # local index of the forced-flat (last RTH) bar
        atr = atr_s[s]
        atr_fin = np.isfinite(atr)
        lastc = last_close_s[s]
        buf = entry_buf_atr * atr if (entry_mode == 1 and atr_fin) else 0.0

        # -- event-entry precompute (threshold/delay): beyond-band(+buf)+VWAP masks --
        if entry_mode == 1 or entry_mode == 2:
            lok = np.zeros(n, dtype=np.bool_)
            sok = np.zeros(n, dtype=np.bool_)
            for j in range(n):
                i = start + j
                up = ff_up[i]
                lo = ff_lo[i]
                if np.isfinite(up):
                    c = close[i]
                    w = vwap[i]
                    if c > up + buf and (require_vwap == 0 or c > w):
                        lok[j] = True
                    if c < lo - buf and (require_vwap == 0 or c < w):
                        sok[j] = True

        # threshold: N-consecutive-bar confirmation run-lengths
        if entry_mode == 1:
            run_l = np.zeros(n, dtype=np.int64)
            run_s = np.zeros(n, dtype=np.int64)
            for j in range(n):
                if j > 0 and lok[j]:
                    run_l[j] = run_l[j - 1] + 1
                else:
                    run_l[j] = 1 if lok[j] else 0
                if j > 0 and sok[j]:
                    run_s[j] = run_s[j - 1] + 1
                else:
                    run_s[j] = 1 if sok[j] else 0

        # delay: arm a timer on first signal, enter `entry_delay` bars later iff still on
        if entry_mode == 2:
            delay_side = np.zeros(n, dtype=np.int64)
            pend = 0
            target = -1
            for j in range(n):
                if pend != 0 and j == target:
                    if (pend == 1 and lok[j]) or (pend == -1 and sok[j]):
                        delay_side[j] = pend
                    pend = 0
                    target = -1
                if pend == 0:
                    if lok[j]:
                        pend = 1
                        target = j + entry_delay
                    elif sok[j]:
                        pend = -1
                        target = j + entry_delay

        # -------------------- the bar-by-bar session simulation --------------------
        pos = 0
        entry_px = np.nan
        entry_mfo = -1
        banked = 0.0
        taken_frac = 0.0
        partial_done = False
        be_on = False
        fav_max = 0.0

        for j in range(n):
            if j >= frel:
                break
            i = start + j
            m = mfo[i]
            isd = is_decision[i]
            c = close[i]
            w = vwap[i]
            du = direct_up[i]
            dl = direct_lo[i]
            have_direct = np.isfinite(du)

            # clock mode skips minutes with no band entirely (no entry/stop/flip)
            if entry_mode == 0 and not have_direct:
                continue

            # stop band = engine2's `up_i,lo_i`: threshold uses the forward-filled
            # band; clock AND delay read the DIRECT band_map.get(m) (NaN off-clock).
            if entry_mode == 1:
                su = ff_up[i]
                sl = ff_lo[i]
            else:
                su = du
                sl = dl
            have_band = np.isfinite(su)

            # ---- desired entry direction ----
            want = 0
            if entry_mode == 0:
                if isd and have_direct:
                    if c > du and (require_vwap == 0 or c > w):
                        want = 1
                    elif c < dl and (require_vwap == 0 or c < w):
                        want = -1
            elif entry_mode == 2:
                want = delay_side[j]
            else:
                if run_l[j] >= entry_persist:
                    want = 1
                elif run_s[j] >= entry_persist:
                    want = -1

            # ---- higher-timeframe trend gate (side-aware veto) ----
            if trend_gate == 1 and want != 0 and np.isfinite(ema[i]):
                e = ema[i]
                if (want == 1 and not (c > e)) or (want == -1 and not (c < e)):
                    want = 0

            # ---- exits / flips ----
            if pos != 0:
                if have_band:
                    if stop_ref == 1:
                        base = w
                    elif stop_ref == 2:
                        base = su if pos == 1 else sl
                    else:
                        base = (su if su > w else w) if pos == 1 else (sl if sl < w else w)
                else:
                    base = w
                sbuf = stop_buf_atr * atr if atr_fin else 0.0
                stop = base - sbuf if pos == 1 else base + sbuf
                fav = (c - entry_px) * pos

                if be_atr > 0 and atr_fin:
                    if be_on or fav >= be_atr * atr:
                        be_on = True
                        if pos == 1:
                            if entry_px > stop:
                                stop = entry_px
                        else:
                            if entry_px < stop:
                                stop = entry_px

                if trail_step_atr > 0 and atr_fin and atr > 0:
                    if fav > fav_max:
                        fav_max = fav
                    start_t = trail_start_atr if trail_start_atr > 0 else trail_step_atr
                    step = trail_step_atr * atr
                    k = int(np.floor(fav_max / step))
                    if fav_max >= start_t * atr and k >= 1:
                        ratchet = entry_px + pos * (k - 1) * step
                        if pos == 1:
                            if ratchet > stop:
                                stop = ratchet
                        else:
                            if ratchet < stop:
                                stop = ratchet

                hit = (c < stop) if pos == 1 else (c > stop)
                check_here = isd or exit_check == 1
                flip = (want == -pos) and (isd if entry_mode == 0 else True)

                if (hit and check_here) or flip:
                    # close_trade: fill(i) -- next-open, or signal-close in aggressive mode
                    if fill_mode == 1:
                        fpx = close[i]
                        fmfo = m
                    else:
                        fpx = opn[i + 1]
                        fmfo = mfo[i + 1]
                    runner = (fpx - entry_px) * pos
                    o_sess[nt] = s
                    o_side[nt] = pos
                    o_emfo[nt] = entry_mfo
                    o_xmfo[nt] = fmfo
                    o_epx[nt] = entry_px
                    o_xpx[nt] = fpx
                    o_pts[nt] = banked + (1.0 - taken_frac) * runner
                    o_reason[nt] = 1 if flip else 0
                    o_tpf[nt] = taken_frac
                    nt += 1
                    pos = 0
                    entry_px = np.nan
                    entry_mfo = -1
                    if flip and allow[i]:
                        pos = want
                        entry_px = fpx
                        entry_mfo = fmfo
                        banked = 0.0
                        taken_frac = 0.0
                        partial_done = False
                        be_on = False
                        fav_max = 0.0
                    continue

                # ---- partial take-profit: bank tp_frac at next open once run tp_atr ----
                if tp_atr > 0 and not partial_done and atr_fin and fav >= tp_atr * atr:
                    if fill_mode == 1:
                        fpx = close[i]
                    else:
                        fpx = opn[i + 1]
                    banked = tp_frac * (fpx - entry_px) * pos
                    taken_frac = tp_frac
                    partial_done = True

            # ---- fresh entry ----
            if pos == 0 and want != 0:
                can_enter = (isd if entry_mode == 0 else True) and allow[i]
                if can_enter:
                    if fill_mode == 1:
                        fpx = close[i]
                        fmfo = m
                    else:
                        fpx = opn[i + 1]
                        fmfo = mfo[i + 1]
                    pos = want
                    entry_px = fpx
                    entry_mfo = fmfo
                    banked = 0.0
                    taken_frac = 0.0
                    partial_done = False
                    be_on = False
                    fav_max = 0.0

        # ---- forced flat at the RTH close ----
        if pos != 0:
            runner = (lastc - entry_px) * pos
            o_sess[nt] = s
            o_side[nt] = pos
            o_emfo[nt] = entry_mfo
            o_xmfo[nt] = mfo[start + frel]
            o_epx[nt] = entry_px
            o_xpx[nt] = lastc
            o_pts[nt] = banked + (1.0 - taken_frac) * runner
            o_reason[nt] = 2
            o_tpf[nt] = taken_frac
            nt += 1

    return nt


def run(bars: pd.DataFrame, bands: pd.DataFrame, decision_mfos,
        fill_mode="next_open", require_vwap=True, exit_check="decision",
        entry_mode="clock", entry_buf_atr=0.0, entry_gate=None,
        stop_ref="both", stop_buf_atr=0.0, trend_gate=False,
        entry_persist=1, tp_atr=0.0, tp_frac=0.5, be_atr=0.0,
        entry_delay=0, trail_step_atr=0.0, trail_start_atr=0.0) -> pd.DataFrame:
    """Drop-in replacement for engine2.run. Same args, same output frame."""
    # only simulate dates that actually have a band (engine2.run skips the rest)
    band_dates = pd.unique(bands["sdate"])
    b = bars[bars["sdate"].isin(band_dates)]
    if b.empty:
        return pd.DataFrame()

    # sessions contiguous in APPEARANCE order (matches groupby(sort=False)), mfo-sorted
    codes, uniq_dates = pd.factorize(b["sdate"], sort=False)
    order = np.lexsort((b["mfo"].to_numpy(), codes))
    codes = codes[order]
    b = b.iloc[order]

    mfo = b["mfo"].to_numpy(np.int64)
    opn = b["open"].to_numpy(np.float64)
    close = b["close"].to_numpy(np.float64)
    vwap = b["vwap"].to_numpy(np.float64)
    is_rth = b["is_rth"].to_numpy()
    N = len(b)

    # session offsets + per-session atr / flat / last_close
    nsess = len(uniq_dates)
    sizes = np.bincount(codes, minlength=nsess)
    offsets = np.empty(nsess + 1, np.int64)
    offsets[0] = 0
    offsets[1:] = np.cumsum(sizes)

    # atr is constant within a session -> take the first bar's value per session
    atr_col = b["atr"].to_numpy(np.float64)
    atr_s = atr_col[offsets[:-1]]

    # flat_rel: local index of the LAST is_rth bar (16:00 ET proxy); n-1 if no RTH bar
    flat_rel = np.empty(nsess, np.int64)
    last_close_s = np.empty(nsess, np.float64)
    for s in range(nsess):
        st, en = offsets[s], offsets[s + 1]
        rth_local = np.where(is_rth[st:en])[0]
        fr = int(rth_local[-1]) if rth_local.size else (en - st - 1)
        flat_rel[s] = fr
        last_close_s[s] = close[st + fr]

    # band lookup: direct (band_map.get) keyed by (sdate, mfo); last wins on dup
    bm = bands.drop_duplicates(["sdate", "mfo"], keep="last").set_index(["sdate", "mfo"])
    row_idx = pd.MultiIndex.from_arrays([b["sdate"].to_numpy(), mfo])
    direct_up = bm["upper"].reindex(row_idx).to_numpy(np.float64)
    direct_lo = bm["lower"].reindex(row_idx).to_numpy(np.float64)

    # forward-filled band (threshold/delay entry masks; threshold stop). Only the
    # threshold STOP and both event-entry masks read it; clock & delay stop read the
    # direct band. Computed only when needed; a harmless alias otherwise.
    em = _ENTRY[entry_mode]
    if em == 0:
        ff_up, ff_lo = direct_up, direct_lo
    else:
        ff_up = pd.Series(direct_up).groupby(codes).ffill().to_numpy(np.float64)
        ff_lo = pd.Series(direct_lo).groupby(codes).ffill().to_numpy(np.float64)

    is_decision = np.isin(mfo, np.asarray(list(decision_mfos), dtype=np.int64))

    # entry gate (Design-C): allow a fresh open only at kept (date, mfo) signal bars
    if entry_gate is None:
        allow = np.ones(N, dtype=np.bool_)
    else:
        gate_idx = pd.MultiIndex.from_tuples(list(entry_gate))
        allow = row_idx.isin(gate_idx)

    if trend_gate and "ema" in b.columns:
        ema = b["ema"].to_numpy(np.float64)
    else:
        ema = np.full(N, np.nan)

    # pre-allocate outputs (at most one trade per bar)
    o_sess = np.empty(N, np.int64)
    o_side = np.empty(N, np.int64)
    o_emfo = np.empty(N, np.int64)
    o_xmfo = np.empty(N, np.int64)
    o_epx = np.empty(N, np.float64)
    o_xpx = np.empty(N, np.float64)
    o_pts = np.empty(N, np.float64)
    o_reason = np.empty(N, np.int64)
    o_tpf = np.empty(N, np.float64)

    nt = _sim_all(
        offsets, flat_rel, atr_s, last_close_s,
        mfo, opn, close, vwap, ema,
        is_decision.astype(np.bool_), allow.astype(np.bool_),
        direct_up, direct_lo, ff_up, ff_lo,
        _FILL[fill_mode], _EXIT[exit_check], em, _STOPREF[stop_ref],
        1 if require_vwap else 0, 1 if trend_gate else 0,
        float(entry_buf_atr), int(entry_persist), int(entry_delay),
        float(stop_buf_atr), float(tp_atr), float(tp_frac), float(be_atr),
        float(trail_step_atr), float(trail_start_atr),
        o_sess, o_side, o_emfo, o_xmfo, o_epx, o_xpx, o_pts, o_reason, o_tpf)

    if nt == 0:
        return pd.DataFrame()

    return pd.DataFrame({
        "date": uniq_dates[o_sess[:nt]],
        "side": o_side[:nt],
        "entry_mfo": o_emfo[:nt],
        "exit_mfo": o_xmfo[:nt],
        "entry_px": o_epx[:nt],
        "exit_px": o_xpx[:nt],
        "points": o_pts[:nt],
        "reason": _REASON[o_reason[:nt]],
        "tp_frac": o_tpf[:nt],
    })
