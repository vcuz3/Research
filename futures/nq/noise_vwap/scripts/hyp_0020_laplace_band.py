"""Test HYP-0020: recast the Noise Area as a LAPLACE recency-weighted band.

User thesis: the lb90 flat mean band beats shorter lookbacks (EXP-0025), but a flat
mean under-weights recent sessions, so recent regime changes are slow to register.
Instead of TRUNCATING history (the EXP-0025 short-history failure), keep a long
window but tilt the trailing per-slot average toward recent sessions with a Laplace
kernel over lag k=1..lookback:

    sigma[d,mfo] = ( Σ_k w_k · |move[d-k,mfo]| ) / Σ w_k,   w_k = exp(-|k-mu|/b)

Two shape knobs (per the user):
  * mu  = center-of-mass lag (which prior session gets peak weight); mu=1 = pure
          recency, mu>1 = "recent-ish but smooth over the noisiest latest session".
  * b   = decay scale, from half-life h (b = h/ln2). Larger h = slower decay =
          flatter = more history-like; b -> inf reduces EXACTLY to the flat lb90 mean.
The window is NOT an independent axis: it is DERIVED as lookback = clip(mu+5b, 90,
250) so slower decay automatically uses a longer lookback (the user's "slow decay
for long lookback"), floored at 90 so we never regress to pure short history and
capped at 250 for coverage. The b->inf, lookback=90 cell IS the deployed baseline.

The trap (EXP-0021): the tilt can also move band WIDTH, and width is a pure
Sharpe-vs-capacity dial. So two views are reported:
  RAW      each (mu,h) cell at scale 1.0        -> exposes the width dial.
  MATCHED  each cell rescaled so its MEDIAN band width == the flat baseline
           -> isolates the recency-tilt SHAPE. This is the real test.
Decisive diagnostic = residual laplace_sigma/flat_sigma by decision slot at matched
width; flat ~1.0 everywhere = the tilt carries no per-slot info (REJECT).

All cells scored on the SAME common post-max-lookback date set (so every cell,
including baseline, is defined on identical dates -> same-sample). Primary metric =
zero-trade-day daily net-ATR-R Sharpe uplift of the best MATCHED cell over the flat
baseline, NQ primary + ES sibling. Because this is a 2-D (mu,h) search, the Null C
uses the FAMILY-MAX statistic, and runs ONLY if a matched cell clears +0.10 Sharpe
uplift with net R >= baseline on the primary (standing gate rule).

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0020_laplace_band real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0020_laplace_band real ES
  python -m futures.nq.noise_vwap.scripts.hyp_0020_laplace_band null NQ 30   # only if the gate passed
"""
from __future__ import annotations

import argparse
import math

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from ..core import bands as B
from .studies import _null_c_frame, diffusivity
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, round_trip_cost_points,
    LOOKBACK, PERIOD, UPLIFT_GATE,
)

LN2 = math.log(2.0)
MU_GRID = (1, 5, 15, 30)          # center-of-mass lag (sessions ago)
HALFLIFE_GRID = (5, 15, 40)       # decay half-life in sessions -> b = h/ln2
LB_FLOOR, LB_CAP = 90, 250        # derived-lookback floor (never < baseline) and cap


def b_of(halflife: float) -> float:
    return halflife / LN2


def lookback_of(mu: int, halflife: float) -> int:
    """Derived window: reach mu+5b (weight<exp(-5)~0.7% beyond), floored at the
    baseline 90 (never pure short history) and capped at 250 (coverage)."""
    reach = math.ceil(mu + 5.0 * b_of(halflife))
    return int(min(LB_CAP, max(LB_FLOOR, reach)))


def max_lookback() -> int:
    return max(lookback_of(mu, h) for mu in MU_GRID for h in HALFLIFE_GRID)


