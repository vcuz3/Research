"""Reusable Stage-A (EXP-0002) characterization primitives.

Kept separate from the orchestration in ``_run_stage_a.py`` so every non-trivial
estimator here is unit-tested in ``test_stage_a.py`` against synthetic series with
known answers (a random walk, an AR(1) with known sign, a pure gap pattern).

Nothing in this module simulates a fill, charges a cost, or computes a P&L metric:
those come from the audited ``forex/exploration_1`` components, imported by the
runner. What lives here is description -- variance ratios, grain resampling,
first-crossing event selection, forward-window lookups, and coverage bookkeeping.

Conventions fixed once, matching ``experiments/hypotheses/HYP-0002.md``:

* tau-bars are epoch-anchored, label='left', closed='left'; the bar stamped T covers
  [T, T+tau) and is tradable only if all tau source minutes exist.
* A signal on bar i is executed at the OPEN of bar i+1, i.e. at 1-minute
  timestamp T_i + tau. Path column m maps to entry_minute + m, so a fixed-horizon
  exit after H minutes is the open at column m = H.
* z_tau(t) = one-bar tau-return / sigma_tau(t); sigma_tau is a trailing std over a
  fixed 28,800-minute (20-day) TIME window with a fractional min_periods floor.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


SESSION_LABELS = ("asia", "london", "overlap", "ny", "off")
ALL_SESSIONS = SESSION_LABELS + ("all",)


# --------------------------------------------------------------------------- #
# Calendars, eras, sessions
# --------------------------------------------------------------------------- #

def as_naive_utc(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Timezone-naive UTC view. Internal timestamps are naive UTC throughout: the
    source Parquets are, and tz-aware indexes lose their datetime64 dtype under
    ``to_numpy`` in pandas 3, which silently breaks integer minute arithmetic."""
    idx = pd.DatetimeIndex(index)
    return idx.tz_convert("UTC").tz_localize(None) if idx.tz is not None else idx


def minute_positions(index: pd.DatetimeIndex) -> np.ndarray:
    """Whole minutes since the Unix epoch (exact for minute-stamped data)."""
    return as_naive_utc(index).to_numpy().astype("datetime64[m]").astype("int64")


def era_of(index: pd.DatetimeIndex, era_split: pd.Timestamp, holdout_start: pd.Timestamp) -> np.ndarray:
    """Era label per timestamp: 'early' < era_split <= 'late' < holdout_start <= 'holdout'."""
    t = as_naive_utc(index).to_numpy()
    split = np.datetime64(pd.Timestamp(era_split).tz_localize(None)
                          if pd.Timestamp(era_split).tz is None
                          else pd.Timestamp(era_split).tz_convert("UTC").tz_localize(None))
    hold = np.datetime64(pd.Timestamp(holdout_start).tz_localize(None)
                         if pd.Timestamp(holdout_start).tz is None
                         else pd.Timestamp(holdout_start).tz_convert("UTC").tz_localize(None))
    return np.where(t >= hold, "holdout", np.where(t >= split, "late", "early"))


def _local_minute(index: pd.DatetimeIndex, tz: str) -> np.ndarray:
    loc = as_naive_utc(index).tz_localize("UTC").tz_convert(tz)
    return loc.hour.to_numpy() * 60 + loc.minute.to_numpy()


