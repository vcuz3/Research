"""HYP-0001 / EXP-0001 -- dollar-decomposed residual momentum.

    python -u -m futures.nq.claude_exploration_1.scripts.s1_residual_momentum

Splits each instrument's trailing return into a dollar-explained leg
(`beta * past_dxy`) and an idiosyncratic residual, and asks which leg -- if either --
predicts the forward return. The paired within-slot IC delta of residual over raw is
the primary metric; the factor leg on its own is the degenerate control that decides
whether the split is doing any work at all.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core import features as F
from ..core import stats as S
from .build_panel import load

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0001"
INSTR = ("GC", "ES", "NQ")
WINS = (15, 30, 60)
HORIZONS = (10, 30, 60)
PRIMARY_W, PRIMARY_H, PRIMARY_I = 30, 30, "GC"
NBOOT = 400


def _common(d: pd.DataFrame, inst: str, W: int, H: int) -> pd.DataFrame:
    """One sample on which every arm is defined, so no arm wins by using more rows."""
    cols = [f"past_{inst}_{W}", f"resid_{inst}_{W}", f"factor_{inst}_{W}",
            f"fwd_{inst}_{H}", f"fwdresid_{inst}_{H}", "past_dxy_{}".format(W), "mfo"]
    return d.dropna(subset=cols)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260731)
    panel = load("4leg")
    d = F.decision_frame(panel, instruments=INSTR, past_wins=WINS, horizons=HORIZONS)
    L: list[str] = []
    P = L.append

    P("=" * 78)
    P("EXP-0001  HYP-0001  dollar-decomposed residual momentum")
    P("=" * 78)
    P(f"decision rows {len(d):,}   sessions {d['date'].nunique():,}   "
      f"slots {sorted(d['mfo'].unique())}")
    P(f"primary cell: {PRIMARY_I}  W={PRIMARY_W}  H={PRIMARY_H}   nboot={NBOOT}")
    P("")

    # ---- rule-23 identity: beta=0 must reproduce the raw baseline exactly ----
    z = d[f"past_{PRIMARY_I}_{PRIMARY_W}"] - 0.0 * d[f"past_dxy_{PRIMARY_W}"]
    ident = float(np.nanmax(np.abs(z - d[f"past_{PRIMARY_I}_{PRIMARY_W}"])))
    P(f"[identity] beta=0 reproduces raw momentum exactly: max|diff|={ident:.3e}")
    dec = d[["date", "mfo"]].copy()
    for i in INSTR:
        rec = d[f"resid_{i}_30"] + d[f"factor_{i}_30"]
        P(f"[identity] resid_{i}_30 + factor_{i}_30 == past_{i}_30 : "
          f"max|diff|={float(np.nanmax(np.abs(rec - d[f'past_{i}_30']))):.3e}")
    P("")

    # ---- betas ----
    P("--- causal dollar beta (20 strictly prior sessions, through the origin) ---")
    P(f"{'inst':<6}{'median':>10}{'p10':>10}{'p90':>10}{'sd':>10}"
      f"{'contemp corr 30m':>19}")
    for i in INSTR:
        b = d[f"beta_{i}"]
        m = d[[f"past_dxy_30", f"past_{i}_30"]].dropna()
        cc = float(np.corrcoef(m.iloc[:, 0], m.iloc[:, 1])[0, 1])
        P(f"{i:<6}{b.median():>10.3f}{b.quantile(.1):>10.3f}{b.quantile(.9):>10.3f}"
          f"{b.std():>10.3f}{cc:>19.4f}")
    P("")

    # ---- ARTIFACT CONTROL 1: the shared endpoint ------------------------- #
    # `past` ends and `fwd` starts at the same close, so measurement error in that one
    # price induces mechanical negative correlation. `pastlag` ends one bar earlier and
    # shares no price with the forward window. Run this BEFORE interpreting any
    # reversal, because a bid-ask-bounce artifact looks exactly like mean reversion.
    P("--- ARTIFACT CONTROL: shared-endpoint (bid-ask bounce) ---")
    P("    `past` shares the close at m with `fwd`; `pastlag` ends at m-1 and shares")
    P("    no price. A reversal that survives the lag is a property of the tape.")
    P(f"{'inst':<6}{'n':>8}  {'IC(past, fwd)':<26}{'IC(pastlag, fwd)':<26}"
      f"{'retained':>10}")
    for i in INSTR:
        s = d.dropna(subset=[f"past_{i}_30", f"pastlag_{i}_30", f"fwd_{i}_30", "mfo"])
        a = S.block_boot_within_slot_ic(s, f"past_{i}_30", f"fwd_{i}_30", rng, NBOOT)
        b = S.block_boot_within_slot_ic(s, f"pastlag_{i}_30", f"fwd_{i}_30", rng, NBOOT)
        keep = b[0] / a[0] if a[0] not in (0.0, np.nan) else np.nan
        P(f"{i:<6}{len(s):>8,}  {S.fmt_ci(a):<26}{S.fmt_ci(b):<26}{keep:>10.2f}")
    P("")

    # ---- ARTIFACT CONTROL 2: the dollar's own autocorrelation ------------ #
    # The `fwdresid` target contains -beta*fwd_dxy and the `factor` predictor contains
    # +beta*past_dxy, so their correlation mechanically inherits -beta^2 *
    # corr(past_dxy, fwd_dxy). If the dollar itself reverts, that term is POSITIVE and
    # would masquerade as "the dollar-explained leg predicts the hedged return".
    P("--- ARTIFACT CONTROL: the dollar's own autocorrelation ---")
    sd_ = d.dropna(subset=["past_dxy_30", "fwd_dxy_30", "pastlag_dxy_30", "mfo"])
    a = S.block_boot_within_slot_ic(sd_, "past_dxy_30", "fwd_dxy_30", rng, NBOOT)
    b = S.block_boot_within_slot_ic(sd_, "pastlag_dxy_30", "fwd_dxy_30", rng, NBOOT)
    P(f"  IC(past_dxy_30, fwd_dxy_30)     = {S.fmt_ci(a)}   n={len(sd_):,}")
    P(f"  IC(pastlag_dxy_30, fwd_dxy_30)  = {S.fmt_ci(b)}   (shared endpoint removed)")
    P("  => any IC of a beta-scaled dollar predictor against a beta-hedged target")
    P("     inherits -beta^2 times this number and is NOT equity/gold information.")
    P("")

    # ---- PRIMARY + siblings, both targets --------------------------------- #
    for tgt_kind in ("fwd", "fwdresid"):
        label = ("RAW forward return" if tgt_kind == "fwd"
                 else "DOLLAR-HEDGED forward return (fwd - beta*fwd_dxy)")
        P(f"--- within-slot Spearman IC vs {label}, W={PRIMARY_W} H={PRIMARY_H} ---")
        P(f"{'inst':<6}{'n':>8}  {'IC(raw past)':<26}{'IC(residual)':<26}"
          f"{'IC(factor leg)':<26}{'PAIRED delta resid-raw':<28}")
        for i in INSTR:
            s = _common(d, i, PRIMARY_W, PRIMARY_H)
            t = f"{tgt_kind}_{i}_{PRIMARY_H}"
            a = S.block_boot_within_slot_ic(s, f"past_{i}_{PRIMARY_W}", t, rng, NBOOT)
            b = S.block_boot_within_slot_ic(s, f"resid_{i}_{PRIMARY_W}", t, rng, NBOOT)
            c = S.block_boot_within_slot_ic(s, f"factor_{i}_{PRIMARY_W}", t, rng, NBOOT)
            e = S.block_boot_within_slot_ic_delta(
                s, f"resid_{i}_{PRIMARY_W}", f"past_{i}_{PRIMARY_W}", t, rng, NBOOT)
            P(f"{i:<6}{len(s):>8,}  {S.fmt_ci(a):<26}{S.fmt_ci(b):<26}"
              f"{S.fmt_ci(c):<26}{S.fmt_ci(e):<28}")
        # HYP-0001 says the residual "predicts BETTER", i.e. larger |IC|. The signed
        # delta above assumed the effect would be momentum (positive IC). Where the
        # tape actually reverts, the signed delta has the OPPOSITE reading, so the
        # honest comparison is on magnitudes and is printed explicitly.
        P(f"  |IC| reading (the hypothesis' actual claim: residual predicts BETTER):")
        for i in INSTR:
            s = _common(d, i, PRIMARY_W, PRIMARY_H)
            t = f"{tgt_kind}_{i}_{PRIMARY_H}"
            ra = abs(S.within_slot_ic_arrays(
                s[f"past_{i}_{PRIMARY_W}"].to_numpy(float), s[t].to_numpy(float),
                s["mfo"].to_numpy(float)))
            rb = abs(S.within_slot_ic_arrays(
                s[f"resid_{i}_{PRIMARY_W}"].to_numpy(float), s[t].to_numpy(float),
                s["mfo"].to_numpy(float)))
            verdict = "residual BETTER" if rb > ra else "residual WORSE"
            P(f"    {i:<4} |IC| raw {ra:.4f} -> residual {rb:.4f}   "
              f"({100 * rb / ra:6.1f}% of raw)   {verdict}")
        P("")

    # ---- (W, H) surface: a SEARCH, read the slope not the argmax ---------- #
    P("--- (W,H) surface of the paired delta [resid - raw], raw forward target ---")
    P("    DESCRIPTIVE SEARCH (9 cells x 3 markets). Point estimates only; the")
    P("    preregistered cell is W=30/H=30 and is the only confirmatory number.")
    for i in INSTR:
        P(f"  {i}:")
        P("    " + f"{'W\\H':<6}" + "".join(f"{h:>12}" for h in HORIZONS)
          + f"{'  |  IC raw @H=30':>18}")
        for W in WINS:
            row = []
            for H in HORIZONS:
                s = _common(d, i, W, H)
                v = (S.within_slot_ic_arrays(
                        s[f"resid_{i}_{W}"].to_numpy(float),
                        s[f"fwd_{i}_{H}"].to_numpy(float), s["mfo"].to_numpy(float))
                     - S.within_slot_ic_arrays(
                        s[f"past_{i}_{W}"].to_numpy(float),
                        s[f"fwd_{i}_{H}"].to_numpy(float), s["mfo"].to_numpy(float)))
                row.append(v)
            s30 = _common(d, i, W, 30)
            base = S.within_slot_ic_arrays(
                s30[f"past_{i}_{W}"].to_numpy(float),
                s30[f"fwd_{i}_30"].to_numpy(float), s30["mfo"].to_numpy(float))
            P("    " + f"{W:<6}" + "".join(f"{v:>+12.4f}" for v in row)
              + f"{base:>+18.4f}")
    P("")

    # ---- era split -------------------------------------------------------- #
    P("--- era split (paired delta, W=30 H=30, raw target) ---")
    P(f"{'inst':<6}{'era':<14}{'n':>8}  {'IC raw':<26}{'IC resid':<26}"
      f"{'PAIRED delta':<28}")
    for i in INSTR:
        s = _common(d, i, PRIMARY_W, PRIMARY_H)
        for era, m in (("2011-2018", s["date"].dt.year <= 2018),
                       ("2019-2026", s["date"].dt.year >= 2019)):
            g = s[m]
            t = f"fwd_{i}_{PRIMARY_H}"
            a = S.block_boot_within_slot_ic(g, f"past_{i}_{PRIMARY_W}", t, rng, NBOOT)
            b = S.block_boot_within_slot_ic(g, f"resid_{i}_{PRIMARY_W}", t, rng, NBOOT)
            e = S.block_boot_within_slot_ic_delta(
                g, f"resid_{i}_{PRIMARY_W}", f"past_{i}_{PRIMARY_W}", t, rng, NBOOT)
            P(f"{i:<6}{era:<14}{len(g):>8,}  {S.fmt_ci(a):<26}{S.fmt_ci(b):<26}"
              f"{S.fmt_ci(e):<28}")
    P("")

    # ---- dollar-fresh subsample ------------------------------------------ #
    P("--- dollar-fresh decisions only (no forward-filled dollar at either endpoint) ---")
    P(f"{'inst':<6}{'n':>8}{'kept':>8}  {'IC raw':<26}{'IC resid':<26}"
      f"{'PAIRED delta':<28}")
    for i in INSTR:
        s = _common(d, i, PRIMARY_W, PRIMARY_H)
        g = s[s["dxy_fresh"]]
        t = f"fwd_{i}_{PRIMARY_H}"
        a = S.block_boot_within_slot_ic(g, f"past_{i}_{PRIMARY_W}", t, rng, NBOOT)
        b = S.block_boot_within_slot_ic(g, f"resid_{i}_{PRIMARY_W}", t, rng, NBOOT)
        e = S.block_boot_within_slot_ic_delta(
            g, f"resid_{i}_{PRIMARY_W}", f"past_{i}_{PRIMARY_W}", t, rng, NBOOT)
        P(f"{i:<6}{len(s):>8,}{len(g) / len(s):>8.3f}  {S.fmt_ci(a):<26}"
          f"{S.fmt_ci(b):<26}{S.fmt_ci(e):<28}")
    P("")

    # ---- economic units --------------------------------------------------- #
    P("--- magnitude in tradable units (rule 19/21): quintile spread of the ---")
    P("--- primary predictor against the mean forward move, W=30 H=30        ---")
    TICK = {"GC": (0.10, 10.0), "ES": (0.25, 12.50), "NQ": (0.25, 5.0)}
    for i in INSTR:
        s = _common(d, i, PRIMARY_W, PRIMARY_H).copy()
        px = np.exp(panel[f"lp_{i}"]).median()
        for pred in (f"past_{i}_{PRIMARY_W}", f"resid_{i}_{PRIMARY_W}"):
            s2 = s.copy()
            s2["_q"] = pd.qcut(s2[pred], 5, labels=False, duplicates="drop")

            def _spread(qq, ff):
                return float(np.nanmean(ff[qq == qq.max()])
                             - np.nanmean(ff[qq == qq.min()]))

            real, lo, hi = (lambda v: v)(
                (_spread(s2["_q"].to_numpy(float),
                         s2[f"fwd_{i}_{PRIMARY_H}"].to_numpy(float)),
                 *np.nanpercentile(
                     S._block_boot(s2, ["_q", f"fwd_{i}_{PRIMARY_H}"], _spread,
                                   rng, 300), [5, 95])))
            tick, dv = TICK[i]
            pts, plo, phi = (v * px for v in (real, lo, hi))
            P(f"  {i:<4}{pred:<18} q5-q1 fwd move = {1e4 * real:+7.2f} bp "
              f"[{1e4 * lo:+6.2f},{1e4 * hi:+6.2f}] = {pts / tick:+6.2f} ticks "
              f"= ${pts / tick * dv:+8.2f}/contract "
              f"(1 tick round-trip approx ${2 * dv:.2f})")
    P("")
    txt = "\n".join(L)
    print(txt)
    (OUT / "residual_momentum.txt").write_text(txt, encoding="utf-8")
    print(f"\nwrote {OUT / 'residual_momentum.txt'}")


if __name__ == "__main__":
    main()
