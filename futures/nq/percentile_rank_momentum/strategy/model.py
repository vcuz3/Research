"""Simple annual walk-forward multinomial model and decision-theoretic readouts."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def add_forward_target(
    features: pd.DataFrame, bars: pd.DataFrame, horizon_minutes: int = 30
) -> pd.DataFrame:
    steps = horizon_minutes // 5
    if steps <= 0 or horizon_minutes % 5:
        raise ValueError("forward horizon must be a positive multiple of five minutes")
    target_rows = []
    for date, group in bars.sort_values(["date", "tod"]).groupby("date", sort=False):
        group = group.reset_index(drop=True)
        for i in range(len(group)):
            start, end = i + 1, i + 1 + steps
            if end < len(group):
                target_rows.append({
                    "date": date,
                    "tod": int(group.loc[i, "tod"]),
                    "forward_points": float(group.loc[end, "open"] - group.loc[start, "open"]),
                })
    return features.merge(pd.DataFrame(target_rows), on=["date", "tod"], how="left")


def feature_columns(horizons: tuple[int, ...]) -> list[str]:
    columns = ["signed_composite", "log_sigma_day"]
    for horizon in horizons:
        columns += [f"signed_rank_{horizon}m", f"normalized_{horizon}m"]
    return columns


def prepare_model_frame(features: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    out = features.copy()
    out["signed_composite"] = out["score_long"] - out["score_short"]
    out["log_sigma_day"] = np.log(out["sigma_day"])
    for horizon in horizons:
        z = out[f"normalized_{horizon}m"]
        out[f"signed_rank_{horizon}m"] = np.sign(z) * out[f"rank_{horizon}m"]
    return out


def walk_forward_predictions(
    frame: pd.DataFrame,
    horizons: tuple[int, ...],
    bins: int = 10,
    trailing_years: int = 5,
    minimum_training_rows: int = 5000,
    regularization_c: float = 0.1,
    random_state: int = 17,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retrain each January on only prior years; emit argmax and E[r]."""
    columns = feature_columns(horizons)
    usable = frame.dropna(subset=columns).copy()
    usable["year"] = usable["date"].dt.year
    predictions, folds = [], []
    for year in sorted(usable["year"].unique()):
        train = usable[
            (usable["year"] < year)
            & (usable["year"] >= year - trailing_years)
            & usable["forward_points"].notna()
        ]
        test = usable[usable["year"] == year]
        if len(train) < minimum_training_rows or test.empty:
            continue
        target = train["forward_points"].to_numpy(float)
        edges = np.unique(np.quantile(target, np.linspace(0, 1, bins + 1)))
        if len(edges) < 4:
            continue
        labels = np.searchsorted(edges[1:-1], target, side="right")
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=regularization_c,
                max_iter=300,
                solver="lbfgs",
                random_state=random_state,
            ),
        )
        model.fit(train[columns], labels)
        probability = model.predict_proba(test[columns])
        classes = model[-1].classes_.astype(int)
        means = np.array([target[labels == category].mean() for category in classes])
        argmax = means[np.argmax(probability, axis=1)]
        expected = probability @ means
        part = test[["date", "tod", "forward_points"]].copy()
        part["argmax_readout"] = argmax
        part["expected_readout"] = expected
        part["fold_year"] = int(year)
        predictions.append(part)
        folds.append({
            "test_year": int(year),
            "train_start": str(train["date"].min().date()),
            "train_end": str(train["date"].max().date()),
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "classes": int(len(classes)),
            "argmax_mean_points": float(argmax.mean()),
            "expected_mean_points": float(expected.mean()),
        })
    if not predictions:
        return pd.DataFrame(), pd.DataFrame(folds)
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(folds)
