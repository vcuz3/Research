"""HYP-0004 / EXP-0004 -- overnight dollar impulse, completed during RTH?

    python -u -m futures.nq.claude_exploration_1.scripts.s4_overnight_impulse

The dollar trades deeply through Asia and Europe; COMEX gold does not. A dollar move at
03:00 ET is therefore fully priced in FX but only partly in gold. The SHORTFALL
`beta_GC * on_dxy - on_GC` is how far gold still is from where the overnight dollar move
implies it should be, and the hypothesis is that New York liquidity completes it.

Structure of the evidence:
  * primary  -- IC(short_GC, rth_GC), sign declared POSITIVE in advance (KT1);
  * KT2      -- the unconstrained pair (on_GC, on_dxy), which spans the shortfall. If
                the raw overnight gap does all the work, this is ordinary gap reversal
                in a dollar costume;
  * KT3      -- ES/NQ, whose overnight books are far deeper. The liquidity mechanism
                predicts a WEAKER effect there, not an equal one;
  * mechanism -- first RTH hour versus the rest of the session. A completion story
                predicts the move is front-loaded.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core import features as F
from ..core import stats as S
from .build_panel import load

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0004"
INSTR = ("GC", "ES", "NQ")
NBOOT = 400
TICK = {"GC": (0.10, 10.0), "ES": (0.25, 12.50), "NQ": (0.25, 5.0)}


def ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    X = np.c_[np.ones(len(X)), X]
    return np.linalg.lstsq(X, y, rcond=None)[0]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260731)
    panel = load("4leg")
    o = F.overnight_frame(panel, instruments=INSTR).dropna(subset=["on_dxy"])
    L: list[str] = []
    P = L.append

    P("=" * 78)
    P("EXP-0004  HYP-0004  overnight dollar impulse under-reaction")
    P("=" * 78)
    P(f"sessions {len(o):,}   {o['date'].min().date()} -> {o['date'].max().date()}")
    P(f"gap_days: 1={int((o['gap_days'] == 1).sum())}  "
      f">1={int((o['gap_days'] > 1).sum())}   nboot={NBOOT}")
    P("declared in advance: primary market GC, expected sign POSITIVE")
    P("")

    # ---- how much of the overnight gap is dollar-explained at all? --------- #
    P("--- how much of the overnight gap is the dollar? (scale of the decomposition) ---")
    P(f"{'inst':<6}{'sd(on) bp':>12}{'sd(factor) bp':>15}{'sd(short) bp':>14}"
      f"{'corr(on,on_dxy)':>18}{'R^2 of factor':>15}")
    for i in INSTR:
        s = o.dropna(subset=[f"on_{i}", "on_dxy", f"factor_on_{i}"])
        c = float(np.corrcoef(s[f"on_{i}"], s["on_dxy"])[0, 1])
        r2 = 1 - s[f"short_{i}"].var() / s[f"on_{i}"].var()
        P(f"{i:<6}{1e4 * s[f'on_{i}'].std():>12.2f}"
          f"{1e4 * s[f'factor_on_{i}'].std():>15.2f}"
          f"{1e4 * s[f'short_{i}'].std():>14.2f}{c:>18.4f}{r2:>15.4f}")
    P("")

    # ---- PRIMARY (KT1) ----------------------------------------------------- #
    P("--- PRIMARY (KT1): IC of the overnight SHORTFALL against the RTH move ---")
    P("    positive = the unabsorbed dollar-implied move is completed during RTH")
    P(f"{'inst':<6}{'n':>7}  {'IC(short, rth)':<28}{'IC(short, rth 1st hr)':<28}"
      f"{'IC(short, rth rest)':<28}")
    for i in INSTR:
        s = o.dropna(subset=[f"short_{i}", f"rth_{i}", f"rth60_{i}", f"rthrest_{i}"])
        a = S.block_boot_ic(s, f"short_{i}", f"rth_{i}", rng, NBOOT)
        b = S.block_boot_ic(s, f"short_{i}", f"rth60_{i}", rng, NBOOT)
        c = S.block_boot_ic(s, f"short_{i}", f"rthrest_{i}", rng, NBOOT)
        P(f"{i:<6}{len(s):>7,}  {S.fmt_ci(a):<28}{S.fmt_ci(b):<28}{S.fmt_ci(c):<28}")
    P("")

    # ---- KT2: the degenerate pair ------------------------------------------ #
    P("--- KT2 (degenerate control): the two raw legs that SPAN the shortfall ---")
    P("    short = beta*on_dxy - on, so any information in `short` must appear")
    P("    in the unconstrained pair. If `on` alone does the work it is gap reversal.")
    P(f"{'inst':<6}{'n':>7}  {'IC(on_INST, rth)':<28}{'IC(on_dxy, rth)':<28}"
      f"{'IC(factor_on, rth)':<28}")
    for i in INSTR:
        s = o.dropna(subset=[f"on_{i}", "on_dxy", f"rth_{i}", f"factor_on_{i}"])
        a = S.block_boot_ic(s, f"on_{i}", f"rth_{i}", rng, NBOOT)
        b = S.block_boot_ic(s, "on_dxy", f"rth_{i}", rng, NBOOT)
        c = S.block_boot_ic(s, f"factor_on_{i}", f"rth_{i}", rng, NBOOT)
        P(f"{i:<6}{len(s):>7,}  {S.fmt_ci(a):<28}{S.fmt_ci(b):<28}{S.fmt_ci(c):<28}")
    P("")
    P("    unconstrained OLS  rth ~ a + b1*on_INST + b2*on_dxy   (block-bootstrap CI)")
    P("    mechanism requires b1 < 0 AND sign(b2) == sign(-beta_INST) i.e. b2 > 0")
    P(f"{'inst':<6}{'b1 (own gap)':<28}{'b2 (dollar gap)':<28}{'R^2':>8}"
      f"{'median beta':>13}")
    for i in INSTR:
        s = o.dropna(subset=[f"on_{i}", "on_dxy", f"rth_{i}"])
        X = s[[f"on_{i}", "on_dxy"]].to_numpy(float)
        y = s[f"rth_{i}"].to_numpy(float)
        bh = ols(y, X)
        res = y - np.c_[np.ones(len(X)), X] @ bh
        r2 = 1 - res.var() / y.var()
        bb = np.array([ols(y[k], X[k]) for k in
                       (rng.integers(0, len(y), len(y)) for _ in range(NBOOT))])
        c1 = (bh[1], *np.percentile(bb[:, 1], [5, 95]))
        c2 = (bh[2], *np.percentile(bb[:, 2], [5, 95]))
        P(f"{i:<6}{S.fmt_ci(c1):<28}{S.fmt_ci(c2):<28}{r2:>8.4f}"
          f"{o[f'beta_{i}'].median():>13.3f}")
    P("")

    # ---- weekend / era splits ---------------------------------------------- #
    P("--- splits of the primary IC(short, rth) ---")
    P(f"{'inst':<6}{'split':<16}{'n':>7}  {'IC':<28}")
    for i in INSTR:
        s = o.dropna(subset=[f"short_{i}", f"rth_{i}"])
        for nm, m in (("gap_days == 1", s["gap_days"] == 1),
                      ("gap_days > 1", s["gap_days"] > 1),
                      ("2011-2018", s["date"].dt.year <= 2018),
                      ("2019-2026", s["date"].dt.year >= 2019)):
            v = S.block_boot_ic(s[m], f"short_{i}", f"rth_{i}", rng, NBOOT)
            P(f"{i:<6}{nm:<16}{int(m.sum()):>7,}  {S.fmt_ci(v):<28}")
    P("")

    # ---- horizon-matched beta sensitivity ---------------------------------- #
    P("--- sensitivity: an OVERNIGHT-horizon beta instead of the RTH 1-min beta ---")
    P("    (regress overnight instrument gap on overnight dollar gap over the")
    P("     trailing 60 strictly prior sessions -- horizon-matched, still causal)")
    P(f"{'inst':<6}{'median beta_on':>16}{'median beta_rth':>17}  {'IC(short_on, rth)':<28}")
    for i in INSTR:
        x = o["on_dxy"].to_numpy(float)
        y = o[f"on_{i}"].to_numpy(float)
        xy = pd.Series(np.where(np.isfinite(x * y), x * y, np.nan)).shift(1) \
            .rolling(60, min_periods=40).sum()
        xx = pd.Series(np.where(np.isfinite(x * y), x * x, np.nan)).shift(1) \
            .rolling(60, min_periods=40).sum()
        b_on = (xy / xx).to_numpy(float)
        s = o.copy()
        s["beta_on"] = b_on
        s["short_on"] = b_on * s["on_dxy"] - s[f"on_{i}"]
        s = s.dropna(subset=["short_on", f"rth_{i}"])
        v = S.block_boot_ic(s, "short_on", f"rth_{i}", rng, NBOOT)
        P(f"{i:<6}{np.nanmedian(b_on):>16.3f}{o[f'beta_{i}'].median():>17.3f}  "
          f"{S.fmt_ci(v):<28}")
    P("")

    # ---- economic units ---------------------------------------------------- #
    P("--- economic size (rules 19/21): mean RTH move by shortfall quintile ---")
    for i in INSTR:
        s = o.dropna(subset=[f"short_{i}", f"rth_{i}"]).copy()
        s["q"] = pd.qcut(s[f"short_{i}"], 5, labels=False, duplicates="drop")
        m = s.groupby("q")[f"rth_{i}"].mean()

        def _sp(q, r):
            return float(np.nanmean(r[q == q.max()]) - np.nanmean(r[q == q.min()]))

        lo, hi = np.nanpercentile(
            S._block_boot(s, ["q", f"rth_{i}"], _sp, rng, NBOOT), [5, 95])
        sp = _sp(s["q"].to_numpy(float), s[f"rth_{i}"].to_numpy(float))
        px = float(np.exp(panel[f"lp_{i}"]).median())
        tick, dv = TICK[i]
        pts = sp * px
        P(f"  {i:<4} q1..q5 mean RTH move (bp): "
          + " ".join(f"{1e4 * v:+7.2f}" for v in m)
          + f"   | q5-q1 = {1e4 * sp:+7.2f} bp [{1e4 * lo:+6.2f},{1e4 * hi:+6.2f}] "
            f"= {pts / tick:+7.1f} ticks = ${pts / tick * dv:+9.2f}/contract")
    P("")

    txt = "\n".join(L)
    print(txt)
    (OUT / "overnight_impulse.txt").write_text(txt, encoding="utf-8")
    print(f"\nwrote {OUT / 'overnight_impulse.txt'}")


if __name__ == "__main__":
    main()
