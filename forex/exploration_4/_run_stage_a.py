"""EXP-0002 -- Stage A: multi-scale market characterization for USD-major spot FX.

Reproduce from the workspace root:
    python -u forex/exploration_4/_run_stage_a.py

Contract: `experiments/hypotheses/HYP-0002.md` (frozen before this ran) and
`RUNBOOK.md` §STAGE A. This is DESCRIPTION: it commits no strategy and issues no
GO/NO-GO. Its one output decision is the (decision grain, holding-horizon cap) that
Stage B will freeze its reference book at.

HONEST LABEL (Stage-A repair F1): that (grain, horizon) is selected by the
pre-committed rule in HYP-0002 §6, which maximizes the z-fade's **gross** strategy
return over horizons and ranks grains by that maximum. So tau=5 / H=240 are
CONSUMED-HISTORY, GROSS-P&L-SELECTED candidates -- not net-P&L-tuned, but not
"untuned" either, and not confirmed. The raw CI on the selected maximum is not
selection-adjusted; "only rung whose CI excludes zero" is descriptive, not
confirmatory. The 2024+ segment was opened once here and its tau=5 CI included zero,
so it did NOT confirm the selection and is no longer a clean holdout. Only future
observations can now provide a clean temporal holdout.

Order of operations is deliberate: the Rule 9a coverage bookkeeping is collected
before any statistic is interpreted, then the three views, then the pre-committed
selection rule is applied mechanically in `apply_grain_rule` so the choice is
reproducible rather than narrated. The sealed 2024+ holdout is segregated
throughout and reported once, at the end, where it cannot influence the selection.

Fills, barrier resolution, costs and the macro calendar are imported from the
audited `forex/exploration_1` implementation and are not reimplemented here.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent
EXPLORATION_1 = PROJECT.parent / "exploration_1"
for _p in (str(EXPLORATION_1), str(PROJECT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _bracket_engine import simulate_bracket                      # noqa: E402
from _cost_model import CostParams, round_trip_pips               # noqa: E402
from _run_rsi_axis6_calendar import high_impact_times             # noqa: E402
from _run_rsi_broad_regime_sweep import PIP                       # noqa: E402

import _stage_a_lib as lib                                        # noqa: E402


CONFIG_PATH = PROJECT / "baseline_replication" / "configs" / "stage_a.json"
ARTIFACT = PROJECT / "artifacts" / "runs" / "EXP-0002"
REPORTS = PROJECT / "reports"
DATA = PROJECT.parent / "data" / "clean"

# The cost model knows two spread eras; the sealed holdout inherits the late one.
ERA_TO_COST_ERA = {"early": "early", "late": "late", "holdout": "late"}

CELL_GROUP = ["pair", "era", "session", "tau"]


def naive_ts(value) -> pd.Timestamp:
    """Config timestamps are written with a UTC 'Z'; internal indexes are naive UTC."""
    t = pd.Timestamp(value)
    return t.tz_convert("UTC").tz_localize(None) if t.tz is not None else t


def log(msg: str) -> None:
    print(f"[{_time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Loading and source-level data quality
# --------------------------------------------------------------------------- #

def load_minutes(pair: str, cfg: dict):
    """Load 1-minute midpoint OHLC and emit this pair's Rule 9a coverage rows."""
    path = DATA / f"{pair}_1m_clean.parquet"
    raw = pd.read_parquet(path, columns=["ts_utc", "open", "high", "low", "close"])
    t = pd.DatetimeIndex(pd.to_datetime(raw.ts_utc))
    overall = {
        "pair": pair,
        "rows_raw": int(len(raw)),
        "start": str(t.min()),
        "end": str(t.max()),
        "duplicate_timestamps": int(t.duplicated().sum()),
        "out_of_order": int((t.to_series().diff().dropna() < pd.Timedelta(0)).sum()),
        "volume_field": "absent",
        "bid_ask": "absent",
    }
    frame = (raw.assign(time=t).sort_values("time", kind="stable")
             .drop_duplicates("time", keep="last").reset_index(drop=True).drop(columns=["ts_utc"]))

    idx = pd.DatetimeIndex(frame.time)
    frame["era"] = lib.era_of(idx, naive_ts(cfg["era_split"]), naive_ts(cfg["holdout_start"]))
    frame["utc_hour"] = idx.hour
    frame["utc_day"] = idx.floor("D")

    delta = frame.time.diff().dt.total_seconds().div(60.0)
    is_gap = delta.gt(1).fillna(False)
    tmp = pd.DataFrame({
        "era": frame.era, "utc_hour": frame.utc_hour, "utc_day": frame.utc_day,
        "gap": is_gap.astype(int),
        "missing_minutes": np.where(is_gap, delta - 1.0, 0.0),
        "short_gap": (is_gap & delta.le(180)).astype(int),
        "short_missing_minutes": np.where(is_gap & delta.le(180), delta - 1.0, 0.0),
    })
    hour_rows = (tmp.groupby(["era", "utc_hour"], observed=True)
                 .agg(minutes=("gap", "size"), utc_days=("utc_day", "nunique"),
                      gaps=("gap", "sum"), missing_minutes=("missing_minutes", "sum"),
                      short_gaps=("short_gap", "sum"),
                      short_missing_minutes=("short_missing_minutes", "sum")).reset_index())
    hour_rows.insert(0, "pair", pair)

    # Long-gap price jumps: the raw material behind the weekend-flat constraint.
    gi = np.flatnonzero(is_gap.to_numpy())
    weekend = pd.DataFrame({
        "pair": pair,
        "era": frame.era.to_numpy()[gi],
        "gap_minutes": delta.to_numpy()[gi],
        "close_weekday": pd.DatetimeIndex(frame.time.to_numpy()[gi - 1]).weekday,
        "jump_pips": (frame.open.to_numpy()[gi] - frame.close.to_numpy()[gi - 1]) / PIP,
    })
    return frame, overall, hour_rows, weekend


# --------------------------------------------------------------------------- #
# View 1: variance ratio
# --------------------------------------------------------------------------- #

def pair_vr_accumulators(frame: pd.DataFrame, cfg: dict) -> dict:
    """Per-era-group VR accumulators from 1-minute log returns.

    Returns for the pooled 'all' cell are demeaned WITHIN each era group so a drift
    difference between eras cannot leak into the ambient autocovariances. For the
    per-session cells the returns are additionally demeaned WITHIN each (era-group,
    session) group (Stage-A repair F5): a per-session VR built on the whole-day mean
    would otherwise charge each session's own drift to its serial dependence. A return
    is valid only when the preceding minute actually exists.
    """
    idx = pd.DatetimeIndex(frame.time)
    mpos = lib.minute_positions(idx)
    logp = np.log(frame.close.to_numpy(float))
    r = np.empty(len(logp))
    r[0] = np.nan
    r[1:] = np.diff(logp)
    contiguous = np.zeros(len(r), bool)
    contiguous[1:] = (mpos[1:] - mpos[:-1]) == 1
    started = np.asarray(idx >= naive_ts(cfg["start"]))
    base_valid = np.isfinite(r) & contiguous & started

    sess = lib.session_codes(idx, cfg["sessions"])
    era = frame.era.to_numpy()
    out = {}
    for name, mask in (("consumed", era != "holdout"), ("holdout", era == "holdout")):
        valid = base_valid & mask
        if valid.sum() < 1000:
            continue
        dm = np.where(valid, r - r[valid].mean(), 0.0)
        # session-demeaned copy: subtract the mean of each session within this
        # era-group. Sessions can overlap in code space, so demean per session code.
        dm_sess = np.array(dm, copy=True)
        for code in np.unique(sess[valid]):
            cell = valid & (sess == code)
            if cell.any():
                dm_sess[cell] = r[cell] - r[cell].mean()
        out[name] = lib.accumulate_vr(dm, mpos, valid, sess,
                                      max_lag=cfg["vr_max_lag_minutes"] - 1,
                                      returns_sess=dm_sess)
    return out


def add_accumulators(a: dict | None, b: dict) -> dict:
    """VR accumulators are plain sums, so pooling across pairs is exact."""
    return {k: v.copy() for k, v in b.items()} if a is None else {k: a[k] + b[k] for k in a}


def vr_rows(acc_by_group: dict, pair: str, cfg: dict) -> list[dict]:
    rows = []
    for group, acc in acc_by_group.items():
        for tau in cfg["grain_ladder_minutes"]:
            for ci, cell in enumerate(lib.ALL_SESSIONS):
                out = lib.variance_ratio(acc, tau, ci)
                rows.append({"pair": pair, "era": group, "session": cell, "tau": tau,
                             "vr": out["vr"], "lm_z": out["z"],
                             "n_returns": out["n_returns"], "min_lag_pairs": out["pairs_min"]})
    return rows


# --------------------------------------------------------------------------- #
# One pass over the grain ladder: DQ, vol profile, shape, signals
# --------------------------------------------------------------------------- #

