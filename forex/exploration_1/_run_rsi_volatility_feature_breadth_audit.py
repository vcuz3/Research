"""Broader volatility-feature and target audit for the RSI programme.

Run from forex/exploration_1:
    python -u _run_rsi_volatility_feature_breadth_audit.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.linear_model import LogisticRegression

from _run_rsi_broad_regime_sweep import (
    DATA,
    HOLDOUT,
    PAIRS,
    ROOT,
    bh_adjust,
    build_pair,
    causal_slot_percentile,
    session_cluster_t,
)

OUT = ROOT / "rsi_volatility_feature_breadth_audit_results.json"
UNIVARIATE_CSV = ROOT / "rsi_volatility_feature_breadth_audit_univariate.csv"
MODELS_CSV = ROOT / "rsi_volatility_feature_breadth_audit_models.csv"
COVERAGE_CSV = ROOT / "rsi_volatility_feature_breadth_audit_coverage.csv"

BOOTSTRAP_DRAWS = 500
RNG_SEED = 20260804
CS = [0.01, 0.1, 1.0, 10.0]
UNIVARIATE_TARGETS = ["survived", "loss", "tail_loss", "tail_loss_scaled"]
MODEL_TARGETS = ["survived", "tail_loss", "tail_loss_scaled"]


def exact_roll(series, time, window, how):
    rolled = getattr(series.rolling(window, min_periods=window), how)()
    return rolled.where(time.shift(window).eq(time - pd.Timedelta(minutes=window)))


def auc(labels, scores):
    labels = np.asarray(labels, bool)
    scores = np.asarray(scores, float)
    ok = np.isfinite(scores)
    labels, scores = labels[ok], scores[ok]
    n_pos, n_neg = labels.sum(), (~labels).sum()
    if n_pos == 0 or n_neg == 0:
        return np.nan
    ranks = rankdata(scores)
    return (ranks[labels].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def bootstrap_auc(labels, scores, sessions, draws=BOOTSTRAP_DRAWS, seed=RNG_SEED):
    frame = pd.DataFrame({"y": labels, "s": scores, "g": sessions}).dropna()
    groups = {k: np.asarray(v) for k, v in frame.groupby("g").indices.items()}
    keys = np.asarray(list(groups))
    rng = np.random.default_rng(seed)
    vals = np.full(draws, np.nan)
    for i in range(draws):
        picked = rng.choice(len(keys), len(keys), replace=True)
        idx = np.concatenate([groups[keys[j]] for j in picked])
        sub = frame.iloc[idx]
        vals[i] = auc(sub.y, sub.s)
    lo, hi = np.nanpercentile(vals, [2.5, 97.5])
    above = np.nanmean(vals > 0.5)
    p = max(2 * min(above, 1 - above), 1.0 / draws)
    return float(lo), float(hi), float(p)


def raw_features(pair):
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "close"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    one = raw.time.diff().eq(pd.Timedelta(minutes=1))
    r = np.log(raw.close.astype(float)).diff().where(one)
    r2, r4 = r.pow(2), r.pow(4)

    out = pd.DataFrame({"ts_utc": raw.time})
    rv = {}
    for w in [5, 15, 30, 60, 120]:
        rv[w] = np.sqrt(exact_roll(r2, raw.time, w, "sum"))
        out[f"rv_{w}"] = rv[w]

    out["rv_ratio_5_30_broad"] = rv[5] / rv[30]
    out["rv_ratio_15_60_broad"] = rv[15] / rv[60]
    out["rv_ratio_30_120_broad"] = rv[30] / rv[120]

    log_rv5 = np.log(rv[5].where(rv[5] > 0))
    log_rv5_change = log_rv5.diff().where(one)
    for w in [60, 120]:
        mean_rv5 = exact_roll(rv[5], raw.time, w, "mean")
        out[f"vov_cv_{w}"] = exact_roll(rv[5], raw.time, w, "std") / mean_rv5
        out[f"vov_innov_{w}"] = exact_roll(log_rv5_change, raw.time, w, "std")

    for w in [30, 60, 120, 240]:
        out[f"kurtosis_{w}_broad"] = exact_roll(r, raw.time, w, "kurt")

    abs_r = r.abs()
    bipower_term = abs_r * abs_r.shift(1)
    for w in [30, 60, 120]:
        sum2 = exact_roll(r2, raw.time, w, "sum")
        mean2 = exact_roll(r2, raw.time, w, "mean")
        mean4 = exact_roll(r4, raw.time, w, "mean")
        out[f"max_sq_share_{w}"] = exact_roll(r2, raw.time, w, "max") / sum2
        out[f"quarticity_ratio_{w}"] = mean4 / mean2.pow(2)
        bpv = (np.pi / 2.0) * exact_roll(bipower_term, raw.time, w, "sum")
        out[f"jump_share_{w}"] = ((sum2 - bpv) / sum2).clip(lower=0)
        down2 = r2.where(r < 0, 0.0)
        out[f"downside_share_{w}"] = exact_roll(down2, raw.time, w, "sum") / sum2

    return out


def add_labels(panel):
    panel = panel.sort_values("ts_utc").reset_index(drop=True)
    next_rsi = panel.rsi_14.shift(-1)
    next_ok = panel.ts_utc.shift(-1).eq(panel.ts_utc + pd.Timedelta(minutes=30))
    low, high = panel.rsi_14.le(30), panel.rsi_14.ge(70)
    panel["is_extreme"] = low | high
    panel["side"] = np.where(low, 1.0, np.where(high, -1.0, np.nan))
    panel["rsi_depth"] = np.where(low, 30 - panel.rsi_14, np.where(high, panel.rsi_14 - 70, np.nan))
    panel["gross_pips"] = panel.side * panel.terminal_return_pips
    panel["survived"] = pd.Series(
        np.where(low, next_rsi.le(30), np.where(high, next_rsi.ge(70), np.nan)),
        index=panel.index,
        dtype=float,
    ).where(next_ok)
    panel["loss"] = panel.gross_pips.lt(0).astype(float)
    early_signal = panel.is_extreme & panel.era.eq("early_exploration") & panel.gross_pips.notna()
    tail_cut = float(panel.loc[early_signal, "gross_pips"].quantile(0.10))
    panel["tail_loss"] = panel.gross_pips.le(tail_cut).astype(float)
    panel["gross_rv_units"] = panel.gross_pips / (panel.rv_30 * 10_000.0)
    tail_scaled_cut = float(panel.loc[early_signal, "gross_rv_units"].quantile(0.10))
    panel["tail_loss_scaled"] = panel.gross_rv_units.le(tail_scaled_cut).astype(float)
    return panel, tail_cut, tail_scaled_cut


def fit_score(train, test, features, target, c):
    train = train[features + [target]].dropna()
    test = test[features + [target]].dropna()
    model = LogisticRegression(C=c, penalty="l2", solver="lbfgs", max_iter=2000)
    model.fit(train[features], train[target].astype(int))
    return model, test.index, model.predict_proba(test[features])[:, 1]


def choose_c(signals, features, target):
    train = signals.year.le(2018)
    valid = signals.year.between(2019, 2020)
    best = None
    for c in CS:
        _, idx, score = fit_score(signals.loc[train], signals.loc[valid], features, target, c)
        value = auc(signals.loc[idx, target], score)
        if best is None or value > best[0]:
            best = (value, c)
    return best[1], best[0]


def analyse(pair):
    panel, _, _ = build_pair(pair)
    engineered = raw_features(pair)
    panel = panel.merge(engineered, on="ts_utc", how="left", validate="one_to_one")
    panel, tail_cut, tail_scaled_cut = add_labels(panel)
    raw_names = [c for c in engineered.columns if c != "ts_utc"]
    pct_names = []
    for name in raw_names:
        pct = f"{name}_pct90"
        panel[pct] = causal_slot_percentile(panel, name, 90)
        pct_names.append(pct)

    panel["rv_30m_baseline_pct"] = panel.rv_30m_pct_90d
    signals = panel.loc[
        panel.is_extreme & panel.survived.notna() & panel.gross_pips.notna()
    ].copy()
    late = signals.era.eq("late_exploration")

    coverage = []
    for feature in pct_names:
        coverage.append({
            "pair": pair,
            "feature": feature,
            "all_signal_coverage": float(signals[feature].notna().mean()),
            "late_signal_coverage": float(signals.loc[late, feature].notna().mean()),
        })

    univariate = []
    for target in UNIVARIATE_TARGETS:
        for feature in pct_names:
            z = signals.loc[late, [target, feature, "sdate"]].dropna()
            a = auc(z[target], z[feature])
            lo, hi, p = bootstrap_auc(z[target], z[feature], z.sdate)
            univariate.append({
                "pair": pair, "target": target, "feature": feature,
                "n_test": int(len(z)), "test_auc": a, "auc_lo": lo,
                "auc_hi": hi, "boot_p": p,
            })

    baseline = ["rsi_depth", "rv_30m_baseline_pct"]
    expanded = baseline + pct_names
    models = []
    for target in MODEL_TARGETS:
        row = {"pair": pair, "target": target, "tail_cut_pips": tail_cut,
               "tail_scaled_cut_rv": tail_scaled_cut}
        scores = {}
        for label, features in [("baseline", baseline), ("expanded", expanded)]:
            c, val_auc = choose_c(signals, features, target)
            early = signals.era.eq("early_exploration")
            _, idx, score = fit_score(signals.loc[early], signals.loc[late], features, target, c)
            frame = signals.loc[idx]
            test_auc = auc(frame[target], score)
            row |= {f"{label}_c": c, f"{label}_validation_auc": val_auc,
                    f"{label}_test_auc": test_auc, f"{label}_n_test": int(len(frame))}
            scores[label] = pd.Series(score, index=idx)
        common = scores["baseline"].index.intersection(scores["expanded"].index)
        base_auc = auc(signals.loc[common, target], scores["baseline"].loc[common])
        exp_auc = auc(signals.loc[common, target], scores["expanded"].loc[common])
        row["common_n"] = int(len(common))
        row["baseline_common_auc"] = base_auc
        row["expanded_common_auc"] = exp_auc
        row["auc_delta"] = exp_auc - base_auc
        risk = scores["expanded"].loc[common]
        keep = risk <= risk.median()
        kept = signals.loc[common[keep]]
        allz = signals.loc[common]
        row["all_gross_pips"] = float(allz.gross_pips.mean())
        row["kept_gross_pips"] = float(kept.gross_pips.mean())
        row["filter_gain_pips"] = row["kept_gross_pips"] - row["all_gross_pips"]
        row["all_cluster_t"] = session_cluster_t(allz.gross_pips, allz.sdate)
        row["kept_cluster_t"] = session_cluster_t(kept.gross_pips, kept.sdate)
        models.append(row)
    return univariate, models, coverage


def main():
    all_u, all_m, all_c = [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        u, m, c = analyse(pair)
        all_u.extend(u); all_m.extend(m); all_c.extend(c)

    univ = pd.DataFrame(all_u)
    univ["boot_q"] = bh_adjust(univ.boot_p)
    models = pd.DataFrame(all_m)
    coverage = pd.DataFrame(all_c)

    stability = (
        univ.assign(above=lambda x: x.test_auc > 0.5,
                    abs_dev=lambda x: (x.test_auc - 0.5).abs())
        .groupby(["target", "feature"])
        .agg(pairs=("pair", "size"), pairs_above=("above", "sum"),
             median_auc=("test_auc", "median"), median_abs_dev=("abs_dev", "median"),
             min_q=("boot_q", "min"))
        .reset_index()
    )
    stability["direction_agrees_3of4"] = stability.pairs_above.isin([0, 1, 3, 4])
    stable = stability.loc[
        stability.direction_agrees_3of4 & (stability.min_q < 0.10) &
        (stability.median_abs_dev >= 0.03)
    ]

    model_gate = []
    for target, z in models.groupby("target"):
        model_gate.append({"target": target,
                           "pairs_delta_ge_015": int((z.auc_delta >= 0.015).sum()),
                           "median_auc_delta": float(z.auc_delta.median())})
    model_gate = pd.DataFrame(model_gate)
    frozen_targets = ["survived", "tail_loss"]
    passes_model = bool(((model_gate.target.isin(frozen_targets)) &
                         (model_gate.pairs_delta_ge_015 >= 3) &
                         (model_gate.median_auc_delta >= 0.015)).any())
    passes_univariate = bool(stable.target.isin(frozen_targets).any())
    if passes_model:
        verdict = "INCREMENTAL MODEL GATE PASSED"
    elif passes_univariate and stable.loc[stable.target.isin(frozen_targets), "feature"].str.match(r"^rv_\d+_pct90$").all():
        verdict = "FORMAL UNIVARIATE GATE PASS — KNOWN RV LEVEL ONLY; NO INCREMENTAL ENGINEERED FEATURE"
    elif passes_univariate:
        verdict = "UNIVARIATE GATE PASSED; INCREMENTAL MODEL GATE FAILED"
    else:
        verdict = "NO-GO FOR THIS SCREEN"

    univ.to_csv(UNIVARIATE_CSV, index=False)
    models.to_csv(MODELS_CSV, index=False)
    coverage.to_csv(COVERAGE_CSV, index=False)
    payload = {
        "metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                     "pairs": PAIRS, "bootstrap_draws": BOOTSTRAP_DRAWS,
                     "seed": RNG_SEED, "holdout_start": HOLDOUT.isoformat(),
                     "feature_count": int(univ.feature.nunique())},
        "model_results": json.loads(models.to_json(orient="records")),
        "model_gate": json.loads(model_gate.to_json(orient="records")),
        "stable_univariate": json.loads(stable.to_json(orient="records")),
        "coverage_summary": {"min_all": float(coverage.all_signal_coverage.min()),
                             "min_late": float(coverage.late_signal_coverage.min())},
        "verdict": verdict,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\nExpanded-model comparison")
    print(models.round(4).to_string(index=False))
    print("\nStable univariate candidates meeting frozen gate")
    print(stable.round(4).to_string(index=False) if len(stable) else "  none")
    print("\nModel gate")
    print(model_gate.round(4).to_string(index=False))
    print(f"\nVERDICT: {verdict}")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
