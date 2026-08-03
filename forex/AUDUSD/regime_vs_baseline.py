"""
regime_vs_baseline.py — does the Step-3 macro regime layer change the Step-2
baseline model's (already weak) predictive value?

Method
------
1. Re-run the leakage-safe walk-forward TECHNICAL Ridge from Step-2 (the only
   feature set that showed any OOS signal) at the 1h and 1d horizons, keeping the
   per-bar out-of-sample predictions.
2. Map the DAILY macro regime onto each 15-min bar with a strict 1-business-day
   lag (the label from the window ending on day D is only attached to bars on
   D+1 onward — identical causality to the panel's daily→intraday join).
3. Split the OOS predictions by regime and recompute the honest, overlap-aware
   metrics (rank IC on non-overlapping samples, directional accuracy, and a
   cost-aware net Sharpe) *within each regime*.

This answers the Step-3 research questions:
  * are some regimes more predictable?
  * are some better for long vs short AUDUSD?
  * does the baseline do better in some regimes / should any be avoided?

Nothing here is a trading recommendation — it tests whether conditioning on the
regime rescues the NO-GO baseline.  Usage:  python regime_vs_baseline.py
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

import baseline_features as bf
import walkforward as wf
import metrics as mt
import macro_regime as mr

RESULTS = "results"
CACHE = "data/_baseline_panel_cache.parquet"
HORIZONS = {"h1h": 4, "h1d": 96}          # bars; the two horizons with any signal
ONE_WAY_COST = bf.DEFAULT_ONE_WAY_COST    # 0.5 pip placeholder (see CLAUDE.md #2)
TRADE_THRESHOLD = {"h1h": 0.0003, "h1d": 0.0015}
BARS_PER_YEAR = mt.BARS_PER_YEAR


def get_panel() -> pd.DataFrame:
    if os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    df = bf.build_all(cost_buffer=ONE_WAY_COST)
    df.to_parquet(CACHE)
    return df


def attach_regime(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach macro_regime + idio_regime to each intraday bar with a 1-business-day
    lag.  reg_daily[d] is known at the close of day d; it becomes usable for bars
    on the next business day.  We shift the daily label by one business day, then
    as-of (backward) join onto each bar's UTC date.
    """
    reg = pd.read_csv("data/audusd_macro_regime_daily.csv",
                      index_col=0, parse_dates=True)
    lab = reg[["macro_regime", "idio_regime", "confidence_score",
               "rolling_r2"]].copy()
    # available from the NEXT business day (no look-ahead)
    lab_avail = lab.shift(1)
    lab_avail = lab_avail.reset_index().rename(columns={"index": "date", lab.index.name or "date": "date"})
    lab_avail.columns = ["date"] + list(lab.columns)
    lab_avail["date"] = pd.to_datetime(lab_avail["date"])

    out = df.copy()
    out["bar_date"] = out["time"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    out = out.sort_values("bar_date")
    merged = pd.merge_asof(
        out, lab_avail.sort_values("date"),
        left_on="bar_date", right_on="date", direction="backward",
    )
    merged.index = df.index                      # restore original bar order index
    return merged.sort_index()


def wf_technical(df: pd.DataFrame, tag: str, h: int) -> pd.DataFrame:
    tech = [c for c in bf.INTRADAY_FEATURES if c in df.columns]
    res = wf.walk_forward_predict(
        df, feature_cols=tech, target_col=f"y_ret_{tag}",
        horizon_bars=h, task="reg", model="ridge", alpha=10.0,
    )
    return res


def per_regime_metrics(res: pd.DataFrame, regime: pd.Series, h: int,
                       tag: str, cost: float, thr: float) -> pd.DataFrame:
    """Overlap-aware IC / dir-acc / net-Sharpe per regime label."""
    f = mt.oos_frame(res).copy()
    f["regime"] = regime.reindex(f.index).values
    rows = []
    for name, g in f.groupby("regime", observed=True):
        if len(g) < 200:
            continue
        # non-overlapping thinning WITHIN the regime rows (every h-th)
        gn = g.iloc[::h]
        pear = np.corrcoef(gn["pred"], gn["y"])[0, 1] if len(gn) > 5 else np.nan
        rank = (pd.Series(gn["pred"]).corr(pd.Series(gn["y"]), method="spearman")
                if len(gn) > 5 else np.nan)
        n = len(gn)
        t = (pear * np.sqrt(max(n - 2, 1)) / np.sqrt(max(1 - pear**2, 1e-12))
             if np.isfinite(pear) else np.nan)
        dir_acc = float((np.sign(gn["pred"]) == np.sign(gn["y"])).mean())
        # cost-aware trading on the non-overlapping regime rows
        sig = gn["pred"].to_numpy(); ret = gn["y"].to_numpy()
        pos = np.where(sig > thr, 1.0, np.where(sig < -thr, -1.0, 0.0))
        pos_prev = np.concatenate([[0.0], pos[:-1]])
        turnover = np.abs(pos - pos_prev)
        gross = pos * ret
        net = gross - cost * turnover
        ppy = BARS_PER_YEAR / h
        def sharpe(x):
            x = x[np.isfinite(x)]
            return (x.mean() / x.std(ddof=1) * np.sqrt(ppy)
                    if len(x) > 3 and x.std(ddof=1) > 0 else np.nan)
        # forward mean by regime (directional bias of the ASSET, not the model)
        rows.append({
            "regime": name, "n_oos": len(g), "n_nonovlp": n,
            "rank_ic": rank, "ic_pearson": pear, "ic_t": t,
            "dir_acc": dir_acc,
            "asset_fwd_mean_bp": float(gn["y"].mean() * 1e4),
            "asset_up_share": float((gn["y"] > 0).mean()),
            "trade_frac": float((pos != 0).mean()),
            "sharpe_gross": sharpe(gross),
            "sharpe_net": sharpe(net),
            "total_net_bp": float(net.sum() * 1e4),
        })
    out = pd.DataFrame(rows).set_index("regime")
    out.attrs["tag"] = tag
    return out.sort_values("n_oos", ascending=False)


def main():
    os.makedirs(RESULTS, exist_ok=True)
    print("loading panel + attaching lagged regime ...")
    df = get_panel()
    df = attach_regime(df)
    print("regime coverage on intraday bars (idio):")
    print(df["idio_regime"].value_counts(normalize=True).round(3).to_string())

    all_tables = {}
    for tag, h in HORIZONS.items():
        print(f"\n=== walk-forward technical Ridge {tag} ({h} bars) ===")
        res = wf_technical(df, tag, h)
        # overall (sanity vs BASELINE_FINDINGS)
        overall = mt.regression_metrics(res, h)
        print(f"overall rank IC (nonovlp) = {overall['rank_ic_nonovlp']:.4f}  "
              f"t = {overall['ic_tstat_nonovlp']:.2f}  n = {overall['n_nonovlp']}")

        for reg_col in ["idio_regime", "macro_regime"]:
            tab = per_regime_metrics(res, df[reg_col], h, tag,
                                     ONE_WAY_COST, TRADE_THRESHOLD[tag])
            path = f"{RESULTS}/baseline_by_{reg_col}_{tag}.csv"
            tab.to_csv(path)
            all_tables[(reg_col, tag)] = tab
            print(f"\n--- {tag} by {reg_col} ---")
            print(tab.round(4).to_string())

    print("\nDONE. tables -> results/baseline_by_*")


if __name__ == "__main__":
    main()
