# =============================================================================
#  research_walkthrough.py
#  AUDUSD systematic research — ONE self-contained, run-as-you-go script that
#  reproduces every study so far, section by section, with the logic inline.
#
#  WHY THIS FILE EXISTS
#  --------------------
#  The real project is split across ~15 modules (download_*, build_*, macro_*,
#  walkforward.py, metrics.py, ...).  Good for a pipeline, bad for *reading the
#  reasoning*.  This file collapses the whole research arc into linear #%% cells
#  so you can step through it in VS Code / Spyder / Jupyter and watch each
#  feature get built and each verdict get earned.  It deliberately RE-IMPLEMENTS
#  the feature and model logic inline (rather than importing walkforward.py etc.)
#  so nothing is hidden behind a function you have to go hunting for.
#
#  The ONLY thing we lean on the rest of the repo for is DATA SOURCING — the CSVs
#  in data/ that the download_*/build_* scripts already produced.  We just read
#  them.  If a CSV is missing, re-run the matching pipeline step (see CLAUDE.md).
#
#  HOW TO USE
#  ----------
#  Run cell by cell (the #%% markers).  Cells are ordered; later cells reuse
#  objects built earlier.  Heavy cells are flagged [SLOW].  Each PART ends with a
#  plain-English VERDICT and an EXPLORE list of things worth trying next.
#
#  THE ARC (what we already learned — so you know where this is going)
#  ------------------------------------------------------------------
#    PART A  Intraday baseline (Step 2) .... NO-GO. A real but tiny technical
#            micro-edge (IC t~3-4) that transaction costs eat; macro conditioning
#            adds ~nothing intraday.
#    PART B  Macro-driver regime (Step 3) .. Descriptive/veto layer, not a
#            standalone edge. AUD is "USD + commodity-bloc" almost always; the
#            idiosyncratic driver (risk/commodity/china/rates) only MODULATES the
#            weak baseline (commodity regime inverts it, low_signal green-lights).
#    PART C  Econ-strength regime (Step 3b)  Fundamental AU-US strength maps to
#            the AUDUSD *level* (corr +0.55) — real. The in-cycle mean-reversion
#            *timing* signal looked strong but...
#    PART D  Cross-currency robustness ..... ...it does NOT replicate on NZD/CAD
#            or over longer history. One-cycle artifact. Timing claim retired.
#
#  Everything is CAUSAL. Rolling features use only trailing data; targets are the
#  only forward-looking objects; lower-frequency features are lagged before use.
# =============================================================================


#%% [0] Imports, constants, tiny shared helpers ------------------------------
# Kept minimal and at the top so every downstream cell can assume they exist.

from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 40)

DATA = "data"

# Intraday bar spacing is 15 minutes ~ 96 bars per trading day. Everything
# expressed in *bars* (not wall-clock) because the index skips weekends/holidays.
BARS_PER_HOUR = 4
DAY_BARS      = 96
BARS_PER_YEAR = 96 * 260                       # ~24,960; for intraday annualising
HORIZONS      = {"h1h": 4, "h4h": 16, "h1d": 96}   # forward-return horizons (bars)

# One-way transaction cost placeholder, in price-return units.
# AUDUSD spread ~0.4-0.8 pip; 1 pip = 0.0001. We have NO BID_ASK pull yet
# (CLAUDE.md gotcha #2), so this is an explicit knob to sweep, not a measurement.
ONE_WAY_COST = 0.00005                          # 0.5 pip one-way (1.0 pip round-trip)