def grain_pass(pair: str, frame: pd.DataFrame, grid: lib.MinuteGrid, cfg: dict,
               news: np.ndarray) -> dict:
    """Build every rung of the ladder once and harvest everything that needs bars."""
    ohlc = frame[["time", "open", "high", "low", "close"]]
    dq_parts, vol_parts, shape_rows, sig_parts, drift_rows = [], [], [], [], []
    z_forward = {}

    for tau in cfg["grain_ladder_minutes"]:
        bars, meta = lib.build_grain_bars(ohlc, tau, cfg["sigma_window_minutes"],
                                          cfg["sigma_min_fraction"])
        bidx = pd.DatetimeIndex(bars.index)
        era = lib.era_of(bidx, naive_ts(cfg["era_split"]), naive_ts(cfg["holdout_start"]))
        sess = np.asarray(lib.SESSION_LABELS, dtype=object)[lib.session_codes(bidx, cfg["sessions"])]
        decision = np.asarray(bidx >= naive_ts(cfg["start"]))
        complete = bars.complete.to_numpy(bool)

        # -- Rule 9a coverage for this rung ---------------------------------- #
        dq = pd.DataFrame({
            "pair": pair, "tau": tau, "era": era, "utc_hour": bidx.hour,
            "eligible_bars": (decision & complete).astype(int),
            "incomplete_bins": (decision & ~complete).astype(int),
            "sigma_underpopulated": (decision & complete
                                     & bars.sigma_count.lt(meta["min_periods"]).to_numpy()).astype(int),
            "z_unavailable": (decision & complete & bars.z.isna().to_numpy()).astype(int),
        })
        agg = dq.groupby(["pair", "tau", "era", "utc_hour"], observed=True).sum().reset_index()
        agg["window_bars"] = meta["window_bars"]
        agg["min_periods"] = meta["min_periods"]
        dq_parts.append(agg)

        live_mask = decision & complete & bars.sigma.notna().to_numpy()
        live = pd.DataFrame({
            "era": era[live_mask], "session": sess[live_mask], "utc_hour": bidx.hour[live_mask],
            "sigma_pips": (bars.sigma.to_numpy()[live_mask] * bars.close.to_numpy()[live_mask] / PIP),
            "ret": bars.ret.to_numpy()[live_mask], "z": bars.z.to_numpy()[live_mask],
        })
        v = (live.groupby(["era", "utc_hour"], observed=True)
             .agg(bars=("sigma_pips", "size"), median_sigma_pips=("sigma_pips", "median"),
                  mean_sigma_pips=("sigma_pips", "mean")).reset_index())
        v.insert(0, "tau", tau)
        v.insert(0, "pair", pair)
        vol_parts.append(v)

        for era_name, zz in live.dropna(subset=["z", "ret"]).groupby("era", observed=True):
            shape_rows.append({
                "pair": pair, "tau": tau, "era": era_name, "n": int(len(zz)),
                "ret_skew": float(zz.ret.skew()), "ret_excess_kurtosis": float(zz.ret.kurtosis()),
                "share_abs_z_gt2": float((zz.z.abs() > 2).mean()),
                "share_abs_z_gt3": float((zz.z.abs() > 3).mean()),
                "share_abs_z_gt4": float((zz.z.abs() > 4).mean()),
                "median_sigma_pips": float(zz.sigma_pips.median()),
            })
        del live

        # -- forward rolling z extremes, for the rolling z->0 exit rate -------- #
        zser = pd.Series(bars.z.to_numpy(float))
        zf = {}
        for h in cfg["horizon_minutes"]:
            nb = h // tau
            if nb >= 1:
                zf[h] = (zser.rolling(nb + 1, min_periods=1).min().shift(-nb).to_numpy(),
                         zser.rolling(nb + 1, min_periods=1).max().shift(-nb).to_numpy())
        z_forward[tau] = zf
        del zser

        # -- naive always-long drift, sampled on the hourly grid --------------- #
        if tau == 60:
            drift_rows = drift_sample(pair, bidx, era, sess, complete & decision, grid, cfg)

        # -- first-crossing signals ------------------------------------------- #
        closes, opens = bars.close.to_numpy(float), bars.open.to_numpy(float)
        sigmas, zs = bars.sigma.to_numpy(float), bars.z.to_numpy(float)
        contiguous = bars.contiguous.to_numpy(bool)
        bar_minutes = lib.minute_positions(bidx)
        for k in cfg["entry_k_grid"]:
            sig = lib.first_crossing(bars.z, bars.complete, bars.contiguous, k)
            sig = sig[decision[sig] & contiguous[sig]]     # anchor bar must exist and adjoin
            sig = sig[sig + 1 < len(bars)]
            ent = sig + 1
            ok = complete[ent] & np.isfinite(sigmas[sig]) & (sigmas[sig] > 0)
            sig, ent = sig[ok], ent[ok]
            if len(sig) == 0:
                continue
            d = pd.DataFrame({
                "pair": pair, "tau": tau, "k": k,
                "entry_bar": ent, "signal_time": bidx[sig], "entry_time": bidx[ent],
                "entry_minute": bar_minutes[ent], "era": era[ent], "session": sess[ent],
                "utc_hour": bidx[ent].hour, "utc_day": bidx[ent].floor("D"),
                "z_signal": zs[sig], "sigma": sigmas[sig],
                "anchor_price": closes[sig - 1], "entry_price": opens[ent],
            })
            d["side"] = np.where(d.z_signal < 0, 1.0, -1.0)
            sig_parts.append(d)
        del bars

    signals = pd.concat(sig_parts, ignore_index=True)
    sidx = pd.DatetimeIndex(signals.entry_time)
    ny = sidx.tz_localize("UTC").tz_convert("America/New_York")
    signals["ny_weekday"] = ny.weekday.to_numpy()
    signals["ny_minute"] = ny.hour.to_numpy() * 60 + ny.minute.to_numpy()
    signals["sigma_pips"] = signals.sigma * signals.entry_price / PIP
    signals["news_distance_minutes"] = nearest_event_minutes(sidx, news)
    signals["news_veto"] = signals.news_distance_minutes < cfg["news_blackout_minutes"]

    return {"dq": pd.concat(dq_parts, ignore_index=True),
            "vol": pd.concat(vol_parts, ignore_index=True),
            "shape": pd.DataFrame(shape_rows),
            "drift": drift_rows,
            "signals": signals,
            "z_forward": z_forward}


