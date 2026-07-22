"""
Generalized Noise-Area + VWAP momentum engine (mfo-keyed) for the parameter
studies. Superset of core.engine: it must reproduce core.engine exactly on the
RTH / 30-min / decision-clock config (validated in scripts/studies.py), and adds:

  * arbitrary decision clock via `decision_mfos` (Study 2: 5/15/30/60 min);
  * ETH sessions (the mfo coordinate spans the overnight; the daily flat is forced
    at the last RTH bar, `is_rth` transition, so we never hold past 16:00 ET);
  * event-driven THRESHOLD entry (Study 3): instead of only checking at clock
    ticks, enter as soon as a bar closes beyond the band by `entry_buf` POINTS
    (buf = X * ATR, a volatility-scaled buffer per rule 4/19 — never ticks).

Fills stay HONEST (rule 1/2): decisions are read on a bar's CLOSE, every fill is
the NEXT bar's open. `fill_mode="signal_close"` fills at the signal bar's own close
and exists ONLY to measure the fill artifact — for fast clocks / event entries this
is the make-or-break check (the slow-clock robustness does not transfer for free).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_session(bars: pd.DataFrame, band: pd.DataFrame,
                     decision_mfos, fill_mode="next_open", require_vwap=True,
                     exit_check="decision", entry_mode="clock",
                     entry_buf_atr=0.0, entry_gate=None,
                     stop_ref="both", stop_buf_atr=0.0, trend_gate=False,
                     entry_persist=1, tp_atr=0.0, tp_frac=0.5, be_atr=0.0,
                     entry_delay=0, trail_step_atr=0.0, trail_start_atr=0.0,
                     ladder=False, ladder_levels=(-1.0, 2.0, 0.0, 5.0),
                     ladder_frac=0.5, exit_band=None, exit_y=0.0,
                     flat_before_close=0, cond_regime=None,
                     hivol_cadence=15, lovol_cadence=1,
                     init_stop_atr=0.0, tp_gate=None,
                     stop_gate=None) -> list[dict]:
    """
    Simulate one session.

    bars: one trade-date, columns mfo, tod, is_rth, open, high, low, close, vwap, atr.
    band: same trade-date, columns mfo, upper, lower (defined where lookback exists).
    entry_mode:
        "clock"     -- entries evaluated only at decision mfos (baseline / Study 2).
        "threshold" -- entries evaluated at EVERY bar; trigger when close is beyond
                       the (interpolated-to-every-bar) band by entry_buf_atr*ATR
                       points AND (if require_vwap) on the correct side of VWAP.
    exit_check: "decision" (only at clock) or "every_bar".
    """
    b = bars.sort_values("mfo").reset_index(drop=True)
    mfo = b["mfo"].to_numpy()
    opn = b["open"].to_numpy()
    close = b["close"].to_numpy()
    vwap = b["vwap"].to_numpy()
    is_rth = b["is_rth"].to_numpy()
    # Higher-timeframe trend filter (rule 18, side-aware entry gate): only take longs
    # when the signal-bar close is ABOVE its causal as-of EMA, shorts when BELOW.
    # The `ema` column is a strictly-prior 200-period ETH EMA aligned as-of each bar
    # (built in scripts/ema_gate.py). NaN (pre-warmup) -> gate is a no-op for that bar.
    ema = (b["ema"].to_numpy() if (trend_gate and "ema" in b.columns)
           else np.full(len(b), np.nan))
    atr = float(b["atr"].iloc[0]) if np.isfinite(b["atr"].iloc[0]) else np.nan
    n = len(b)
    the_date = b["sdate"].iloc[0]

    # Force the daily flat at the LAST RTH bar (16:00 ET proxy). For RTH that is the
    # last bar; for ETH it is the 15:59-ET bar, so we never carry past the close.
    # flat_before_close>0 (IDEA-0002) moves the flat EARLIER by that many minutes:
    # the loop breaks at flat_i, so it also stops taking new entries after the cutoff
    # (paper's exit_trades_before_close). 0 -> last RTH bar (baseline, unchanged).
    rth_idx = np.where(is_rth)[0]
    last_rth = int(rth_idx[-1]) if len(rth_idx) else n - 1
    if flat_before_close > 0 and len(rth_idx):
        target_mfo = int(mfo[last_rth]) - int(flat_before_close)
        elig = rth_idx[mfo[rth_idx] <= target_mfo]
        flat_i = int(elig[-1]) if len(elig) else int(rth_idx[0])
    else:
        flat_i = last_rth
    last_close = close[flat_i]

    band_map = {int(r.mfo): (r.upper, r.lower) for r in band.itertuples()}
    decision_set = {int(t) for t in decision_mfos}

    # exit_check stop-check cadence (entries/flips stay on the decision clock).
    # "decision" -> only at decision mfos; "every_bar" -> every 1-min bar; int N ->
    # every N minutes from the open. minute-from-open is (mfo+1) with the open bar
    # counted as minute 1, so an N-min cadence checks mfos where (mfo+1) % N == 0.
    # 5 and 15 divide 30, so decision mfos are always a subset; N=1 == every_bar.
    cadence = int(exit_check) if isinstance(exit_check, (int, np.integer)) else None
    check_mfos = ({int(mm) for mm in mfo if (int(mm) + 1) % cadence == 0}
                  if cadence is not None else None)

    # Separate EXIT boundary (paper 5095349 s.4.3/4.4, "different entry & exit
    # boundaries"): entries keep the multiplier-1.0 `band_map`; the stop instead
    # uses `exit_band_map` (a narrower noise band, scaled by s upstream) combined
    # with a VWAP +/- exit_y*sigma_vw band, where sigma_vw is the per-bar causal
    # volume-weighted std of typical price about VWAP (`sig_vw` column on bars,
    # matching core.vol_bands.vwap_sigma_bands). exit_band=None -> baseline stop.
    exit_band_map = ({int(r.mfo): (r.upper, r.lower) for r in exit_band.itertuples()}
                     if exit_band is not None else None)
    sig_vw = (b["sig_vw"].to_numpy() if (exit_band is not None and "sig_vw" in b.columns)
              else np.zeros(n))

    # Event entries (threshold + delay) need a band value at EVERY bar, not just clock
    # mfos. Carry the most recent clock band forward (a band is a step function of tod).
    if entry_mode in ("threshold", "delay"):
        up_arr = np.full(n, np.nan)
        lo_arr = np.full(n, np.nan)
        cur_up = cur_lo = np.nan
        for i in range(n):
            if int(mfo[i]) in band_map:
                cur_up, cur_lo = band_map[int(mfo[i])]
            up_arr[i], lo_arr[i] = cur_up, cur_lo

    pos = 0
    entry_px = np.nan
    entry_mfo = None
    # Exit-management state (rule 14/15): a partial take-profit banks `taken_frac` of the
    # position at `banked` per-unit points; the runner carries `1-taken_frac`. A latched
    # break-even flag floors the trailing stop at entry once price has run `be_atr` in
    # favour. All default OFF (tp_atr=be_atr=0) -> reproduces the baseline exactly.
    banked = 0.0
    taken_frac = 0.0
    partial_done = False
    be_on = False
    fav_max = 0.0          # peak favourable close-excursion (points); drives the ratchet
    # Two-stage RR ladder (rule 14/15, paper 5095349 s.4.5): 1R = lad_r = the
    # entry-frozen distance from the fill to the band/VWAP stop reference at entry
    # (the strategy's own intrinsic per-trade risk, vol-scaled, NOT ATR/ticks).
    # Levels are (sl0, tp0, sl1, tp1) in R relative to entry; bank ladder_frac at
    # the step-0 TP then move to step-1 (breakeven stop / far TP). The ladder
    # REPLACES the band stop and flip: exits are ladder SL/TP or the daily time
    # flat only. All off by default (ladder=False) -> baseline is untouched.
    lad_r = np.nan
    lad_step = 0
    trades: list[dict] = []

    def fill(i):
        if fill_mode == "signal_close":
            return close[i], mfo[i]
        if i + 1 <= flat_i:
            return opn[i + 1], mfo[i + 1]
        return None, None

    def open_pos(side, px, pmfo):
        nonlocal pos, entry_px, entry_mfo, banked, taken_frac, partial_done, be_on, fav_max
        nonlocal lad_r, lad_step
        pos, entry_px, entry_mfo = side, px, pmfo
        banked, taken_frac, partial_done, be_on = 0.0, 0.0, False, False
        fav_max = 0.0
        lad_r, lad_step = np.nan, 0

    def close_trade(i, reason):
        # Blend the banked partial with the runner's realised exit: a trade's points are
        # taken_frac*partial + (1-taken_frac)*runner. Cost is charged once per trade row
        # downstream and the contract-sides net to one round trip (1 in, 0.5+0.5 out).
        nonlocal pos, entry_px, entry_mfo
        px, pmfo = fill(i)
        if px is None:
            return False
        runner = (px - entry_px) * pos
        pts = banked + (1.0 - taken_frac) * runner
        trades.append(dict(sdate=the_date, side=pos, entry_mfo=entry_mfo, exit_mfo=pmfo,
                           entry_px=entry_px, exit_px=px, points=pts, reason=reason,
                           tp_frac=taken_frac))
        pos, entry_px, entry_mfo = 0, np.nan, None
        return True

    buf = (entry_buf_atr * atr) if (entry_mode == "threshold" and np.isfinite(atr)) else 0.0

    # Persistence/confirmation (threshold mode): require the beyond-band(+buffer)+VWAP
    # condition to hold for `entry_persist` CONSECUTIVE 1-min bars before a fresh entry
    # is allowed (a fake breakout that snaps back inside within N min never qualifies).
    # entry_persist=1 == the single-bar first-close event (reproduces the prior study).
    # Fills stay next-open (rule 1/2): confirmation reads closes, never fills intra-bar.
    if entry_mode in ("threshold", "delay"):
        finite = np.isfinite(up_arr)
        lok = finite & (close > up_arr + buf) & (True if not require_vwap else (close > vwap))
        sok = finite & (close < lo_arr - buf) & (True if not require_vwap else (close < vwap))
    if entry_mode == "threshold":
        run_l = np.zeros(n, dtype=int); run_s = np.zeros(n, dtype=int)
        for i in range(n):
            run_l[i] = run_l[i - 1] + 1 if (i > 0 and lok[i]) else int(lok[i])
            run_s[i] = run_s[i - 1] + 1 if (i > 0 and sok[i]) else int(sok[i])
    # DELAYED re-entry (user's corrected 5m/15m spec): the FIRST 1-min close beyond
    # band+VWAP arms a timer; `entry_delay` bars later we ENTER *iff the condition still
    # holds at that later bar* (endpoint recheck, NOT persistence -- the price may wander
    # inside and back during the wait). While a timer is armed, further signals are
    # ignored until it resolves; then we re-arm on the next fresh signal. `delay_side[i]`
    # is the confirmed want at bar i (fill is next-open, as everywhere -- rule 1/2).
    if entry_mode == "delay":
        delay_side = np.zeros(n, dtype=int)
        pend = 0; target = -1
        for i in range(n):
            if pend != 0 and i == target:
                if (pend == 1 and lok[i]) or (pend == -1 and sok[i]):
                    delay_side[i] = pend
                pend, target = 0, -1
            if pend == 0:
                if lok[i]:
                    pend, target = 1, i + entry_delay
                elif sok[i]:
                    pend, target = -1, i + entry_delay

    def gate_ok(m):
        # Design-C bad-trade filter (rule 18): if a gate is supplied, a position may
        # only be OPENED at signal bars the filter kept. None -> allow all (identity).
        return entry_gate is None or (the_date, int(m)) in entry_gate

    for i in range(n):
        if i >= flat_i:
            break
        m = int(mfo[i])
        is_decision = m in decision_set
        c = close[i]
        w = vwap[i]

        # Clock mode mirrors core.engine: a bar whose minute has no band (its
        # same-time-of-day sigma was dropped for lack of history) is skipped
        # entirely -- no entry, no stop, no flip. (Threshold mode carries the
        # band forward every bar, so this guard does not apply there.)
        if entry_mode == "clock" and m not in band_map:
            continue

        # ---- desired entry direction ----
        want = 0
        if entry_mode == "clock":
            if is_decision and m in band_map:
                up, lo = band_map[m]
                if c > up and (not require_vwap or c > w):
                    want = 1
                elif c < lo and (not require_vwap or c < w):
                    want = -1
        elif entry_mode == "delay":  # enter only at the armed timer's resolution bar
            want = int(delay_side[i])
        else:  # threshold: evaluate every bar; require `entry_persist`-bar confirmation
            if run_l[i] >= entry_persist:
                want = 1
            elif run_s[i] >= entry_persist:
                want = -1

        # ---- higher-timeframe trend gate (side-aware): veto counter-trend wants ---
        # Applied to `want` BEFORE the flip/entry logic, so it gates fresh entries AND
        # flips consistently, while leaving stops on existing positions untouched.
        if trend_gate and want != 0 and np.isfinite(ema[i]):
            if (want == 1 and not (c > ema[i])) or (want == -1 and not (c < ema[i])):
                want = 0

        # ---- RR ladder exit (replaces the band stop AND the flip when on) ----
        if pos != 0 and ladder:
            if np.isfinite(lad_r) and lad_r > 0:
                sl_mult = ladder_levels[0] if lad_step == 0 else ladder_levels[2]
                tp_mult = ladder_levels[1] if lad_step == 0 else ladder_levels[3]
                sl_abs = entry_px + pos * sl_mult * lad_r
                tp_abs = entry_px + pos * tp_mult * lad_r
                # close-trigger (consistent with the baseline stop discipline) +
                # next-open fill; a single close cannot be both beyond SL and TP, so
                # ambiguous same-bar resolution never arises (rule 3 satisfied).
                sl_hit = (c <= sl_abs) if pos == 1 else (c >= sl_abs)
                tp_hit = (c >= tp_abs) if pos == 1 else (c <= tp_abs)
                if sl_hit:
                    close_trade(i, "ladder_sl")
                    continue
                if tp_hit:
                    if lad_step == 0:
                        px_p, _ = fill(i)
                        if px_p is not None:
                            banked = ladder_frac * (px_p - entry_px) * pos
                            taken_frac = ladder_frac
                            lad_step = 1
                    else:
                        close_trade(i, "ladder_tp")
                        continue
            # fall through to fresh-entry guard (which requires pos==0, so a held
            # ladder position simply continues to the next bar / daily time flat).

        # ---- exits / flips (stop is the SAME as baseline: band-or-VWAP) ----
        if pos != 0 and not ladder:
            # band at this bar for the stop: clock uses band_map at decision mfos;
            # threshold carries it forward every bar. With a separate exit boundary,
            # the STOP reads the (narrower) exit_band_map instead, and the VWAP leg
            # is shifted by exit_y*sigma_vw (sign mirrored by side).
            if exit_band_map is not None:
                up_i, lo_i = exit_band_map.get(m, (np.nan, np.nan))
                wv = w - pos * exit_y * sig_vw[i]
            elif entry_mode == "threshold":
                up_i, lo_i = up_arr[i], lo_arr[i]
                wv = w
            else:
                up_i, lo_i = band_map.get(m, (np.nan, np.nan))
                wv = w
            have_band = np.isfinite(up_i)
            # Design B: choose the stop reference and a volatility-scaled buffer.
            #   stop_ref "both" -> max(band,vwap) long / min(band,vwap) short (baseline),
            #            "vwap" -> VWAP only, "band" -> band edge only.
            #   stop_buf_atr>0 LOOSENS the stop by that many ATRs (more room), <0 tightens.
            # Defaults ("both", 0.0) reproduce the baseline exactly (rule 23).
            if have_band:
                if stop_ref == "vwap":
                    base = wv
                elif stop_ref == "band":
                    base = up_i if pos == 1 else lo_i
                else:
                    base = (max(up_i, wv) if pos == 1 else min(lo_i, wv))
            else:
                base = wv
            sbuf = (stop_buf_atr * atr) if np.isfinite(atr) else 0.0
            stop = (base - sbuf) if pos == 1 else (base + sbuf)
            # favourable excursion so far (close-based, consistent with the decision
            # discipline); drives the break-even latch and the partial take-profit.
            fav = (c - entry_px) * pos
            if be_atr > 0 and np.isfinite(atr):
                if be_on or fav >= be_atr * atr:
                    be_on = True
                    stop = max(stop, entry_px) if pos == 1 else min(stop, entry_px)
            # ---- ratchet trailing stop (rule 14/15): R = trail_step_atr*ATR. Once the
            #      PEAK favourable close has run trail_start_atr*ATR, tighten the stop to
            #      sit one step (1R) behind the highest whole-R milestone reached, and
            #      ratchet it up (long) / down (short) as further milestones print. Peak
            #      is close-based and the exit still fills next-open, so no intrabar
            #      optimism (rule 1/2/3); the ratchet only ever TIGHTENS. Off at 0.
            if trail_step_atr > 0 and np.isfinite(atr) and atr > 0:
                if fav > fav_max:
                    fav_max = fav
                start = trail_start_atr if trail_start_atr > 0 else trail_step_atr
                step = trail_step_atr * atr
                k = int(np.floor(fav_max / step))
                if fav_max >= start * atr and k >= 1:
                    ratchet = entry_px + pos * (k - 1) * step
                    stop = max(stop, ratchet) if pos == 1 else min(stop, ratchet)
            # ---- fixed INITIAL stop (rule 14, entry-frozen): a hard protective line
            #      init_stop_atr*ATR adverse of the fill, latched at entry. It is a
            #      CAP: the effective stop is the TIGHTER of the band/VWAP trail and
            #      this line, so a wide init line only ever binds on a fast adverse
            #      move the tight band trail has not yet caught (a gap/tail cap). The
            #      committed per-trade risk for constant-% sizing is init_stop_atr*ATR.
            #      0.0 -> off (baseline untouched, parity). Close-trigger + next-open
            #      fill as everywhere (rule 1/2/3).
            istop_binds = False
            if init_stop_atr > 0 and np.isfinite(atr) and atr > 0:
                init_line = entry_px - pos * init_stop_atr * atr
                if pos == 1 and init_line > stop:
                    stop, istop_binds = init_line, True
                elif pos == -1 and init_line < stop:
                    stop, istop_binds = init_line, True
            hit = (c < stop) if pos == 1 else (c > stop)
            if cond_regime is not None:
                # Conditional cadence (prop-account vol lever): switch the stop-check
                # frequency by a CAUSAL intraday vol regime. cond_regime is the set of
                # this session's hi-vol mfos (intraday-to-date range above its same-tod
                # trailing median). High vol -> check only on the hivol_cadence grid
                # (fewer checks -> less whipsaw); low vol -> lovol_cadence (1==every bar).
                cad = hivol_cadence if (m in cond_regime) else lovol_cadence
                check_here = is_decision or ((m + 1) % cad == 0)
            else:
                check_here = (is_decision or exit_check == "every_bar"
                              or (check_mfos is not None and m in check_mfos))
            flip = (want == -pos) and (is_decision if entry_mode == "clock" else True)
            # Optional state-dependent hysteresis gate.  A supplied gate contains
            # (date, mfo, side) keys at which the ordinary band/VWAP stop is armed.
            # Flips and the daily flat are never suppressed.  None is the exact
            # historical behaviour (HYP-0021; default-off parity).
            stop_armed = (stop_gate is None
                          or (the_date, int(m), int(pos)) in stop_gate)
            if (hit and check_here and stop_armed) or flip:
                stop_reason = "istop" if (hit and istop_binds and not flip) else "stop"
                if close_trade(i, "flip" if flip else stop_reason) and flip and gate_ok(m):
                    px, pmfo = fill(i)
                    if px is not None:
                        open_pos(want, px, pmfo)
                continue
            # ---- partial take-profit: bank tp_frac at the next open once price has run
            #      tp_atr in favour (momentum-confirmed close + next-open fill = honest,
            #      conservative vs an intrabar limit; rule 1/2/3). Runner keeps trailing.
            #      tp_gate (HYP-0018, default None -> fire on every trade, parity): the
            #      partial only fires for trades whose entry key (date, entry_mfo) is in
            #      the gate, so the exit horizon can be conditioned per-trade (e.g. on
            #      entry-bar Hurst) without touching entries. entry_mfo is the fill mfo.
            tp_here = tp_gate is None or (the_date, int(entry_mfo)) in tp_gate
            if (tp_atr > 0 and tp_here and not partial_done and np.isfinite(atr)
                    and fav >= tp_atr * atr):
                px, _ = fill(i)
                if px is not None:
                    banked = tp_frac * (px - entry_px) * pos
                    taken_frac = tp_frac
                    partial_done = True

        # ---- fresh entry ----
        if pos == 0 and want != 0:
            can_enter = (is_decision if entry_mode == "clock" else True) and gate_ok(m)
            if can_enter:
                px, pmfo = fill(i)
                if px is not None:
                    open_pos(want, px, pmfo)
                    if ladder:
                        # 1R = distance from the fill to the band/VWAP stop reference
                        # at the entry bar, frozen (rule 14). Same reference the
                        # baseline stop would use, per stop_ref.
                        if entry_mode == "threshold":
                            up_e, lo_e = up_arr[i], lo_arr[i]
                        else:
                            up_e, lo_e = band_map.get(m, (np.nan, np.nan))
                        if stop_ref == "vwap":
                            base_e = w
                        elif stop_ref == "band":
                            base_e = up_e if want == 1 else lo_e
                        else:
                            base_e = (max(up_e, w) if want == 1 else min(lo_e, w))
                        lad_r = abs(px - base_e) if np.isfinite(base_e) else np.nan
                        lad_step = 0

    if pos != 0:
        runner = (last_close - entry_px) * pos
        trades.append(dict(sdate=the_date, side=pos, entry_mfo=entry_mfo,
                           exit_mfo=int(mfo[flat_i]), entry_px=entry_px,
                           exit_px=last_close, points=banked + (1.0 - taken_frac) * runner,
                           reason="eod", tp_frac=taken_frac))
    return trades


def run(bars: pd.DataFrame, bands: pd.DataFrame, decision_mfos,
        fill_mode="next_open", require_vwap=True, exit_check="decision",
        entry_mode="clock", entry_buf_atr=0.0, entry_gate=None,
        stop_ref="both", stop_buf_atr=0.0, trend_gate=False,
        entry_persist=1, tp_atr=0.0, tp_frac=0.5, be_atr=0.0,
        entry_delay=0, trail_step_atr=0.0, trail_start_atr=0.0,
        ladder=False, ladder_levels=(-1.0, 2.0, 0.0, 5.0),
        ladder_frac=0.5, exit_bands=None, exit_y=0.0,
        flat_before_close=0, cond_regime=None,
        hivol_cadence=15, lovol_cadence=1,
        init_stop_atr=0.0, tp_gate=None, stop_gate=None) -> pd.DataFrame:
    band_by = {d: g for d, g in bands.groupby("sdate", sort=False)}
    exit_band_by = ({d: g for d, g in exit_bands.groupby("sdate", sort=False)}
                    if exit_bands is not None else None)
    # cond_regime: long frame (sdate, mfo, hivol). Reduce to date -> set of hi-vol
    # mfos; a missing date/mfo defaults to low-vol (lovol_cadence). None -> off.
    cond_by = None
    if cond_regime is not None:
        cond_by = {d: set(gg.loc[gg["hivol"], "mfo"].astype(int))
                   for d, gg in cond_regime.groupby("sdate", sort=False)}
    out: list[dict] = []
    for d, g in bars.groupby("sdate", sort=False):
        bd = band_by.get(d)
        if bd is None or bd.empty:
            continue
        ex_bd = exit_band_by.get(d) if exit_band_by is not None else None
        cr = cond_by.get(d, set()) if cond_by is not None else None
        out.extend(simulate_session(g, bd, decision_mfos, fill_mode, require_vwap,
                                    exit_check, entry_mode, entry_buf_atr, entry_gate,
                                    stop_ref, stop_buf_atr, trend_gate, entry_persist,
                                    tp_atr, tp_frac, be_atr, entry_delay,
                                    trail_step_atr, trail_start_atr,
                                    ladder, ladder_levels, ladder_frac,
                                    exit_band=ex_bd, exit_y=exit_y,
                                    flat_before_close=flat_before_close,
                                    cond_regime=cr, hivol_cadence=hivol_cadence,
                                    lovol_cadence=lovol_cadence,
                                    init_stop_atr=init_stop_atr, tp_gate=tp_gate,
                                    stop_gate=stop_gate))
    df = pd.DataFrame(out)
    if not df.empty:
        df = df.rename(columns={"sdate": "date"})
    return df
