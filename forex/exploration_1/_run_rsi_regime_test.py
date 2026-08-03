"""Run the frozen full-range RSI regime test on the pre-2024 decision panels."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr


os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "forex_feature_ml_research.ipynb"
OUT = ROOT / "rsi_regime_test_results.json"
EARLY_START = pd.Timestamp("2012-01-01", tz="UTC")
ERA_SPLIT = pd.Timestamp("2021-01-01", tz="UTC")
HOLDOUT_START = pd.Timestamp("2024-01-01", tz="UTC")
MIN_BIN_N = 250


def execute_build_cells() -> dict:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    namespace = {"__name__": "__main__"}
    for index in [1, 3, 6, 7]:
        print(f"\n--- executing source notebook cell {index} ---", flush=True)
        source = "".join(notebook["cells"][index]["source"])
        exec(compile(source, f"{NOTEBOOK.name}:cell-{index}", "exec"), namespace)
        if index == 1:
            pairs = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
            namespace["PAIRS"] = pairs
            namespace["ACTIVE_PAIRS"] = pairs
            namespace["PIP_SIZE"] = {pair: 0.0001 for pair in pairs}
            namespace["data_dir"] = ROOT.parent / "data" / "archive"
            print(f"Runner override: pairs={pairs}; data_dir={namespace['data_dir']}", flush=True)
    return namespace


def bh_adjust(values) -> np.ndarray:
    p = np.asarray(values, float)
    out = np.full(len(p), np.nan)
    valid = np.isfinite(p)
    if not valid.any():
        return out
    x = p[valid]
    order = np.argsort(x)
    ranked = x[order]
    adjusted = ranked * len(x) / np.arange(1, len(x) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1].clip(0, 1)
    restored = np.empty(len(x))
    restored[order] = adjusted
    out[valid] = restored
    return out


def within_slot_ic(frame: pd.DataFrame) -> float:
    z = frame[["session_minute", "rsi_14", "signed_return_bp"]].dropna().copy()
    if len(z) < MIN_BIN_N:
        return np.nan
    z["rsi_rank"] = z.groupby("session_minute").rsi_14.rank(pct=True)
    z["return_rank"] = z.groupby("session_minute").signed_return_bp.rank(pct=True)
    return z.rsi_rank.corr(z.return_rank)


def session_cluster_t(values, sessions) -> float:
    z = pd.DataFrame({"value": values, "session": sessions}).dropna()
    n = len(z)
    groups = z.session.nunique()
    if n < 2 or groups < 2:
        return np.nan
    mean = z.value.mean()
    scores = (z.value - mean).groupby(z.session).sum()
    se = np.sqrt((groups / (groups - 1)) * np.square(scores).sum()) / n
    return mean / se if se > 0 else np.nan


def interaction_fit(frame: pd.DataFrame, regime: str) -> dict:
    cols = ["sdate", "session_minute", "year", "rsi_14", "signed_return_bp", regime]
    z = frame[cols].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(z) < 1000 or z.sdate.nunique() < 30:
        return {"n": len(z)}
    z["rsi_rank"] = z.groupby("session_minute").rsi_14.rank(pct=True) - 0.5
    z["return_rank"] = z.groupby("session_minute").signed_return_bp.rank(pct=True) - 0.5
    z["regime_rank"] = z.groupby("session_minute")[regime].rank(pct=True) - 0.5
    z["interaction"] = z.rsi_rank * z.regime_rank
    year_dummies = pd.get_dummies(z.year.astype(int), prefix="year", drop_first=True, dtype=float)
    X = pd.concat(
        [
            pd.DataFrame(
                {
                    "const": 1.0,
                    "rsi_rank": z.rsi_rank,
                    "regime_rank": z.regime_rank,
                    "interaction": z.interaction,
                },
                index=z.index,
            ),
            year_dummies,
        ],
        axis=1,
    )
    fit = sm.OLS(z.return_rank.to_numpy(), X).fit(
        cov_type="cluster", cov_kwds={"groups": z.sdate}
    )
    return {
        "n": int(fit.nobs),
        "sessions": int(z.sdate.nunique()),
        "rsi_beta": fit.params["rsi_rank"],
        "interaction_beta": fit.params["interaction"],
        "interaction_t": fit.tvalues["interaction"],
        "interaction_p": fit.pvalues["interaction"],
        "r2": fit.rsquared,
    }


def main() -> None:
    namespace = execute_build_cells()
    frames = namespace["frames"]
    quality_report = namespace["quality_report"].reset_index()

    regime_builders = {
        "vei_pct": lambda f: f.vei_pct,
        "vei_z_90": lambda f: f.vei_z_90,
        "rv_30m_slot_z": lambda f: f.rv_30m_slot_z,
        "rv_5m": lambda f: f.rv_5m,
        "rv_15m": lambda f: f.rv_15m,
        "rv_30m": lambda f: f.rv_30m,
        "rv_60m": lambda f: f.rv_60m,
        "range_rv_15m": lambda f: f.range_rv_15m,
        "range_rv_30m": lambda f: f.range_rv_30m,
        "range_rv_60m": lambda f: f.range_rv_60m,
        "rv_ratio_5_30": lambda f: f.rv_ratio_5_30,
        "rv_ratio_15_60": lambda f: f.rv_ratio_15_60,
        "bar_range_atr": lambda f: f.bar_range_atr,
        "session_rv_bp": lambda f: f.session_rv_bp,
        "session_range_bp": lambda f: f.session_range_bp,
        "prior_session_rv": lambda f: f.prior_session_rv,
        "prior_rv_5d": lambda f: f.prior_rv_5d,
        "daily_vol_pct": lambda f: f.daily_vol_pct,
        "jump_share_30m": lambda f: f.jump_share_30m,
        "concentration_30m": lambda f: f.concentration_30m,
        "path_efficiency_30m": lambda f: f.path_efficiency_30m,
        "return_autocorr_30m": lambda f: f.return_autocorr_30m,
        "variance_ratio_30m": lambda f: f.variance_ratio_30m,
        "zero_return_share_30m": lambda f: f.zero_return_share_30m,
        "abs_dist_twap_atr14": lambda f: f.dist_twap_atr14.abs(),
        "abs_bollinger_z_60m": lambda f: f.bollinger_z_60m.abs(),
        "abs_ret_30m": lambda f: f.ret_30m.abs(),
    }

    panels = {}
    for pair, source in frames.items():
        f = source.loc[
            source.ts_utc.ge(EARLY_START) & source.ts_utc.lt(HOLDOUT_START)
        ].copy()
        f["era"] = np.where(f.ts_utc.lt(ERA_SPLIT), "early_exploration", "late_exploration")
        for name, builder in regime_builders.items():
            f[name] = builder(f)
        panels[pair] = f
        assert f.ts_utc.max() < HOLDOUT_START

    quintile_rows = []
    interaction_rows = []
    cutpoint_rows = []
    cutpoint_map = {}
    for pair, panel in panels.items():
        early = panel.loc[panel.era.eq("early_exploration")]
        for regime in regime_builders:
            cuts = np.unique(early[regime].replace([np.inf, -np.inf], np.nan).dropna().quantile([0.2, 0.4, 0.6, 0.8]))
            if len(cuts) != 4:
                continue
            cutpoint_map[(pair, regime)] = cuts
            cutpoint_rows.append({"pair": pair, "regime": regime, **{f"cut_{i+1}": v for i, v in enumerate(cuts)}})
            for era, group in panel.groupby("era"):
                values = group[regime].to_numpy(float)
                bins = np.digitize(values, cuts, right=True)
                for bin_index in range(5):
                    z = group.loc[np.isfinite(values) & (bins == bin_index)]
                    pooled = z.rsi_14.corr(z.signed_return_bp, method="spearman") if len(z) >= MIN_BIN_N else np.nan
                    quintile_rows.append(
                        {
                            "pair": pair,
                            "era": era,
                            "regime": regime,
                            "bin": bin_index + 1,
                            "n": len(z),
                            "pooled_ic": pooled,
                            "within_slot_ic": within_slot_ic(z),
                            "mean_return_bp": z.signed_return_bp.mean(),
                        }
                    )
                row = {"pair": pair, "era": era, "regime": regime}
                row.update(interaction_fit(group, regime))
                interaction_rows.append(row)

    quintiles = pd.DataFrame(quintile_rows)
    interactions = pd.DataFrame(interaction_rows)
    interactions["interaction_q"] = np.nan
    for _, idx in interactions.groupby(["pair", "era"]).groups.items():
        interactions.loc[idx, "interaction_q"] = bh_adjust(interactions.loc[idx, "interaction_p"])

    summaries = []
    for keys, group in quintiles.groupby(["pair", "era", "regime"]):
        q1 = group.loc[group.bin.eq(1)].iloc[0]
        q5 = group.loc[group.bin.eq(5)].iloc[0]
        strengths = -group.sort_values("bin").within_slot_ic.to_numpy()
        summaries.append(
            dict(zip(["pair", "era", "regime"], keys))
            | {
                "q1_ic": q1.within_slot_ic,
                "q5_ic": q5.within_slot_ic,
                "strength_q5_minus_q1": (-q5.within_slot_ic) - (-q1.within_slot_ic),
                "bin_strength_monotonic_rho": spearmanr(np.arange(1, 6), strengths).statistic,
            }
        )
    summaries = pd.DataFrame(summaries).merge(
        interactions[
            ["pair", "era", "regime", "interaction_beta", "interaction_t", "interaction_p", "interaction_q"]
        ],
        on=["pair", "era", "regime"],
        how="left",
    )

    categorical_rows = []
    for pair, panel in panels.items():
        utc_hour = panel.ts_utc.dt.hour
        panel = panel.copy()
        panel["utc_block"] = pd.cut(
            utc_hour,
            [0, 7, 12, 16, 24],
            right=False,
            labels=["00-07 UTC", "07-12 UTC", "12-16 UTC", "16-24 UTC"],
            include_lowest=True,
        )
        categories = {
            "utc_block": panel.utc_block.astype(str),
            "tokyo_open": panel.tokyo_open.map({0: "closed", 1: "open"}),
            "london_open": panel.london_open.map({0: "closed", 1: "open"}),
            "newyork_open": panel.newyork_open.map({0: "closed", 1: "open"}),
            "london_newyork_overlap": panel.london_newyork_overlap.map({0: "no", 1: "yes"}),
            "rollover_hour": panel.rollover_hour.map({0: "no", 1: "yes"}),
        }
        for era, era_group in panel.groupby("era"):
            for regime, labels in categories.items():
                for level in pd.unique(labels.loc[era_group.index].dropna()):
                    z = era_group.loc[labels.loc[era_group.index].eq(level)]
                    categorical_rows.append(
                        {
                            "pair": pair,
                            "era": era,
                            "regime": regime,
                            "level": str(level),
                            "n": len(z),
                            "pooled_ic": z.rsi_14.corr(z.signed_return_bp, method="spearman"),
                            "within_slot_ic": within_slot_ic(z),
                        }
                    )
    categorical = pd.DataFrame(categorical_rows)

    # Prespecified primary-claim checks: the VEI interaction by UTC block and
    # extreme-signal payoff by long/short direction.
    vei_time_rows = []
    vei_direction_rows = []
    for pair, panel in panels.items():
        cuts = cutpoint_map[(pair, "vei_pct")]
        panel = panel.copy()
        panel["vei_bin"] = np.digitize(panel.vei_pct.to_numpy(float), cuts, right=True) + 1
        panel["utc_block"] = pd.cut(
            panel.ts_utc.dt.hour,
            [0, 7, 12, 16, 24],
            right=False,
            labels=["00-07 UTC", "07-12 UTC", "12-16 UTC", "16-24 UTC"],
            include_lowest=True,
        )
        for era, era_group in panel.groupby("era"):
            for block, block_group in era_group.groupby("utc_block", observed=True):
                row = {"pair": pair, "era": era, "utc_block": str(block)}
                row.update(interaction_fit(block_group, "vei_pct"))
                vei_time_rows.append(row)
            for direction, mask, side in [
                ("long_rsi_le_30", era_group.rsi_14.le(30), 1.0),
                ("short_rsi_ge_70", era_group.rsi_14.ge(70), -1.0),
            ]:
                for bin_index in range(1, 6):
                    z = era_group.loc[mask & era_group.vei_bin.eq(bin_index)].copy()
                    pnl = side * z.signed_return_bp
                    vei_direction_rows.append(
                        {
                            "pair": pair,
                            "era": era,
                            "direction": direction,
                            "vei_bin": bin_index,
                            "n": len(z),
                            "mean_reversion_bp": pnl.mean(),
                            "cluster_t": session_cluster_t(pnl, z.sdate),
                        }
                    )
    vei_time = pd.DataFrame(vei_time_rows)
    vei_direction = pd.DataFrame(vei_direction_rows)

    stability = []
    for regime, group in summaries.groupby("regime"):
        stability.append(
            {
                "regime": regime,
                "cells": len(group),
                "q5_stronger_cells": int(group.strength_q5_minus_q1.gt(0).sum()),
                "strengthening_interaction_cells": int(group.interaction_beta.lt(0).sum()),
                "median_strength_q5_minus_q1": group.strength_q5_minus_q1.median(),
                "median_interaction_beta": group.interaction_beta.median(),
                "median_abs_interaction_t": group.interaction_t.abs().median(),
                "min_interaction_q": group.interaction_q.min(),
                "max_interaction_q": group.interaction_q.max(),
            }
        )
    stability = pd.DataFrame(stability).sort_values(
        ["q5_stronger_cells", "strengthening_interaction_cells", "median_abs_interaction_t"],
        ascending=False,
    )

    payload = {
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "holdout_start": HOLDOUT_START.isoformat(),
            "pairs": list(panels),
            "regimes": list(regime_builders),
            "primary_estimand": "negative full-range RSI(14) signed-return IC",
        },
        "quality_report": json.loads(quality_report.to_json(orient="records", date_format="iso")),
        "cutpoints": cutpoint_rows,
        "quintiles": json.loads(quintiles.to_json(orient="records")),
        "summaries": json.loads(summaries.to_json(orient="records")),
        "interactions": json.loads(interactions.to_json(orient="records")),
        "stability": json.loads(stability.to_json(orient="records")),
        "categorical": json.loads(categorical.to_json(orient="records")),
        "vei_time_interactions": json.loads(vei_time.to_json(orient="records")),
        "vei_direction_quintiles": json.loads(vei_direction.to_json(orient="records")),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\nPrimary VEI summary:")
    print(summaries.loc[summaries.regime.eq("vei_pct")].round(4).to_string(index=False))
    print("\nTop stability rows:")
    print(stability.head(20).round(4).to_string(index=False))
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