def drift_sample(pair, bidx, era, sess, usable, grid: lib.MinuteGrid, cfg: dict) -> pd.DataFrame:
    """Raw always-long observations from every complete hourly bar open.

    This exists so that no later overlay can be credited with a directional tilt that
    was in the tape all along. The always-short drift is the exact negative.

    Deliberately returns RAW rows, not cell summaries: pooling has to happen after all
    pairs are concatenated. Summarizing inside the per-pair pass would emit four
    different "POOLED" cells, each secretly a single pair.
    """
    minutes = lib.minute_positions(bidx)[usable]
    off = grid.offsets(minutes)
    entry_px = grid.open_at(off)
    era_u, sess_u = era[usable], sess[usable]
    day = bidx[usable].floor("D")
    rows = []
    for h in cfg["horizon_minutes"]:
        ok = grid.path_complete(off, h)
        pips = np.where(ok, (grid.open_at(off + h) - entry_px) / PIP, np.nan)
        d = pd.DataFrame({"pair": pair, "era": era_u, "session": sess_u, "utc_day": day,
                          "horizon_minutes": h, "long_pips": pips}).dropna(subset=["long_pips"])
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def drift_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Cell summaries for the naive drift, pooled across pairs exactly once."""
    out = []
    for h, d in raw.groupby("horizon_minutes", observed=True):
        parts = [cluster_summary(f, ["pair", "era", "session"], "long_pips") for f in cell_frames(d)]
        s = pd.concat(parts, ignore_index=True)
        s["horizon_minutes"] = h
        out.append(s)
    return pd.concat(out, ignore_index=True).rename(
        columns={"mean": "always_long_pips", "ci_low": "long_ci_low", "ci_high": "long_ci_high"})


def nearest_event_minutes(times: pd.DatetimeIndex, events: np.ndarray) -> np.ndarray:
    et = lib.as_naive_utc(times).to_numpy().astype("datetime64[m]")
    if len(events) == 0:
        return np.full(len(et), np.inf)
    pos = np.searchsorted(events, et, side="left")
    nxt = np.full(len(et), np.inf)
    ok = pos < len(events)
    nxt[ok] = (events[pos[ok]] - et[ok]) / np.timedelta64(1, "m")
    prv = np.full(len(et), np.inf)
    okp = pos > 0
    prv[okp] = (et[okp] - events[pos[okp] - 1]) / np.timedelta64(1, "m")
    return np.minimum(np.abs(nxt), np.abs(prv))


def attach_forward_outcomes(signals: pd.DataFrame, grid: lib.MinuteGrid,
                            z_forward: dict, cfg: dict) -> pd.DataFrame:
    """Fixed-horizon fade returns, anchor-retrace touches and rolling z->0 rates.

    Every horizon requires a STRICTLY complete 1-minute path over [entry, entry+H];
    no stale price is ever carried across a hole. Coverage is therefore horizon-
    dependent by construction, which is exactly why the per-cell count travels with
    every statistic and why the common-sample view exists alongside the maximal one.

    Two entry arms are measured. `d0` enters at the open of the bar after the signal
    bar, as the frozen spec says. `d1` waits one further bar. This is not a latency
    model -- it is the control for a known artifact: in this archive
    `open[i] == close[i-1]` for 99.99998% of contiguous minutes, so the d0 entry price
    is the SAME NUMBER as the price that ends the displacement window. Any transient
    pricing error at that instant enters the displacement with +1 and the forward
    return with -1, manufacturing reversion that no cost model can remove. `d1` puts
    one bar of separation between the two and is the arm that is free of it. Both
    arms are screened on the SAME span [signal-adjacent bar, delayed exit] so the
    comparison is coverage-matched rather than sample-shifted.
    """
    off = grid.offsets(signals.entry_minute.to_numpy())
    side = signals.side.to_numpy(float)
    anchor = signals.anchor_price.to_numpy(float)
    sigma = signals.sigma.to_numpy(float)
    tau = signals.tau.to_numpy()
    bars = signals.entry_bar.to_numpy()
    zsig = signals.z_signal.to_numpy(float)
    inside = (off >= 0) & (off < grid.size)

    for delay in cfg["entry_delay_bars"]:
        start = off + delay * tau
        entry_px_d = grid.open_at(start)
        for h in cfg["horizon_minutes"]:
            end = start + h
            complete = grid.path_complete_span(off, end)
            ret = np.where(complete, side * (grid.open_at(end) / entry_px_d - 1.0), np.nan)
            signals[f"gross_R_d{delay}_{h}"] = ret / sigma
            signals[f"gross_pips_d{delay}_{h}"] = ret * entry_px_d / PIP
            signals[f"complete_d{delay}_{h}"] = complete

    entry_px = signals.entry_price.to_numpy(float)
    for h in cfg["horizon_minutes"]:
        complete = signals[f"complete_d0_{h}"].to_numpy(bool)
        hi, lo = grid.forward_extremes(h)
        fmax = np.full(len(off), np.nan)
        fmin = np.full(len(off), np.nan)
        fmax[inside] = hi[off[inside]]
        fmin[inside] = lo[off[inside]]
        del hi, lo
        for frac in cfg["retrace_fractions"]:
            target = entry_px + frac * (anchor - entry_px)
            touched = np.where(side > 0, fmax >= target, fmin <= target)
            signals[f"touch{int(frac * 100)}_{h}"] = np.where(complete, touched.astype(float), np.nan)

        zc = np.full(len(off), np.nan)
        for t in cfg["grain_ladder_minutes"]:
            zf = z_forward.get(t, {}).get(h)
            if zf is None:
                continue
            m = tau == t
            if not m.any():
                continue
            zmin, zmax = zf
            zc[m] = np.where(zsig[m] > 0, zmin[bars[m]] <= 0.0, zmax[bars[m]] >= 0.0)
        signals[f"zcross_{h}"] = np.where(complete, zc, np.nan)
        signals[f"friday_truncated_{h}"] = (signals.ny_weekday.to_numpy() == 4) & \
                                           (signals.ny_minute.to_numpy() + h > cfg["friday_flat_ny_minute"])
    return signals


def attach_costs(signals: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Modelled round-trip cost per signal, in pips and in that signal's own R.

    Nothing here is measured: the archive has no bid/ask. The number that decides
    anything is the breakeven round-trip pip reported beside gross.
    """
    # F2 (Stage-A repair): the vol_ratio denominator is a per-(pair,tau) sigma
    # median. Computing it over ALL rows leaks the sealed 2024+ holdout into every
    # consumed-era cost. Estimate the median on consumed eras only and map it back
    # onto every row (holdout rows are priced against the consumed median, causal).
    consumed = signals.loc[signals.era.ne("holdout")]
    med_map = consumed.groupby(["pair", "tau"], observed=True).sigma_pips.median()
    keys = pd.MultiIndex.from_arrays([signals.pair, signals.tau])
    med = keys.map(med_map).to_numpy(dtype=float)
    vol_ratio = signals.sigma_pips.to_numpy() / med
    cost_era = signals.era.map(ERA_TO_COST_ERA).to_numpy()
    hour = signals.utc_hour.to_numpy()
    pair_arr = signals.pair.to_numpy()
    for scenario in cfg["cost_scenarios"]:
        params = CostParams(scenario=scenario)
        pips = np.full(len(signals), np.nan)
        for pair in np.unique(pair_arr):
            m = pair_arr == pair
            pips[m] = round_trip_pips(pair, hour[m], cost_era[m], vol_ratio[m], params)
        signals[f"cost_pips_{scenario}"] = pips
        signals[f"cost_R_{scenario}"] = pips * PIP / (signals.sigma * signals.entry_price)
    return signals


# --------------------------------------------------------------------------- #
# Cell pooling and cluster-robust aggregation
# --------------------------------------------------------------------------- #

def cell_frames(frame: pd.DataFrame):
    """Yield the frame relabelled for each pooling combination.

    Pooled cells are produced by relabelling rather than by concatenating copies:
    ``assign`` shares the untouched column data, so the eight passes cost eight
    groupbys instead of an eight-fold memory blow-up on a 600k-row signal table.
    """
    for era_pool in (False, True):
        f0 = frame
        if era_pool:
            f0 = f0.loc[f0.era.isin(("early", "late"))]
            if f0.empty:
                continue
            f0 = f0.assign(era="consumed")
        for sess_pool in (False, True):
            f1 = f0.assign(session="all") if sess_pool else f0
            for pair_pool in (False, True):
                yield f1.assign(pair="POOLED") if pair_pool else f1


def cluster_summary(frame: pd.DataFrame, group_cols: list[str], value_col: str,
                    cluster_col: str = "utc_day") -> pd.DataFrame:
    """Vectorized per-observation mean with a one-way (UTC-day) cluster-robust SE.

    This is the estimand the run-book fixes. Averaging within the block first and
    then across blocks is the trap it exists to avoid: that inverts sign when the
    number of signals in a block is endogenous to the outcome.
    """
    cols = group_cols + [value_col, cluster_col]
    d = frame[cols].dropna(subset=[value_col])
    if d.empty:
        return pd.DataFrame(columns=group_cols + ["n", "clusters", "mean", "se", "t",
                                                  "ci_low", "ci_high"])
    per = (d.groupby(group_cols + [cluster_col], observed=True)[value_col]
           .agg(s="sum", c="count").reset_index())
    per["s2"] = per.s ** 2
    per["sc"] = per.s * per.c
    per["c2"] = per.c.astype(float) ** 2
    g = (per.groupby(group_cols, observed=True)
         .agg(sum_v=("s", "sum"), n=("c", "sum"), clusters=("s", "size"),
              S2=("s2", "sum"), SC=("sc", "sum"), C2=("c2", "sum")).reset_index())
    mean = g.sum_v / g.n
    ss = g.S2 - 2.0 * mean * g.SC + mean ** 2 * g.C2
    scale = np.where(g.clusters > 1, g.clusters / (g.clusters - 1.0), np.nan)
    se = np.sqrt(np.maximum(scale * ss, 0.0)) / g.n
    g["mean"] = mean
    g["se"] = se
    g["t"] = np.where(se > 0, mean / se, np.nan)
    g["ci_low"] = mean - 1.96 * se
    g["ci_high"] = mean + 1.96 * se
    return g[group_cols + ["n", "clusters", "mean", "se", "t", "ci_low", "ci_high"]]


# --------------------------------------------------------------------------- #
# View 2
# --------------------------------------------------------------------------- #

def view2_table(signals: pd.DataFrame, cfg: dict, common_sample: bool, delay: int = 0) -> pd.DataFrame:
    """The tau x k x H conditional reversion surface, per pair/era/session cell.

    ``delay`` selects the entry arm: 0 is the frozen spec, 1 is the shared-endpoint
    control (see ``attach_forward_outcomes``).
    """
    group = CELL_GROUP + ["k"]
    hc = cfg["common_sample_horizon_minutes"]
    keep = ["pair", "era", "session", "tau", "k", "utc_day", "z_signal",
            "cost_pips_base", "cost_R_base"]
    live = ~signals.news_veto.to_numpy()
    out_rows = []
    for h in cfg["horizon_minutes"]:
        m = live & signals[f"complete_d{delay}_{h}"].to_numpy(bool)
        if common_sample:
            m &= signals[f"complete_d{delay}_{hc}"].to_numpy(bool)
        if not m.any():
            continue
        base = signals.loc[m, keep].copy()
        for src, dst in ((f"gross_R_d{delay}_{h}", "gross_R"),
                         (f"gross_pips_d{delay}_{h}", "gross_pips"),
                         (f"touch50_{h}", "touch50"), (f"touch100_{h}", "touch100"),
                         (f"zcross_{h}", "zcross")):
            base[dst] = signals.loc[m, src].to_numpy()
        base["abs_z"] = base.z_signal.abs()
        base["win"] = (base.gross_R > 0).astype(float)

        parts = []
        for f in cell_frames(base):
            stat = cluster_summary(f, group, "gross_R").rename(
                columns={"mean": "gross_R", "se": "gross_R_se", "t": "gross_R_t",
                         "ci_low": "gross_R_ci_low", "ci_high": "gross_R_ci_high"})
            means = (f.groupby(group, observed=True)
                     .agg(gross_pips=("gross_pips", "mean"), touch50=("touch50", "mean"),
                          touch100=("touch100", "mean"), zcross=("zcross", "mean"),
                          cost_pips_base=("cost_pips_base", "mean"),
                          cost_R_base=("cost_R_base", "mean"), abs_z=("abs_z", "mean"),
                          win_rate=("win", "mean")).reset_index())
            parts.append(stat.merge(means, on=group, how="left"))
        o = pd.concat(parts, ignore_index=True)
        o["horizon_minutes"] = h
        out_rows.append(o)
        del base
    tab = pd.concat(out_rows, ignore_index=True)
    tab["net_R_base"] = tab.gross_R - tab.cost_R_base
    tab["breakeven_round_trip_pips"] = tab.gross_pips
    tab["sample"] = "common" if common_sample else "maximal"
    tab["entry_delay_bars"] = delay
    return tab


