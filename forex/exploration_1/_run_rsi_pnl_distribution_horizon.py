"""P&L distribution, horizon and threshold economics for the RSI fade.

Answers three questions left open by the programme report:
  1. What does the per-signal P&L distribution actually look like at 30 minutes?
  2. Does the edge scale with holding horizon faster than cost does?
  3. Does going deeper into the RSI extreme help or hurt?

Reproduce with:
    python -u _run_rsi_pnl_distribution_horizon.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _run_rsi_broad_regime_sweep import (
    DATA,
    HOLDOUT,
    PAIRS,
    PIP,
    ROOT,
    SESSIONS_PER_YEAR,
    build_pair,
    session_cluster_t,
)

OUT = ROOT / "rsi_pnl_distribution_horizon_results.json"
DIST_CSV = ROOT / "rsi_pnl_distribution.csv"
GRID_CSV = ROOT / "rsi_horizon_threshold_grid.csv"

HORIZONS = [5, 15, 30, 60, 120, 240, 480]
THRESHOLDS = [(40, 60), (35, 65), (30, 70), (25, 75), (20, 80), (15, 85), (10, 90)]
COSTS = [0.2, 0.5, 1.0]


def horizon_targets(pair, panel):
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "open"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    open_ = raw.open.astype(float)

    out = pd.DataFrame({"ts_utc": raw.time})
    entry = open_.shift(-1)
    entry_ok = raw.time.shift(-1).eq(raw.time + pd.Timedelta(minutes=1))
    for h in HORIZONS:
        b = h + 1
        exit_ = open_.shift(-b)
        ok = entry_ok & raw.time.shift(-b).eq(raw.time + pd.Timedelta(minutes=b))
        out[f"pips_h{h}"] = ((exit_ - entry) / PIP).where(ok)
    return panel.merge(out, on="ts_utc", how="left")


def distribution(gross):
    g = gross.dropna()
    if g.empty:
        return {}
    wins, losses = g[g > 0], g[g <= 0]
    total = g.sum()
    worst1 = g.nsmallest(max(1, int(0.01 * len(g)))).sum()
    worst5 = g.nsmallest(max(1, int(0.05 * len(g)))).sum()
    return {
        "n": int(len(g)),
        "mean": g.mean(),
        "median": g.median(),
        "sd": g.std(ddof=1),
        "skew": g.skew(),
        "p01": g.quantile(0.01),
        "p05": g.quantile(0.05),
        "p25": g.quantile(0.25),
        "p75": g.quantile(0.75),
        "p95": g.quantile(0.95),
        "p99": g.quantile(0.99),
        "hit_rate": (g > 0).mean(),
        "mean_win": wins.mean() if len(wins) else np.nan,
        "mean_loss": losses.mean() if len(losses) else np.nan,
        "win_loss_ratio": abs(wins.mean() / losses.mean()) if len(losses) and losses.mean() else np.nan,
        "worst_1pct_share_of_gross": worst1 / total if total else np.nan,
        "worst_5pct_share_of_gross": worst5 / total if total else np.nan,
    }


def analyse(pair):
    panel, _, _ = build_pair(pair)
    panel = horizon_targets(pair, panel)
    years = panel.sdate.nunique() / SESSIONS_PER_YEAR

    dist_rows = []
    grid_rows = []
    for low, high in THRESHOLDS:
        side = pd.Series(
            np.where(panel.rsi_14 <= low, 1.0, np.where(panel.rsi_14 >= high, -1.0, 0.0)),
            index=panel.index,
        )
        signals = panel.loc[side.ne(0)].copy()
        signals["side"] = side.loc[signals.index]
        for h in HORIZONS:
            gross = signals.side * signals[f"pips_h{h}"]
            z = signals.loc[gross.notna()]
            g = gross.dropna()
            if len(g) < 200:
                continue
            row = {
                "pair": pair,
                "low": low,
                "high": high,
                "horizon_min": h,
                "signals": int(len(g)),
                "signals_per_year": len(g) / years,
                "coverage": len(g) / len(signals),
                "mean_gross_pips": g.mean(),
                "median_gross_pips": g.median(),
                "cluster_t": session_cluster_t(g, z.sdate),
                "hit_rate": (g > 0).mean(),
                "sd_pips": g.std(ddof=1),
                "gross_per_hour": g.mean() / (h / 60),
                "annual_gross_pips": g.mean() * len(g) / years,
            }
            for c in COSTS:
                row[f"net_{c}_pips"] = g.mean() - c
                row[f"annual_net_{c}_pips"] = (g.mean() - c) * len(g) / years
            grid_rows.append(row)

            if (low, high) == (30, 70) and h == 30:
                dist_rows.append({"pair": pair, "low": low, "high": high, "horizon_min": h, **distribution(gross)})
        # distribution at the canonical horizon for every threshold
        gross30 = signals.side * signals["pips_h30"]
        if gross30.notna().sum() >= 200 and (low, high) != (30, 70):
            dist_rows.append(
                {"pair": pair, "low": low, "high": high, "horizon_min": 30, **distribution(gross30)}
            )
    return dist_rows, grid_rows


def main():
    dist_rows, grid_rows = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        d, g = analyse(pair)
        dist_rows.extend(d)
        grid_rows.extend(g)

    dist = pd.DataFrame(dist_rows)
    grid = pd.DataFrame(grid_rows)

    canonical = dist.loc[dist.low.eq(30) & dist.high.eq(70)]
    print("\n=== 1. P&L distribution at the canonical RSI 30/70, 30-minute horizon ===")
    print(
        canonical[
            ["pair", "n", "mean", "median", "sd", "skew", "hit_rate", "mean_win", "mean_loss",
             "win_loss_ratio", "p01", "p05", "p95", "p99",
             "worst_1pct_share_of_gross", "worst_5pct_share_of_gross"]
        ].round(3).to_string(index=False)
    )

    print("\n=== 2. Horizon sweep at RSI 30/70 (median across the four pairs) ===")
    h = grid.loc[grid.low.eq(30) & grid.high.eq(70)]
    by_h = h.groupby("horizon_min").agg(
        signals_per_year=("signals_per_year", "median"),
        coverage=("coverage", "median"),
        mean_gross=("mean_gross_pips", "median"),
        median_gross=("median_gross_pips", "median"),
        cluster_t=("cluster_t", "median"),
        sd_pips=("sd_pips", "median"),
        gross_per_hour=("gross_per_hour", "median"),
        net_02=("net_0.2_pips", "median"),
        net_05=("net_0.5_pips", "median"),
        net_10=("net_1.0_pips", "median"),
        annual_net_05=("annual_net_0.5_pips", "median"),
    )
    print(by_h.round(3).to_string())

    print("\n=== 3. Threshold sweep at the 30-minute horizon (median across pairs) ===")
    t = grid.loc[grid.horizon_min.eq(30)]
    by_t = t.groupby(["low", "high"]).agg(
        signals_per_year=("signals_per_year", "median"),
        mean_gross=("mean_gross_pips", "median"),
        median_gross=("median_gross_pips", "median"),
        cluster_t=("cluster_t", "median"),
        hit_rate=("hit_rate", "median"),
        net_05=("net_0.5_pips", "median"),
        annual_net_05=("annual_net_0.5_pips", "median"),
    )
    print(by_t.round(3).to_string())

    print("\n=== 4. Full grid: median mean_gross_pips by threshold x horizon ===")
    pivot = grid.groupby(["low", "horizon_min"]).mean_gross_pips.median().unstack()
    print(pivot.round(3).to_string())

    print("\n=== 5. Break-even: gross pips needed, and where the grid clears 0.5 pip ===")
    clears = grid.groupby(["low", "horizon_min"]).agg(
        median_gross=("mean_gross_pips", "median"),
        pairs_positive_net_05=("net_0.5_pips", lambda s: int((s > 0).sum())),
        median_t=("cluster_t", "median"),
    ).reset_index()
    clears = clears.loc[clears.pairs_positive_net_05.ge(3)].sort_values("median_gross", ascending=False)
    print(clears.head(20).round(3).to_string(index=False))

    dist.to_csv(DIST_CSV, index=False)
    grid.to_csv(GRID_CSV, index=False)
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "pairs": PAIRS,
                    "horizons_min": HORIZONS,
                    "thresholds": THRESHOLDS,
                    "costs_pips": COSTS,
                    "holdout_start": HOLDOUT.isoformat(),
                    "note": "Longer horizons overlap heavily; per-signal mean with session-clustered SE.",
                },
                "distribution": json.loads(dist.to_json(orient="records")),
                "grid": json.loads(grid.to_json(orient="records")),
            },
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
