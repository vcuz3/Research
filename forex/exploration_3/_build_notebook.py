"""Build the self-contained analysis notebook with the recorded EXP-0001 result."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
import hashlib
import json

import pandas as pd


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "anchored_twap_sma_zband_atr.ipynb"
RESULTS = ROOT / "artifacts" / "runs" / "EXP-0001"


def md(text: str) -> dict:
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "markdown",
        "id": hashlib.sha1(("m" + source).encode()).hexdigest()[:12],
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def code(text: str) -> dict:
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "code",
        "id": hashlib.sha1(("c" + source).encode()).hexdigest()[:12],
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


split = pd.read_csv(RESULTS / "split_metrics.csv").set_index("sample")
manifest = json.loads((RESULTS / "run_manifest.json").read_text(encoding="utf-8"))
oos = split.loc["oos_2021_2023"]
hold = split.loc["holdout_2024_latest"]
recorded = f"""
## Recorded material result (EXP-0001)

The pre-2020 search selected **{manifest['selected_config']['name']}**. The frozen
strategy failed the prespecified OOS kill test:

- 2021–2023: {int(oos.trades):,} trades, {oos.gross_mean_pips:.3f} gross pips/trade,
  {oos.net_mean_pips:.3f} net pips/trade, daily net-pip Sharpe {oos.daily_sharpe_net_pips:.3f}.
- 2024–{str(manifest['latest_data_timestamp'])[:10]}: {int(hold.trades):,} trades,
  {hold.gross_mean_pips:.3f} gross pips/trade, {hold.net_mean_pips:.3f} net pips/trade,
  daily net-pip Sharpe {hold.daily_sharpe_net_pips:.3f}.
- Verdict: **{manifest['verdict']}**.