def session_codes(index: pd.DatetimeIndex, sessions_cfg: dict) -> np.ndarray:
    """DST-aware session code per timestamp, indexing ``SESSION_LABELS``.

    Overlap dominates: a minute inside both London and New York hours is 'overlap',
    never double-counted. 'asia' is Tokyo hours that are not already London or NY.
    Using each venue's OWN timezone (with real DST) rather than a fixed UTC block is
    deliberate: a hardcoded UTC session boundary misfiles roughly six weeks a year.
    """
    tok = sessions_cfg["tokyo"]
    lon = sessions_cfg["london"]
    nyc = sessions_cfg["new_york"]
    m_tok = _local_minute(index, tok["tz"])
    m_lon = _local_minute(index, lon["tz"])
    m_ny = _local_minute(index, nyc["tz"])
    in_tok = (m_tok >= tok["open_minute"]) & (m_tok < tok["close_minute"])
    in_lon = (m_lon >= lon["open_minute"]) & (m_lon < lon["close_minute"])
    in_ny = (m_ny >= nyc["open_minute"]) & (m_ny < nyc["close_minute"])

    code = np.full(len(index), SESSION_LABELS.index("off"), dtype=np.int16)
    code[in_tok & ~in_lon & ~in_ny] = SESSION_LABELS.index("asia")
    code[in_lon & ~in_ny] = SESSION_LABELS.index("london")
    code[in_ny & ~in_lon] = SESSION_LABELS.index("ny")
    code[in_lon & in_ny] = SESSION_LABELS.index("overlap")
    return code


# --------------------------------------------------------------------------- #
# View 1: variance ratio with Lo-MacKinlay heteroskedasticity-robust inference
# --------------------------------------------------------------------------- #

def accumulate_vr(returns, minute_pos, valid, sess_code, max_lag: int) -> dict:
    """Autocovariance sums for VR, per session cell and pooled ('all').

    ``returns`` must already be demeaned over the analysed subset, with zeros where
    ``valid`` is False. A lag-k pair (t, t-k) is counted only when BOTH one-minute
    returns are individually valid AND the two timestamps are exactly k minutes
    apart, so a data gap can never masquerade as a k-minute serial link. Session
    cells additionally require both endpoints in the same session.

    Returns arrays indexed [lag-1, cell] for lags 1..max_lag, where cell indexes
    ``ALL_SESSIONS`` (the final 'all' cell pools sessions and does NOT require the
    endpoints to share a session -- it is the ambient map).
    """
    r = np.asarray(returns, float)
    mp = np.asarray(minute_pos, np.int64)
    ok = np.asarray(valid, bool)
    sc = np.asarray(sess_code, np.int16)
    n_cell = len(ALL_SESSIONS)
    all_cell = n_cell - 1

    s0 = np.zeros(n_cell)
    n0 = np.zeros(n_cell)
    sq = np.where(ok, r * r, 0.0)
    s0[:len(SESSION_LABELS)] = np.bincount(sc[ok], weights=sq[ok], minlength=len(SESSION_LABELS))
    n0[:len(SESSION_LABELS)] = np.bincount(sc[ok], minlength=len(SESSION_LABELS))
    s0[all_cell] = sq.sum()
    n0[all_cell] = ok.sum()

    s_k = np.zeros((max_lag, n_cell))
    d_k = np.zeros((max_lag, n_cell))
    n_k = np.zeros((max_lag, n_cell))

    for k in range(1, max_lag + 1):
        a, b = r[k:], r[:-k]
        base = ok[k:] & ok[:-k] & ((mp[k:] - mp[:-k]) == k)
        prod = a * b
        # pooled 'all' cell: no same-session requirement
        w = np.where(base, prod, 0.0)
        s_k[k - 1, all_cell] = w.sum()
        d_k[k - 1, all_cell] = np.square(w).sum()
        n_k[k - 1, all_cell] = base.sum()
        # per-session cells
        same = base & (sc[k:] == sc[:-k])
        if same.any():
            cs = sc[k:][same]
            ps = prod[same]
            s_k[k - 1, :len(SESSION_LABELS)] = np.bincount(cs, weights=ps, minlength=len(SESSION_LABELS))
            d_k[k - 1, :len(SESSION_LABELS)] = np.bincount(cs, weights=ps * ps, minlength=len(SESSION_LABELS))
            n_k[k - 1, :len(SESSION_LABELS)] = np.bincount(cs, minlength=len(SESSION_LABELS))
    return {"s_k": s_k, "d_k": d_k, "n_k": n_k, "s0": s0, "n0": n0}


