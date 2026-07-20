"""Test HYP-0013: recast the Noise Area dispersion as a QUANTILE envelope.

Transform 2 of the noise-area recast programme. Holds the working baseline fixed
(lookback 90, 30-min RTH decision clock, VWAP gate, every-bar band/VWAP stop,
next-open fills, explicit costs) and swaps ONLY the per-slot dispersion statistic:
the baseline MEAN of |move| (`core.session.noise_bands`) vs the qth PERCENTILE
(`core.bands.noise_bands_quantile`).

The trap this study is built to avoid: raising q just WIDENS the band -> fewer,
more-extreme trades -> higher Sharpe / less money = the width/capacity dial that
killed EXP-0010/0012 and the k-multiplier WFO. So two views are reported:

  RAW      q-grid at scale 1.0  -> exposes the capacity dial (expected).
  MATCHED  each q rescaled by a fixed constant so its MEDIAN band width equals the
           mean band -> isolates the distribution-SHAPE effect (robustness to
           outlier trend days in the trailing window). This is the real test.

Because the quantile stays a per-slot rolling statistic, it PRESERVES the empirical
intraday shape (incl. the super-diffusive morning the diffusion cone missed,
EXP-0020) and matches the baseline coverage exactly.

Primary metric = zero-trade-day daily net-ATR-R Sharpe uplift of the best
MATCHED-width q cell over the mean baseline, NQ primary + ES sibling. Null C runs
only if a matched cell clears +0.10 Sharpe uplift with net R >= baseline.

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0013_quantile_band real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0013_quantile_band real ES
  python -m futures.nq.noise_vwap.scripts.hyp_0013_quantile_band null NQ 30   # only if the gate passed
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
    Score, score_candidate, common_dates, round_trip_cost_points,
    LOOKBACK, PERIOD, UPLIFT_GATE,
)

Q_GRID = (0.50, 0.65, 0.80, 0.90)


def matched_scale(bars: pd.DataFrame, q: float) -> float:
    """Fixed multiplier so the quantile band's MEDIAN sigma equals the mean band's,
    over the common (date, mfo). A study normalization (one constant, not a causal
    per-decision input) that isolates SHAPE from width."""
    base = S.noise_bands(bars, LOOKBACK)[["sdate", "mfo", "sigma"]]
    qb = B.noise_bands_quantile(bars, LOOKBACK, q, 1.0)[["sdate", "mfo", "sigma"]]
    m = base.merge(qb, on=["sdate", "mfo"], suffixes=("_b", "_q"))
    return float(m["sigma_b"].median() / m["sigma_q"].median())


def build(bars: pd.DataFrame, spec) -> pd.DataFrame:
    if spec == "baseline":
        return S.noise_bands(bars, LOOKBACK)
    _, q, scale = spec
    return B.noise_bands_quantile(bars, LOOKBACK, q, scale)


def run_spec(bars: pd.DataFrame, spec) -> pd.DataFrame:
    bands = build(bars, spec)
    decisions = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    return E.run(bars, bands, decisions, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar")


def evaluate(bars: pd.DataFrame, inst: str) -> dict:
    dates = common_dates(bars)
    scales = {q: matched_scale(bars, q) for q in Q_GRID}
    out = {"baseline": score_candidate(run_spec(bars, "baseline"), bars, dates, inst,
                                       "mean(base)")}
    for q in Q_GRID:
        out[("raw", q)] = score_candidate(run_spec(bars, ("q", q, 1.0)), bars, dates,
                                          inst, f"raw q{q:.2f}")
        out[("matched", q)] = score_candidate(
            run_spec(bars, ("q", q, scales[q])), bars, dates, inst, f"mat q{q:.2f}")
    out["_scales"] = scales
    return out


def best_matched(scores: dict) -> tuple[float, Score]:
    base = scores["baseline"]
    cells = {q: scores[("matched", q)] for q in Q_GRID}
    q = max(cells, key=lambda k: cells[k].sharpe - base.sharpe)
    return q, cells[q]


def _row(sc: Score, base: Score) -> str:
    return (f"{sc.name:>11} {sc.trades:>6} {sc.gross_r:>+9.1f} {sc.net_r:>+9.1f} "
            f"{sc.net_pt_per_trade:>+9.3f} {sc.sharpe:>6.2f} {sc.sharpe-base.sharpe:>+7.3f} "
            f"{sc.max_dd:>7.1f} {sc.recent_sharpe:>7.2f}")


def residual_by_mfo(bars: pd.DataFrame, q: float, scale: float) -> pd.DataFrame:
    dm = set(S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    base = (S.noise_bands(bars, LOOKBACK)[["sdate", "mfo", "sigma"]]
            .rename(columns={"sigma": "mean"}))
    qb = (B.noise_bands_quantile(bars, LOOKBACK, q, scale)[["sdate", "mfo", "sigma"]]
          .rename(columns={"sigma": "quant"}))
    m = base.merge(qb, on=["sdate", "mfo"])
    m = m[m["mfo"].isin(dm)]
    g = m.groupby("mfo").agg(mean=("mean", "mean"), quant=("quant", "mean"))
    g["quant/mean"] = g["quant"] / g["mean"]
    return g


def print_report(scores: dict, bars: pd.DataFrame, inst: str) -> float:
    base = scores["baseline"]
    scales = scores["_scales"]
    print(f"HYP-0013 quantile envelope vs mean band: {inst}")
    print("Common post-lb90; lb90; 30m RTH clock + VWAP gate; every-bar stop; next-open")
    hdr = (f"{'band':>11} {'n':>6} {'grossR':>9} {'netR':>9} {'net_pt/t':>9} "
           f"{'Sh':>6} {'dSh':>7} {'maxDD':>7} {'23+Sh':>7}")
    print("\n-- RAW quantile (scale 1.0; exposes the width/capacity dial) --")
    print(hdr)
    print(_row(base, base))
    for q in Q_GRID:
        print(_row(scores[("raw", q)], base))
    print("\n-- MATCHED width (median sigma == mean band; isolates SHAPE) --")
    print(f"matched scales: " + ", ".join(f"q{q:.2f}={scales[q]:.3f}" for q in Q_GRID))
    print(hdr)
    print(_row(base, base))
    for q in Q_GRID:
        print(_row(scores[("matched", q)], base))

    bq, bsc = best_matched(scores)
    up = bsc.sharpe - base.sharpe
    print(f"\nBest MATCHED cell: q={bq:.2f}, dSharpe={up:+.3f}, "
          f"dNetR={bsc.net_r-base.net_r:+.1f}, dMaxDD={bsc.max_dd-base.max_dd:+.1f}, "
          f"dTrades={bsc.trades-base.trades:+d}")

    print(f"\nResidual quant/mean by decision slot (best matched q={bq:.2f}) — "
          "does the quantile reshape the intraday profile?")
    print(residual_by_mfo(bars, bq, scales[bq]).to_string(
        float_format=lambda x: f"{x:.4f}"))

    gate = (up >= UPLIFT_GATE) and (bsc.net_r >= base.net_r)
    print(f"\nGATE (best matched dSharpe>=+{UPLIFT_GATE:.2f} and netR>=baseline): "
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
        null_up.append(best_matched(ns)[1].sharpe - ns["baseline"].sharpe)
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_up)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    z = (observed - a.mean()) / a.std(ddof=1) if a.std(ddof=1) > 0 else float("nan")
    print(f"Null C (best matched - baseline dSharpe): real={observed:+.3f}; "
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
