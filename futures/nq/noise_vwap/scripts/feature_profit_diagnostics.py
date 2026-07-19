"""Exploratory feature-vs-profit diagnostics for the continuous-stop baseline.

This is a screen, not a strategy claim. It enriches the existing WFO per-trade
dataset with causal breakout-time RVOL, then reports correlations, feature
quantile bins, and a small gap x RVOL interaction grid. Any apparent filter must
be promoted to a preregistered engine rerun + Null-C twin before interpretation.

Run:
  python -m futures.nq.noise_vwap.scripts.feature_profit_diagnostics
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from . import wfo_data

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0015"
WFO_PATH = ROOT / "outputs" / "wfo_dataset_continuous_stop.parquet"
LOOKBACK = 90


FEATURES = [
    ("aligned_gap", "side * overnight/RTH gap"),
    ("abs_gap", "absolute overnight/RTH gap"),
    ("rvol_90", "breakout-minute RVOL vs prior 90 same-mfo bars"),
    ("log_rvol_90", "log1p(RVOL)"),
    ("ext_atr", "signal close extension beyond band, ATR units"),
    ("vwap_dist_atr", "signal close distance beyond VWAP, ATR units"),
    ("sess_move", "side-aligned session move at signal"),
    ("band_width_bps", "noise band width, bps"),
    ("atr_pts", "prior-14-session RTH ATR, points"),
    ("ord_in_day", "trade ordinal within session"),
]


def _safe_t(x: pd.Series) -> float:
    x = x.dropna()
    if len(x) < 2:
        return np.nan
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / np.sqrt(len(x)))) if sd > 0 else np.nan


def _sharpe_daily(df: pd.DataFrame) -> float:
    day = df.groupby("date")["net_atr"].sum()
    sd = day.std(ddof=1)
    return float(day.mean() / sd * np.sqrt(252)) if len(day) > 1 and sd > 0 else np.nan


def _summary(df: pd.DataFrame) -> dict:
    q90 = df["net_atr"].quantile(0.90) if len(df) else np.nan
    return {
        "n": len(df),
        "days": df["date"].nunique() if len(df) else 0,
        "sumR": df["net_atr"].sum(),
        "meanR": df["net_atr"].mean(),
        "medianR": df["net_atr"].median(),
        "hit": (df["net_atr"] > 0).mean(),
        "trade_t": _safe_t(df["net_atr"]),
        "daily_sharpe": _sharpe_daily(df),
        "p90R": q90,
        "tail_share": df.loc[df["net_atr"] >= q90, "net_atr"].sum() / df["net_atr"].sum()
        if len(df) and df["net_atr"].sum() != 0 else np.nan,
    }


def load_or_build_wfo() -> pd.DataFrame:
    if WFO_PATH.exists():
        return pd.read_parquet(WFO_PATH)
    df = wfo_data.build()
    wfo_data.validate(df)
    WFO_PATH.parent.mkdir(exist_ok=True)
    df.to_parquet(WFO_PATH, index=False)
    return df


def add_rvol(df: pd.DataFrame) -> pd.DataFrame:
    bars = S.load_session("NQ", "RTH")
    b = bars[["sdate", "mfo", "volume"]].sort_values(["mfo", "sdate"]).copy()
    b["vol_base_90"] = (
        b.groupby("mfo")["volume"]
        .transform(lambda s: s.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).mean())
    )
    b["rvol_90"] = b["volume"] / b["vol_base_90"]
    b = b.rename(columns={"sdate": "date", "mfo": "signal_mfo", "volume": "signal_volume"})

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out["signal_mfo"] = out["entry_mfo"].astype(int) - 1
    out = out.merge(b, on=["date", "signal_mfo"], how="left")
    out["aligned_gap"] = out["side"] * out["open_gap"]
    out["abs_gap"] = out["open_gap"].abs()
    out["log_rvol_90"] = np.log1p(out["rvol_90"])
    out["era"] = np.select(
        [out["year"] < 2018, out["year"] < 2023, out["year"] >= 2023],
        ["2011-2017", "2018-2022", "2023+"],
        default="unknown",
    )
    return out


def correlations(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, desc in FEATURES:
        g = df[[col, "net_atr"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(g) < 20:
            continue
        rows.append({
            "feature": col,
            "description": desc,
            "n": len(g),
            "pearson": g[col].corr(g["net_atr"], method="pearson"),
            "spearman": g[col].corr(g["net_atr"], method="spearman"),
        })
    return pd.DataFrame(rows).sort_values("spearman", key=lambda s: s.abs(), ascending=False)


def quantile_bins(df: pd.DataFrame, q: int = 5) -> pd.DataFrame:
    rows = []
    for col, desc in FEATURES:
        x = df[[col, "net_atr", "date"]].replace([np.inf, -np.inf], np.nan).dropna()
        if x[col].nunique() < q or len(x) < 100:
            continue
        try:
            x["bin"] = pd.qcut(x[col], q, duplicates="drop")
        except ValueError:
            continue
        for label, g in x.groupby("bin", observed=True):
            s = _summary(g)
            s.update({
                "feature": col,
                "description": desc,
                "bin": str(label),
                "feature_min": g[col].min(),
                "feature_max": g[col].max(),
            })
            rows.append(s)
    cols = ["feature", "description", "bin", "feature_min", "feature_max",
            "n", "days", "sumR", "meanR", "medianR", "hit", "trade_t",
            "daily_sharpe", "p90R", "tail_share"]
    return pd.DataFrame(rows)[cols]


def interaction_grid(df: pd.DataFrame) -> pd.DataFrame:
    x = df[["aligned_gap", "rvol_90", "net_atr", "date"]].replace([np.inf, -np.inf], np.nan).dropna()
    x["gap_bin"] = pd.qcut(x["aligned_gap"], 3, labels=["gap_against", "gap_mid", "gap_with"])
    x["rvol_bin"] = pd.qcut(x["rvol_90"], 3, labels=["rvol_low", "rvol_mid", "rvol_high"])
    rows = []
    for (gb, rb), g in x.groupby(["gap_bin", "rvol_bin"], observed=True):
        s = _summary(g)
        s.update({"gap_bin": str(gb), "rvol_bin": str(rb)})
        rows.append(s)
    return pd.DataFrame(rows).sort_values(["gap_bin", "rvol_bin"])


def era_top_bottom(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, _ in FEATURES[:8]:
        x = df[[col, "net_atr", "date", "era"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(x) < 100 or x[col].nunique() < 5:
            continue
        lo, hi = x[col].quantile([0.2, 0.8])
        for tag, g in [("bottom20", x[x[col] <= lo]), ("middle60", x[(x[col] > lo) & (x[col] < hi)]), ("top20", x[x[col] >= hi])]:
            for era, eg in g.groupby("era", observed=True):
                s = _summary(eg)
                s.update({"feature": col, "slice": tag, "era": era})
                rows.append(s)
    return pd.DataFrame(rows)


def write_report(df: pd.DataFrame, corr: pd.DataFrame, bins: pd.DataFrame,
                 grid: pd.DataFrame, era: pd.DataFrame) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "feature_trade_dataset.parquet", index=False)
    corr.to_csv(OUT / "correlations.csv", index=False)
    bins.to_csv(OUT / "quantile_bins.csv", index=False)
    grid.to_csv(OUT / "gap_rvol_grid.csv", index=False)
    era.to_csv(OUT / "era_top_bottom.csv", index=False)

    base = _summary(df)
    strongest = bins.sort_values("meanR", ascending=False).head(10)
    weakest = bins.sort_values("meanR", ascending=True).head(10)

    def csv_block(frame: pd.DataFrame) -> str:
        return frame.to_csv(index=False, float_format="%.6f").strip()

    with (OUT / "review.md").open("w", encoding="utf-8") as f:
        f.write("# EXP-0015 Feature-Profit Diagnostic Screen\n\n")
        f.write("Status: exploratory screen only; no engine filter or Null-C validation.\n\n")
        f.write("Baseline sample: continuous-stop NQ trades from the existing WFO dataset, ")
        f.write("scored in net ATR R. RVOL is breakout/signal-minute volume divided by ")
        f.write("the strictly prior 90-session same-mfo average.\n\n")
        f.write("## Baseline\n\n")
        f.write("```csv\n")
        f.write(csv_block(pd.DataFrame([base])))
        f.write("\n```")
        f.write("\n\n## Correlations\n\n")
        f.write("```csv\n")
        f.write(csv_block(corr))
        f.write("\n```")
        f.write("\n\n## Strongest Single-Feature Bins By Mean R\n\n")
        f.write("```csv\n")
        f.write(csv_block(strongest[["feature", "bin", "n", "sumR", "meanR", "hit", "trade_t", "daily_sharpe"]]))
        f.write("\n```")
        f.write("\n\n## Weakest Single-Feature Bins By Mean R\n\n")
        f.write("```csv\n")
        f.write(csv_block(weakest[["feature", "bin", "n", "sumR", "meanR", "hit", "trade_t", "daily_sharpe"]]))
        f.write("\n```")
        f.write("\n\n## Aligned Gap x RVOL Tercile Grid\n\n")
        f.write("```csv\n")
        f.write(csv_block(grid[["gap_bin", "rvol_bin", "n", "sumR", "meanR", "hit", "trade_t", "daily_sharpe"]]))
        f.write("\n```")
        f.write("\n")


def main() -> None:
    df = add_rvol(load_or_build_wfo())
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["net_atr"])
    corr = correlations(df)
    bins = quantile_bins(df)
    grid = interaction_grid(df)
    era = era_top_bottom(df)
    write_report(df, corr, bins, grid, era)

    print(f"wrote diagnostics -> {OUT}")
    print("\n=== correlations ===")
    print(corr.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\n=== gap x RVOL grid ===")
    print(grid[["gap_bin", "rvol_bin", "n", "sumR", "meanR", "hit", "trade_t", "daily_sharpe"]]
          .to_string(index=False, float_format=lambda x: f"{x:+.4f}"))


if __name__ == "__main__":
    main()
