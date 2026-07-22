"""Historical validation of SSRN-6650958 on GC treated as XAU/USD.

Primary comparison: calendar 2024, 1% current-equity risk per trade, 0.24R
round-trip cost. Full history is reported only as a robustness context.

Run:
  python -m futures.gc.vwap_ema.scripts.run_baseline [artifact_dir]
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

from ..core.data import load_15m, load_1s_index
from ..core.engine import run
from ..core import metrics as M
from ..strategy.events import add_2024_news_exclusion
from ..strategy.signals import add_signals, condition_funnel
from .data_quality import build_report

COST_R = 0.24
RISK_FRAC = 0.01


def assert_fills(trades: pd.DataFrame) -> None:
    lg = trades.side == 1; sh = trades.side == -1
    st = trades.reason == "stop"; tg = trades.reason == "target"
    assert not (((lg & st) & (trades.exit_px > trades.stop_px + 1e-9)).any()
                or ((sh & st) & (trades.exit_px < trades.stop_px - 1e-9)).any())
    assert not (((lg & tg) & (trades.exit_px < trades.target_px - 1e-9)).any()
                or ((sh & tg) & (trades.exit_px > trades.target_px + 1e-9)).any())
    assert np.allclose(trades.gross_R, trades.points / trades.risk_pts)


def _summary(trades: pd.DataFrame, dates, label: str) -> dict:
    contract = M.summarize_contract(trades, dates, COST_R, label=label)
    compound = M.summarize_compound(trades, dates, COST_R, RISK_FRAC, label=label)
    return {"contract": contract, "compound": compound}


def main(artifact_dir: str | None = None) -> None:
    bars = add_2024_news_exclusion(add_signals(load_15m()))
    s1s = load_1s_index()
    is2024 = pd.to_datetime(bars.date).dt.year.eq(2024)
    bars24 = bars[is2024].copy()
    # Indicators retain pre-2024 warmup, but the engine sees only 2024 trades.
    trades24 = run(bars24, s1s, cost_R=COST_R)
    trades_all = run(bars, s1s, cost_R=COST_R)
    assert_fills(trades24); assert_fills(trades_all)
    funnel24 = condition_funnel(bars24)
    dq = build_report(bars, s1s)
    results = {
        "assumptions": {"instrument_proxy": "GC treated as XAU/USD",
                        "risk_fraction": RISK_FRAC, "round_trip_cost_R": COST_R,
                        "primary_period": "2024-01-01/2024-12-31"},
        "primary_2024": _summary(trades24, bars24.date.drop_duplicates(), "2024"),
        "full_history_context": _summary(trades_all, bars.date.drop_duplicates(), "all"),
        "raw_signals_2024": int((bars24.sig_side != 0).sum()),
        "news_blocked_signal_entries_2024": int(sum(
            bool(bars24.iloc[j - 1].sig_side) and bool(bars24.iloc[j].entry_blocked)
            for j in range(1, len(bars24))
            if bars24.iloc[j].date == bars24.iloc[j - 1].date)),
        "completed_trades_2024": int(len(trades24)),
        "completed_trade_sessions_without_1s_2024": int(sum(
            np.datetime64(x, "ns") not in {np.datetime64(k, "ns") for k in s1s}
            for x in trades24.date)),
        "paper_synthetic_trade_count": 247,
        "data_quality": dq,
    }
    print(json.dumps(results, indent=2, default=str))
    print("\n2024 condition funnel\n", funnel24.to_string(index=False))
    if artifact_dir:
        out = Path(artifact_dir); out.mkdir(parents=True, exist_ok=True)
        trades24.to_parquet(out / "trades_2024.parquet", index=False)
        trades_all.to_parquet(out / "trades_full_history.parquet", index=False)
        funnel24.to_csv(out / "signal_funnel_2024.csv", index=False)
        (out / "summary.json").write_text(json.dumps(results, indent=2, default=str) + "\n",
                                          encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
