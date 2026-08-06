"""Test the frozen joint current-RV / expected-slot-RV RSI regime."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.api as sm
from scipy.stats import spearmanr

from _run_rsi_broad_regime_sweep import (
    ERA_SPLIT,
    HYPOTHETICAL_COST_PIPS,
    PAIRS,
    ROOT,
    SESSIONS_PER_YEAR,
    bh_adjust,
    build_pair,
    interaction_fit,
    pnl_metrics,
    session_cluster_t,
    within_slot_ic,
)


OUT = ROOT / "rsi_joint_volatility_regime_results.json"
MATRIX_CSV = ROOT / "rsi_joint_volatility_regime_matrix.csv"
SUMMARY_CSV = ROOT / "rsi_joint_volatility_regime_summary.csv"
INTERACTION_CSV = ROOT / "rsi_joint_volatility_regime_interactions.csv"
SURPRISE_INTERACTION_CSV = ROOT / "rsi_joint_volatility_regime_surprise_interactions.csv"
CHART_DIR = ROOT / "charts" / "rsi_joint_volatility_regime"
MEMORIES = [30, 90]


def fixed_empirical_percentile(values, reference):
    ref = np.sort(np.asarray(reference, float))
    ref = ref[np.isfinite(ref)]
    out = np.full(len(values), np.nan)
    valid = np.isfinite(values)
    if len(ref):
        out[valid] = np.searchsorted(ref, np.asarray(values)[valid], side="right") / len(ref)
    return out


def fixed_bins(values, cuts):
    values = np.asarray(values, float)
    out = np.full(len(values), np.nan)
    valid = np.isfinite(values)
    out[valid] = np.digitize(values[valid], cuts, right=True) + 1
    return out


def session_sharpe_at_cost(frame, all_sessions, cost):
    signals = frame.loc[(frame.rsi_14 <= 30) | (frame.rsi_14 >= 70)].copy()
    if signals.empty:
        return np.nan
    signals["side"] = np.where(signals.rsi_14 <= 30, 1.0, -1.0)
    signals["net"] = signals.side * signals.terminal_return_pips - cost
    daily = signals.groupby("sdate").net.sum().reindex(all_sessions, fill_value=0.0)
    sd = daily.std(ddof=1)
    return np.sqrt(SESSIONS_PER_YEAR) * daily.mean() / sd if sd > 0 else np.nan


def normalized_signal_metrics(frame, expected):
    signals = frame.loc[(frame.rsi_14 <= 30) | (frame.rsi_14 >= 70)].copy()
    if signals.empty:
        return {}
    signals["side"] = np.where(signals.rsi_14 <= 30, 1.0, -1.0)
    signals["expected_rv_units"] = signals.side * signals.signed_return_bp / signals[expected]
    signals["past_rv_units"] = signals.side * signals.signed_return_bp / (1e4 * signals.rv_30m_raw)
    signals = signals.replace([np.inf, -np.inf], np.nan)
    return {
        "mean_expected_rv_units": signals.expected_rv_units.mean(),
        "expected_rv_units_cluster_t": session_cluster_t(signals.expected_rv_units, signals.sdate),
        "mean_past_rv_units": signals.past_rv_units.mean(),
        "past_rv_units_cluster_t": session_cluster_t(signals.past_rv_units, signals.sdate),
    }


def joint_interaction(frame, current, expected_rank):
    cols = ["sdate", "session_minute", "year", "rsi_14", "signed_return_bp", current, expected_rank]
    z = frame[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(z) < 1000 or z.sdate.nunique() < 30:
        return {"n": len(z)}
    z["r"] = z.groupby("session_minute").rsi_14.rank(pct=True) - 0.5
    z["y"] = z.groupby("session_minute").signed_return_bp.rank(pct=True) - 0.5
    z["c"] = z[current] - 0.5
    z["e"] = z[expected_rank] - 0.5
    z["ce"] = z.c * z.e
    z["rc"] = z.r * z.c
    z["re"] = z.r * z.e
    z["rce"] = z.r * z.c * z.e
    years = pd.get_dummies(z.year.astype(int), prefix="year", drop_first=True, dtype=float)
    X = pd.concat(
        [pd.DataFrame({"const": 1.0, "r": z.r, "c": z.c, "e": z.e, "ce": z.ce,
                       "rc": z.rc, "re": z.re, "rce": z.rce}, index=z.index), years],
        axis=1,
    )
    fit = sm.OLS(z.y.to_numpy(), X).fit(cov_type="cluster", cov_kwds={"groups": z.sdate})
    return {
        "n": int(fit.nobs),
        "sessions": int(z.sdate.nunique()),
        "rsi_current_beta": fit.params["rc"],
        "rsi_current_t": fit.tvalues["rc"],
        "rsi_expected_beta": fit.params["re"],
        "rsi_expected_t": fit.tvalues["re"],
        "three_way_beta": fit.params["rce"],
        "three_way_t": fit.tvalues["rce"],
        "three_way_p": fit.pvalues["rce"],
        "r2": fit.rsquared,
    }


def analyze_panel(panel, pair, memory):
    current = f"rv_30m_pct_{memory}d"
    expected = f"slot_fwd_rv_median_{memory}d"
    expected_rank = f"slot_fwd_rv_rank_{memory}d"
    surprise = f"rv_surprise_log_{memory}d"
    early = panel.era.eq("early_exploration")
    panel = panel.copy()
    panel[expected_rank] = fixed_empirical_percentile(panel[expected].to_numpy(float), panel.loc[early, expected])
    ratio = (1e4 * panel.rv_30m_raw) / panel[expected]
    panel[surprise] = np.log(ratio.where(ratio.gt(0))).replace([np.inf, -np.inf], np.nan)

    current_cuts = panel.loc[early, current].quantile([1 / 3, 2 / 3]).to_numpy()
    expected_cuts = panel.loc[early, expected].quantile([1 / 3, 2 / 3]).to_numpy()
    surprise_cuts = panel.loc[early, surprise].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    panel["current_tercile"] = fixed_bins(panel[current], current_cuts)
    panel["expected_tercile"] = fixed_bins(panel[expected], expected_cuts)
    panel["surprise_quintile"] = fixed_bins(panel[surprise], surprise_cuts)

    matrix_rows = []
    summary_rows = []
    interaction_rows = []
    surprise_rows = []
    surprise_interaction_rows = []
    for era, group in panel.groupby("era"):
        all_sessions = pd.Index(sorted(group.sdate.unique()))
        for c in [1, 2, 3]:
            for e in [1, 2, 3]:
                z = group.loc[group.current_tercile.eq(c) & group.expected_tercile.eq(e)]
                metrics = pnl_metrics(z, all_sessions)
                normalized = normalized_signal_metrics(z, expected)
                matrix_rows.append({
                    "pair": pair, "era": era, "memory": memory,
                    "current_tercile": c, "expected_tercile": e,
                    "n": len(z), "within_slot_ic": within_slot_ic(z),
                    "net_10_mean_pips": metrics.get("mean_gross_pips", np.nan) - 1.0,
                    "net_10_session_sharpe": session_sharpe_at_cost(z, all_sessions, 1.0),
                    **metrics, **normalized,
                })
        for q in range(1, 6):
            z = group.loc[group.surprise_quintile.eq(q)]
            metrics = pnl_metrics(z, all_sessions)
            normalized = normalized_signal_metrics(z, expected)
            surprise_rows.append({
                "pair": pair, "era": era, "memory": memory, "quintile": q,
                "n": len(z), "within_slot_ic": within_slot_ic(z), **metrics, **normalized,
            })
        candidate = group.loc[group.current_tercile.eq(3) & group.expected_tercile.eq(1)]
        adverse = group.loc[group.current_tercile.eq(3) & group.expected_tercile.eq(3)]
        cm = pnl_metrics(candidate, all_sessions)
        am = pnl_metrics(adverse, all_sessions)
        cn = normalized_signal_metrics(candidate, expected)
        an = normalized_signal_metrics(adverse, expected)
        c_ic = within_slot_ic(candidate)
        a_ic = within_slot_ic(adverse)
        summary_rows.append({
            "pair": pair, "era": era, "memory": memory,
            "candidate_n": len(candidate), "adverse_n": len(adverse),
            "candidate_signals": cm.get("signals", 0), "adverse_signals": am.get("signals", 0),
            "candidate_ic": c_ic, "adverse_ic": a_ic,
            "candidate_minus_adverse_ic_strength": -c_ic - (-a_ic),
            "candidate_gross_pips": cm.get("mean_gross_pips", np.nan),
            "adverse_gross_pips": am.get("mean_gross_pips", np.nan),
            "candidate_minus_adverse_gross_pips": cm.get("mean_gross_pips", np.nan) - am.get("mean_gross_pips", np.nan),
            "candidate_hit_rate": cm.get("hit_rate", np.nan),
            "adverse_hit_rate": am.get("hit_rate", np.nan),
            "candidate_session_sharpe": cm.get("session_sharpe", np.nan),
            "adverse_session_sharpe": am.get("session_sharpe", np.nan),
            "candidate_net_05_pips": cm.get("mean_net_05_pips", np.nan),
            "adverse_net_05_pips": am.get("mean_net_05_pips", np.nan),
            "candidate_net_05_sharpe": cm.get("net_05_session_sharpe", np.nan),
            "adverse_net_05_sharpe": am.get("net_05_session_sharpe", np.nan),
            "candidate_mfe_mae": cm.get("mfe_mae_ratio", np.nan),
            "adverse_mfe_mae": am.get("mfe_mae_ratio", np.nan),
            "candidate_max_drawdown": cm.get("max_drawdown_pips", np.nan),
            "adverse_max_drawdown": am.get("max_drawdown_pips", np.nan),
            "candidate_expected_rv_units": cn.get("mean_expected_rv_units", np.nan),
            "adverse_expected_rv_units": an.get("mean_expected_rv_units", np.nan),
            "candidate_past_rv_units": cn.get("mean_past_rv_units", np.nan),
            "adverse_past_rv_units": an.get("mean_past_rv_units", np.nan),
        })
        interaction_rows.append({"pair": pair, "era": era, "memory": memory} | joint_interaction(group, current, expected_rank))
        surprise_interaction_rows.append(
            {"pair": pair, "era": era, "memory": memory} | interaction_fit(group, surprise)
        )
    cuts = {
        "pair": pair, "memory": memory,
        "current_terciles": current_cuts.tolist(),
        "expected_terciles": expected_cuts.tolist(),
        "surprise_quintiles": surprise_cuts.tolist(),
    }
    return matrix_rows, summary_rows, interaction_rows, surprise_rows, surprise_interaction_rows, cuts


def create_charts(matrix, summary, surprise):
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    for memory in MEMORIES:
        z = matrix.loc[matrix.memory.eq(memory)].copy()
        agg = z.groupby(["expected_tercile", "current_tercile"], as_index=False).agg(
            ic_strength=("within_slot_ic", lambda x: -x.median()),
            gross_pips=("mean_gross_pips", "median"),
            signals=("signals", "median"),
        )
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        ic = agg.pivot(index="expected_tercile", columns="current_tercile", values="ic_strength").sort_index(ascending=False)
        pnl = agg.pivot(index="expected_tercile", columns="current_tercile", values="gross_pips").sort_index(ascending=False)
        sns.heatmap(ic, annot=True, fmt=".03f", cmap="Blues", ax=axes[0], cbar_kws={"label": "Median |RSI IC|"})
        sns.heatmap(pnl, annot=True, fmt=".02f", center=0, cmap="vlag", ax=axes[1], cbar_kws={"label": "Gross pips/signal"})
        for ax in axes:
            ax.set_xlabel("Current RV tercile (high →)")
            ax.set_ylabel("Expected forward RV tercile")
        axes[0].set_title("RSI predictive strength")
        axes[1].set_title("Fixed RSI 30/70 payoff")
        fig.suptitle(f"Joint current/expected volatility regime — {memory}-session memory", y=1.02)
        fig.tight_layout()
        fig.savefig(CHART_DIR / f"joint_regime_{memory}d_heatmaps.png", dpi=180, bbox_inches="tight")
        plt.close(fig)

    s = summary.copy()
    s["cell"] = s.pair.str[:3] + "-" + s.era.map({"early_exploration": "early", "late_exploration": "late"})
    s = s.loc[s.memory.eq(90)].sort_values("candidate_minus_adverse_ic_strength")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].barh(s.cell, s.candidate_minus_adverse_ic_strength)
    axes[0].axvline(0, color="0.2", lw=1)
    axes[0].set_xlabel("Candidate − adverse |IC|")
    axes[0].set_title("High-current/low-expected IC advantage")
    axes[1].barh(s.cell, s.candidate_minus_adverse_gross_pips)
    axes[1].axvline(0, color="0.2", lw=1)
    axes[1].set_xlabel("Candidate − adverse gross pips/signal")
    axes[1].set_title("Corresponding fixed-threshold P&L difference")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "candidate_vs_adverse_90d.png", dpi=180)
    plt.close(fig)

    q = surprise.groupby(["memory", "quintile"], as_index=False).agg(
        ic_strength=("within_slot_ic", lambda x: -x.median()),
        gross_pips=("mean_gross_pips", "median"),
        expected_rv_units=("mean_expected_rv_units", "median"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for memory, group in q.groupby("memory"):
        label = f"{memory} sessions"
        axes[0].plot(group.quintile, group.ic_strength, marker="o", label=label)
        axes[1].plot(group.quintile, group.gross_pips, marker="o", label=label)
        axes[2].plot(group.quintile, group.expected_rv_units, marker="o", label=label)
    axes[0].set_title("RSI predictive strength")
    axes[0].set_ylabel("Median |RSI IC|")
    axes[1].set_title("Fixed RSI 30/70 payoff")
    axes[1].set_ylabel("Median gross pips/signal")
    axes[2].set_title("Volatility-normalized payoff")
    axes[2].set_ylabel("Mean return / expected RV")
    for ax in axes:
        ax.set_xlabel("Volatility-surprise quintile")
        ax.set_xticks(range(1, 6))
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(CHART_DIR / "surprise_quintile_curves.png", dpi=180)
    plt.close(fig)


def main():
    matrix_rows, summary_rows, interaction_rows, surprise_rows, surprise_interaction_rows, cuts = [], [], [], [], [], []
    qualities = []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        panel, _, quality = build_pair(pair)
        qualities.append(quality)
        for memory in MEMORIES:
            result = analyze_panel(panel, pair, memory)
            for destination, values in zip(
                [matrix_rows, summary_rows, interaction_rows, surprise_rows, surprise_interaction_rows, cuts], result
            ):
                destination.extend(values if isinstance(values, list) else [values])
    matrix = pd.DataFrame(matrix_rows)
    summary = pd.DataFrame(summary_rows)
    interactions = pd.DataFrame(interaction_rows)
    interactions["three_way_q"] = np.nan
    for memory, idx in interactions.groupby("memory").groups.items():
        interactions.loc[idx, "three_way_q"] = bh_adjust(interactions.loc[idx, "three_way_p"])
    surprise = pd.DataFrame(surprise_rows)
    surprise_interactions = pd.DataFrame(surprise_interaction_rows)
    surprise_interactions["interaction_q"] = np.nan
    for memory, idx in surprise_interactions.groupby("memory").groups.items():
        surprise_interactions.loc[idx, "interaction_q"] = bh_adjust(surprise_interactions.loc[idx, "interaction_p"])
    create_charts(matrix, summary, surprise)
    payload = {
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "pairs": PAIRS, "era_split": ERA_SPLIT.isoformat(),
            "holdout_start": "2024-01-01T00:00:00+00:00",
            "timezone": "America/New_York", "memories": MEMORIES,
            "hypothetical_cost_pips": HYPOTHETICAL_COST_PIPS,
        },
        "quality": json.loads(pd.DataFrame(qualities).to_json(orient="records", date_format="iso")),
        "cutpoints": cuts,
        "matrix": json.loads(matrix.to_json(orient="records")),
        "summary": json.loads(summary.to_json(orient="records")),
        "interactions": json.loads(interactions.to_json(orient="records")),
        "surprise_quintiles": json.loads(surprise.to_json(orient="records")),
        "surprise_interactions": json.loads(surprise_interactions.to_json(orient="records")),
        "charts": [str(p.relative_to(ROOT)) for p in sorted(CHART_DIR.glob("*.png"))],
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    matrix.to_csv(MATRIX_CSV, index=False)
    summary.to_csv(SUMMARY_CSV, index=False)
    interactions.to_csv(INTERACTION_CSV, index=False)
    surprise_interactions.to_csv(SURPRISE_INTERACTION_CSV, index=False)
    print("\nCandidate versus adverse:")
    print(summary.round(4).to_string(index=False))
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