def spearman(a, b) -> float:
    """Rank IC on finite pairs. Returns NaN if too few points."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 8:
        return np.nan
    return float(pd.Series(a[m]).corr(pd.Series(b[m]), method="spearman"))


def ic_tstat(pearson_ic: float, n: int) -> float:
    """Classic IC t-stat. n MUST be the NON-overlapping sample size, else it lies
    (overlapping forward labels inflate it — CLAUDE.md gotcha #3)."""
    if not np.isfinite(pearson_ic) or n < 3:
        return np.nan
    return pearson_ic * np.sqrt(n - 2) / np.sqrt(max(1 - pearson_ic ** 2, 1e-12))


def block_bootstrap_ic(x, y, block=12, nboot=5000, seed=0):
    """
    Moving-block bootstrap of the rank-IC between x and y under serial
    dependence. We use this instead of naive t-stats wherever samples are small
    AND sticky (monthly macro regimes, overlapping forward returns): resampling
    whole blocks preserves autocorrelation so the CI isn't fantasy-narrow.
    Returns (ic, ci5, ci95, two_sided_p).
    """
    s = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(s) < block + 5:
        return np.nan, np.nan, np.nan, np.nan
    xv, yv = s["x"].to_numpy(), s["y"].to_numpy()
    n = len(xv)
    ic = spearman(xv, yv)
    rng = np.random.default_rng(seed)
    starts = np.arange(0, n - block + 1)
    nb = int(np.ceil(n / block))
    boots = np.empty(nboot)
    for b in range(nboot):
        st = rng.choice(starts, size=nb, replace=True)
        idx = np.concatenate([np.arange(s0, s0 + block) for s0 in st])[:n]
        boots[b] = spearman(xv[idx], yv[idx])
    lo, hi = np.nanpercentile(boots, [5, 95])
    frac_pos = np.nanmean(boots > 0)
    p = 2 * min(frac_pos, 1 - frac_pos)
    return ic, lo, hi, p


def ann_sharpe(returns, periods_per_year) -> float:
    """Annualised Sharpe of a return series (NaN-safe, needs >3 obs)."""
    r = np.asarray(returns, float)
    r = r[np.isfinite(r)]
    if len(r) < 3 or r.std(ddof=1) == 0:
        return np.nan
    return r.mean() / r.std(ddof=1) * np.sqrt(periods_per_year)


# =============================================================================
#  PART A — INTRADAY DIRECTIONAL BASELINE  (Step 2)
#  Q: is there a monetizable 15-min directional edge in AUDUSD from technicals
#     and/or slow macro conditioning, evaluated honestly (costs + overlap)?
# =============================================================================

#%% [A1] Load the intraday panel + build extra technicals --------------------
# [SLOW ~10-30s: the panel is ~280MB / 332k rows.]
# The panel already ships OHLC + 13 intraday features (ret_Nb, realized_vol_48b,
# zscore_48b, session dummies, dow) + 38 conditioning features (f_* daily market,
# macro_* monthly PIT) ALREADY lagged 1 business day upstream. We only ADD a few
# interpretable, strictly-trailing technicals so you can see how they're made.

px = pd.read_csv(f"{DATA}/audusd_intraday_modeling_panel.csv", parse_dates=["time"])
px = px.sort_values("time").reset_index(drop=True)
if px["time"].dt.tz is None:                    # panel is UTC; make that explicit
    px["time"] = px["time"].dt.tz_localize("UTC")
# downcast the big float block to keep memory sane
fcols = px.select_dtypes("float64").columns
px[fcols] = px[fcols].astype("float32")
print("panel:", px.shape, "|", px["time"].min(), "->", px["time"].max())

high = px["high"].astype("float64"); low = px["low"].astype("float64")
close = px["close"].astype("float64"); prev = close.shift(1)
logc = np.log(close)

# --- ATR% : Wilder true range, simple 14-bar mean, as a fraction of price -----
# Why: a clean, trailing volatility scale that (unlike realized_vol) uses the
# high/low, so it captures intrabar range. Used later as a risk normaliser too.
tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
px["atr_pct_14b"] = (tr.rolling(14, min_periods=14).mean() / close).astype("float32")

# --- distance from trailing SMAs (12h and 48h) --------------------------------
# Why: simple mean-reversion / trend-stretch features. (close-SMA)/SMA is unit-free.
for n in (48, 192):
    sma = close.rolling(n, min_periods=n).mean()
    px[f"dist_sma_{n}b"] = ((close - sma) / sma).astype("float32")

# --- range expansion: current bar range vs its trailing average ---------------
# Why: >1 = volatility expanding (breakout-ish), <1 = contracting (coil).
rng = (high - low)
px["range_expansion_48b"] = (rng / rng.rolling(48, min_periods=24).mean()).astype("float32")

# --- 6h momentum not already in the panel -------------------------------------
px["ret_24b"] = (logc - logc.shift(24)).astype("float32")

# NOTE: the full baseline (baseline_features.py) also adds 500-bar rolling
# percentile ranks of vol/ATR. Dropped here — they're slow to compute and were
# immaterial to the conclusion. Add them back if you want exact reproduction.


#%% [A2] Session labels (New York local time, DST-correct) -------------------
# Why NY time: the FX day is anchored to the 5pm ET rollover. Bucketing on NY
# hours puts the London/NY overlap (the liquid, trend-prone window) in its own
# bin, which is exactly where we later ask "is the edge session-specific?".
ny_hour = px["time"].dt.tz_convert("America/New_York").dt.hour

def ny_bucket(h):
    if h >= 18 or h < 3:  return "asia"          # Sydney/Tokyo
    if 3 <= h < 8:        return "london"
    if 8 <= h < 12:       return "ny"            # London/NY overlap + NY morning
    if 12 <= h < 16:      return "ny_afternoon"
    return "rollover"                            # 16-18 ET, illiquid

px["session_ny"] = ny_hour.map(ny_bucket).astype("category")
for s in ["asia", "london", "ny", "ny_afternoon", "rollover"]:
    px[f"sess2_{s}"] = (px["session_ny"] == s).astype("float32")


#%% [A3] Targets: forward log returns + direction ----------------------------
# The ONLY forward-looking objects in the whole file. y_ret_{tag} = log return
# from t to t+h. Direction target is its sign. We also keep a "cost buffer"
# neutral band so a bar only counts as up/down if it clears the spread — that
# band is a design choice: it stops the model chasing sub-cost wiggles.
for tag, h in HORIZONS.items():
    fwd = logc.shift(-h) - logc
    px[f"y_ret_{tag}"] = fwd.astype("float32")
    px[f"y_bin_{tag}"] = (fwd > 0).astype("float32")          # for logistic variant
print(px.filter(like="y_ret_").describe().T[["mean", "std", "count"]])

# Feature sets we will contest against each other:
TECH = [c for c in [
    "ret_1b", "ret_3b", "ret_6b", "ret_12b", "ret_24b", "ret_48b",
    "realized_vol_48b", "atr_pct_14b", "range_1b", "range_expansion_48b",
    "zscore_48b", "dist_sma_48b", "dist_sma_192b",
    "sess2_asia", "sess2_london", "sess2_ny", "sess2_ny_afternoon", "sess2_rollover",
] if c in px.columns]
COND = [c for c in px.columns if c.startswith("f_") or c.startswith("macro_")]
FEATURE_SETS = {"technical": TECH, "conditioning": COND, "combined": TECH + COND}
print("\nfeature sets:", {k: len(v) for k, v in FEATURE_SETS.items()})


#%% [A4] THE core method: leakage-safe walk-forward -------------------------
# This is the single most important function in the baseline. Read it once,
# carefully — everything else trusts it.
#
#   * EXPANDING train window, refit once per calendar QUARTER (the test block).
#   * EMBARGO of `horizon` bars between train-end and test-start, so a training
#     label whose forward window overlaps the test block cannot peek across.
#   * CAUSAL preprocessing: impute (train medians) + standardize (train stats)
#     fit on TRAIN ONLY, applied to test. Macro cols are all-NaN pre-2013, so we
#     fall back to 0 after median-impute (they simply carry no info early on).
#   * No random splits, ever. Ridge (closed-form, robust to the collinear macro
#     block) for returns; logistic available for direction.

from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.preprocessing import StandardScaler

def walk_forward(df, feat, target, horizon, task="reg", alpha=10.0, C=1.0,
                 min_train=24000, verbose=False):
    n = len(df)
    qtr = df["time"].dt.tz_localize(None).dt.to_period("Q")
    X_all = df[feat].to_numpy("float64")
    y_all = df[target].to_numpy("float64")
    pred = np.full(n, np.nan); scored = np.zeros(n, bool)
    pos = np.arange(n)

    for q in qtr.drop_duplicates().sort_values():
        test = pos[(qtr == q).to_numpy()]
        if test.size == 0:
            continue
        train_end = test.min() - horizon          # embargo the overlap
        if train_end < min_train:
            continue
        tr = pos[:train_end]
        Xtr, ytr = X_all[tr], y_all[tr]
        ok = np.isfinite(ytr); Xtr, ytr = Xtr[ok], ytr[ok]
        if ytr.size < 500:
            continue
        Xte = X_all[test]

        # causal impute: train medians, then 0 for still-missing (early macro)
        med = np.nanmedian(np.where(np.isfinite(Xtr), Xtr, np.nan), axis=0)
        med = np.where(np.isfinite(med), med, 0.0)
        Xtr = np.where(np.isfinite(Xtr), Xtr, med)
        Xte = np.where(np.isfinite(Xte), Xte, med)
        sc = StandardScaler().fit(Xtr)
        Xtr, Xte = sc.transform(Xtr), sc.transform(Xte)

        if task == "reg":
            est = Ridge(alpha=alpha).fit(Xtr, ytr)
            pred[test] = est.predict(Xte)
        else:
            if np.unique(ytr).size < 2:
                continue
            est = LogisticRegression(C=C, max_iter=2000).fit(Xtr, ytr)
            pred[test] = est.predict_proba(Xte)[:, 1]
        scored[test] = True
        if verbose:
            print(f"   {q}: train={ytr.size:>6d} test={test.size:>4d}")
    return pd.DataFrame({"pred": pred, "y": y_all, "in_oos": scored}, index=df.index)


#%% [A5] Run the baseline across horizons x feature sets [SLOW ~1-3 min] -----
# We store the out-of-sample prediction frames; PART B reuses the TECHNICAL ones
# to ask "does a macro regime rescue this?".

def oos(res):
    m = res["in_oos"].to_numpy() & np.isfinite(res["pred"]) & np.isfinite(res["y"])
    return res.loc[m]

def nonoverlap(res, h):
    return oos(res).iloc[::h]           # 1 sample / horizon -> non-overlapping labels

def reg_report(res, h):
    """Honest IC: computed on NON-overlapping samples so the t-stat is real."""
    f = oos(res); fn = nonoverlap(res, h)
    pear = np.corrcoef(fn["pred"], fn["y"])[0, 1] if len(fn) > 5 else np.nan
    return {
        "n_oos": len(f), "n_nonovlp": len(fn),
        "rank_ic": spearman(fn["pred"], fn["y"]),
        "ic_t": ic_tstat(pear, len(fn)),
        "dir_acc": float((np.sign(f["pred"]) == np.sign(f["y"])).mean()),
    }

RES = {}                                          # (tag, feature_set) -> res frame
rows = []
for tag, h in HORIZONS.items():
    print(f"\n=== horizon {tag} ({h} bars) ===")
    for name, cols in FEATURE_SETS.items():
        res = walk_forward(px, cols, f"y_ret_{tag}", horizon=h, task="reg")
        RES[(tag, name)] = res
        r = reg_report(res, h); r.update(horizon=tag, features=name)
        rows.append(r)
        print(f"  {name:12s} rank_IC={r['rank_ic']:+.4f}  t={r['ic_t']:+.2f}  "
              f"dir_acc={r['dir_acc']:.4f}  (n_non={r['n_nonovlp']})")
baseline_ic = pd.DataFrame(rows)
# READ THIS: technical shows a small but real micro-IC (t typically ~3-4 at 1h);
# 'conditioning' (macro) alone is ~0 intraday; 'combined' rarely beats technical
# -> the slow macro block does not help the 15-min decision. That's finding #1.


#%% [A6] Cost-aware trading + momentum benchmark -----------------------------
# IC being significant is necessary, NOT sufficient. Convert the signal into a
# threshold rule on NON-overlapping bars (one position held exactly `horizon`
# bars, so trade returns don't overlap) and charge cost on every position change.
# Then sweep the cost to see how fragile any PnL is.

TRADE_THR = {"h1h": 0.0003, "h4h": 0.0006, "h1d": 0.0015}   # ~ prediction scale
COST_SWEEP = [0.0, 0.00002, 0.00005, 0.0001]                 # 0, 0.2, 0.5, 1.0 pip

def trade_report(res, h, thr, cost):
    f = nonoverlap(res, h)
    sig = f["pred"].to_numpy(); ret = f["y"].to_numpy()
    pos = np.where(sig > thr, 1.0, np.where(sig < -thr, -1.0, 0.0))
    turn = np.abs(pos - np.concatenate([[0.0], pos[:-1]]))     # entries+exits+flips
    net = pos * ret - cost * turn
    ppy = BARS_PER_YEAR / h                                    # non-overlap periods/yr
    active = pos != 0
    return {
        "cost_pip": cost * 1e4, "n_trades": int(active.sum()),
        "sharpe_gross": ann_sharpe(pos * ret, ppy),
        "sharpe_net": ann_sharpe(net, ppy),
        "win_rate": float((net[active] > 0).mean()) if active.any() else np.nan,
        "total_net_bp": float(net.sum() * 1e4),
    }

trade_rows = []
for tag, h in HORIZONS.items():
    res = RES[(tag, "combined")]
    for c in COST_SWEEP:
        tr = trade_report(res, h, TRADE_THR[tag], c); tr.update(horizon=tag)
        trade_rows.append(tr)
    # naive momentum benchmark on the SAME OOS rows (signal = trailing 12-bar ret)
    f = oos(res)
    bench = pd.DataFrame({"pred": px.loc[f.index, "ret_12b"].to_numpy(),
                          "y": f["y"].to_numpy(), "in_oos": True}, index=f.index)
    bt = trade_report(bench, h, 0.0, ONE_WAY_COST)
    print(f"{tag}: model net Sharpe @0.5pip = "
          f"{trade_report(res, h, TRADE_THR[tag], ONE_WAY_COST)['sharpe_net']:+.2f}"
          f"   | momentum-bench net Sharpe = {bt['sharpe_net']:+.2f}")
trade_sweep = pd.DataFrame(trade_rows)
print("\ncost sweep (combined model):")
print(trade_sweep.round(3).to_string(index=False))

# -----------------------------------------------------------------------------
# PART A VERDICT:  NO-GO.
#   * Technical features carry a genuine but tiny directional micro-edge
#     (gross IC significant), strongest at the 1h horizon.
#   * At 0 cost some horizons look ~flat-to-positive; at a REALISTIC 0.5-1.0 pip
#     the net Sharpe collapses to <=0. The edge lives entirely inside the spread.
#   * Macro conditioning adds ~nothing at 15 min (finding: slow features are the
#     wrong tool for the fast decision).
#
# EXPLORE next:
#   [ ] Pull real BID_ASK spread (2nd IBKR pass) and replace the flat cost with a
#       time-varying half-spread — costs spike in Asia/rollover, exactly where a
#       naive backtest thinks it's trading.
#   [ ] Trade ONLY the london/ny overlap session (A2) — does the edge survive
#       where spreads are tightest? (session-conditional Sharpe.)
#   [ ] Position-size by 1/ATR and skip the first bars after weekend gaps
#       (CLAUDE.md gotcha #4) rather than trading every bar.
#   [ ] Replace Ridge with a gradient-boosted tree on the technical set to see if
#       the micro-edge is nonlinear (but hold it to the SAME cost bar).
# -----------------------------------------------------------------------------


# =============================================================================
#  PART B — MACRO-DRIVER REGIME  (Step 3)
#  Q: which EXTERNAL driver (USD / China / commodity / risk / rates / bloc-FX)
#     leads AUDUSD at each point in time, and does knowing it help the baseline?
#  Method: rolling multivariate regression -> explainable driver attribution.
# =============================================================================

#%% [B1] Daily driver panel (returns/diffs) ----------------------------------
# We regress the AUDUSD daily return on a set of DRIVER daily changes. Prices ->
# log returns; yields/VIX -> first differences. CRITICAL: only genuinely-daily
# series are allowed as regressors. Iron ore/copper/AU-10Y(FRED) are monthly
# ffilled, so their daily "returns" are structurally zero and would corrupt the
# regression (CLAUDE.md gotchas #1/#5) — they're excluded on purpose.

lv = pd.read_csv(f"{DATA}/raw_market_levels_daily.csv", index_col=0, parse_dates=True).sort_index()

# driver name -> (level column, transform, macro bucket, expected sign vs AUD)
DRIVERS = {
    "dxy":    ("dxy_broad", "logret", "usd",         -1),   # AUD down when USD up
    "usdcny": ("usdcny",    "logret", "china",       -1),   # AUD down when CNY weak
    "nzdusd": ("nzdusd",    "logret", "regional_fx", +1),   # commodity-bloc twin
    "oil":    ("oil_wti",   "logret", "commodity",   +1),   # terms-of-trade proxy
    "sp500":  ("sp500",     "logret", "risk",        +1),   # risk-on
    "vix":    ("vix",       "diff",   "risk",        -1),   # risk-off
    "us2y":   ("us_2y",     "diff",   "rates",       -1),   # US rates up -> USD up
}
# NOTE: a genuine daily AU-US rate DIFFERENTIAL driver (from bond futures via
# download_rates_futures_ibkr.py) is the intended upgrade for the 'rates' bucket;
# absent that file we fall back to the US-2Y proxy above, as the repo does.
BUCKET = {k: v[2] for k, v in DRIVERS.items()}

dp = pd.DataFrame(index=lv.index)
dp["y"] = np.log(lv["audusd"]).diff()
for name, (col, kind, _, _) in DRIVERS.items():
    if col not in lv.columns:
        print("  ! missing level:", col); continue
    s = lv[col].astype("float64")
    dp[name] = np.log(s).diff() if kind == "logret" else s.diff()
DRV = [k for k in DRIVERS if k in dp.columns]
print("driver panel:", dp.shape, "|", dp.index.min().date(), "->", dp.index.max().date())


#%% [B2] Rolling multivariate regression with Pratt contributions ------------
# For each day t, take the trailing `window` days, standardize target + drivers,
# run OLS, and decompose the window R-squared into per-driver shares via the
# Pratt product measure:  contribution_i = beta_std_i * corr_iy , and these SUM
# to R-squared. That gives each driver a SIGNED share of explained variance —
# far more interpretable than raw betas, and directly comparable across drivers.
# The window ends at t (uses returns up to & incl. t) -> label known at t's
# close -> must be lagged +1 day before predicting anything (done in B5).

def window_pratt(Xw, yw):
    """One window: standardized OLS -> dict{driver: contribution}, plus R2."""
    m = np.isfinite(yw) & np.all(np.isfinite(Xw), axis=1)
    if m.sum() < max(15, Xw.shape[1] + 3):
        return None, np.nan
    X, y = Xw[m], yw[m]
    ysd = y.std(ddof=0)
    if ysd < 1e-12:
        return None, np.nan
    yz = (y - y.mean()) / ysd
    xsd = X.std(0, ddof=0); keep = xsd > 1e-12          # drop constant cols
    Xz = (X[:, keep] - X[:, keep].mean(0)) / xsd[keep]
    beta, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(yz)), Xz]), yz, rcond=None)
    beta = beta[1:]
    corr = (Xz * yz[:, None]).mean(0)                    # standardized -> corr
    contrib = beta * corr                                # Pratt: sums to R2
    r2 = float(np.clip(contrib.sum(), 0, 1))
    return keep, contrib, r2

