"""Test HYP-0011: does a 15-minute stop-check cadence beat the 30-min decision-clock stop?

Motivation (exit_cadence.py screen, 2026-07-20): the continuous-stop finding only
ever compared the two extremes -- stop checked on the 30-min decision clock
("decision") vs every 1-min bar ("every_bar"). Filling in the intermediate
cadences showed a NON-MONOTONE interior optimum at ~15 min: on NQ it beats
every_bar on Sharpe AND net R AND t; on ES it lifts Sharpe +0.16 (a market where
every_bar was a wash) with gross/trade held flat. This runs the claim-matched
Null C on that interior optimum.

Single prespecified change on the working baseline (lookback 90, 30m RTH decision
clock, VWAP entry gate, band-or-VWAP `both` stop, next-open fills, explicit costs):

  baseline   exit_check="decision"  -> stop checked only at 30-min decision mfos
  treatment  exit_check=15          -> stop checked every 15 min (decision mfos + midpoints)

Both arms are the audited core.engine2 with stop_ref="both". The null mode reruns
band construction, BOTH arms, execution, costs, metrics, and the Sharpe-uplift
statistic on each corrected path-preserving Null C draw, then compares the
observed uplift to that null distribution (upper tail). One contrast, one uplift.

A looser/differently-clocked exit is a variance/selectivity amplifier until Null C
clears it (EXP-0010/0012 precedent): if the null reproduces the uplift, the 15-min
cadence is machinery (turnover/capacity lever), not exit information.

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0011_exit_cadence real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0011_exit_cadence real ES
  python -m futures.nq.noise_vwap.scripts.hyp_0011_exit_cadence null NQ 30
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
# (label, exit_check) — baseline first, treatment second
ARMS = (("decision", "decision"), ("cad15", 15))
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
TICK = {"NQ": 0.25, "ES": 0.25}
FEE_USD_PER_SIDE = 2.25


@dataclass(frozen=True)
class Score:
    label: str
    trades: int
    trades_per_year: float
    gross_r: float
    net_r: float
    net_r_per_trade: float
    hit: float
    sharpe: float
    day_t: float
    sharpe_usd: float
    day_t_usd: float
    recent_net_r: float
    recent_sharpe: float


def round_trip_cost_points(inst: str) -> float:
    per_side = FEE_USD_PER_SIDE / POINT_VALUE[inst] + 0.25 * TICK[inst]
    return 2.0 * per_side


def common_dates(bars: pd.DataFrame) -> np.ndarray:
    bands = S.noise_bands(bars, LOOKBACK)
    return np.sort(bands["sdate"].unique())


def run_candidate(bars: pd.DataFrame, exit_check,
                  fill_mode: str = "next_open") -> pd.DataFrame:
    bands = S.noise_bands(bars, LOOKBACK)
    decisions = S.decision_mfos(30, int(bars["mfo"].max()))
    return E.run(
        bars,
        bands,
        decisions,
        fill_mode=fill_mode,
        require_vwap=True,
        exit_check=exit_check,
        stop_ref="both",
    )


def score_candidate(trades: pd.DataFrame, bars: pd.DataFrame, dates: np.ndarray,
                    inst: str, label: str) -> Score:
    dates_idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(dates_idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    rt_cost = round_trip_cost_points(inst)
    t["gross_r"] = t["points"] / t["atr"]
    t["net_r"] = (t["points"] - rt_cost) / t["atr"]
    # dollar net per trade (the screen / es_continuous_stop metric): NOT ATR-scaled,
    # so it weights high-volatility eras more heavily (rule 19). Reported alongside
    # net-ATR-R to expose whether the cadence uplift is a vol-era normalization effect.
    t["net_usd"] = (t["points"] - rt_cost) * POINT_VALUE[inst]

    def day_stats(frame: pd.DataFrame, eligible: pd.Index,
                  col: str = "net_r") -> tuple[float, float, float]:
        day = frame.groupby("date")[col].sum().reindex(eligible, fill_value=0.0)
        sd = float(day.std(ddof=1))
        sharpe = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
        day_t = float(day.mean() / (sd / np.sqrt(len(day)))) if sd > 0 else 0.0
        return float(day.sum()), sharpe, day_t

    net_r, sharpe, day_t = day_stats(t, dates_idx)
    _, sharpe_usd, day_t_usd = day_stats(t, dates_idx, "net_usd")
    recent_dates = dates_idx[dates_idx >= pd.Timestamp("2023-01-01")]
    recent = t[t["date"] >= pd.Timestamp("2023-01-01")]
    recent_r, recent_sharpe, _ = day_stats(recent, recent_dates)
    years = max(len(dates_idx) / 252.0, 1.0 / 252.0)
    return Score(
        label=label,
        trades=len(t),
        trades_per_year=len(t) / years,
        gross_r=float(t["gross_r"].sum()),
        net_r=net_r,
        net_r_per_trade=float(t["net_r"].mean()) if len(t) else 0.0,
        hit=float((t["points"] > 0).mean()) if len(t) else 0.0,
        sharpe=sharpe,
        day_t=day_t,
        sharpe_usd=sharpe_usd,
        day_t_usd=day_t_usd,
        recent_net_r=recent_r,
        recent_sharpe=recent_sharpe,
    )


def evaluate_arms(bars: pd.DataFrame, inst: str) -> dict[str, Score]:
    dates = common_dates(bars)
    return {
        label: score_candidate(run_candidate(bars, ec), bars, dates, inst, label)
        for label, ec in ARMS
    }


def uplift(scores: dict[str, Score]) -> float:
    return scores["cad15"].sharpe - scores["decision"].sharpe


def uplift_usd(scores: dict[str, Score]) -> float:
    return scores["cad15"].sharpe_usd - scores["decision"].sharpe_usd


def print_arms(scores: dict[str, Score], inst: str) -> None:
    print(f"HYP-0011 15-min cadence vs 30-min decision-clock stop: {inst}")
    print("Common post-lb90 sample; lb90; 30m RTH + VWAP gate; both stop; next-open")
    print(
        f"{'arm':>9} {'n':>6} {'n/yr':>7} {'grossR':>9} {'netR':>9} "
        f"{'R/trade':>9} {'hit':>6} {'Sh':>6} {'day-t':>7} {'23+R':>9} {'23+Sh':>7}"
    )
    for label, _ in ARMS:
        s = scores[label]
        print(
            f"{label:>9} {s.trades:>6} {s.trades_per_year:>7.1f} "
            f"{s.gross_r:>+9.1f} {s.net_r:>+9.1f} {s.net_r_per_trade:>+9.4f} "
            f"{s.hit:>6.3f} {s.sharpe:>6.2f} {s.day_t:>+7.2f} "
            f"{s.recent_net_r:>+9.1f} {s.recent_sharpe:>7.2f}"
        )
    b, v = scores["decision"], scores["cad15"]
    print(
        f"Uplift (cad15 - decision): ATR-R dSharpe={v.sharpe-b.sharpe:+.3f} "
        f"(dNetR={v.net_r-b.net_r:+.1f}); "
        f"dollar dSharpe={v.sharpe_usd-b.sharpe_usd:+.3f}; "
        f"dRecentSh={v.recent_sharpe-b.recent_sharpe:+.3f}"
    )
    print("This is descriptive until the null mode passes the kill test.")


def run_null(inst: str, draws: int) -> None:
    bars = S.load_session(inst, "RTH")
    real = evaluate_arms(bars, inst)
    observed = uplift(real)
    observed_usd = uplift_usd(real)
    print_arms(real, inst)
    print(f"Real diffusivity={diffusivity(bars):.6f}")
    null_uplift: list[float] = []
    null_uplift_usd: list[float] = []
    for draw in range(draws):
        null_bars = _null_c_frame(bars, seed=5095349 + draw)
        null_scores = evaluate_arms(null_bars, inst)
        null_uplift.append(uplift(null_scores))
        null_uplift_usd.append(uplift_usd(null_scores))
        if draw == 0:
            print(f"Null draw 1 diffusivity={diffusivity(null_bars):.6f}")
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()

    def report(name: str, obs: float, arr: list[float]) -> float:
        a = np.asarray(arr)
        p = (1.0 + float((a >= obs).sum())) / (draws + 1.0)
        print(
            f"[{name}] real uplift dSharpe={obs:+.3f}; "
            f"null mean={a.mean():+.3f}, sd={a.std(ddof=1):.3f}, "
            f"p={p:.4f} ({int((a >= obs).sum())}/{draws} null >= real)"
        )
        return p

    p_r = report("ATR-R", observed, null_uplift)
    p_usd = report("dollar", observed_usd, null_uplift_usd)
    # Primary gate is the canonical ATR-R day-Sharpe (EXP-0010/0012 precedent):
    # +0.10 uplift, treatment net R >= baseline, and p<=0.05 vs Null C.
    passed = (
        observed >= 0.10
        and real["cad15"].net_r >= real["decision"].net_r
        and p_r <= 0.05
    )
    print("KILL TEST (ATR-R primary): PASS" if passed else "KILL TEST (ATR-R primary): REJECT")
    print(f"(dollar-metric Null C p={p_usd:.4f}, reported for the rule-19 cross-check)")


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


if __name__ == "__main__":
    main()
