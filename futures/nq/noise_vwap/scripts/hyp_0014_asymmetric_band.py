"""Test HYP-0014: recast the Noise Area as an ASYMMETRIC (per-side) band.

Transform 3 (anchor/symmetry) of the noise-area recast programme (cone -> quantile
-> asymmetric). Holds the working baseline fixed (lookback 90, 30-min RTH decision
clock, VWAP gate, every-bar band/VWAP stop, next-open fills, explicit costs) and
swaps ONLY the band construction: the baseline sizes BOTH edges from one symmetric
statistic sigma = mean(|move|) (`core.session.noise_bands`); the asymmetric band
sizes each edge from its own causal SEMI-mean (`core.bands.noise_bands_asymmetric`).

The trap this study is built to neutralize (same one that killed EXP-0010/0012/0021):
a "better band" that merely WIDENS or NARROWS the total width is a Sharpe-vs-capacity
dial, not alpha. The asymmetric band avoids it BY CONSTRUCTION: for every tilt the
total half-width budget is conserved (sig_up + sig_dn == 2*sigma), so the change is a
PURE up/down REDISTRIBUTION of the baseline width. tilt=0 is the baseline bit-exact;
tilt=1 is the full empirical split (sig_up=2*up, sig_dn=2*dn); tilt=1.5 over-tilts.
There is therefore no RAW-vs-MATCHED split needed here (unlike the quantile study):
every tilt is already width-matched.

Mechanism: on a drift-asymmetric index NQ up-days are larger and more frequent, so
the pooled mean(|move|) mis-sizes at least one edge (it over-widens the down edge with
up-day magnitudes and/or under-widens the up edge). Sizing each edge to its own
dispersion tests whether per-side selection improves entries.

Primary metric = zero-trade-day daily net-ATR-R Sharpe uplift of the best tilt over
the baseline, NQ primary + ES sibling. Null C runs ONLY if a tilt clears +0.10 Sharpe
uplift with net R >= baseline (standing rule; a wash/negative real pass is a REJECT).

Diagnostic: the per-side residual sig_up/sigma and sig_dn/sigma by decision slot shows
HOW asymmetric each slot's tape is and whether it varies by time of day (a morning
up-tilt would mirror the super-diffusive-open residual EXP-0020 found).

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0014_asymmetric_band real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0014_asymmetric_band real ES
  python -m futures.nq.noise_vwap.scripts.hyp_0014_asymmetric_band null NQ 30   # only if the gate passed
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from ..core import bands as B
from .studies import _null_c_frame, diffusivity
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, common_dates,
    LOOKBACK, PERIOD, UPLIFT_GATE,
)

TILT_GRID = (0.5, 1.0, 1.5)


def build(bars: pd.DataFrame, spec) -> pd.DataFrame:
    if spec == "baseline":
        return S.noise_bands(bars, LOOKBACK)
    _, tilt = spec
    return B.noise_bands_asymmetric(bars, LOOKBACK, tilt)


def run_spec(bars: pd.DataFrame, spec) -> pd.DataFrame:
    bands = build(bars, spec)
    decisions = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    return E.run(bars, bands, decisions, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar")


def evaluate(bars: pd.DataFrame, inst: str) -> dict:
    dates = common_dates(bars)
    out = {"baseline": score_candidate(run_spec(bars, "baseline"), bars, dates, inst,
                                       "mean(base)")}
    for t in TILT_GRID:
        out[("tilt", t)] = score_candidate(run_spec(bars, ("t", t)), bars, dates,
                                           inst, f"tilt {t:.1f}")
    return out


def best_tilt(scores: dict) -> tuple[float, Score]:
    base = scores["baseline"]
    cells = {t: scores[("tilt", t)] for t in TILT_GRID}
    t = max(cells, key=lambda k: cells[k].sharpe - base.sharpe)
    return t, cells[t]


def _row(sc: Score, base: Score) -> str:
    return (f"{sc.name:>11} {sc.trades:>6} {sc.gross_r:>+9.1f} {sc.net_r:>+9.1f} "
            f"{sc.net_pt_per_trade:>+9.3f} {sc.sharpe:>6.2f} {sc.sharpe-base.sharpe:>+7.3f} "
            f"{sc.max_dd:>7.1f} {sc.recent_sharpe:>7.2f}")


def residual_by_mfo(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-side residual sig_up/sigma and sig_dn/sigma at tilt=1 (the full empirical
    split), averaged over the common (date, slot). >1 = that edge is WIDER than the
    symmetric baseline, <1 = narrower. up>dn tells the up-side carries more of the
    move budget at that slot."""
    dm = set(S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    a = B.noise_bands_asymmetric(bars, LOOKBACK, 1.0)[["sdate", "mfo", "sigma",
                                                       "sig_up", "sig_dn"]]
    a = a[a["mfo"].isin(dm)]
    g = a.groupby("mfo").agg(sigma=("sigma", "mean"), sig_up=("sig_up", "mean"),
                             sig_dn=("sig_dn", "mean"))
    g["up/sig"] = g["sig_up"] / g["sigma"]
    g["dn/sig"] = g["sig_dn"] / g["sigma"]
    g["up/dn"] = g["sig_up"] / g["sig_dn"]
    return g


def print_report(scores: dict, bars: pd.DataFrame, inst: str) -> float:
    base = scores["baseline"]
    print(f"HYP-0014 asymmetric (per-side) band vs symmetric mean band: {inst}")
    print("Common post-lb90; lb90; 30m RTH clock + VWAP gate; every-bar stop; next-open")
    print("Total half-width conserved for every tilt (sig_up+sig_dn==2*sigma): "
          "pure up/down redistribution, NOT a width dial.")
    hdr = (f"{'band':>11} {'n':>6} {'grossR':>9} {'netR':>9} {'net_pt/t':>9} "
           f"{'Sh':>6} {'dSh':>7} {'maxDD':>7} {'23+Sh':>7}")
    print(hdr)
    print(_row(base, base))
    for t in TILT_GRID:
        print(_row(scores[("tilt", t)], base))

    bt, bsc = best_tilt(scores)
    up = bsc.sharpe - base.sharpe
    print(f"\nBest tilt: {bt:.1f}, dSharpe={up:+.3f}, "
          f"dNetR={bsc.net_r-base.net_r:+.1f}, dMaxDD={bsc.max_dd-base.max_dd:+.1f}, "
          f"dTrades={bsc.trades-base.trades:+d}")

    print("\nPer-side residual at tilt=1 (sig_up/sigma, sig_dn/sigma by decision slot) "
          "— how asymmetric is each slot's tape?")
    print(residual_by_mfo(bars).to_string(float_format=lambda x: f"{x:.4f}"))

    gate = (up >= UPLIFT_GATE) and (bsc.net_r >= base.net_r)
    print(f"\nGATE (best tilt dSharpe>=+{UPLIFT_GATE:.2f} and netR>=baseline): "
          f"{'PASS -> run Null C' if gate else 'FAIL -> REJECT from real evidence (no Null C)'}")
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
        null_up.append(best_tilt(ns)[1].sharpe - ns["baseline"].sharpe)
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_up)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    z = (observed - a.mean()) / a.std(ddof=1) if a.std(ddof=1) > 0 else float("nan")
    print(f"Null C (best tilt - baseline dSharpe): real={observed:+.3f}; "
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
