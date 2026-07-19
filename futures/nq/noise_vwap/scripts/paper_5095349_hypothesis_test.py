"""Test HYP-0001: do short causal noise lookbacks improve the working strategy?

This tester isolates one paper-derived change. It holds the audited engine,
30-minute RTH clock, VWAP gate, every-bar band/VWAP stop, costs, and next-open
execution fixed. Every candidate is scored on the common lookback-90 sample.

The null mode reruns band construction, every candidate, execution, costs,
metrics, and winner selection on each corrected path-preserving Null C draw.
The resulting maximum-statistic comparison is the family-wise test; individual
lookback cells are descriptive screens only.

Examples:
  python -m futures.nq.noise_vwap.scripts.paper_5095349_hypothesis_test real NQ
  python -m futures.nq.noise_vwap.scripts.paper_5095349_hypothesis_test real ES
  python -m futures.nq.noise_vwap.scripts.paper_5095349_hypothesis_test null NQ 100
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .studies import _null_c_frame, diffusivity


LOOKBACKS = (2, 4, 5, 8, 14, 30, 60, 90)
BASELINE_LOOKBACK = 90
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
TICK = {"NQ": 0.25, "ES": 0.25}
FEE_USD_PER_SIDE = 2.25


@dataclass(frozen=True)
class Score:
    lookback: int
    trades: int
    trades_per_year: float
    gross_r: float
    net_r: float
    net_r_per_trade: float
    sharpe: float
    day_t: float
    recent_net_r: float
    recent_sharpe: float


def round_trip_cost_points(inst: str) -> float:
    per_side = FEE_USD_PER_SIDE / POINT_VALUE[inst] + 0.25 * TICK[inst]
    return 2.0 * per_side


def common_dates(bars: pd.DataFrame) -> np.ndarray:
    """Use the baseline's eligible dates so short windows get no extra history."""
    bands = S.noise_bands(bars, BASELINE_LOOKBACK)
    return np.sort(bands["sdate"].unique())


def run_candidate(
    bars: pd.DataFrame,
    lookback: int,
    fill_mode: str = "next_open",
) -> pd.DataFrame:
    bands = S.noise_bands(bars, lookback)
    decisions = S.decision_mfos(30, int(bars["mfo"].max()))
    return E.run(
        bars,
        bands,
        decisions,
        fill_mode=fill_mode,
        require_vwap=True,
        exit_check="every_bar",
    )


