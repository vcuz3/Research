"""
run_macro_econ_regime.py — Step-3b end-to-end: fundamental AU–US economic-
strength regime classifier for AUDUSD, with honest small-sample evaluation.

Answers:
  * Does AUDUSD trade richer when the AU economy is relatively strong? (level)
  * Does the strength regime forecast forward AUDUSD returns? (timing)
  * Is a fundamentals misalignment (rich/cheap vs fair value) mean-reverting?
  * Are the effects significant given ~105 sticky monthly observations?

Outputs: results/econ_regime_*.csv, results/figures/econ_*.png
Usage:  python run_macro_econ_regime.py
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import macro_econ_regime as er
from macro_regime import transition_matrix, persistence_stats

RESULTS = "results"
FIGDIR = os.path.join(RESULTS, "figures")
ANN_M = np.sqrt(12)                    # monthly -> annualised

REGIME_COLORS = {
    "AU_strong": "#2E7D32", "balanced": "#BAB0AC", "AU_weak": "#C62828",
}
QUAD_COLORS = {
    "reflation": "#2E7D32", "overheating": "#F58518",
    "stagflation": "#C62828", "slowdown": "#4C78A8",
}


# --------------------------------------------------------------------------- #
def behavior_by_regime(reg: pd.DataFrame, label: str) -> pd.DataFrame:
    """Contemporaneous AUDUSD behaviour within each regime."""
    d = reg.dropna(subset=[label, "ret_1m"])
    g = d.groupby(label, observed=True)
    out = pd.DataFrame({
        "months": g.size(),
        "share": g.size() / len(d),
        "mean_audusd_level": g["audusd"].mean(),
        "mean_ret_1m_bp": g["ret_1m"].mean() * 1e4,
        "ann_vol_pct": g["ret_1m"].std() * ANN_M * 100,
        "up_month_share": g["ret_1m"].apply(lambda s: float((s > 0).mean())),
    })
    return out


def forward_by_regime(reg: pd.DataFrame, label: str, horizons) -> pd.DataFrame:
    """Predictive: forward return by regime known AS OF month t (no look-ahead)."""
    d = er.forward_returns(reg, horizons)
    d = d.dropna(subset=[label])
    g = d.groupby(label, observed=True)
    cols = {}
    for h in horizons:
        cols[f"fwd_{h}m_mean_bp"] = g[f"fwd_{h}m"].mean() * 1e4
        cols[f"fwd_{h}m_hit_up"] = g[f"fwd_{h}m"].apply(lambda s: float((s.dropna() > 0).mean()))
    return pd.DataFrame(cols)


def predictive_ic(reg: pd.DataFrame, cfg) -> pd.DataFrame:
    """Block-bootstrap rank-IC of strength_z vs forward returns (honest CI)."""
    d = er.forward_returns(reg, cfg.fwd_horizons)
    rows = []
    for h in cfg.fwd_horizons:
        ic, lo, hi, p = er.block_bootstrap_ic(d["strength_z"], d[f"fwd_{h}m"], cfg)
        rows.append({"horizon_m": h, "rank_ic": ic, "ci5": lo, "ci95": hi,
                     "boot_p": p, "significant_5pct": bool(p < 0.05)})
    return pd.DataFrame(rows).set_index("horizon_m")


def regime_tilt_strategy(reg: pd.DataFrame, cfg) -> dict:
    """
    Simplest fundamental overlay: hold AUD long in AU_strong, short in AU_weak,
    flat in balanced; realise next-month return.  Also a continuous tanh(z) tilt.
    Reports monthly Sharpe with a moving-block-bootstrap CI (no costs — this is a
    slow monthly overlay; costs are negligible vs the intraday layer).
    """
    d = er.forward_returns(reg, (1,)).dropna(subset=["strength_regime", "fwd_1m"])
    pos_map = {"AU_strong": 1.0, "balanced": 0.0, "AU_weak": -1.0}
    pos = d["strength_regime"].map(pos_map).to_numpy()
    fwd = d["fwd_1m"].to_numpy()
    disc = pos * fwd
    cont_pos = np.tanh(d["strength_z"].to_numpy())
    cont = cont_pos * fwd

    def sharpe_boot(x):
        x = x[np.isfinite(x)]
        if len(x) < cfg.block_len + 5 or x.std(ddof=1) == 0:
            return np.nan, np.nan, np.nan
        sr = x.mean() / x.std(ddof=1) * np.sqrt(12)
        rng = np.random.default_rng(cfg.seed)
        L = cfg.block_len; n = len(x); nb = int(np.ceil(n / L))
        starts = np.arange(0, n - L + 1)
        boots = []
        for _ in range(cfg.n_boot):
            st = rng.choice(starts, size=nb, replace=True)
            idx = np.concatenate([np.arange(s, s + L) for s in st])[:n]
            xb = x[idx]
            if xb.std(ddof=1) > 0:
                boots.append(xb.mean() / xb.std(ddof=1) * np.sqrt(12))
        lo, hi = np.nanpercentile(boots, [5, 95])
        return sr, lo, hi

    sr_d, lo_d, hi_d = sharpe_boot(disc)
    sr_c, lo_c, hi_c = sharpe_boot(cont)
    return {
        "n_months": int(len(d)),
        "discrete_sharpe_ann": sr_d, "discrete_ci5": lo_d, "discrete_ci95": hi_d,
        "discrete_hit": float((disc > 0).mean()),
        "continuous_sharpe_ann": sr_c, "continuous_ci5": lo_c, "continuous_ci95": hi_c,
    }


def fair_value_test(reg: pd.DataFrame, cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Causal fair-value residual + does misalignment predict forward returns?"""
    fv = er.fair_value_residual(reg)
    joined = reg.join(fv["misalignment"])
    joined = er.forward_returns(joined, cfg.fwd_horizons)
    rows = []
    for h in cfg.fwd_horizons:
        ic, lo, hi, p = er.block_bootstrap_ic(joined["misalignment"], joined[f"fwd_{h}m"], cfg)
        rows.append({"horizon_m": h, "rank_ic_misalign_vs_fwd": ic,
                     "ci5": lo, "ci95": hi, "boot_p": p,
                     "significant_5pct": bool(p < 0.05)})
    return fv, pd.DataFrame(rows).set_index("horizon_m")


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _spans(dates, labels):
    labels = labels.to_numpy()
    start = 0
    for i in range(1, len(labels)):
        if labels[i] != labels[start]:
            yield dates[start], dates[i], labels[start]; start = i
    yield dates[start], dates[-1], labels[start]


