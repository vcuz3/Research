"""The z / RSI mean-reversion system transplanted to a FIVE-MINUTE bar clock.

Frozen spec: RSI_FIVE_MINUTE_CLOCK_SPEC.md.

Everything this project knows about the surviving system is a one-minute result,
and two of its recorded weaknesses are one-minute-scale (the first-traded-minute
concentration in RSI_CLOCK_CONFOUND_REPORT.md, and the entry-delay decay in
RSI_COHERENCE_TIMEEXIT_REPORT.md). A five-minute decision bar cannot trade
sub-five-minute microstructure at all, so this run measures how much of the edge
is a sub-five-minute effect.

Design notes that matter:

  * Signals, features and exits live on the 5-minute clock; the STOP is resolved
    on the underlying ONE-MINUTE path. A 5m bar hides a minute that opens beyond
    the stop level, and crediting the exact level there would be a rule-5
    violation in the optimistic direction.
  * Strategy parameters are preserved in BAR units (EMA20, z sd 120, RSI 14,
    ATR 14/50), so this is a transplant, not a re-tune.
  * The risk unit is trailing realised volatility over ONE holding period, the
    same convention the 1-minute study used, which is what makes mean R
    comparable across clocks. The regime GATE keeps the canonical 30-minute RV
    percentile (6 bars) at every horizon so the conditioning variable is the one
    this project already validated.
  * A 5-minute grid has five possible offsets, and this project has already been
    burned by a clock phase once. All five are run as a placebo.

Reproduce with:
    python -u _run_rsi_five_minute_clock.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    COSTS,
    load_minutes,
    metrics,
    simulate,
    slot_pct,
    slot_z,
)
from _run_rsi_broad_regime_sweep import (
    ERA_SPLIT,
    HOLDOUT,
    PAIRS,
    ROOT,
    SESSIONS_PER_YEAR,
    START,
    recursive_wilder,
    wilder_rsi,
)

OUT = ROOT / "rsi_five_minute_clock_results.json"
CSV = ROOT / "rsi_five_minute_clock.csv"

BAR = 5                       # minutes per decision bar
STOP_K = 2.0
SLIPPAGE = 1.0
Z_WINDOW = 120                # bars
EMA_SPAN = 20                 # bars
GATE_RV_BARS = 6              # canonical 30-minute RV, in 5m bars
HORIZONS = [6, 12, 30]        # bars -> 30, 60, 150 minutes
PRIMARY_H = 30
Z_GRID = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
RSI_GRID = [35, 30, 25, 20, 15]
BASE_K = 1.5
GATE_KEEP = 0.40
PHASES = [0, 1, 2, 3, 4]
PLACEBO_ARMS = ["z 1.5", "z1.5 + ATR40 + rv40"]
# The off-phase runs carry the |z| FRONTIER as well as the gates, so the primary
# metric (excess over the frontier) can be recomputed inside every phase. A phase
# shift that moves the arm and its own frontier together cancels there; without
# the frontier at each phase that cancellation would be an assumption.
PLACEBO_FAMILIES = ["frontier |z|", "B regime"]
PLACEBO_HORIZONS = [6, 30]


# --------------------------------------------------------------------------- #
# bar construction
# --------------------------------------------------------------------------- #
def build_bars(pair, phase):
    """5-minute bars plus the 1-minute arrays the stop is resolved on.

    A bar is valid only when all five constituent minutes are present. An
    invalid bar breaks recursion and breaks contiguity, exactly as a missing
    minute does on the 1-minute clock.
    """
    raw = load_minutes(pair)
    n1 = len(raw)
    t1 = raw.time
    one1 = t1.diff().eq(pd.Timedelta(minutes=1)).to_numpy()
    brk1 = np.r_[0, np.cumsum(~one1[1:])]
    arrays1 = {c: raw[c].astype(float).to_numpy() for c in ("open", "high", "low", "close")}

    # unit-safe: the archives are microsecond-resolution, so never divide raw int64
    epoch_min = ((t1 - pd.Timestamp("1970-01-01", tz="UTC"))
                 // pd.Timedelta(minutes=1)).to_numpy()
    bar_id = (epoch_min - phase) // BAR

    g = pd.DataFrame({
        "bar_id": bar_id,
        "idx": np.arange(n1),
        "time": t1.to_numpy(),
        "open": arrays1["open"], "high": arrays1["high"],
        "low": arrays1["low"], "close": arrays1["close"],
    }).groupby("bar_id", sort=True)

    f = pd.DataFrame({
        "bar_id": g.bar_id.first().to_numpy(),
        "time": g.time.first().to_numpy(),
        "m_first": g.idx.first().to_numpy(),
        "m_last": g.idx.last().to_numpy(),
        "open": g.open.first().to_numpy(),
        "high": g.high.max().to_numpy(),
        "low": g.low.min().to_numpy(),
        "close": g.close.last().to_numpy(),
        "n_min": g.idx.count().to_numpy(),
    })
    f["time"] = pd.to_datetime(f.time, utc=True)
    f["valid"] = f.n_min.eq(BAR)

    # bar-to-bar contiguity: consecutive ids AND both bars complete
    prev_ok = np.r_[False, (f.bar_id.to_numpy()[1:] - f.bar_id.to_numpy()[:-1]) == 1]
    f["one"] = prev_ok & f.valid.to_numpy() & np.r_[False, f.valid.to_numpy()[:-1]]
    return f, arrays1, brk1, n1


def bar_roll(series, brk, window, how, max_breaks=0):
    """Rolling statistic over `window` bars; `max_breaks=None` drops the gate.

    Rule 9a, and this bit twice. On the 1-minute clock the `z` scale needed 120
    contiguous MINUTES, which costs two hours a session. Preserving 120 BARS
    makes that 600 minutes, and the daily 17:00 New York rollover gap never fits
    inside it: the strict rule returns coverage 0.000 for the first TEN hours of
    every session, i.e. it silently deletes the whole Asia session.

    Allowing ONE break repairs that at grid phase 0 only. Off-phase the bar
    straddling the rollover is incomplete and therefore invalid, which creates
    TWO breaks, so the Asia session is deleted again -- and the phase placebo
    then compares grid offsets against a 10-hour-a-day coverage hole rather than
    against each other. The scale estimator therefore takes no break gate at all:
    displacement from the EMA is defined at every bar, a trailing dispersion
    estimate across a weekend is still a valid causal dispersion estimate, and
    every phase is treated identically. The strict-rule coverage is still
    reported so the size of the deletion stays on the record.
    """
    r = getattr(series.rolling(window, min_periods=window), how)()
    if max_breaks is None:
        return r
    ok = np.zeros(len(series), bool)
    ok[window:] = (brk[window:] - brk[:-window]) <= max_breaks
    return r.where(ok)


def bar_rv(sq, window, min_frac=2 / 3):
    """Realised vol over `window` bars with a fractional coverage floor.

    Squared returns are undefined across a break, so a strict `min_periods`
    deletes every post-rollover window -- the same hidden time-of-day filter.
    Sum what is present and rescale to the full window.
    """
    min_obs = int(np.ceil(window * min_frac))
    roll = sq.rolling(window, min_periods=min_obs)
    return np.sqrt(roll.sum() * window / roll.count())


def build_features(pair, phase):
    f, arrays1, brk1, n1 = build_bars(pair, phase)
    brk = np.r_[0, np.cumsum(~f.one.to_numpy()[1:])]
    one_arr = f.one.to_numpy()

    close = f.close.astype(float)
    logc = pd.Series(np.log(close.to_numpy()), index=f.index)
    ret1 = logc.diff().where(pd.Series(one_arr, index=f.index))

    ny = f.time.dt.tz_convert("America/New_York")
    ny_min = ny.dt.hour * 60 + ny.dt.minute
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    f["sdate"] = ny_date + pd.to_timedelta((ny_min >= 17 * 60).astype(int), unit="D")
    f["session_minute"] = ((ny_min - 17 * 60) % 1440).astype("int16")

    ema = logc.ewm(span=EMA_SPAN, adjust=False).mean()
    disp = logc - ema
    f["z"] = disp / bar_roll(disp, brk, Z_WINDOW, "std",
                             max_breaks=None).replace(0, np.nan)
    f["z_strict"] = disp / bar_roll(disp, brk, Z_WINDOW, "std").replace(0, np.nan)
    f["rsi_14"] = wilder_rsi(close.to_numpy(), one_arr, 14)

    prev_close = np.r_[np.nan, close.to_numpy()[:-1]]
    high, low = f.high.astype(float).to_numpy(), f.low.astype(float).to_numpy()
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    tr[~one_arr] = (high - low)[~one_arr]
    f["vei_atr"] = (pd.Series(recursive_wilder(tr, one_arr, 14), index=f.index)
                    / pd.Series(recursive_wilder(tr, one_arr, 50), index=f.index)
                    .replace(0, np.nan))
    f["vei_atr_z"] = slot_z(f, "vei_atr")

    sq = ret1.pow(2)
    for h in sorted(set(HORIZONS + [GATE_RV_BARS])):
        f[f"rv_{h}"] = bar_rv(sq, h)
    f["rv_gate_pct"] = slot_pct(f, f"rv_{GATE_RV_BARS}")
    f["era"] = np.where(f.time.lt(ERA_SPLIT), "early", "late")
    return f, arrays1, brk1, n1


# --------------------------------------------------------------------------- #
# events
# --------------------------------------------------------------------------- #
def select_events(f, cond, horizon_bars, brk1, n1, delay_bars=1):
    """First crossings on the 5m clock, non-overlap enforced (rule 13).

    A crossing is a bar where `cond` holds and did not hold at the immediately
    preceding CONTIGUOUS bar, so a condition is never carried across a gap.
    Entry is the next bar's open; the 1-minute path must be unbroken from entry
    through the latest exit any arm needs (including the delay arm).
    """
    one_arr = f.one.to_numpy()
    prev = np.r_[False, cond[:-1]]
    crossing = cond & ~(one_arr & prev)

    m_first = f.m_first.to_numpy()
    nxt = np.r_[np.arange(1, len(f)), len(f) - 1]
    entry_m = np.where(np.arange(len(f)) + 1 < len(f), m_first[nxt], -1)

    ok = (
        crossing
        & f.time.ge(START).to_numpy()
        & f.time.lt(HOLDOUT).to_numpy()
        & f.valid.to_numpy()
        & np.r_[f.one.to_numpy()[1:], False]   # entry bar is complete AND contiguous
        & (entry_m >= 0)
    )
    cand = np.flatnonzero(ok)
    if not len(cand):
        return cand, 0

    width = (horizon_bars + delay_bars) * BAR           # last 1-min offset needed
    e = entry_m[cand]
    path_ok = (e + width < n1) & (brk1[np.clip(e + width, 0, n1 - 1)] == brk1[e])
    dropped = int((~path_ok).sum())
    cand = cand[path_ok]

    keep = np.empty(len(cand), bool)
    last = -(10 ** 9)
    for j, i in enumerate(cand):
        keep[j] = i - last >= horizon_bars
        if keep[j]:
            last = i
    return cand[keep], dropped


def extract_paths(f, arrays1, idx, horizon_bars, delay_bars=1):
    m_first = f.m_first.to_numpy()
    e = m_first[idx + 1]
    width = (horizon_bars + delay_bars) * BAR
    take = e[:, None] + np.arange(width + 1)[None, :]
    return {k: v[take] for k, v in arrays1.items()}


# --------------------------------------------------------------------------- #
# arms
# --------------------------------------------------------------------------- #
def early_cut(f, col, keep):
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(1 - keep)) if len(s) else np.nan


def rules(f, full=True):
    z, rsi = f.z, f.rsi_14
    cuts = {
        "vei": early_cut(f, "vei_atr_z", GATE_KEEP),
        "rv40": early_cut(f, "rv_gate_pct", GATE_KEEP),
        "rv20": early_cut(f, "rv_gate_pct", 0.20),
    }
    g_vei = f.vei_atr_z.ge(cuts["vei"])
    g_rv40 = f.rv_gate_pct.ge(cuts["rv40"])
    g_rv20 = f.rv_gate_pct.ge(cuts["rv20"])

    out = []

    def add(label, family, long_s, short_s, extra=None):
        lc = long_s if extra is None else (long_s & extra)
        sc = short_s if extra is None else (short_s & extra)
        cond = (lc | sc).fillna(False).to_numpy()
        side = np.where(lc.fillna(False), 1.0, np.where(sc.fillna(False), -1.0, 0.0))
        out.append((label, family, cond, side))

    for k in Z_GRID:
        add(f"z {k}", "frontier |z|", z.le(-k), z.ge(k))
    b_l, b_s = z.le(-BASE_K), z.ge(BASE_K)
    add("z1.5 + ATR expansion 40", "B regime", b_l, b_s, g_vei)
    add("z1.5 + rv pct 40", "B regime", b_l, b_s, g_rv40)
    add("z1.5 + rv pct 20", "B regime", b_l, b_s, g_rv20)
    add("z1.5 + ATR40 + rv40", "B regime", b_l, b_s, g_vei & g_rv40)
    if full:
        for t in RSI_GRID:
            add(f"rsi {t}/{100 - t}", "A trigger", rsi.le(t), rsi.ge(100 - t))
        add("z 1.5 AND rsi 30/70", "A trigger",
            b_l & rsi.le(30), b_s & rsi.ge(70))
    return out, cuts


def run_arms(f, arrays1, brk1, n1, pair, phase, horizons, full=True):
    arms, cuts = rules(f, full=full)
    rows, drops = [], []
    for horizon in horizons:
        sig_col = f[f"rv_{horizon}"]
        for label, family, cond, side_all in arms:
            if not full and family not in PLACEBO_FAMILIES:
                continue
            idx, dropped = select_events(f, cond, horizon, brk1, n1)
            if len(idx) < 300:
                continue
            drops.append({"pair": pair, "phase": phase, "horizon_bars": horizon,
                          "arm": label, "events": int(len(idx)),
                          "dropped_incomplete_path": dropped})
            d = f.iloc[idx].reset_index(drop=True)
            paths = extract_paths(f, arrays1, idx, horizon)
            side = side_all[idx]
            years = d.sdate.nunique() / SESSIONS_PER_YEAR
            entry0 = paths["open"][:, 0]
            sigma = (sig_col.to_numpy()[idx] * 1e4 * entry0)
            good = np.isfinite(sigma) & (sigma > 0)
            for delay in (0, 1):
                off = delay * BAR
                pp = {k: v[:, off: off + horizon * BAR + 1] for k, v in paths.items()}
                pnl, st, _ = simulate(pp, side, STOP_K * sigma, horizon * BAR, SLIPPAGE)
                pnl = np.where(good, pnl, np.nan)
                base = dict(pair=pair, phase=phase, horizon_bars=horizon,
                            arm=label, family=family, delay=delay, era="all")
                rows.append({**base, **metrics(pnl, sigma, d.sdate.values, years, st)})
                if delay == 0:
                    for era in ("early", "late"):
                        m = d.era.eq(era).to_numpy()
                        if m.sum() < 100:
                            continue
                        yrs = d.loc[m].sdate.nunique() / SESSIONS_PER_YEAR
                        rows.append({**base, "era": era,
                                     **metrics(pnl[m], sigma[m], d.sdate.values[m],
                                               yrs, st[m])})
    return rows, cuts, drops


def add_excess(df):
    """Excess mean R over the |z| frontier interpolated to the arm's own rate."""
    df = df.copy()
    df["excess_R"] = np.nan
    df["frontier_R"] = np.nan
    keys = ["pair", "phase", "horizon_bars", "delay", "era"]
    for _, grp in df.groupby(keys, observed=True):
        fr = grp.loc[grp.family.eq("frontier |z|")].sort_values("signals_per_year")
        if len(fr) < 3:
            continue
        x, y = np.log(fr.signals_per_year.values), fr.mean_R.values
        interp = np.interp(np.log(grp.signals_per_year.values), x, y)
        df.loc[grp.index, "frontier_R"] = interp
        df.loc[grp.index, "excess_R"] = grp.mean_R.values - interp
    return df


