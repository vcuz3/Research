"""Canonical causal forward-30-minute realised-volatility forecast (EXP-0011).

The operational specification adopted by EXP-0011 / HYP-0008 is deliberately small:

    features = [causal trailing 90-session same-slot median of the target,
                range_rv_15m]

The same-slot median supplies "the normal volatility for this exact decision slot"
using only earlier sessions; `range_rv_15m` supplies the latest local volatility
state. The six-variable multi-horizon candidate beat it out of sample by only
+0.009 IC and was NOT adopted (see `MEMORY.md`, `artifacts/runs/EXP-0011/`).

This module re-implements that frozen specification as importable, testable code so
that later studies can consume the forecast without re-executing (or mutating) the
confirmation notebook `notebooks/range_multihorizon_vol_confirmation.ipynb`, which
remains the immutable record of EXP-0011 (sha256 ccb9f5e9...79606).

Every construction below is copied from that notebook so the numbers reproduce
exactly (rule 23). Every study that consumes it asserts the reproduction
against the notebook's published pooled ICs before it uses the forecast.

Causality notes (rule 7):
  * `range_rv_15m` at a decision bar uses the 15 bars ENDING at that bar.
  * the target starts at the NEXT minute's open and ends 30 clock minutes later,
    so feature and target windows never overlap;
  * the same-slot median is `groupby(mfo).shift(1).rolling(90, min_periods=60)`,
    so the current session's own target can never enter its own normaliser;
  * forecasts are walk-forward: the model for test year Y is fitted only on
    sessions from years strictly before Y.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from .loaders import ONE_MIN

# ---- frozen constants (identical to the EXP-0011 notebook) ------------------- #
HORIZON_MIN = 30
SLOT_LOOKBACK, SLOT_MIN_OBS = 90, 60
RANDOM_SEED = 20260730
MODEL_MAX_ITER = 220
RTH_START, RTH_END = 570, 960          # 09:30 / 16:00 ET
RTH_MINUTES = RTH_END - RTH_START      # 390

TARGET = "fwd_rv_bp"
TARGET_NORM = "fwd_rv_bp_norm"
SLOT_MEDIAN = "fwd_rv_bp_slot_median90"
#: The adopted two-input core. Order matters for exact model reproduction.
FEATURES = [SLOT_MEDIAN, "range_rv_15m"]

#: Candidate state variables built only when `build_decision_frame(candidates=True)`.
#: Definitions are copied verbatim from the EXP-0011 notebook, which computed all four
#: and then dropped three of them from its kept columns, so they have never been
#: through the walk-forward. Gated because the frozen core must not silently grow.
CANDIDATE_FEATURES = ["jump_share_60m", "rv_ratio_15_60",
                      "path_efficiency_15m", "overnight_rv_slot_z"]


def decision_mfos() -> list[int]:
    """Decision slots with a fully-defined 30-minute forward window (09:59..14:59).

    The Concretum clock also decides at 15:29 and 15:59, but a 30-minute forward
    window does not fit inside the session there, so the canonical forecast is
    undefined at those two slots. Consumers must report that coverage loss.
    """
    return [m for m in range(29, RTH_MINUTES, 30)
            if m + HORIZON_MIN + 1 < RTH_MINUTES]


def _target_paths_for_session(group: pd.DataFrame) -> pd.DataFrame:
    """Forward 30-minute |move|, realised vol and semivariances, in bp, from opens.

    Returns NaN unless the whole window is one unbroken run of consecutive minutes
    in a single contract with no roll marker (rule 11).

    `fwd_dsv_bp` / `fwd_usv_bp` are the downside/upside semivariance legs. Because
    every one-minute return is either non-positive or positive, they satisfy
    `fwd_rv_bp**2 == fwd_dsv_bp**2 + fwd_usv_bp**2` exactly (pinned by a test).
    """
    opens = group["open"].to_numpy(float)
    mfo = group["mfo"].to_numpy(int)
    symbols = group["symbol"].astype(str).to_numpy()
    rolls = group["is_roll"].fillna(False).to_numpy(bool)
    abs_bp = np.full(len(group), np.nan)
    rv_bp = np.full(len(group), np.nan)
    dsv_bp = np.full(len(group), np.nan)
    usv_bp = np.full(len(group), np.nan)
    for p in range(len(group)):
        end = p + HORIZON_MIN + 1
        if end >= len(group) or mfo[p + 1] != mfo[p] + 1 or mfo[end] != mfo[p] + HORIZON_MIN + 1:
            continue
        if np.any(rolls[p + 1:end + 1]) or np.any(symbols[p + 1:end + 1] != symbols[p + 1]):
            continue
        path = np.diff(np.log(opens[p + 1:end + 1]))
        if len(path) == HORIZON_MIN and np.all(np.isfinite(path)):
            abs_bp[p] = 1e4 * abs(np.log(opens[end] / opens[p + 1]))
            rv_bp[p] = 1e4 * np.sqrt(np.sum(path * path))
            neg = np.minimum(path, 0.0)
            pos = np.maximum(path, 0.0)
            dsv_bp[p] = 1e4 * np.sqrt(np.sum(neg * neg))
            usv_bp[p] = 1e4 * np.sqrt(np.sum(pos * pos))
    return pd.DataFrame({"fwd_abs_bp": abs_bp, "fwd_rv_bp": rv_bp,
                         "fwd_dsv_bp": dsv_bp, "fwd_usv_bp": usv_bp}, index=group.index)


def _past_paths_for_session(group: pd.DataFrame) -> pd.DataFrame:
    """The BACKWARD twin of `_target_paths_for_session`: trailing 30-minute state.

    Same estimator, same price series, applied to the window ENDING at the decision
    bar's own open — so `past_rv30_bp` is directly comparable with `fwd_rv_bp` and
    `log(fwd/past)` is a clean "did volatility change" quantity. This is the naive
    "volatility persists" benchmark used to define the disagreement set.

    Strictly causal: the window ends at `open[p]`, which is observed before the
    decision is taken at the close of bar `p`, and never reaches into bar `p+1`.

    At the first decision slot (mfo 29) only 29 in-session returns exist, so the sum
    of squares is scaled by `HORIZON_MIN / n`. The window is never allowed to cross
    the session open into overnight trade, because the forward target never does.
    Any residual per-slot scale bias is absorbed by within-slot comparison.
    """
    opens = group["open"].to_numpy(float)
    mfo = group["mfo"].to_numpy(int)
    symbols = group["symbol"].astype(str).to_numpy()
    rolls = group["is_roll"].fillna(False).to_numpy(bool)
    rv = np.full(len(group), np.nan)
    share = np.full(len(group), np.nan)
    ret = np.full(len(group), np.nan)
    for p in range(len(group)):
        start = max(0, p - HORIZON_MIN)
        n = p - start
        if n < HORIZON_MIN - 1:
            continue
        if mfo[start] != mfo[p] - n:                      # a missing minute in the window
            continue
        if np.any(rolls[start:p + 1]) or np.any(symbols[start:p + 1] != symbols[p]):
            continue
        path = np.diff(np.log(opens[start:p + 1]))
        if len(path) != n or not np.all(np.isfinite(path)):
            continue
        ss = float(np.sum(path * path))
        rv[p] = 1e4 * np.sqrt(ss * HORIZON_MIN / n)
        ret[p] = 1e4 * float(np.log(opens[p] / opens[start]))
        if ss > 0:
            neg = np.minimum(path, 0.0)
            share[p] = float(np.sum(neg * neg) / ss)
    return pd.DataFrame({"past_rv30_bp": rv, "past_down_share_30m": share,
                         "past_ret30_bp": ret}, index=group.index)


def _rolling_slot_z(frame: pd.DataFrame, column: str, lookback: int = SLOT_LOOKBACK,
                    min_obs: int = SLOT_MIN_OBS) -> pd.Series:
    """Trailing same-slot z-score, causal: `shift(1)` before the rolling window.

    Verbatim from the EXP-0011 notebook's `rolling_slot_z`, and the same construction
    EXP-0009 adopted as the canonical regime label (`analysis.causal_slot_stats`).
    """
    grouped = frame.groupby("mfo")[column]
    mean = grouped.transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).mean())
    std = grouped.transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=min_obs).std(ddof=1))
    return (frame[column] - mean) / std.replace(0, np.nan)


def _add_candidate_columns(raw: pd.DataFrame, ret_1m: pd.Series) -> None:
    """Add the HYP-0013 candidate state variables to the CONTINUOUS one-minute frame.

    Copied verbatim from the EXP-0011 notebook so the definitions are the ones the
    correlation screen was read on. All are trailing windows ending at the decision
    bar, exactly like `range_rv_15m`, so they are observable at the decision and never
    touch the forward window (pinned in `tests/test_forward_vol.py`).

    `ret_1m` is already masked at every timestamp gap, symbol change and roll, and every
    window uses `min_periods=window`, so no window bridges a discontinuity. These are
    60-minute windows on the CONTINUOUS series, so at the early decision slots they reach
    back across the overnight session where bars are thin — the resulting per-slot null
    rate is a rule-9a reportable, measured by the consuming script.
    """
    abs_ret = ret_1m.abs()
    # rv_120m is not a candidate; it exists so EXP-0016 can build a REDUNDANT
    # level-proxy control arm (the cheap analogue of EXP-0011's multi-horizon set).
    for window in (15, 60, 120):
        raw[f"rv_{window}m"] = np.sqrt(ret_1m.pow(2).rolling(window, min_periods=window).sum())

    # Jump share: the fraction of trailing realised variance NOT explained by bipower
    # variation, which is jump-robust. Barndorff-Nielsen & Shephard.
    rv2_60 = ret_1m.pow(2).rolling(60, min_periods=60).sum()
    bipower = abs_ret * abs_ret.shift(1)
    bv60 = (np.pi / 2) * bipower.rolling(59, min_periods=59).sum()
    raw["jump_share_60m"] = (rv2_60 - bv60).clip(lower=0) / rv2_60.replace(0, np.nan)

    raw["rv_ratio_15_60"] = raw.rv_15m / raw.rv_60m.replace(0, np.nan)

    # Path efficiency: distance travelled / ground covered. 1.0 = a straight line,
    # near 0 = churn. `travelled` is masked, so a gap in the window nulls the ratio.
    endpoint = np.log(raw.close / raw.close.shift(15)).abs()
    travelled = abs_ret.rolling(15, min_periods=15).sum()
    raw["path_efficiency_15m"] = endpoint / travelled.replace(0, np.nan)


def _overnight_rv_bp(raw: pd.DataFrame, ret_1m: pd.Series) -> pd.Series:
    """Realised vol of the COMPLETED Globex overnight session, keyed by its RTH date.

    18:00 ET onward belongs to the next calendar day's RTH session; 00:00-09:29 belongs
    to the same day's. The window closes at 09:29, before the first decision at 09:59,
    so this is known in full at every decision (rule 7).
    """
    tod = raw.tod.to_numpy()
    rth_date = raw.calendar_date + pd.to_timedelta((tod >= 18 * 60).astype(int), unit="D")
    overnight = pd.DataFrame({"rth_date": rth_date, "ret": ret_1m}).loc[
        (tod >= 18 * 60) | (tod < RTH_START)]
    return 1e4 * overnight.groupby("rth_date").ret.apply(
        lambda s: np.sqrt(np.nansum(np.square(s.to_numpy(float)))))


def build_decision_frame(inst: str, data_end_utc: pd.Timestamp | None = None,
                         candidates: bool = False) -> tuple[pd.DataFrame, dict]:
    """One row per decision slot with the two core features and the forward target.

    `candidates=True` additionally builds the HYP-0013 candidate state variables
    (`CANDIDATE_FEATURES`). It is OFF by default so the frozen core path stays
    bit-identical and cheap for the studies that only need the adopted specification.

    `data_end_utc` seals the read at a timestamp (the notebook's Part-A seal). All
    features are backward-looking, so sealing must not change any surviving row —
    `tests/test_forward_vol.py::test_sealing_the_read_does_not_change_earlier_rows`
    pins that, which is also the study's leakage invariant.
    """
    cols = ["ts_utc", "symbol", "open", "high", "low", "close", "volume", "is_roll"]
    filters = [("ts_utc", "<", data_end_utc)] if data_end_utc is not None else None
    raw = pd.read_parquet(ONE_MIN[inst], columns=cols, filters=filters)
    duplicate_ts = int(raw.ts_utc.duplicated().sum())
    out_of_order = int((raw.ts_utc.diff().dropna() < pd.Timedelta(0)).sum())
    raw = raw.sort_values("ts_utc").reset_index(drop=True)
    et = raw.ts_utc.dt.tz_convert("America/New_York")
    raw["calendar_date"] = et.dt.tz_localize(None).dt.normalize()
    raw["tod"] = et.dt.hour * 60 + et.dt.minute

    # A NaN return after any timestamp gap, symbol change or roll, plus
    # min_periods=window, stops a row-count window from bridging a discontinuity.
    link_gap = raw.ts_utc.diff().ne(pd.Timedelta(minutes=1))
    symbol_change = raw.symbol.astype(str).ne(raw.symbol.astype(str).shift(1))
    bad_link = link_gap | symbol_change | raw.is_roll.fillna(False)
    raw["range_log"] = np.log(raw.high / raw.low).mask(bad_link)
    raw["range_rv_15m"] = np.sqrt(raw.range_log.pow(2).rolling(15, min_periods=15).sum())
    if candidates:
        ret_1m = np.log(raw.close).diff().mask(bad_link)
        _add_candidate_columns(raw, ret_1m)
        overnight_rv = _overnight_rv_bp(raw, ret_1m)

    rth = raw.loc[(raw.tod >= RTH_START) & (raw.tod < RTH_END)].copy()
    rth["sdate"] = rth.calendar_date
    rth["mfo"] = rth.tod - RTH_START
    rth = rth.sort_values(["sdate", "mfo"]).reset_index(drop=True)
    tcols = ["fwd_abs_bp", "fwd_rv_bp", "fwd_dsv_bp", "fwd_usv_bp"]
    targets = rth.groupby("sdate", group_keys=False).apply(_target_paths_for_session)
    rth[tcols] = targets[tcols]
    pcols = ["past_rv30_bp", "past_down_share_30m", "past_ret30_bp"]
    past = rth.groupby("sdate", group_keys=False).apply(_past_paths_for_session)
    rth[pcols] = past[pcols]

    d = rth.loc[rth.mfo.isin(decision_mfos())].copy()
    # Share of forward variance contributed by down-minutes. Bounded in [0, 1] and
    # always defined when the forward window moved at all, unlike log(dsv/usv).
    d["fwd_down_share"] = np.where(
        d.fwd_rv_bp.to_numpy() > 0,
        np.square(d.fwd_dsv_bp.to_numpy()) / np.square(d.fwd_rv_bp.to_numpy().clip(min=1e-12)),
        np.nan)
    for target in tcols + ["fwd_down_share"]:
        median_col = f"{target}_slot_median90"
        d[median_col] = d.groupby("mfo")[target].transform(
            lambda s: s.shift(1).rolling(SLOT_LOOKBACK, min_periods=SLOT_MIN_OBS).median())
        d[f"{target}_norm"] = d[target] / d[median_col].replace(0, np.nan)
    if candidates:
        d["overnight_rv_bp"] = d.sdate.map(overnight_rv)
        d["overnight_rv_slot_z"] = _rolling_slot_z(d, "overnight_rv_bp")
    d["inst"] = inst
    d["year"] = d.sdate.dt.year

    quality = {
        "instrument": inst, "raw_rows": len(raw), "rth_rows": len(rth),
        "decision_rows": len(d), "sessions": int(d.sdate.nunique()),
        "first": d.sdate.min(), "last": d.sdate.max(),
        "duplicate_ts": duplicate_ts, "out_of_order_ts": out_of_order,
        "roll_rows": int(raw.is_roll.fillna(False).sum()),
        "missing_rv_targets": int(d.fwd_rv_bp.isna().sum()),
        "missing_range_rv_15m": int(d.range_rv_15m.isna().sum()),
        "missing_slot_median": int(d[SLOT_MEDIAN].isna().sum()),
        "missing_past_rv30": int(d.past_rv30_bp.isna().sum()),
    }
    if candidates:
        quality.update({f"missing_{c}": int(d[c].isna().sum()) for c in CANDIDATE_FEATURES})
    keep = (["inst", "ts_utc", "sdate", "year", "mfo", "close", "range_rv_15m",
             "past_rv30_bp", "past_down_share_30m", "past_ret30_bp"]
            + (CANDIDATE_FEATURES + ["overnight_rv_bp", "rv_15m", "rv_60m", "rv_120m"]
               if candidates else [])
            + [c for c in d.columns if c.startswith("fwd_")])
    return d[list(dict.fromkeys(c for c in keep if c in d.columns))].copy(), quality


def make_model(seed: int) -> Pipeline:
    """The frozen EXP-0011 learner. Not tuned here; changing it breaks reproduction."""
    return Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("model", HistGradientBoostingRegressor(
            max_iter=MODEL_MAX_ITER, learning_rate=.04, max_leaf_nodes=15,
            l2_regularization=1.0, random_state=seed))])


def walkforward_forecast(frame: pd.DataFrame, first_test_year: int,
                         last_test_year: int | None = None,
                         target: str = TARGET, features: list[str] | None = None,
                         pred_col: str = "fvol_bp", min_train: int = 1000,
                         min_test: int = 100) -> pd.DataFrame:
    """Expanding-window walk-forward forecast; year Y is fitted on years < Y only.

    Returns the decision rows of the tested years with `pred_col` added. Rows whose
    target is missing are dropped, matching the EXP-0011 evaluation sample.
    """
    features = list(FEATURES if features is None else features)
    years = sorted(y for y in frame.year.unique()
                   if y >= first_test_year and (last_test_year is None or y <= last_test_year))
    parts = []
    for year in years:
        train = frame.loc[frame.year < year].dropna(subset=[target])
        test = frame.loc[frame.year == year].dropna(subset=[target]).copy()
        if len(train) < min_train or len(test) < min_test:
            continue
        model = make_model(RANDOM_SEED + year)
        model.fit(train[features], np.log1p(train[target].clip(lower=0)))
        test[pred_col] = np.expm1(model.predict(test[features])).clip(min=0)
        parts.append(test)
    if not parts:
        return frame.iloc[:0].assign(**{pred_col: []})
    return pd.concat(parts, ignore_index=True)