def chart_level_and_strength(reg, path):
    d = reg.dropna(subset=["strength_regime"])
    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.plot(d.index, d["audusd"], color="black", lw=1.2, zorder=3, label="AUDUSD")
    seen = set()
    for s, e, lab in _spans(d.index, d["strength_regime"].fillna("balanced")):
        ax.axvspan(s, e, color=REGIME_COLORS.get(lab, "#ccc"), alpha=0.30, lw=0,
                   label=lab if lab not in seen else None); seen.add(lab)
    ax2 = ax.twinx()
    ax2.plot(d.index, d["strength_z"], color="#1f4e79", lw=1.4, ls="--",
             label="AU–US strength z")
    ax2.axhline(0, color="#1f4e79", lw=0.5, alpha=0.5)
    ax.set_ylabel("AUDUSD"); ax2.set_ylabel("AU–US economic-strength z-score")
    ax.set_title("AUDUSD vs AU–US fundamental economic-strength regime (PIT, monthly)")
    l1, la1 = ax.get_legend_handles_labels(); l2, la2 = ax2.get_legend_handles_labels()
    ax.legend(l1 + l2, la1 + la2, loc="upper right", fontsize=8, ncol=2)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def chart_scatter(reg, path):
    d = reg.dropna(subset=["strength_z", "audusd"])
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    sc = ax.scatter(d["strength_z"], d["audusd"], c=d.index.year, cmap="viridis", s=22)
    r = d["strength_z"].corr(d["audusd"])
    b = np.polyfit(d["strength_z"], d["audusd"], 1)
    xs = np.linspace(d["strength_z"].min(), d["strength_z"].max(), 50)
    ax.plot(xs, b[0]*xs + b[1], color="black", lw=1)
    ax.set_xlabel("AU–US economic-strength z-score"); ax.set_ylabel("AUDUSD level")
    ax.set_title(f"Strength vs AUDUSD level  (Pearson r={r:.2f})")
    fig.colorbar(sc, ax=ax, label="year")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def chart_behavior(beh, fwd, path):
    cols = [c for c in ["AU_strong", "balanced", "AU_weak"] if c in beh.index]
    colors = [REGIME_COLORS[c] for c in cols]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    axes[0].bar(cols, beh.loc[cols, "mean_audusd_level"], color=colors)
    axes[0].set_title("Mean AUDUSD level by regime"); axes[0].tick_params(axis="x", rotation=20)
    axes[1].bar(cols, beh.loc[cols, "mean_ret_1m_bp"], color=colors)
    axes[1].axhline(0, color="k", lw=.6); axes[1].set_title("Mean 1m return (bp, contemporaneous)")
    axes[1].tick_params(axis="x", rotation=20)
    fc = [c for c in cols if c in fwd.index]
    axes[2].bar(fc, fwd.loc[fc, "fwd_3m_mean_bp"], color=[REGIME_COLORS[c] for c in fc])
    axes[2].axhline(0, color="k", lw=.6); axes[2].set_title("Mean fwd-3m return (bp, predictive)")
    axes[2].tick_params(axis="x", rotation=20)
    fig.suptitle("AUDUSD behaviour by AU–US economic-strength regime")
    fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(path, dpi=110); plt.close(fig)


