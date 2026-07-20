"""Test HYP-0012: recast the Noise Area as an analytic DIFFUSION CONE (√t).

Holds the working baseline fixed (lookback 90, 30-min RTH decision clock, VWAP
gate, every-bar band/VWAP stop, next-open fills, explicit costs) and swaps ONLY
the band construction: the empirical per-slot mean-|move| band
(`core.session.noise_bands`) vs the diffusion cone
(`core.bands.noise_bands_cone`), which replaces the 13 per-slot means with one
causal per-session vol scalar times a sqrt(mfo/M) profile. The cone is calibrated
to match the baseline's end-of-day width, so this isolates intraday SHAPE, not
width (width is a known Sharpe-vs-capacity dial).

Primary metric = zero-trade-day daily net-ATR-R Sharpe uplift of the cone over the
empirical baseline, on the common post-lookback sample, reported for NQ and ES.
Also reports:
  * the residual m(mfo) = mean_empirical_sigma / mean_cone_sigma per decision slot
    (a U-shape = genuine intraday vol seasonality the √t cone misses -> the target
    for transforms 2/3);
  * decision-point COVERAGE, baseline vs cone (the cone cannot incur the Rule-9a
    per-slot min_periods deletion).

Per the standing rule the drift-preserving Null C runs ONLY if the cone clears the
+0.10 Sharpe uplift AND net-R >= baseline gate (a wash/negative real pass is
already a REJECT). A near-WASH with equal/greater net R and improved coverage is a
distinct ADOPT-AS-SIMPLIFICATION outcome (robustness, not alpha).

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0012_diffusion_cone real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0012_diffusion_cone real ES
  python -m futures.nq.noise_vwap.scripts.hyp_0012_diffusion_cone null NQ 30   # only if the alpha gate passed
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from ..core import bands as B
from .studies import _null_c_frame, diffusivity


LOOKBACK = 90
PERIOD = 30
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
TICK = {"NQ": 0.25, "ES": 0.25}
FEE_USD_PER_SIDE = 2.25
UPLIFT_GATE = 0.10
SIMPLIFY_TOL = 0.05


@dataclass(frozen=True)
class Score:
    name: str
    trades: int
    gross_r: float
    net_r: float
    net_pt_per_trade: float
    sharpe: float
    day_t: float
    max_dd: float
    top_decile_r: float
    recent_sharpe: float


def round_trip_cost_points(inst: str) -> float:
    per_side = FEE_USD_PER_SIDE / POINT_VALUE[inst] + 0.25 * TICK[inst]
    return 2.0 * per_side


def make_bands(bars: pd.DataFrame, which: str) -> pd.DataFrame:
    if which == "baseline":
        return S.noise_bands(bars, LOOKBACK)
    if which == "cone":
        return B.noise_bands_cone(bars, LOOKBACK)
    raise ValueError(which)


def common_dates(bars: pd.DataFrame) -> np.ndarray:
    return np.sort(S.noise_bands(bars, LOOKBACK)["sdate"].unique())


def run_candidate(bars: pd.DataFrame, which: str) -> pd.DataFrame:
    bands = make_bands(bars, which)
    decisions = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    return E.run(bars, bands, decisions, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar")


def score_candidate(trades: pd.DataFrame, bars: pd.DataFrame, dates: np.ndarray,
                    inst: str, name: str) -> Score:
    dates_idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(dates_idx)].copy() if not trades.empty else trades.copy()
    atr = bars.groupby("sdate")["atr"].first()
    rt_cost = round_trip_cost_points(inst)
    if t.empty:
        return Score(name, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    t["gross_r"] = t["points"] / t["atr"]
    t["net_r"] = (t["points"] - rt_cost) / t["atr"]

    day = t.groupby("date")["net_r"].sum().reindex(dates_idx, fill_value=0.0)
    sd = float(day.std(ddof=1))
    sharpe = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    day_t = float(day.mean() / (sd / np.sqrt(len(day)))) if sd > 0 else 0.0
    equity = day.cumsum()
    max_dd = float((equity.cummax() - equity).max())

    recent_idx = dates_idx[dates_idx >= pd.Timestamp("2023-01-01")]
    rday = (t[t["date"] >= pd.Timestamp("2023-01-01")].groupby("date")["net_r"].sum()
            .reindex(recent_idx, fill_value=0.0))
    rsd = float(rday.std(ddof=1))
    recent_sharpe = float(rday.mean() / rsd * np.sqrt(252)) if rsd > 0 else 0.0

    return Score(name, len(t), float(t["gross_r"].sum()), float(day.sum()),
                 float((t["points"] - rt_cost).mean()), sharpe, day_t, max_dd,
                 float(t["gross_r"].quantile(0.90)), recent_sharpe)


def evaluate(bars: pd.DataFrame, inst: str) -> dict[str, Score]:
    dates = common_dates(bars)
    return {w: score_candidate(run_candidate(bars, w), bars, dates, inst, w)
            for w in ("baseline", "cone")}


def residual_table(bars: pd.DataFrame) -> pd.DataFrame:
    dm = set(S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    base = (S.noise_bands(bars, LOOKBACK)[["sdate", "mfo", "sigma"]]
            .rename(columns={"sigma": "emp"}))
    cone = (B.noise_bands_cone(bars, LOOKBACK)[["sdate", "mfo", "sigma"]]
            .rename(columns={"sigma": "cone"}))
    m = base.merge(cone, on=["sdate", "mfo"])
    m = m[m["mfo"].isin(dm)]
    g = m.groupby("mfo").agg(emp=("emp", "mean"), cone=("cone", "mean"),
                             n=("emp", "size"))
    g["ratio"] = g["emp"] / g["cone"]
    return g


def coverage(bars: pd.DataFrame) -> pd.DataFrame:
    dm = sorted(S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    base = S.noise_bands(bars, LOOKBACK)
    cone = B.noise_bands_cone(bars, LOOKBACK)
    bc = base[base["mfo"].isin(dm)].groupby("mfo").size()
    cc = cone[cone["mfo"].isin(dm)].groupby("mfo").size()
    out = pd.DataFrame({"baseline": bc, "cone": cc}).reindex(dm).fillna(0).astype(int)
    out["dropped_vs_cone"] = out["cone"] - out["baseline"]
    return out


def print_report(scores: dict[str, Score], bars: pd.DataFrame, inst: str) -> float:
    base, cone = scores["baseline"], scores["cone"]
    up = cone.sharpe - base.sharpe
    print(f"HYP-0012 diffusion cone vs empirical band: {inst}")
    print("Common post-lb90; lb90; 30m RTH decision clock + VWAP gate; "
          "every-bar stop; next-open fills")
    print(f"{'band':>9} {'n':>6} {'grossR':>9} {'netR':>9} {'net_pt/t':>9} "
          f"{'Sh':>6} {'dayT':>6} {'maxDD':>7} {'p90R':>6} {'23+Sh':>7}")
    for sc in (base, cone):
        print(f"{sc.name:>9} {sc.trades:>6} {sc.gross_r:>+9.1f} {sc.net_r:>+9.1f} "
              f"{sc.net_pt_per_trade:>+9.3f} {sc.sharpe:>6.2f} {sc.day_t:>6.2f} "
              f"{sc.max_dd:>7.1f} {sc.top_decile_r:>+6.2f} {sc.recent_sharpe:>7.2f}")
    print(f"CONE vs BASELINE: dSharpe={up:+.3f}, dNetR={cone.net_r-base.net_r:+.1f}, "
          f"dMaxDD={cone.max_dd-base.max_dd:+.1f}, dTrades={cone.trades-base.trades:+d}")

    print("\nResidual m(mfo) = mean_empirical_sigma / mean_cone_sigma (decision slots):")
    rt = residual_table(bars)
    print(rt.to_string(float_format=lambda x: f"{x:.4f}"))

    print("\nDecision-point coverage (baseline vs cone; dropped = Rule-9a deletions):")
    cov = coverage(bars)
    print(cov.to_string())
    tot_b, tot_c = int(cov["baseline"].sum()), int(cov["cone"].sum())
    print(f"total decision points: baseline={tot_b}  cone={tot_c}  "
          f"cone recovers {tot_c-tot_b} ({100*(tot_c-tot_b)/max(tot_c,1):.1f}% of cone)")

    alpha_gate = (up >= UPLIFT_GATE) and (cone.net_r >= base.net_r)
    simplify = (abs(up) <= SIMPLIFY_TOL and cone.net_r >= base.net_r - abs(base.net_r) * 0.02
                and tot_c >= tot_b)
    print(f"\nALPHA GATE (dSharpe>=+{UPLIFT_GATE:.2f} and netR>=baseline): "
          f"{'PASS -> run Null C' if alpha_gate else 'FAIL'}")
    print(f"SIMPLIFY OUTCOME (|dSharpe|<={SIMPLIFY_TOL:.2f}, netR~>=baseline, coverage>=): "
          f"{'YES -> cone is a robustness-preserving simplification' if simplify else 'no'}")
    if not alpha_gate and not simplify:
        print("VERDICT: REJECT from real evidence (no Null C).")
    return up


def run_null(inst: str, draws: int) -> None:
    bars = S.load_session(inst, "RTH")
    real = evaluate(bars, inst)
    observed = print_report(real, bars, inst)
    print(f"\nReal diffusivity={diffusivity(bars):.6f}")
    null_up: list[float] = []
    for draw in range(draws):
        nb = _null_c_frame(bars, seed=4824172 + draw)
        ns = evaluate(nb, inst)
        null_up.append(ns["cone"].sharpe - ns["baseline"].sharpe)
        if draw == 0:
            print(f"Null draw 1 diffusivity={diffusivity(nb):.6f}")
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_up)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    z = (observed - a.mean()) / a.std(ddof=1) if a.std(ddof=1) > 0 else float("nan")
    print(f"Null C (cone - baseline dSharpe): real={observed:+.3f}; "
          f"null mean={a.mean():+.3f} sd={a.std(ddof=1):.3f} center_sign="
          f"{'POS' if a.mean() > 0 else 'NEG'}; z={z:+.2f} p={p:.4f}")
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
    print_report(evaluate(bars, args.instrument), bars, args.instrument)


if __name__ == "__main__":
    main()
