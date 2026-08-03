"""Run frozen HYP-0002 on the locked 2021-2023 strategy-validation era."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[1]
sys.path.insert(0, str(PROJECT))

from backtest_engine.engine import run_variant
from core.data import build_five_minute, eligible_days, load_discovery_minutes, quality_report
from core.metrics import exit_mix, summarize


def fingerprint(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    cfg_path = PROJECT / "baseline_replication" / "configs" / "hyp_0002.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    start, end = pd.Timestamp(cfg["validation_start"]), pd.Timestamp(cfg["validation_end"])
    assert start == pd.Timestamp("2021-01-01T00:00:00Z")
    assert end == pd.Timestamp("2024-01-01T00:00:00Z")
    run_dir = PROJECT / "artifacts" / "runs" / args.experiment_id
    run_dir.mkdir(parents=True, exist_ok=True)
    all_trades, all_audit, quality = [], [], []
    for pair in cfg["pairs"]:
        path = WORKSPACE / "forex" / "data" / f"{pair.lower()}_intraday_1min.csv"
        print(f"Loading locked-era data for {pair} ...", flush=True)
        raw, reached = load_discovery_minutes(path, start, end)
        assert raw.time.min() >= start and raw.time.max() < end
        q = quality_report(raw, path, reached)
        q["pair"] = pair
        q["sha256"] = fingerprint(path)
        eligible, _ = eligible_days(raw, cfg["min_session_coverage"])
        q["eligible_days"] = len(eligible)
        q["excluded_days"] = raw.trading_date.nunique() - len(eligible)
        bars = build_five_minute(raw, cfg["rsi_length"], cfg["atr_length"])
        q["complete_5m_bars"] = len(bars)
        q["rsi_available_bars"] = int(bars.rsi.notna().sum())
        q["atr_available_bars"] = int(bars.atr.notna().sum())
        quality.append(q)
        trades, audit = run_variant(raw, bars, eligible, pair, cfg["pip_size"][pair], "midpoint", cfg)
        all_trades.append(trades)
        all_audit.append(audit)
        print(f"  midpoint: {len(trades):,} trades", flush=True)

    trades = pd.concat(all_trades, ignore_index=True)
    audit = pd.concat(all_audit, ignore_index=True)
    dates = pd.to_datetime(trades.trading_date)
    assert len(trades) and dates.min() >= pd.Timestamp("2021-01-01") and dates.max() < pd.Timestamp("2024-01-01")
    assert trades.groupby(["pair","trading_date"]).size().max() == 1
    assert trades.entry_slot.between(425, 780).all()
    assert trades.signal_rsi.between(25, 75, inclusive="both").all()
    assert not trades.duplicated(["pair","trading_date"]).any()
    summary = summarize(trades, audit, tuple(cfg["cost_pips"]))
    exits = exit_mix(trades)
    trades["year"] = dates.dt.year.to_numpy()
    yearly = (trades.groupby(["pair","direction","year"])
              .agg(trades=("gross_pips","size"), gross_mean=("gross_pips","mean"),
                   gross_r_mean=("gross_r","mean"), target_rate=("exit_reason",lambda x:x.isin(["target","target_gap"]).mean()))
              .reset_index())
    yearly["net_0p5_mean"] = yearly.gross_mean - 0.5
    pair_primary = summary.loc[(summary.slice == "all") & (summary.cost_pips == 0.5)]
    side_primary = summary.loc[summary.slice.isin(["long","short"]) & (summary.cost_pips == 0.5)]
    required_count = len(cfg["pairs"]) * 2
    pass_test = bool(len(pair_primary) == len(cfg["pairs"]) and len(side_primary) == required_count and
                     (pair_primary.mean_net_pips > 0).all() and
                     (side_primary.mean_net_pips > 0).all() and (side_primary.trades >= 100).all())
    verdict = "PASS_LOCKED_ERA_KILL_TEST" if pass_test else "FAIL_LOCKED_ERA_KILL_TEST"

    trades.to_csv(run_dir / "trades.csv", index=False)
    audit.to_csv(run_dir / "daily_audit.csv", index=False)
    summary.to_csv(run_dir / "summary.csv", index=False)
    exits.to_csv(run_dir / "exit_mix.csv", index=False)
    yearly.to_csv(run_dir / "yearly.csv", index=False)
    (run_dir / "data_quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    state_cols = ["entries","ignored_signals","capped_signals","ambiguous_signals","invalid_geometry"]
    state = audit.groupby(["target","pair"])[state_cols].sum().reset_index()
    payload = {"experiment_id":args.experiment_id,"verdict":verdict,
               "config_sha256":fingerprint(cfg_path),"validation_start":str(start),"validation_end":str(end),
               "trades":len(trades),"pair_primary":pair_primary.to_dict(orient="records"),
               "side_primary":side_primary.to_dict(orient="records")}
    (run_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report = [f"{args.experiment_id} HYP-0002 locked-era run",f"Verdict: {verdict}",
              "Scope: 2021-2023 only; configuration frozen before run.",
              "This interval is strategy-specific locked evidence, not a pristine market holdout.","",
              "SUMMARY",summary.to_string(index=False),"","YEARLY",yearly.to_string(index=False),"",
              "EXIT MIX",exits.to_string(index=False),"","STATE AUDIT",state.to_string(index=False)]
    (run_dir / "report.txt").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report[:7]))
    print(f"Artifacts: {run_dir}")


if __name__ == "__main__":
    main()