def shared_endpoint_delta(signals: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Paired per-signal difference between the delayed and undelayed entry arms.

    A ratio of two cell means is unreadable when the denominator is near zero, so the
    comparison is done as a PAIRED difference on the identical set of signals -- the
    same rows, complete under both arms -- with a day-clustered SE. `gross_R_d0` and
    `gross_R_d1` in this table are therefore exactly coverage-matched, which the
    separate per-arm surfaces in view 2 are not.
    """
    k = cfg["bracket_k_signal"]
    live = (~signals.news_veto.to_numpy()) & signals.k.eq(k).to_numpy()
    rows = []
    for h in cfg["horizon_minutes"]:
        m = (live & signals[f"complete_d0_{h}"].to_numpy(bool)
             & signals[f"complete_d1_{h}"].to_numpy(bool))
        if not m.any():
            continue
        base = signals.loc[m, ["pair", "era", "session", "tau", "utc_day"]].copy()
        base["gross_R_d0"] = signals.loc[m, f"gross_R_d0_{h}"].to_numpy()
        base["gross_R_d1"] = signals.loc[m, f"gross_R_d1_{h}"].to_numpy()
        base["delta_R"] = base.gross_R_d1 - base.gross_R_d0
        parts = []
        for f in cell_frames(base):
            stat = cluster_summary(f, CELL_GROUP, "delta_R").rename(
                columns={"mean": "delta_R", "se": "delta_R_se", "t": "delta_R_t",
                         "ci_low": "delta_R_ci_low", "ci_high": "delta_R_ci_high"})
            arms = (f.groupby(CELL_GROUP, observed=True)
                    .agg(gross_R_d0=("gross_R_d0", "mean"),
                         gross_R_d1=("gross_R_d1", "mean")).reset_index())
            parts.append(stat.merge(arms, on=CELL_GROUP, how="left"))
        o = pd.concat(parts, ignore_index=True)
        o["horizon_minutes"] = h
        rows.append(o)
    tab = pd.concat(rows, ignore_index=True)
    # A retained share only means anything when the undelayed arm is meaningfully
    # POSITIVE: over a near-zero or negative base the ratio is noise over noise and
    # its sign is unreadable. Blank it there and read delta_R instead.
    denom = tab.gross_R_d0.where(tab.gross_R_d0 >= 0.01)
    tab["retained_share"] = tab.gross_R_d1 / denom
    tab["k"] = k
    return tab


# --------------------------------------------------------------------------- #
# View 3
# --------------------------------------------------------------------------- #

def view3_brackets(signals: pd.DataFrame, grids: dict, cfg: dict):
    """Gross-R profit factor by grain from the audited bracket simulator.

    Barriers are in VOL units (TP = SL = 1.0 sigma_tau) with RR fixed at 1.0 across
    grains, so a rung cannot win on barrier geometry alone. Two caps are reported: a
    fixed 240-minute cap (equal wall-clock budget, the raw view) and a tau-scaled
    8-bar cap (equal bar budget, the matched view).
    """
    k = cfg["bracket_k_signal"]
    sel = signals.loc[signals.k.eq(k) & ~signals.news_veto]
    trade_parts = []
    for tau in cfg["grain_ladder_minutes"]:
        caps = {"fixed_240m": int(cfg["bracket_fixed_cap_minutes"]),
                f"scaled_{cfg['bracket_scaled_cap_bars']}bar": int(cfg["bracket_scaled_cap_bars"]) * tau}
        for cap_name, cap in caps.items():
            for delay in cfg["entry_delay_bars"]:
                shift = delay * tau
                for pair, grid in grids.items():
                    d = sel.loc[sel.pair.eq(pair) & sel.tau.eq(tau)].sort_values("entry_minute")
                    if d.empty:
                        continue
                    off = grid.offsets(d.entry_minute.to_numpy())
                    good = grid.path_complete_span(off, off + shift + cap)
                    d, off = d.loc[good], off[good] + shift
                    if d.empty:
                        continue
                    sig_pips = d.sigma_pips.to_numpy(float)
                    side = d.side.to_numpy(float)
                    pnl = np.empty(len(d))
                    kind = np.empty(len(d), int)
                    batch = max(200, int(2_000_000 / (cap + 1)))
                    for s in range(0, len(d), batch):
                        e = slice(s, min(s + batch, len(d)))
                        paths = grid.extract_paths(off[e], cap)
                        p, kd = simulate_bracket(paths, side[e],
                                                 cfg["bracket_tp_sigma"] * sig_pips[e],
                                                 cfg["bracket_sl_sigma"] * sig_pips[e], cap,
                                                 slippage_pips=cfg["bracket_stop_slippage_pips"],
                                                 pip=PIP)
                        pnl[e], kind[e] = p, kd
                        del paths
                    t = d[["pair", "tau", "era", "session", "utc_day", "entry_minute",
                           "sigma_pips", "cost_pips_base"]].copy()
                    t["cap_name"] = cap_name
                    t["cap_minutes"] = cap
                    t["entry_delay_bars"] = delay
                    t["gross_pips"] = pnl
                    t["gross_R"] = pnl / sig_pips
                    t["net_R"] = t.gross_R - d.cost_R_base.to_numpy()
                    t["exit_kind"] = kind
                    trade_parts.append(t)
    if not trade_parts:
        return pd.DataFrame(), pd.DataFrame()
    trades = pd.concat(trade_parts, ignore_index=True)

    group = CELL_GROUP + ["cap_name", "entry_delay_bars"]
    parts = []
    for f in cell_frames(trades):
        stat = cluster_summary(f, group, "gross_R").rename(
            columns={"mean": "gross_R", "se": "gross_R_se", "t": "gross_R_t",
                     "ci_low": "gross_R_ci_low", "ci_high": "gross_R_ci_high"})
        aux = (f.assign(_win=(f.gross_R > 0).astype(float),
                        _stop=(f.exit_kind == -1).astype(float),
                        _tp=(f.exit_kind == 1).astype(float),
                        _to=(f.exit_kind == 0).astype(float))
               .groupby(group, observed=True)
               .agg(net_R=("net_R", "mean"), gross_pips=("gross_pips", "mean"),
                    cost_pips_base=("cost_pips_base", "mean"), win_rate=("_win", "mean"),
                    stop_share=("_stop", "mean"), target_share=("_tp", "mean"),
                    timeout_share=("_to", "mean"), cap_minutes=("cap_minutes", "first")).reset_index())
        pf = (f.groupby(group, observed=True).gross_R.apply(lib.profit_factor)
              .reset_index().rename(columns={"gross_R": "profit_factor"}))
        parts.append(stat.merge(aux, on=group, how="left").merge(pf, on=group, how="left"))
    summary = pd.concat(parts, ignore_index=True)
    summary["breakeven_round_trip_pips"] = summary.gross_pips
    return trades, summary


def bracket_sharpes(trades: pd.DataFrame) -> pd.DataFrame:
    """Three Sharpes on a one-position-at-a-time book, per grain (Rule 13).

    Non-overlap is enforced greedily on the timeout window, which is conservative:
    a trade that exits early at a barrier still blocks its full cap.
    """
    rows = []
    for (tau, cap_name, delay), d in trades.groupby(
            ["tau", "cap_name", "entry_delay_bars"], observed=True):
        for era in ("consumed", "holdout"):
            sub = d.loc[d.era.ne("holdout")] if era == "consumed" else d.loc[d.era.eq("holdout")]
            if sub.empty:
                continue
            kept = []
            for _, g in sub.groupby("pair", observed=True):
                g = g.sort_values("entry_minute")
                keep = lib.greedy_non_overlap(g.entry_minute.to_numpy(),
                                              g.entry_minute.to_numpy() + g.cap_minutes.to_numpy())
                kept.append(g.loc[keep])
            book = pd.concat(kept, ignore_index=True)
            days = pd.DatetimeIndex(pd.date_range(book.utc_day.min(), book.utc_day.max(), freq="D"))
            for label, col in (("gross", "gross_R"), ("net", "net_R")):
                s = lib.three_sharpes(book.groupby("utc_day", observed=True)[col].sum(), days)
                s.update({"tau": int(tau), "cap_name": cap_name, "entry_delay_bars": int(delay),
                          "era": era, "basis": label, "trades": int(len(book)),
                          "mean_R": float(book[col].mean())})
                rows.append(s)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Coverage bookkeeping
# --------------------------------------------------------------------------- #

def signal_exclusions(signals: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """How many decisions each coverage rule removes, by grain/era/hour (Rule 9a)."""
    keys = ["pair", "tau", "k", "era", "utc_hour"]
    work = signals[keys + ["news_veto"]].copy()
    for h in cfg["horizon_minutes"]:
        work[f"path_incomplete_{h}"] = ~signals[f"complete_d0_{h}"].to_numpy(bool)
        work[f"path_incomplete_d1_{h}"] = ~signals[f"complete_d1_{h}"].to_numpy(bool)
        work[f"friday_truncated_{h}"] = signals[f"friday_truncated_{h}"].to_numpy(bool)
    agg_spec = {"signals": ("news_veto", "size"), "news_vetoed": ("news_veto", "sum")}
    for h in cfg["horizon_minutes"]:
        agg_spec[f"path_incomplete_{h}"] = (f"path_incomplete_{h}", "sum")
        agg_spec[f"path_incomplete_d1_{h}"] = (f"path_incomplete_d1_{h}", "sum")
        agg_spec[f"friday_truncated_{h}"] = (f"friday_truncated_{h}", "sum")
    return work.groupby(keys, observed=True).agg(**agg_spec).reset_index()


def coverage_defects(dq_grain: pd.DataFrame, excl: pd.DataFrame) -> list[str]:
    """Coverage rules whose effect is NOT enumerated anywhere in the artifacts.

    This gates REPORTING, not cleanliness: an enumerated hole is a finding, an
    unenumerated one is a defect.
    """
    defects = []
    if dq_grain.empty or "z_unavailable" not in dq_grain.columns:
        defects.append("grain-level z availability not enumerated")
    cols = list(getattr(excl, "columns", []))
    if not any(c.startswith("path_incomplete_") for c in cols):
        defects.append("per-horizon path-completeness exclusions not enumerated")
    if "news_vetoed" not in cols:
        defects.append("news blackout removals not enumerated")
    if not any(c.startswith("friday_truncated_") for c in cols):
        defects.append("Friday-flat truncation not enumerated")
    return defects


# --------------------------------------------------------------------------- #
# The pre-committed grain-selection rule (HYP-0002 §6)
# --------------------------------------------------------------------------- #

def apply_grain_rule(vr, v2_common, v2_max, v3, dq_defects, cfg, delay: int = 0) -> dict:
    """Mechanical application of the frozen rule. No result may edit this logic.

    ``delay`` selects which entry arm the rule is applied to. The frozen contract is
    the ``delay = 0`` answer; running the same rule on ``delay = 1`` says whether that
    answer survives the shared-endpoint control, and the two are reported side by side
    rather than one being quietly substituted for the other.
    """
    ladder = [int(t) for t in cfg["grain_ladder_minutes"]]
    dsel = f" and entry_delay_bars == {int(delay)}"
    trace = {"rule": "HYP-0002 §6", "entry_delay_bars": int(delay), "ladder": ladder,
             "unreported_coverage_defects": dq_defects,
             "coverage_gate_pass": len(dq_defects) == 0}

    vr_pool = vr.query("pair == 'POOLED' and era == 'consumed' and session == 'all'").set_index("tau")
    trace["vr_by_tau"] = {t: float(vr_pool.vr.get(t, np.nan)) for t in ladder}
    trace["vr_lm_z_by_tau"] = {t: float(vr_pool.lm_z.get(t, np.nan)) for t in ladder}

    def best_v2(tab):
        q = tab.query("pair == 'POOLED' and era == 'consumed' and session == 'all' and k == 2.0" + dsel)
        best = {}
        for t in ladder:
            sub = q.loc[q.tau.eq(t)].dropna(subset=["gross_R"])
            if sub.empty:
                best[t] = {"gross_R": np.nan, "horizon_minutes": None, "n": 0}
                continue
            r = sub.loc[sub.gross_R.idxmax()]
            best[t] = {"gross_R": float(r.gross_R), "horizon_minutes": int(r.horizon_minutes),
                       "n": int(r.n), "ci_low": float(r.gross_R_ci_low),
                       "ci_high": float(r.gross_R_ci_high)}
        return best

    trace["view2_best_common"] = best_v2(v2_common)
    trace["view2_best_maximal"] = best_v2(v2_max)

    eligible = []
    for t in ladder:
        vr_t = trace["vr_by_tau"].get(t, np.nan)
        g_t = trace["view2_best_common"][t]["gross_R"]
        eligible.append({"tau": t, "vr": vr_t, "view2_gross_R": g_t,
                         "eligible": bool(np.isfinite(vr_t) and vr_t < 1.0
                                          and np.isfinite(g_t) and g_t > 0)})
    trace["eligibility"] = eligible

    live = [e for e in eligible if e["eligible"]]
    if not live:
        trace.update({
            "selected_tau": None, "selected_horizon_minutes": None,
            "outcome": ("NO ELIGIBLE GRAIN: no rung has both VR(tau) < 1 and a positive "
                        "conditional gross mean R at k=2.0. The rule forbids selecting a "
                        "grain by strategy PnL, so Stage A terminates with a documented "
                        "no-selection and Stage B must be re-specified rather than "
                        "silently proceeding.")})
        return trace

    tol_r, tol_vr = cfg["tie_tolerance_R"], cfg["tie_tolerance_vr"]
    by_vr = sorted(live, key=lambda e: e["vr"])
    by_v2 = sorted(live, key=lambda e: -e["view2_gross_R"])
    trace["rank_by_vr"] = [e["tau"] for e in by_vr]
    trace["rank_by_view2"] = [e["tau"] for e in by_v2]

    top_vr = [e["tau"] for e in by_vr if e["vr"] <= by_vr[0]["vr"] + tol_vr]
    top_v2 = [e["tau"] for e in by_v2 if e["view2_gross_R"] >= by_v2[0]["view2_gross_R"] - tol_r]
    shared = [t for t in top_v2 if t in top_vr]
    if shared:
        tau_star = max(shared)
        trace["selection_basis"] = "views 1 and 2 agree within the frozen tie tolerances"
    else:
        tau_star = max(top_v2)
        trace["selection_basis"] = ("views 1 and 2 DISAGREE; rule §6.3 takes tau* from view 2, "
                                    "the conditional view, because VR is unconditional and "
                                    "linear and cannot see extreme-conditional behaviour")

    q = v2_common.query("pair == 'POOLED' and era == 'consumed' and session == 'all' and k == 2.0" + dsel)
    sub = q.loc[q.tau.eq(tau_star)].dropna(subset=["gross_R"]).sort_values("horizon_minutes")
    near = sub.loc[sub.gross_R >= sub.gross_R.max() - tol_r]
    trace["selected_tau"] = int(tau_star)
    trace["selected_horizon_minutes"] = int(near.horizon_minutes.min())
    trace["horizon_candidates"] = sub[["horizon_minutes", "gross_R", "n"]].to_dict("records")

    pf = v3.query("pair == 'POOLED' and era == 'consumed' and session == 'all' and "
                  "cap_name == 'fixed_240m'" + dsel).dropna(subset=["profit_factor"])
    if not pf.empty:
        order = [int(t) for t in pf.sort_values("profit_factor", ascending=False).tau]
        trace["rank_by_view3_pf"] = order
        trace["view3_agrees"] = bool(order and order[0] == int(tau_star))
    trace["outcome"] = f"selected tau*={tau_star} min, H*={trace['selected_horizon_minutes']} min"
    return trace


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def main() -> None:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    overall_rows, hour_rows, weekend_rows = [], [], []
    dq_parts, vol_parts, shape_parts, drift_parts, sig_parts = [], [], [], [], []
    vr_all, acc_pooled, grids = [], {}, {}

    for pair in cfg["pairs"]:
        log(f"{pair}: loading minutes")
        frame, overall, hours, weekend = load_minutes(pair, cfg)
        overall_rows.append(overall)
        hour_rows.append(hours)
        weekend_rows.append(weekend)

        log(f"{pair}: variance ratios (lags 1..{cfg['vr_max_lag_minutes'] - 1})")
        accs = pair_vr_accumulators(frame, cfg)
        vr_all.extend(vr_rows(accs, pair, cfg))
        for group, acc in accs.items():
            acc_pooled[group] = add_accumulators(acc_pooled.get(group), acc)

        grid = lib.MinuteGrid(pd.DatetimeIndex(frame.time), frame.open, frame.high, frame.low)
        grids[pair] = grid

        log(f"{pair}: grain ladder pass")
        got = grain_pass(pair, frame, grid, cfg, high_impact_times(pair))
        dq_parts.append(got["dq"])
        vol_parts.append(got["vol"])
        shape_parts.append(got["shape"])
        drift_parts.append(got["drift"])
        log(f"{pair}: {len(got['signals']):,} signals; attaching forward outcomes")
        sig_parts.append(attach_forward_outcomes(got["signals"], grid, got["z_forward"], cfg))
        del frame, got

    for group, acc in acc_pooled.items():
        vr_all.extend(vr_rows({group: acc}, "POOLED", cfg))
    vr = pd.DataFrame(vr_all)

    signals = pd.concat(sig_parts, ignore_index=True)
    del sig_parts
    log(f"total signals: {len(signals):,} ({int(signals.news_veto.sum()):,} news-vetoed)")
    signals = attach_costs(signals, cfg)

    v2_max_parts, v2_common_parts = [], []
    for delay in cfg["entry_delay_bars"]:
        log(f"view 2: conditional reversion surface (entry delay {delay} bar)")
        v2_max_parts.append(view2_table(signals, cfg, common_sample=False, delay=delay))
        v2_common_parts.append(view2_table(signals, cfg, common_sample=True, delay=delay))
    v2_max = pd.concat(v2_max_parts, ignore_index=True)
    v2_common = pd.concat(v2_common_parts, ignore_index=True)

    log("shared-endpoint control (paired entry-delay difference)")
    sec = shared_endpoint_delta(signals, cfg)

    log("view 3: bounded double barrier by grain")
    v3_trades, v3 = view3_brackets(signals, grids, cfg)
    sharpes = bracket_sharpes(v3_trades) if not v3_trades.empty else pd.DataFrame()
    del grids

    log("coverage bookkeeping")
    dq_overall = pd.DataFrame(overall_rows)
    dq_hours = pd.concat(hour_rows, ignore_index=True)
    dq_grain = pd.concat(dq_parts, ignore_index=True)
    weekend = pd.concat(weekend_rows, ignore_index=True)
    vol_profile = pd.concat(vol_parts, ignore_index=True)
    return_shape = pd.concat(shape_parts, ignore_index=True)
    drift = drift_table(pd.concat(drift_parts, ignore_index=True))
    excl = signal_exclusions(signals, cfg)

    log("applying the pre-committed grain-selection rule")
    defects = coverage_defects(dq_grain, excl)
    verdict = apply_grain_rule(vr, v2_common, v2_max, v3, defects, cfg,
                               delay=cfg["primary_entry_delay_bars"])
    control = apply_grain_rule(vr, v2_common, v2_max, v3, defects, cfg, delay=1)
    verdict["shared_endpoint_control"] = {
        "why": ("open[i] == close[i-1] in this archive, so the delay-0 entry price is the "
                "same number that ends the displacement window; a transient pricing error "
                "there enters the displacement with +1 and the forward return with -1. The "
                "delay-1 arm puts one bar between them and is free of that artifact."),
        "selected_tau": control.get("selected_tau"),
        "selected_horizon_minutes": control.get("selected_horizon_minutes"),
        "view2_best": control.get("view2_best_common"),
        "eligibility": control.get("eligibility"),
        "outcome": control.get("outcome"),
        "agrees_with_frozen_arm": control.get("selected_tau") == verdict.get("selected_tau"),
    }

    log("writing artifacts")
    manifest = {
        "experiment_id": "EXP-0002", "stage": "A",
        "hypothesis": "experiments/hypotheses/HYP-0002.md",
        "config": cfg,
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "inputs": {f"{p}_1m_clean.parquet": {"sha256": sha256(DATA / f"{p}_1m_clean.parquet"),
                                             "bytes": (DATA / f"{p}_1m_clean.parquet").stat().st_size}
                   for p in cfg["pairs"]},
        "imported_from_exploration_1": ["_bracket_engine.simulate_bracket",
                                        "_cost_model.round_trip_pips", "_rsi_stop_engine.PIP",
                                        "_run_rsi_axis6_calendar.high_impact_times"],
        "signals_total": int(len(signals)),
        "signals_news_vetoed": int(signals.news_veto.sum()),
        "bracket_trades": int(len(v3_trades)),
    }
    (ARTIFACT / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (ARTIFACT / "verdict.json").write_text(json.dumps(verdict, indent=2, default=str), encoding="utf-8")

    for name, obj in (("variance_ratio", vr), ("view2_surface_maximal", v2_max),
                      ("view2_surface_common", v2_common), ("view3_bracket_summary", v3),
                      ("view3_sharpes", sharpes), ("data_quality_overall", dq_overall),
                      ("data_quality_by_hour", dq_hours), ("data_quality_by_grain", dq_grain),
                      ("signal_exclusions", excl), ("vol_profile", vol_profile),
                      ("return_shape", return_shape), ("naive_drift", drift),
                      ("weekend_gaps", weekend), ("shared_endpoint_control", sec)):
        obj.to_csv(ARTIFACT / f"{name}.csv", index=False)
    keep = [c for c in signals.columns if not c.startswith(("touch", "zcross", "friday_"))]
    signals[keep].to_parquet(ARTIFACT / "signals.parquet", index=False)

    write_data_quality(cfg, dq_overall, dq_hours, dq_grain, excl, weekend, defects)
    write_characterization(cfg, vr, v2_max, v2_common, v3, sharpes, vol_profile,
                           return_shape, drift, excl, verdict, sec)
    log(f"done: {verdict['outcome']}")


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #

def write_data_quality(cfg, dq_overall, dq_hours, dq_grain, excl, weekend, defects) -> None:
    tt = lib.to_text_table
    grain_tot = (dq_grain.groupby(["pair", "tau", "era"], observed=True)
                 .agg(eligible_bars=("eligible_bars", "sum"),
                      incomplete_bins=("incomplete_bins", "sum"),
                      sigma_underpopulated=("sigma_underpopulated", "sum"),
                      z_unavailable=("z_unavailable", "sum"),
                      window_bars=("window_bars", "first"),
                      min_periods=("min_periods", "first")).reset_index())
    grain_tot["z_available_share"] = 1 - grain_tot.z_unavailable / grain_tot.eligible_bars.replace(0, np.nan)

    worst = (dq_grain.assign(share=dq_grain.z_unavailable / dq_grain.eligible_bars.replace(0, np.nan))
             .sort_values("share", ascending=False).head(25)
             [["pair", "tau", "era", "utc_hour", "eligible_bars", "z_unavailable", "share"]])

    hs = cfg["horizon_minutes"]
    ex_tot = excl.groupby(["pair", "tau", "era"], observed=True).agg(
        signals=("signals", "sum"), news_vetoed=("news_vetoed", "sum"),
        **{f"path_incomplete_{h}": (f"path_incomplete_{h}", "sum") for h in hs},
        **{f"friday_truncated_{h}": (f"friday_truncated_{h}", "sum") for h in hs}).reset_index()

    hc = cfg["common_sample_horizon_minutes"]
    nz = (excl.loc[excl.pair.eq("NZDUSD")].groupby(["era", "utc_hour"], observed=True)
          .agg(signals=("signals", "sum"),
               path_incomplete=(f"path_incomplete_{hc}", "sum")).reset_index())
    nz["excluded_share"] = nz.path_incomplete / nz.signals.replace(0, np.nan)
    nz = nz.sort_values("excluded_share", ascending=False).head(20)

    hourly = (excl.groupby(["tau", "utc_hour"], observed=True)
              .agg(signals=("signals", "sum"),
                   path_incomplete=(f"path_incomplete_{hc}", "sum")).reset_index())
    hourly["excluded_share"] = hourly.path_incomplete / hourly.signals.replace(0, np.nan)
    hourly = (hourly.pivot(index="utc_hour", columns="tau", values="excluded_share")
              .reset_index())
    hourly.columns = ["utc_hour"] + [f"tau_{c}" for c in hourly.columns[1:]]

    wk = weekend.loc[weekend.gap_minutes.ge(120)]
    wk_desc = (wk.groupby(["pair", "era"], observed=True)
               .jump_pips.describe(percentiles=[0.05, 0.5, 0.95]).reset_index())

    gate = ("none — every coverage rule below writes its own per-cell exclusion count"
            if not defects else "; ".join(defects))
    text = f"""# Data Quality Report — Rule 9a (Stage A / EXP-0002)

Written by `python -u forex/exploration_4/_run_stage_a.py` **before** any Stage-A
statistic was interpreted. This supersedes the EXP-0001 version of this file for the
multi-grain work; the EXP-0001 snapshot is preserved at
`artifacts/runs/EXP-0001/DATA_QUALITY.md`.

Source fields are **midpoint OHLC only**: there is no `volume` column and no bid/ask.
Every cost figure in this project is therefore a modelling assumption and a
breakeven-pip curve, never a measured spread.

## Reporting gate

Unenumerated coverage rules: **{gate}**.

A coverage hole is a *finding* and is reported. A coverage hole that is not counted
is a *defect* and fails this gate.

## 1. Source integrity

{tt(dq_overall, 0)}

## 2. Grain construction, per pair × grain × era

A τ-bar is tradable only when **all τ source minutes exist**; incomplete bars are
nulled, never forward-filled. `sigma` uses a **fixed {cfg['sigma_window_minutes']:,}-minute
(20-day) time window** at every rung — `window_bars` × τ = {cfg['sigma_window_minutes']:,}
for all τ — with a **fractional** `min_periods` floor of
{cfg['sigma_min_fraction']}·window. A strict `min_periods == window` floor is what
turns one missing bar into a silent, time-of-day-dependent deletion of decisions; it
is deliberately not used.

{tt(grain_tot, 4)}

### Worst 25 (pair × grain × era × UTC-hour) cells by unavailable-z share

{tt(worst, 4)}

## 3. What each coverage rule removes, per pair × grain × era

`signals` counts first-crossing events at all four `k` thresholds pooled.
`news_vetoed` is the standing ±{cfg['news_blackout_minutes']}-minute high-impact
blackout. `path_incomplete_H` is the strict requirement that every one-minute bar in
`[entry, entry+H]` exists. `friday_truncated_H` counts entries whose H-window would
run past the Friday 16:55 New York flat rule.

{tt(ex_tot, 0)}

### Where the long-horizon path rule bites, by UTC hour

The `H = {hc}` completeness rule removes a **third to two-fifths** of all signals, and
it does not remove them evenly. Any 8-hour window that spans the weekend, or the
archive's daily ~21:00–22:00 UTC rollover hole, is excluded. That matters here because
the conditional reversion in `MARKET_CHARACTERIZATION.md` §2 concentrates in exactly
those thin hours, so **the common (H = {hc}-complete) sample is biased away from the
hours where the effect is largest**. Both the common and the maximal-sample surfaces
are reported for that reason; read them together.

Share of signals excluded at H = {hc}, by UTC hour and grain:

{tt(hourly, 3)}

## 4. NZDUSD-specific exclusion (known late-era 18:00–19:00 UTC holes)

NZD's coverage limits NZD-specific claims. It is enumerated rather than summarized —
worst 20 cells by excluded share at H = {hc}:

{tt(nz, 4)}

## 5. Weekend / long-gap jump distribution (gaps ≥ 120 minutes)

The weekend-flat constraint exists because these jumps are unhedgeable. Jump is
`(first open after the gap − last close before it)` in pips.

{tt(wk_desc, 3)}

## 6. Known limitations carried forward

- The exact 17:00 New York rollover bar is unavailable in this archive; 16:55 is the
  last attainable open, and the Friday-flat minute is set there.
- Midpoint-only data means the spread is unmeasured; all "net" figures are
  assumption-driven and are always shown beside gross and a breakeven pip.
- Session labels use each venue's own timezone with real DST, not fixed UTC blocks.
"""
    (REPORTS / "DATA_QUALITY.md").write_text(text, encoding="utf-8")
    (ARTIFACT / "DATA_QUALITY.md").write_text(text, encoding="utf-8")


def write_characterization(cfg, vr, v2_max, v2_common, v3, sharpes, vol_profile,
                           return_shape, drift, excl, verdict, sec) -> None:
    tt = lib.to_text_table
    d0 = f"entry_delay_bars == {cfg['primary_entry_delay_bars']}"
    q = "pair == 'POOLED' and era == 'consumed' and session == 'all' and " + d0

    vr_pool = vr.query("pair == 'POOLED' and era == 'consumed'")[
        ["session", "tau", "vr", "lm_z", "n_returns", "min_lag_pairs"]].sort_values(["session", "tau"])
    vr_pair = vr.query("era == 'consumed' and session == 'all' and pair != 'POOLED'")[
        ["pair", "tau", "vr", "lm_z", "n_returns"]].sort_values(["pair", "tau"])
    vr_hold = vr.query("pair == 'POOLED' and era == 'holdout' and session == 'all'")[
        ["tau", "vr", "lm_z", "n_returns"]].sort_values("tau")

    surf_c = v2_common.query(q + " and k == 2.0")[
        ["tau", "horizon_minutes", "n", "gross_R", "gross_R_ci_low", "gross_R_ci_high",
         "gross_pips", "cost_pips_base", "net_R_base", "win_rate", "touch100", "zcross"]
    ].sort_values(["tau", "horizon_minutes"])
    surf_m = v2_max.query(q + " and k == 2.0")[
        ["tau", "horizon_minutes", "n", "gross_R", "gross_pips", "net_R_base"]
    ].sort_values(["tau", "horizon_minutes"])
    kcurve = v2_common.query(q)[
        ["tau", "k", "horizon_minutes", "n", "gross_R", "gross_R_t", "gross_pips",
         "cost_pips_base", "touch100"]].sort_values(["tau", "k", "horizon_minutes"])
    by_sess = v2_common.query("pair == 'POOLED' and era == 'consumed' and k == 2.0 and " + d0)[
        ["session", "tau", "horizon_minutes", "n", "gross_R", "gross_R_t"]].sort_values(
        ["session", "tau", "horizon_minutes"])
    by_pair = v2_common.query("era == 'consumed' and session == 'all' and k == 2.0 and pair != 'POOLED' and " + d0)[
        ["pair", "tau", "horizon_minutes", "n", "gross_R", "gross_R_t"]].sort_values(
        ["pair", "tau", "horizon_minutes"])
    hold = v2_common.query("pair == 'POOLED' and era == 'holdout' and session == 'all' and k == 2.0 and " + d0)[
        ["tau", "horizon_minutes", "n", "gross_R", "gross_R_ci_low", "gross_R_ci_high", "net_R_base"]
    ].sort_values(["tau", "horizon_minutes"])

    v3_pool = v3.query(q)[["tau", "cap_name", "cap_minutes", "n", "profit_factor", "gross_R",
                           "gross_R_t", "net_R", "win_rate", "stop_share", "target_share",
                           "timeout_share", "gross_pips"]].sort_values(["cap_name", "tau"])
    sh = (sharpes.query("era == 'consumed' and " + d0)[
        ["tau", "cap_name", "basis", "trades", "mean_R", "sharpe_zero_day",
         "sharpe_trade_days", "sharpe_vol_targeted"]].sort_values(["cap_name", "tau", "basis"])
        if len(sharpes) else pd.DataFrame())

    vol_p = (vol_profile.query("era != 'holdout' and tau == 60")
             .groupby("utc_hour", observed=True)
             .agg(median_sigma_pips=("median_sigma_pips", "median"),
                  bars=("bars", "sum")).reset_index())
    shape = (return_shape.query("era != 'holdout'").groupby("tau", observed=True)
             .agg(n=("n", "sum"), ret_skew=("ret_skew", "mean"),
                  excess_kurtosis=("ret_excess_kurtosis", "mean"),
                  share_abs_z_gt2=("share_abs_z_gt2", "mean"),
                  share_abs_z_gt3=("share_abs_z_gt3", "mean"),
                  share_abs_z_gt4=("share_abs_z_gt4", "mean")).reset_index())
    dr = drift.query("pair == 'POOLED' and era == 'consumed'")[
        ["session", "horizon_minutes", "n", "always_long_pips", "long_ci_low", "long_ci_high"]
    ].sort_values(["session", "horizon_minutes"])
    dcmp = sec.query("pair == 'POOLED' and era == 'consumed' and session == 'all'")[
        ["tau", "horizon_minutes", "n", "gross_R_d0", "gross_R_d1", "retained_share",
         "delta_R", "delta_R_t", "delta_R_ci_low", "delta_R_ci_high"]
    ].sort_values(["tau", "horizon_minutes"])
    v3d = v3.query("pair == 'POOLED' and era == 'consumed' and session == 'all' and "
                   "cap_name == 'fixed_240m'")[
        ["tau", "entry_delay_bars", "n", "profit_factor", "gross_R", "gross_R_t"]
    ].sort_values(["tau", "entry_delay_bars"])

    fri = excl.groupby("tau", observed=True).agg(
        signals=("signals", "sum"),
        friday_truncated_240=("friday_truncated_240", "sum"),
        friday_truncated_480=("friday_truncated_480", "sum")).reset_index()

    sel_tau, sel_h = verdict.get("selected_tau"), verdict.get("selected_horizon_minutes")
    headline = (f"**τ\\* = {sel_tau} min, H\\* = {sel_h} min**" if sel_tau
                else "**No grain selected — see §7.**")
    trace = {k: v for k, v in verdict.items() if k != "horizon_candidates"}

    text = f"""# Market Characterization — Stage A (EXP-0002)

> **SUPERSEDED IN PART (2026-08-08) — read `SAME_SLOT_ADDENDUM.md` (EXP-0003) first.**
> The `|z|` threshold in this report is measured against an **all-hours** σ, which fires
> on 0.96% of decisions at 04:00 UTC and 10.11% at 14:00 (selection-rate CV 0.707) — the
> threshold is acting as a time-of-day selector.
> **§2's session breakdown is RETRACTED:** under a same-slot σ at matched trade count the
> `off`/`asia`-vs-`london` separation no longer clears its pre-committed bar. Session
> differences are **not** established.
> **What stands:** view 1 (VR, strategy-free), the shared-endpoint control, the grain
> choice τ\\* = 5 / H\\* = 240 (re-confirmed and sharpened under the same-slot arm), and the
> cost arithmetic. Read every §2 session number through the addendum.

Contract: `experiments/hypotheses/HYP-0002.md` (frozen before this run) and
`RUNBOOK.md` §STAGE A. Reproduce with `python -u forex/exploration_4/_run_stage_a.py`.

**This report describes the market. It commits no strategy and issues no GO/NO-GO.**
Its only decision is the decision grain and holding-horizon cap that Stage B will
freeze its reference book at, taken by the pre-committed rule in HYP-0002 §6 and
applied mechanically in `apply_grain_rule`.

**Honest label (Stage-A repair F1):** that rule maximizes the z-fade's **gross**
strategy return over horizons and ranks grains by it, so **τ\\* = 5 / H\\* = 240 are
consumed-history, GROSS-P&L-selected candidates** — not net-tuned, but not "untuned"
and not confirmed. The CI on the selected maximum is not selection-adjusted, so "only
rung whose CI excludes zero" is descriptive, not confirmatory. 2024+ was opened once
(§8) with a tau=5 CI that included zero: it did not confirm the choice and is no longer
a clean holdout; only future data can now serve as one.

Grain outcome: {headline}

Coverage gate: `reports/DATA_QUALITY.md`. Every table below prints its **n**. The
sealed 2024+ holdout is kept out of every gross statistic and the grain selection and
is opened once, in §8. **Cost caveat (F2):** the modelled-cost `vol_ratio` denominator
now uses the **consumed-era** per-(pair,tau) σ median only; the earlier build computed
it over the full table including 2024+, so pre-repair net/cost columns had a small
holdout leak (medians 2–7% lower). Gross statistics and the grain selection never used
the cost column and are unaffected.

---

## 1. View 1 — Variance ratio `VR(τ)` (strategy-free ambient map)

`VR(τ) = Var(r_τ)/(τ·Var(r_1)) = 1 + 2·Σ(1−k/τ)·ρ(k)` on 1-minute log returns.
`VR < 1` = reversion, `= 1` = random walk, `> 1` = trend. `lm_z` is the
**Lo–MacKinlay heteroskedasticity-robust** statistic: FX volatility clusters hard,
and that inflates the estimator's standard error without moving its point estimate,
so homoskedastic inference would print a significant "edge" on a random walk.

VR is **scale-invariant to the volatility level** — a compression regime cannot move
it; only serial dependence can. It is also **unconditional and linear**, which is
exactly why it cannot settle the grain question alone: it measures the average move's
serial dependence, not reversion from an extreme to an anchor. That is view 2.

Autocovariance pairs are counted only when both one-minute returns are valid and the
timestamps are exactly `k` minutes apart, so no gap is ever read as a serial link.
`min_lag_pairs` is the smallest per-lag pair count entering that τ.

### Pooled across pairs, consumed history, by session

{tt(vr_pool, 4)}

### Per pair (all sessions), consumed history

{tt(vr_pair, 4)}

---

## 2. View 2 — Conditional extreme→anchor reversion (the entry-information view)

Fade a first crossing of `|z_τ| ≥ k`, enter at the next τ-bar open, hold H minutes.
`gross_R` is the per-signal mean in **R units where R = σ_τ at the signal**, so a
signal fired at `|z| = 2` that retraces exactly to its anchor earns +2R. The estimand
is the **per-signal mean with a UTC-day cluster-robust SE** — never a day-averaged R,
which inverts sign when signal count is endogenous to the outcome.

`touch100` is the share of signals whose path trades back to the **anchor** (the close
at the start of the displacement window) within H — a touch, not a fill. `zcross` is
the share where the rolling `z_τ` crosses zero within H, which is how Stage B's
proposed exit is defined; the two differ and Stage B needs to know by how much.

`cost_pips_base` is the modelled base-scenario round trip. Because the spread is
unmeasured, read `gross_pips` as the **breakeven round-trip pip**: the entry is
viable only if the true round trip is below it.

### Surface at k = 2.0 — common sample (signals complete at H = {cfg['common_sample_horizon_minutes']})

{tt(surf_c, 4)}

### Same surface on each horizon's own maximal sample (coverage cross-check)

If the shape differs from the table above, the shape is a coverage artifact.

{tt(surf_m, 4)}

### Threshold curve `E[R | |z| ≥ k]` (common sample, pooled)

{tt(kcurve, 4)}

### By session (k = 2.0, common sample, pooled pairs)

{tt(by_sess, 4)}

### By pair (k = 2.0, common sample) — four USD majors are ≈2 effective independent

{tt(by_pair, 4)}

### Shared-endpoint control: what survives one bar of separation

In this archive `open[i] == close[i-1]` for **99.99998%** of contiguous minutes, so
the delay-0 entry price is *the same number* that ends the displacement window. A
transient pricing error at that instant enters the displacement with `+1` and the
forward return with `−1`, manufacturing reversion that no cost model can remove.
`entry_delay_bars = 1` waits one further bar, putting real separation between the two,
and is screened on the **same span** so the comparison is coverage-matched.

The comparison below is a **paired** difference on the identical set of signals —
the same rows, complete under both arms — so it is exactly coverage-matched.
`delta_R = gross_R(delay 1) − gross_R(delay 0)` carries a day-clustered CI;
`retained_share` is the ratio, shown only where the undelayed arm is above +0.01 R —
over a near-zero or negative base a ratio is noise over noise and its sign is
unreadable, so read `delta_R` there instead. A share near 1 means the measured
reversion is a property of the market; a share near 0 means it was the shared
endpoint. **Read this table before believing any number in §2.**

{tt(dcmp, 4)}

---

## 3. View 3 — Gross-R profit factor by grain (strategy-level corroboration)

Bounded double barrier from the audited `_bracket_engine.simulate_bracket`: adverse
intrabar tiebreak when one minute touches both barriers, gap-through fills at the
first tradable price, {cfg['bracket_stop_slippage_pips']} pip adverse stop slippage.
**Barriers are in vol units (TP = SL = {cfg['bracket_tp_sigma']}σ_τ) and RR is fixed
at 1.0 across grains**, so no rung can win on barrier geometry alone — prior RSI work
held RR constant but not vol-unit barriers, and part of its 15-minute advantage was
exactly that.

Two caps: `fixed_240m` gives every grain the same wall-clock budget (the raw view);
`scaled_8bar` gives every grain the same bar budget (the matched view). A conclusion
that holds in only one of them is a statement about the cap, not the grain.

{tt(v3_pool, 4)}

### Same book under the shared-endpoint control (fixed 240m cap)

{tt(v3d, 4)}

### Three Sharpes on a one-position-at-a-time book (consumed history)

Zero-day charges the book for days it sits out; trade-days-only does not; the
vol-targeted figure depends on the leverage clip and hence on account size. They are
reported together because they routinely disagree.

{tt(sh, 3)}

---

## 4. Realized-volatility profile by slot (description)

Median σ over the 60-minute grain, pooled pairs, consumed history, by UTC hour.

{tt(vol_p, 3)}

## 5. Return-distribution shape across the ladder (description)

Pooled pairs, consumed history. Fat tails at the fine grains are what make a fixed
`|z|` threshold fire more often than a Gaussian would suggest.

{tt(shape, 5)}

## 6. Naive always-long drift (so no later overlay is credited with it)

Mean pips from holding long for H minutes, sampled at every complete hourly bar open,
with a day-clustered CI. The always-short drift is the exact negative of these numbers
by construction, so only the long side is tabulated.

{tt(dr, 4)}

### Friday-flat truncation counts

{tt(fri, 0)}

---

## 7. Grain selection — the pre-committed rule, applied mechanically

The rule was frozen in `experiments/hypotheses/HYP-0002.md` §6 before this run and is
executed in code (`apply_grain_rule`), not narrated. Full trace:
`artifacts/runs/EXP-0002/verdict.json`.

```json
{json.dumps(trace, indent=2, default=str)}
```

**Outcome: {verdict.get('outcome')}**

## 8. Sealed holdout (2024+) — opened once, descriptive only

Nothing below influenced the grain choice above.

### VR(τ), pooled, holdout

{tt(vr_hold, 4)}

### View-2 surface at k = 2.0, pooled, holdout (common sample)

{tt(hold, 4)}

---

## 9. Exit gate

The Stage-A gate asks that views 1–3 agree on a grain (or that the disagreement is
understood and documented), that the selection rule resolves to a specific
(decision grain, holding-horizon cap), and that no coverage defect at that grain is
unreported. §7 records which of those hold; `reports/DATA_QUALITY.md` records the
coverage position. Read the two together before starting Stage B.
"""
    (REPORTS / "MARKET_CHARACTERIZATION.md").write_text(text, encoding="utf-8")
    (ARTIFACT / "MARKET_CHARACTERIZATION.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
