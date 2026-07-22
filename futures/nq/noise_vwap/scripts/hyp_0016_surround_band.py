"""Test HYP-0016: SURROUND-SMOOTHED, short-history noise band.

User thesis: the baseline sigma[d,mfo] averages ONE thin same-time-of-day sample
(|move| at exactly `mfo`) over the prior 90 sessions -- a high-variance per-slot
estimator that forces a long, LAGGING history. Pooling the local minute
neighbourhood [mfo-w, mfo+w] on each prior day first drops the estimator variance,
so a SHORT (more adaptive) history becomes usable. Test whether the surround band
with a short history beats the current continuous-stop baseline (empirical per-slot
mean band, lookback 90).

Holds the working baseline fixed (30-min RTH decision clock, VWAP gate, every-bar
band/VWAP stop, next-open fills, explicit costs) and swaps ONLY the band
construction: `core.session.noise_bands(bars, 90)` vs
`core.bands.noise_bands_surround(bars, hist, w)` (center-included half-width w,
edge-truncated so the open averages forward-only; strictly-prior so causal).

Grid: surround half-width w in {5,14,30} x history hist in {5,14,30} (9 cells).
Also reports `plain(hist)` = noise_bands(bars, hist) (surround off, w=0) so the
SHORT-HISTORY effect is separated from the SURROUND-SMOOTHING effect, and the
median band-WIDTH ratio vs baseline so a Sharpe move that is really the
width/capacity dial (EXP-0021) is not mistaken for an edge.

All cells are scored on the SAME common post-lookback-90 date set as the baseline,
so the comparison is same-sample (the short-history cells' extra early history is
not scored -- the adaptivity benefit, if any, shows WITHIN the common sample).

Primary metric = zero-trade-day daily net-ATR-R Sharpe uplift of the best surround
cell over the lookback-90 mean baseline, NQ primary + ES sibling. Null C runs only
if the best cell clears +0.10 Sharpe uplift with net R >= baseline.

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0016_surround_band real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0016_surround_band real ES
  python -m futures.nq.noise_vwap.scripts.hyp_0016_surround_band null NQ 30   # only if the gate passed
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

W_GRID = (5, 14, 30)
HIST_GRID = (5, 14, 30)
SMOOTH_W = (5, 14, 30, 60)      # `smooth` mode: surround width at the FIXED lb90 history


def build(bars: pd.DataFrame, spec) -> pd.DataFrame:
    if spec == "baseline":
        return S.noise_bands(bars, LOOKBACK)
    kind = spec[0]
    if kind == "plain":                       # short-history mean band, no surround
        return S.noise_bands(bars, spec[1])
    _, hist, w = spec                         # surround-smoothed short-history band
    return B.noise_bands_surround(bars, hist, w)


def run_spec(bars: pd.DataFrame, spec) -> pd.DataFrame:
    bands = build(bars, spec)
    decisions = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    return E.run(bars, bands, decisions, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar")


def median_width(bars: pd.DataFrame, spec) -> float:
    """Median band sigma over the common (date, decision-mfo) set -- the capacity dial."""
    dm = set(S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    b = build(bars, spec)
    return float(b[b["mfo"].isin(dm)]["sigma"].median())


def win_rate(trades: pd.DataFrame, bars: pd.DataFrame, dates: np.ndarray,
             inst: str) -> float:
    """Fraction of trades with POSITIVE net (cost-of-round-trip) P&L, on the common
    date set -- the same trade population score_candidate scores."""
    dates_idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(dates_idx)].copy() if not trades.empty else trades
    if t.empty:
        return 0.0
    atr = bars.groupby("sdate")["atr"].first()
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    if t.empty:
        return 0.0
    net = t["points"] - round_trip_cost_points(inst)
    return float((net > 0).mean())


def evaluate(bars: pd.DataFrame, inst: str) -> dict:
    dates = common_dates(bars)
    out: dict = {"_width": {}, "_wr": {}}

    def add(k, spec, name):
        tr = run_spec(bars, spec)
        out[k] = score_candidate(tr, bars, dates, inst, name)
        out["_width"][k] = median_width(bars, spec)
        out["_wr"][k] = win_rate(tr, bars, dates, inst)

    add("baseline", "baseline", "base lb90")
    for hist in HIST_GRID:
        add(pspec_key(hist), ("plain", hist), f"plain h{hist}")
        for w in W_GRID:
            add(key(hist, w), ("surr", hist, w), f"h{hist} w{w}")
    return out


def key(hist: int, w: int) -> tuple:
    return ("surr", hist, w)


def pspec_key(hist: int) -> tuple:
    return ("plain", hist)


def best_cell(scores: dict) -> tuple:
    base = scores["baseline"]
    cells = {(h, w): scores[key(h, w)] for h in HIST_GRID for w in W_GRID}
    bk = max(cells, key=lambda k: cells[k].sharpe - base.sharpe)
    return bk, cells[bk]


def _row(sc: Score, base: Score, width: float, wbase: float, wr: float) -> str:
    return (f"{sc.name:>10} {sc.trades:>6} {sc.net_pt_per_trade:>+9.3f} "
            f"{100*wr:>6.1f} {sc.sharpe:>6.2f} {sc.sharpe-base.sharpe:>+7.3f} "
            f"{sc.net_r:>+8.1f} {sc.max_dd:>7.1f} {sc.recent_sharpe:>7.2f} "
            f"{width/wbase:>7.2f}")


def print_report(scores: dict, inst: str) -> float:
    base = scores["baseline"]
    wds = scores["_width"]
    wrs = scores["_wr"]
    wbase = wds["baseline"]
    print(f"HYP-0016 surround-smoothed short-history band vs lb90 mean band: {inst}")
    print("Common post-lb90; 30m RTH clock + VWAP gate; CONTINUOUS (every-bar) stop; "
          "next-open; cost-net ATR-R")
    print("net_pt/t = per-trade quality (net points/trade); win% = net-positive "
          "trades; wRatio = median band width vs baseline")
    hdr = (f"{'cell':>10} {'n':>6} {'net_pt/t':>9} {'win%':>6} {'Sh':>6} {'dSh':>7} "
           f"{'netR':>8} {'maxDD':>7} {'23+Sh':>7} {'wRatio':>7}")
    print(hdr)
    print(_row(base, base, wbase, wbase, wrs["baseline"]))
    for hist in HIST_GRID:
        pk = pspec_key(hist)
        print(_row(scores[pk], base, wds[pk], wbase, wrs[pk]))  # short-history, no surround
        for w in W_GRID:
            k = key(hist, w)
            print(_row(scores[k], base, wds[k], wbase, wrs[k]))

    bk, bsc = best_cell(scores)
    up = bsc.sharpe - base.sharpe
    print(f"\nBest SURROUND cell: hist={bk[0]}, w={bk[1]}; dSharpe={up:+.3f}, "
          f"dNetR={bsc.net_r-base.net_r:+.1f}, dGrossPt/t="
          f"{bsc.net_pt_per_trade-base.net_pt_per_trade:+.3f}, "
          f"dMaxDD={bsc.max_dd-base.max_dd:+.1f}, dTrades={bsc.trades-base.trades:+d}, "
          f"wRatio={wds[key(*bk)]/wbase:.2f}")

    gate = (up >= UPLIFT_GATE) and (bsc.net_r >= base.net_r)
    print(f"\nGATE (best surround dSharpe>=+{UPLIFT_GATE:.2f} and netR>=baseline): "
          f"{'PASS -> run Null C' if gate else 'FAIL -> REJECT from real evidence (no Null C)'}")
    return up


def evaluate_smooth(bars: pd.DataFrame, inst: str) -> dict:
    """Isolate the SURROUND-SMOOTHING effect at the FIXED baseline history (lb90):
    baseline (w=0) vs surround width w in SMOOTH_W, all at hist=90. Same date set,
    so the ONLY change vs baseline is candle-neighbourhood smoothing."""
    dates = common_dates(bars)
    out: dict = {"_width": {}, "_wr": {}}

    def add(k, spec, name):
        tr = run_spec(bars, spec)
        out[k] = score_candidate(tr, bars, dates, inst, name)
        out["_width"][k] = median_width(bars, spec)
        out["_wr"][k] = win_rate(tr, bars, dates, inst)

    add("baseline", "baseline", "base lb90")
    for w in SMOOTH_W:
        add(("surr", LOOKBACK, w), ("surr", LOOKBACK, w), f"lb90 w{w}")
    return out


def print_smooth(scores: dict, inst: str) -> None:
    base = scores["baseline"]
    wds, wrs, wbase = scores["_width"], scores["_wr"], scores["_width"]["baseline"]
    print(f"HYP-0016 surround SMOOTHING at fixed lb90 history: {inst}")
    print("Common post-lb90; 30m RTH clock + VWAP gate; CONTINUOUS (every-bar) stop; "
          "next-open; cost-net ATR-R")
    print("Only change vs baseline = candle-neighbourhood smoothing (w=0 IS baseline)")
    hdr = (f"{'cell':>10} {'n':>6} {'net_pt/t':>9} {'win%':>6} {'Sh':>6} {'dSh':>7} "
           f"{'netR':>8} {'maxDD':>7} {'23+Sh':>7} {'wRatio':>7}")
    print(hdr)
    print(_row(base, base, wbase, wbase, wrs["baseline"]))
    for w in SMOOTH_W:
        k = ("surr", LOOKBACK, w)
        print(_row(scores[k], base, wds[k], wbase, wrs[k]))


def run_null(inst: str, draws: int) -> None:
    bars = S.load_session(inst, "RTH")
    real = evaluate(bars, inst)
    observed = print_report(real, inst)
    print(f"\nReal diffusivity={diffusivity(bars):.6f}")
    null_up: list[float] = []
    for draw in range(draws):
        nb = _null_c_frame(bars, seed=4824172 + draw)
        ns = evaluate(nb, inst)
        null_up.append(best_cell(ns)[1].sharpe - ns["baseline"].sharpe)
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_up)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    z = (observed - a.mean()) / a.std(ddof=1) if a.std(ddof=1) > 0 else float("nan")
    print(f"Null C (best surround - baseline dSharpe): real={observed:+.3f}; "
          f"null mean={a.mean():+.3f} sd={a.std(ddof=1):.3f} center_sign="
          f"{'POS' if a.mean() > 0 else 'NEG'}; z={z:+.2f} p={p:.4f}")
    print("KILL TEST: PASS" if (observed >= UPLIFT_GATE and p <= 0.05) else "KILL TEST: REJECT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("real", "smooth", "null"))
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
    if args.mode == "smooth":
        print_smooth(evaluate_smooth(bars, args.instrument), args.instrument)
        return
    print_report(evaluate(bars, args.instrument), args.instrument)


if __name__ == "__main__":
    main()
