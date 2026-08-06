"""Arm 0 of RSI_MEAN_REVERSION_PROGRAMME_SPEC.md — the entry-delay gating test.

Delay entry and exit by d minutes while holding the 30-minute holding period
fixed, and measure what happens to the volatility-regime gradient in RSI
reversion. If the gradient is majority first-traded-minute, the family is a
microstructure artifact and the remaining arms are not run.

Reproduce with:
    python -u _run_rsi_arm0_entry_delay.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from _run_rsi_broad_regime_sweep import (
    DATA,
    HOLDOUT,
    HORIZON,
    PAIRS,
    PIP,
    ROOT,
    build_pair,
    exact_lag,
    session_cluster_t,
)

OUT = ROOT / "rsi_arm0_entry_delay_results.json"
QUINTILE_CSV = ROOT / "rsi_arm0_entry_delay_quintiles.csv"
GRADIENT_CSV = ROOT / "rsi_arm0_entry_delay_gradients.csv"

DELAYS = [0, 1, 2, 3, 5]
REGIME = "rv_30m_pct_90d"
GRADIENT_KILL_RATIO = 0.50


def within_slot_ic(frame, feature, target):
    z = frame[["session_minute", feature, target]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(z) < 200:
        return np.nan
    fr = z.groupby("session_minute")[feature].rank(pct=True)
    tr = z.groupby("session_minute")[target].rank(pct=True)
    return spearmanr(fr, tr).statistic


def delayed_targets(pair, panel):
    """Entry at open(t+1+d), exit at open(t+31+d); both legs required exact."""
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "open", "close"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    open_ = raw.open.astype(float)
    logc = pd.Series(np.log(raw.close.astype(float)), index=raw.index)

    out = pd.DataFrame({"ts_utc": raw.time})
    out["past_ret_30m_bp"] = 1e4 * (logc - exact_lag(logc, raw.time, 30))
    out["past_ret_1m_bp"] = 1e4 * (logc - exact_lag(logc, raw.time, 1))

    for d in DELAYS:
        a, b = 1 + d, HORIZON + 1 + d
        entry = open_.shift(-a)
        exit_ = open_.shift(-b)
        exact = raw.time.shift(-a).eq(raw.time + pd.Timedelta(minutes=a)) & raw.time.shift(-b).eq(
            raw.time + pd.Timedelta(minutes=b)
        )
        out[f"ret_bp_d{d}"] = (1e4 * np.log(exit_ / entry)).where(exact)
        out[f"ret_pips_d{d}"] = ((exit_ - entry) / PIP).where(exact)
    return panel.merge(out, on="ts_utc", how="left")


def fade_stats(frame, side, pips_col):
    z = frame.loc[side.ne(0) & frame[pips_col].notna()]
    if z.empty:
        return {"n": 0, "gross_pips": np.nan, "cluster_t": np.nan}
    gross = side.loc[z.index] * z[pips_col]
    return {
        "n": int(len(z)),
        "gross_pips": gross.mean(),
        "cluster_t": session_cluster_t(gross, z.sdate),
    }


def analyse(pair):
    panel, _, _ = build_pair(pair)
    panel = delayed_targets(pair, panel)
    early = panel.era.eq("early_exploration")

    cuts = panel.loc[early, REGIME].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    quintile = pd.Series(
        np.digitize(panel[REGIME].to_numpy(float), cuts, right=True) + 1.0, index=panel.index
    )
    quintile[panel[REGIME].isna()] = np.nan

    baseline_rows = int(panel[f"ret_bp_d0"].notna().sum())
    rows = []
    for d in DELAYS:
        ret_bp, ret_pips = f"ret_bp_d{d}", f"ret_pips_d{d}"
        coverage = panel[ret_bp].notna().sum() / baseline_rows
        pooled = {
            "ic_rsi": within_slot_ic(panel, "rsi_14", ret_bp),
            "ic_past_30m": within_slot_ic(panel, "past_ret_30m_bp", ret_bp),
            "ic_past_1m": within_slot_ic(panel, "past_ret_1m_bp", ret_bp),
        }
        for q in range(1, 6):
            g = panel.loc[quintile.eq(q)]
            rsi_side = pd.Series(
                np.where(g.rsi_14 <= 30, 1.0, np.where(g.rsi_14 >= 70, -1.0, 0.0)), index=g.index
            )
            past_rank = g.groupby("session_minute").past_ret_30m_bp.rank(pct=True)
            no_rsi_side = pd.Series(
                np.where(past_rank <= 0.10, 1.0, np.where(past_rank >= 0.90, -1.0, 0.0)),
                index=g.index,
            )
            rsi_pnl = fade_stats(g, rsi_side, ret_pips)
            no_rsi_pnl = fade_stats(g, no_rsi_side, ret_pips)
            rows.append(
                {
                    "pair": pair,
                    "delay": d,
                    "quintile": q,
                    "n": int(len(g)),
                    "coverage_vs_d0": coverage,
                    "pooled_ic_rsi": pooled["ic_rsi"],
                    "pooled_ic_past_30m": pooled["ic_past_30m"],
                    "pooled_ic_past_1m": pooled["ic_past_1m"],
                    "ic_rsi": within_slot_ic(g, "rsi_14", ret_bp),
                    "ic_past_30m": within_slot_ic(g, "past_ret_30m_bp", ret_bp),
                    "ic_past_1m": within_slot_ic(g, "past_ret_1m_bp", ret_bp),
                    "rsi_signals": rsi_pnl["n"],
                    "rsi_gross_pips": rsi_pnl["gross_pips"],
                    "rsi_cluster_t": rsi_pnl["cluster_t"],
                    "no_rsi_gross_pips": no_rsi_pnl["gross_pips"],
                    "no_rsi_cluster_t": no_rsi_pnl["cluster_t"],
                }
            )
    return rows


def main():
    rows = []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        rows.extend(analyse(pair))
    quintiles = pd.DataFrame(rows)

    gradient_rows = []
    for (pair, delay), g in quintiles.groupby(["pair", "delay"]):
        g = g.set_index("quintile")
        row = {"pair": pair, "delay": delay, "coverage_vs_d0": g.coverage_vs_d0.iloc[0]}
        for column in ["ic_rsi", "ic_past_30m", "ic_past_1m"]:
            row[f"{column}_gradient"] = -g.loc[5, column] - (-g.loc[1, column])
        row["pooled_ic_rsi"] = g.pooled_ic_rsi.iloc[0]
        row["q5_rsi_gross_pips"] = g.loc[5, "rsi_gross_pips"]
        row["q5_rsi_cluster_t"] = g.loc[5, "rsi_cluster_t"]
        gradient_rows.append(row)
    gradients = pd.DataFrame(gradient_rows).sort_values(["pair", "delay"])

    median = gradients.groupby("delay").agg(
        median_ic_rsi_gradient=("ic_rsi_gradient", "median"),
        median_ic_past30_gradient=("ic_past_30m_gradient", "median"),
        median_pooled_ic_rsi=("pooled_ic_rsi", "median"),
        median_q5_gross_pips=("q5_rsi_gross_pips", "median"),
        min_coverage=("coverage_vs_d0", "min"),
    )
    g0 = median.loc[0, "median_ic_rsi_gradient"]
    g1 = median.loc[1, "median_ic_rsi_gradient"]
    level0 = abs(median.loc[0, "median_pooled_ic_rsi"])
    level1 = abs(median.loc[1, "median_pooled_ic_rsi"])
    ratio = g1 / g0 if g0 else np.nan
    level_ratio = level1 / level0 if level0 else np.nan

    print("\nPer pair and delay")
    print(gradients.round(4).to_string(index=False))
    print("\nMedian across pairs by delay")
    print(median.round(4).to_string())

    verdict = (
        "RETIRE — regime gradient is majority first traded minute"
        if ratio < GRADIENT_KILL_RATIO
        else (
            "PROCEED to Arms 1-3"
            if level_ratio >= 0.50
            else "WATCH ONLY — gradient survives but reversion level does not"
        )
    )
    print(
        f"\nKILL TEST  G(1)/G(0) = {ratio:.3f}  (threshold {GRADIENT_KILL_RATIO})"
        f"   level retention = {level_ratio:.3f}"
        f"\nVERDICT: {verdict}"
    )

    quintiles.to_csv(QUINTILE_CSV, index=False)
    gradients.to_csv(GRADIENT_CSV, index=False)
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "pairs": PAIRS,
                    "delays": DELAYS,
                    "regime": REGIME,
                    "gradient_kill_ratio": GRADIENT_KILL_RATIO,
                    "holdout_start": HOLDOUT.isoformat(),
                },
                "quintiles": json.loads(quintiles.to_json(orient="records")),
                "gradients": json.loads(gradients.to_json(orient="records")),
                "median_by_delay": json.loads(median.reset_index().to_json(orient="records")),
                "kill_test": {
                    "gradient_ratio_d1_over_d0": ratio,
                    "level_retention_d1_over_d0": level_ratio,
                    "verdict": verdict,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