def variance_ratio(acc: dict, tau: int, cell: int) -> dict:
    """VR(tau) for one cell plus the Lo-MacKinlay heteroskedasticity-robust z.

    VR(tau) = 1 + 2 * sum_{k=1}^{tau-1} (1 - k/tau) * rho(k).
    Var[VR] = sum_{k=1}^{tau-1} [2(tau-k)/tau]^2 * delta_k, with
    delta_k = E[(r_t-mu)^2 (r_{t-k}-mu)^2] / (n_k * m2^2).

    The robust form matters here because FX volatility clusters hard: homoskedastic
    inference would understate the SE without moving the point estimate, so a
    random walk would look like a significant reversion.
    """
    n0 = acc["n0"][cell]
    if tau < 2 or n0 < 2:
        return {"vr": np.nan, "z": np.nan, "pairs_min": 0.0, "n_returns": float(n0)}
    m2 = acc["s0"][cell] / n0
    if not np.isfinite(m2) or m2 <= 0:
        return {"vr": np.nan, "z": np.nan, "pairs_min": 0.0, "n_returns": float(n0)}

    vr, var = 1.0, 0.0
    pairs_min = np.inf
    for k in range(1, tau):
        nk = acc["n_k"][k - 1, cell]
        pairs_min = min(pairs_min, nk)
        if nk <= 0:
            return {"vr": np.nan, "z": np.nan, "pairs_min": 0.0, "n_returns": float(n0)}
        rho = (acc["s_k"][k - 1, cell] / nk) / m2
        delta = (acc["d_k"][k - 1, cell] / nk) / (nk * m2 * m2)
        weight = 2.0 * (tau - k) / tau
        vr += weight * rho
        var += weight * weight * delta
    z = (vr - 1.0) / math.sqrt(var) if var > 0 else np.nan
    return {"vr": vr, "z": z, "pairs_min": float(pairs_min), "n_returns": float(n0)}


# --------------------------------------------------------------------------- #
# Grain construction
# --------------------------------------------------------------------------- #

def build_grain_bars(minute_frame: pd.DataFrame, tau: int, sigma_window_minutes: int,
                     min_fraction: float) -> tuple[pd.DataFrame, dict]:
    """Resample 1-minute midpoint OHLC to a tau-minute grid and attach z_tau.

    A bar is ``complete`` only when all tau source minutes are present; incomplete
    bars are nulled rather than filled, so a weekend or an outage can never borrow a
    stale price.

    sigma_tau's window is fixed in TIME at ``sigma_window_minutes`` of MARKET time,
    i.e. ``sigma_window_minutes / tau`` tradable bars at every rung, so the estimator
    spans the same amount of market history at every grain. It is measured over the
    compacted series of tradable returns rather than over raw bins: spot FX covers
    only ~71% of calendar minutes, so a window counted in bins would need a
    ``min_periods`` floor below 0.71 to ever be satisfied, and any floor above that
    silently nulls sigma everywhere. Compacting first means ``min_periods`` acts as a
    warm-up requirement and cannot become a hidden, time-of-day-dependent filter on
    decisions -- which is exactly the failure a strict bin-counted floor produces.
    """
    idx = minute_frame.set_index("time")[["open", "high", "low", "close"]]
    bars = idx.resample(f"{tau}min", origin="epoch", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), minute_count=("close", "count"))
    complete = bars.minute_count.eq(tau)
    bars.loc[~complete, ["open", "high", "low", "close"]] = np.nan

    contiguous = complete & complete.shift(1, fill_value=False)
    ret = bars.close.pct_change(fill_method=None).where(contiguous)

    window = int(round(sigma_window_minutes / tau))
    min_periods = int(math.ceil(min_fraction * window))
    tradable = ret.dropna()
    bars["ret"] = ret
    bars["sigma_count"] = tradable.rolling(window, min_periods=1).count().reindex(bars.index)
    bars["sigma"] = tradable.rolling(window, min_periods=min_periods).std(ddof=1).reindex(bars.index)
    bars["z"] = ret / bars.sigma.replace(0.0, np.nan)
    bars["complete"] = complete
    bars["contiguous"] = contiguous
    meta = {"tau": tau, "window_bars": window, "min_periods": min_periods,
            "sigma_window_minutes": sigma_window_minutes}
    return bars, meta


