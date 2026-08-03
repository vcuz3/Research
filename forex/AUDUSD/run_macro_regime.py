"""
run_macro_regime.py — Step-3 end-to-end driver.

Builds the AUDUSD macro-driver regime-labelled dataset, all diagnostic tables,
and charts, and writes them to data/ and results/.

Two regime layers are produced (see macro_regime.py):
  * macro_regime : FULL contest — the dominant *explainer* of AUDUSD
                   (regional_fx / usd dominate; this is a structural fact).
  * idio_regime  : IDIOSYNCRATIC contest — net of the USD axis and the
                   commodity-bloc (NZD) co-move, which AUD-specific driver
                   (china / commodity / risk / rates) leads.  This is the
                   discriminating layer used for behaviour-by-regime analysis.

Usage:  python run_macro_regime.py
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

import macro_regime as mr

RESULTS = "results"
FIGDIR = os.path.join(RESULTS, "figures")
DATA = "data"
ANN = np.sqrt(252)                      # daily -> annualised

# consistent regime colour map
REGIME_COLORS = {
    "usd": "#4C78A8", "china": "#E45756", "commodity": "#F58518",
    "risk": "#B279A2", "rates": "#54A24B", "regional_fx": "#72B7B2",
    "low_signal": "#BAB0AC",
}


# --------------------------------------------------------------------------- #
# Behaviour-by-regime tables
# --------------------------------------------------------------------------- #
def behavior_table(reg: pd.DataFrame, label_col: str) -> pd.DataFrame:
    """
    Contemporaneous behaviour of AUDUSD within each regime:
      mean daily return, annualised vol, directional (up-day) share, daily
      Sharpe, and a t-stat on the mean (naive; days within a regime are treated
      as the sample — serial correlation caveat applies).
    """
    df = reg.dropna(subset=[label_col, "audusd_ret"]).copy()
    g = df.groupby(label_col, observed=True)["audusd_ret"]
    n = g.size()
    mean = g.mean()
    std = g.std()
    rows = pd.DataFrame({
        "days": n,
        "share": n / n.sum(),
        "mean_ret_bp": mean * 1e4,
        "ann_vol_pct": std * ANN * 100,
        "up_day_share": df.groupby(label_col, observed=True)["audusd_ret"]
                          .apply(lambda s: float((s > 0).mean())),
        "daily_sharpe_ann": (mean / std) * ANN,
        "t_mean": mean / (std / np.sqrt(n)),
    })
    return rows.sort_values("days", ascending=False)


def forward_table(reg: pd.DataFrame, label_col: str, horizon: int = 1) -> pd.DataFrame:
    """
    PREDICTIVE view: does the regime *as of day t* forecast the forward return?
    Uses the regime label known at t's close to predict the return over the next
    `horizon` days — strictly no look-ahead.  Reports directional-bias suitability
    (is the regime good for long vs short) and forward predictability.
    """
    df = reg.copy()
    logp = np.log(df["audusd_ret"].add(0))          # placeholder to keep index
    # forward cumulative return over `horizon` days
    fwd = (df["audusd_ret"].shift(-1)
             .rolling(horizon).sum().shift(-(horizon - 1)))
    # simpler & exact: sum of next `horizon` daily returns
    r = df["audusd_ret"].to_numpy()
    n = len(r)
    fwd = np.full(n, np.nan)
    csum = np.concatenate([[0.0], np.nancumsum(r)])
    for t in range(n - horizon):
        fwd[t] = csum[t + 1 + horizon] - csum[t + 1]     # r[t+1..t+horizon]
    df = df.assign(fwd=fwd).dropna(subset=[label_col, "fwd"])
    g = df.groupby(label_col, observed=True)["fwd"]
    nn = g.size()
    mean = g.mean()
    std = g.std()
    out = pd.DataFrame({
        "n": nn,
        f"fwd{horizon}d_mean_bp": mean * 1e4,
        f"fwd{horizon}d_hit_up": df.groupby(label_col, observed=True)["fwd"]
                                   .apply(lambda s: float((s > 0).mean())),
        f"fwd{horizon}d_sharpe_ann": (mean / std) * np.sqrt(252 / horizon),
        # t-stat on non-overlapping samples (every `horizon`-th day per regime)
        f"fwd{horizon}d_t_nonovlp": g.apply(
            lambda s: _t_nonoverlap(s.to_numpy(), horizon)),
    })
    return out.sort_values("n", ascending=False)


def _t_nonoverlap(x: np.ndarray, horizon: int) -> float:
    x = x[np.isfinite(x)][::horizon]                  # thin to non-overlapping
    if len(x) < 5 or x.std(ddof=1) == 0:
        return np.nan
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def driver_strength_by_regime(reg: pd.DataFrame, label_col: str) -> pd.DataFrame:
    """Mean per-regime *contribution* (variance share) of every driver bucket."""
    rc = reg.attrs["reg_contrib"].reindex(reg.index)
    df = rc.join(reg[label_col]).dropna(subset=[label_col])
    return df.groupby(label_col, observed=True).mean(numeric_only=True)


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _regime_spans(dates: pd.DatetimeIndex, labels: pd.Series):
    """Yield (start, end, label) contiguous spans for shading."""
    labels = labels.to_numpy()
    if len(labels) == 0:
        return
    start = 0
    for i in range(1, len(labels)):
        if labels[i] != labels[start]:
            yield dates[start], dates[i], labels[start]
            start = i
    yield dates[start], dates[-1], labels[start]


def chart_price_by_regime(levels, reg, label_col, path, title):
    fig, ax = plt.subplots(figsize=(14, 5))
    px = levels["audusd"].reindex(reg.index)
    ax.plot(reg.index, px, color="black", lw=0.7, zorder=3)
    seen = set()
    for s, e, lab in _regime_spans(reg.index, reg[label_col].fillna("low_signal")):
        ax.axvspan(s, e, color=REGIME_COLORS.get(lab, "#ccc"), alpha=0.35,
                   lw=0, label=lab if lab not in seen else None)
        seen.add(lab)
    ax.set_title(title)
    ax.set_ylabel("AUDUSD")
    ax.legend(loc="upper right", ncol=4, fontsize=8, framealpha=0.9)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def chart_frequency_over_time(reg, label_col, path):
    df = reg.dropna(subset=[label_col]).copy()
    df["year"] = df.index.year
    ct = (df.groupby(["year", label_col], observed=True).size()
            .unstack(fill_value=0))
    ct = ct.div(ct.sum(axis=1), axis=0)
    cols = [c for c in mr.ALL_REGIMES if c in ct.columns]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.stackplot(ct.index, *[ct[c] for c in cols],
                 labels=cols, colors=[REGIME_COLORS[c] for c in cols])
    ax.set_title(f"Regime frequency over time — {label_col}")
    ax.set_ylabel("share of days"); ax.set_xlabel("year")
    ax.set_ylim(0, 1); ax.legend(loc="upper center", ncol=len(cols), fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def chart_dashboard(reg, label_col, beh, fwd, dstr, tmat, path):
    cols = [c for c in mr.ALL_REGIMES if c in beh.index]
    colors = [REGIME_COLORS[c] for c in cols]
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))

    # 1. mean daily return by regime
    ax = axes[0, 0]
    ax.bar(cols, beh.loc[cols, "mean_ret_bp"], color=colors)
    ax.axhline(0, color="k", lw=0.6); ax.set_title("Mean daily AUDUSD return (bp)")
    ax.tick_params(axis="x", rotation=45)

    # 2. annualised vol by regime
    ax = axes[0, 1]
    ax.bar(cols, beh.loc[cols, "ann_vol_pct"], color=colors)
    ax.set_title("Annualised vol (%)"); ax.tick_params(axis="x", rotation=45)

    # 3. directional (up-day) share
    ax = axes[0, 2]
    ax.bar(cols, beh.loc[cols, "up_day_share"], color=colors)
    ax.axhline(0.5, color="k", lw=0.6, ls="--")
    ax.set_ylim(0.4, 0.6); ax.set_title("Up-day share"); ax.tick_params(axis="x", rotation=45)

    # 4. driver strength heatmap (mean contribution)
    ax = axes[1, 0]
    d = dstr.reindex(cols)
    im = ax.imshow(d.values, aspect="auto", cmap="RdBu_r", vmin=-0.2, vmax=0.6)
    ax.set_xticks(range(len(d.columns))); ax.set_xticklabels(d.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(d.index))); ax.set_yticklabels(d.index, fontsize=8)
    ax.set_title("Mean driver contribution by regime"); fig.colorbar(im, ax=ax, shrink=0.8)

    # 5. forward 5d Sharpe by regime (predictive)
    ax = axes[1, 1]
    sc = [c for c in cols if c in fwd.index]
    fwd_col = "fwd5d_sharpe_ann" if "fwd5d_sharpe_ann" in fwd.columns else fwd.columns[3]
    ax.bar(sc, fwd.reindex(sc)[fwd_col].values, color=[REGIME_COLORS[c] for c in sc])
    ax.axhline(0, color="k", lw=0.6); ax.set_title(f"Forward Sharpe (predictive) — {fwd_col}")
    ax.tick_params(axis="x", rotation=45)

    # 6. transition matrix heatmap
    ax = axes[1, 2]
    tc = [c for c in cols if c in tmat.index]
    T = tmat.reindex(index=tc, columns=tc)
    im = ax.imshow(T.values, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(tc))); ax.set_xticklabels(tc, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(tc))); ax.set_yticklabels(tc, fontsize=8)
    for i in range(len(tc)):
        for j in range(len(tc)):
            v = T.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        color="white" if v > 0.5 else "black", fontsize=7)
    ax.set_title("Transition matrix P(to|from)"); ax.set_ylabel("from"); ax.set_xlabel("to")

    fig.suptitle(f"AUDUSD macro-regime diagnostics — {label_col}", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.97]); fig.savefig(path, dpi=110); plt.close(fig)


# --------------------------------------------------------------------------- #
# Comparison-method agreement
# --------------------------------------------------------------------------- #
def method_comparison(panel, levels, reg, cfg) -> pd.DataFrame:
    """Agreement of the primary (idio) regime with the secondary methods."""
    prim = reg["idio_regime"]
    methods = {
        "corr_dominance": mr.corr_dominance_regime(panel, cfg),
        "pca_dominance": mr.pca_dominance_regime(panel, cfg),
        "rules_based": mr.rules_based_regime(levels, panel, cfg),
        "kmeans_cluster": mr.cluster_regime(reg, cfg),
    }
    rows = []
    idx = reg.loc["2013-01-01":].index
    for name, s in methods.items():
        a = prim.reindex(idx)
        b = s.reindex(idx)
        m = a.notna() & b.notna()
        agree = float((a[m] == b[m]).mean()) if m.any() else np.nan
        rows.append({"method": name, "agreement_with_idio": agree,
                     "n": int(m.sum())})
    return pd.DataFrame(rows).set_index("method"), methods


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    os.makedirs(FIGDIR, exist_ok=True)
    cfg = mr.RegimeConfig()

    levels = mr.load_levels()
    panel = mr.build_driver_panel(levels)
    rates_src = panel.attrs.get("rates_source", "?")
    print(f"rates driver source: {rates_src}"
          + ("  (genuine daily AU–US differential from bond futures)"
             if rates_src == "futures"
             else "  (US-2Y proxy — run download_rates_futures_ibkr.py to upgrade)"))
    reg = mr.assign_macro_regimes(panel, cfg)

    # focus analysis on the coherent 2013+ window (intraday-panel era; before
    # 2013 macro PIT is absent and some drivers start later)
    reg_full = reg
    reg = reg.loc["2013-01-01":].copy()
    levels13 = levels.loc["2013-01-01":]

    # ---- save the labelled dataset (full history) --------------------------
    keep = ["audusd_ret", "macro_regime", "idio_regime", "dominant_driver",
            "dominant_beta", "dominant_corr", "dominant_tstat", "rolling_r2",
            "dominant_regime_contribution", "second_strongest_regime",
            "second_regime_contribution", "dominance_ratio",
            "macro_ex_contribution", "macro_ex_dominance", "regional_contribution",
            "confidence_score", "regime_stability", "regime_duration",
            "regime_short", "regime_long", "r2_short", "r2_long"]
    keep = [c for c in keep if c in reg_full.columns]
    out_path = os.path.join(DATA, "audusd_macro_regime_daily.csv")
    reg_full[keep].to_csv(out_path)
    print(f"saved labelled dataset -> {out_path}  {reg_full[keep].shape}")

    # ---- tables for BOTH layers --------------------------------------------
    summary = {}
    for label_col in ["macro_regime", "idio_regime"]:
        beh = behavior_table(reg, label_col)
        fwd1 = forward_table(reg, label_col, horizon=1)
        fwd5 = forward_table(reg, label_col, horizon=5).drop(columns=["n"])
        fwd = fwd1.join(fwd5)
        dstr = driver_strength_by_regime(reg, label_col)
        tmat = mr.transition_matrix(reg[label_col])
        pers = mr.persistence_stats(reg[label_col])
        freq = reg[label_col].value_counts(normalize=True)

        beh.to_csv(f"{RESULTS}/regime_behavior_{label_col}.csv")
        fwd.to_csv(f"{RESULTS}/regime_forward_{label_col}.csv")
        dstr.to_csv(f"{RESULTS}/regime_driver_strength_{label_col}.csv")
        tmat.to_csv(f"{RESULTS}/regime_transition_{label_col}.csv")
        pers.to_csv(f"{RESULTS}/regime_persistence_{label_col}.csv")

        chart_price_by_regime(levels13, reg, label_col,
                              f"{FIGDIR}/price_by_{label_col}.png",
                              f"AUDUSD coloured by {label_col} (2013+)")
        chart_frequency_over_time(reg, label_col, f"{FIGDIR}/frequency_{label_col}.png")
        chart_dashboard(reg, label_col, beh, fwd, dstr, tmat,
                        f"{FIGDIR}/dashboard_{label_col}.png")

        summary[label_col] = dict(beh=beh, fwd=fwd, pers=pers, freq=freq,
                                  dstr=dstr, tmat=tmat)
        print(f"\n================= {label_col} (2013+) =================")
        print("frequency:\n", freq.round(3).to_string())
        print("\nbehaviour (contemporaneous):\n", beh.round(3).to_string())
        print("\nforward predictive:\n", fwd.round(3).to_string())
        print("\npersistence:\n", pers.round(3).to_string())

    # ---- comparison methods -------------------------------------------------
    cmp_df, methods = method_comparison(panel, levels, reg, cfg)
    cmp_df.to_csv(f"{RESULTS}/regime_method_comparison.csv")
    # also save each method's labels aligned for inspection
    comp_labels = pd.DataFrame({k: v for k, v in methods.items()})
    comp_labels["idio_regime"] = reg_full["idio_regime"]
    comp_labels["macro_regime"] = reg_full["macro_regime"]
    comp_labels.loc["2013-01-01":].to_csv(f"{RESULTS}/regime_all_methods_labels.csv")
    print("\n================= method comparison =================")
    print(cmp_df.round(3).to_string())
    for name, s in methods.items():
        vc = s.reindex(reg.index).value_counts(normalize=True).round(3)
        print(f"\n{name} freq:\n{vc.to_string()}")

    print("\nDONE. figures in", FIGDIR)


if __name__ == "__main__":
    main()
