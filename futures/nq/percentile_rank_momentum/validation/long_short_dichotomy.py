"""Long vs short decomposition of the direct (B1) and hysteresis (B2) books.

Motivation: B2 makes +1.6 gross ticks/trade including BOTH sides. On an index
that drifts UP, a long book can profit from drift alone, but a short book cannot
-- positive short gross must come from timing. This script separates the two
sides and strips the drift so we can see where the gross actually comes from.

For each side we report raw gross (points/ticks), hit rate, payoff, holding time,
per-hour gross, session-cluster t; a DRIFT-ADJUSTED "timing" return that removes
each trade's expected drift (side * mu_per_min * holding_min); the above/below
200DMA split; the entry-hour profile; and the cumulative gross path (to see if a
side's edge is broad or concentrated in a few bear episodes).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from futures.nq.percentile_rank_momentum.strategy.features import (
    build_same_slot_features,
    load_canonical_rth_5m,
)
from futures.nq.percentile_rank_momentum.strategy.signal import direct_state, hysteresis_state
from futures.nq.percentile_rank_momentum.backtest_engine.adapter import run_desired_positions
from futures.nq.noise_vwap.core.data import TICK, POINT_VALUE

import json

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT / "experiments" / "configs" / "hyp_0001.json").read_text())
OUT = PROJECT / "artifacts" / "explore" / "long_short"
OUT.mkdir(parents=True, exist_ok=True)
INST = "NQ"


def cluster_t(y: np.ndarray, groups: np.ndarray) -> float:
    y = np.asarray(y, float)
    if len(y) < 2 or len(np.unique(groups)) < 2:
        return np.nan
    fit = sm.OLS(y, np.ones((len(y), 1))).fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True}
    )
    return float(fit.tvalues[0])


def era(date: pd.Timestamp) -> str:
    y = date.year
    return "2011-2014" if y <= 2014 else "2015-2019" if y <= 2019 else \
        "2020-2022" if y <= 2022 else "2023+"


def enrich(trades: pd.DataFrame, mu_per_min: float, regime: pd.Series) -> pd.DataFrame:
    t = trades.copy()
    t["hold_min"] = (t["exit_tod"] - t["entry_tod"]).clip(lower=1)
    t["w"] = np.log(t["exit_px"] / t["entry_px"])          # market log-return over window
    t["pos_ret"] = t["side"] * t["w"]                       # realized position return
    t["drift_exp"] = t["side"] * mu_per_min * t["hold_min"] # expected drift for this exposure
    t["timing_ret"] = t["pos_ret"] - t["drift_exp"]         # drift-removed timing return
    t["gross_ticks"] = t["points"] / TICK[INST]
    t["era"] = t["date"].map(era)
    t["above200"] = t["date"].map(regime)
    return t


def side_stats(t: pd.DataFrame, label: str) -> dict:
    g = t["points"].to_numpy()
    tim_bps = t["timing_ret"].to_numpy() * 1e4
    wins = g > 0
    return {
        "book": label,
        "n": len(t),
        "gross_pts_per_trade": float(g.mean()),
        "gross_ticks_per_trade": float(t["gross_ticks"].mean()),
        "total_gross_usd": float(g.sum() * POINT_VALUE[INST]),
        "hit_rate": float(wins.mean()),
        "avg_win_pts": float(g[wins].mean()) if wins.any() else np.nan,
        "avg_loss_pts": float(g[~wins].mean()) if (~wins).any() else np.nan,
        "median_hold_min": float(t["hold_min"].median()),
        "gross_pts_per_hour": float(g.sum() / (t["hold_min"].sum() / 60.0)),
        "gross_cluster_t": cluster_t(g, t["date"].to_numpy()),
        "timing_bps_per_trade": float(tim_bps.mean()),
        "timing_cluster_t": cluster_t(t["timing_ret"].to_numpy(), t["date"].to_numpy()),
        "frac_above200": float(t["above200"].mean()),
    }


def book_table(t: pd.DataFrame, name: str) -> pd.DataFrame:
    rows = [
        side_stats(t, f"{name}_all"),
        side_stats(t[t["side"] == 1], f"{name}_long"),
        side_stats(t[t["side"] == -1], f"{name}_short"),
    ]
    return pd.DataFrame(rows)


def main() -> None:
    horizons = tuple(CONFIG["momentum_horizons_minutes"])
    weights = tuple(CONFIG["horizon_weights"])
    window = int(CONFIG["primary_rank_window_sessions"])
    alpha = float(CONFIG["primary_vol_blend_alpha"])
    floor = float(CONFIG["same_sign_coverage_fraction"])
    qe, qx = float(CONFIG["entry_threshold"]), float(CONFIG["exit_threshold"])

    bars, _ = load_canonical_rth_5m(INST, CONFIG["minimum_1m_bars_per_session"])
    features = build_same_slot_features(bars, window, floor, alpha, horizons, weights)

    # per-minute RTH drift (return space), and daily 200DMA regime
    daily = bars.sort_values(["date", "tod"]).groupby("date").agg(
        rth_open=("open", "first"), rth_close=("close", "last"),
        span_min=("tod", lambda s: s.max() - s.min())
    )
    day_ret = np.log(daily["rth_close"] / daily["rth_open"])
    mu_per_min = float((day_ret / daily["span_min"].clip(lower=1)).mean())
    sma = daily["rth_close"].rolling(200).mean()
    dist_prior = ((daily["rth_close"] - sma) / sma).shift(1)
    regime = (dist_prior > 0).reindex(daily.index)

    print(f"{INST} RTH per-minute drift mu = {mu_per_min:.3e} "
          f"(~{mu_per_min*390*1e4:.2f} bps/session)")

    b1 = enrich(run_desired_positions(bars, direct_state(features, qe)), mu_per_min, regime)
    b2 = enrich(run_desired_positions(bars, hysteresis_state(features, qe, qx)), mu_per_min, regime)

    table = pd.concat([book_table(b1, "B1_direct"), book_table(b2, "B2_hyst")], ignore_index=True)
    pd.set_option("display.width", 240, "display.max_columns", 40)
    print("\n=== Long/short decomposition (full sample) ===")
    print(table.round(4).to_string(index=False))
    table.to_csv(OUT / "long_short_stats.csv", index=False)

    # era x side breakdown for B2
    rows = []
    for e, g in b2.groupby("era"):
        for side, sname in [(1, "long"), (-1, "short")]:
            s = g[g["side"] == side]
            if len(s) < 10:
                continue
            rows.append({
                "era": e, "side": sname, "n": len(s),
                "gross_ticks": float(s["gross_ticks"].mean()),
                "timing_bps": float(s["timing_ret"].mean() * 1e4),
                "timing_t": cluster_t(s["timing_ret"].to_numpy(), s["date"].to_numpy()),
                "total_usd": float(s["points"].sum() * POINT_VALUE[INST]),
            })
    era_tab = pd.DataFrame(rows)
    print("\n=== B2 by era x side ===")
    print(era_tab.round(3).to_string(index=False))
    era_tab.to_csv(OUT / "b2_era_side.csv", index=False)

    _figures(b2)
    print(f"\nsaved under {OUT}")


def _figures(b2: pd.DataFrame):
    longs = b2[b2["side"] == 1].sort_values("date")
    shorts = b2[b2["side"] == -1].sort_values("date")

    # Fig 1: cumulative gross USD path, long vs short
    fig, ax = plt.subplots(figsize=(11, 5))
    for s, lab, col in [(longs, "long", "tab:green"), (shorts, "short", "tab:red")]:
        cum = (s.set_index("date")["points"].cumsum() * POINT_VALUE[INST])
        ax.plot(cum.index, cum.values, label=f"{lab} (n={len(s)})", color=col)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title("B2 hysteresis — cumulative GROSS P&L, long vs short (1 contract)")
    ax.set_ylabel("cumulative gross $"); ax.legend()
    fig.tight_layout(); fig.savefig(OUT / "fig1_cum_gross.png", dpi=110); plt.close(fig)

    # Fig 2: entry-hour profile long vs short
    fig, ax = plt.subplots(figsize=(11, 4.5))
    hours = np.arange(9, 16)
    lh = (longs["entry_tod"] // 60).value_counts(normalize=True)
    sh = (shorts["entry_tod"] // 60).value_counts(normalize=True)
    ax.bar(hours - 0.18, [lh.get(h, 0) for h in hours], width=0.36, color="tab:green", label="long")
    ax.bar(hours + 0.18, [sh.get(h, 0) for h in hours], width=0.36, color="tab:red", label="short")
    ax.set_xlabel("entry hour (ET)"); ax.set_ylabel("share of trades")
    ax.set_title("B2 entry-hour profile: when do longs vs shorts fire?")
    ax.legend(); fig.tight_layout(); fig.savefig(OUT / "fig2_entry_hour.png", dpi=110); plt.close(fig)

    # Fig 3: mean gross ticks by era x side
    fig, ax = plt.subplots(figsize=(10, 4.5))
    eras = ["2011-2014", "2015-2019", "2020-2022", "2023+"]
    lg = b2[b2["side"] == 1].groupby("era")["gross_ticks"].mean()
    sg = b2[b2["side"] == -1].groupby("era")["gross_ticks"].mean()
    x = np.arange(len(eras))
    ax.bar(x - 0.18, [lg.get(e, np.nan) for e in eras], 0.36, color="tab:green", label="long")
    ax.bar(x + 0.18, [sg.get(e, np.nan) for e in eras], 0.36, color="tab:red", label="short")
    ax.axhline(0, color="k", lw=0.6)
    ax.axhline(1.9, color="grey", ls="--", lw=1, label="1.9-tick cost")
    ax.set_xticks(x); ax.set_xticklabels(eras)
    ax.set_ylabel("mean gross ticks/trade")
    ax.set_title("B2 gross by era x side (vs cost line)")
    ax.legend(); fig.tight_layout(); fig.savefig(OUT / "fig3_era_side.png", dpi=110); plt.close(fig)


if __name__ == "__main__":
    main()
