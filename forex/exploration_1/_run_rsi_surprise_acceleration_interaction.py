"""Test RSI interaction between volatility surprise and acceleration."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm

from _run_rsi_broad_regime_sweep import (
    ERA_SPLIT,
    HYPOTHETICAL_COST_PIPS,
    PAIRS,
    ROOT,
    bh_adjust,
    build_pair,
    interaction_fit as single_interaction_fit,
    pnl_metrics,
    within_slot_ic,
)
from _run_rsi_joint_volatility_regime import (
    fixed_bins,
    fixed_empirical_percentile,
    normalized_signal_metrics,
)


OUT = ROOT / "rsi_surprise_acceleration_interaction_results.json"
MATRIX_CSV = ROOT / "rsi_surprise_acceleration_interaction_matrix.csv"
SUMMARY_CSV = ROOT / "rsi_surprise_acceleration_interaction_summary.csv"
INTERACTION_CSV = ROOT / "rsi_surprise_acceleration_interaction_regressions.csv"
FAST_CSV = ROOT / "rsi_fast_volatility_surprise_quintiles.csv"
FAST_INTERACTION_CSV = ROOT / "rsi_fast_volatility_surprise_interactions.csv"
CHART_DIR = ROOT / "charts" / "rsi_surprise_acceleration_interaction"
MEMORIES = [30, 90]
ACCELERATIONS = {
    "rv_5_30": "rv_ratio_5_30_pct_{memory}d",
    "vei_10_50": "vei_10_50_pct_{memory}d",
    "vei_25_100": "vei_25_100_pct_{memory}d",
}


def interaction_fit(frame, surprise_rank, acceleration):
    cols = ["sdate", "session_minute", "year", "rsi_14", "signed_return_bp", surprise_rank, acceleration]
    z = frame[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(z) < 1000 or z.sdate.nunique() < 30:
        return {"n": len(z)}
    z["r"] = z.groupby("session_minute").rsi_14.rank(pct=True) - 0.5
    z["y"] = z.groupby("session_minute").signed_return_bp.rank(pct=True) - 0.5
    z["s"] = z[surprise_rank] - 0.5
    z["a"] = z[acceleration] - 0.5
    z["sa"] = z.s * z.a
    z["rs"] = z.r * z.s
    z["ra"] = z.r * z.a
    z["rsa"] = z.r * z.s * z.a
    years = pd.get_dummies(z.year.astype(int), prefix="year", drop_first=True, dtype=float)
    X = pd.concat(
        [pd.DataFrame({"const": 1.0, "r": z.r, "s": z.s, "a": z.a, "sa": z.sa,
                       "rs": z.rs, "ra": z.ra, "rsa": z.rsa}, index=z.index), years],
        axis=1,
    )
    fit = sm.OLS(z.y.to_numpy(), X).fit(cov_type="cluster", cov_kwds={"groups": z.sdate})
    return {
        "n": int(fit.nobs), "sessions": int(z.sdate.nunique()),
        "rsi_surprise_beta": fit.params["rs"], "rsi_surprise_t": fit.tvalues["rs"],
        "rsi_acceleration_beta": fit.params["ra"], "rsi_acceleration_t": fit.tvalues["ra"],
        "three_way_beta": fit.params["rsa"], "three_way_t": fit.tvalues["rsa"],
        "three_way_p": fit.pvalues["rsa"], "r2": fit.rsquared,
    }


def cell_metrics(frame, all_sessions, expected):
    p = pnl_metrics(frame, all_sessions)
    n = normalized_signal_metrics(frame, expected)
    return {"n": len(frame), "within_slot_ic": within_slot_ic(frame), **p, **n}


def analyze(panel, pair, memory, acceleration_name, acceleration):
    expected = f"slot_fwd_rv_median_{memory}d"
    surprise = f"surprise_log_{memory}d"
    surprise_rank = f"surprise_rank_{memory}d"
    panel = panel.copy()
    ratio = (1e4 * panel.rv_30m_raw) / panel[expected]
    panel[surprise] = np.log(ratio.where(ratio.gt(0))).replace([np.inf, -np.inf], np.nan)
    early = panel.era.eq("early_exploration")
    panel[surprise_rank] = fixed_empirical_percentile(panel[surprise].to_numpy(float), panel.loc[early, surprise])
    s_cuts = panel.loc[early, surprise_rank].quantile([1 / 3, 2 / 3]).to_numpy()
    a_cuts = panel.loc[early, acceleration].quantile([1 / 3, 2 / 3]).to_numpy()
    panel["surprise_tercile"] = fixed_bins(panel[surprise_rank], s_cuts)
    panel["acceleration_tercile"] = fixed_bins(panel[acceleration], a_cuts)

    matrix_rows, summary_rows, regression_rows = [], [], []
    for era, group in panel.groupby("era"):
        sessions = pd.Index(sorted(group.sdate.unique()))
        cells = {}
        for s in [1, 2, 3]:
            for a in [1, 2, 3]:
                z = group.loc[group.surprise_tercile.eq(s) & group.acceleration_tercile.eq(a)]
                metrics = cell_metrics(z, sessions, expected)
                row = {"pair": pair, "era": era, "memory": memory,
                       "acceleration": acceleration_name, "surprise_tercile": s,
                       "acceleration_tercile": a, **metrics}
                matrix_rows.append(row)
                cells[(s, a)] = row
        hh, hl, lh, ll = cells[(3, 3)], cells[(3, 1)], cells[(1, 3)], cells[(1, 1)]
        strength = lambda row: -row["within_slot_ic"]
        summary_rows.append({
            "pair": pair, "era": era, "memory": memory, "acceleration": acceleration_name,
            "raw_spearman": group[surprise_rank].corr(group[acceleration], method="spearman"),
            "within_slot_spearman": group.groupby("session_minute")[surprise_rank].rank(pct=True).corr(
                group.groupby("session_minute")[acceleration].rank(pct=True), method="spearman"),
            "hh_n": hh["n"], "hh_signals": hh.get("signals", 0), "hh_ic": hh["within_slot_ic"],
            "hh_gross_pips": hh.get("mean_gross_pips", np.nan),
            "hh_net_05_pips": hh.get("mean_net_05_pips", np.nan),
            "hh_hit_rate": hh.get("hit_rate", np.nan),
            "hh_session_sharpe": hh.get("session_sharpe", np.nan),
            "hh_net_05_sharpe": hh.get("net_05_session_sharpe", np.nan),
            "hh_signals_per_year": hh.get("signals_per_year", np.nan),
            "hh_mfe_mae": hh.get("mfe_mae_ratio", np.nan),
            "hh_drawdown": hh.get("max_drawdown_pips", np.nan),
            "hh_expected_rv_units": hh.get("mean_expected_rv_units", np.nan),
            "acceleration_within_high_surprise_ic_gain": strength(hh) - strength(hl),
            "acceleration_within_high_surprise_pnl_gain": hh.get("mean_gross_pips", np.nan) - hl.get("mean_gross_pips", np.nan),
            "surprise_within_high_acceleration_ic_gain": strength(hh) - strength(lh),
            "surprise_within_high_acceleration_pnl_gain": hh.get("mean_gross_pips", np.nan) - lh.get("mean_gross_pips", np.nan),
            "ic_difference_in_differences": (strength(hh) - strength(hl)) - (strength(lh) - strength(ll)),
            "pnl_difference_in_differences":
                (hh.get("mean_gross_pips", np.nan) - hl.get("mean_gross_pips", np.nan))
                - (lh.get("mean_gross_pips", np.nan) - ll.get("mean_gross_pips", np.nan)),
        })
        regression_rows.append({"pair": pair, "era": era, "memory": memory,
                                "acceleration": acceleration_name}
                               | interaction_fit(group, surprise_rank, acceleration))
    cuts = {"pair": pair, "memory": memory, "acceleration": acceleration_name,
            "surprise_terciles": s_cuts.tolist(), "acceleration_terciles": a_cuts.tolist()}
    return matrix_rows, summary_rows, regression_rows, cuts


def analyze_fast_surprise(panel, pair, memory):
    expected = f"slot_fwd_rv_median_{memory}d"
    feature = f"fast_surprise_5m_{memory}d"
    panel = panel.copy()
    fast_rv_bp = 1e4 * panel.rv_30m_raw * panel.rv_ratio_5_30_raw
    ratio = fast_rv_bp / panel[expected]
    panel[feature] = np.log(ratio.where(ratio.gt(0))).replace([np.inf, -np.inf], np.nan)
    early = panel.era.eq("early_exploration")
    cuts = panel.loc[early, feature].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    panel["fast_quintile"] = fixed_bins(panel[feature], cuts)
    rows, interactions = [], []
    for era, group in panel.groupby("era"):
        sessions = pd.Index(sorted(group.sdate.unique()))
        for q in range(1, 6):
            z = group.loc[group.fast_quintile.eq(q)]
            rows.append({"pair": pair, "era": era, "memory": memory, "quintile": q,
                         **cell_metrics(z, sessions, expected)})
        interactions.append({"pair": pair, "era": era, "memory": memory}
                            | single_interaction_fit(group, feature))
    return rows, interactions, {"pair": pair, "memory": memory, "fast_surprise_quintiles": cuts.tolist()}


def create_charts(matrix, summary):
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    primary = matrix.loc[matrix.memory.eq(90) & matrix.acceleration.eq("rv_5_30")]
    agg = primary.groupby(["surprise_tercile", "acceleration_tercile"], as_index=False).agg(
        ic_strength=("within_slot_ic", lambda x: -x.median()),
        gross_pips=("mean_gross_pips", "median"),
        normalized=("mean_expected_rv_units", "median"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax, col, title, cmap, center, fmt in [
        (axes[0], "ic_strength", "RSI predictive strength", "Blues", None, ".03f"),
        (axes[1], "gross_pips", "Fixed RSI 30/70 payoff", "vlag", 0, ".02f"),
        (axes[2], "normalized", "Expected-RV-normalized payoff", "vlag", 0, ".03f"),
    ]:
        pivot = agg.pivot(index="surprise_tercile", columns="acceleration_tercile", values=col).sort_index(ascending=False)
        sns.heatmap(pivot, annot=True, fmt=fmt, cmap=cmap, center=center, ax=ax)
        ax.set_xlabel("RV(5)/RV(30) acceleration tercile")
        ax.set_ylabel("Volatility-surprise tercile")
        ax.set_title(title)
    fig.suptitle("Volatility surprise × acceleration — 90-session memory", y=1.02)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "primary_90d_interaction_heatmaps.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    s = summary.loc[summary.memory.eq(90) & summary.acceleration.eq("rv_5_30")].copy()
    s["cell"] = s.pair.str[:3] + "-" + s.era.map({"early_exploration": "early", "late_exploration": "late"})
    s = s.sort_values("acceleration_within_high_surprise_ic_gain")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].barh(s.cell, s.acceleration_within_high_surprise_ic_gain)
    axes[0].axvline(0, color="0.2", lw=1)
    axes[0].set_title("Acceleration value within high surprise")
    axes[0].set_xlabel("High-vs-low acceleration |IC| gain")
    axes[1].barh(s.cell, s.ic_difference_in_differences)
    axes[1].axvline(0, color="0.2", lw=1)
    axes[1].set_title("Non-additive interaction")
    axes[1].set_xlabel("IC difference-in-differences")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "primary_90d_incremental_and_synergy.png", dpi=180)
    plt.close(fig)


def main():
    matrix_rows, summary_rows, regression_rows, cuts, quality = [], [], [], [], []
    fast_rows, fast_interaction_rows = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        panel, _, q = build_pair(pair)
        quality.append(q)
        for memory in MEMORIES:
            fast_result = analyze_fast_surprise(panel, pair, memory)
            fast_rows.extend(fast_result[0]); fast_interaction_rows.extend(fast_result[1]); cuts.append(fast_result[2])
            for acceleration_name, template in ACCELERATIONS.items():
                result = analyze(panel, pair, memory, acceleration_name, template.format(memory=memory))
                matrix_rows.extend(result[0]); summary_rows.extend(result[1]); regression_rows.extend(result[2]); cuts.append(result[3])
    matrix = pd.DataFrame(matrix_rows)
    summary = pd.DataFrame(summary_rows)
    regressions = pd.DataFrame(regression_rows)
    regressions["three_way_q"] = np.nan
    for keys, idx in regressions.groupby(["memory", "acceleration"]).groups.items():
        regressions.loc[idx, "three_way_q"] = bh_adjust(regressions.loc[idx, "three_way_p"])
    fast = pd.DataFrame(fast_rows)
    fast_interactions = pd.DataFrame(fast_interaction_rows)
    fast_interactions["interaction_q"] = np.nan
    for memory, idx in fast_interactions.groupby("memory").groups.items():
        fast_interactions.loc[idx, "interaction_q"] = bh_adjust(fast_interactions.loc[idx, "interaction_p"])
    create_charts(matrix, summary)
    payload = {
        "metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "pairs": PAIRS,
                     "era_split": ERA_SPLIT.isoformat(), "holdout_start": "2024-01-01T00:00:00+00:00",
                     "timezone": "America/New_York", "memories": MEMORIES,
                     "accelerations": list(ACCELERATIONS), "hypothetical_cost_pips": HYPOTHETICAL_COST_PIPS},
        "quality": json.loads(pd.DataFrame(quality).to_json(orient="records", date_format="iso")),
        "cutpoints": cuts,
        "matrix": json.loads(matrix.to_json(orient="records")),
        "summary": json.loads(summary.to_json(orient="records")),
        "regressions": json.loads(regressions.to_json(orient="records")),
        "fast_surprise_quintiles": json.loads(fast.to_json(orient="records")),
        "fast_surprise_interactions": json.loads(fast_interactions.to_json(orient="records")),
        "charts": [str(p.relative_to(ROOT)) for p in sorted(CHART_DIR.glob("*.png"))],
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    matrix.to_csv(MATRIX_CSV, index=False); summary.to_csv(SUMMARY_CSV, index=False); regressions.to_csv(INTERACTION_CSV, index=False)
    fast.to_csv(FAST_CSV, index=False); fast_interactions.to_csv(FAST_INTERACTION_CSV, index=False)
    print("\nPrimary 90-session summary:")
    print(summary.loc[summary.memory.eq(90) & summary.acceleration.eq("rv_5_30")].round(4).to_string(index=False))
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
