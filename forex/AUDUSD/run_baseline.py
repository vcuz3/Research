"""
run_baseline.py — drive the AUDUSD Step-2 baseline end to end.

Runs leakage-safe walk-forward Ridge (returns) and Logistic (direction) across
three horizons (1h / 4h / 1d), three feature sets (technical / conditioning /
combined), evaluates with overlap-aware metrics, compares to a naive-momentum
benchmark, and writes result tables to results/.

Usage:  python run_baseline.py
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

import baseline_features as bf
import walkforward as wf
import metrics as mt

RESULTS = "results"
CACHE = "data/_baseline_panel_cache.parquet"
HORIZONS = bf.HORIZONS_BARS                     # {"h1h":4,"h4h":16,"h1d":96}
ONE_WAY_COST = bf.DEFAULT_ONE_WAY_COST          # 0.5 pip
COST_SWEEP = [0.0, 0.00002, 0.00005, 0.0001]    # 0, 0.2, 0.5, 1.0 pip one-way
TRADE_THRESHOLD = {"h1h": 0.0003, "h4h": 0.0006, "h1d": 0.0015}  # ~ prediction scale


def get_panel(rebuild: bool = False) -> pd.DataFrame:
    if os.path.exists(CACHE) and not rebuild:
        return pd.read_parquet(CACHE)
    df = bf.build_all(cost_buffer=ONE_WAY_COST)
    # binary direction target per horizon for classification
    for tag in HORIZONS:
        df[f"y_bin_{tag}"] = (df[f"y_ret_{tag}"] > 0).astype("float32")
    df.to_parquet(CACHE)
    return df


def feature_sets(df: pd.DataFrame) -> dict[str, list[str]]:
    tech = [c for c in bf.INTRADAY_FEATURES if c in df.columns]
    cond = bf.conditioning_features(df)
    return {"technical": tech, "conditioning": cond, "combined": tech + cond}


def main(rebuild: bool = False) -> None:
    os.makedirs(RESULTS, exist_ok=True)
    df = get_panel(rebuild=rebuild)
    fsets = feature_sets(df)
    print(f"panel {df.shape}  | feature sets: "
          f"{ {k: len(v) for k, v in fsets.items()} }")

    reg_rows, clf_rows, trade_rows, bench_rows = [], [], [], []
    bucket_tables, calib_tables, coef_tables = {}, {}, {}

    for tag, h in HORIZONS.items():
        print(f"\n=== horizon {tag} ({h} bars) ===")

        # ---- regression across feature sets ---------------------------------
        combined_res = None
        for fs_name, cols in fsets.items():
            res = wf.walk_forward_predict(
                df, cols, f"y_ret_{tag}", horizon_bars=h,
                task="reg", model="ridge", alpha=10.0,
            )
            m = mt.regression_metrics(res, h)
            m.update(horizon=tag, feature_set=fs_name, model="ridge")
            reg_rows.append(m)
            print(f"  reg[{fs_name:12s}] rank_IC(non)={m['rank_ic_nonovlp']:+.4f} "
                  f"t={m['ic_tstat_nonovlp']:+.2f} dir_acc={m['dir_acc_all']:.4f}")
            if fs_name == "combined":
                combined_res = res

        # confidence buckets + coefficients for the combined regression
        bucket_tables[tag] = mt.confidence_buckets(combined_res)
        coef_tables[tag] = wf.fit_full_coefficients(
            df, fsets["combined"], f"y_ret_{tag}", task="reg", model="ridge")

        # ---- trading rule + cost sweep on the combined regression -----------
        for c in COST_SWEEP:
            tm = mt.trading_metrics(combined_res, h,
                                    threshold=TRADE_THRESHOLD[tag], one_way_cost=c)
            tm.update(horizon=tag, one_way_cost=c, sizing="threshold_reg")
            trade_rows.append(tm)
        base_tm = mt.trading_metrics(combined_res, h,
                                     threshold=TRADE_THRESHOLD[tag],
                                     one_way_cost=ONE_WAY_COST)
        print(f"  trade@{ONE_WAY_COST*1e4:.1f}pip: sharpe_net={base_tm['sharpe_net']:+.2f} "
              f"pf={base_tm['profit_factor']:.2f} trades={base_tm['n_trades']} "
              f"cost_drag={base_tm['cost_drag_frac']:.2f}")

        # ---- momentum benchmark (same OOS rows) -----------------------------
        bench = mt.momentum_benchmark(df, combined_res, h, mom_col="ret_12b")
        bm = mt.regression_metrics(bench, h)
        btm = mt.trading_metrics(bench, h, threshold=0.0,
                                 one_way_cost=ONE_WAY_COST)
        bench_rows.append(dict(horizon=tag, rank_ic_nonovlp=bm["rank_ic_nonovlp"],
                               ic_tstat_nonovlp=bm["ic_tstat_nonovlp"],
                               dir_acc=bm["dir_acc_all"],
                               sharpe_net=btm["sharpe_net"],
                               profit_factor=btm["profit_factor"]))
        print(f"  benchmark(mom): rank_IC(non)={bm['rank_ic_nonovlp']:+.4f} "
              f"dir_acc={bm['dir_acc_all']:.4f} sharpe_net={btm['sharpe_net']:+.2f}")

        # ---- logistic direction classification (combined) -------------------
        cres = wf.walk_forward_predict(
            df, fsets["combined"], f"y_bin_{tag}", horizon_bars=h,
            task="clf", model="logit", C=1.0,
        )
        cm = mt.classification_metrics(cres)
        cm.update(horizon=tag)
        clf_rows.append(cm)
        calib_tables[tag] = mt.calibration_table(cres)
        print(f"  clf: acc={cm['accuracy']:.4f} auc={cm['roc_auc']:.4f} "
              f"base={cm['base_rate']:.4f} f1={cm['f1']:.4f}")

    # -------------------------------------------------------- write tables ---
    pd.DataFrame(reg_rows).to_csv(f"{RESULTS}/regression_metrics.csv", index=False)
    pd.DataFrame(clf_rows).to_csv(f"{RESULTS}/classification_metrics.csv", index=False)
    pd.DataFrame(trade_rows).to_csv(f"{RESULTS}/trading_metrics.csv", index=False)
    pd.DataFrame(bench_rows).to_csv(f"{RESULTS}/benchmark_metrics.csv", index=False)
    for tag in HORIZONS:
        bucket_tables[tag].to_csv(f"{RESULTS}/conf_buckets_{tag}.csv")
        calib_tables[tag].to_csv(f"{RESULTS}/calibration_{tag}.csv")
        coef_tables[tag].to_frame("coef").to_csv(f"{RESULTS}/coefficients_{tag}.csv")
    print(f"\nwrote tables to {RESULTS}/")


if __name__ == "__main__":
    import sys
    main(rebuild="--rebuild" in sys.argv)
