"""Shared measurement helpers for the VEI exploration (no trading).

Provides:
  * the decision clock (PERIOD / decision_mfos) shared by every study.
  * forward_features: per (date, decision-mfo) causal PAST realized vol and FORWARD
    realized vol / range / signed return over horizons, from 1-min RTH bars.
  * spearman + session-block-bootstrap IC and Pearson correlation (rule-12
    dependence via resampling whole sessions), on one shared resampler.
  * causal_slot_percentile: same-time-of-day percentile rank of a feature against
    its own trailing history at that slot (a time-of-day de-seasonalisation).
  * variance ratio (Lo-MacKinlay style) for MR-vs-momentum reads, pooled or over
    a stack of equal-length forward windows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# decision clock (shared; every study used to redefine this locally)
# --------------------------------------------------------------------------- #
PERIOD = 30
RTH_MINUTES = 390


def decision_mfos(period: int = PERIOD, rth_minutes: int = RTH_MINUTES) -> list[int]:
    """Closing minute of each `period`-long RTH block: 29, 59, ... for period=30.

    These are the bars whose CLOSE is observable at the decision; the fill is the
    next bar's open (rule 2).
    """
    return [j * period - 1 for j in range(1, rth_minutes // period + 1)]


DM = decision_mfos()


# --------------------------------------------------------------------------- #
# rank correlation with session-block bootstrap
# --------------------------------------------------------------------------- #
def _rankcorr(rx: np.ndarray, ry: np.ndarray) -> float:
    rx = rx - rx.mean(); ry = ry - ry.mean()
    d = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / d) if d > 0 else np.nan


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 20:
        return np.nan
    rx = pd.Series(x[m]).rank().to_numpy().astype(float)
    ry = pd.Series(y[m]).rank().to_numpy().astype(float)
    return _rankcorr(rx, ry)


def session_slices(d: pd.DataFrame, date_col: str = "date"):
    """Group a frame into contiguous per-session slices for block resampling.

    Returns `(order, slices)` where `order` sorts the frame's rows so each session
    is contiguous, and `slices` indexes those sessions in that sorted order. Callers
    apply `order` to their own arrays. Resampling whole sessions is how every study
    here handles intraday dependence (rule 12).
    """
    codes, uniq = pd.factorize(d[date_col].to_numpy())
    order = np.argsort(codes, kind="stable")
    counts = np.bincount(codes, minlength=len(uniq))
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    return order, [slice(starts[i], starts[i] + counts[i]) for i in range(len(uniq))]


def _block_boot(d: pd.DataFrame, cols: list[str], stat, rng, nboot: int,
                date_col: str = "date") -> np.ndarray:
    """Draw `nboot` session-block-resampled values of `stat(*resampled_columns)`.

    One `rng.integers(0, nsess, size=nsess)` call per draw, so the RNG call order
    matches the per-study implementations this consolidates.
    """
    order, sl = session_slices(d, date_col)
    arrs = [d[c].to_numpy(float)[order] for c in cols]
    nsess = len(sl)
    out = np.empty(nboot)
    for b in range(nboot):
        pick = rng.integers(0, nsess, size=nsess)
        out[b] = stat(*[np.concatenate([a[sl[j]] for j in pick]) for a in arrs])
    return out


def block_boot_ic(df: pd.DataFrame, xcol: str, ycol: str, rng,
                  nboot: int = 1000) -> tuple[float, float, float]:
    """Pooled Spearman IC + session-block bootstrap 90% CI (resample sessions)."""
    d = df.dropna(subset=[xcol, ycol])
    if len(d) < 50:
        return np.nan, np.nan, np.nan
    real = spearman(d[xcol].to_numpy(float), d[ycol].to_numpy(float))

    def _stat(xb, yb):
        rx = pd.Series(xb).rank().to_numpy().astype(float)
        ry = pd.Series(yb).rank().to_numpy().astype(float)
        return _rankcorr(rx, ry)

    boots = _block_boot(d, [xcol, ycol], _stat, rng, nboot)
    lo, hi = np.nanpercentile(boots, [5, 95])
    return real, float(lo), float(hi)


def block_boot_corr(df: pd.DataFrame, xcol: str, ycol: str, rng,
                    nboot: int = 1000, min_n: int = 50
                    ) -> tuple[float, float, float]:
    """Pooled PEARSON correlation + session-block bootstrap 90% CI.

    The past->forward return statistic used by the regime studies (Study D and the
    term structure). Separate from `block_boot_ic`, which ranks first.
    """
    d = df.dropna(subset=[xcol, ycol])
    if len(d) < min_n:
        return np.nan, np.nan, np.nan
    real = float(np.corrcoef(d[xcol].to_numpy(float), d[ycol].to_numpy(float))[0, 1])

    def _stat(xb, yb):
        return np.corrcoef(xb, yb)[0, 1] if len(xb) > 2 else np.nan

    boots = _block_boot(d, [xcol, ycol], _stat, rng, nboot)
    return real, float(np.nanpercentile(boots, 5)), float(np.nanpercentile(boots, 95))


# --------------------------------------------------------------------------- #
# time-of-day de-seasonalisation
# --------------------------------------------------------------------------- #
def causal_slot_percentile(df: pd.DataFrame, col: str, *, slot_col: str = "mfo",
                           date_col: str = "date", lookback: int = 90,
                           min_obs: int = 60) -> pd.Series:
    """Percentile rank of `col` against its own trailing history AT THE SAME SLOT.

    For each (date, slot) the value is compared only with the `lookback` STRICTLY
    PRIOR sessions' values at that same slot, so the result is causal (rule 7). A
    fractional `min_obs` requirement (not the strict `lookback`) keeps coverage
    uniform across slots rather than deleting decisions wherever history is thin —
    the rule-9a lesson from the GC noise-band port.

    Answers "how unusual is this reading FOR THIS TIME OF DAY", which is a different
    question from the raw level whenever the feature has a time-of-day profile.
    """
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for _, g in df.groupby(slot_col, sort=False):
        g = g.sort_values(date_col)
        v = g[col].to_numpy(float)
        res = np.full(len(v), np.nan)
        for i in range(len(v)):
            if not np.isfinite(v[i]):
                continue
            w = v[max(0, i - lookback):i]
            w = w[np.isfinite(w)]
            if len(w) >= min_obs:
                res[i] = float((w < v[i]).mean())
        out.loc[g.index] = res
    return out


# --------------------------------------------------------------------------- #
# forward / past realized-vol features at the decision clock
# --------------------------------------------------------------------------- #
def forward_features(bars: pd.DataFrame, dm, horizons=(30, 60),
                     past_win: int = 30) -> pd.DataFrame:
    """Per (date, decision-mfo): causal PAST vol and FORWARD vol/range/return.

    All quantities are dimensionless (log-return based) so they compare across
    price levels and eras. PAST features use bars strictly at/before the decision
    bar; FORWARD features use bars strictly after it (targets, not predictors).
      past_absvar  = sum |r| over (m-past_win, m]
      past_rv      = sqrt(sum r^2) over (m-past_win, m]
      fwd_absvar_H = sum |r| over (m, m+H]
      fwd_rv_H     = sqrt(sum r^2) over (m, m+H]
      fwd_range_H  = (max high - min low)/close[m] over (m, m+H]
      fwd_ret_H    = log(close[m+H]/close[m])   (signed)

    A horizon may also be the literal "close", meaning "to the last bar of the
    session" (columns `fwd_*_close`); it is NaN at the final decision bar, where
    there is no forward window left.
    """
    dmset = {int(x) for x in dm}
    rows = []
    for sd, g in bars.groupby("sdate", sort=False):
        g = g.sort_values("mfo")
        mfo = g["mfo"].to_numpy(int)
        c = g["close"].to_numpy(float)
        hi = g["high"].to_numpy(float)
        lo = g["low"].to_numpy(float)
        lc = np.log(c)
        r = np.diff(lc, prepend=lc[0])   # r[0]=0; r[i]=log(c[i]/c[i-1])
        cs_abs = np.cumsum(np.abs(r))
        cs_sq = np.cumsum(r * r)
        n = len(mfo)
        pos = {int(m): i for i, m in enumerate(mfo)}
        for i in range(n):
            m = int(mfo[i])
            if m not in dmset:
                continue
            j0 = max(0, i - past_win)
            past_absvar = cs_abs[i] - cs_abs[j0]
            past_rv = np.sqrt(max(cs_sq[i] - cs_sq[j0], 0.0))
            past_ret = lc[i] - lc[j0]
            rec = {"date": sd, "mfo": m, "past_absvar": past_absvar,
                   "past_rv": past_rv, "past_ret": past_ret}
            for H in horizons:
                k = n - 1 if H == "close" else i + H
                if i < k < n:
                    rec[f"fwd_absvar_{H}"] = cs_abs[k] - cs_abs[i]
                    rec[f"fwd_rv_{H}"] = np.sqrt(max(cs_sq[k] - cs_sq[i], 0.0))
                    rec[f"fwd_range_{H}"] = (hi[i + 1:k + 1].max()
                                            - lo[i + 1:k + 1].min()) / c[i]
                    rec[f"fwd_ret_{H}"] = lc[k] - lc[i]
                    rec[f"fwd_n_{H}"] = k - i
                else:
                    rec[f"fwd_absvar_{H}"] = np.nan
                    rec[f"fwd_rv_{H}"] = np.nan
                    rec[f"fwd_range_{H}"] = np.nan
                    rec[f"fwd_ret_{H}"] = np.nan
                    rec[f"fwd_n_{H}"] = np.nan
            rows.append(rec)
    return pd.DataFrame(rows)


def variance_ratio(returns: np.ndarray, q: int) -> float:
    """Lo-MacKinlay variance ratio VR(q) = Var(q-sum)/(q*Var(1)). >1 trending,
    <1 mean-reverting, ~1 random walk. `returns` is a 1-D array of 1-period rets."""
    r = returns[np.isfinite(returns)]
    n = len(r)
    if n < q * 5:
        return np.nan
    mu = r.mean()
    var1 = np.sum((r - mu) ** 2) / n
    if var1 <= 0:
        return np.nan
    rq = np.convolve(r, np.ones(q), mode="valid")   # rolling q-sums
    varq = np.sum((rq - q * mu) ** 2) / len(rq)
    return float(varq / (q * var1))


def forward_return_windows(bars: pd.DataFrame, keys, horizon: int) -> np.ndarray:
    """Stack the next `horizon` 1-min log returns after each decision bar.

    `keys` is an iterable of (date, mfo). Returns an (n_windows, horizon) array;
    windows that run past the session end are dropped. Purely forward-looking — a
    measurement target, never a predictor.
    """
    want = {}
    for sd, m in keys:
        want.setdefault(pd.Timestamp(sd), set()).add(int(m))
    rows = []
    for sd, g in bars.groupby("sdate", sort=False):
        slots = want.get(pd.Timestamp(sd))
        if not slots:
            continue
        g = g.sort_values("mfo")
        lc = np.log(g["close"].to_numpy(float))
        r = np.diff(lc, prepend=lc[0])
        pos = {int(m): i for i, m in enumerate(g["mfo"].to_numpy(int))}
        for m in slots:
            i = pos.get(m)
            if i is None or i + horizon >= len(r):
                continue
            rows.append(r[i + 1:i + 1 + horizon])
    return np.asarray(rows) if rows else np.empty((0, horizon))


def variance_ratio_windows(windows: np.ndarray, q: int) -> float:
    """VR(q) over a stack of equal-length forward windows.

    Same estimand as `variance_ratio` (>1 trending, <1 mean-reverting, ~1 random
    walk) but the q-sums are formed WITHIN each window, so no statistic ever spans
    two different sessions or decision points. Pools the per-window sums to get one
    ratio.
    """
    w = np.asarray(windows, dtype=float)
    if w.ndim != 2 or w.shape[0] < 20 or w.shape[1] < q:
        return np.nan
    flat = w[np.isfinite(w)]
    mu = flat.mean()
    var1 = np.mean((flat - mu) ** 2)
    if var1 <= 0:
        return np.nan
    cs = np.cumsum(w, axis=1)
    cs = np.concatenate([np.zeros((w.shape[0], 1)), cs], axis=1)
    rq = cs[:, q:] - cs[:, :-q]              # rolling q-sums within each window
    rq = rq[np.isfinite(rq)]
    varq = np.mean((rq - q * mu) ** 2)
    return float(varq / (q * var1))
