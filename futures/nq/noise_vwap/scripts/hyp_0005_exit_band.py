"""Test HYP-0005: does a narrower noise exit boundary + VWAP-sigma band beat the
band-or-VWAP stop?

Entries are the frozen working baseline (lookback 90, 30m RTH clock, VWAP gate,
next-open fills, explicit costs; entry noise band at multiplier 1.0). Only the
STOP changes to a separate, narrower exit boundary (paper 5095349 s.4.3/4.4):

  long  exit when close < max( ref_hi*(1 + s*sigma),  VWAP - y*sigma_vw )
  short exit when close > min( ref_lo*(1 - s*sigma),  VWAP + y*sigma_vw )

  * s in {0.5, 0.75}  scales the noise band narrower than the 1.0 entry band.
  * y in {0.5, 1.0} offsets a VWAP band by y volume-weighted stds; sigma_vw is the
    per-bar causal cumulative volume-weighted std of typical price about VWAP (same
    definition as core.vol_bands.vwap_sigma_bands). The VWAP leg sits BELOW VWAP for
    a long / ABOVE for a short (the "give the position more room" version, chosen by
    the user over the literal negative-y version which failed both markets).
  * baseline `both` is recovered at s=1.0, y=0.0.

Grid: (s, y) in {0.5,0.75} x {-0.5,-1.0} = 4 cells, plus the baseline. Primary
metric = max cell zero-trade-day daily net-ATR-R Sharpe uplift over baseline.
Per the standing rule, the Null C is run ONLY if a cell clears the +0.10 uplift
AND net R >= baseline gate; a failing real grid is already a REJECT.

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0005_exit_band real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0005_exit_band null NQ 30   # only if gate passed
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
S_GRID = (0.5, 0.75)
Y_GRID = (0.5, 1.0)  # positive -> VWAP band BELOW vwap for a long (looser / more room)
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
TICK = {"NQ": 0.25, "ES": 0.25}
FEE_USD_PER_SIDE = 2.25
UPLIFT_GATE = 0.10


@dataclass(frozen=True)
class Score:
    label: str
    trades: int
    gross_r: float
    net_r: float
    net_r_per_trade: float
    sharpe: float
    day_t: float
    recent_sharpe: float


def round_trip_cost_points(inst: str) -> float:
    per_side = FEE_USD_PER_SIDE / POINT_VALUE[inst] + 0.25 * TICK[inst]
    return 2.0 * per_side


def common_dates(bars: pd.DataFrame) -> np.ndarray:
    return np.sort(S.noise_bands(bars, LOOKBACK)["sdate"].unique())


def add_sig_vw(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-bar causal cumulative volume-weighted std of typical price about VWAP
    (matches core.vol_bands.vwap_sigma_bands). Recomputed on whatever frame is
    passed, so null draws get their own sigma_vw."""
    b = bars.sort_values(["sdate", "mfo"]).reset_index(drop=True)
    tp = ((b["high"] + b["low"] + b["close"]) / 3.0).to_numpy()
    v = b["volume"].astype("float64").to_numpy()
    cum_v = b.groupby("sdate", sort=False)["volume"].cumsum().astype("float64").to_numpy()
    cum_vtp2 = pd.Series(v * tp * tp, index=b.index).groupby(b["sdate"]).cumsum().to_numpy()
    vwap = b["vwap"].to_numpy()
    var = cum_vtp2 / cum_v - vwap * vwap
    b["sig_vw"] = np.sqrt(np.clip(var, 0.0, None))
    return b


def build_exit_bands(bands: pd.DataFrame, s: float) -> pd.DataFrame:
    """Narrower noise band: same reference, sigma scaled by s (< 1.0 = narrower)."""
    ex = bands.copy()
    hi_ref = np.maximum(ex["rth_open"], ex["prior_close"])
    lo_ref = np.minimum(ex["rth_open"], ex["prior_close"])
    ex["upper"] = hi_ref * (1.0 + s * ex["sigma"])
    ex["lower"] = lo_ref * (1.0 - s * ex["sigma"])
    return ex