def build(bars: pd.DataFrame, spec, scale: float = 1.0) -> pd.DataFrame:
    if spec == "baseline":
        return S.noise_bands(bars, LOOKBACK)
    _, mu, h = spec
    return B.noise_bands_laplace(bars, mu, b_of(h), lookback_of(mu, h), scale)


def run_spec(bars: pd.DataFrame, spec, scale: float = 1.0) -> pd.DataFrame:
    bands = build(bars, spec, scale)
    decisions = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    return E.run(bars, bands, decisions, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar")


def common_dates(bars: pd.DataFrame) -> np.ndarray:
    """Post-MAX-lookback dates: every cell (incl. baseline) is defined here, so all
    cells are scored on the identical sample (same-sample control)."""
    return np.sort(S.noise_bands(bars, max_lookback())["sdate"].unique())


def matched_scale(bars: pd.DataFrame, mu: int, h: float, dates: np.ndarray) -> float:
    """Fixed multiplier so the laplace band's MEDIAN sigma equals the flat baseline's
    over the common (date, decision-mfo) set -- isolates SHAPE from the width dial."""
    dm = set(S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    di = pd.Index(pd.to_datetime(dates))
    base = build(bars, "baseline")[["sdate", "mfo", "sigma"]]
    lap = build(bars, ("lap", mu, h))[["sdate", "mfo", "sigma"]]
    m = base.merge(lap, on=["sdate", "mfo"], suffixes=("_b", "_l"))
    m = m[m["mfo"].isin(dm) & m["sdate"].isin(di)]
    return float(m["sigma_b"].median() / m["sigma_l"].median())


def median_width(bars: pd.DataFrame, spec, scale, dates: np.ndarray) -> float:
    dm = set(S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    di = pd.Index(pd.to_datetime(dates))
    b = build(bars, spec, scale)
    b = b[b["mfo"].isin(dm) & b["sdate"].isin(di)]
    return float(b["sigma"].median())


def evaluate(bars: pd.DataFrame, inst: str) -> dict:
    dates = common_dates(bars)
    out: dict = {"_scale": {}, "_lb": {}}
    base_tr = run_spec(bars, "baseline")
    out["baseline"] = score_candidate(base_tr, bars, dates, inst, "flat lb90")
    out["_wbase"] = median_width(bars, "baseline", 1.0, dates)
    for mu in MU_GRID:
        for h in HALFLIFE_GRID:
            spec = ("lap", mu, h)
            sc = matched_scale(bars, mu, h, dates)
            out["_scale"][(mu, h)] = sc
            out["_lb"][(mu, h)] = lookback_of(mu, h)
            out[("raw", mu, h)] = score_candidate(
                run_spec(bars, spec, 1.0), bars, dates, inst, f"mu{mu} h{h}")
            out[("mat", mu, h)] = score_candidate(
                run_spec(bars, spec, sc), bars, dates, inst, f"mu{mu} h{h}")
    return out


def best_matched(scores: dict) -> tuple:
    base = scores["baseline"]
    cells = {(mu, h): scores[("mat", mu, h)] for mu in MU_GRID for h in HALFLIFE_GRID}
    k = max(cells, key=lambda kk: cells[kk].sharpe - base.sharpe)
    return k, cells[k]


def residual_by_mfo(bars: pd.DataFrame, mu: int, h: float, scale: float,
                    dates: np.ndarray) -> pd.DataFrame:
    dm = set(S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    di = pd.Index(pd.to_datetime(dates))
    base = build(bars, "baseline")[["sdate", "mfo", "sigma"]].rename(columns={"sigma": "flat"})
    lap = build(bars, ("lap", mu, h), scale)[["sdate", "mfo", "sigma"]].rename(columns={"sigma": "lap"})
    m = base.merge(lap, on=["sdate", "mfo"])
    m = m[m["mfo"].isin(dm) & m["sdate"].isin(di)]
    g = m.groupby("mfo").agg(flat=("flat", "mean"), lap=("lap", "mean"))
    g["lap/flat"] = g["lap"] / g["flat"]
    return g


def _row(sc: Score, base: Score, wratio: float, lb: int) -> str:
    return (f"{sc.name:>9} {lb:>4} {sc.trades:>6} {sc.net_pt_per_trade:>+9.3f} "
            f"{sc.sharpe:>6.2f} {sc.sharpe-base.sharpe:>+7.3f} {sc.net_r:>+8.1f} "
            f"{sc.max_dd:>7.1f} {sc.recent_sharpe:>7.2f} {wratio:>7.2f}")


def print_report(scores: dict, bars: pd.DataFrame, inst: str) -> float:
    base = scores["baseline"]
    wbase = scores["_wbase"]
    dates = common_dates(bars)
    print(f"HYP-0020 Laplace recency-weighted band vs flat lb90 mean band: {inst}")
    print(f"Common post-lb{max_lookback()} (same-sample); 30m RTH clock + VWAP gate; "
          "CONTINUOUS (every-bar) stop; next-open; cost-net ATR-R")
    print("net_pt/t = per-trade quality; wRatio = median band width vs baseline; "
          "lb = derived lookback")
    hdr = (f"{'cell':>9} {'lb':>4} {'n':>6} {'net_pt/t':>9} {'Sh':>6} {'dSh':>7} "
           f"{'netR':>8} {'maxDD':>7} {'23+Sh':>7} {'wRatio':>7}")

    print("\n-- RAW laplace (scale 1.0; exposes the width/capacity dial) --")
    print(hdr)
    print(_row(base, base, 1.0, LOOKBACK))
    for mu in MU_GRID:
        for h in HALFLIFE_GRID:
            k = ("raw", mu, h)
            wr = median_width(bars, ("lap", mu, h), 1.0, dates) / wbase
            print(_row(scores[k], base, wr, scores["_lb"][(mu, h)]))

    print("\n-- MATCHED width (median sigma == flat baseline; isolates recency SHAPE) --")
    print(hdr)
    print(_row(base, base, 1.0, LOOKBACK))
    for mu in MU_GRID:
        for h in HALFLIFE_GRID:
            k = ("mat", mu, h)
            print(_row(scores[k], base, 1.0, scores["_lb"][(mu, h)]))

    (bmu, bh), bsc = best_matched(scores)
    up = bsc.sharpe - base.sharpe
    print(f"\nBest MATCHED cell: mu={bmu}, h={bh} (b={b_of(bh):.1f}, lb={scores['_lb'][(bmu,bh)]}), "
          f"scale={scores['_scale'][(bmu,bh)]:.3f}; dSharpe={up:+.3f}, "
          f"dNetR={bsc.net_r-base.net_r:+.1f}, dGrossPt/t="
          f"{bsc.net_pt_per_trade-base.net_pt_per_trade:+.3f}, "
          f"dMaxDD={bsc.max_dd-base.max_dd:+.1f}, dTrades={bsc.trades-base.trades:+d}")

    print(f"\nResidual lap/flat by decision slot (best matched mu={bmu}, h={bh}) — "
          "does the recency tilt reshape the per-slot level?")
    print(residual_by_mfo(bars, bmu, bh, scores["_scale"][(bmu, bh)], dates).to_string(
        float_format=lambda x: f"{x:.4f}"))

    gate = (up >= UPLIFT_GATE) and (bsc.net_r >= base.net_r)
    print(f"\nGATE (best matched dSharpe>=+{UPLIFT_GATE:.2f} and netR>=baseline): "
          f"{'PASS -> run family-max Null C' if gate else 'FAIL -> REJECT from real evidence (no Null C)'}")
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
        null_up.append(best_matched(ns)[1].sharpe - ns["baseline"].sharpe)
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_up)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    z = (observed - a.mean()) / a.std(ddof=1) if a.std(ddof=1) > 0 else float("nan")
    print(f"Null C (family-max matched - baseline dSharpe): real={observed:+.3f}; "
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
