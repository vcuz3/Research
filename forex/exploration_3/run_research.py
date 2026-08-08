"""Run the frozen train/OOS/holdout TWAP/SMA Z-band research workflow."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import pandas as pd

from backtest_engine.engine import daily_portfolio, run_config, summarize_trades
from strategy.twap_zband import (
    HOLDOUT_START,
    OOS_START,
    PAIRS,
    TRAIN_END,
    StrategyConfig,
    active_arrays,
    baseline_candidates,
    build_signal_bars,
    load_raw_minutes,
    raw_data_quality,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT.parent / "data" / "clean"
SAMPLES = ("train_pre2020", "oos_2021_2023", "holdout_2024_latest")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feature_coverage(bars: pd.DataFrame, pair: str, config: StrategyConfig) -> pd.DataFrame:
    baseline, stdev, atr = active_arrays(bars, config)
    frame = bars[["sample", "utc_hour"]].copy()
    frame["baseline_defined"] = np.isfinite(baseline)
    frame["stdev_defined"] = np.isfinite(stdev) & (stdev > 0)
    frame["atr_defined"] = np.isfinite(atr) & (atr > 0)
    frame["decision_ready"] = frame[["baseline_defined", "stdev_defined", "atr_defined"]].all(axis=1)
    out = (
        frame.groupby(["sample", "utc_hour"], observed=True)
        .agg(
            signal_bars=("decision_ready", "size"),
            baseline_defined=("baseline_defined", "sum"),
            stdev_defined=("stdev_defined", "sum"),
            atr_defined=("atr_defined", "sum"),
            decision_ready=("decision_ready", "sum"),
        )
        .reset_index()
    )
    out.insert(0, "pair", pair)
    out["decision_ready_share"] = out.decision_ready / out.signal_bars
    out["underpopulated_rows"] = out.signal_bars - out.decision_ready
    out["underpopulation_policy"] = "no decision until full causal warm-up; session dispersion undefined on first session bar"
    return out


def session_sets(bars: pd.DataFrame) -> dict[str, set[str]]:
    return {
        sample: set(bars.loc[bars["sample"].eq(sample), "session_id"].astype(str).unique())
        for sample in bars["sample"].unique()
    }


def add_sets(target: dict[str, set[str]], source: dict[str, set[str]]) -> None:
    for key, values in source.items():
        target.setdefault(key, set()).update(values)


def train_search(configs: list[StrategyConfig], pairs: tuple[str, ...]) -> tuple[pd.DataFrame, StrategyConfig]:
    by_config: dict[str, list[pd.DataFrame]] = {cfg.name: [] for cfg in configs}
    by_config_pair: list[dict] = []
    sessions: set[str] = set()

    for pair in pairs:
        print(f"[train] loading {pair}", flush=True)
        raw = load_raw_minutes(pair, DATA_DIR, end=TRAIN_END)
        bars, _ = build_signal_bars(raw, configs)
        pair_sessions = set(bars.session_id.astype(str).unique())
        sessions.update(pair_sessions)
        for cfg in configs:
            trades = run_config(bars, raw, pair, cfg)
            if len(trades):
                trades = trades.loc[trades["sample"].eq("train_pre2020")].copy()
                by_config[cfg.name].append(trades)
            row = {"pair": pair, "config": cfg.name}
            row.update(summarize_trades(trades, pair_sessions))
            by_config_pair.append(row)
        del bars, raw

    rows = []
    for cfg in configs:
        frames = by_config[cfg.name]
        trades = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        row = asdict(cfg)
        row.update(summarize_trades(trades, sessions))
        positive_pairs = sum(
            1
            for r in by_config_pair
            if r["config"] == cfg.name and r.get("net_mean_pips", -np.inf) > 0
        )
        row["positive_pairs"] = positive_pairs
        rows.append(row)
    grid = pd.DataFrame(rows).sort_values(
        ["daily_sharpe_net_pips", "net_total_pips"], ascending=False, na_position="last"
    ).reset_index(drop=True)
    selected_name = str(grid.iloc[0]["name"])
    selected = next(c for c in configs if c.name == selected_name)
    grid["selected"] = grid.name.eq(selected.name)
    grid.attrs["pair_metrics"] = pd.DataFrame(by_config_pair)
    return grid, selected


def metrics_tables(
    trades: pd.DataFrame,
    sessions: dict[str, set[str]],
    pair_sessions: dict[str, dict[str, set[str]]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    split_rows = []
    pair_rows = []
    for sample in SAMPLES:
        subset = trades.loc[trades["sample"].eq(sample)]
        row = {"sample": sample}
        row.update(summarize_trades(subset, sessions.get(sample, set())))
        split_rows.append(row)
        for pair in sorted(pair_sessions):
            p = subset.loc[subset.pair.eq(pair)]
            prow = {"sample": sample, "pair": pair}
            prow.update(summarize_trades(p, pair_sessions[pair].get(sample, set())))
            pair_rows.append(prow)

    annual_rows = []
    trade_year = pd.to_datetime(trades.entry_time).dt.year
    for year in sorted(trade_year.unique()):
        subset = trades.loc[trade_year.eq(year)]
        year_sessions = {s for s in sessions.get(str(subset["sample"].iloc[0]), set()) if str(s).startswith(str(year))}
        row = {"year": int(year), "sample": str(subset["sample"].iloc[0])}
        row.update(summarize_trades(subset, year_sessions))
        annual_rows.append(row)
    return pd.DataFrame(split_rows), pd.DataFrame(pair_rows), pd.DataFrame(annual_rows)


def cost_stress_table(trades: pd.DataFrame, sessions: dict[str, set[str]]) -> pd.DataFrame:
    rows = []
    for cost in (0.0, 0.5, 1.0, 1.5, 2.0):
        stressed = trades.copy()
        stressed["cost_pips"] = cost
        stressed["net_pips"] = stressed.gross_pips - cost
        stressed["net_r"] = stressed.gross_r - cost / stressed.risk_pips
        for sample in SAMPLES:
            subset = stressed.loc[stressed["sample"].eq(sample)]
            row = {"round_trip_cost_pips": cost, "sample": sample}
            row.update(summarize_trades(subset, sessions.get(sample, set())))
            rows.append(row)
    return pd.DataFrame(rows)


def equity_table(trades: pd.DataFrame, sessions: dict[str, set[str]]) -> pd.DataFrame:
    all_sessions: set[str] = set()
    for values in sessions.values():
        all_sessions.update(values)
    net = daily_portfolio(trades, all_sessions, "net_pips")
    gross = daily_portfolio(trades, all_sessions, "gross_pips")
    out = pd.DataFrame({"gross_pips": gross, "net_pips": net}).reset_index()
    out["session_date"] = pd.to_datetime(out.entry_session)
    out["sample"] = np.select(
        [out.session_date < TRAIN_END, out.session_date < OOS_START, out.session_date < HOLDOUT_START],
        ["train_pre2020", "embargo_2020_unused", "oos_2021_2023"],
        default="holdout_2024_latest",
    )
    out["gross_cumulative_pips"] = out.gross_pips.cumsum()
    out["net_cumulative_pips"] = out.net_pips.cumsum()
    return out


def decide_verdict(split: pd.DataFrame, pair_split: pd.DataFrame) -> tuple[str, dict]:
    oos = split.set_index("sample").loc["oos_2021_2023"]
    hold = split.set_index("sample").loc["holdout_2024_latest"]
    oos_pairs = int(
        (pair_split.loc[pair_split["sample"].eq("oos_2021_2023"), "net_mean_pips"] > 0).sum()
    )
    hold_pairs = int(
        (pair_split.loc[pair_split["sample"].eq("holdout_2024_latest"), "net_mean_pips"] > 0).sum()
    )
    checks = {
        "oos_net_mean_pips_positive": bool(oos.net_mean_pips > 0),
        "oos_daily_sharpe_positive": bool(oos.daily_sharpe_net_pips > 0),
        "oos_positive_pairs_at_least_3": bool(oos_pairs >= 3),
        "holdout_net_mean_pips_positive": bool(hold.net_mean_pips > 0),
        "holdout_daily_sharpe_positive": bool(hold.daily_sharpe_net_pips > 0),
        "holdout_positive_pairs_at_least_3": bool(hold_pairs >= 3),
    }
    if not all(list(checks.values())[:3]):
        verdict = "NO_GO_OOS_KILL_TEST"
    elif not all(list(checks.values())[3:]):
        verdict = "NO_GO_HOLDOUT_CONFIRMATION"
    else:
        verdict = "PROVISIONAL_SURVIVOR_REQUIRES_NULL_AND_SPREAD_DATA"
    return verdict, checks


def write_review(
    path: Path,
    selected: StrategyConfig,
    split: pd.DataFrame,
    pair_split: pd.DataFrame,
    verdict: str,
    checks: dict,
    latest: pd.Timestamp,
) -> None:
    def metric(sample: str, col: str) -> float:
        return float(split.set_index("sample").loc[sample, col])

    text = f"""# EXP-0001 review: clarified ATR-stop Z-band strategy

