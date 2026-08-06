"""Shared event-clock path engine for the compulsory-stop arms.

Two deployment facts drive the design, both supplied by the user and both
changing the estimand rather than decorating it:

  1. A single-price-barrier stop is COMPULSORY on every trade (prop challenge),
     so the unconstrained fixed-horizon return is not the target. Every P&L here
     is simulated with a stop already in place.
  2. Decisions are NOT taken on a fixed :29/:59 clock. That grid was exploration
     scaffolding, and this project's own `RSI_CLOCK_CONFOUND_REPORT.md` showed it
     is a minute-of-half-hour selector (phase :29 ranks 30/30 of 30 phases). The
     engine therefore fires on the EVENT: the first minute at which the entry
     condition becomes true, with non-overlap enforced so only one position is
     open at a time (rule 13).

Because every signal is a first crossing, every trade is `age == 0` in the sense
of `RSI_THRESHOLD_FRESHNESS_REPORT.md`. That report found age 0 is the best state
but that 85% of its advantage is the first traded minute, so the one-minute-delay
arm is mandatory here, not optional.

Single barrier, so there is no intrabar stop-versus-target ordering to resolve.
The rules that still bite are rule 3 (the entry bar is inside the stop scan) and
rule 5 (a minute that OPENS beyond the stop fills at that open, and a slippage
variant is always reported).

Path indexing, fixed once here so both arms agree:
    signal at bar i, path column m maps to bar i+1+m
    m = 0   -> the entry bar; entry price is open(i+1) = O[:, 0]
    m = N   -> exit price for a time exit after N elapsed minutes = O[:, N]
    m = 30  -> the baseline horizon exit = O[:, 30]
    a position closed at O[:, N] lived through bars m = 0 .. N-1, so that is the
    stop scan range; close(i+N), the last observable close before that exit, is
    C[:, N-1].
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from _run_rsi_broad_regime_sweep import (
    DATA,
    ERA_SPLIT,
    HOLDOUT,
    HORIZON,
    PIP,
    SESSIONS_PER_YEAR,
    START,
    recursive_wilder,
    session_cluster_t,
    wilder_rsi,
)

Z_WINDOW = 120
BASE_K = 1.5          # no volatility scaling: the surviving recommendation
EXPANSION_KEEP = 0.40
SLOT_LOOKBACK = 90
COSTS = [0.2, 0.5, 1.0]


def exact_roll(series, time, window, how):
    rolled = getattr(series.rolling(window, min_periods=window), how)()
    return rolled.where(time.shift(window).eq(time - pd.Timedelta(minutes=window)))


def slot_z(frame, column, lookback=SLOT_LOOKBACK):
    """Causal same-time-of-day z-score, prior sessions only."""
    min_obs = int(np.ceil(lookback * 2 / 3))
    g = frame.groupby("session_minute", sort=False)[column]
    mean = g.transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).mean())
    std = g.transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).std(ddof=1))
    return (frame[column] - mean) / std.replace(0, np.nan)


def slot_pct(frame, column, lookback=SLOT_LOOKBACK):
    """Causal same-time-of-day percentile, prior sessions plus the current value."""
    min_obs = int(np.ceil(lookback * 2 / 3))

    def transform(s):
        r = s.rolling(lookback + 1, min_periods=min_obs + 1)
        return (r.rank(method="average") - 1) / (r.count() - 1)

    return frame.groupby("session_minute", sort=False)[column].transform(transform)


def load_minutes(pair):
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "open", "high", "low", "close"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    return raw.sort_values("time", kind="stable").reset_index(drop=True)


def unitfree_move(pair):
    """`u = trailing 30-minute log return / trailing 30-minute realised vol`.

    Signed and scale-free, so the four USD-quoted pairs are directly comparable.
    Returned indexed by timestamp for the cross-pair join in arm 3.
    """
    raw = load_minutes(pair)
    time = raw.time
    one = time.diff().eq(pd.Timedelta(minutes=1))
    logc = pd.Series(np.log(raw.close.astype(float)), index=raw.index)
    ret1 = logc.diff().where(one)
    r30 = (logc - logc.shift(30)).where(time.shift(30).eq(time - pd.Timedelta(minutes=30)))
    rv30 = np.sqrt(exact_roll(ret1.pow(2), time, 30, "sum"))
    u = (r30 / rv30.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    return pd.Series(u.to_numpy(), index=time.to_numpy(), name=pair)


def build_features(pair):
    """Per-minute causal feature frame plus the raw OHLC arrays for path slicing."""
    raw = load_minutes(pair)
    time = raw.time
    one = time.diff().eq(pd.Timedelta(minutes=1))
    one_arr = one.to_numpy()
    close = raw.close.astype(float)
    logc = pd.Series(np.log(close), index=raw.index)
    ret1 = logc.diff().where(one)

    ny = time.dt.tz_convert("America/New_York")
    ny_min = ny.dt.hour * 60 + ny.dt.minute
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    raw["sdate"] = ny_date + pd.to_timedelta((ny_min >= 17 * 60).astype(int), unit="D")
    raw["session_minute"] = ((ny_min - 17 * 60) % 1440).astype("int16")
    raw["phase30"] = (ny_min % 30).astype("int16")   # placebo axis, reported not used

    ema20 = logc.ewm(span=20, adjust=False).mean()
    disp = logc - ema20
    raw["z"] = disp / exact_roll(disp, time, Z_WINDOW, "std").replace(0, np.nan)
    raw["rv_30m"] = np.sqrt(exact_roll(ret1.pow(2), time, 30, "sum"))
    raw["r30"] = (logc - logc.shift(30)).where(
        time.shift(30).eq(time - pd.Timedelta(minutes=30)))
    raw["u"] = (raw.r30 / raw.rv_30m.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    raw["rsi_14"] = wilder_rsi(close.to_numpy(), one_arr, 14)

    prev_close = np.r_[np.nan, close.to_numpy()[:-1]]
    high, low = raw.high.astype(float).to_numpy(), raw.low.astype(float).to_numpy()
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    tr[~one_arr] = (high - low)[~one_arr]
    raw["vei_atr"] = (pd.Series(recursive_wilder(tr, one_arr, 14), index=raw.index)
                      / pd.Series(recursive_wilder(tr, one_arr, 50), index=raw.index)
                      .replace(0, np.nan))

    raw["vol_pct"] = slot_pct(raw, "rv_30m")
    raw["vei_atr_z"] = slot_z(raw, "vei_atr")
    raw["era"] = np.where(time.lt(ERA_SPLIT), "early", "late")
    raw["one"] = one_arr
    raw["sigma_ok"] = raw.rv_30m.gt(0).fillna(False)
    return raw


def condition(frame, kind, expansion_cut):
    """Entry condition evaluated at EVERY minute, plus the trade side."""
    if kind == "gated":
        long_s, short_s = frame.z.le(-BASE_K), frame.z.ge(BASE_K)
        cond = (long_s | short_s) & frame.vei_atr_z.ge(expansion_cut)
    elif kind == "rsi3070":
        long_s, short_s = frame.rsi_14.le(30), frame.rsi_14.ge(70)
        cond = long_s | short_s
    elif kind == "zonly":                      # degenerate: no expansion gate
        long_s, short_s = frame.z.le(-BASE_K), frame.z.ge(BASE_K)
        cond = long_s | short_s
    else:
        raise ValueError(kind)
    side = np.where(long_s, 1.0, np.where(short_s, -1.0, 0.0))
    return cond.fillna(False).to_numpy(), side


def expansion_cutpoint(frame, keep=EXPANSION_KEEP):
    """Fitted on the EARLY era only and applied unchanged to the late era.

    The audited fixed-clock script took this quantile over the whole sample,
    which is a two-sided statistic; fitting it early removes that.
    """
    early = frame.loc[frame.era.eq("early"), "vei_atr_z"].dropna()
    return float(early.quantile(1 - keep)) if len(early) else np.nan


def select_events(frame, cond, horizon=HORIZON, extra_bars=1, cooldown=None, overlap=False):
    """First-crossing events with non-overlap enforced.

    A crossing is a minute at which `cond` is true and was NOT true at the
    immediately preceding minute; a non-contiguous minute always starts a new
    run, so a condition is never carried across a gap.

    Non-overlap (rule 13): once a trade is entered it holds `horizon` minutes, so
    the next accepted signal must be at least `cooldown` minutes later. Only one
    position is open at any time, which is what a single prop account runs.
    """
    n = len(frame)
    cooldown = horizon if cooldown is None else cooldown
    one_arr = frame.one.to_numpy()
    prev = np.r_[False, cond[:-1]]
    crossing = cond & ~(one_arr & prev)

    need = horizon + 1 + extra_bars
    brk = np.r_[0, np.cumsum(~one_arr[1:])]
    time = frame.time
    ok = (
        crossing
        & time.ge(START).to_numpy()
        & time.lt(HOLDOUT).to_numpy()
        & frame.rv_30m.gt(0).to_numpy()
        & frame.sigma_ok.to_numpy()
    )
    cand = np.flatnonzero(ok)
    cand = cand[cand + need < n]
    cand = cand[brk[cand + need] == brk[cand]]
    if overlap or not len(cand):
        return cand

    keep = np.empty(len(cand), bool)
    last = -(10 ** 9)
    for j, i in enumerate(cand):
        keep[j] = i - last >= cooldown
        if keep[j]:
            last = i
    return cand[keep]


def extract(frame, arrays, idx, horizon=HORIZON, extra_bars=1):
    d = frame.iloc[idx].reset_index(drop=True)
    offs = np.arange(horizon + 1 + extra_bars)[None, :]
    take = (idx[:, None] + 1) + offs
    paths = {k: v[take] for k, v in arrays.items()}
    d["entry_px"] = paths["open"][:, 0]
    d["sigma_pips"] = d.rv_30m * 1e4 * d.entry_px
    return d, paths


def ohlc_arrays(frame):
    return {
        "open": frame.open.astype(float).to_numpy(),
        "high": frame.high.astype(float).to_numpy(),
        "low": frame.low.astype(float).to_numpy(),
        "close": frame.close.astype(float).to_numpy(),
    }


def shift_paths(paths, delay, horizon=HORIZON):
    """The same trades entered `delay` minutes later, holding period unchanged."""
    return {k: v[:, delay: delay + horizon + 1] for k, v in paths.items()}


def simulate(paths, side, stop_dist, exit_idx, slippage_pips=0.0, pip=PIP):
    """P&L in pips for a single-barrier stop plus a fixed exit index.

    `exit_idx` may be a scalar or a per-trade array; the stop is scanned over path
    bars 0 .. exit_idx-1, which are exactly the bars the position lives through.
    `stop_dist` in pips; np.inf disables the stop.

    Returns (pnl_pips, stopped_mask, stop_bar).
    """
    o, hi, lo = paths["open"], paths["high"], paths["low"]
    n, width = o.shape
    exit_idx = np.broadcast_to(np.asarray(exit_idx), (n,)).astype(int)
    s = np.asarray(side, float)
    entry = o[:, 0]

    dist_px = np.broadcast_to(np.asarray(stop_dist, float), (n,)) * pip
    level = entry - s * dist_px                       # long: below, short: above
    worst = np.where(s[:, None] > 0, lo, hi)          # the adverse extreme per bar

    # bars 0 .. exit_idx-1 are the ones the position lives through; the bar whose
    # OPEN is the exit price is not one of them
    live = np.arange(width)[None, :] < exit_idx[:, None]
    breach = live & (s[:, None] * worst <= s[:, None] * level[:, None])
    breach &= np.isfinite(dist_px)[:, None]

    stopped = breach.any(axis=1)
    bar = np.where(stopped, breach.argmax(axis=1), -1)

    rows = np.arange(n)
    open_at_stop = o[rows, np.clip(bar, 0, width - 1)]
    gapped = s * open_at_stop <= s * level            # already beyond at the open
    fill = np.where(gapped, open_at_stop, level)
    fill = fill - s * slippage_pips * pip             # adverse slippage

    exit_px = o[rows, exit_idx]
    px = np.where(stopped, fill, exit_px)
    return s * (px - entry) / pip, stopped, bar


def drawdown_R(r_series):
    """Maximum peak-to-trough drawdown of the cumulative per-bet R curve."""
    c = np.cumsum(np.asarray(r_series, float))
    if not len(c):
        return np.nan
    return float(np.max(np.maximum.accumulate(c) - c))


def metrics(pips, sigma, sdate, years, stopped=None, **extra):
    g = pd.Series(np.asarray(pips, float))
    ok = g.notna().to_numpy()
    g = g[ok]
    if len(g) < 100:
        return {"signals": int(len(g)), **extra}
    sig = pd.Series(np.asarray(sigma, float))[ok]
    sd = pd.Series(np.asarray(sdate))[ok]
    r = (g / sig.values).values
    mean_pips, mean_R = float(g.mean()), float(np.mean(r))
    total = g.sum()
    w1 = g.nsmallest(max(1, int(0.01 * len(g)))).sum() / total if total else np.nan
    w5 = g.nsmallest(max(1, int(0.05 * len(g)))).sum() / total if total else np.nan
    daily = pd.Series(r).groupby(sd.values).sum()
    row = {
        "signals": int(len(g)),
        "signals_per_year": len(g) / years,
        "mean_pips": mean_pips,
        "median_pips": float(g.median()),
        "mean_R": mean_R,
        "implied_risk_unit_pips": mean_pips / mean_R if mean_R else np.nan,
        "cluster_t": session_cluster_t(g, sd),
        "hit_rate": float((g > 0).mean()),
        "per_signal_sharpe": mean_pips / float(g.std(ddof=1)),
        "worst_1pct_share": float(w1),
        "worst_5pct_share": float(w5),
        "max_drawdown_R": drawdown_R(r),
        "worst_day_R": float(daily.min()),
        "sd_daily_R": float(daily.std(ddof=1)),
        **extra,
    }
    if stopped is not None:
        row["stopped_frac"] = float(np.asarray(stopped, bool)[ok].mean())
    for c in COSTS:
        row[f"net_{c}_pips"] = mean_pips - c
        row[f"annual_net_{c}_pips"] = (mean_pips - c) * len(g) / years
    return row


def years_of(d):
    return d.sdate.nunique() / SESSIONS_PER_YEAR