def score_candidate(
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    dates: np.ndarray,
    inst: str,
    lookback: int,
) -> Score:
    dates_idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(dates_idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    rt_cost = round_trip_cost_points(inst)
    t["gross_r"] = t["points"] / t["atr"]
    t["net_r"] = (t["points"] - rt_cost) / t["atr"]

    def day_stats(frame: pd.DataFrame, eligible: pd.Index) -> tuple[float, float, float]:
        day = frame.groupby("date")["net_r"].sum().reindex(eligible, fill_value=0.0)
        sd = float(day.std(ddof=1))
        sharpe = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
        day_t = float(day.mean() / (sd / np.sqrt(len(day)))) if sd > 0 else 0.0
        return float(day.sum()), sharpe, day_t

    net_r, sharpe, day_t = day_stats(t, dates_idx)
    recent_dates = dates_idx[dates_idx >= pd.Timestamp("2023-01-01")]
    recent = t[t["date"] >= pd.Timestamp("2023-01-01")]
    recent_r, recent_sharpe, _ = day_stats(recent, recent_dates)
    years = max(len(dates_idx) / 252.0, 1.0 / 252.0)
    return Score(
        lookback=lookback,
        trades=len(t),
        trades_per_year=len(t) / years,
        gross_r=float(t["gross_r"].sum()),
        net_r=net_r,
        net_r_per_trade=float(t["net_r"].mean()) if len(t) else 0.0,
        sharpe=sharpe,
        day_t=day_t,
        recent_net_r=recent_r,
        recent_sharpe=recent_sharpe,
    )


def evaluate_family(bars: pd.DataFrame, inst: str) -> dict[int, Score]:
    dates = common_dates(bars)
    return {
        lb: score_candidate(run_candidate(bars, lb), bars, dates, inst, lb)
        for lb in LOOKBACKS
    }


def best_short(scores: dict[int, Score]) -> Score:
    return max(
        (score for lb, score in scores.items() if lb != BASELINE_LOOKBACK),
        key=lambda score: score.sharpe - scores[BASELINE_LOOKBACK].sharpe,
    )


def print_family(scores: dict[int, Score], inst: str) -> None:
    base = scores[BASELINE_LOOKBACK]
    print(f"HYP-0001 short-lookback family: {inst}")
    print("Common post-lb90 sample; 30m RTH + VWAP; every-bar stop; next-open fills")
    print(
        f"{'lb':>3} {'n':>6} {'n/yr':>7} {'grossR':>9} {'netR':>9} "
        f"{'R/trade':>9} {'Sh':>6} {'dSh':>7} {'day-t':>7} {'23+R':>9} {'23+Sh':>7}"
    )
    for lb in LOOKBACKS:
        s = scores[lb]
        print(
            f"{lb:>3} {s.trades:>6} {s.trades_per_year:>7.1f} "
            f"{s.gross_r:>+9.1f} {s.net_r:>+9.1f} {s.net_r_per_trade:>+9.4f} "
            f"{s.sharpe:>6.2f} {s.sharpe-base.sharpe:>+7.3f} {s.day_t:>+7.2f} "
            f"{s.recent_net_r:>+9.1f} {s.recent_sharpe:>7.2f}"
        )
    best = best_short(scores)
    print(
        f"Selected screen: lb={best.lookback}, dSharpe={best.sharpe-base.sharpe:+.3f}, "
        f"dNetR={best.net_r-base.net_r:+.1f}, "
        f"dRecentSh={best.recent_sharpe-base.recent_sharpe:+.3f}"
    )
    print("This is descriptive until the full-family null mode passes the kill test.")


def fill_sensitivity(bars: pd.DataFrame, inst: str, lookback: int) -> None:
    dates = common_dates(bars)
    honest = score_candidate(run_candidate(bars, lookback), bars, dates, inst, lookback)
    aggressive = score_candidate(
        run_candidate(bars, lookback, fill_mode="signal_close"),
        bars,
        dates,
        inst,
        lookback,
    )
    print(
        f"Fill sensitivity lb={lookback}: signal_close - next_open "
        f"dSharpe={aggressive.sharpe-honest.sharpe:+.3f}, "
        f"dNetR={aggressive.net_r-honest.net_r:+.1f}"
    )


def run_null(inst: str, draws: int) -> None:
    bars = S.load_session(inst, "RTH")
    real = evaluate_family(bars, inst)
    base = real[BASELINE_LOOKBACK]
    winner = best_short(real)
    observed = winner.sharpe - base.sharpe
    null_max: list[float] = []
    real_diff = diffusivity(bars)
    print_family(real, inst)
    print(f"Real diffusivity={real_diff:.6f}")
    for draw in range(draws):
        null_bars = _null_c_frame(bars, seed=5095349 + draw)
        null_scores = evaluate_family(null_bars, inst)
        null_base = null_scores[BASELINE_LOOKBACK]
        null_winner = best_short(null_scores)
        null_max.append(null_winner.sharpe - null_base.sharpe)
        if draw == 0:
            print(f"Null draw 1 diffusivity={diffusivity(null_bars):.6f}")
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_max)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    print(
        f"Family-wise result: real max dSharpe={observed:+.3f}; "
        f"null max mean={a.mean():+.3f}, sd={a.std(ddof=1):.3f}, "
        f"p={p:.4f} ({int((a >= observed).sum())}/{draws} null maxima >= real)"
    )
    passed = (
        observed >= 0.10
        and winner.net_r >= base.net_r
        and p <= 0.05
    )
    print("KILL TEST: PASS" if passed else "KILL TEST: REJECT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("real", "null"))
    parser.add_argument("instrument", choices=("NQ", "ES"), nargs="?", default="NQ")
    parser.add_argument("draws", type=int, nargs="?", default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "null":
        if args.draws < 20:
            raise SystemExit("Use at least 20 null draws; 100+ is recommended.")
        run_null(args.instrument, args.draws)
        return
    bars = S.load_session(args.instrument, "RTH")
    scores = evaluate_family(bars, args.instrument)
    print_family(scores, args.instrument)
    fill_sensitivity(bars, args.instrument, best_short(scores).lookback)


if __name__ == "__main__":
    main()
