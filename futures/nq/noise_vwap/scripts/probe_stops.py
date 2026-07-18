"""
Residual-gap test: does continuous (every-bar) stop monitoring vs semi-hourly
close the standalone Sharpe/DD gap to Quantitativo? Also serves as a regression
check that the refactored engine reproduces the decision-mode numbers.

Faithful config: concretum clock + VWAP entry gate, lb90, 0.25tick, 3%/8x.
"""
from __future__ import annotations

from ..core.data import load_rth, noise_bands, TICK
from ..core.engine import run
from .forensic import sizing, per_trade_t, fees_pt, hl

CONC = [570 + k - 1 for k in range(30, 391, 30)]


def main():
    for inst in ("NQ", "ES"):
        bars = load_rth(inst); b90 = noise_bands(bars, 90)
        cost = fees_pt(inst) + 0.25 * TICK[inst]
        print(f"\n{inst}  (concretum + vwap gate, lb90, 0.25tick, 3%/8x)")
        for xc in ("decision", "every_bar"):
            tr = run(bars, b90, decision_tods=CONC, require_vwap=True, exit_check=xc)
            m = sizing(inst, bars, tr, cost); _, tt = per_trade_t(inst, tr, cost)
            rc = tr["reason"].value_counts().to_dict()
            print(f"  stop={xc:9s} net={m['pt_net']:>+6.3f}pt day$t={tt:>+5.2f} "
                  f"annVol={m['annvol']:>5.1%}  {hl(m)}  {rc}")
    print("\n  Quantitativo: ES 16.8%/1.25/-21% | NQ 24.3%/1.67/-24%")


if __name__ == "__main__":
    main()
