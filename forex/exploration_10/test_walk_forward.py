import json
from pathlib import Path

import pandas as pd

from run_walk_forward import candidates, load_pre_holdout, make_folds


ROOT = Path(__file__).resolve().parent


def config():
    return json.loads((ROOT / "experiments/configs/walk_forward_grid.json").read_text())


def test_grid_has_frozen_243_unique_candidates():
    grid = candidates(config())
    assert len(grid) == 243
    assert len({row["config_id"] for row in grid}) == 243


def test_folds_never_cross_holdout_and_use_rolling_five_years():
    cutoff = pd.Timestamp("2024-07-18")
    folds = make_folds(config(), cutoff)
    assert len(folds) == 8
    assert folds[-1]["validation_end"] == cutoff
    assert folds[-1]["partial_validation"]
    assert all(fold["validation_end"] <= cutoff for fold in folds)
    assert all(fold["train_end"] - pd.DateOffset(years=5) == fold["train_start"] for fold in folds)


def test_parquet_loader_excludes_holdout_rows(tmp_path):
    path = tmp_path / "bars.parquet"
    frame = pd.DataFrame({
        "ts_utc": pd.date_range("2024-07-17 23:58", periods=4, freq="min"),
        "open": [1.0] * 4, "high": [1.1] * 4,
        "low": [0.9] * 4, "close": [1.0] * 4,
    })
    frame.to_parquet(path, index=False)
    loaded = load_pre_holdout(path, pd.Timestamp("2024-07-18 00:00"))
    assert len(loaded) == 2
    assert loaded.index.max() < pd.Timestamp("2024-07-18 00:00")
