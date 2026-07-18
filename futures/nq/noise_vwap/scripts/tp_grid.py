"""
Partial-TP GRID + FAMILY-WISE Null-C: is tp1.0_50 a stable optimum or a lucky cell?

Grid: tp_atr in {0.75, 1.0, 1.25} x tp_frac in {0.33, 0.5, 0.67} (9 cells), same
continuous_stop entries/exit-trail, only the partial take-profit differs. Two questions:

  1. SHAPE — is the real-tape Sharpe-uplift surface a PLATEAU around 1.0/0.50 (neighbours
     also positive => a real region) or an isolated SPIKE (=> a lucky cell)?
  2. FAMILY-WISE Null-C (rule 17 + the rule-18 max-|t| idea) — run the WHOLE grid on each
     path-preserving return-shuffle draw and keep the MAX Sharpe uplift across the 9 cells.
     The real best cell is only real if it beats the distribution of the null's BEST-OF-9,
     not just its own single-cell null. This is the honest multiple-testing threshold.

Metric is the user's: Sharpe (return-to-DD proxy) including zero-trade days; sumR reported
but secondary. R = net/ATR (rule 19), day is the unit (rule 22).

Run:  python -u -m futures.nq.noise_vwap.scripts.tp_grid real
      python -u -m futures.nq.noise_vwap.scripts.tp_grid null 30
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from .studies import get_session, INST, COST_025, _null_c_frame
from .wfo import add_pnl
from .wfo_data import enrich_trades, LOOKBACK
from .event_entry import score_ztd, tail_and_shape

TP_ATRS = [0.75, 1.0, 1.25]
TP_FRACS = [0.33, 0.5, 0.67]
CELLS = [(a, f) for a in TP_ATRS for f in TP_FRACS]


def lab(a, f):
    return f"tp{a:g}_{int(round(f * 100))}"


def _dayR(tr, all_dates):
    if tr.empty:
        return None
    return tr.groupby("date")["net_atr"].sum().reindex(all_dates, fill_value=0.0)


def _sr_sh(bars, bands, dm, all_dates, atr, a, f):
    tr = add_pnl(E.run(bars, bands, dm, exit_check="every_bar", tp_atr=a, tp_frac=f), atr)
    d = _dayR(tr, all_dates)
    if d is None:
        return 0.0, 0.0
    sd = d.std(ddof=1)
    return float(d.sum()), (float(d.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0)


def _prep():
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    all_dates = np.sort(bands["sdate"].unique())
    return bars, bands, dm, all_dates


def run_real():
    bars, bands, dm, all_dates = _prep()
    base = enrich_trades(bars, bands, E.run(bars, bands, dm, exit_check="every_bar"))
    b = score_ztd(base, all_dates); bsh = tail_and_shape(base)
    print("=== Partial-TP GRID (real tape) vs continuous_stop baseline ===")
    print(f"baseline: n={b['n']} sumR={b['sumR']:+.1f} Sharpe(ztd)={b['sharpe']:.3f} "
          f"win={bsh['win']*100:.1f}% avgLoser={bsh['avg_loser_pt']:+.2f}pt\n")

    cell = {}
    print(f"{'cell':<10s} {'n':>5s} {'win%':>5s} {'sumR':>7s} {'Sharpe':>7s} "
          f"{'dSharpe':>8s} {'dSumR':>7s} {'avgLos':>7s} {'winMFEcap':>9s}")
    for a, f in CELLS:
        df = enrich_trades(bars, bands, E.run(bars, bands, dm, exit_check="every_bar",
                                              tp_atr=a, tp_frac=f))
        s = score_ztd(df, all_dates); sh = tail_and_shape(df)
        cell[(a, f)] = s["sharpe"] - b["sharpe"]
        print(f"{lab(a,f):<10s} {s['n']:>5d} {sh['win']*100:>4.1f} {s['sumR']:>+7.1f} "
              f"{s['sharpe']:>7.3f} {s['sharpe']-b['sharpe']:>+8.3f} {s['sumR']-b['sumR']:>+7.1f} "
              f"{sh['avg_loser_pt']:>+7.2f} {sh['win_mfecap']:>+9.3f}")

    print("\ndSharpe SURFACE (rows tp_atr, cols tp_frac) — plateau vs spike:")
    print(f"  {'atr\\frac':>9s}" + "".join(f"{f:>9.2f}" for f in TP_FRACS))
    for a in TP_ATRS:
        print(f"  {a:>9.2f}" + "".join(f"{cell[(a,f)]:>+9.3f}" for f in TP_FRACS))
    best = max(CELLS, key=lambda k: cell[k])
    pos = sum(1 for k in CELLS if cell[k] > 0)
    print(f"\nbest cell = {lab(*best)} (dSharpe {cell[best]:+.3f}); "
          f"{pos}/9 cells positive. A plateau (best's neighbours also +) argues real; "
          f"an isolated spike argues lucky. Family-wise Null-C is the arbiter -> `null`.")


def run_null(ndraw=30):
    bars, bands, dm, all_dates = _prep()
    atr = bars.groupby("sdate")["atr"].first()
    b_sr0, b_sh0 = (lambda d: (float(d.sum()),
                    float(d.mean() / d.std(ddof=1) * np.sqrt(252))))(
        _dayR(add_pnl(E.run(bars, bands, dm, exit_check="every_bar"), atr), all_dates))
    real = {}
    for a, f in CELLS:
        sr, sh = _sr_sh(bars, bands, dm, all_dates, atr, a, f)
        real[(a, f)] = (sr - b_sr0, sh - b_sh0)
    best = max(CELLS, key=lambda k: real[k][1])
    print(f"=== Partial-TP GRID FAMILY-WISE Null-C ({ndraw} draws) ===")
    print(f"real best cell (by Sharpe uplift) = {lab(*best)}: dSharpe={real[best][1]:+.3f} "
          f"dSumR={real[best][0]:+.1f}\n")

    per = {k: [] for k in CELLS}       # per-cell null Sharpe uplift
    fam_max = []                        # per-draw MAX Sharpe uplift across the 9 cells
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=11000 + k)
        nbd = S.noise_bands(nb, LOOKBACK); natr = nb.groupby("sdate")["atr"].first()
        bsr, bsh = (lambda d: (float(d.sum()),
                    float(d.mean() / d.std(ddof=1) * np.sqrt(252))))(
            _dayR(add_pnl(E.run(nb, nbd, dm, exit_check="every_bar"), natr), all_dates))
        draw = {}
        for a, f in CELLS:
            _, sh = _sr_sh(nb, nbd, dm, all_dates, natr, a, f)
            draw[(a, f)] = sh - bsh
            per[(a, f)].append(sh - bsh)
        fam_max.append(max(draw.values()))
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()

    print("per-cell Sharpe uplift: real vs its OWN null (single-cell z):")
    print(f"  {'cell':<10s} {'real':>7s} {'nullMean':>9s} {'nullSD':>7s} {'z':>6s}")
    for a, f in CELLS:
        arr = np.array(per[(a, f)]); sd = arr.std(ddof=1)
        z = (real[(a, f)][1] - arr.mean()) / sd if sd > 0 else np.nan
        print(f"  {lab(a,f):<10s} {real[(a,f)][1]:>+7.3f} {arr.mean():>+9.3f} "
              f"{sd:>7.3f} {z:>+6.2f}")

    fam = np.array(fam_max)
    rb = real[best][1]
    p_fw = float((fam >= rb).mean())
    z_fw = (rb - fam.mean()) / fam.std(ddof=1) if fam.std(ddof=1) > 0 else np.nan
    print(f"\nFAMILY-WISE (the honest multiple-testing bar):")
    print(f"  null best-of-9 Sharpe uplift: mean={fam.mean():+.3f} sd={fam.std(ddof=1):.3f} "
          f"max={fam.max():+.3f}")
    print(f"  real best ({lab(*best)}) dSharpe={rb:+.3f}  ->  family-wise z={z_fw:+.2f}  "
          f"p={p_fw:.3f}  ({int(p_fw*ndraw)}/{ndraw} null draws' best beat it)")
    print("\nVERDICT: a stable optimum -> real best beats the null BEST-OF-9 (p<~0.05) AND "
          "the real surface is a plateau. A lucky cell -> real best ~ inside the null max dist.")


def run_boundary():
    """Extend past the winning corner (tighter TP, up to frac=1.0 = NO runner) to see
    whether the Sharpe plateau keeps rising and, crucially, what it costs the WINNER
    TAIL. frac=1.0 converts the trend-follower into a pure reversion scalp -- the tail
    (top-decile winners) is the thing that check protects."""
    bars, bands, dm, all_dates = _prep()
    base = enrich_trades(bars, bands, E.run(bars, bands, dm, exit_check="every_bar"))
    b = score_ztd(base, all_dates); bt = tail_and_shape(base)
    base_top = bt["top_sumR"]
    print("=== Partial-TP BOUNDARY probe (real): Sharpe vs WINNER-TAIL tradeoff ===")
    print(f"baseline Sharpe(ztd)={b['sharpe']:.3f} sumR={b['sumR']:+.1f} "
          f"tailR(top-decile)={base_top:+.1f} winMFEcap={bt['win_mfecap']:+.3f}\n")
    atrs = [0.5, 0.75, 1.0]; fracs = [0.5, 0.67, 0.83, 1.0]
    print(f"{'cell':<11s} {'Sharpe':>7s} {'dSharpe':>8s} {'sumR':>7s} {'dSumR':>7s} "
          f"{'tailR':>7s} {'tailReten':>9s} {'winMFEcap':>9s}")
    for a in atrs:
        for f in fracs:
            df = enrich_trades(bars, bands, E.run(bars, bands, dm, exit_check="every_bar",
                                                  tp_atr=a, tp_frac=f))
            s = score_ztd(df, all_dates); sh = tail_and_shape(df)
            tag = "  <- no runner" if f == 1.0 else ""
            print(f"{lab(a,f):<11s} {s['sharpe']:>7.3f} {s['sharpe']-b['sharpe']:>+8.3f} "
                  f"{s['sumR']:>+7.1f} {s['sumR']-b['sumR']:>+7.1f} {sh['top_sumR']:>+7.1f} "
                  f"{sh['top_sumR']/base_top:>8.0%} {sh['win_mfecap']:>+9.3f}{tag}")
    print("\nRead: Sharpe keeps rising toward tighter/larger-frac, but watch tailReten -- "
          "if it collapses the 'edge' is just abandoning the winner tail (reversion scalp), "
          "which vol-target sizing/leverage cannot buy back. Pick the point where Sharpe is "
          "up AND the tail is largely intact.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "real"
    if cmd == "real":
        run_real()
    elif cmd == "null":
        run_null(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif cmd == "boundary":
        run_boundary()
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