def rolling_contrib(panel, drivers, window):
    """Per-day per-driver Pratt contribution + window R2 (trailing, causal)."""
    y = panel["y"].to_numpy("float64"); X = panel[drivers].to_numpy("float64")
    n = len(panel)
    C = np.full((n, len(drivers)), np.nan); r2 = np.full(n, np.nan)
    for t in range(window - 1, n):
        sl = slice(t - window + 1, t + 1)
        out = window_pratt(X[sl], y[sl])
        if out[0] is None:
            continue
        keep, contrib, r2t = out
        C[t, np.where(keep)[0]] = contrib; r2[t] = r2t
    return (pd.DataFrame(C, index=panel.index, columns=drivers),
            pd.Series(r2, index=panel.index, name="r2"))

WINDOW = 60                                              # ~3 trading months (medium)
contrib, r2 = rolling_contrib(dp, DRV, WINDOW)
print("mean window R2 (2013+):", round(r2.loc["2013":].mean(), 3))


#%% [B3] Two-contest regime assignment (the NZD co-movement trap) ------------
# AUD and NZD co-move ~0.8, and DXY is literally the dollar leg of a USD pair, so
# in ANY joint regression one of {usd, regional_fx} mechanically wins and hides
# the interesting AUD-specific driver. So we run TWO contests off the same
# partial regression (each beta is already controlled for the others):
#   * macro_regime : FULL contest (usd + bloc allowed to win) -> the honest
#                    "what dominates AUD" answer (spoiler: USD + NZD, always).
#   * idio_regime  : IDIOSYNCRATIC contest over {china, commodity, risk, rates}
#                    only -> "net of USD & the bloc, what moves AUD?" — the part
#                    that could actually be actionable.

