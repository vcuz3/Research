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
                     stop_gate=None, reentry="later_decision",
                     reset_check="decision", audit_out=None,
                     reset_hazard=None, reset_seed=0,
                     hard_stop_buf_atr=None, hard_stop_trigger="touch",
                     hard_stop_atr_col=None, track_excursion=False,
                     fast_overlay=False, fast_release="opposite", fast_horizon=5,
                     fast_entry=True, fast_exit=True, fast_fixed_delay=5,
                     fast_hazard=None, fast_seed=0, fast_audit=None) -> list[dict]:
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
    reentry (HYP-0031, default-off):
        "later_decision" -- current/baseline behaviour: after a stop-out the same
                       side may be retaken at any later decision bar whose
                       breakout condition still holds.
        "require_reset" -- after a STOP exit on side S, block fresh same-side
                       entries until price has been observed back INSIDE the
                       noise area (lower <= close <= upper). Opposite-side
                       entries and flips are never blocked. State
                       (stopped_side, reset_observed) is per session.
    reset_check: cadence on which a reset is recognised, "decision" (the source
                       spec: only at scheduled checkpoints) or "every_bar".
    """
    b = bars.sort_values("mfo").reset_index(drop=True)
    mfo = b["mfo"].to_numpy()
    opn = b["open"].to_numpy()
    close = b["close"].to_numpy()
    high = b["high"].to_numpy()
    low = b["low"].to_numpy()
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
    hard_line = np.nan     # entry-frozen mandatory stop price (resting order)
    hard_risk = np.nan     # its distance from the fill, in points
    mae = 0.0              # max adverse excursion, points (intraday risk, rule 22)
    mfe = 0.0              # max favourable excursion, points
    # Optional INTRADAY causal volatility scale for the hard stop, read at the entry
    # bar, instead of the session-constant prior-14-session range ATR. Supplied as a
    # bars column so the causal construction stays in one place upstream.
    iatr = (b[hard_stop_atr_col].to_numpy()
            if (hard_stop_atr_col is not None and hard_stop_atr_col in b.columns)
            else None)
    # HYP-0031 same-side re-entry lock. `stopped_side` is the side of the most
    # recent STOP exit (a flip does not arm the lock -- it is an opposite-side
    # entry, which the rule never blocks); `reset_observed` records whether price
    # has since been seen back inside the noise area. Both are session-local, so
    # the first entry of a day is never blocked. Initialised unlocked, which makes
    # "later_decision" and "require_reset" identical until the first stop.
    # "random_reset" is the matched NULL for "require_reset" (HYP-0031 control 1b):
    # it keeps the lock and its PERSISTENCE -- same side-scoping, same cadence, the
    # lock survives across checkpoints -- but clears it on a coin flip at hazard
    # `reset_hazard` per checked bar instead of on "price is back inside the band".
    # It therefore destroys ONLY the information the rule claims to use. This is the
    # control a one-shot entry blocklist cannot express: blocking every candidate key
    # once still removes fewer trades than the persistent lock does.
    require_reset = reentry in ("require_reset", "random_reset")
    random_reset = (reentry == "random_reset")
    if reentry not in ("later_decision", "require_reset", "random_reset"):
        raise ValueError(f"unknown reentry policy {reentry!r}")
    if random_reset and reset_hazard is None:
        raise ValueError("reentry='random_reset' requires reset_hazard")
    # Per-session RNG so draws are reproducible and independent across sessions.
    rrng = (np.random.default_rng([int(reset_seed),
                                   int(pd.Timestamp(b["sdate"].iloc[0]).value % (2 ** 31))])
            if random_reset else None)
    stopped_side = 0
    reset_observed = True
    blocked: list[dict] = []   # audit trail of entries the lock suppressed
    trades: list[dict] = []

    # ---- HYP-0034 fast-alpha execution overlay (default OFF -> bit-exact) -------
    # A fast-decaying reversal alpha used only to TIME the base strategy's entries
    # and stop-exits (never traded directly). The alpha at bar i is the sign of the
    # trailing `fast_horizon`-minute return close[i]-close[i-h], known at the close
    # of bar i; every fill stays next-open (rule 1/2). Entries are held pending
    # after a breakout and released on a micro-pullback; stop-exits are held pending
    # after the stop triggers and released on a favourable bounce. `fast_release`
    # swaps ONLY the release trigger so the controls share the identical wait
    # machinery: "opposite"=the paper, "same"=inverted, "fixed"=blind N-bar wait,
    # "random"=coin flip (the decisive matched-exposure null, EXP-0043 control 1b).
    h = int(fast_horizon)
    ret_h = np.full(n, np.nan)
    if fast_overlay and 0 < h < n:
        ret_h[h:] = close[h:] - close[:-h]
    if fast_release not in ("opposite", "same", "fixed", "random"):
        raise ValueError(f"unknown fast_release {fast_release!r}")
    if fast_overlay and fast_release == "random" and fast_hazard is None:
        raise ValueError("fast_release='random' requires fast_hazard")
    frng = (np.random.default_rng([int(fast_seed),
                                   int(pd.Timestamp(b["sdate"].iloc[0]).value % (2 ** 31))])
            if (fast_overlay and fast_release == "random") else None)
    pend_entry = 0            # armed pending-entry side (0 = none)
    pend_entry_arm = -1       # bar index the pending entry was armed
    pend_entry_arm_mfo = -1
    pend_entry_ref_m = None
    pend_exit = False         # a stop has triggered; liquidation is pending
    pend_exit_arm = -1
    pend_exit_arm_mfo = -1
    pend_exit_reason = "stop"

    def _sgn(x):
        return int(x > 0) - int(x < 0)

    def _release_entry(i):
        """Release a pending entry of side `pend_entry` at bar i (fill next-open)."""
        if fast_release == "fixed":
            return (i - pend_entry_arm) >= int(fast_fixed_delay)
        if fast_release == "random":
            return frng.random() < fast_hazard
        r = ret_h[i]
        if not np.isfinite(r):
            return False
        s = _sgn(r)
        # opposite: a pullback OPPOSITE the entry side; same (inverted): with it.
        return s == (-pend_entry if fast_release == "opposite" else pend_entry)

    def _release_exit(i, side):
        """Release a pending stop-exit of a `side` position at bar i (next-open)."""
        if fast_release == "fixed":
            return (i - pend_exit_arm) >= int(fast_fixed_delay)
        if fast_release == "random":
            return frng.random() < fast_hazard
        r = ret_h[i]
        if not np.isfinite(r):
            return False
        s = _sgn(r)
        # opposite: a FAVOURABLE bounce for the position; same (inverted): adverse.
        return s == (side if fast_release == "opposite" else -side)

    def fill(i):
        if fill_mode == "signal_close":
            return close[i], mfo[i]
        if i + 1 <= flat_i:
            return opn[i + 1], mfo[i + 1]
        return None, None

    def stop_ref_at(m_, i_, side):
        """The strategy's OWN stop reference at a bar: max(band,VWAP) long /
        min(band,VWAP) short, per stop_ref. This is the level the soft trail would
        exit at, and the anchor the mandatory hard stop is frozen to."""
        if entry_mode == "threshold":
            up_e, lo_e = up_arr[i_], lo_arr[i_]
        else:
            up_e, lo_e = band_map.get(m_, (np.nan, np.nan))
        w_e = vwap[i_]
        if stop_ref == "vwap":
            return w_e
        if stop_ref == "band":
            return up_e if side == 1 else lo_e
        return (max(up_e, w_e) if side == 1 else min(lo_e, w_e))

    def open_pos(side, px, pmfo, ref_m=None, ref_i=None):
        nonlocal pos, entry_px, entry_mfo, banked, taken_frac, partial_done, be_on, fav_max
        nonlocal lad_r, lad_step, hard_line, hard_risk, mae, mfe
        pos, entry_px, entry_mfo = side, px, pmfo
        banked, taken_frac, partial_done, be_on = 0.0, 0.0, False, False
        fav_max = 0.0
        lad_r, lad_step = np.nan, 0
        # ---- mandatory protective stop (prop-firm constraint), entry-frozen (rule 14).
        # Anchored on the strategy's own band/VWAP touch level at entry, widened by a
        # volatility buffer: risk = (entry - stop_ref)+ + buf*ATR. The (.)+ floor matters
        # because ~29% of signals sit within 0.10 ATR of their own reference (and a gap
        # can even fill through it), so a bare b=0 line would be pure noise-stop.
        hard_line, hard_risk = np.nan, np.nan
        mae, mfe = 0.0, 0.0
        if hard_stop_buf_atr is not None:
            base_e = stop_ref_at(ref_m, ref_i, side) if ref_i is not None else np.nan
            atr_u = (iatr[ref_i] if (iatr is not None and ref_i is not None) else atr)
            buf = (hard_stop_buf_atr * atr_u) if np.isfinite(atr_u) else 0.0
            raw = ((px - base_e) if side == 1 else (base_e - px)) if np.isfinite(base_e) else 0.0
            hard_risk = max(float(raw), 0.0) + buf
            if hard_risk > 0:
                hard_line = px - side * hard_risk

    def close_at(i, px, reason):
        """Close at an explicit price inside bar i (used by the resting hard stop,
        which fills at its own level, not at a later bar's open)."""
        nonlocal pos, entry_px, entry_mfo, hard_line, hard_risk
        runner = (px - entry_px) * pos
        trades.append(dict(sdate=the_date, side=pos, entry_mfo=entry_mfo,
                           exit_mfo=int(mfo[i]), entry_px=entry_px, exit_px=px,
                           points=banked + (1.0 - taken_frac) * runner, reason=reason,
                           tp_frac=taken_frac, hard_risk=hard_risk, mae=mae, mfe=mfe))
        pos, entry_px, entry_mfo = 0, np.nan, None
        hard_line, hard_risk = np.nan, np.nan
        return True

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
                           tp_frac=taken_frac, hard_risk=hard_risk, mae=mae, mfe=mfe))
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

    def gate_ok(m, side):
        # Design-C bad-trade filter (rule 18): if a gate is supplied, a position may
        # only be OPENED at signal bars the filter kept.  Existing two-key gates
        # remain valid; a three-key gate can additionally distinguish long/short.
        # None -> allow all (identity).
        return (entry_gate is None
                or (the_date, int(m)) in entry_gate
                or (the_date, int(m), int(side)) in entry_gate)

    for i in range(n):
        if i >= flat_i:
            break
        m = int(mfo[i])
        is_decision = m in decision_set
        c = close[i]
        w = vwap[i]

        # ---- max adverse / favourable excursion (rule 22: risk where it accumulates).
        # Updated before any exit logic so the exit bar's own extreme is included.
        if track_excursion and pos != 0:
            adv = (entry_px - low[i]) if pos == 1 else (high[i] - entry_px)
            fav = (high[i] - entry_px) if pos == 1 else (entry_px - low[i])
            if adv > mae:
                mae = adv
            if fav > mfe:
                mfe = fav

        # ---- mandatory protective stop: a RESTING order, so it is live on EVERY bar
        # (including the fill bar, rule 3) regardless of the soft trail's check cadence,
        # and it is checked FIRST because it would execute intrabar before any
        # close-based decision. Gap-through fills at the first tradable price -- the
        # bar's open -- never at the stop level (rule 5).
        if pos != 0 and np.isfinite(hard_line):
            # A hard stop IS a stop-driven exit, so it must arm the same-side re-entry
            # lock exactly as the soft trail does. Without this the engine re-buys the
            # very breakout the protective stop just closed (it inflated trade count
            # ~48% at b=0), which is the churn `require_reset` exists to prevent.
            if hard_stop_trigger == "touch":
                hit_h = ((opn[i] <= hard_line or low[i] <= hard_line) if pos == 1
                         else (opn[i] >= hard_line or high[i] >= hard_line))
                if hit_h:
                    px_h = (opn[i] if ((opn[i] <= hard_line) if pos == 1
                                       else (opn[i] >= hard_line)) else hard_line)
                    stopped_side, reset_observed = pos, False
                    close_at(i, px_h, "hard_stop")
                    continue
            else:  # close-confirmed variant, for comparability with the soft trail
                if (c < hard_line) if pos == 1 else (c > hard_line):
                    stopped_side, reset_observed = pos, False
                    if close_trade(i, "hard_stop"):
                        continue

        # Clock mode mirrors core.engine: a bar whose minute has no band (its
        # same-time-of-day sigma was dropped for lack of history) is skipped
        # entirely -- no entry, no stop, no flip. (Threshold mode carries the
        # band forward every bar, so this guard does not apply there.)
        if entry_mode == "clock" and m not in band_map:
            continue

        # ---- HYP-0031 step 1: recognise a reset BEFORE the exit/entry logic ----
        # The evaluation order is load-bearing (source spec): observing "price is
        # inside the band" first means a bar that both resets and stops ends up
        # LOCKED, because the stop clears the flag afterwards.
        if m in band_map and (reset_check == "every_bar" or is_decision):
            if random_reset:
                # same lock, same cadence, uninformative trigger
                if not reset_observed and rrng.random() < reset_hazard:
                    reset_observed = True
            else:
                _up, _lo = band_map[m]
                if _lo <= c <= _up:
                    reset_observed = True

        # ---- HYP-0034 fast overlay: resolve a pending stop-EXIT ----------------
        # Once the stop has triggered we are committed to exiting; we only wait for
        # a favourable fast bounce (or the EOD flat). While pending, no other logic
        # runs on this bar. Release strictly after the arming bar.
        if fast_overlay and fast_exit and pos != 0 and pend_exit:
            if i > pend_exit_arm and _release_exit(i, pos):
                if fast_audit is not None:
                    fast_audit.append(dict(kind="exit", side=int(pos),
                                           delay=int(m - pend_exit_arm_mfo),
                                           dropped=False))
                stopped_side, reset_observed = pos, False
                close_trade(i, pend_exit_reason)
                pend_exit = False
            continue

        # ---- HYP-0034 fast overlay: resolve a pending ENTRY --------------------
        # After a breakout is confirmed we wait for a micro-pullback before
        # entering. While pending, fresh breakout signals are ignored until this
        # resolves or is dropped at the daily flat. Release strictly after arming.
        if fast_overlay and fast_entry and pos == 0 and pend_entry != 0:
            if i > pend_entry_arm and _release_entry(i):
                px, pmfo = fill(i)
                if px is not None:
                    if fast_audit is not None:
                        fast_audit.append(dict(kind="entry", side=int(pend_entry),
                                               delay=int(m - pend_entry_arm_mfo),
                                               dropped=False))
                    open_pos(pend_entry, px, pmfo, ref_m=m, ref_i=i)
                    pend_entry = 0
                else:
                    pend_entry = 0
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
                if flip:
                    # A flip is a reversal, not a stop: close now (baseline), then
                    # the NEW-side entry is delayed by the fast overlay (if on), so
                    # entries are timed symmetrically with plain entries.
                    if close_trade(i, "flip") and gate_ok(m, want):
                        if fast_overlay and fast_entry:
                            pend_entry, pend_entry_arm = want, i
                            pend_entry_arm_mfo, pend_entry_ref_m = m, m
                        else:
                            px, pmfo = fill(i)
                            if px is not None:
                                open_pos(want, px, pmfo, ref_m=m, ref_i=i)
                    continue
                # ---- non-flip stop ----
                if fast_overlay and fast_exit:
                    # arm the pending exit; the actual liquidation waits for a fast
                    # bounce (resolved at the top of a later bar). The stop RULE is
                    # unchanged -- only its timing is refined (paper s.4).
                    pend_exit, pend_exit_arm = True, i
                    pend_exit_arm_mfo, pend_exit_reason = m, stop_reason
                    continue
                # ---- HYP-0031 step 2: a STOP exit arms the same-side lock ----
                stopped_side, reset_observed = pos, False
                close_trade(i, stop_reason)
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
            # ---- HYP-0031 step 3: same-side permission ----
            # Audit every post-stop SAME-SIDE re-entry candidate (the pool the
            # matched-count random control must draw from), flagging the ones the
            # lock actually suppresses. Under "later_decision" nothing is blocked,
            # so the same call records the unfiltered pool.
            same_side_post_stop = (stopped_side == want)
            reset_block = require_reset and same_side_post_stop and not reset_observed
            if same_side_post_stop and audit_out is not None:
                audit_out.append(dict(sdate=the_date, mfo=m, side=int(want),
                                      blocked=bool(reset_block)))
            can_enter = ((is_decision if entry_mode == "clock" else True)
                         and gate_ok(m, want) and not reset_block)
            if can_enter and fast_overlay and fast_entry:
                # Delay the entry: arm a pending entry and wait for a fast pullback.
                pend_entry, pend_entry_arm = want, i
                pend_entry_arm_mfo, pend_entry_ref_m = m, m
            elif can_enter:
                px, pmfo = fill(i)
                if px is not None:
                    open_pos(want, px, pmfo, ref_m=m, ref_i=i)
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
        # a pending exit that never got its bounce is force-flattened at EOD.
        reason = pend_exit_reason if (fast_overlay and fast_exit and pend_exit) else "eod"
        if fast_audit is not None and fast_overlay and fast_exit and pend_exit:
            fast_audit.append(dict(kind="exit", side=int(pos),
                                   delay=int(mfo[flat_i] - pend_exit_arm_mfo),
                                   dropped=True))
        trades.append(dict(sdate=the_date, side=pos, entry_mfo=entry_mfo,
                           exit_mfo=int(mfo[flat_i]), entry_px=entry_px,
                           exit_px=last_close, points=banked + (1.0 - taken_frac) * runner,
                           reason=reason, tp_frac=taken_frac, hard_risk=hard_risk, mae=mae, mfe=mfe))
    if fast_audit is not None and fast_overlay and fast_entry and pend_entry != 0:
        # a breakout whose pullback never came: no trade taken that session.
        fast_audit.append(dict(kind="entry", side=int(pend_entry),
                               delay=int(mfo[flat_i] - pend_entry_arm_mfo), dropped=True))
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
        init_stop_atr=0.0, tp_gate=None, stop_gate=None,
        reentry="later_decision", reset_check="decision",
        audit_out=None, reset_hazard=None, reset_seed=0,
        hard_stop_buf_atr=None, hard_stop_trigger="touch",
        hard_stop_atr_col=None, track_excursion=False,
        fast_overlay=False, fast_release="opposite", fast_horizon=5,
        fast_entry=True, fast_exit=True, fast_fixed_delay=5,
        fast_hazard=None, fast_seed=0, fast_audit=None) -> pd.DataFrame:
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
    for si, (d, g) in enumerate(bars.groupby("sdate", sort=False)):
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
                                    stop_gate=stop_gate, reentry=reentry,
                                    reset_check=reset_check, audit_out=audit_out,
                                    reset_hazard=reset_hazard,
                                    reset_seed=reset_seed,
                                    hard_stop_buf_atr=hard_stop_buf_atr,
                                    hard_stop_trigger=hard_stop_trigger,
                                    hard_stop_atr_col=hard_stop_atr_col,
                                    track_excursion=track_excursion,
                                    fast_overlay=fast_overlay,
                                    fast_release=fast_release,
                                    fast_horizon=fast_horizon,
                                    fast_entry=fast_entry, fast_exit=fast_exit,
                                    fast_fixed_delay=fast_fixed_delay,
                                    fast_hazard=fast_hazard,
                                    fast_seed=fast_seed + si, fast_audit=fast_audit))
    df = pd.DataFrame(out)
    if not df.empty:
        df = df.rename(columns={"sdate": "date"})
    return df
