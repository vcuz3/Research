"""Test HYP-0003: does an every-bar VWAP-touch exit beat the band-or-VWAP stop?

Single prespecified binary change on the working NQ baseline (lookback 90, 30m
RTH clock, VWAP entry gate, every-bar exit, next-open fills, explicit costs):

  baseline  stop_ref="both"  -> exit at max(band, vwap) long / min(band, vwap) short
  treatment stop_ref="vwap"  -> exit only when the close crosses VWAP (more room)

Both arms are the audited core.engine2. The null mode reruns band construction,
BOTH arms, execution, costs, metrics, and the uplift statistic on each corrected
path-preserving Null C draw, then compares the observed uplift to that null
distribution (upper tail). There is no family maximum: one contrast, one uplift.

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0003_vwap_touch_exit real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0003_vwap_touch_exit real ES
  python -m futures.nq.noise_vwap.scripts.hyp_0003_vwap_touch_exit null NQ 30
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
STOP_REFS = ("both", "vwap")  # baseline, treatment
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
TICK = {"NQ": 0.25, "ES": 0.25}
FEE_USD_PER_SIDE = 2.25


@dataclass(frozen=True)
class Score:
    stop_ref: str
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
    bands = S.noise_bands(bars, LOOKBACK)
    return np.sort(bands["sdate"].unique())


def run_candidate(bars: pd.DataFrame, stop_ref: str,
                  fill_mode: str = "next_open") -> pd.DataFrame:
    bands = S.noise_bands(bars, LOOKBACK)
    decisions = S.decision_mfos(30, int(bars["mfo"].max()))
    return E.run(
        bars,
        bands,
        decisions,
        fill_mode=fill_mode,
        require_vwap=True,
        exit_check="every_bar",
        stop_ref=stop_ref,
    )


def score_candidate(trades: pd.DataFrame, bars: pd.DataFrame, dates: np.ndarray,
                    inst: str, stop_ref: str) -> Score:
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
        stop_ref=stop_ref,
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


def evaluate_arms(bars: pd.DataFrame, inst: str) -> dict[str, Score]:
    dates = common_dates(bars)
    return {
        ref: score_candidate(run_candidate(bars, ref), bars, dates, inst, ref)
        for ref in STOP_REFS
    }


def uplift(scores: dict[str, Score]) -> float:
    return scores["vwap"].sharpe - scores["both"].sharpe


def print_arms(scores: dict[str, Score], inst: str) -> None:
    print(f"HYP-0003 VWAP-touch exit vs band-or-VWAP stop: {inst}")
    print("Common post-lb90 sample; lb90; 30m RTH + VWAP gate; every-bar; next-open")
    print(
        f"{'stop':>6} {'n':>6} {'n/yr':>7} {'grossR':>9} {'netR':>9} "
        f"{'R/trade':>9} {'Sh':>6} {'day-t':>7} {'23+R':>9} {'23+Sh':>7}"
    )
    for ref in STOP_REFS:
        s = scores[ref]
        print(
            f"{ref:>6} {s.trades:>6} {s.trades_per_year:>7.1f} "
            f"{s.gross_r:>+9.1f} {s.net_r:>+9.1f} {s.net_r_per_trade:>+9.4f} "
            f"{s.sharpe:>6.2f} {s.day_t:>+7.2f} "
            f"{s.recent_net_r:>+9.1f} {s.recent_sharpe:>7.2f}"
        )
    b, v = scores["both"], scores["vwap"]
    print(
        f"Uplift (vwap - both): dSharpe={v.sharpe-b.sharpe:+.3f}, "
        f"dNetR={v.net_r-b.net_r:+.1f}, dRecentSh={v.recent_sharpe-b.recent_sharpe:+.3f}"
    )
    print("This is descriptive until the null mode passes the kill test.")


def fill_sensitivity(bars: pd.DataFrame, inst: str) -> None:
    dates = common_dates(bars)
    honest = score_candidate(run_candidate(bars, "vwap"), bars, dates, inst, "vwap")
    aggressive = score_candidate(
        run_candidate(bars, "vwap", fill_mode="signal_close"), bars, dates, inst, "vwap"
    )
    print(
        f"Fill sensitivity (vwap arm): signal_close - next_open "
        f"dSharpe={aggressive.sharpe-honest.sharpe:+.3f}, "
        f"dNetR={aggressive.net_r-honest.net_r:+.1f}"
    )


def run_null(inst: str, draws: int) -> None:
    bars = S.load_session(inst, "RTH")
    real = evaluate_arms(bars, inst)
    observed = uplift(real)
    print_arms(real, inst)
    print(f"Real diffusivity={diffusivity(bars):.6f}")
    null_uplift: list[float] = []
    for draw in range(draws):
        null_bars = _null_c_frame(bars, seed=5095349 + draw)
        null_scores = evaluate_arms(null_bars, inst)
        null_uplift.append(uplift(null_scores))
        if draw == 0:
            print(f"Null draw 1 diffusivity={diffusivity(null_bars):.6f}")
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_uplift)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    print(
        f"Family-wise result: real uplift dSharpe={observed:+.3f}; "
        f"null uplift mean={a.mean():+.3f}, sd={a.std(ddof=1):.3f}, "
        f"p={p:.4f} ({int((a >= observed).sum())}/{draws} null uplifts >= real)"
    )
    passed = (
        observed >= 0.10
        and real["vwap"].net_r >= real["both"].net_r
        and p <= 0.05
    )
    print("KILL TEST: PASS" if passed else "KILL TEST: REJECT")


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
    scores = evaluate_arms(bars, args.instrument)
    print_arms(scores, args.instrument)
    fill_sensitivity(bars, args.instrument)


if __name__ == "__main__":
    main()
