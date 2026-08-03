"""
fairvalue_panel_test.py — cross-currency ROBUSTNESS test of the Step-3b
fair-value mean-reversion finding.

Question: is "a commodity currency mean-reverts to its fundamental fair value"
a real pattern, or a single-cycle AUD artifact?  We rebuild a causal fair-value
model for AUD, NZD and CAD over 1999–2026 (multi-cycle) and test whether the
misalignment predicts forward returns — per currency and pooled.

Fair-value model (per currency, CAUSAL expanding OLS, both regressors observed /
PIT-safe):
    log(FX) ~ a + b1 * rate_diff(country − US) + b2 * log(terms_of_trade)
Fit on data up to month t only; misalignment = actual − fair (positive = rich).

Controls / honesty:
  * a PURE-TECHNICAL control — deviation of log(FX) from its trailing 12m mean —
    tests whether the FUNDAMENTALS add anything beyond generic price reversion;
  * moving-block bootstrap (respecting within-currency autocorrelation) for CIs;
  * a slow monthly overlay (fade richness) with bootstrap-CI Sharpe, per currency
    and pooled, to see if any of it is monetizable.

Outputs: results/fairvalue_panel_*.csv, results/figures/fairvalue_*.png
Usage:  python fairvalue_panel_test.py   (needs data/commodity_fx_panel_monthly.csv)
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = "results"
FIGDIR = os.path.join(RESULTS, "figures")
PANEL = "data/commodity_fx_panel_monthly.csv"
CCYS = ["au", "nz", "ca"]
FXCOL = {"au": "audusd", "nz": "nzdusd", "ca": "cadusd"}
NAME = {"au": "AUDUSD", "nz": "NZDUSD", "ca": "CADUSD"}
HORIZONS = (1, 3, 6, 12)
MIN_TRAIN = 60           # months before first fair-value estimate (expanding)
BLOCK = 12               # bootstrap block length (months)
NBOOT = 5000
SEED = 0


# --------------------------------------------------------------------------- #
def load_panel() -> pd.DataFrame:
    return pd.read_csv(PANEL, index_col=0, parse_dates=True).sort_index()


def fair_value(df: pd.DataFrame, ccy: str) -> pd.DataFrame:
    """Causal expanding OLS fair value + misalignment for one currency."""
    sub = df[[FXCOL[ccy], f"rate_diff_{ccy}", f"log_tot_{ccy}"]].dropna()
    y = np.log(sub[FXCOL[ccy]].to_numpy("float64"))
    X = np.column_stack([sub[f"rate_diff_{ccy}"].to_numpy("float64"),
                         sub[f"log_tot_{ccy}"].to_numpy("float64")])
    n = len(sub)
    fair = np.full(n, np.nan)
    for t in range(MIN_TRAIN, n):
        A = np.column_stack([np.ones(t), X[:t]])
        beta, *_ = np.linalg.lstsq(A, y[:t], rcond=None)
        fair[t] = beta[0] + beta[1:] @ X[t]
    mis = y - fair
    # pure-technical control: deviation from trailing 12m mean of log FX
    logfx = pd.Series(y, index=sub.index)
    ma_dev = (logfx - logfx.rolling(12, min_periods=12).mean()).to_numpy()
    out = pd.DataFrame({"logfx": y, "fair": fair, "misalignment": mis,
                        "ma_dev": ma_dev}, index=sub.index)
    # forward returns
    for h in HORIZONS:
        out[f"fwd_{h}m"] = pd.Series(y, index=sub.index).shift(-h) - pd.Series(y, index=sub.index)
    return out


def _spearman(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 8:
        return np.nan
    return float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman"))


def block_boot_ic(segments, seed=SEED):
    """
    Moving-block bootstrap IC over one or more (x, y) segments (segments =
    currencies).  Blocks are drawn WITHIN each segment to preserve serial
    dependence, then pooled.  Returns (ic, ci5, ci95, p_two_sided).
    """
    xs = [np.asarray(x, float) for x, _ in segments]
    ys = [np.asarray(y, float) for _, y in segments]
    # point estimate = pooled spearman on finite pairs
    X = np.concatenate(xs); Y = np.concatenate(ys)
    ic = _spearman(X, Y)
    rng = np.random.default_rng(seed)
    boots = np.full(NBOOT, np.nan)
    for b in range(NBOOT):
        bx, by = [], []
        for x, y in zip(xs, ys):
            n = len(x)
            if n < BLOCK + 2:
                continue
            nb = int(np.ceil(n / BLOCK))
            starts = rng.integers(0, n - BLOCK + 1, size=nb)
            idx = np.concatenate([np.arange(s, s + BLOCK) for s in starts])[:n]
            bx.append(x[idx]); by.append(y[idx])
        if bx:
            boots[b] = _spearman(np.concatenate(bx), np.concatenate(by))
    lo, hi = np.nanpercentile(boots, [5, 95])
    fp = np.nanmean(boots > 0)
    p = 2 * min(fp, 1 - fp)
    return ic, lo, hi, p


def overlay_sharpe(segments, seed=SEED):
    """Fade-richness overlay: pos = -sign(signal); next-period return; pooled
    monthly Sharpe with block-bootstrap CI (signal-return pairs per currency)."""
    rets = []
    for sig, fwd1 in segments:
        sig = np.asarray(sig, float); fwd1 = np.asarray(fwd1, float)
        m = np.isfinite(sig) & np.isfinite(fwd1)
        rets.append(-np.sign(sig[m]) * fwd1[m])
    allr = np.concatenate(rets)
    if len(allr) < BLOCK + 5 or allr.std(ddof=1) == 0:
        return np.nan, np.nan, np.nan, np.nan
    sr = allr.mean() / allr.std(ddof=1) * np.sqrt(12)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(NBOOT):
        chunks = []
        for r in rets:
            n = len(r)
            if n < BLOCK + 2:
                continue
            nb = int(np.ceil(n / BLOCK))
            starts = rng.integers(0, n - BLOCK + 1, size=nb)
            idx = np.concatenate([np.arange(s, s + BLOCK) for s in starts])[:n]
            chunks.append(r[idx])
        rb = np.concatenate(chunks)
        if rb.std(ddof=1) > 0:
            boots.append(rb.mean() / rb.std(ddof=1) * np.sqrt(12))
    lo, hi = np.nanpercentile(boots, [5, 95])
    return sr, lo, hi, float((allr > 0).mean())


# --------------------------------------------------------------------------- #
def main():
    os.makedirs(FIGDIR, exist_ok=True)
    df = load_panel()
    fv = {c: fair_value(df, c) for c in CCYS}

    # ---- 1. per-currency & pooled IC: fundamental misalignment vs fwd ------
    rows = []
    for h in HORIZONS:
        segs = [(fv[c]["misalignment"].to_numpy(), fv[c][f"fwd_{h}m"].to_numpy())
                for c in CCYS]
        # per currency
        for c in CCYS:
            ic, lo, hi, p = block_boot_ic([(fv[c]["misalignment"].to_numpy(),
                                            fv[c][f"fwd_{h}m"].to_numpy())])
            rows.append({"signal": "fundamental_misalign", "scope": NAME[c],
                         "horizon_m": h, "rank_ic": ic, "ci5": lo, "ci95": hi, "boot_p": p})
        icp, lop, hip, pp = block_boot_ic(segs)
        rows.append({"signal": "fundamental_misalign", "scope": "POOLED",
                     "horizon_m": h, "rank_ic": icp, "ci5": lop, "ci95": hip, "boot_p": pp})
        # technical control (pooled only)
        segs_ma = [(fv[c]["ma_dev"].to_numpy(), fv[c][f"fwd_{h}m"].to_numpy()) for c in CCYS]
        icm, lom, him, pm = block_boot_ic(segs_ma)
        rows.append({"signal": "technical_ma_dev(control)", "scope": "POOLED",
                     "horizon_m": h, "rank_ic": icm, "ci5": lom, "ci95": him, "boot_p": pm})
    ic_tbl = pd.DataFrame(rows)
    ic_tbl.to_csv(f"{RESULTS}/fairvalue_panel_ic.csv", index=False)

    # ---- 2. fade-richness overlay (monthly), fundamental vs technical ------
    strat_rows = []
    for label, key in [("fundamental", "misalignment"), ("technical(control)", "ma_dev")]:
        segs = [(fv[c][key].to_numpy(), fv[c]["fwd_1m"].to_numpy()) for c in CCYS]
        sr, lo, hi, hit = overlay_sharpe(segs)
        strat_rows.append({"overlay": f"fade_{label}", "scope": "POOLED",
                           "sharpe_ann": sr, "ci5": lo, "ci95": hi, "hit": hit})
        for c in CCYS:
            sr, lo, hi, hit = overlay_sharpe([(fv[c][key].to_numpy(), fv[c]["fwd_1m"].to_numpy())])
            strat_rows.append({"overlay": f"fade_{label}", "scope": NAME[c],
                               "sharpe_ann": sr, "ci5": lo, "ci95": hi, "hit": hit})
    strat = pd.DataFrame(strat_rows)
    strat.to_csv(f"{RESULTS}/fairvalue_panel_overlay.csv", index=False)

    # ---- 3. sample spans ---------------------------------------------------
    spans = {NAME[c]: (fv[c]["misalignment"].dropna().index.min().date(),
                       fv[c]["misalignment"].dropna().index.max().date(),
                       int(fv[c]["misalignment"].notna().sum())) for c in CCYS}

    # ---- charts ------------------------------------------------------------
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    for ax, c in zip(axes, CCYS):
        d = fv[c]
        ax.plot(d.index, np.exp(d["logfx"]), color="black", lw=1, label="actual")
        ax.plot(d.index, np.exp(d["fair"]), color="#C62828", lw=1.2, ls="--", label="fair value")
        ax.set_title(f"{NAME[c]}: actual vs causal fair value (rate diff + terms of trade)")
        ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout(); fig.savefig(f"{FIGDIR}/fairvalue_actual_vs_fair.png", dpi=110); plt.close(fig)

    # IC bar chart (pooled + per ccy at 6m)
    fig, ax = plt.subplots(figsize=(9, 5))
    sub = ic_tbl[(ic_tbl.signal == "fundamental_misalign")]
    piv = sub.pivot(index="scope", columns="horizon_m", values="rank_ic")
    piv = piv.reindex([NAME["au"], NAME["nz"], NAME["ca"], "POOLED"])
    piv.plot(kind="bar", ax=ax, colormap="viridis")
    ax.axhline(0, color="k", lw=.6)
    ax.set_title("Fair-value misalignment → forward-return rank-IC (negative = mean-reversion)")
    ax.set_ylabel("rank IC"); ax.set_xlabel(""); ax.legend(title="horizon (m)", fontsize=8)
    ax.tick_params(axis="x", rotation=0)
    fig.tight_layout(); fig.savefig(f"{FIGDIR}/fairvalue_ic_by_currency.png", dpi=110); plt.close(fig)

    # ---- print -------------------------------------------------------------
    print("sample spans (misalignment available):")
    for k, v in spans.items():
        print(f"   {k}: {v[0]} -> {v[1]}  n={v[2]}")
    print("\n=== fair-value misalignment -> forward-return rank-IC ===")
    show = ic_tbl.copy()
    show[["rank_ic","ci5","ci95","boot_p"]] = show[["rank_ic","ci5","ci95","boot_p"]].round(3)
    print(show.to_string(index=False))
    print("\n=== fade-richness monthly overlay (Sharpe, block-bootstrap CI) ===")
    print(strat.round(3).to_string(index=False))
    print("\nDONE. figures in", FIGDIR)


if __name__ == "__main__":
    main()