## Frozen design

- User-confirmed arming threshold: **2.5 standard deviations**.
- User-confirmed stop: **2.0 x Wilder ATR(14)** from the actual next-bar entry.
- Target: 1.0R; arm timeout: 10 completed 15-minute bars.
- Training search: session TWAP versus SMA(10/20/40/80), with every risk parameter fixed.
- Selected on pre-2020 fixed-quantity daily net-pip Sharpe: **{selected.name}**.
- 2020 was unused as an embargo. OOS is 2021-2023. Historical holdout is 2024 through {latest.date()}.

## Prespecified kill test

The candidate fails if 2021-2023 has non-positive net mean pips, non-positive
daily net-pip Sharpe, or fewer than three of four pairs with positive net mean
pips. A proceed verdict also requires the same three checks in the historical
holdout. Baseline cost is 1.0 pip round trip.

Checks: `{json.dumps(checks, sort_keys=True)}`

## Result

- OOS: {int(metric('oos_2021_2023', 'trades')):,} trades, net mean
  {metric('oos_2021_2023', 'net_mean_pips'):.4f} pips,
  daily Sharpe {metric('oos_2021_2023', 'daily_sharpe_net_pips'):.3f},
  clustered net-R t {metric('oos_2021_2023', 'net_r_cluster_t'):.3f}.