The midpoint gross result is mildly positive in both later windows, but it is
smaller than the modeled 1-pip round-trip cost. This is cost-fragile descriptive
evidence, not a tradable edge.
"""


cells = [
    md(r"""
    # Anchored TWAP/SMA Z-band strategy — ATR-stop train/OOS/holdout test

    This notebook implements the user-clarified strategy on AUDUSD, EURUSD, GBPUSD,
    and NZDUSD. A completed 15-minute close arms beyond ±2.5 standard deviations,
    triggers after closing back inside, enters at the next observed complete
    15-minute open, and uses a frozen 2.0× Wilder ATR(14) stop with a symmetric 1R
    target. Stops and targets are replayed on underlying one-minute bars.

    The pasted pivot-stop / 2.0Z / 1.5ATR defaults are superseded by the user's
    clarification. The 2020 calendar year is intentionally unused between the
    pre-2020 training search and 2021–2023 OOS evaluation.
    """),
    md(recorded),
    md(r"""
    ## Research contract

    Only the anchor family is selected in training: session TWAP versus
    SMA(10/20/40/80). The 2.5Z arming threshold, 2ATR stop, 10-bar arm timeout,
    1R target, one-minute execution replay, and 1-pip baseline round-trip cost all
    remain fixed. The selected configuration is then evaluated without retuning.

    The historical 2024-latest window is consumed by this requested report. Only
    observations arriving after the local data endpoint are a clean new holdout.
    """),
    code(r"""
    from pathlib import Path
    import json
    import os
    import subprocess
    import sys

    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    from IPython.display import display

    sns.set_theme(style="whitegrid", context="notebook")
    pd.set_option("display.max_columns", 100)
    pd.set_option("display.width", 240)

    here = Path.cwd().resolve()
    PROJECT_ROOT = here if here.name == "exploration_3" else here / "forex" / "exploration_3"
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError("Run from the workspace root or forex/exploration_3")
    RESULT_DIR = PROJECT_ROOT / "artifacts" / "runs" / "EXP-0001"
    RUN_MATERIAL_RESEARCH = False  # set True to reproduce and overwrite EXP-0001 artifacts

    print("Project:", PROJECT_ROOT)
    print("Result directory:", RESULT_DIR)
    """),
    md(r"""
    ## 1. Execute engine invariants

    These fixtures test the corrected 2.5Z/2ATR parameters, strict Pine timeout,
    next-open entry, Wilder ATR seeding, one-minute entry-bar exits, stop-first
    ambiguity, gap-through fills, cost accounting, and non-overlap.
    """),
    code(r"""
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "backtest_engine/test_engine.py", "-q"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    print(test.stdout.strip())
    """),
    md(r"""
    ## 2. Optional full reproduction

    The checked-in artifacts are immutable evidence for this material run. Set
    `RUN_MATERIAL_RESEARCH=True` to rerun all four files. The runner fingerprints
    every input and rebuilds features, trades, metrics, and the review.
    """),
    code(r"""
    if RUN_MATERIAL_RESEARCH:
        subprocess.run(
            [sys.executable, "run_research.py", "--output-dir", str(RESULT_DIR)],
            cwd=PROJECT_ROOT, check=True,
        )
    assert (RESULT_DIR / "run_manifest.json").exists()
    manifest = json.loads((RESULT_DIR / "run_manifest.json").read_text(encoding="utf-8"))
    display(pd.Series(manifest["selected_config"], name="selected_config").to_frame())
    print("Latest local data:", manifest["latest_data_timestamp"])
    print("Recorded verdict:", manifest["verdict"])
    """),
    md(r"""
    ## 3. Data-quality gate

    The reports expose rows and gaps per period, duplicates, timestamp order,
    invalid OHLC, incomplete 15-minute intervals by UTC hour, and rolling/session
    feature underpopulation. Spot FX has no contract-roll boundaries.
    """),
    code(r"""
    dq = pd.read_csv(RESULT_DIR / "data_quality.csv")
    coarse = pd.read_csv(RESULT_DIR / "coarse_bar_coverage.csv")
    features = pd.read_csv(RESULT_DIR / "feature_coverage.csv")
    assert dq[["duplicate_ts", "out_of_order", "invalid_ohlc"]].to_numpy().sum() == 0
    assert coarse.complete_bars.le(coarse.observed_intervals).all()
    assert features.decision_ready.le(features.signal_bars).all()

    display(dq)
    display(
        coarse.groupby(["pair", "sample"], observed=True)
        .agg(observed_intervals=("observed_intervals", "sum"),
             complete_bars=("complete_bars", "sum"), raw_minutes=("raw_minutes", "sum"))
        .assign(complete_share=lambda x: x.complete_bars / x.observed_intervals)
        .round(5)
    )
    display(
        features.groupby(["pair", "sample"], observed=True)
        .agg(signal_bars=("signal_bars", "sum"), decision_ready=("decision_ready", "sum"),
             underpopulated_rows=("underpopulated_rows", "sum"))
        .assign(decision_ready_share=lambda x: x.decision_ready / x.signal_bars)
        .round(5)
    )
    """),
    md(r"""
    ## 4. Pre-2020 training search

    Ranking uses fixed-quantity portfolio daily net-pip Sharpe with portfolio
    session P&L summed across trades and pairs. Later windows never enter this
    ranking.
    """),
    code(r"""
    training = pd.read_csv(RESULT_DIR / "training_grid.csv")
    cols = ["name", "anchor_mode", "sma_length", "trades", "gross_mean_pips",
            "net_mean_pips", "daily_sharpe_net_pips", "positive_pairs", "selected"]
    display(training[cols].round(4))
    """),
    md(r"""
    ## 5. Frozen OOS and holdout results

    The clustered t-stat treats the per-trade mean as the estimand and clusters
    dependence by New-York FX session. Daily portfolio P&L is a sum, never a mean
    of that day's trades.
    """),
    code(r"""
    split = pd.read_csv(RESULT_DIR / "split_metrics.csv")
    pair_split = pd.read_csv(RESULT_DIR / "pair_split_metrics.csv")
    annual = pd.read_csv(RESULT_DIR / "annual_metrics.csv")
    headline = ["sample", "trades", "gross_mean_pips", "net_mean_pips", "gross_mean_r",
                "net_mean_r", "net_r_cluster_t", "daily_sharpe_net_pips",
                "daily_max_drawdown_pips", "ambiguous_1m_share", "gap_exit_share"]
    display(split[headline].round(4))
    display(pair_split[["sample", "pair", "trades", "gross_mean_pips", "net_mean_pips",
                        "net_r_cluster_t", "daily_sharpe_net_pips"]].round(4))
    display(annual[["year", "sample", "trades", "gross_mean_pips", "net_mean_pips",
                    "daily_sharpe_net_pips"]].round(4))
    """),
    md(r"""
    ## 6. Cost sensitivity and equity path

    Cost stress is shown only after causal fill checks. Because costs do not alter
    entries or exits in this fixed-quantity simulation, the same trades can be
    re-accounted at each round-trip cost.
    """),
    code(r"""
    stress = pd.read_csv(RESULT_DIR / "cost_stress.csv")
    equity = pd.read_csv(RESULT_DIR / "daily_equity.csv", parse_dates=["session_date"])

    fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
    for sample, group in stress.groupby("sample", observed=True):
        axes[0].plot(group.round_trip_cost_pips, group.net_mean_pips, marker="o", label=sample)
    axes[0].axhline(0, color="black", lw=1)
    axes[0].set(title="Mean P&L versus round-trip cost", xlabel="cost (pips)", ylabel="net pips/trade")
    axes[0].legend(fontsize=8)

    axes[1].plot(equity.session_date, equity.gross_cumulative_pips, label="gross")
    axes[1].plot(equity.session_date, equity.net_cumulative_pips, label="net @ 1 pip RT")
    axes[1].axvspan(pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01"), color="grey", alpha=0.15, label="unused 2020")
    axes[1].axvline(pd.Timestamp("2024-01-01"), color="black", ls="--", lw=1, label="holdout starts")
    axes[1].set(title="Fixed-quantity portfolio cumulative pips", xlabel="NY session", ylabel="pips")
    axes[1].legend(fontsize=8)
    plt.tight_layout()
    plt.show()
    display(stress[["round_trip_cost_pips", "sample", "net_mean_pips", "daily_sharpe_net_pips"]].round(4))
    """),
    md(r"""
    ## 7. Trade audit and final interpretation

    The assertions below recheck the most important temporal/accounting invariants
    on the material trade table. The stop/target geometry is symmetric 1R, so the
    gross result directly tests whether the re-entry signal wins more often than
    adverse gaps and forced end marks imply.
    """),
    code(r"""
    trades = pd.read_parquet(RESULT_DIR / "trades.parquet")
    trades["signal_time"] = pd.to_datetime(trades.signal_time)
    trades["entry_time"] = pd.to_datetime(trades.entry_time)
    trades["exit_time"] = pd.to_datetime(trades.exit_time)
    assert (trades.entry_time >= trades.signal_time).all()
    assert (trades.exit_time >= trades.entry_time).all()
    assert np.allclose(trades.net_pips, trades.gross_pips - trades.cost_pips)
    for _, group in trades.sort_values("entry_time").groupby("pair", observed=True):
        assert (group.entry_time.iloc[1:].to_numpy() >= group.exit_time.iloc[:-1].to_numpy()).all()

    display(trades.head())
    display(trades.groupby(["sample", "exit_reason"], observed=True).size().unstack(fill_value=0))
    print("Material verdict:", manifest["verdict"])
    print("Kill-test checks:", json.dumps(manifest["kill_test_checks"], indent=2))
    """),
    md(r"""
    ## Conclusion

    **NO-GO at the 1-pip round-trip baseline.** The later-period midpoint gross
    expectancy is only about 0.35 pips per trade, while modeled costs are 1 pip.
    Both OOS and holdout are negative net, and their clustered net-R statistics
    are negative. The strategy is therefore cost-dependent even before measured
    spread, slippage, financing, or a claim-matched null.

    The next defensible step is not more parameter search. It is quote-level spread
    measurement and a path-preserving null only if the user wants to investigate
    whether the small gross effect is real. Any new holdout must be future data
    after the recorded endpoint.
    """),
]


notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {OUT}")

