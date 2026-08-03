"""Causal intraday CBOE VIX state, joined to the project's 30-minute decision clock.

Backlog item 17 recorded "trade volatility as the object itself" as DATA-BLOCKED:

    "No options data exists in this workspace, and there is no good intraday implied
     proxy from futures alone."

`futures/data/vix/` unblocks it. Ten TradingView `CBOE_DLY_VIX, 15` exports tile
2011-08-01 .. 2026-07-17 contiguously with no overlap, giving 15-minute intraday
implied volatility across the whole NQ/ES sample.

Why this is not just another volatility proxy
---------------------------------------------
Every feature the project has tested -- the two-input core, EXP-0011's multi-horizon
set, EXP-0016's decorrelated six and its redundant-level control -- is a function of
PAST PRICE, and finding P showed they all converge on the same level-IC ceiling of
+0.009..+0.011. VIX is the first input that is not past price: it is the option
market's FORWARD-LOOKING price of volatility, so it can contain volatility that has
been SCHEDULED but has not happened yet (backlog item 13's target).

The quantity that expresses that, and which cannot be built from past price at all,
is the intraday variance risk premium

    vrp_log = log(vix_fwd30_bp / past_rv30_bp)

i.e. what options charge for the next 30 minutes against what the last 30 minutes
actually delivered.

Causality (rule 7)
------------------
A TradingView bar stamped `T` covers `[T, T+15m)`, so its close is only observable at
`T + 15m`. The project's decision at RTH minute `mfo` uses the one-minute bar stamped
`ts_utc`, which closes at `ts_utc + 1m`; that is the information cutoff, and the
forward target starts at the next minute's open. So a VIX bar is admissible iff

    vix_ts_utc + 15m <= ts_utc + 1m

The clocks align exactly: decision cutoffs fall at :00 and :30, and the VIX bars
stamped :45 and :15 close precisely there. `attach_vix(..., lag_bars=1)` drops back a
further full 15 minutes as the conservative robustness arm -- if a result survives
that, the join boundary cannot be what produced it.

Every joined row carries `vix_stale_min`, the age of the quote in minutes. Nothing is
forward-filled silently: the staleness is a reported rule-9a quantity, because
`claude_exploration_1` found a stale-price control to be load-bearing on a
forward-filled synthetic index.

Scope limits, stated up front
-----------------------------
  * VIX is an **SPX** measure. It is the native implied volatility for ES and only a
    proxy for NQ, whose own index is VXN. The mechanism therefore predicts ES >= NQ,
    which is a falsifiable cross-market asymmetry rather than the usual "both markets
    agree" robustness check.
  * VIX is 30-**day** implied volatility. Mapping it onto a 30-**minute** horizon
    inherits the entire intraday volatility seasonal, so a fixed threshold on any
    VIX-vs-realised ratio is a time-of-day selector in exactly the sense of finding I.
    Use the same-slot z-scores (`*_slot_z`) for anything threshold-like.
  * Only spot VIX exists here -- no VIX9D/VIX3M, so no implied term structure.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

VIX_DIR = Path(__file__).resolve().parents[3] / "data" / "vix"
BAR_MINUTES = 15

#: Minutes of RTH trading per year used to rescale annualised VIX onto the 30-minute
#: decision horizon: 252 sessions x 390 RTH minutes. The constant is a pure scale, so
#: it cannot change any rank statistic or any tree model; it exists so that
#: `vix_fwd30_bp` is directly comparable in basis points with `fwd_rv_bp` and so that
#: `vrp_log == 0` means "options price the next 30 minutes exactly as the last 30
#: minutes delivered".
MINUTES_PER_YEAR = 252 * 390

RTH_START, RTH_END = 570, 960


def _read_tiles() -> pd.DataFrame:
    files = sorted(VIX_DIR.glob("CBOE_DLY_VIX*.csv"))
    if not files:
        raise FileNotFoundError(f"no VIX exports under {VIX_DIR}")
    parts = []
    for path in files:
        tile = pd.read_csv(path, usecols=["time", "open", "high", "low", "close"])
        tile["ts_utc"] = pd.to_datetime(tile["time"], utc=True)
        tile["tile"] = path.stem.split("_")[-1]
        parts.append(tile.drop(columns=["time"]))
    return pd.concat(parts, ignore_index=True)


def load_vix_15m() -> tuple[pd.DataFrame, dict]:
    """The 15-minute VIX panel with a rule-9a quality report.

    Returns one row per bar with `ts_utc` (bar OPEN) and `avail_utc` (bar CLOSE, the
    first instant the value is observable). Sorted, de-duplicated and asserted
    monotonic, because the ten source tiles are separate manual exports.
    """
    raw = _read_tiles()
    duplicate_ts = int(raw.ts_utc.duplicated().sum())
    v = raw.sort_values("ts_utc").drop_duplicates("ts_utc").reset_index(drop=True)
    assert v.ts_utc.is_monotonic_increasing

    et = v.ts_utc.dt.tz_convert("America/New_York")
    v["date"] = et.dt.tz_localize(None).dt.normalize()
    v["tod"] = et.dt.hour * 60 + et.dt.minute
    v["avail_utc"] = v.ts_utc + pd.Timedelta(minutes=BAR_MINUTES)

    # A frozen print (open==high==low==close) is normal for the 16:15 stub and for very
    # quiet minutes; a RUN of identical closes would mean a dead feed. Both are counted
    # rather than assumed away.
    frozen_bar = (v.open == v.close) & (v.high == v.low)
    repeat_close = v.close.eq(v.close.shift(1)) & v.date.eq(v.date.shift(1))

    in_rth = v.tod.between(RTH_START, RTH_END)
    per_session = v.loc[in_rth].groupby("date").size()

    quality = {
        "files": len(sorted(VIX_DIR.glob("CBOE_DLY_VIX*.csv"))),
        "raw_rows": len(raw), "rows": len(v), "duplicate_ts": duplicate_ts,
        "first": v.ts_utc.min(), "last": v.ts_utc.max(),
        "sessions": int(v.date.nunique()),
        "rth_rows": int(in_rth.sum()),
        "median_bars_per_session": float(per_session.median()),
        "short_sessions": int((per_session < 27).sum()),
        "frozen_bars": int(frozen_bar.sum()),
        "repeat_close_bars": int(repeat_close.sum()),
        "nonpositive": int((v.close <= 0).sum()),
        "min_close": float(v.close.min()), "max_close": float(v.close.max()),
    }
    return v, quality


def vix_to_bp(vix: pd.Series | np.ndarray, horizon_min: int = 30) -> np.ndarray:
    """Annualised VIX points -> expected |move| over `horizon_min` RTH minutes, in bp."""
    return 1e4 * (np.asarray(vix, dtype=float) / 100.0) * np.sqrt(
        horizon_min / MINUTES_PER_YEAR)


def _session_anchors(v: pd.DataFrame) -> pd.DataFrame:
    """Per-session VIX anchors: the first observable RTH close and the final close.

    `open_close` is the close of the 09:30 bar, observable at 09:45 and therefore known
    before the first decision cutoff at 10:00. `prev_close` is the PRIOR session's last
    close, so `overnight_chg` is complete at the open (rule 7).
    """
    rth = v.loc[v.tod.between(RTH_START, RTH_END)]
    anchors = rth.groupby("date").agg(open_close=("close", "first"),
                                      day_close=("close", "last"))
    anchors["prev_close"] = anchors.day_close.shift(1)
    anchors["overnight_chg"] = np.log(anchors.open_close / anchors.prev_close)
    return anchors


def attach_vix(d: pd.DataFrame, *, lag_bars: int = 0,
               tolerance_min: int = 45) -> tuple[pd.DataFrame, dict]:
    """Join causal VIX state onto a decision frame from `forward_vol.build_decision_frame`.

    `d` must carry `ts_utc` (the decision bar's OPEN), `sdate`, `mfo` and, for the
    variance-risk-premium features, `past_rv30_bp`.

    `lag_bars` drops back that many extra 15-minute bars before the cutoff. `0` uses
    the freshest legitimately observable quote; `1` is the conservative arm.

    `tolerance_min` caps how stale a quote may be. Rows beyond it are left NaN rather
    than forward-filled from an arbitrary distance, and `vix_stale_min` reports the age
    of every quote that was used.
    """
    v, vq = load_vix_15m()
    anchors = _session_anchors(v)

    right = v[["avail_utc", "close", "high", "low"]].rename(
        columns={"close": "vix", "high": "vix_bar_high", "low": "vix_bar_low"}).copy()
    right["vix_prev"] = right.vix.shift(1)
    right["vix_prev4"] = right.vix.shift(4)
    # Shifting `avail_utc` FORWARD by `lag_bars` bars makes each row look older than it
    # is, so the as-of join lands on an earlier quote. The value carried is still the
    # value of the bar that closed at the original `avail_utc`.
    right["join_ts"] = right.avail_utc + pd.Timedelta(minutes=BAR_MINUTES * lag_bars)
    right = right.sort_values("join_ts")

    left = d.copy()
    left["cutoff_utc"] = left.ts_utc + pd.Timedelta(minutes=1)
    left = left.sort_values("cutoff_utc")

    # The parquet stores microsecond-resolution timestamps while `pd.to_datetime` on the
    # CSV yields nanoseconds; `merge_asof` refuses to join across the two. Both are UTC
    # instants, so aligning the unit is lossless.
    left["cutoff_utc"] = left.cutoff_utc.astype("datetime64[ns, UTC]")
    for col in ("join_ts", "avail_utc"):
        right[col] = right[col].astype("datetime64[ns, UTC]")

    joined = pd.merge_asof(
        left, right, left_on="cutoff_utc", right_on="join_ts", direction="backward",
        tolerance=pd.Timedelta(minutes=tolerance_min))

    # ---- the causality invariant, asserted rather than asserted-in-prose (rule 7) ---- #
    used = joined.avail_utc.notna()
    assert bool((joined.loc[used, "avail_utc"]
                 <= joined.loc[used, "cutoff_utc"]).all()), \
        "a VIX bar was joined that had not closed by the decision cutoff"

    joined["vix_stale_min"] = (
        joined.cutoff_utc - joined.avail_utc).dt.total_seconds() / 60.0

    # ---- features -------------------------------------------------------------------- #
    joined["vix_fwd30_bp"] = vix_to_bp(joined.vix)
    # 15- and 60-minute VIX changes. Reported with their correlation against the market's
    # own trailing return, because intraday VIX moves nearly mechanically against SPX and
    # a "VIX change" feature can be a restatement of past price rather than new state.
    joined["vix_chg_15m"] = np.log(joined.vix / joined.vix_prev)
    joined["vix_chg_60m"] = np.log(joined.vix / joined.vix_prev4)
    joined["vix_intraday_range"] = np.log(joined.vix_bar_high / joined.vix_bar_low)

    joined["vix_open_close"] = joined.sdate.map(anchors.open_close)
    joined["vix_overnight_chg"] = joined.sdate.map(anchors.overnight_chg)
    joined["vix_chg_since_open"] = np.log(joined.vix / joined.vix_open_close)

    # THE feature that no past-price set can contain: implied vs realised for the same
    # 30-minute horizon. NaN where realised is zero rather than clipped to a sentinel.
    if "past_rv30_bp" in joined:
        past = joined.past_rv30_bp.where(joined.past_rv30_bp > 0)
        joined["vrp_log"] = np.log(joined.vix_fwd30_bp / past)

    joined = joined.sort_values(["sdate", "mfo"]).reset_index(drop=True)

    # Same-slot z-scores. The 30-day -> 30-minute mapping carries the whole intraday
    # volatility seasonal, so the raw ratio is partly a clock (finding I). These are the
    # forms to use for anything threshold-like.
    for col in ["vix", "vrp_log", "vix_chg_since_open"]:
        if col in joined:
            joined[f"{col}_slot_z"] = _slot_z(joined, col)

    quality = dict(vq)
    quality.update({
        "lag_bars": lag_bars, "tolerance_min": tolerance_min,
        "decision_rows": len(joined),
        "joined": int(used.sum()), "unjoined": int((~used).sum()),
        "join_rate": float(used.mean()),
        "stale_median_min": float(joined.vix_stale_min.median(skipna=True)),
        "stale_p99_min": float(joined.vix_stale_min.quantile(.99)),
        "stale_gt_20min": int((joined.vix_stale_min > 20).sum()),
    })
    return joined, quality


def _slot_z(frame: pd.DataFrame, column: str, lookback: int = 90,
            min_obs: int = 60) -> pd.Series:
    """Trailing same-slot z-score, causal (`shift(1)` before the window).

    Identical construction to `forward_vol._rolling_slot_z` and to the canonical regime
    label adopted by EXP-0009 (`analysis.causal_slot_stats`).
    """
    grouped = frame.groupby("mfo")[column]
    mean = grouped.transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).mean())
    std = grouped.transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).std(ddof=1))
    return (frame[column] - mean) / std.replace(0, np.nan)


#: Feature families, declared before any result is read.
VIX_LEVEL = ["vix_fwd30_bp", "vix_slot_z"]
VIX_PREMIUM = ["vrp_log", "vrp_log_slot_z"]
VIX_DYNAMICS = ["vix_chg_15m", "vix_chg_60m", "vix_chg_since_open",
                "vix_overnight_chg", "vix_intraday_range"]
VIX_ALL = VIX_LEVEL + VIX_PREMIUM + VIX_DYNAMICS
