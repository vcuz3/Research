"""Test HYP-0006: does a fixed early-flat cutoff before the close help?

Holds the working baseline fixed (lookback 90, 30m RTH clock, VWAP gate, every-bar
band/VWAP stop, next-open fills, explicit costs) and forces the daily flat at
(16:00 ET - cutoff), also stopping new entries after the cutoff
(engine2.flat_before_close). Grid cutoff in {15, 30, 45, 60} minutes; baseline is
cutoff 0.

Primary metric = max-cell zero-trade-day daily net-ATR-R Sharpe uplift over the
cutoff-0 baseline. Reports top-decile winner-R (does early flat truncate the winner
tail?) and daily max drawdown. Per the standing rule, the Null C runs ONLY if a
cell clears the +0.10 uplift AND net R >= baseline gate.

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0006_early_flat real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0006_early_flat null NQ 30   # only if gate passed
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .studies import _null_c_frame, diffusivity


LOOKBACK = 90
CUTOFFS = (0, 15, 30, 45, 60)  # 0 = baseline
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
TICK = {"NQ": 0.25, "ES": 0.25}
FEE_USD_PER_SIDE = 2.25
UPLIFT_GATE = 0.10


@dataclass(frozen=True)
class Score:
    cutoff: int
    trades: int
    gross_r: float
    net_r: float
    net_r_per_trade: float
    sharpe: float
    day_t: float
    max_dd: float
    top_decile_r: float
    recent_sharpe: float


def round_trip_cost_points(inst: str) -> float:
    per_side = FEE_USD_PER_SIDE / POINT_VALUE[inst] + 0.25 * TICK[inst]
    return 2.0 * per_side


def common_dates(bars: pd.DataFrame) -> np.ndarray:
    return np.sort(S.noise_bands(bars, LOOKBACK)["sdate"].unique())


def run_candidate(bars: pd.DataFrame, cutoff: int) -> pd.DataFrame:
    bands = S.noise_bands(bars, LOOKBACK)
    decisions = S.decision_mfos(30, int(bars["mfo"].max()))
    return E.run(bars, bands, decisions, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar", flat_before_close=cutoff)


def score_candidate(trades: pd.DataFrame, bars: pd.DataFrame, dates: np.ndarray,
                    inst: str, cutoff: int) -> Score:
    dates_idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(dates_idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    rt_cost = round_trip_cost_points(inst)
    t["gross_r"] = t["points"] / t["atr"]
    t["net_r"] = (t["points"] - rt_cost) / t["atr"]

    day = t.groupby("date")["net_r"].sum().reindex(dates_idx, fill_value=0.0)
    sd = float(day.std(ddof=1))
    sharpe = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    day_t = float(day.mean() / (sd / np.sqrt(len(day)))) if sd > 0 else 0.0
    equity = day.cumsum()
    max_dd = float((equity.cummax() - equity).max())

    recent_idx = dates_idx[dates_idx >= pd.Timestamp("2023-01-01")]
    rday = t[t["date"] >= pd.Timestamp("2023-01-01")].groupby("date")["net_r"].sum().reindex(recent_idx, fill_value=0.0)
    rsd = float(rday.std(ddof=1))
    recent_sharpe = float(rday.mean() / rsd * np.sqrt(252)) if rsd > 0 else 0.0

    return Score(cutoff, len(t), float(t["gross_r"].sum()), float(day.sum()),
                 float(t["net_r"].mean()) if len(t) else 0.0, sharpe, day_t, max_dd,
                 float(t["gross_r"].quantile(0.90)) if len(t) else 0.0, recent_sharpe)


def evaluate_grid(bars: pd.DataFrame, inst: str) -> dict[int, Score]:
    dates = common_dates(bars)
    return {c: score_candidate(run_candidate(bars, c), bars, dates, inst, c) for c in CUTOFFS}


def best_cell(scores: dict[int, Score]) -> Score:
    base = scores[0]
    return max((sc for c, sc in scores.items() if c != 0),
               key=lambda sc: sc.sharpe - base.sharpe)


def print_grid(scores: dict[int, Score], inst: str) -> None:
    base = scores[0]
    print(f"HYP-0006 early-flat cutoff before close: {inst}")
    print("Common post-lb90; lb90; 30m RTH + VWAP gate; every-bar stop; next-open")
    print(f"{'cut':>4} {'n':>6} {'grossR':>9} {'netR':>9} {'R/trade':>9} "
          f"{'Sh':>6} {'dSh':>7} {'maxDD':>7} {'p90R':>6} {'23+Sh':>7}")
    for c in CUTOFFS:
        sc = scores[c]
        print(f"{c:>4} {sc.trades:>6} {sc.gross_r:>+9.1f} {sc.net_r:>+9.1f} "
              f"{sc.net_r_per_trade:>+9.4f} {sc.sharpe:>6.2f} {sc.sharpe-base.sharpe:>+7.3f} "
              f"{sc.max_dd:>7.1f} {sc.top_decile_r:>+6.2f} {sc.recent_sharpe:>7.2f}")
    b = best_cell(scores)
    up = b.sharpe - base.sharpe
    print(f"Best cell: cutoff={b.cutoff}, dSharpe={up:+.3f}, dNetR={b.net_r-base.net_r:+.1f}, "
          f"dMaxDD={b.max_dd-base.max_dd:+.1f}")
    gate = (up >= UPLIFT_GATE) and (b.net_r >= base.net_r)
    print(f"SUCCESS GATE (dSharpe>=+{UPLIFT_GATE:.2f} and netR>=baseline): "
          f"{'PASS -> run Null C' if gate else 'FAIL -> REJECT from real evidence, no Null C'}")


def run_null(inst: str, draws: int) -> None:
    bars = S.load_session(inst, "RTH")
    real = evaluate_grid(bars, inst)
    observed = best_cell(real).sharpe - real[0].sharpe
    print_grid(real, inst)
    print(f"Real diffusivity={diffusivity(bars):.6f}")
    null_max: list[float] = []
    for draw in range(draws):
        nb = _null_c_frame(bars, seed=5095349 + draw)
        ns = evaluate_grid(nb, inst)
        null_max.append(best_cell(ns).sharpe - ns[0].sharpe)
        if draw == 0:
            print(f"Null draw 1 diffusivity={diffusivity(nb):.6f}")
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_max)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    print(f"Family-wise: real max dSharpe={observed:+.3f}; null max mean={a.mean():+.3f}, "
          f"sd={a.std(ddof=1):.3f}, p={p:.4f}")
    print("KILL TEST: PASS" if (observed >= UPLIFT_GATE and p <= 0.05) else "KILL TEST: REJECT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("real", "null"))
    parser.add_argument("instrument", choices=("NQ", "ES"), nargs="?", default="NQ")
    parser.add_argument("draws", type=int, nargs="?", default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "null":
        if args.draws < 20:
            raise SystemExit("Use at least 20 null draws; 30+ is recommended.")
        run_null(args.instrument, args.draws)
        return
    bars = S.load_session(args.instrument, "RTH")
    print_grid(evaluate_grid(bars, args.instrument), args.instrument)


if __name__ == "__main__":
    main()