def same_slot_moments(bars: pd.DataFrame, tau: int, lookback_sessions: int,
                      min_fraction: float) -> tuple[pd.Series, pd.Series]:
    """Causal same-time-of-day mean and std of tau-returns, from PRIOR sessions only.

    An all-hours volatility window cannot see the intraday profile, so a fixed threshold
    on ``ret / sigma_all_hours`` fires far more often in busy hours than quiet ones --
    it is a time-of-day selector wearing a volatility label. Normalising against the
    trailing distribution of the SAME slot removes that.

    Construction details that matter:

    * A full z-score is returned (mean and std), not a ratio-to-mean: a ratio removes
      per-slot location but leaves per-slot scale, and scale is what varies here.
    * The moments are estimated on the FULL slot grid and read at the events. Estimating
      a seasonal normaliser from sparse events instead lets the survivors quietly
      reconstruct the very clock the normalisation was meant to escape.
    * The session axis is compacted to days that actually traded before rolling, so a
      weekend never consumes window slots, and ``min_periods`` is a fractional floor.
    * ``shift(1)`` along the session axis: slot statistics never see the current session.

    Slots are UTC minute-of-day // tau, so slot width equals the decision grain. UTC
    slots do not track DST, so a slot's meaning moves by an hour twice a year relative
    to London/New York local time -- a known limitation, not corrected here.
    """
    idx = as_naive_utc(bars.index)
    slot = (idx.hour.to_numpy() * 60 + idx.minute.to_numpy()) // tau
    day = idx.floor("D")
    ret = bars["ret"]

    frame = pd.DataFrame({"day": day, "slot": slot, "ret": ret.to_numpy()})
    # rows = trading sessions (only days that actually traded), columns = slots
    grid = frame.dropna(subset=["ret"]).pivot_table(index="day", columns="slot",
                                                    values="ret", aggfunc="last")
    min_obs = max(2, int(math.ceil(min_fraction * lookback_sessions)))
    prior = grid.shift(1)
    mu = prior.rolling(lookback_sessions, min_periods=min_obs).mean()
    sd = prior.rolling(lookback_sessions, min_periods=min_obs).std(ddof=1)

    keys = pd.MultiIndex.from_arrays([day, slot])
    mu_flat = mu.stack(future_stack=True)
    sd_flat = sd.stack(future_stack=True)
    return (pd.Series(mu_flat.reindex(keys).to_numpy(), index=bars.index),
            pd.Series(sd_flat.reindex(keys).to_numpy(), index=bars.index))


def first_crossing(z: pd.Series, complete: pd.Series, contiguous: pd.Series, k: float) -> np.ndarray:
    """Bar positions where |z| first crosses k (event clock, not a fixed clock).

    'First' means the immediately preceding bar was either not above k or not
    contiguous with this one. A gap therefore re-arms the signal rather than
    silently suppressing it.
    """
    cond = (z.abs() >= k) & complete
    cond = cond.fillna(False)
    prev_hot = cond.shift(1, fill_value=False) & contiguous.fillna(False)
    return np.flatnonzero((cond & ~prev_hot).to_numpy())


# --------------------------------------------------------------------------- #
# Minute grid: forward windows and coverage
# --------------------------------------------------------------------------- #

