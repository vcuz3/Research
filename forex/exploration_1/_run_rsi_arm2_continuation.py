"""Arm 2 of RSI_MEAN_REVERSION_PROGRAMME_SPEC.md — continuation versus snap-back.

The project's dominant loss mechanism is extremes that persist instead of
reverting. Splitting on realised survival is not a filter, because survival is not
known at the decision. This arm asks whether anything OBSERVABLE AT DECISION TIME
predicts survival, using an out-of-sample era split and session-clustered
inference.

Reproduce with:
    python -u _run_rsi_arm2_continuation.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import rankdata

from _run_rsi_broad_regime_sweep import (
    DATA,
    HOLDOUT,
    PAIRS,
    ROOT,
    build_pair,
    causal_slot_percentile,
    session_cluster_t,
)

OUT = ROOT / "rsi_arm2_continuation_results.json"
UNIVARIATE_CSV = ROOT / "rsi_arm2_continuation_univariate.csv"
SUMMARY_CSV = ROOT / "rsi_arm2_continuation_summary.csv"

BOOTSTRAP_DRAWS = 300
RNG_SEED = 20260804

# Decision-time candidates, all converted to causal same-slot percentiles so that
# no fixed threshold on them can act as a time-of-day selector.
CANDIDATES = [
    "vol_of_vol_60m",
    "kurtosis_30m",
    "kurtosis_60m",
    "efficiency_15m_raw",
    "efficiency_60m_raw",
    "rv_ratio_5_30_raw",
    "rv_30m_raw",
]
# Depth into the extreme zone is only defined on signal rows, so it cannot take a
# same-slot percentile over all rows; it enters raw as a within-signal control.
EXTRA_FEATURES = ["rsi_depth"]


def auc(labels, scores):
    """Rank-based AUC. labels is a boolean array of positives."""
    labels = np.asarray(labels, bool)
    scores = np.asarray(scores, float)
    ok = np.isfinite(scores)
    labels, scores = labels[ok], scores[ok]
    n_pos, n_neg = labels.sum(), (~labels).sum()
    if n_pos == 0 or n_neg == 0:
        return np.nan
    ranks = rankdata(scores)
    return (ranks[labels].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def cluster_bootstrap_auc(labels, scores, sessions, draws=BOOTSTRAP_DRAWS, seed=RNG_SEED):
    """Resample whole sessions so dependence within a session is preserved."""
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({"y": np.asarray(labels), "s": np.asarray(scores), "g": np.asarray(sessions)})
    frame = frame.loc[np.isfinite(frame.s)]
    groups = {k: np.asarray(v) for k, v in frame.groupby("g").indices.items()}
    keys = np.array(list(groups.keys()))
    values = np.array([np.nan] * draws)
    for i in range(draws):
        picked = rng.choice(len(keys), size=len(keys), replace=True)
        idx = np.concatenate([groups[keys[j]] for j in picked])
        sub = frame.iloc[idx]
        values[i] = auc(sub.y.to_numpy(bool), sub.s.to_numpy(float))
    lo, hi = np.nanpercentile(values, [2.5, 97.5])
    above = np.nanmean(values > 0.5)
    p = 2 * min(above, 1 - above)
    return lo, hi, max(p, 1.0 / draws)


def exact_window(series, time, window, how):
    rolled = getattr(series.rolling(window, min_periods=window), how)()
    return rolled.where(time.shift(window).eq(time - pd.Timedelta(minutes=window)))


def decision_time_features(pair, panel):
    """Vol-of-vol and rolling kurtosis, gap-exact, at the decision bar."""
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "close"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    one = raw.time.diff().eq(pd.Timedelta(minutes=1))
    ret1 = pd.Series(np.log(raw.close.astype(float)), index=raw.index).diff().where(one)

    rv5 = np.sqrt(exact_window(ret1.pow(2), raw.time, 5, "sum"))
    out = pd.DataFrame(
        {
            "ts_utc": raw.time,
            # how unstable volatility itself has been (second moment of the vol process),
            # which is distinct from a ratio of two volatility windows
            "vol_of_vol_60m": exact_window(rv5, raw.time, 60, "std"),
            "kurtosis_30m": exact_window(ret1, raw.time, 30, "kurt"),
            "kurtosis_60m": exact_window(ret1, raw.time, 60, "kurt"),
        }
    )
    return panel.merge(out, on="ts_utc", how="left")


def build_labels(panel):
    """Did the RSI extreme persist to the next scheduled checkpoint 30 minutes on?"""
    panel = panel.sort_values("ts_utc").reset_index(drop=True)
    next_rsi = panel.rsi_14.shift(-1)
    next_ok = panel.ts_utc.shift(-1).eq(panel.ts_utc + pd.Timedelta(minutes=30))
    low, high = panel.rsi_14.le(30), panel.rsi_14.ge(70)
    survived = np.where(
        low, next_rsi.le(30), np.where(high, next_rsi.ge(70), np.nan)
    ).astype(float)
    panel["survived"] = pd.Series(survived, index=panel.index).where(next_ok)
    panel["is_extreme"] = low | high
    panel["side"] = np.where(low, 1.0, np.where(high, -1.0, np.nan))
    panel["rsi_depth"] = np.where(low, 30 - panel.rsi_14, np.where(high, panel.rsi_14 - 70, np.nan))
    panel["gross_pips"] = panel.side * panel.terminal_return_pips
    return panel


def analyse(pair):
    panel, _, _ = build_pair(pair)
    panel = decision_time_features(pair, panel)
    panel = build_labels(panel)

    for column in CANDIDATES:
        panel[f"{column}_pct"] = causal_slot_percentile(panel, column, 90)

    signals = panel.loc[
        panel.is_extreme & panel.survived.notna() & panel.gross_pips.notna()
    ].copy()
    early = signals.era.eq("early_exploration")
    late = ~early

    # Confirm the known, non-actionable survival split before testing predictability.
    split = {}
    for label, mask in [("survivors", signals.survived.eq(1)), ("reverters", signals.survived.eq(0))]:
        z = signals.loc[mask]
        split[label] = {
            "n": int(len(z)),
            "gross_pips": z.gross_pips.mean(),
            "cluster_t": session_cluster_t(z.gross_pips, z.sdate),
        }
    split["survival_rate"] = float(signals.survived.mean())

    features = [f"{c}_pct" for c in CANDIDATES] + EXTRA_FEATURES
    univariate = []
    for feature in features:
        z = signals.loc[late, [feature, "survived", "sdate"]].dropna()
        if len(z) < 500:
            univariate.append({"pair": pair, "feature": feature, "test_auc": np.nan})
            continue
        a = auc(z.survived.to_numpy(bool), z[feature].to_numpy(float))
        lo, hi, p = cluster_bootstrap_auc(
            z.survived.to_numpy(bool), z[feature].to_numpy(float), z.sdate.to_numpy()
        )
        univariate.append(
            {
                "pair": pair,
                "feature": feature,
                "n_test": int(len(z)),
                "test_auc": a,
                "auc_lo": lo,
                "auc_hi": hi,
                "boot_p": p,
                "excludes_half": bool((lo > 0.5) or (hi < 0.5)),
            }
        )

    # Multivariate: fit on the early era only, score the late era.
    fit_frame = signals.loc[early, features + ["survived"]].dropna()
    test_frame = signals.loc[late, features + ["survived", "sdate", "gross_pips", "side"]].dropna()
    multi = {"pair": pair}
    if len(fit_frame) > 1000 and len(test_frame) > 500:
        X = sm.add_constant(fit_frame[features].astype(float))
        model = sm.Logit(fit_frame.survived.astype(float), X).fit(disp=0)
        Xt = sm.add_constant(test_frame[features].astype(float), has_constant="add")
        score = model.predict(Xt)
        a = auc(test_frame.survived.to_numpy(bool), score.to_numpy())
        lo, hi, p = cluster_bootstrap_auc(
            test_frame.survived.to_numpy(bool), score.to_numpy(), test_frame.sdate.to_numpy()
        )
        # Actionable version: drop the half predicted most likely to persist.
        keep = score <= score.median()
        multi |= {
            "n_fit": int(len(fit_frame)),
            "n_test": int(len(test_frame)),
            "test_auc": a,
            "auc_lo": lo,
            "auc_hi": hi,
            "boot_p": p,
            "excludes_half": bool((lo > 0.5) or (hi < 0.5)),
            "all_gross_pips": test_frame.gross_pips.mean(),
            "all_cluster_t": session_cluster_t(test_frame.gross_pips, test_frame.sdate),
            "kept_gross_pips": test_frame.loc[keep, "gross_pips"].mean(),
            "kept_cluster_t": session_cluster_t(
                test_frame.loc[keep, "gross_pips"], test_frame.loc[keep, "sdate"]
            ),
            "dropped_gross_pips": test_frame.loc[~keep, "gross_pips"].mean(),
            "filter_gain_pips": test_frame.loc[keep, "gross_pips"].mean() - test_frame.gross_pips.mean(),
        }
    return univariate, {"pair": pair, **split}, multi


def main():
    univariate_rows, split_rows, multi_rows = [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        u, s, m = analyse(pair)
        univariate_rows.extend(u)
        split_rows.append(s)
        multi_rows.append(m)

    univariate = pd.DataFrame(univariate_rows)
    multi = pd.DataFrame(multi_rows)

    print("\nRealised survival split (NOT actionable — survival is unknown at the decision)")
    for row in split_rows:
        print(
            f"  {row['pair']}  survival rate {row['survival_rate']:.3f}"
            f"   survivors {row['survivors']['gross_pips']:+.3f} pip (t {row['survivors']['cluster_t']:+.2f}, n {row['survivors']['n']})"
            f"   reverters {row['reverters']['gross_pips']:+.3f} pip (t {row['reverters']['cluster_t']:+.2f}, n {row['reverters']['n']})"
        )

    # The univariate scan is 4 pairs x 8 features, so raw CI exclusion overstates
    # evidence. Correct across the whole scan, and require the same feature to point
    # the same way on all four pairs before calling it a separator.
    from _run_rsi_broad_regime_sweep import bh_adjust

    univariate["boot_q"] = np.nan
    ok = univariate.boot_p.notna()
    univariate.loc[ok, "boot_q"] = bh_adjust(univariate.loc[ok, "boot_p"])

    consistency = (
        univariate.dropna(subset=["test_auc"])
        .assign(above=lambda f: f.test_auc > 0.5)
        .groupby("feature")
        .agg(
            pairs=("above", "size"),
            pairs_above_half=("above", "sum"),
            median_auc=("test_auc", "median"),
            min_q=("boot_q", "min"),
        )
        .assign(sign_consistent=lambda f: f.pairs_above_half.isin([0, f.pairs.iloc[0]]))
        .reset_index()
    )

    print("\nUnivariate out-of-sample AUC for predicting survival (late era)")
    print(univariate.round(4).to_string(index=False))

    print("\nCross-pair consistency (a real separator points the same way on all four)")
    print(consistency.round(4).to_string(index=False))

    print("\nMultivariate (fit early era, tested late era)")
    print(multi.round(4).to_string(index=False))

    raw_excludes = bool(univariate.excludes_half.any())
    n_excludes = int(univariate.excludes_half.sum())
    n_tests = int(univariate.test_auc.notna().sum())
    survives_bh = bool((univariate.boot_q < 0.10).any())
    multi_excludes = bool(multi.excludes_half.any()) if "excludes_half" in multi else False
    consistent_and_significant = consistency.loc[
        consistency.sign_consistent & (consistency.min_q < 0.10)
    ]
    max_dev = float((univariate.test_auc - 0.5).abs().max())
    multi_max_dev = float((multi.test_auc - 0.5).abs().max()) if "test_auc" in multi else np.nan

    verdict = (
        "NO-GO — no decision-time separator of continuation from snap-back"
        if not (survives_bh and len(consistent_and_significant))
        else "SIGNAL PRESENT — a sign-consistent separator survives correction"
    )
    print(
        f"\nKILL TEST"
        f"\n  max |univariate AUC - 0.50| = {max_dev:.4f} over {n_tests} tests"
        f"\n  raw CIs excluding 0.50: {n_excludes}/{n_tests} (expected ~{0.05 * n_tests:.1f} by chance)"
        f"\n  any BH q < 0.10: {survives_bh}"
        f"\n  sign-consistent across all four pairs AND q < 0.10: {len(consistent_and_significant)}"
        f"\n  max |multivariate AUC - 0.50| = {multi_max_dev:.4f}, any CI excluding 0.50: {multi_excludes}"
        f"\nVERDICT: {verdict}"
    )

    univariate.to_csv(UNIVARIATE_CSV, index=False)
    multi.to_csv(SUMMARY_CSV, index=False)
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "pairs": PAIRS,
                    "candidates": CANDIDATES,
                    "bootstrap_draws": BOOTSTRAP_DRAWS,
                    "seed": RNG_SEED,
                    "holdout_start": HOLDOUT.isoformat(),
                },
                "realised_survival_split": split_rows,
                "univariate": json.loads(univariate.to_json(orient="records")),
                "consistency": json.loads(consistency.to_json(orient="records")),
                "multivariate": json.loads(multi.to_json(orient="records")),
                "kill_test": {
                    "max_univariate_auc_deviation": max_dev,
                    "max_multivariate_auc_deviation": multi_max_dev,
                    "n_tests": n_tests,
                    "n_raw_ci_excluding_half": n_excludes,
                    "expected_by_chance": 0.05 * n_tests,
                    "any_bh_q_below_10pct": survives_bh,
                    "sign_consistent_and_significant": consistency.loc[
                        consistency.sign_consistent & (consistency.min_q < 0.10), "feature"
                    ].tolist(),
                    "multivariate_ci_excludes_half": multi_excludes,
                    "verdict": verdict,
                },
            },
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
