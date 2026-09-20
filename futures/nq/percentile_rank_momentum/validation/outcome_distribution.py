"""Diagnostic: is the signal's outcome distribution bimodal, and how do long vs
short differ?  Reviewer-requested (2026-08-22).

Charts and tabulates three things on NQ:
  1. Realized per-trade P&L (points) for B1 (direct rank) and B2 (hysteresis),
     split by side.
  2. The underlying 30-min forward outcome (the model target) UNCONDITIONALLY
     and CONDITIONAL on the B1 long / B1 short signal being on -- this is the
     "characteristic return" object the bimodal paper claims is two-peaked.

For each distribution we print n, mean, sd, skew, excess kurtosis, the
Sarle bimodality coefficient BC=(skew^2+1)/kurt (BC>0.555 hints bimodality),
and a Hartigan dip test if `diptest` is importable.  KDE + histogram figures
are written to artifacts/runs/EXP-0002/figs/.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from futures.nq.percentile_rank_momentum.strategy.features import (
    build_same_slot_features,
    load_canonical_rth_5m,
)
from futures.nq.percentile_rank_momentum.strategy.model import add_forward_target
from futures.nq.percentile_rank_momentum.strategy.signal import (
    direct_state,
    hysteresis_state,
)
from futures.nq.percentile_rank_momentum.backtest_engine.adapter import run_desired_positions

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT / "experiments" / "configs" / "hyp_0001.json").read_text())
FIGDIR = PROJECT / "artifacts" / "runs" / "EXP-0002" / "figs"
FIGDIR.mkdir(parents=True, exist_ok=True)

try:
    import diptest as _diptest

    def dip_pvalue(x: np.ndarray) -> float:
        if len(x) < 4:
            return np.nan
        return float(_diptest.diptest(np.asarray(x, float))[1])
except Exception:  # pragma: no cover - optional dep
    def dip_pvalue(x: np.ndarray) -> float:
        return np.nan


def describe(x: np.ndarray) -> dict:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return {"n": n}
    sk = float(stats.skew(x, bias=False))
    ku = float(stats.kurtosis(x, fisher=True, bias=False))  # excess
    # Sarle bimodality coefficient uses NON-excess kurtosis and a sample correction
    m3 = float(stats.skew(x, bias=True))
    m4 = float(stats.kurtosis(x, fisher=False, bias=True))
    bc = (m3 ** 2 + 1.0) / (m4 + (3.0 * (n - 1) ** 2) / ((n - 2) * (n - 3)))
    return {
        "n": n,
        "mean": float(x.mean()),
        "sd": float(x.std(ddof=1)),
        "median": float(np.median(x)),
        "skew": sk,
        "excess_kurt": ku,
        "bimod_coef": float(bc),
        "dip_p": dip_pvalue(x),
        "q05": float(np.quantile(x, 0.05)),
        "q25": float(np.quantile(x, 0.25)),
        "q75": float(np.quantile(x, 0.75)),
        "q95": float(np.quantile(x, 0.95)),
    }


def kde_modes(x: np.ndarray, grid: int = 512) -> int:
    """Count interior local maxima of a Gaussian KDE (Scott bandwidth)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 20 or x.std() == 0:
        return 0
    kde = stats.gaussian_kde(x)
    lo, hi = np.quantile(x, [0.005, 0.995])
    xs = np.linspace(lo, hi, grid)
    ys = kde(xs)
    # interior local maxima with a small prominence guard
    peaks = 0
    for i in range(1, len(ys) - 1):
        if ys[i] > ys[i - 1] and ys[i] >= ys[i + 1] and ys[i] > 0.05 * ys.max():
            peaks += 1
    return peaks


def plot_hist_kde(ax, x: np.ndarray, label: str, color: str, clip=(-40, 40)):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    xc = np.clip(x, *clip)
    ax.hist(xc, bins=80, density=True, alpha=0.35, color=color, label=f"{label} (n={len(x)})")
    if len(x) >= 20 and x.std() > 0:
        kde = stats.gaussian_kde(x)
        xs = np.linspace(*clip, 400)
        ax.plot(xs, kde(xs), color=color, lw=1.8)
    ax.axvline(0, color="k", lw=0.6, ls=":")


