"""Run frozen HYP-0001 on discovery data only (2012-2020)."""

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
    cfg_path = PROJECT / "baseline_replication" / "configs" / "hyp_0001.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    start, end = pd.Timestamp(cfg["start"]), pd.Timestamp(cfg["discovery_end"])
    assert end == pd.Timestamp("2021-01-01T00:00:00Z"), "EXP-0001 must not open 2021+."
    run_dir = PROJECT / "artifacts" / "runs" / args.experiment_id
    run_dir.mkdir(parents=True, exist_ok=True)
    all_trades, all_audit, quality = [], [], []
    for pair in cfg["pairs"]:
        path = WORKSPACE / "forex" / "data" / f"{pair.lower()}_intraday_1min.csv"
        print(f"Loading discovery data for {pair} ...", flush=True)
        raw, reached = load_discovery_minutes(path, start, end)
        assert raw.time.max() < end
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
        for target in cfg["targets"]:
            trades, audit = run_variant(raw, bars, eligible, pair, cfg["pip_size"][pair], target, cfg)
            all_trades.append(trades)
            all_audit.append(audit)
            print(f"  {target}: {len(trades):,} trades", flush=True)

    trades = pd.concat(all_trades, ignore_index=True)
    audit = pd.concat(all_audit, ignore_index=True)
    assert len(trades) and pd.to_datetime(trades.trading_date).max() < pd.Timestamp("2021-01-01")
    assert not trades.duplicated(["pair","target","trading_date","entry_slot"]).any()
    assert (trades.exit_slot >= trades.entry_slot).all() and trades.gross_pips.notna().all()
    summary = summarize(trades, audit, tuple(cfg["cost_pips"]))
    exits = exit_mix(trades)
    main_rows = summary.loc[(summary.target == "midpoint") & (summary.slice == "all") &
                            (summary.cost_pips == 0.5)]
    side_rows = summary.loc[(summary.target == "midpoint") & summary.slice.isin(["long","short"]) &
                            (summary.cost_pips == 0.0)]
    enough = bool((side_rows.trades >= 100).all())
    kill_pass = bool(len(main_rows) == len(cfg["pairs"]) and (main_rows.mean_net_pips > 0).all() and
                     (side_rows.mean_gross_pips > 0).all() and enough)
    verdict = "SURVIVES_INITIAL_KILL_TEST" if kill_pass else "REJECT_INITIAL_SPEC"

    trades.to_csv(run_dir / "trades.csv", index=False)
    audit.to_csv(run_dir / "daily_audit.csv", index=False)
    summary.to_csv(run_dir / "summary.csv", index=False)
    exits.to_csv(run_dir / "exit_mix.csv", index=False)
    (run_dir / "data_quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    payload = {"experiment_id":args.experiment_id, "verdict":verdict,
               "config_sha256":fingerprint(cfg_path), "discovery_end":str(end),
               "pairs":cfg["pairs"], "trades":len(trades),
               "midpoint_cost_0p5":main_rows.to_dict(orient="records"),
               "midpoint_side_gross":side_rows.to_dict(orient="records")}
    (run_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    state = audit.groupby(["target","pair"])[["entries","ignored_signals","ambiguous_signals","invalid_geometry"]].sum().reset_index()
    report = [f"{args.experiment_id} HYP-0001 discovery run", f"Verdict: {verdict}",
              "Scope: 2012-2020 only; 2021-2023 was not retained or scored.",
              "Prices: midpoint; costs are hypothetical round-trip pips.", "",
              "PRIMARY / CORE SUMMARY", summary.to_string(index=False), "", "EXIT MIX",
              exits.to_string(index=False), "", "SIGNAL/STATE AUDIT", state.to_string(index=False)]
    (run_dir / "report.txt").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report[:7]))
    print(f"Artifacts: {run_dir}")


if __name__ == "__main__":
    main()
