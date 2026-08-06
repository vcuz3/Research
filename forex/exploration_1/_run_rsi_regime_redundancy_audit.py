"""Audit the volatility-regime features carried by the joint and acceleration reports.

Arm 1 (redundancy): are the two recommended features distinguishable, at the metric
those reports use (within-slot rank correlation), from same-slot percentiles of the
volatility levels in their own numerators?

Arm 2 (no-RSI degenerate control): does the surprise-quintile gradient in reversion
strength survive when RSI is removed from the pipeline entirely and replaced by the
raw trailing return?

Reproduce with:
    python -u _run_rsi_regime_redundancy_audit.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from _run_rsi_broad_regime_sweep import (
    DATA,
    HOLDOUT,
    PAIRS,
    ROOT,
    build_pair,
    causal_slot_percentile,
    exact_lag,
    session_cluster_t,
)

OUT = ROOT / "rsi_regime_redundancy_audit_results.json"
REDUNDANCY_CSV = ROOT / "rsi_regime_redundancy_audit_redundancy.csv"
QUINTILE_CSV = ROOT / "rsi_regime_redundancy_audit_no_rsi_quintiles.csv"
MEMORIES = [30, 90]
MIN_SLOT_N = 50


def within_slot_rho(frame, a, b):
    """Median across New York slots of Spearman(a, b) computed inside each slot.

    The reports measure RSI information with a within-slot rank statistic, so the
    within-slot correlation is the one that decides whether two candidate features
    are the same variable for their purposes. The pooled correlation is reported
    alongside it because the two differ materially here.
    """
    z = frame[["session_minute", a, b]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(z) < 200:
        return np.nan, np.nan
    per_slot = z.groupby("session_minute").apply(
        lambda g: spearmanr(g[a], g[b]).statistic if len(g) > MIN_SLOT_N else np.nan,
        include_groups=False,
    )
    return per_slot.median(), spearmanr(z[a], z[b]).statistic


def top_quintile_overlap(frame, a, b):
    z = frame[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
    if z.empty:
        return np.nan
    qa = z[a] >= z[a].quantile(0.8)
    qb = z[b] >= z[b].quantile(0.8)
    return (qa & qb).sum() / qa.sum()


def within_slot_ic(frame, feature, target="signed_return_bp"):
    """Within-slot Spearman IC, matching the construction used by the audited reports."""
    z = frame[["session_minute", feature, target]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(z) < 200:
        return np.nan
    fr = z.groupby("session_minute")[feature].rank(pct=True)
    tr = z.groupby("session_minute")[target].rank(pct=True)
    return spearmanr(fr, tr).statistic


def attach_past_returns(pair, panel):
    """Trailing 30-minute and 1-minute returns at the decision bar, gap-exact."""
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "close"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    logc = pd.Series(np.log(raw.close.astype(float)), index=raw.index)
    past = pd.DataFrame(
        {
            "ts_utc": raw.time,
            "past_ret_30m_bp": 1e4 * (logc - exact_lag(logc, raw.time, 30)),
            "past_ret_1m_bp": 1e4 * (logc - exact_lag(logc, raw.time, 1)),
        }
    )
    return panel.merge(past, on="ts_utc", how="left")


def fade_stats(frame, side):
    z = frame.loc[side.ne(0) & frame.terminal_return_pips.notna()]
    if z.empty:
        return {"n": 0, "gross_pips": np.nan, "cluster_t": np.nan, "hit_rate": np.nan}
    gross = side.loc[z.index] * z.terminal_return_pips
    return {
        "n": int(len(z)),
        "gross_pips": gross.mean(),
        "cluster_t": session_cluster_t(gross, z.sdate),
        "hit_rate": gross.gt(0).mean(),
    }


def analyse(pair):
    panel, _, quality = build_pair(pair)
    panel = attach_past_returns(pair, panel)
    panel["rv_5m_raw"] = panel.rv_ratio_5_30_raw * panel.rv_30m_raw
    early = panel.era.eq("early_exploration")

    redundancy_rows = []
    for memory in MEMORIES:
        expected = f"slot_fwd_rv_median_{memory}d"
        panel[f"rv_5m_pct_{memory}d"] = causal_slot_percentile(panel, "rv_5m_raw", memory)

        ratio_30 = (1e4 * panel.rv_30m_raw) / panel[expected]
        panel[f"surprise_{memory}d"] = np.log(ratio_30.where(ratio_30.gt(0))).replace(
            [np.inf, -np.inf], np.nan
        )
        ratio_5 = (1e4 * panel.rv_5m_raw) / panel[expected]
        panel[f"fast_surprise_{memory}d"] = np.log(ratio_5.where(ratio_5.gt(0))).replace(
            [np.inf, -np.inf], np.nan
        )

        # The recommended feature, versus the same-slot percentile of its own numerator.
        comparisons = [
            (f"surprise_{memory}d", f"rv_30m_pct_{memory}d", "30m surprise vs RV(30) slot pct"),
            (f"fast_surprise_{memory}d", f"rv_5m_pct_{memory}d", "fast surprise vs RV(5) slot pct"),
            (
                f"fast_surprise_{memory}d",
                f"rv_ratio_5_30_pct_{memory}d",
                "fast surprise vs RV(5)/RV(30) acceleration",
            ),
            (
                f"fast_surprise_{memory}d",
                f"surprise_{memory}d",
                "fast surprise vs 30m surprise",
            ),
        ]
        for feature, benchmark, label in comparisons:
            rho_slot, rho_pooled = within_slot_rho(panel, feature, benchmark)
            redundancy_rows.append(
                {
                    "pair": pair,
                    "memory": memory,
                    "comparison": label,
                    "feature": feature,
                    "benchmark": benchmark,
                    "within_slot_rho": rho_slot,
                    "pooled_rho": rho_pooled,
                    "top_quintile_overlap": top_quintile_overlap(panel, feature, benchmark),
                }
            )

    # Arm 2 uses the joint report's preferred primary feature and memory.
    feature = "surprise_90d"
    cuts = panel.loc[early, feature].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    quintile = pd.Series(
        np.digitize(panel[feature].to_numpy(float), cuts, right=True) + 1.0, index=panel.index
    )
    quintile[panel[feature].isna()] = np.nan

    quintile_rows = []
    for q in range(1, 6):
        g = panel.loc[quintile.eq(q)]
        rsi_side = pd.Series(
            np.where(g.rsi_14 <= 30, 1.0, np.where(g.rsi_14 >= 70, -1.0, 0.0)), index=g.index
        )
        # No-RSI fade: same 30/70-style tail selectivity, applied to the raw trailing
        # return ranked within its own slot. No RSI anywhere in this arm.
        past_rank = g.groupby("session_minute").past_ret_30m_bp.rank(pct=True)
        no_rsi_side = pd.Series(
            np.where(past_rank <= 0.10, 1.0, np.where(past_rank >= 0.90, -1.0, 0.0)), index=g.index
        )
        rsi_pnl = fade_stats(g, rsi_side)
        no_rsi_pnl = fade_stats(g, no_rsi_side)
        quintile_rows.append(
            {
                "pair": pair,
                "quintile": q,
                "n": int(len(g)),
                "ic_rsi": within_slot_ic(g, "rsi_14"),
                "ic_past_30m": within_slot_ic(g, "past_ret_30m_bp"),
                "ic_past_1m": within_slot_ic(g, "past_ret_1m_bp"),
                "rsi_signals": rsi_pnl["n"],
                "rsi_gross_pips": rsi_pnl["gross_pips"],
                "rsi_cluster_t": rsi_pnl["cluster_t"],
                "no_rsi_signals": no_rsi_pnl["n"],
                "no_rsi_gross_pips": no_rsi_pnl["gross_pips"],
                "no_rsi_cluster_t": no_rsi_pnl["cluster_t"],
                "mean_abs_forward_bp": g.signed_return_bp.abs().mean(),
            }
        )
    return redundancy_rows, quintile_rows, quality


def main():
    redundancy_rows, quintile_rows, qualities = [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, q, quality = analyse(pair)
        redundancy_rows.extend(r)
        quintile_rows.extend(q)
        qualities.append(quality)

    redundancy = pd.DataFrame(redundancy_rows)
    quintiles = pd.DataFrame(quintile_rows)

    # Share of the RSI regime gradient that survives with RSI removed.
    gradient_rows = []
    for pair, g in quintiles.groupby("pair"):
        g = g.set_index("quintile")
        for column, label in [("ic_past_30m", "past 30m return"), ("ic_past_1m", "past 1m return")]:
            rsi_gradient = -g.loc[5, "ic_rsi"] - (-g.loc[1, "ic_rsi"])
            other_gradient = -g.loc[5, column] - (-g.loc[1, column])
            gradient_rows.append(
                {
                    "pair": pair,
                    "no_rsi_feature": label,
                    "rsi_q5_minus_q1_ic_strength": rsi_gradient,
                    "no_rsi_q5_minus_q1_ic_strength": other_gradient,
                    "share_of_rsi_gradient": other_gradient / rsi_gradient
                    if rsi_gradient
                    else np.nan,
                }
            )
    gradients = pd.DataFrame(gradient_rows)

    print("\nArm 1 — feature redundancy")
    print(redundancy.round(4).to_string(index=False))
    print("\nArm 2 — surprise quintiles with and without RSI")
    print(quintiles.round(4).to_string(index=False))
    print("\nArm 2 — share of the regime gradient surviving without RSI")
    print(gradients.round(4).to_string(index=False))

    payload = {
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "pairs": PAIRS,
            "memories": MEMORIES,
            "holdout_start": HOLDOUT.isoformat(),
            "arm2_feature": "surprise_90d",
            "min_slot_n_for_within_slot_rho": MIN_SLOT_N,
        },
        "quality": json.loads(pd.DataFrame(qualities).to_json(orient="records", date_format="iso")),
        "redundancy": json.loads(redundancy.to_json(orient="records")),
        "no_rsi_quintiles": json.loads(quintiles.to_json(orient="records")),
        "gradient_shares": json.loads(gradients.to_json(orient="records")),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    redundancy.to_csv(REDUNDANCY_CSV, index=False)
    quintiles.to_csv(QUINTILE_CSV, index=False)
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