def main() -> None:
    horizons = tuple(CONFIG["momentum_horizons_minutes"])
    weights = tuple(CONFIG["horizon_weights"])
    window = int(CONFIG["primary_rank_window_sessions"])
    alpha = float(CONFIG["primary_vol_blend_alpha"])
    floor = float(CONFIG["same_sign_coverage_fraction"])
    qe, qx = float(CONFIG["entry_threshold"]), float(CONFIG["exit_threshold"])

    bars, _ = load_canonical_rth_5m("NQ", CONFIG["minimum_1m_bars_per_session"])
    features = build_same_slot_features(bars, window, floor, alpha, horizons, weights)

    b1_trades = run_desired_positions(bars, direct_state(features, qe))
    b2_trades = run_desired_positions(bars, hysteresis_state(features, qe, qx))

    # forward 30m outcome per decision bar + which side B1 fires
    fwd = add_forward_target(features, bars, int(CONFIG["forward_horizon_minutes"]))
    d1 = direct_state(features, qe)
    fwd = fwd.merge(d1[["date", "tod", "desired"]], on=["date", "tod"], how="left")

    dists: dict[str, np.ndarray] = {
        "B1_long_pnl": b1_trades.loc[b1_trades["side"] == 1, "points"].to_numpy(),
        "B1_short_pnl": b1_trades.loc[b1_trades["side"] == -1, "points"].to_numpy(),
        "B2_long_pnl": b2_trades.loc[b2_trades["side"] == 1, "points"].to_numpy(),
        "B2_short_pnl": b2_trades.loc[b2_trades["side"] == -1, "points"].to_numpy(),
        "fwd30_unconditional": fwd["forward_points"].to_numpy(),
        "fwd30_B1_long_on": fwd.loc[fwd["desired"] == 1, "forward_points"].to_numpy(),
        "fwd30_B1_short_on": fwd.loc[fwd["desired"] == -1, "forward_points"].to_numpy(),
    }

    rows = []
    for name, x in dists.items():
        d = describe(x)
        d["dist"] = name
        d["kde_modes"] = kde_modes(x)
        rows.append(d)
    table = pd.DataFrame(rows).set_index("dist")
    cols = ["n", "mean", "sd", "median", "skew", "excess_kurt", "bimod_coef",
            "kde_modes", "dip_p", "q05", "q25", "q75", "q95"]
    table = table[cols]
    out_csv = FIGDIR / "outcome_distribution_stats.csv"
    table.to_csv(out_csv)
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print(table.round(4).to_string())
    print(f"\nsaved: {out_csv}")

    # Figure 1: realized trade P&L, long vs short, B1 and B2
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
    plot_hist_kde(axes[0, 0], dists["B1_long_pnl"], "B1 long", "tab:green")
    plot_hist_kde(axes[0, 1], dists["B1_short_pnl"], "B1 short", "tab:red")
    plot_hist_kde(axes[1, 0], dists["B2_long_pnl"], "B2 long", "tab:green")
    plot_hist_kde(axes[1, 1], dists["B2_short_pnl"], "B2 short", "tab:red")
    for ax, ttl in zip(axes.ravel(), ["B1 long", "B1 short", "B2 long", "B2 short"]):
        ax.set_title(f"{ttl} realized P&L (points)")
        ax.legend(fontsize=8)
    fig.suptitle("NQ signal realized per-trade P&L distribution (clipped +/-40 pts)")
    fig.tight_layout()
    f1 = FIGDIR / "fig1_trade_pnl_by_side.png"
    fig.savefig(f1, dpi=110)
    plt.close(fig)

    # Figure 2: underlying 30m forward outcome, unconditional vs signal-on
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    plot_hist_kde(axes[0], dists["fwd30_unconditional"], "all bars", "tab:blue", clip=(-30, 30))
    axes[0].set_title("30m forward outcome (points) — unconditional")
    plot_hist_kde(axes[1], dists["fwd30_B1_long_on"], "B1 long-on", "tab:green", clip=(-30, 30))
    plot_hist_kde(axes[1], dists["fwd30_B1_short_on"], "B1 short-on", "tab:red", clip=(-30, 30))
    axes[1].set_title("30m forward outcome — conditional on B1 signal")
    for ax in axes:
        ax.legend(fontsize=8)
    fig.suptitle("NQ characteristic (30m forward) return — is it bimodal?")
    fig.tight_layout()
    f2 = FIGDIR / "fig2_forward_outcome.png"
    fig.savefig(f2, dpi=110)
    plt.close(fig)

    print(f"saved: {f1}\nsaved: {f2}")


if __name__ == "__main__":
    main()