def run_candidate(bars: pd.DataFrame, s: float | None, y: float,
                  fill_mode: str = "next_open") -> pd.DataFrame:
    bands = S.noise_bands(bars, LOOKBACK)
    decisions = S.decision_mfos(30, int(bars["mfo"].max()))
    kw = dict(fill_mode=fill_mode, require_vwap=True, exit_check="every_bar")
    if s is not None:  # exit-band cell (s=None -> baseline both stop)
        bars = add_sig_vw(bars)
        kw.update(exit_bands=build_exit_bands(bands, s), exit_y=y)
    return E.run(bars, bands, decisions, **kw)


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

    def day_stats(frame: pd.DataFrame, eligible: pd.Index) -> tuple[float, float, float]:
        day = frame.groupby("date")["net_r"].sum().reindex(eligible, fill_value=0.0)
        sd = float(day.std(ddof=1))
        sharpe = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
        day_t = float(day.mean() / (sd / np.sqrt(len(day)))) if sd > 0 else 0.0
        return float(day.sum()), sharpe, day_t

    net_r, sharpe, day_t = day_stats(t, dates_idx)
    recent = t[t["date"] >= pd.Timestamp("2023-01-01")]
    _, recent_sharpe, _ = day_stats(recent, dates_idx[dates_idx >= pd.Timestamp("2023-01-01")])
    return Score(label, len(t), float(t["gross_r"].sum()), net_r,
                 float(t["net_r"].mean()) if len(t) else 0.0, sharpe, day_t, recent_sharpe)


def cells():
    yield ("both", None, 0.0)
    for s in S_GRID:
        for y in Y_GRID:
            yield (f"s{s}_y{y}", s, y)


def evaluate_grid(bars: pd.DataFrame, inst: str) -> dict[str, Score]:
    dates = common_dates(bars)
    return {label: score_candidate(run_candidate(bars, s, y), bars, dates, inst, label)
            for (label, s, y) in cells()}


def best_cell(scores: dict[str, Score]) -> Score:
    base = scores["both"]
    return max((sc for lbl, sc in scores.items() if lbl != "both"),
               key=lambda sc: sc.sharpe - base.sharpe)


def print_grid(scores: dict[str, Score], inst: str) -> None:
    base = scores["both"]
    print(f"HYP-0005 narrower exit band + VWAP-sigma band: {inst}")
    print("Common post-lb90; lb90; 30m RTH + VWAP gate; next-open; entries unchanged")
    print(f"{'cell':>10} {'n':>6} {'grossR':>9} {'netR':>9} {'R/trade':>9} "
          f"{'Sh':>6} {'dSh':>7} {'day-t':>7} {'23+Sh':>7}")
    for label, _, _ in cells():
        sc = scores[label]
        print(f"{label:>10} {sc.trades:>6} {sc.gross_r:>+9.1f} {sc.net_r:>+9.1f} "
              f"{sc.net_r_per_trade:>+9.4f} {sc.sharpe:>6.2f} "
              f"{sc.sharpe-base.sharpe:>+7.3f} {sc.day_t:>+7.2f} {sc.recent_sharpe:>7.2f}")
    b = best_cell(scores)
    up = b.sharpe - base.sharpe
    print(f"Best cell: {b.label}, dSharpe={up:+.3f}, dNetR={b.net_r-base.net_r:+.1f}")
    gate = (up >= UPLIFT_GATE) and (b.net_r >= base.net_r)
    print(f"SUCCESS GATE (dSharpe>=+{UPLIFT_GATE:.2f} and netR>=baseline): "
          f"{'PASS -> run Null C' if gate else 'FAIL -> REJECT from real evidence, no Null C'}")


def run_null(inst: str, draws: int) -> None:
    bars = S.load_session(inst, "RTH")
    real = evaluate_grid(bars, inst)
    base = real["both"]
    observed = best_cell(real).sharpe - base.sharpe
    print_grid(real, inst)
    print(f"Real diffusivity={diffusivity(bars):.6f}")
    null_max: list[float] = []
    for draw in range(draws):
        nb = _null_c_frame(bars, seed=5095349 + draw)
        ns = evaluate_grid(nb, inst)
        null_max.append(best_cell(ns).sharpe - ns["both"].sharpe)
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
