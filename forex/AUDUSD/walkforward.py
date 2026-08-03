"""
walkforward.py — leakage-safe walk-forward validation for the AUDUSD baseline.

Design (matches regression_signal_demo.py's discipline, adapted to intraday):
  * EXPANDING training window, refit once per calendar quarter (test block).
  * EMBARGO of `horizon` bars between the end of train and the start of test,
    so overlapping forward-looking labels in the training set cannot peek into
    the test block.
  * CAUSAL standardization: StandardScaler + median-imputation are fit on the
    training slice ONLY, then applied to the test slice.
  * No random splits, ever.

Returns an out-of-sample prediction Series aligned to the panel's row index
(NaN where a row was never in any test block, e.g. the initial train burn-in).
"""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import (
    Ridge, LogisticRegression, ElasticNet,
)
from sklearn.preprocessing import StandardScaler


# ------------------------------------------------------------- WF core loop ---
def walk_forward_predict(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    horizon_bars: int,
    task: str = "reg",               # "reg" | "clf"
    model: str = "ridge",            # "ridge"|"elasticnet" (reg); "logit" (clf)
    alpha: float = 10.0,
    l1_ratio: float = 0.2,
    C: float = 1.0,
    min_train: int = 24000,          # ~first 2 years burn-in before first test
    refit_freq: str = "Q",           # refit cadence (test-block size)
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Walk forward over `refit_freq` test blocks.  Returns a DataFrame indexed
    like `df` with columns:
        pred   : model output (regression value, or P(up) for clf)
        y      : realised target
        in_oos : bool, row was scored out-of-sample
    """
    n = len(df)
    time = df["time"].values
    block = df["time"].dt.tz_localize(None).dt.to_period(refit_freq)
    blocks = block.drop_duplicates().sort_values().tolist()

    X_all = df[feature_cols].to_numpy("float64")
    y_all = df[target_col].to_numpy("float64")

    pred = np.full(n, np.nan)
    scored = np.zeros(n, dtype=bool)

    pos = np.arange(n)
    for q in blocks:
        test_mask = (block == q).values
        test_pos = pos[test_mask]
        if test_pos.size == 0:
            continue
        test_start = test_pos.min()
        # expanding train = everything strictly before test, minus embargo bars
        train_end = test_start - horizon_bars
        if train_end < min_train:
            continue
        train_pos = pos[:train_end]

        Xtr, ytr = X_all[train_pos], y_all[train_pos]
        Xte = X_all[test_pos]
        yte = y_all[test_pos]

        # rows with a usable target in train
        ok = np.isfinite(ytr)
        Xtr, ytr = Xtr[ok], ytr[ok]
        if ytr.size < 500:
            continue

        # --- causal impute (train medians) + standardize (train stats) -------
        # some conditioning columns are all-NaN in early windows (macro PIT
        # only starts ~mid-2013); nanmedian warns then -> fall back to 0.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(Xtr, axis=0)
        med = np.where(np.isfinite(med), med, 0.0)
        Xtr = np.where(np.isfinite(Xtr), Xtr, med)
        Xte = np.where(np.isfinite(Xte), Xte, med)

        scaler = StandardScaler().fit(Xtr)
        Xtr_s = scaler.transform(Xtr)
        Xte_s = scaler.transform(Xte)

        if task == "reg":
            est = (ElasticNet(alpha=alpha, l1_ratio=l1_ratio, max_iter=5000)
                   if model == "elasticnet" else Ridge(alpha=alpha))
            est.fit(Xtr_s, ytr)
            yhat = est.predict(Xte_s)
        else:  # classification on binary direction target (0/1)
            cls = np.unique(ytr)
            if cls.size < 2:
                continue
            est = LogisticRegression(C=C, max_iter=2000)
            est.fit(Xtr_s, ytr)
            yhat = est.predict_proba(Xte_s)[:, 1]

        pred[test_pos] = yhat
        scored[test_pos] = True
        if verbose:
            print(f"  {q}: train={ytr.size:>6d} test={test_pos.size:>4d}")

    return pd.DataFrame(
        {"pred": pred, "y": y_all, "in_oos": scored}, index=df.index
    )


def fit_full_coefficients(
    df: pd.DataFrame, feature_cols: list[str], target_col: str,
    task: str = "reg", model: str = "ridge",
    alpha: float = 10.0, l1_ratio: float = 0.2, C: float = 1.0,
) -> pd.Series:
    """
    Fit ONE model on all rows with a finite target (standardized features) to
    read off coefficient magnitudes for interpretation.  Not used for scoring —
    scoring is always walk-forward.  Coefs are on standardized features so they
    are directly comparable across features.
    """
    X = df[feature_cols].to_numpy("float64")
    y = df[target_col].to_numpy("float64")
    ok = np.isfinite(y)
    X, y = X[ok], y[ok]
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    X = np.where(np.isfinite(X), X, med)
    Xs = StandardScaler().fit_transform(X)
    if task == "reg":
        est = (ElasticNet(alpha=alpha, l1_ratio=l1_ratio, max_iter=5000)
               if model == "elasticnet" else Ridge(alpha=alpha))
    else:
        est = LogisticRegression(C=C, max_iter=2000)
    est.fit(Xs, y)
    coef = est.coef_.ravel()
    return pd.Series(coef, index=feature_cols).sort_values(key=np.abs, ascending=False)
