"""Item 22 -- reframe conviction as a SUPERVISED prediction problem.

Instead of hand-picking gates, label each historical fade with "did it revert
profitably over the 240-min hold" and let a model weight the decision-time axes
jointly. Trade only the top-conviction predicted bucket and ask the deployment
question: does the model's top decile beat simply deepening z at the same trade
rate (the |z_twap| depth frontier)?

Leakage controls (this is the whole point of the item):
  - Features are DECISION-TIME only (the same conditioner axes as item 21).
  - PURGED + EMBARGOED time cross-validation. Trades are pooled across pairs and
    sorted by entry time into K contiguous folds. When a fold is the TEST set,
    every training trade whose entry falls within EMBARGO minutes of the test
    block's time span is dropped, so no training label's 240-min outcome window
    can overlap the test period. Predictions are out-of-fold only.
  - Standardiser + median-imputer are fit on the TRAINING fold only.

Two models (item 22's suggestion): a clustered/standardised LOGISTIC regression
and a gradient-boosted tree ensemble (HistGradientBoosting). Two feature sets:
DEPTH-ONLY (|z_twap| alone -- the benchmark the joint model must beat) and
ALL-AXES. The out-of-fold predicted probability is the conviction score; it is
ranked within pair, the top {10,20,40}% kept, and scored as excess mean R over
each pair's depth frontier at the matched rate (median across pairs), delay 0/1,
raw and news-blackout books.

Screen on consumed history (rule 26); 2024+ sealed.

Reproduce:  python -u _run_rsi_supervised.py   (needs rsi_conviction_trades.parquet)
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from _run_rsi_broad_regime_sweep import PAIRS, ROOT
from _run_rsi_conviction_score import (
    ALL_AXES, KEEPS, eval_selection, frontier_interp, signals_per_year, topq_mask,
)

TRADES = ROOT / "rsi_conviction_trades.parquet"
FRONTIER = ROOT / "rsi_conviction_frontier.json"
OUT = ROOT / "rsi_supervised_results.json"

FEATURES = ["absz_twap", "rv30_pct", "rv5_pct", "vei_atr_z", "abs_sigma_pips",
            "xdiv", "zvel5", "thrust5", "decel5", "prox_hi", "vix_z"]
DEPTH_ONLY = ["absz_twap"]
N_FOLDS = 6
EMBARGO_MIN = 240 + 1440           # hold horizon + one day buffer


def purged_folds(times, k=N_FOLDS, embargo_min=EMBARGO_MIN):
    """Yield (train_idx, test_idx) for k contiguous time folds with purge+embargo.

    `times` is an int64 ns array. A training row is dropped if its entry time is
    within `embargo` of the contiguous test block's [t0, t1] span, so no training
    outcome window (240 min) can overlap the test period.
    """
    order = np.argsort(times, kind="stable")
    emb = np.int64(embargo_min) * np.int64(60_000_000_000)
    bounds = np.linspace(0, len(order), k + 1).astype(int)
    for j in range(k):
        test = order[bounds[j]:bounds[j + 1]]
        t0, t1 = times[test].min(), times[test].max()
        far = (times < t0 - emb) | (times > t1 + emb)
        train = np.flatnonzero(far)
        yield train, test


def oof_predictions(df, feats, model_kind, y):
    """Out-of-fold predicted P(reverts profitably), purged+embargoed CV."""
    X = df[feats].to_numpy(dtype=float)
    times = df["time"].to_numpy().astype("datetime64[ns]").astype("int64")
    oof = np.full(len(df), np.nan)
    coefs = []
    for train, test in purged_folds(times):
        imp = SimpleImputer(strategy="median").fit(X[train])
        Xtr, Xte = imp.transform(X[train]), imp.transform(X[test])
        ytr = y[train]
        if ytr.sum() < 20 or (~ytr).sum() < 20:
            continue
        if model_kind == "logit":
            sc = StandardScaler().fit(Xtr)
            m = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced")
            m.fit(sc.transform(Xtr), ytr)
            oof[test] = m.predict_proba(sc.transform(Xte))[:, 1]
            if len(feats) > 1:
                coefs.append(m.coef_[0])
        else:
            m = HistGradientBoostingClassifier(
                max_depth=3, max_iter=200, learning_rate=0.05,
                min_samples_leaf=200, l2_regularization=1.0, random_state=0)
            m.fit(Xtr, ytr)
            oof[test] = m.predict_proba(Xte)[:, 1]
    return oof, (np.mean(coefs, axis=0) if coefs else None)


def main():
    df = pd.read_parquet(TRADES).reset_index(drop=True)
    df["pair"] = df["pair"].astype(str)
    frontier = json.loads(FRONTIER.read_text())
    y = (df["R_d0"] > 0).to_numpy()

    print(f"Loaded {len(df):,} trades | base reversion rate P(R_d0>0) = {y.mean():.3f}")
    print(f"CV: {N_FOLDS} purged+embargoed contiguous time folds, "
          f"embargo {EMBARGO_MIN} min")

    deployable = (df.news_nearest_min >= 30) & (~df.news_holdspan)
    results = {"base_reversion_rate": float(y.mean()), "sets": {}, "coefs": {}}

    for model_kind in ("logit", "hgbt"):
        for set_name, feats in [("all_axes", FEATURES), ("depth_only", DEPTH_ONLY)]:
            oof, coef = oof_predictions(df, feats, model_kind, y)
            score = pd.Series(oof, index=df.index)
            cov = np.isfinite(oof).mean()
            # AUC-ish: rank correlation of score with the label (OOF)
            m = np.isfinite(oof)
            auc = float(((pd.Series(oof[m]).rank().to_numpy()[y[m]].mean()
                          - (y[m].sum() + 1) / 2) / (~y[m]).sum())) if m.sum() else np.nan
            tag = f"{model_kind}|{set_name}"
            print(f"\n########## {tag}  (feats={len(feats)}, OOF cov {cov:.2f}, "
                  f"AUC {auc:.3f}) ##########")
            if coef is not None:
                order = np.argsort(-np.abs(coef))
                print("   top logit coefs: " +
                      ", ".join(f"{feats[i]} {coef[i]:+.2f}" for i in order[:6]))
                results["coefs"][tag] = {feats[i]: float(coef[i]) for i in range(len(feats))}
            set_res = {"oof_cov": float(cov), "auc": auc}
            for book_name, book in [("raw", pd.Series(True, index=df.index)),
                                    ("blackout", deployable)]:
                for keep in KEEPS:
                    mask = topq_mask(df, score, keep) & book & score.notna()
                    for delay in (0, 1):
                        r = eval_selection(df, mask, f"R_d{delay}", frontier, keep=keep)
                        if r is None:
                            continue
                        key = f"{book_name}|keep{int(keep*100)}|d{delay}"
                        set_res[key] = r
                        if book_name == "raw":
                            print(f"   {key:22s} n/yr {r['signals_per_year']:6.0f}  "
                                  f"meanR {r['mean_R']:+.4f}  vs_depth_topq "
                                  f"{r.get('depth_topq_excess_R', float('nan')):+.4f} "
                                  f"({r.get('pairs_beat_depth_topq', 0)}/4)  "
                                  f"vs_frontier {r['excess_R']:+.4f}")
            results["sets"][tag] = set_res

    print("\n=== VERDICT: top-decile OOF conviction vs depth-top-q (raw book) ===")
    verdict = {}
    for tag, s in results["sets"].items():
        d0 = s.get("raw|keep10|d0", {})
        d1 = s.get("raw|keep10|d1", {})
        dexc0 = d0.get("depth_topq_excess_R", np.nan)
        dexc1 = d1.get("depth_topq_excess_R", np.nan)
        npos = d0.get("pairs_beat_depth_topq", 0)
        ok = (dexc0 >= 0.005) and (npos >= 3) and (dexc1 > 0)
        status = "SUPPORTED" if ok else "NO-GO (does not beat depth)"
        verdict[tag] = {"vs_depth_topq_d0": dexc0, "vs_depth_topq_d1": dexc1,
                        "pairs_beat_depth": npos, "auc": s.get("auc"), "status": status}
        print(f"   {tag:20s} vs_depth_topq d0 {dexc0:+.4f}  d1 {dexc1:+.4f}  {npos}/4  "
              f"AUC {s.get('auc', float('nan')):.3f}  -> {status}")

    results["verdict"] = verdict
    OUT.write_text(json.dumps({
        "metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                     "item": "22 (supervised conviction, purged+embargoed CV)",
                     "features": FEATURES, "n_folds": N_FOLDS,
                     "embargo_min": EMBARGO_MIN, "label": "R_d0 > 0",
                     "primary_metric": "top-bucket OOF excess mean R over depth frontier"},
        **results}, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