- Holdout: {int(metric('holdout_2024_latest', 'trades')):,} trades, net mean
  {metric('holdout_2024_latest', 'net_mean_pips'):.4f} pips,
  daily Sharpe {metric('holdout_2024_latest', 'daily_sharpe_net_pips'):.3f},
  clustered net-R t {metric('holdout_2024_latest', 'net_r_cluster_t'):.3f}.
- Verdict: **{verdict}**.

## Interpretation limits

The source archive is midpoint OHLC without measured bid/ask quotes. The 1.0-pip
round-trip cost is a stress assumption, not a measured fill model. Stops and
targets are replayed on one-minute bars; same-minute dual touches are stop-first,
but one-minute ordering is still unresolved. This run performs a small training
search and consumes the requested historical holdout. It is not a clean future
holdout and no claim-matched path-preserving null has yet been run. Therefore a
survivor is research evidence only, not deployment evidence.
"""
    path.write_text(text, encoding="utf-8")


def run(output_dir: Path, smoke: bool = False) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    test_cmd = [sys.executable, "-m", "pytest", "backtest_engine/test_engine.py", "-q"]
    subprocess.run(test_cmd, cwd=PROJECT_ROOT, check=True)

    configs = baseline_candidates()
    pairs = ("EURUSD",) if smoke else PAIRS
    if smoke:
        # Smoke still checks the exact user-confirmed baseline and one alternative.
        configs = configs[:2]

    grid, selected = train_search(configs, pairs)
    grid.attrs.pop("pair_metrics", None)
    grid.to_csv(output_dir / "training_grid.csv", index=False)
    (output_dir / "selected_config.json").write_text(
        json.dumps(asdict(selected), indent=2, sort_keys=True), encoding="utf-8"
    )

    quality_frames = []
    coarse_frames = []
    feature_frames = []
    trade_frames = []
    sessions: dict[str, set[str]] = {}
    pair_sessions: dict[str, dict[str, set[str]]] = {}
    data_files = []
    latest = pd.Timestamp.min

    for pair in pairs:
        print(f"[full] loading {pair}", flush=True)
        raw = load_raw_minutes(pair, DATA_DIR)
        latest = max(latest, raw.ts_utc.max())
        quality_frames.append(raw_data_quality(raw, pair))
        bars, coarse = build_signal_bars(raw, [selected])
        coarse.insert(0, "pair", pair)
        coarse_frames.append(coarse)
        feature_frames.append(feature_coverage(bars, pair, selected))
        psets = session_sets(bars)
        pair_sessions[pair] = psets
        add_sets(sessions, psets)
        trades = run_config(bars, raw, pair, selected)
        trade_frames.append(trades)
        path = DATA_DIR / f"{pair}_1m_clean.parquet"
        data_files.append(
            {
                "pair": pair,
                "path": str(path.relative_to(PROJECT_ROOT.parent.parent)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "rows": int(len(raw)),
                "first_ts": str(raw.ts_utc.min()),
                "last_ts": str(raw.ts_utc.max()),
            }
        )
        del bars, raw

    # Smoke tables are structurally valid but are not the material result.
    trades = pd.concat(trade_frames, ignore_index=True)
    split, pair_split, annual = metrics_tables(trades, sessions, pair_sessions)
    stress = cost_stress_table(trades, sessions)
    equity = equity_table(trades, sessions)
    verdict, checks = decide_verdict(split, pair_split) if not smoke else ("SMOKE_ONLY", {})

    pd.concat(quality_frames, ignore_index=True).to_csv(output_dir / "data_quality.csv", index=False)
    pd.concat(coarse_frames, ignore_index=True).to_csv(output_dir / "coarse_bar_coverage.csv", index=False)
    pd.concat(feature_frames, ignore_index=True).to_csv(output_dir / "feature_coverage.csv", index=False)
    trades.to_parquet(output_dir / "trades.parquet", index=False)
    split.to_csv(output_dir / "split_metrics.csv", index=False)
    pair_split.to_csv(output_dir / "pair_split_metrics.csv", index=False)
    annual.to_csv(output_dir / "annual_metrics.csv", index=False)
    stress.to_csv(output_dir / "cost_stress.csv", index=False)
    equity.to_csv(output_dir / "daily_equity.csv", index=False)

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "smoke": smoke,
        "selected_config": asdict(selected),
        "selection_metric": "pre-2020 fixed-quantity portfolio daily net-pip Sharpe",
        "split_boundaries": {
            "train": "entry_time < 2020-01-01",
            "embargo_unused": "2020-01-01 <= entry_time < 2021-01-01",
            "oos": "2021-01-01 <= entry_time < 2024-01-01",
            "holdout": "entry_time >= 2024-01-01",
        },
        "latest_data_timestamp": str(latest),
        "verdict": verdict,
        "kill_test_checks": checks,
        "data_files": data_files,
        "test_command": "python -m pytest backtest_engine/test_engine.py -q",
        "run_command": f"python run_research.py --output-dir {output_dir}",
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_review(output_dir / "review.md", selected, split, pair_split, verdict, checks, latest)
    print(split.to_string(index=False), flush=True)
    print(f"Selected={selected.name}; verdict={verdict}", flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    run(args.output_dir.resolve(), args.smoke)


if __name__ == "__main__":
    main()