class MinuteGrid:
    """Dense minute-indexed view of a pair, for O(1) forward-window lookups.

    The dense grid exists so that "is every minute in [e, e+H] present?" is an exact
    integer test rather than an approximate one, and so that forward rolling
    extremes can be computed once per horizon for the whole pair instead of per
    signal. Positions are minutes since the Unix epoch.
    """

    def __init__(self, time: pd.DatetimeIndex, open_, high, low):
        pos = minute_positions(time)
        self.start = int(pos.min())
        self.size = int(pos.max()) - self.start + 1
        self.open = np.full(self.size, np.nan)
        self.high = np.full(self.size, np.nan)
        self.low = np.full(self.size, np.nan)
        off = pos - self.start
        self.open[off] = np.asarray(open_, float)
        self.high[off] = np.asarray(high, float)
        self.low[off] = np.asarray(low, float)
        present = np.zeros(self.size, np.int32)
        present[off] = 1
        # cum[i] = number of present minutes at grid offsets 0..i
        self.cum = np.cumsum(present, dtype=np.int64)
        self.present = present.astype(bool)

    def offsets(self, minute_pos) -> np.ndarray:
        return np.asarray(minute_pos, np.int64) - self.start

    def _gather(self, arr: np.ndarray, off: np.ndarray) -> np.ndarray:
        out = np.full(len(off), np.nan)
        ok = (off >= 0) & (off < self.size)
        out[ok] = arr[off[ok]]
        return out

    def open_at(self, off: np.ndarray) -> np.ndarray:
        return self._gather(self.open, off)

    def path_complete_span(self, start_off, end_off) -> np.ndarray:
        """True where every minute in [start_off, end_off] exists. Ends may be arrays,
        which is what lets a per-row entry delay (delay * tau, and tau varies by row)
        be screened on exactly the same span as the undelayed arm."""
        start = np.asarray(start_off, np.int64)
        end = np.asarray(end_off, np.int64)
        ok = (start >= 0) & (end < self.size) & (end >= start)
        lo = start - 1
        got = np.where(lo >= 0, self.cum[np.clip(lo, 0, self.size - 1)], 0)
        span = self.cum[np.clip(end, 0, self.size - 1)] - got
        return ok & (span == (end - start + 1))

    def path_complete(self, off: np.ndarray, horizon: int) -> np.ndarray:
        """True where every minute in [off, off+horizon] exists (horizon+1 minutes)."""
        off = np.asarray(off, np.int64)
        return self.path_complete_span(off, off + int(horizon))

    def forward_extremes(self, horizon: int) -> tuple[np.ndarray, np.ndarray]:
        """(max high, min low) over [m, m+horizon] for every grid offset m."""
        w = horizon + 1
        hi = pd.Series(self.high).rolling(w, min_periods=1).max().shift(-horizon).to_numpy()
        lo = pd.Series(self.low).rolling(w, min_periods=1).min().shift(-horizon).to_numpy()
        return hi, lo

    def extract_paths(self, off: np.ndarray, horizon: int) -> dict:
        """(n, horizon+1) OHL path block starting at each offset. Callers must have
        already screened rows with ``path_complete``; unavailable cells are NaN."""
        cols = np.arange(horizon + 1, dtype=np.int64)
        idx = np.asarray(off, np.int64)[:, None] + cols[None, :]
        valid = (idx >= 0) & (idx < self.size)
        safe = np.clip(idx, 0, self.size - 1)
        out = {}
        for name, arr in (("open", self.open), ("high", self.high), ("low", self.low)):
            block = arr[safe]
            block[~valid] = np.nan
            out[name] = block
        return out


# --------------------------------------------------------------------------- #
# Inference and metrics
# --------------------------------------------------------------------------- #