# --------------------------------------------------------------------------- #
def main():
    os.makedirs(FIGDIR, exist_ok=True)
    cfg = er.EconRegimeConfig()
    df = er.load_factor_panel()
    reg = er.assign_econ_regimes(df, cfg)

    labelled = reg.dropna(subset=["strength_regime"])
    print(f"labelled months: {len(labelled)}  "
          f"{labelled.index.min().date()} -> {labelled.index.max().date()}")

    # save labelled dataset
    keep = ["audusd", "ret_1m", "strength_z", "growth_z", "inflation_z",
            "monetary_z", "external_z", "n_components", "strength_regime",
            "gi_quadrant", "confidence", "regime_duration"]
    reg[keep].to_csv("data/audusd_econ_regime_monthly.csv")
    print("saved -> data/audusd_econ_regime_monthly.csv")

    # ---- tables ------------------------------------------------------------
    beh = behavior_by_regime(reg, "strength_regime")
    fwd = forward_by_regime(reg, "strength_regime", cfg.fwd_horizons)
    quad_beh = behavior_by_regime(reg, "gi_quadrant")
    ic = predictive_ic(reg, cfg)
    strat = regime_tilt_strategy(reg, cfg)
    fv, fv_ic = fair_value_test(reg, cfg)
    tmat = transition_matrix(labelled["strength_regime"])
    pers = persistence_stats(labelled["strength_regime"])
    level_corr = reg["strength_z"].corr(reg["audusd"])

    beh.to_csv(f"{RESULTS}/econ_regime_behavior.csv")
    fwd.to_csv(f"{RESULTS}/econ_regime_forward.csv")
    quad_beh.to_csv(f"{RESULTS}/econ_quadrant_behavior.csv")
    ic.to_csv(f"{RESULTS}/econ_regime_predictive_ic.csv")
    fv_ic.to_csv(f"{RESULTS}/econ_fair_value_ic.csv")
    tmat.to_csv(f"{RESULTS}/econ_regime_transition.csv")
    pers.to_csv(f"{RESULTS}/econ_regime_persistence.csv")
    pd.Series(strat).to_csv(f"{RESULTS}/econ_regime_tilt_strategy.csv")

    # ---- charts ------------------------------------------------------------
    chart_level_and_strength(reg, f"{FIGDIR}/econ_level_and_strength.png")
    chart_scatter(reg, f"{FIGDIR}/econ_strength_vs_level_scatter.png")
    chart_behavior(beh, fwd, f"{FIGDIR}/econ_behavior_by_regime.png")

    # ---- print summary -----------------------------------------------------
    print(f"\ncorr(strength_z, AUDUSD level) = {level_corr:.3f}")
    print("\nstrength_regime frequency:\n",
          labelled["strength_regime"].value_counts(normalize=True).round(3).to_string())
    print("\nbehaviour by regime:\n", beh.round(3).to_string())
    print("\nforward returns by regime (predictive):\n", fwd.round(2).to_string())
    print("\npredictive rank-IC (strength_z vs fwd, block-bootstrap CI):\n", ic.round(3).to_string())
    print("\nfair-value misalignment vs fwd returns (mean-reversion test):\n", fv_ic.round(3).to_string())
    print("\nregime-tilt overlay strategy:")
    for k, v in strat.items():
        print(f"   {k}: {v:.3f}" if isinstance(v, float) else f"   {k}: {v}")
    print("\npersistence:\n", pers.round(3).to_string())
    print("\nDONE. figures in", FIGDIR)


if __name__ == "__main__":
    main()