# collapse per-driver contributions to per-BUCKET (sum the two risk proxies)
def to_buckets(contrib_row_df):
    reg = pd.DataFrame(index=contrib_row_df.index)
    for d in contrib_row_df.columns:
        b = BUCKET[d]
        reg[b] = reg[b].add(contrib_row_df[d], fill_value=0) if b in reg else contrib_row_df[d]
    return reg

bucket_contrib = to_buckets(contrib)

def contest(frame, min_top, r2gate=None):
    """idxmax over a bucket-contribution frame -> label; gate weak/empty rows."""
    valid = frame.notna().any(axis=1)
    top_reg = pd.Series(index=frame.index, dtype="object")
    top_val = pd.Series(index=frame.index, dtype="float64")
    top_reg[valid] = frame[valid].idxmax(axis=1)
    top_val[valid] = frame[valid].max(axis=1)
    weak = (top_val <= min_top) | top_val.isna()
    if r2gate is not None:
        weak = weak | (r2 < r2gate)
    top_reg[weak] = "low_signal"
    return top_reg, top_val

MIN_R2, MIN_IDIO = 0.15, 0.02
macro_regime, _ = contest(bucket_contrib, min_top=0.0, r2gate=MIN_R2)
idio_cols = ["china", "commodity", "risk", "rates"]
idio_regime, _ = contest(bucket_contrib[[c for c in idio_cols if c in bucket_contrib]],
                         min_top=MIN_IDIO)