def cluster_stats(values, clusters) -> dict:
    """Per-observation mean with a one-way cluster-robust SE (clusters = UTC days).

    This is the estimand the run-book fixes: the per-signal mean with a block
    cluster-robust SE. Block-AVERAGING the values first would be the trap -- it
    inverts sign when signal count is endogenous to the outcome.
    """
    z = pd.DataFrame({"value": np.asarray(values, float), "cluster": np.asarray(clusters)}).dropna()
    n = len(z)
    groups = z.cluster.nunique()
    if n < 2 or groups < 2:
        return {"n": n, "clusters": groups, "mean": np.nan, "se": np.nan,
                "t": np.nan, "ci_low": np.nan, "ci_high": np.nan}
    mean = float(z.value.mean())
    scores = (z.value - mean).groupby(z.cluster).sum()
    se = float(np.sqrt((groups / (groups - 1)) * np.square(scores).sum()) / n)
    return {"n": int(n), "clusters": int(groups), "mean": mean, "se": se,
            "t": mean / se if se > 0 else np.nan,
            "ci_low": mean - 1.96 * se, "ci_high": mean + 1.96 * se}


def profit_factor(r) -> float:
    """sum(positive R) / sum(|negative R|). Bounded barriers keep this off the tails."""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    gain = r[r > 0].sum()
    loss = -r[r < 0].sum()
    if loss <= 0:
        return np.inf if gain > 0 else np.nan
    return float(gain / loss)


def greedy_non_overlap(entry_minute, exit_minute) -> np.ndarray:
    """Boolean keep-mask enforcing one position at a time (Rule 13), first come first
    served in time order. Inputs must already be sorted by ``entry_minute``."""
    e = np.asarray(entry_minute, np.int64)
    x = np.asarray(exit_minute, np.int64)
    keep = np.zeros(len(e), bool)
    free_at = -np.inf
    for i in range(len(e)):
        if e[i] >= free_at:
            keep[i] = True
            free_at = x[i]
    return keep


def three_sharpes(daily: pd.Series, all_days: pd.DatetimeIndex, periods: int = 252,
                  vol_target: float = 0.01, lookback: int = 60, max_leverage: float = 5.0) -> dict:
    """Zero-day, trade-days-only and vol-targeted annualized Sharpes.

    They routinely disagree, which is why all three are reported: the zero-day
    figure charges the strategy for the days it sits out, the trade-days-only figure
    does not, and the vol-targeted figure depends on account size through the
    leverage clip. The targeting is causal -- leverage uses a trailing standard
    deviation shifted one day, so today's scale never sees today's return.
    """
    filled = daily.reindex(all_days).fillna(0.0)
    out = {}
    sd = filled.std(ddof=1)
    out["sharpe_zero_day"] = float(filled.mean() / sd * np.sqrt(periods)) if sd > 0 else np.nan
    traded = daily.dropna()
    sdt = traded.std(ddof=1)
    out["sharpe_trade_days"] = float(traded.mean() / sdt * np.sqrt(periods)) if sdt > 0 and len(traded) > 1 else np.nan
    roll = filled.rolling(lookback, min_periods=max(10, lookback // 3)).std(ddof=1).shift(1)
    lev = (vol_target / roll).clip(upper=max_leverage).fillna(0.0)
    scaled = filled * lev
    sds = scaled.std(ddof=1)
    out["sharpe_vol_targeted"] = float(scaled.mean() / sds * np.sqrt(periods)) if sds > 0 else np.nan
    out["n_days_zero_filled"] = int(len(filled))
    out["n_trade_days"] = int(len(traded))
    return out


def to_text_table(frame: pd.DataFrame, decimals: int = 4) -> str:
    """Fenced plain-text table; avoids a hard dependency on ``tabulate``."""
    if frame is None or len(frame) == 0:
        return "_No rows._"
    show = frame.copy()
    for col in show.select_dtypes(include=["number"]).columns:
        show[col] = show[col].round(decimals)
    with pd.option_context("display.max_columns", None, "display.width", 250):
        return "```text\n" + show.to_string(index=False) + "\n```"