# --------------------------------------------------------------------------- #
def data_quality(f, pair, phase, n1):
    v = f.valid.to_numpy()
    row = {"pair": pair, "phase": phase, "minutes": int(n1), "bars": int(len(f)),
           "complete_bars": int(v.sum()), "complete_share": float(v.mean())}
    for era in ("early", "late"):
        m = f.era.eq(era).to_numpy()
        row[f"complete_share_{era}"] = float(f.valid.to_numpy()[m].mean())
    fin = f.loc[f.valid]
    for c in ("z", "z_strict", "rsi_14", "vei_atr_z", "rv_gate_pct", f"rv_{PRIMARY_H}"):
        row[f"cov_{c}"] = float(fin[c].notna().mean())
    # per-slot coverage gradient, rule 9a: a coverage that tracks time of day is
    # a hidden clock filter, a uniform one is the pass signal
    for c in ("z", "z_strict", "vei_atr_z"):
        per_slot = fin.groupby("session_minute")[c].apply(lambda s: s.notna().mean())
        row[f"cov_{c}_slot_min"] = float(per_slot.min())
        row[f"cov_{c}_slot_max"] = float(per_slot.max())
    return row


def main():
    rows, cutrows, qrows, droprows = [], [], [], []
    for pair in PAIRS:
        for phase in PHASES:
            full = phase == 0
            print(f"Building {pair} phase {phase} ...", flush=True)
            f, arrays1, brk1, n1 = build_features(pair, phase)
            qrows.append(data_quality(f, pair, phase, n1))
            r, cuts, drops = run_arms(
                f, arrays1, brk1, n1, pair, phase,
                HORIZONS if full else PLACEBO_HORIZONS, full=full)
            rows.extend(r)
            droprows.extend(drops)
            cutrows.append({"pair": pair, "phase": phase,
                            **{f"cut_{k}": v for k, v in cuts.items()}})

    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_pips"]))
    q = pd.DataFrame(qrows)
    main0 = df.loc[df.delay.eq(0) & df.era.eq("all") & df.phase.eq(0)]

    print("\n=== 0. Rule-9a data quality (phase 0) ===")
    print(q.loc[q.phase.eq(0)].drop(columns=["phase"]).round(4).to_string(index=False))
    dd = pd.DataFrame(droprows)
    print("\n   events dropped for an incomplete 1-minute holding path, "
          f"median across arms: {dd.dropped_incomplete_path.median():.0f} "
          f"of {dd.events.median():.0f} kept (max {dd.dropped_incomplete_path.max()})")

    print("\n=== 0b. Early-era-fitted gate cutpoints (phase 0) ===")
    c = pd.DataFrame(cutrows)
    print(c.loc[c.phase.eq(0)].drop(columns=["phase"]).round(4).to_string(index=False))

    for h in HORIZONS:
        s = main0.loc[main0.horizon_bars.eq(h) & main0.family.eq("frontier |z|")]
        print(f"\n=== 1. |z| frontier, horizon {h} bars = {h * BAR} min "
              "(median across pairs) ===")
        print(s.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
            cluster_t=("cluster_t", "median"), hit=("hit_rate", "median"),
            stopped=("stopped_frac", "median"),
        ).reindex([f"z {k}" for k in Z_GRID]).round(3).to_string())

    print("\n=== 2. Trigger redundancy on the 5m clock "
          f"(horizon {PRIMARY_H} bars, median across pairs) ===")
    s = main0.loc[main0.horizon_bars.eq(PRIMARY_H) & main0.family.eq("A trigger")]
    print(s.groupby("arm").agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), frontier_R=("frontier_R", "median"),
        excess_R=("excess_R", "median"), cluster_t=("cluster_t", "median"),
    ).round(4).to_string())

    print("\n=== 3. Regime gates by horizon (median across pairs) ===")
    s = main0.loc[main0.family.eq("B regime")]
    print(s.groupby(["arm", "horizon_bars"]).agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), frontier_R=("frontier_R", "median"),
        excess_R=("excess_R", "median"), risk_unit=("implied_risk_unit_pips", "median"),
        cluster_t=("cluster_t", "median"), hit=("hit_rate", "median"),
    ).round(4).to_string())

    verdict = {}
    for horizon in (PRIMARY_H, 6):
        tag = "PRIMARY" if horizon == PRIMARY_H else "TIME-MATCHED to the 1-minute study"
        print(f"\n=== 4. KILL TEST at horizon {horizon} bars = {horizon * BAR} min "
              f"({tag}), phase 0 ===")
        print("   SUPPORTED >= +0.005 R median AND >=3/4 pairs; dial if within +/-0.005")
        sel = main0.loc[main0.horizon_bars.eq(horizon) & ~main0.family.eq("frontier |z|")]
        for arm, grp in sel.groupby("arm"):
            w = grp.set_index("pair").excess_R
            med, npos = float(w.median()), int((w >= 0.005).sum())
            d1 = df.loc[df.arm.eq(arm) & df.delay.eq(1) & df.era.eq("all")
                        & df.phase.eq(0) & df.horizon_bars.eq(horizon)]
            late = df.loc[df.arm.eq(arm) & df.delay.eq(0) & df.era.eq("late")
                          & df.phase.eq(0) & df.horizon_bars.eq(horizon)]
            med_d1 = float(d1.excess_R.median()) if len(d1) else np.nan
            med_late = float(late.excess_R.median()) if len(late) else np.nan
            # phase-robust: median excess across ALL FIVE grid offsets, each arm
            # scored against the frontier measured at its own phase
            allp = df.loc[df.arm.eq(arm) & df.delay.eq(0) & df.era.eq("all")
                          & df.horizon_bars.eq(horizon)]
            byphase = allp.groupby("phase").excess_R.median()
            med_ph = float(byphase.median()) if len(byphase) else np.nan
            if med >= 0.005 and npos >= 3:
                status = "SUPPORTED"
                if not (med_d1 > 0 and med_late > 0):
                    status = "supported-but-fragile"
            elif med <= -0.005:
                status = "REJECTED (worse than frontier)"
            else:
                status = "REJECTED (selectivity dial)"
            if status.startswith("SUPPORT") and not (med_ph >= 0.005):
                status += " / phase-0 only"
            verdict[f"H{horizon} {arm}"] = {
                "horizon_bars": horizon, "median_excess_R": med,
                "pairs_ge_0.005": npos, "median_excess_delay1": med_d1,
                "median_excess_late": med_late,
                "median_excess_all_phases": med_ph,
                "excess_by_phase": {int(k): float(v) for k, v in byphase.items()},
                "status": status,
                "per_pair": {k: float(v) for k, v in w.items()}}
            print(f"   {arm:26s} excess {med:+.4f} R  {npos}/4  | delay1 {med_d1:+.4f} "
                  f"| late {med_late:+.4f} | all-phase {med_ph:+.4f}  -> {status}")

    print("\n=== 5. CLOCK COMPARISON: 5m base and gate against the published 1m result ===")
    print("   1-minute reference (RSI_Z_REGIME_MATRIX_REPORT.md, 30-min horizon):")
    print("     z>=1.5 base            0.0230 R   ~1,700 signals/yr")
    print("     z1.5 + ATR40 + rv30_40 0.0451 R   ~2,803 signals/yr, excess +0.0137")
    ref = main0.loc[main0.arm.isin(["z 1.5", "z1.5 + ATR40 + rv40"])]
    print(ref.groupby(["arm", "horizon_bars"]).agg(
        per_year=("signals_per_year", "median"), mean_R=("mean_R", "median"),
        mean_pips=("mean_pips", "median"), excess_R=("excess_R", "median"),
        risk_unit=("implied_risk_unit_pips", "median"),
        cluster_t=("cluster_t", "median"),
    ).round(4).to_string())

    print("\n=== 6. Delay retention (one full 5-minute bar, median across pairs) ===")
    ret = df.loc[df.era.eq("all") & df.phase.eq(0)
                 & df.arm.isin(["z 1.5", "z1.5 + ATR40 + rv40"])]
    piv = ret.pivot_table(index=["arm", "horizon_bars"], columns="delay",
                          values=["mean_pips", "mean_R"], aggfunc="median")
    piv[("retained_pips", "")] = piv[("mean_pips", 1)] / piv[("mean_pips", 0)]
    piv[("retained_R", "")] = piv[("mean_R", 1)] / piv[("mean_R", 0)]
    print(piv.round(4).to_string())
    print("   1-minute reference: 72% of pips / 71% of R retained at a ONE-MINUTE delay.")

    print("\n=== 7. PHASE PLACEBO: all five 5-minute grid offsets "
          f"(horizon {PRIMARY_H} bars) ===")
    ph = df.loc[df.delay.eq(0) & df.era.eq("all") & df.horizon_bars.eq(PRIMARY_H)
                & df.arm.isin(PLACEBO_ARMS)]
    print("   excess over each phase's OWN frontier (the primary metric):")
    print(df.loc[df.delay.eq(0) & df.era.eq("all") & df.family.eq("B regime")]
          .pivot_table(index=["arm", "horizon_bars"], columns="phase",
                       values="excess_R", aggfunc="median").round(4).to_string())
    tab = ph.pivot_table(index="arm", columns="phase", values="mean_R", aggfunc="median")
    print("   median mean_R across pairs, by grid offset:")
    print(tab.round(4).to_string())
    tab2 = ph.pivot_table(index="arm", columns="phase", values="mean_pips", aggfunc="median")
    print("   median mean_pips across pairs, by grid offset:")
    print(tab2.round(4).to_string())
    placebo = {}
    for arm in tab.index:
        v = tab.loc[arm].astype(float)
        rank0 = int((v > v[0]).sum()) + 1
        placebo[arm] = {"by_phase_R": {int(k): float(x) for k, x in v.items()},
                        "phase0_rank_of_5": rank0,
                        "sd_across_phases": float(v.std(ddof=1))}
        print(f"   {arm:26s} phase 0 ranks {rank0}/5, sd across phases "
              f"{v.std(ddof=1):+.4f} R")

    print("\n=== 8. Era split (phase 0, primary horizon, median across pairs) ===")
    e = df.loc[df.delay.eq(0) & df.era.isin(["early", "late"]) & df.phase.eq(0)
               & df.horizon_bars.eq(PRIMARY_H)
               & df.arm.isin(["z 1.5", "z1.5 + ATR40 + rv40", "z1.5 + rv pct 40",
                              "z1.5 + ATR expansion 40"])]
    print(e.groupby(["arm", "era"]).agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        mean_R=("mean_R", "median"), excess_R=("excess_R", "median"),
        cluster_t=("cluster_t", "median"),
    ).round(4).to_string())

    print("\n=== 9. Cost stress (phase 0, median across pairs) ===")
    cs = main0.loc[main0.arm.isin(["z 1.5", "z1.5 + ATR40 + rv40"])]
    print(cs.groupby(["arm", "horizon_bars"]).agg(
        per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
        **{f"annual_net_{c}": (f"annual_net_{c}_pips", "median") for c in COSTS},
    ).round(1).to_string())

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_FIVE_MINUTE_CLOCK_SPEC.md",
            "pairs": PAIRS, "bar_minutes": BAR, "horizons_bars": HORIZONS,
            "primary_horizon_bars": PRIMARY_H, "stop_R": STOP_K,
            "slippage_pips": SLIPPAGE, "z_grid": Z_GRID, "rsi_grid": RSI_GRID,
            "gate_keep": GATE_KEEP, "phases": PHASES, "costs_pips": COSTS,
            "primary_metric": ("mean R excess over the |z| frontier linearly "
                               "interpolated in log signals/year to the arm's own rate"),
            "stop_resolution": "1-minute path under a 5-minute decision clock",
        },
        "data_quality": json.loads(q.to_json(orient="records")),
        "gate_cutpoints": cutrows,
        "event_drops": droprows,
        "verdicts": verdict,
        "phase_placebo": placebo,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
