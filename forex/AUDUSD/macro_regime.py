"""
macro_regime.py — Step-3 macro-driver regime classifier for AUDUSD.

Goal (NOT a trading strategy): label each day by the *dominant external driver*
of AUDUSD, using rolling relationships that are explainable, not a black box.

Primary method
--------------
Rolling multivariate OLS of the AUDUSD daily log return on a set of driver daily
returns, over short/medium/long windows (default 20 / 60 / 120 trading days).
For each window ending at day t we compute, per driver:
  * standardized beta        (comparable across drivers; sign + magnitude)
  * OLS t-stat               (stability of that beta)
  * simple correlation r_iy
  * Pratt product-measure contribution  c_i = beta_std_i * r_iy   (Σ c_i = R²),
    i.e. that driver's signed share of the window R².
The dominant driver is the one with the largest *positive* variance share; the
regime is that driver's macro bucket.  A minimum-R² gate produces a
"low_signal" regime when nothing explains AUDUSD in the window.

Causality
---------
The window ending at day t uses returns up to and INCLUDING day t, so the label
`macro_regime[t]` is known at t's close.  It is therefore contemporaneous with
return_t (fine for *descriptive* stats) and must be shifted +1 day before being
used to *predict* anything (see `shift_for_prediction`).  No future returns ever
enter a window.  Monthly-frequency series (iron ore, copper, FRED AU yields) are
deliberately NOT used as daily regressors — they only move ~once a month, so
their daily "returns" are structurally zero and would corrupt the regression
(see the driver spec below and CLAUDE.md gotchas #1/#5).  The one exception is
the AU–US RATE DIFFERENTIAL: once `download_rates_futures_ibkr.py` has pulled
daily AU/US bond-futures yields, `build_driver_panel` rebuilds it as a genuine
daily driver (`rate_diff_10y`); until then the rates channel falls back to the
US-2Y proxy.

Comparison methods (secondary, for cross-checking the explainable primary one):
  * rolling correlation dominance
  * rolling-PCA factor dominance
  * simple rules-based macro classification
  * unsupervised KMeans on the rolling driver-strength features

Public API:
    build_driver_panel(levels)            -> daily driver-return DataFrame
    assign_macro_regimes(df, config)      -> regime-labelled DataFrame
    RegimeConfig                          -> all thresholds / windows / drivers
    transition_matrix / persistence_stats -> post-hoc diagnostics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
# Daily AU/US bond-futures yields (from download_rates_futures_ibkr.py).  When
# present, unlocks the genuine daily AU–US rate-differential driver; when absent,
# the classifier falls back to the US-2Y-only rates proxy.
RATES_FUTURES_FILE = DATA_DIR / "rates_futures_daily.csv"


# --------------------------------------------------------------------------- #
# Driver specification
# --------------------------------------------------------------------------- #
# Each driver maps a market series (in raw_market_levels_daily.csv) to:
#   kind   : "logret"  -> log return of the level (FX, equity, commodity, USD ix)
#            "diff"    -> first difference of the level (yields, VIX levels)
#   regime : the macro bucket this driver votes for
#   sign   : the *expected* sign of the beta w.r.t. AUDUSD (for a sanity read;
#            not used to force anything).  +1 = AUD rises when driver rises.
#   daily  : True if the series genuinely updates ~daily (safe as a daily
#            regressor).  Monthly-ffilled series are marked False and excluded.
@dataclass(frozen=True)
class Driver:
    name: str
    series: str
    kind: str          # "logret" | "diff"
    regime: str
    sign: int
    daily: bool = True


# The competing driver universe.  USD / China / commodity / risk / regional /
# rates.  Only genuinely-daily series are enabled by default.
DRIVER_UNIVERSE: list[Driver] = [
    Driver("dxy",    "dxy_broad", "logret", "usd",         sign=-1),  # AUD ↓ when USD ↑
    Driver("usdcny", "usdcny",    "logret", "china",       sign=-1),  # AUD ↓ when CNY weak
    Driver("nzdusd", "nzdusd",    "logret", "regional_fx", sign=+1),  # commodity-bloc twin
    Driver("oil",    "oil_wti",   "logret", "commodity",   sign=+1),  # ToT proxy (daily)
    Driver("sp500",  "sp500",     "logret", "risk",        sign=+1),  # risk-on
    Driver("vix",    "vix",       "diff",   "risk",        sign=-1),  # risk-off
    Driver("us2y",   "us_2y",     "diff",   "rates",       sign=-1),  # US rates ↑ → USD ↑ → AUD ↓
    # --- AU–US rate DIFFERENTIAL (computed in build_driver_panel from bond ----
    #     futures via download_rates_futures_ibkr.py; series="" = not a raw
    #     column, so the generic loader skips it).  This is the genuine daily
    #     rates driver; present only once the futures file has been pulled.  AUD
    #     STRENGTHENS when the AU–US spread widens (carry) -> sign +1.
    Driver("rate_diff_10y", "", "diff", "rates", sign=+1),
    # --- monthly-only series: NOT daily regressors, kept for reference -------
    Driver("iron_ore", "iron_ore", "logret", "commodity", sign=+1, daily=False),
    Driver("copper",   "copper",   "logret", "commodity", sign=+1, daily=False),
    Driver("au_10y",   "au_10y",   "diff",   "rates",     sign=+1, daily=False),
]

# Driver -> human-readable macro regime label.
REGIME_OF_DRIVER = {d.name: d.regime for d in DRIVER_UNIVERSE}

# All macro regimes the classifier can emit.
ALL_REGIMES = ["usd", "china", "commodity", "risk", "rates", "regional_fx", "low_signal"]


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass
class RegimeConfig:
    # driver names (subset of DRIVER_UNIVERSE) that compete for the label.
    # "rate_diff_10y" is listed but only enters if build_driver_panel produced it
    # (i.e. the bond-futures file exists); assign_macro_regimes filters to the
    # columns actually present, so this is safe pre- and post-futures-pull.
    drivers: list[str] = field(default_factory=lambda: [
        "dxy", "usdcny", "nzdusd", "oil", "sp500", "vix", "us2y", "rate_diff_10y",
    ])
    windows: dict[str, int] = field(default_factory=lambda: {
        "short": 20, "medium": 60, "long": 120,
    })
    primary_window: str = "medium"          # which window drives the emitted label
    # ---- assignment thresholds (sensible defaults; do NOT overfit) ----------
    min_r2: float = 0.15                     # below → low_signal regime (full contest)
    min_idio_contrib: float = 0.02           # min partial R² share for an idiosyncratic driver
    min_dominance: float = 1.25              # top / 2nd variance-share ratio to be "clean"
    min_abs_beta: float = 0.05               # ignore near-zero standardized betas
    stability_win: int = 20                  # window for rolling regime-stability share
    # ---- risk driver de-duplication -----------------------------------------
    # sp500 and vix both vote "risk"; sum their contributions so risk isn't
    # penalised for being split across two proxies.
    merge_risk_proxies: bool = True
    # ---- regional-FX handling -----------------------------------------------
    # AUD and NZD co-move ~0.8, so NZD (regional_fx) mechanically eats most of
    # the window R².  It is kept in the regression (macro betas become PARTIAL,
    # i.e. controlled for the commodity-bloc co-move) but is excluded from the
    # "which external MACRO driver leads" contest and reported separately.  The
    # full contest (regional_fx allowed to win) is emitted as `macro_regime`;
    # the macro-only contest as `idio_regime`.
    regional_bucket: str = "regional_fx"
    # buckets that compete in the IDIOSYNCRATIC contest (idio_regime).
    # USD (DXY) and regional (NZD) are excluded because they are near-tautological
    # for a USD pair (DXY = the dollar leg) / a co-moving twin (NZD = the bloc):
    # in a partial regression one of them always wins and hides the interesting
    # AUD-specific driver.  This contest asks: net of USD & the bloc, does
    # China / commodity / risk / rates move AUD?
    macro_buckets: list[str] = field(default_factory=lambda: [
        "china", "commodity", "risk", "rates",
    ])


DEFAULT_CONFIG = RegimeConfig()


# --------------------------------------------------------------------------- #
# Driver panel
# --------------------------------------------------------------------------- #
def load_levels(path: str | Path = DATA_DIR / "raw_market_levels_daily.csv") -> pd.DataFrame:
    lv = pd.read_csv(path, index_col=0, parse_dates=True)
    lv.index.name = "date"
    return lv.sort_index()


def build_driver_panel(levels: pd.DataFrame,
                       universe: list[Driver] = DRIVER_UNIVERSE,
                       rates_futures_path: str | Path | None = RATES_FUTURES_FILE,
                       ) -> pd.DataFrame:
    """
    Turn raw daily levels into a panel of driver daily changes plus the AUDUSD
    target return.  Log-returns for prices/indices, first-difference for yields
    and VIX levels.  All strictly contemporaneous (no shifting here).

    If `rates_futures_path` exists (produced by download_rates_futures_ibkr.py),
    a genuine daily AU–US 10Y rate-differential driver (`rate_diff_10y`, the
    first difference of the AU10Y−US10Y spread) is added and the panel is tagged
    `attrs["rates_source"]="futures"`.  Otherwise that column is simply absent
    and the classifier falls back to the US-2Y proxy (`rates_source="fred_us2y"`).
    """
    out = pd.DataFrame(index=levels.index)
    out["audusd_ret"] = np.log(levels["audusd"]).diff()
    for d in universe:
        if not d.series or d.series not in levels.columns:
            continue                                     # graceful: skip missing/computed
        s = levels[d.series].astype("float64")
        if d.kind == "logret":
            out[d.name] = np.log(s).diff()
        else:                                            # "diff"
            out[d.name] = s.diff()

    out.attrs["rates_source"] = "fred_us2y"
    out = _add_rate_differential(out, levels, rates_futures_path)
    return out


def _add_rate_differential(out: pd.DataFrame, levels: pd.DataFrame,
                           rates_futures_path: str | Path | None) -> pd.DataFrame:
    """
    Build the daily AU–US 10Y rate-differential driver from bond futures.

    AU 10Y yield comes from the ASX 10Y bond future (100 − price); the US 10Y
    yield prefers the CME 10Y yield future when available and long enough, else
    falls back to FRED us_10y (daily, point-in-time).  The driver value is the
    first difference of the spread level (spread widens when AU rates rise vs US
    -> AUD carry tailwind).  If no futures file exists, no column is added.
    """
    if rates_futures_path is None or not Path(rates_futures_path).exists():
        return out
    rf = pd.read_csv(rates_futures_path, index_col=0, parse_dates=True).sort_index()
    if "au_10y_yield" not in rf.columns:
        return out
    au10 = rf["au_10y_yield"].reindex(out.index).ffill()
    # US 10Y: prefer the yield future if it has decent coverage, else FRED daily
    us10 = None
    if "us_10y_yield" in rf.columns and rf["us_10y_yield"].notna().mean() > 0.3:
        us10 = rf["us_10y_yield"].reindex(out.index).ffill()
    if us10 is None or us10.notna().mean() < 0.5:
        us10 = levels["us_10y"].astype("float64") if "us_10y" in levels else None
    if us10 is None:
        return out
    spread = (au10 - us10)
    out["rate_diff_10y_level"] = spread                 # kept for inspection
    out["rate_diff_10y"] = spread.diff()                # the driver (Δ spread)
    out.attrs["rates_source"] = "futures"
    return out


# --------------------------------------------------------------------------- #
# Rolling regression core
# --------------------------------------------------------------------------- #
def _standardize(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = np.nanmean(a, axis=0)
    sd = np.nanstd(a, axis=0, ddof=0)
    return mu, sd


def _window_regression(Xw: np.ndarray, yw: np.ndarray,
                       driver_names: list[str],
                       min_abs_beta: float) -> dict:
    """
    One window's standardized multivariate OLS.  Returns per-driver
    standardized beta, t-stat, correlation, Pratt contribution, plus window R².
    Drivers that are all-NaN or (near) constant in the window are dropped.
    """
    n = Xw.shape[0]
    p_all = Xw.shape[1]
    empty = {
        "r2": np.nan,
        "beta": {k: np.nan for k in driver_names},
        "tstat": {k: np.nan for k in driver_names},
        "corr": {k: np.nan for k in driver_names},
        "contrib": {k: np.nan for k in driver_names},
        "n_used": 0,
    }
    # rows fully observed across target + all drivers
    mask = np.isfinite(yw) & np.all(np.isfinite(Xw), axis=1)
    # also allow columns that are entirely NaN in-window to be dropped rather
    # than killing every row (e.g. sp500 pre-2015)
    col_ok = np.isfinite(Xw).mean(axis=0) > 0.8
    if col_ok.sum() == 0:
        return empty
    Xw = Xw[:, col_ok]
    used_names = [driver_names[i] for i in range(p_all) if col_ok[i]]
    mask = np.isfinite(yw) & np.all(np.isfinite(Xw), axis=1)
    if mask.sum() < max(10, Xw.shape[1] + 3):
        return empty
    X = Xw[mask]
    y = yw[mask]

    # drop near-constant columns (std≈0) inside the window
    xsd = X.std(axis=0, ddof=0)
    keep = xsd > 1e-12
    if keep.sum() == 0:
        return empty
    X = X[:, keep]
    used_names = [used_names[i] for i in range(len(used_names)) if keep[i]]

    # standardize target + drivers within the window
    ymu, ysd = y.mean(), y.std(ddof=0)
    if ysd < 1e-12:
        return empty
    yz = (y - ymu) / ysd
    xmu = X.mean(axis=0)
    xsd = X.std(axis=0, ddof=0)
    Xz = (X - xmu) / xsd

    # standardized OLS with intercept (~0 after centering, kept for safety)
    A = np.column_stack([np.ones(len(yz)), Xz])
    beta_full, *_ = np.linalg.lstsq(A, yz, rcond=None)
    beta = beta_full[1:]                                  # drop intercept
    resid = yz - A @ beta_full
    dof = max(len(yz) - A.shape[1], 1)
    sigma2 = (resid @ resid) / dof
    # covariance of coefficients
    try:
        XtX_inv = np.linalg.inv(A.T @ A)
        se = np.sqrt(np.maximum(np.diag(XtX_inv) * sigma2, 0.0))[1:]
    except np.linalg.LinAlgError:
        se = np.full_like(beta, np.nan)
    tstat = np.where(se > 0, beta / se, np.nan)

    # simple correlations (standardized -> corr = mean(xz*yz))
    corr = (Xz * yz[:, None]).mean(axis=0)
    # Pratt product measure: contribution_i = beta_i * corr_i ; Σ = R²
    contrib = beta * corr
    r2 = float(np.clip(contrib.sum(), 0.0, 1.0))

    # zero-out negligible betas so noise doesn't win the dominance contest
    small = np.abs(beta) < min_abs_beta
    contrib_eff = contrib.copy()
    contrib_eff[small] = np.minimum(contrib_eff[small], 0.0)

    res = {
        "r2": r2,
        "beta": {k: np.nan for k in driver_names},
        "tstat": {k: np.nan for k in driver_names},
        "corr": {k: np.nan for k in driver_names},
        "contrib": {k: np.nan for k in driver_names},
        "n_used": int(mask.sum()),
    }
    for i, nm in enumerate(used_names):
        res["beta"][nm] = float(beta[i])
        res["tstat"][nm] = float(tstat[i])
        res["corr"][nm] = float(corr[i])
        res["contrib"][nm] = float(contrib_eff[i])
    return res


def rolling_regression(panel: pd.DataFrame, driver_names: list[str],
                       window: int, min_abs_beta: float) -> dict[str, pd.DataFrame]:
    """
    Run `_window_regression` for every day with a full trailing window.
    Returns dict of DataFrames keyed by quantity: beta / tstat / corr / contrib
    (each cols=drivers) and a scalar-per-day 'r2' Series inside 'meta'.
    """
    y = panel["audusd_ret"].to_numpy("float64")
    X = panel[driver_names].to_numpy("float64")
    idx = panel.index
    n = len(panel)

    betas = np.full((n, len(driver_names)), np.nan)
    tstats = np.full((n, len(driver_names)), np.nan)
    corrs = np.full((n, len(driver_names)), np.nan)
    contribs = np.full((n, len(driver_names)), np.nan)
    r2 = np.full(n, np.nan)
    n_used = np.zeros(n, dtype=int)

    name_pos = {nm: i for i, nm in enumerate(driver_names)}
    for t in range(window - 1, n):
        sl = slice(t - window + 1, t + 1)
        r = _window_regression(X[sl], y[sl], driver_names, min_abs_beta)
        r2[t] = r["r2"]
        n_used[t] = r["n_used"]
        for nm in driver_names:
            j = name_pos[nm]
            betas[t, j] = r["beta"][nm]
            tstats[t, j] = r["tstat"][nm]
            corrs[t, j] = r["corr"][nm]
            contribs[t, j] = r["contrib"][nm]

    mk = lambda a: pd.DataFrame(a, index=idx, columns=driver_names)
    return {
        "beta": mk(betas), "tstat": mk(tstats),
        "corr": mk(corrs), "contrib": mk(contribs),
        "r2": pd.Series(r2, index=idx, name="r2"),
        "n_used": pd.Series(n_used, index=idx, name="n_used"),
    }


# --------------------------------------------------------------------------- #
# Regime assignment
# --------------------------------------------------------------------------- #
def _regime_contrib_frame(contrib: pd.DataFrame, cfg: RegimeConfig) -> pd.DataFrame:
    """
    Collapse per-driver contributions to per-REGIME contributions (summing the
    two risk proxies when merge_risk_proxies is on).  Columns = regime buckets.
    """
    reg = pd.DataFrame(index=contrib.index)
    for driver in contrib.columns:
        bucket = REGIME_OF_DRIVER[driver]
        col = contrib[driver]
        if bucket in reg:
            if cfg.merge_risk_proxies and bucket == "risk":
                reg[bucket] = reg[bucket].add(col, fill_value=0.0)
            else:
                # keep the larger contributor for non-merged duplicate buckets
                reg[bucket] = np.fmax(reg[bucket], col)
        else:
            reg[bucket] = col
    return reg


def assign_macro_regimes(panel: pd.DataFrame,
                         config: RegimeConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """
    MAIN ENTRY POINT.  Given a daily driver panel (from build_driver_panel),
    return a regime-labelled DataFrame indexed by date with the columns the
    Step-3 brief asks for.

    The emitted label uses `config.primary_window`.  Short/medium/long window
    diagnostics are attached with suffixes so the full picture is inspectable.
    """
    cfg = config
    # keep only drivers whose column was actually produced (e.g. rate_diff_10y
    # exists only after the bond-futures pull) -> graceful pre/post-futures.
    drivers = [d for d in cfg.drivers if d in panel.columns]
    dropped = [d for d in cfg.drivers if d not in panel.columns]
    if dropped:
        print(f"[macro_regime] drivers not in panel, skipped: {dropped} "
              f"(rates_source={panel.attrs.get('rates_source','?')})")

    # run every window on the FULL driver set — the macro betas here are PARTIAL
    # (each controlled for every other driver incl. USD & the commodity-bloc
    # co-move), which is exactly what the idiosyncratic contest needs.
    roll = {w: rolling_regression(panel, drivers, win, cfg.min_abs_beta)
            for w, win in cfg.windows.items()}

    prim = cfg.primary_window
    contrib = roll[prim]["contrib"]
    beta = roll[prim]["beta"]
    corr = roll[prim]["corr"]
    tstat = roll[prim]["tstat"]
    r2 = roll[prim]["r2"]

    reg_contrib = _regime_contrib_frame(contrib, cfg)

    def _contest(frame: pd.DataFrame):
        """idxmax / max / 2nd-best over a regime-contribution frame, NaN-safe."""
        valid = frame.notna().any(axis=1)
        top_r = pd.Series(index=frame.index, dtype="object")
        top_v = pd.Series(index=frame.index, dtype="float64")
        top_r[valid] = frame[valid].idxmax(axis=1)
        top_v[valid] = frame[valid].max(axis=1)

        def second_best(row):
            s = row.dropna().sort_values(ascending=False)
            return (s.index[1], s.iloc[1]) if len(s) > 1 else (np.nan, np.nan)
        sb = frame.apply(second_best, axis=1, result_type="expand")
        sb.columns = ["second_regime", "second_val"]
        dom = top_v / sb["second_val"].replace(0, np.nan).abs()
        return top_r, top_v, sb, dom

    # --- full contest: regional_fx allowed to win (it usually does) ----------
    top_regime, top_val, sb, dominance = _contest(reg_contrib)

    # --- idiosyncratic contest: net of USD & the bloc, which AUD-specific -----
    #     driver (china/commodity/risk/rates) has the largest PARTIAL share -----
    macro_cols = [b for b in cfg.macro_buckets if b in reg_contrib.columns]
    macro_contrib = reg_contrib[macro_cols]
    m_top_regime, m_top_val, m_sb, m_dominance = _contest(macro_contrib)

    # ---- apply thresholds (full contest -> macro_regime) -------------------
    regime = top_regime.copy()
    low = (r2 < cfg.min_r2) | (top_val <= 0) | top_val.isna()
    regime[low] = "low_signal"

    # ---- idiosyncratic regime (USD & regional netted out) ------------------
    # gated on its OWN explained share, not the full-model R² (which is huge
    # thanks to USD/NZD).  A small min share keeps only days where an
    # idiosyncratic driver genuinely contributes.
    macro_regime_ex = m_top_regime.copy()
    low_m = (m_top_val <= cfg.min_idio_contrib) | m_top_val.isna()
    macro_regime_ex[low_m] = "low_signal"

    # dominant driver name (within the winning regime) for explainability
    def dominant_driver(row):
        c = contrib.loc[row.name]
        winners = [d for d in drivers if REGIME_OF_DRIVER[d] == row["regime"]]
        if not winners or row["regime"] == "low_signal":
            return np.nan
        sub = c[winners]
        if sub.isna().all():
            return np.nan
        return sub.idxmax()

    out = pd.DataFrame(index=panel.index)
    out["audusd_ret"] = panel["audusd_ret"]
    out["macro_regime"] = regime.astype("object")
    out["idio_regime"] = macro_regime_ex.astype("object")
    out["rolling_r2"] = r2
    out["dominant_regime_contribution"] = top_val
    out["second_strongest_regime"] = sb["second_regime"]
    out["second_regime_contribution"] = sb["second_val"]
    out["dominance_ratio"] = dominance
    # idiosyncratic contest diagnostics (partial R² share of the winning driver)
    out["macro_ex_contribution"] = m_top_val
    out["macro_ex_dominance"] = m_dominance
    # regional co-movement measure (how much the bloc twin explains AUD)
    out["regional_contribution"] = reg_contrib[cfg.regional_bucket] \
        if cfg.regional_bucket in reg_contrib.columns else np.nan

    tmp = out[["macro_regime"]].rename(columns={"macro_regime": "regime"})
    out["dominant_driver"] = tmp.apply(dominant_driver, axis=1)

    # dominant driver's beta / corr / t-stat (explainability of the label)
    def _pick(frame, key_col):
        vals = []
        for dt, dv in out["dominant_driver"].items():
            vals.append(frame.at[dt, dv] if isinstance(dv, str) and dv in frame.columns else np.nan)
        return pd.Series(vals, index=out.index, name=key_col)
    out["dominant_beta"] = _pick(beta, "dominant_beta")
    out["dominant_corr"] = _pick(corr, "dominant_corr")
    out["dominant_tstat"] = _pick(tstat, "dominant_tstat")

    # confidence score: R² gated by dominance (both in [0,1]-ish); simple, bounded
    dom_clip = dominance.clip(upper=3.0).fillna(0) / 3.0
    out["confidence_score"] = (r2.clip(0, 1) * (0.5 + 0.5 * dom_clip)).where(
        out["macro_regime"] != "low_signal", 0.0)

    # regime stability: share of the trailing stability_win days with same label
    lbl = out["macro_regime"]
    same = pd.Series(index=out.index, dtype="float64")
    codes = lbl.astype("category").cat.codes.to_numpy()
    win = cfg.stability_win
    for i in range(len(codes)):
        a = codes[max(0, i - win + 1): i + 1]
        same.iloc[i] = np.mean(a == codes[i]) if len(a) else np.nan
    out["regime_stability"] = same

    # regime duration: length of current uninterrupted run up to t
    dur = np.ones(len(lbl), dtype=int)
    lc = lbl.to_numpy()
    for i in range(1, len(lc)):
        if lc[i] == lc[i - 1]:
            dur[i] = dur[i - 1] + 1
    out["regime_duration"] = dur

    # attach short/long window regime labels for robustness inspection
    for w in cfg.windows:
        if w == prim:
            continue
        rc = _regime_contrib_frame(roll[w]["contrib"], cfg)
        valid = rc.notna().any(axis=1)
        tr = pd.Series(index=rc.index, dtype="object")
        tv = pd.Series(index=rc.index, dtype="float64")
        tr[valid] = rc[valid].idxmax(axis=1)
        tv[valid] = rc[valid].max(axis=1)
        lowr = (roll[w]["r2"] < cfg.min_r2) | (tv <= 0) | tv.isna()
        tr = tr.astype("object")
        tr[lowr] = "low_signal"
        out[f"regime_{w}"] = tr
        out[f"r2_{w}"] = roll[w]["r2"]

    out.attrs["roll"] = roll
    out.attrs["reg_contrib"] = reg_contrib
    out.attrs["config"] = cfg
    return out


def shift_for_prediction(regime_df: pd.DataFrame, lag: int = 1) -> pd.DataFrame:
    """
    Return a copy whose label columns are lagged by `lag` business days so they
    can be used to CONDITION forward outcomes without look-ahead (the label at
    row t then reflects information available at t-lag).
    """
    label_cols = [c for c in regime_df.columns
                  if c.startswith("macro_regime") or c.startswith("regime_")
                  or c in ("dominant_driver", "confidence_score", "rolling_r2")]
    out = regime_df.copy()
    out[label_cols] = out[label_cols].shift(lag)
    return out


# --------------------------------------------------------------------------- #
# Comparison methods (secondary cross-checks)
# --------------------------------------------------------------------------- #
def corr_dominance_regime(panel: pd.DataFrame, cfg: RegimeConfig) -> pd.Series:
    """
    Simplest cross-check of the idiosyncratic label: regime = bucket of the
    idiosyncratic driver (china/commodity/risk/rates) with the largest |rolling
    corr| to AUDUSD.  Restricted to the same buckets as idio_regime so the
    agreement number is meaningful.
    """
    win = cfg.windows[cfg.primary_window]
    drivers = [d for d in cfg.drivers if REGIME_OF_DRIVER[d] in cfg.macro_buckets]
    y = panel["audusd_ret"]
    cc = pd.DataFrame({d: y.rolling(win).corr(panel[d]) for d in drivers})
    reg = pd.DataFrame(index=cc.index)
    for d in drivers:
        b = REGIME_OF_DRIVER[d]
        reg[b] = np.fmax(reg[b], cc[d].abs()) if b in reg else cc[d].abs()
    valid = reg.notna().any(axis=1)
    lab = pd.Series("low_signal", index=reg.index, dtype="object")
    lab[valid] = reg[valid].idxmax(axis=1)
    lab[reg.max(axis=1) < 0.10] = "low_signal"
    return lab.rename("regime_corr")


def pca_dominance_regime(panel: pd.DataFrame, cfg: RegimeConfig) -> pd.Series:
    """
    Rolling PCA of the driver returns; regime = bucket of the driver most loaded
    on PC1 in the window (a black-box cross-check that ignores AUDUSD itself).
    """
    from numpy.linalg import svd
    win = cfg.windows[cfg.primary_window]
    drivers = [d for d in cfg.drivers if REGIME_OF_DRIVER[d] in cfg.macro_buckets]
    X = panel[drivers].to_numpy("float64")
    idx = panel.index
    out = pd.Series(index=idx, dtype="object")
    for t in range(win - 1, len(idx)):
        W = X[t - win + 1: t + 1]
        m = np.all(np.isfinite(W), axis=1)
        if m.sum() < win // 2:
            continue
        Wc = W[m] - W[m].mean(0)
        sd = Wc.std(0, ddof=0)
        sd[sd < 1e-12] = 1.0
        Wc = Wc / sd
        try:
            _, _, Vt = svd(Wc, full_matrices=False)
        except np.linalg.LinAlgError:
            continue
        load = np.abs(Vt[0])
        out.iloc[t] = REGIME_OF_DRIVER[drivers[int(load.argmax())]]
    return out.rename("regime_pca")


def rules_based_regime(levels: pd.DataFrame, panel: pd.DataFrame,
                       cfg: RegimeConfig) -> pd.Series:
    """
    Transparent hand rules (no fitting), evaluated causally on trailing windows:
      * risk-off   : VIX high (z>1) and rising           -> risk
      * USD trend  : |21d DXY move| large & > other moves -> usd
      * China      : |21d USDCNY move| large              -> china
      * commodity  : |63d oil move| large                 -> commodity
      * else       : regional_fx if AUD-NZD corr high, else low_signal
    Priority order encodes a simple macro narrative; purely for comparison.
    """
    idx = panel.index
    out = pd.Series("low_signal", index=idx, dtype="object")
    vix = levels["vix"]
    vix_z = (vix - vix.rolling(252).mean()) / vix.rolling(252).std()
    vix_up = vix.diff(5) > 0
    dxy_m = np.log(levels["dxy_broad"]).diff(21).abs()
    cny_m = np.log(levels["usdcny"]).diff(21).abs()
    oil_m = np.log(levels["oil_wti"]).diff(63).abs()
    nzd_corr = panel["audusd_ret"].rolling(cfg.windows[cfg.primary_window]).corr(panel["nzdusd"])

    out[(nzd_corr > 0.6)] = "regional_fx"
    out[(oil_m > oil_m.rolling(252).median() * 1.5)] = "commodity"
    out[(cny_m > cny_m.rolling(252).quantile(0.8))] = "china"
    out[(dxy_m > dxy_m.rolling(252).quantile(0.8))] = "usd"
    out[(vix_z > 1.0) & vix_up] = "risk"
    return out.rename("regime_rules")


def cluster_regime(regime_df: pd.DataFrame, cfg: RegimeConfig, k: int = 6) -> pd.Series:
    """
    Unsupervised KMeans on the rolling driver-strength features (per-driver
    contributions + r2).  Clusters are then *named* by their dominant mean
    contribution so they line up with the macro buckets.  Purely a cross-check;
    KMeans is not causal within-fit but is applied only for descriptive
    comparison, never as a live label.
    """
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    reg_contrib = regime_df.attrs["reg_contrib"]
    feat = reg_contrib.copy()
    feat["r2"] = regime_df["rolling_r2"]
    feat = feat.dropna()
    if len(feat) < k * 10:
        return pd.Series(index=regime_df.index, dtype="object", name="regime_cluster")
    Xs = StandardScaler().fit_transform(feat.values)
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(Xs)
    lab = pd.Series(km.labels_, index=feat.index)
    # name each cluster by its dominant mean contribution, restricted to the
    # idiosyncratic buckets so it lines up with idio_regime for comparison.
    macro_cols = [c for c in cfg.macro_buckets if c in reg_contrib.columns]
    names = {}
    for c in range(k):
        m = reg_contrib.loc[lab.index[lab == c], macro_cols].mean()
        names[c] = m.idxmax() if m.notna().any() else "low_signal"
    named = lab.map(names)
    return named.reindex(regime_df.index).rename("regime_cluster")


# --------------------------------------------------------------------------- #
# Post-hoc diagnostics
# --------------------------------------------------------------------------- #
def _ordered_cats(a: pd.Series) -> list:
    """Categories present, ordered by ALL_REGIMES first then any extras (so this
    works for the Step-3 market vocabulary AND arbitrary label sets, e.g. the
    fundamental econ regimes)."""
    present = set(a)
    ordered = [r for r in ALL_REGIMES if r in present]
    extras = [r for r in dict.fromkeys(a.tolist()) if r not in ALL_REGIMES]
    return ordered + extras


def transition_matrix(labels: pd.Series, normalize: bool = True) -> pd.DataFrame:
    """Period-to-period regime transition counts / probabilities."""
    a = labels.dropna()
    frm = a.iloc[:-1].to_numpy()
    to = a.iloc[1:].to_numpy()
    cats = _ordered_cats(a)
    mat = pd.DataFrame(0.0, index=cats, columns=cats)
    for f, t in zip(frm, to):
        if f in mat.index and t in mat.columns:
            mat.at[f, t] += 1
    if normalize:
        mat = mat.div(mat.sum(axis=1).replace(0, np.nan), axis=0)
    return mat


def persistence_stats(labels: pd.Series) -> pd.DataFrame:
    """Per-regime frequency, mean/median run length, and self-transition prob."""
    a = labels.dropna()
    # run lengths
    runs = []
    cur, cnt = None, 0
    for v in a:
        if v == cur:
            cnt += 1
        else:
            if cur is not None:
                runs.append((cur, cnt))
            cur, cnt = v, 1
    if cur is not None:
        runs.append((cur, cnt))
    rdf = pd.DataFrame(runs, columns=["regime", "len"])
    tm = transition_matrix(a, normalize=True)
    rows = []
    for r in _ordered_cats(a):
        lens = rdf.loc[rdf["regime"] == r, "len"]
        rows.append({
            "regime": r,
            "days": int((a == r).sum()),
            "frequency": float((a == r).mean()),
            "n_runs": int(len(lens)),
            "mean_run_len": float(lens.mean()) if len(lens) else 0.0,
            "median_run_len": float(lens.median()) if len(lens) else 0.0,
            "max_run_len": int(lens.max()) if len(lens) else 0,
            "self_transition_prob": float(tm.at[r, r]) if r in tm.index else np.nan,
        })
    return pd.DataFrame(rows).set_index("regime")


if __name__ == "__main__":
    lv = load_levels()
    panel = build_driver_panel(lv)
    print("driver panel:", panel.shape, "range", panel.index.min().date(),
          "->", panel.index.max().date())
    reg = assign_macro_regimes(panel)
    sub = reg.loc["2013-01-01":]
    print("\nFULL contest — macro_regime frequency (2013+):")
    print(sub["macro_regime"].value_counts(normalize=True).round(3).to_string())
    print("\nMACRO-ONLY contest — idio_regime frequency (2013+):")
    print(sub["idio_regime"].value_counts(normalize=True).round(3).to_string())
    print("\npersistence of idio_regime (2013+):")
    print(persistence_stats(sub["idio_regime"]).round(3).to_string())
    print("\nmean rolling R² (2013+): %.3f" % sub["rolling_r2"].mean())
    print("mean regional (NZD) contribution: %.3f" % sub["regional_contribution"].mean())
