"""
Walk-forward regression-learning signal -- a template, not a finished strategy.

This mirrors the Macrosynergy methodology in miniature: at each point in time,
fit a model using ONLY past, fully-realized data, predict the next period, and
never peek ahead. Here it is a ridge regression refit monthly on an expanding
window, run on the DAILY placeholder target from build_feature_panel.py.

It exists to demonstrate correct sequential evaluation (expanding window +
horizon embargo + causal standardization) that you can later re-point at an
intraday target. It is NOT evidence of a tradable edge:
  * daily frequency, daily placeholder target (real goal is intraday);
  * no transaction-cost model (at intraday frequency costs dominate -- see the
    paper's TCA section);
  * PIT macro features only exist from ~2013, so the usable sample is short.

    python regression_signal_demo.py
"""

from pathlib import Path
import warnings

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

HORIZON = 5          # predict forward 5-day return
MIN_TRAIN = 756      # ~3y before first prediction
REFIT_EVERY = 21     # refit monthly
RIDGE_LAMBDA = 25.0  # L2 penalty (features are standardized)


def fit_ridge(X, y, lam):
    """Closed-form ridge with an unpenalized intercept. X already standardized."""
    n, k = X.shape
    Xi = np.hstack([np.ones((n, 1)), X])
    penalty = lam * np.eye(k + 1)
    penalty[0, 0] = 0.0  # don't penalize intercept
    beta = np.linalg.solve(Xi.T @ Xi + penalty, Xi.T @ y)
    return beta


def walk_forward(panel):
    feat_cols = [c for c in panel.columns if c.startswith(("f_", "macro_"))]
    target = f"target_fwd_ret_{HORIZON}d"
    daily_ret = "target_fwd_ret_1d"

    df = panel[feat_cols + [target, daily_ret]].replace([np.inf, -np.inf], np.nan)
    X_all = df[feat_cols].to_numpy(dtype=float)
    y_all = df[target].to_numpy(dtype=float)
    n = len(df)

    preds = np.full(n, np.nan)
    mu = sd = beta = None

    for i in range(MIN_TRAIN, n):
        # Embargo: only use samples whose H-day target has fully realized strictly
        # before day i, so the model never trains on information from its own future.
        train_end = i - HORIZON
        if train_end <= 50:
            continue

        if (i - MIN_TRAIN) % REFIT_EVERY == 0 or beta is None:
            Xtr = X_all[:train_end]
            ytr = y_all[:train_end]
            good = np.isfinite(ytr)
            Xtr, ytr = Xtr[good], ytr[good]
            if len(ytr) < 100:
                continue

            # causal standardization from the training window only. Some feature
            # columns are all-NaN in early windows (macro pre-2013, DXY pre-2006);
            # they collapse to a neutral 0 below, so silence the empty-slice noise.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                mu = np.nanmean(Xtr, axis=0)
                sd = np.nanstd(Xtr, axis=0)
            mu = np.where(np.isfinite(mu), mu, 0.0)
            sd[~np.isfinite(sd) | (sd == 0)] = 1.0
            Ztr = np.nan_to_num((Xtr - mu) / sd)  # missing feature -> neutral 0
            beta = fit_ridge(Ztr, ytr, RIDGE_LAMBDA)

        zi = np.nan_to_num((X_all[i] - mu) / sd)
        preds[i] = beta[0] + zi @ beta[1:]

    df["pred"] = preds
    return df, feat_cols


def evaluate(df):
    oos = df.dropna(subset=["pred", f"target_fwd_ret_{HORIZON}d"])
    ic = oos["pred"].corr(oos[f"target_fwd_ret_{HORIZON}d"], method="spearman")
    hit = (np.sign(oos["pred"]) == np.sign(oos[f"target_fwd_ret_{HORIZON}d"])).mean()

    # simple daily long/short: yesterday's signed prediction * today's daily return
    pos = np.sign(df["pred"]).shift(1)
    pnl = (pos * df["target_fwd_ret_1d"].shift(1)).dropna()  # both realized, no lookahead
    pnl = pnl[pnl.index.isin(df.dropna(subset=["pred"]).index)]
    sharpe = np.sqrt(252) * pnl.mean() / pnl.std() if pnl.std() > 0 else np.nan
    cum = pnl.sum()

    print("Out-of-sample (walk-forward, daily placeholder target):")
    print(f"  period          : {oos.index.min().date()} -> {oos.index.max().date()}"
          f"  ({len(oos)} days)")
    print(f"  rank IC (H={HORIZON}d) : {ic:+.3f}")
    print(f"  direction hit   : {hit:6.1%}")
    print(f"  L/S gross Sharpe: {sharpe:+.2f}  (NO costs -> optimistic)")
    print(f"  L/S cum log-ret : {cum:+.3f}")
    print("\nReminder: template on daily data, no costs. Re-point at intraday bars")
    print("and add a transaction-cost model before trusting any of these numbers.")


if __name__ == "__main__":
    panel = pd.read_csv(DATA_DIR / "audusd_modeling_panel_daily.csv",
                        parse_dates=["date"], index_col="date")
    df, feat_cols = walk_forward(panel)
    print(f"Features used: {len(feat_cols)}  |  refit every {REFIT_EVERY}d, "
          f"ridge lambda={RIDGE_LAMBDA}\n")
    evaluate(df)