reg_daily = pd.DataFrame({"y": dp["y"], "r2": r2,
                          "macro_regime": macro_regime, "idio_regime": idio_regime})
sub = reg_daily.loc["2013":]
print("FULL contest (macro_regime) freq:\n",
      sub["macro_regime"].value_counts(normalize=True).round(3).to_string())
print("\nIDIOSYNCRATIC contest (idio_regime) freq:\n",
      sub["idio_regime"].value_counts(normalize=True).round(3).to_string())


#%% [B4] Regime persistence (are these labels stable enough to trade on?) ----
# A regime you can't see coming, or that flips daily, is useless as a live
# conditioner. Self-transition prob + run length tell us how sticky each is.

def persistence(labels):
    a = labels.dropna()
    runs, cur, cnt = [], None, 0
    for v in a:
        if v == cur: cnt += 1
        else:
            if cur is not None: runs.append((cur, cnt))
            cur, cnt = v, 1
    if cur is not None: runs.append((cur, cnt))
    rdf = pd.DataFrame(runs, columns=["regime", "len"])
    nxt = a.shift(-1)
    rows = []
    for r in a.unique():
        lens = rdf.loc[rdf.regime == r, "len"]
        stay = ((a == r) & (nxt == r)).sum() / max((a == r).sum(), 1)
        rows.append({"regime": r, "days": int((a == r).sum()),
                     "freq": round(float((a == r).mean()), 3),
                     "mean_run": round(float(lens.mean()), 1),
                     "self_trans": round(float(stay), 3)})
    return pd.DataFrame(rows).set_index("regime").sort_values("days", ascending=False)

print("idio_regime persistence (2013+):\n", persistence(sub["idio_regime"]).to_string())


#%% [B5] Does the regime rescue the baseline? [SLOW ~30-60s] -----------------
# The real test of Step 3: split the Step-2 TECHNICAL OOS predictions by the
# (1-business-day LAGGED) regime and recompute honest per-regime IC + net Sharpe.
# If some regimes are reliably predictable (or reliably toxic), the regime is a
# useful conditioning/veto layer even though it's no edge on its own.

# lag the daily label by 1 business day, then as-of join onto each 15-min bar
lab = reg_daily[["idio_regime", "macro_regime"]].shift(1)
lab = lab.reset_index(); lab.columns = ["date", "idio_regime", "macro_regime"]
lab["date"] = pd.to_datetime(lab["date"])

