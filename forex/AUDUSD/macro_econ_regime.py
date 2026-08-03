"""
macro_econ_regime.py — Step-3b FUNDAMENTAL economic-strength regime classifier
for AUDUSD.

Thesis
------
A currency reflects the RELATIVE strength of two economies.  Step-3
(`macro_regime.py`) asked *which market factor moves AUDUSD*; this asks the more
fundamental question: *is the Australian economy strong or weak relative to the
US*, straight from the point-in-time (PIT) macro factors — growth, labour,
inflation, real rates, terms of trade — and does that regime line up with where
AUDUSD trades.

Inputs (all already AU-minus-US relatives, all causal)
------------------------------------------------------
`data/audusd_point_in_time_macro_factors.csv` from download_public_macro_factors.py.
The `*_score` columns are **expanding, zero-neutral z-scores** (no look-ahead:
scaled by an expanding std of past+current data only), so a score dated month-end
t uses only data released by t.  ALFRED vintages mean the well-populated composite
only exists from ~2017 (~105 monthly obs) — a SMALL, highly persistent sample, so
significance is tested with a moving-block bootstrap, not naive t-stats.

Construction
------------
Component scores are grouped into economic dimensions and signed so that
**positive = AU relatively stronger / AUD-supportive**:

  growth     = mean(gdp, consumption, mfg_confidence, unemployment_trend)
  monetary   = relative_real_short_rate            (AU real-rate carry)
  external   = terms_of_trade_dynamics             (commodity terms of trade)
  inflation  = mean(excess_core_cpi, excess_ppi, inflation_expectations)   [own axis]

  STRENGTH   = mean(growth, monetary, external)     — the real-economy + carry axis
               (inflation is kept as a SEPARATE axis because its currency sign is
                ambiguous: hotter AU inflation can be AUD+ via a hawkish RBA or
                AUD− via lost competitiveness).

Regimes emitted
---------------
  * strength_regime : AU_strong / balanced / AU_weak   (thresholds on STRENGTH z)
  * gi_quadrant     : reflation / overheating / stagflation / slowdown
                      (sign of growth × sign of inflation — the classic macro 2×2)

Public API:
    load_factor_panel()                 -> monthly PIT factor frame
    assign_econ_regimes(df, config)     -> regime-labelled monthly frame
    EconRegimeConfig                    -> dimension maps + thresholds
    block_bootstrap_ic / fair_value_residual  -> honest small-sample diagnostics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# reuse the Step-3 post-hoc diagnostics
from macro_regime import transition_matrix, persistence_stats

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FACTOR_FILE = DATA_DIR / "audusd_point_in_time_macro_factors.csv"


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass
class EconRegimeConfig:
    # economic-dimension -> list of *_score columns (all "positive = AU stronger")
    dimensions: dict[str, list[str]] = field(default_factory=lambda: {
        "growth": [
            "relative_gdp_growth_trend_score",
            "relative_consumption_growth_score",
            "manufacturing_confidence_improvement_score",
            "relative_unemployment_trend_score",
        ],
        "monetary": ["relative_real_short_rate_score"],
        "external": ["terms_of_trade_dynamics_score"],
        "inflation": [
            "relative_excess_core_cpi_score",
            "relative_excess_ppi_score",
            "relative_inflation_expectations_score",
        ],
    })
    # which dimensions make up the STRENGTH composite (inflation excluded — see docstring)
    strength_dims: list[str] = field(default_factory=lambda: ["growth", "monetary", "external"])
    # a month is scored only if at least this many component scores are present
    min_components: int = 5
    # strength_regime thresholds on the strength z-score
    strong_z: float = 0.4
    weak_z: float = -0.4
    # forward-return horizons (months) for the predictive test
    fwd_horizons: tuple[int, ...] = (1, 3, 6)
    # moving-block bootstrap
    block_len: int = 12
    n_boot: int = 5000
    seed: int = 0


DEFAULT_ECON_CONFIG = EconRegimeConfig()


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
def load_factor_panel(path: str | Path = FACTOR_FILE) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True).sort_index()
    df.index.name = "date"
    return df


# --------------------------------------------------------------------------- #
# Classifier
# --------------------------------------------------------------------------- #
def _dim_composite(df: pd.DataFrame, cols: list[str]) -> tuple[pd.Series, pd.Series]:
    """Row-mean of present component scores + count present (graceful to NaNs)."""
    present = [c for c in cols if c in df.columns]
    sub = df[present]
    n = sub.notna().sum(axis=1)
    comp = sub.mean(axis=1)          # mean ignores NaN
    return comp, n


def assign_econ_regimes(df: pd.DataFrame,
                        config: EconRegimeConfig = DEFAULT_ECON_CONFIG) -> pd.DataFrame:
    """
    MAIN ENTRY POINT.  Label each month by AU–US economic-strength regime.
    Returns a frame indexed by month-end with dimension z-scores, the strength
    composite, the two regime labels, AUDUSD level/returns, and diagnostics.
    All inputs are causal (expanding zn-scores); labels are contemporaneous with
    month t and must be used as-of t (or lagged) to predict t+h.
    """
    cfg = config
    out = pd.DataFrame(index=df.index)

    # AUDUSD level + returns from the (not-revised) spot column
    px = df["audusd_spot"].astype("float64")
    out["audusd"] = px
    logp = np.log(px)
    out["ret_1m"] = logp.diff()

    # dimension composites
    comps, counts = {}, {}
    for dim, cols in cfg.dimensions.items():
        comps[dim], counts[dim] = _dim_composite(df, cols)
        out[f"{dim}_z"] = comps[dim]

    # strength composite = mean of the chosen strength dimensions
    strength = pd.concat([comps[d] for d in cfg.strength_dims], axis=1).mean(axis=1)
    n_components = df[[c for d in cfg.strength_dims for c in cfg.dimensions[d]]].notna().sum(axis=1)
    strength = strength.where(n_components >= cfg.min_components)
    out["strength_z"] = strength
    out["n_components"] = n_components

    # ---- strength regime ---------------------------------------------------
    reg = pd.Series(index=out.index, dtype="object")
    reg[strength >= cfg.strong_z] = "AU_strong"
    reg[strength <= cfg.weak_z] = "AU_weak"
    reg[(strength > cfg.weak_z) & (strength < cfg.strong_z)] = "balanced"
    out["strength_regime"] = reg

    # ---- growth × inflation quadrant --------------------------------------
    g = out["growth_z"]
    infl = out["inflation_z"]
    quad = pd.Series(index=out.index, dtype="object")
    ok = g.notna() & infl.notna()
    quad[ok & (g >= 0) & (infl < 0)] = "reflation"      # strong growth, cooling inflation
    quad[ok & (g >= 0) & (infl >= 0)] = "overheating"   # strong growth, hot inflation
    quad[ok & (g < 0) & (infl >= 0)] = "stagflation"    # weak growth, hot inflation
    quad[ok & (g < 0) & (infl < 0)] = "slowdown"        # weak growth, cooling inflation
    out["gi_quadrant"] = quad

    # confidence + persistence bookkeeping
    out["confidence"] = strength.abs()
    out["regime_duration"] = _run_length(reg)

    out.attrs["config"] = cfg
    return out


def _run_length(labels: pd.Series) -> pd.Series:
    dur = np.ones(len(labels), dtype=float)
    v = labels.to_numpy()
    for i in range(1, len(v)):
        if pd.notna(v[i]) and v[i] == v[i - 1]:
            dur[i] = dur[i - 1] + 1
        elif pd.isna(v[i]):
            dur[i] = np.nan
    return pd.Series(dur, index=labels.index)


def shift_for_prediction(reg: pd.DataFrame, lag: int = 1) -> pd.DataFrame:
    """Lag labels/scores by `lag` months for strict predictive use."""
    cols = ["strength_regime", "gi_quadrant", "strength_z", "growth_z",
            "inflation_z", "monetary_z", "external_z", "confidence"]
    out = reg.copy()
    out[cols] = out[cols].shift(lag)
    return out


# --------------------------------------------------------------------------- #
# Small-sample honest diagnostics
# --------------------------------------------------------------------------- #
def forward_returns(reg: pd.DataFrame, horizons=(1, 3, 6)) -> pd.DataFrame:
    """Attach forward log returns over h months (causal; NaN at the tail)."""
    logp = np.log(reg["audusd"].astype("float64"))
    out = reg.copy()
    for h in horizons:
        out[f"fwd_{h}m"] = logp.shift(-h) - logp
    return out


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 5:
        return np.nan
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def block_bootstrap_ic(score: pd.Series, fwd: pd.Series, cfg: EconRegimeConfig):
    """
    Moving-block bootstrap of the rank-IC between a score and a forward return,
    to get an honest CI under strong serial dependence (macro regimes are sticky
    and forward returns overlap).  Returns (ic, lo, hi, p_two_sided).
    """
    s = pd.concat([score, fwd], axis=1).dropna()
    if len(s) < cfg.block_len + 5:
        return np.nan, np.nan, np.nan, np.nan
    x = s.iloc[:, 0].to_numpy()
    y = s.iloc[:, 1].to_numpy()
    n = len(x)
    ic = _spearman(x, y)
    L = cfg.block_len
    rng = np.random.default_rng(cfg.seed)
    nblocks = int(np.ceil(n / L))
    boots = np.empty(cfg.n_boot)
    starts_all = np.arange(0, n - L + 1)
    for b in range(cfg.n_boot):
        starts = rng.choice(starts_all, size=nblocks, replace=True)
        idx = np.concatenate([np.arange(st, st + L) for st in starts])[:n]
        boots[b] = _spearman(x[idx], y[idx])
    lo, hi = np.nanpercentile(boots, [5, 95])
    # two-sided p vs 0 from the bootstrap distribution
    frac_pos = np.nanmean(boots > 0)
    p = 2 * min(frac_pos, 1 - frac_pos)
    return ic, lo, hi, p


def fair_value_residual(reg: pd.DataFrame, min_train: int = 36) -> pd.DataFrame:
    """
    CAUSAL fair-value model: at each month t, fit OLS of log(AUDUSD) on the
    strength composite using data up to t only, predict the "fair" level, and
    take residual = actual − fair (positive = AUD rich vs fundamentals).  Then a
    forward-return column lets us test mean-reversion of the misalignment.
    Expanding (walk-forward) so there is no look-ahead.
    """
    s = reg[["audusd", "strength_z"]].dropna().copy()
    logp = np.log(s["audusd"].to_numpy("float64"))
    x = s["strength_z"].to_numpy("float64")
    n = len(s)
    resid = np.full(n, np.nan)
    fair = np.full(n, np.nan)
    for t in range(min_train, n):
        xt = x[:t]
        yt = logp[:t]
        A = np.column_stack([np.ones(t), xt])
        beta, *_ = np.linalg.lstsq(A, yt, rcond=None)
        fair[t] = beta[0] + beta[1] * x[t]
        resid[t] = logp[t] - fair[t]
    out = pd.DataFrame({"log_audusd": logp, "fair_log": fair,
                        "misalignment": resid}, index=s.index)
    return out


if __name__ == "__main__":
    df = load_factor_panel()
    reg = assign_econ_regimes(df)
    sub = reg.dropna(subset=["strength_regime"])
    print("econ-strength labelled months:", len(sub),
          "range", sub.index.min().date(), "->", sub.index.max().date())
    print("\nstrength_regime frequency:")
    print(sub["strength_regime"].value_counts(normalize=True).round(3).to_string())
    print("\ngi_quadrant frequency:")
    print(reg.dropna(subset=["gi_quadrant"])["gi_quadrant"]
          .value_counts(normalize=True).round(3).to_string())
    print("\ncorr(strength_z, AUDUSD level):",
          round(reg["strength_z"].corr(reg["audusd"]), 3))