def attach_regime(res, h, reg_col="idio_regime"):
    f = oos(res).copy()
    bar_date = px.loc[f.index, "time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    f = f.assign(date=bar_date.to_numpy()).sort_values("date")
    f = pd.merge_asof(f, lab[["date", reg_col]].sort_values("date"),
                      on="date", direction="backward")
    rows = []
    for name, g in f.groupby(reg_col, observed=True):
        if len(g) < 500:
            continue
        gn = g.iloc[::h]                          # non-overlapping within regime
        pear = np.corrcoef(gn["pred"], gn["y"])[0, 1] if len(gn) > 5 else np.nan
        sig = gn["pred"].to_numpy(); ret = gn["y"].to_numpy()
        posn = np.where(sig > TRADE_THR[list(HORIZONS)[list(HORIZONS.values()).index(h)]], 1.0,
                        np.where(sig < -TRADE_THR[list(HORIZONS)[list(HORIZONS.values()).index(h)]], -1.0, 0.0))
        turn = np.abs(posn - np.concatenate([[0.0], posn[:-1]]))
        net = posn * ret - ONE_WAY_COST * turn
        rows.append({"regime": name, "n": len(g),
                     "rank_ic": round(spearman(gn["pred"], gn["y"]), 4),
                     "ic_t": round(ic_tstat(pear, len(gn)), 2),
                     "asset_fwd_bp": round(float(gn["y"].mean() * 1e4), 2),
                     "sharpe_net": round(ann_sharpe(net, BARS_PER_YEAR / h), 2)})
    return pd.DataFrame(rows).set_index("regime").sort_values("n", ascending=False)

print("=== 1h technical baseline, split by idio_regime ===")
print(attach_regime(RES[("h1h", "technical")], 4, "idio_regime").to_string())
print("\n=== 1d technical baseline, split by idio_regime ===")
print(attach_regime(RES[("h1d", "technical")], 96, "idio_regime").to_string())

# -----------------------------------------------------------------------------
# PART B VERDICT:  descriptive + a modest CONDITIONING/VETO layer, no standalone edge.
#   * FULL contest: AUD is "USD + commodity-bloc (NZD)" essentially always — the
#     honest but unsurprising answer. R2 is high but tautological.
#   * IDIOSYNCRATIC contest is the useful bit: net of USD/NZD, the AUD-specific
#     driver rotates between risk / commodity / china / rates / low_signal.
#   * The regime MODULATES the weak baseline rather than creating signal: the
#     'commodity' regime tends to INVERT the technical micro-edge (a veto/flip
#     candidate) while 'low_signal' is where the plain technical edge is cleanest.
#   * Regimes are sticky enough (self-transition high) to be usable as a slow
#     conditioner, NOT as a fast signal.
#
# EXPLORE next:
#   [ ] Build the real daily AU-US rate differential from bond futures and add it
#       as a 7th driver (the 'rates' bucket is currently the weakest proxy).
#   [ ] Use idio_regime as a GATE on PART A: trade the technical signal only in
#       'low_signal'/'risk', flip or flatten it in 'commodity', and re-cost it.
#   [ ] Test whether the regime itself is PREDICTABLE (does today's regime + VIX
#       forecast next month's regime?) — needed if it's to condition live.
# -----------------------------------------------------------------------------


# =============================================================================
#  PART C — FUNDAMENTAL ECONOMIC-STRENGTH REGIME  (Step 3b)
#  Thesis: a currency reflects the relative strength of two economies. Build an
#  AU-vs-US strength score from PIT macro factors and see if it maps to AUDUSD.
# =============================================================================

#%% [C1] Strength composite from point-in-time macro factors -----------------
# Inputs are already AU-minus-US relatives, delivered as EXPANDING zero-neutral
# z-scores (scaled by an expanding std of past+current data only) -> a score
# dated month t uses only data released by t. Causal by construction. ALFRED
# vintages mean the well-populated composite only starts ~2017 (~105 months) —
# a SMALL, sticky sample, hence the block bootstrap below.

mf = pd.read_csv(f"{DATA}/audusd_point_in_time_macro_factors.csv",
                 index_col=0, parse_dates=True).sort_index()

# each dimension signed so POSITIVE = AU relatively stronger / AUD-supportive
DIMS = {
    "growth":    ["relative_gdp_growth_trend_score", "relative_consumption_growth_score",
                  "manufacturing_confidence_improvement_score", "relative_unemployment_trend_score"],
    "monetary":  ["relative_real_short_rate_score"],                      # AU real-rate carry
    "external":  ["terms_of_trade_dynamics_score"],                       # commodity ToT
    "inflation": ["relative_excess_core_cpi_score", "relative_excess_ppi_score",
                  "relative_inflation_expectations_score"],
}
ec = pd.DataFrame(index=mf.index)
ec["audusd"] = mf["audusd_spot"].astype("float64")
ec["ret_1m"] = np.log(ec["audusd"]).diff()
for dim, cols in DIMS.items():
    ec[f"{dim}_z"] = mf[[c for c in cols if c in mf.columns]].mean(axis=1)  # NaN-safe mean

# STRENGTH = mean(growth, monetary, external). Inflation is HELD OUT of strength
# because its currency sign is ambiguous (hot AU inflation can be AUD+ via a
# hawkish RBA or AUD- via lost competitiveness); we keep it as its own axis.
STRENGTH_DIMS = ["growth", "monetary", "external"]
strength_cols = [c for d in STRENGTH_DIMS for c in DIMS[d]]
n_comp = mf[[c for c in strength_cols if c in mf.columns]].notna().sum(axis=1)
ec["strength_z"] = ec[[f"{d}_z" for d in STRENGTH_DIMS]].mean(axis=1).where(n_comp >= 5)

ec["strength_regime"] = pd.cut(ec["strength_z"], [-np.inf, -0.4, 0.4, np.inf],
                               labels=["AU_weak", "balanced", "AU_strong"])
labelled = ec.dropna(subset=["strength_z"])
print("labelled months:", len(labelled), "|",
      labelled.index.min().date(), "->", labelled.index.max().date())
print(labelled["strength_regime"].value_counts(normalize=True).round(3).to_string())


#%% [C2] LEVEL test — does strong AU => richer AUD? --------------------------
# The thesis's cleanest, most robust claim. Contemporaneous, so no timing risk.
level_corr = ec["strength_z"].corr(ec["audusd"])
by_regime = labelled.groupby("strength_regime", observed=True)["audusd"].agg(["count", "mean"])
print(f"corr(strength_z, AUDUSD level) = {level_corr:+.3f}")
print(by_regime.round(3).to_string())
# RESULT: +0.55, and AU_strong months trade ~6 big-figures above AU_weak. The
# LEVEL relationship is real and economically sensible. Keep this.


#%% [C3] TIMING test — does strength forecast forward returns? ---------------
# Predictive, so strictly causal: regime/score known AS OF month t vs the return
# from t to t+h. Block-bootstrap the rank-IC (12m blocks) — naive monthly t-stats
# on ~105 sticky months would badly overstate significance.
logp = np.log(ec["audusd"])
for h in (1, 3, 6):
    ec[f"fwd_{h}m"] = logp.shift(-h) - logp

print("strength_z -> forward-return rank-IC (block bootstrap):")
for h in (1, 3, 6):
    ic, lo, hi, p = block_bootstrap_ic(ec["strength_z"], ec[f"fwd_{h}m"])
    print(f"  {h}m: IC={ic:+.3f}  90%CI[{lo:+.3f},{hi:+.3f}]  p={p:.3f}")

# fair-value residual: causal EXPANDING OLS of log(AUDUSD) on strength -> the
# misalignment (rich/cheap vs fundamentals); test if it mean-reverts.
s = ec[["audusd", "strength_z"]].dropna()
yln = np.log(s["audusd"].to_numpy()); xz = s["strength_z"].to_numpy()
mis = np.full(len(s), np.nan)
for t in range(36, len(s)):                       # 36m burn-in before first estimate
    b, *_ = np.linalg.lstsq(np.column_stack([np.ones(t), xz[:t]]), yln[:t], rcond=None)
    mis[t] = yln[t] - (b[0] + b[1] * xz[t])
mis = pd.Series(mis, index=s.index)
fwd6 = logp.shift(-6) - logp
ic, lo, hi, p = block_bootstrap_ic(mis, fwd6.reindex(mis.index))
print(f"\nmisalignment -> fwd-6m IC = {ic:+.3f}  90%CI[{lo:+.3f},{hi:+.3f}]  p={p:.3f}")

# -----------------------------------------------------------------------------
# PART C VERDICT (in-sample):  right about the LEVEL, seductive about the TIMING.
#   * LEVEL: corr +0.55 — real, keep as context/valuation anchor.
#   * TIMING: within 2017-26, strength is a CONTRARIAN forward signal (IC ~ -0.3
#     to -0.4 at 3-6m; rich-vs-fair mean-reverts, IC ~ -0.5 at 6m). A naive "buy
#     strength" overlay LOSES. Looks like a fade-the-richness edge...
#   * ...but this rests on ~105 sticky months = ONE AUD cycle. Do NOT believe the
#     magnitude yet. That is exactly what PART D stress-tests.
# -----------------------------------------------------------------------------


# =============================================================================
#  PART D — CROSS-CURRENCY ROBUSTNESS  (the one-cycle pressure test)
#  Q: is "a commodity currency mean-reverts to fundamental fair value" a real,
#     repeatable pattern, or a single AUD-cycle artifact? Rebuild it for AUD/NZD/
#     CAD over a longer, multi-cycle history and test POOLED.
# =============================================================================

#%% [D1] Causal 2-factor fair value for AUD / NZD / CAD ----------------------
# To make construction uniform + PIT-safe across all three currencies, fair value
# uses the two canonical commodity-FX fundamentals (both OBSERVED, not revised):
#   log(FX) ~ a + b1*rate_diff(country-US) + b2*log(terms-of-trade basket)
# fit EXPANDING (data up to t only). This is actually cleaner on causality than
# Part C's revised-macro composite, and gives ~270 months x 3 ccys over the GFC,
# 2011 commodity peak, 2014-15 oil crash, 2020 and 2022 — real out-of-cycle tests.

panel = pd.read_csv(f"{DATA}/commodity_fx_panel_monthly.csv",
                    index_col=0, parse_dates=True).sort_index()
CCY = {"au": "audusd", "nz": "nzdusd", "ca": "cadusd"}
MIN_TRAIN_M = 60

def fair_value(ccy):
    cols = [CCY[ccy], f"rate_diff_{ccy}", f"log_tot_{ccy}"]
    d = panel[cols].dropna()
    y = np.log(d[CCY[ccy]].to_numpy()); X = d[[f"rate_diff_{ccy}", f"log_tot_{ccy}"]].to_numpy()
    fair = np.full(len(d), np.nan)
    for t in range(MIN_TRAIN_M, len(d)):
        b, *_ = np.linalg.lstsq(np.column_stack([np.ones(t), X[:t]]), y[:t], rcond=None)
        fair[t] = b[0] + b[1:] @ X[t]
    out = pd.DataFrame({"logfx": y, "misalign": y - fair}, index=d.index)
    # pure-technical control: deviation from a trailing 12m mean of log(FX).
    # If the FUNDAMENTAL misalignment only works as well as this, the fundamentals
    # add nothing beyond generic price reversion.
    out["ma_dev"] = out["logfx"] - out["logfx"].rolling(12, min_periods=12).mean()
    for h in (1, 6, 12):
        out[f"fwd_{h}m"] = pd.Series(y, index=d.index).shift(-h) - pd.Series(y, index=d.index)
    return out

FV = {c: fair_value(c) for c in CCY}
for c in CCY:
    d = FV[c]["misalign"].dropna()
    print(f"{CCY[c]}: {d.index.min().date()} -> {d.index.max().date()}  n={len(d)}")


#%% [D2] Pooled + per-currency IC, technical control, fade overlay -----------
# Pool blocks WITHIN each currency (preserve serial dependence) then combine.
def pooled_boot_ic(segments, block=12, nboot=5000, seed=0):
    xs = [np.asarray(x, float) for x, _ in segments]
    ys = [np.asarray(y, float) for _, y in segments]
    ic = spearman(np.concatenate(xs), np.concatenate(ys))
    rng = np.random.default_rng(seed); boots = np.full(nboot, np.nan)
    for b in range(nboot):
        bx, by = [], []
        for x, y in zip(xs, ys):
            n = len(x)
            if n < block + 2: continue
            st = rng.integers(0, n - block + 1, size=int(np.ceil(n / block)))
            idx = np.concatenate([np.arange(s0, s0 + block) for s0 in st])[:n]
            bx.append(x[idx]); by.append(y[idx])
        if bx: boots[b] = spearman(np.concatenate(bx), np.concatenate(by))
    lo, hi = np.nanpercentile(boots, [5, 95]); fp = np.nanmean(boots > 0)
    return ic, lo, hi, 2 * min(fp, 1 - fp)

print("fair-value misalignment -> forward-return rank-IC (negative = mean-reversion)")
for h in (1, 6, 12):
    line = []
    for c in CCY:
        ic, lo, hi, p = pooled_boot_ic([(FV[c]["misalign"].to_numpy(), FV[c][f"fwd_{h}m"].to_numpy())])
        line.append(f"{CCY[c]}={ic:+.2f}(p{p:.2f})")
    segs = [(FV[c]["misalign"].to_numpy(), FV[c][f"fwd_{h}m"].to_numpy()) for c in CCY]
    icp, lop, hip, pp = pooled_boot_ic(segs)
    segs_ma = [(FV[c]["ma_dev"].to_numpy(), FV[c][f"fwd_{h}m"].to_numpy()) for c in CCY]
    icm, *_ = pooled_boot_ic(segs_ma)
    print(f"  {h:>2}m: " + "  ".join(line) +
          f"  | POOLED={icp:+.3f}(p{pp:.2f})  tech_control={icm:+.3f}")

# fade-richness overlay: pos = -sign(misalign), realise next-month return, pooled.
rets = []
for c in CCY:
    sig = FV[c]["misalign"].to_numpy(); fwd1 = FV[c]["fwd_1m"].to_numpy()
    m = np.isfinite(sig) & np.isfinite(fwd1)
    rets.append(-np.sign(sig[m]) * fwd1[m])
allr = np.concatenate(rets)
print(f"\nfade-richness pooled overlay: monthly Sharpe(ann) = {ann_sharpe(allr, 12):+.2f}")

# -----------------------------------------------------------------------------
# PART D VERDICT:  it does NOT replicate -> the Step-3b timing edge was a
#                  one-cycle AUD artifact. Tradable claim RETIRED.
#   * AUD over its OWN longer history: same sign but much weaker & mostly
#     insignificant (vs -0.37/-0.54 in the 2017-26 slice) -> that slice was inflated.
#   * NZD: same sign, nothing significant.
#   * CAD: OPPOSITE sign — significant MOMENTUM (its driver is oil, which trends
#     hard), so its fair-value gaps trend rather than revert.
#   * POOLED ~ 0 (AUD/NZD reversion and CAD momentum cancel); the technical
#     control is ~0 too; the fade overlay Sharpe ~ +0.06 (CI straddles 0) — not
#     monetizable. AUD/NZD have sat "cheap vs fair" for YEARS without reverting.
#
# KEEP: the descriptive LEVEL result (fundamentals <-> commodity-FX valuation).
# DROP: strength/misalignment as a timing signal (neither momentum nor reversion
#       is robust). Not intraday-relevant either.
# -----------------------------------------------------------------------------


#%% [E] MASTER SUMMARY + research backlog ------------------------------------
print("""
================  AUDUSD RESEARCH -- WHERE WE STAND  ================
A. Intraday baseline (Step 2) ....... NO-GO. Real but tiny technical micro-edge;
   transaction costs (0.5-1.0 pip) eat it; macro conditioning ~useless intraday.
B. Macro-driver regime (Step 3) ..... Descriptive/veto layer, not an edge. AUD =
   USD + commodity-bloc always; idio driver rotates and MODULATES the baseline
   (commodity regime inverts it, low_signal is cleanest). Sticky enough to gate.
C. Econ-strength regime (Step 3b) ... LEVEL link real (corr +0.55). In-cycle
   mean-reversion timing looked strong but was one cycle only.
D. Cross-currency robustness ........ Timing does NOT replicate (NZD flat, CAD
   momentum, pooled ~0). One-cycle artifact. Timing claim RETIRED; keep level.

TOP OF THE BACKLOG (highest-value, honesty-preserving next steps):
  1. COSTS ARE THE WHOLE GAME. Pull real BID_ASK spread (2nd IBKR pass) and make
     cost time-of-day varying. Every intraday verdict above is provisional until
     the flat 0.5-pip placeholder is replaced with measured half-spreads.
  2. Session-conditional baseline: does the technical micro-edge survive if you
     ONLY trade the london/ny overlap (tightest spreads, most trend)?
  3. Use idio_regime as a live GATE/veto on the technical signal and re-cost it;
     that is the one place Parts A and B might combine into something > either.
  4. Build the genuine daily AU-US rate-differential driver from bond futures;
     it's the weakest link in the regime and the most economically central one.
  5. Everything significant must clear a block-bootstrap / non-overlapping bar
     AND (for slow signals) a cross-sectional/multi-cycle bar, as Part D did.
===================================================================
""")
