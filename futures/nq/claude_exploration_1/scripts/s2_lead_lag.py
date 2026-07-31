"""HYP-0002 / EXP-0002 -- does the dollar LEAD gold and the equity indices?

    python -u -m futures.nq.claude_exploration_1.scripts.s2_lead_lag

Measures the within-slot PARTIAL Spearman IC of the trailing dollar return against an
instrument's forward return, controlling for the instrument's own trailing return, at a
5-minute non-overlapping clock. The three arms that decide the run are the REVERSE
direction (a real lead is asymmetric), the EUR-only dollar proxy (a lead that lives
only in the thin legs is stale prices), and the dollar-fresh subsample.

Within-slot grouping uses the 30-minute block rather than each of the 78 five-minute
slots: the purpose is to strip time-of-day composition, which a 13-cell block does just
as well, and it keeps every cell at ~22k observations instead of ~3.7k.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core import features as F
from ..core import stats as S
from .build_panel import load

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0002"
INSTR = ("GC", "ES", "NQ")
WINS = (5, 10, 30)
HORIZONS = (5, 10, 30)
PRIMARY_W, PRIMARY_H, PRIMARY_I = 5, 5, "GC"
NBOOT = 200
TICK = {"GC": (0.10, 10.0), "ES": (0.25, 12.50), "NQ": (0.25, 5.0)}


def build(tag: str, period: int) -> pd.DataFrame:
    d = F.decision_frame(load(tag), instruments=INSTR, past_wins=WINS,
                         horizons=HORIZONS, period=period)
    d["blk"] = (d["mfo"] // 30) * 30
    return d


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260731)
    d5 = build("4leg", 5)
    L: list[str] = []
    P = L.append

    P("=" * 78)
    P("EXP-0002  HYP-0002  cross-asset lead-lag: does the dollar lead?")
    P("=" * 78)
    P(f"5-minute clock: {len(d5):,} decision rows, {d5['date'].nunique():,} sessions, "
      f"{d5['mfo'].nunique()} slots grouped into {d5['blk'].nunique()} 30-min blocks")
    P(f"primary cell: {PRIMARY_I}  W={PRIMARY_W}  H={PRIMARY_H}   nboot={NBOOT}")
    P("expected sign: NEGATIVE (dollar up -> gold keeps falling)")
    P("")

    # ---- how big is the contemporaneous link, for scale ------------------- #
    P("--- contemporaneous link, for scale (same 5-minute window) ---")
    for i in INSTR:
        s = d5.dropna(subset=[f"past_dxy_{PRIMARY_W}", f"past_{i}_{PRIMARY_W}"])
        c = float(np.corrcoef(s[f"past_dxy_{PRIMARY_W}"], s[f"past_{i}_{PRIMARY_W}"])[0, 1])
        r = S.within_slot_ic_arrays(s[f"past_dxy_{PRIMARY_W}"].to_numpy(float),
                                    s[f"past_{i}_{PRIMARY_W}"].to_numpy(float),
                                    s["blk"].to_numpy(float))
        P(f"  {i:<4} pearson {c:+.4f}   within-block rank {r:+.4f}   n={len(s):,}")
    P("")

    # ---- PRIMARY: forward and reverse ------------------------------------ #
    P("--- PRIMARY: within-block partial rank IC, 5-min clock, W=5 H=5 ---")
    P("    forward : pIC(past_dxy, fwd_INST | past_INST)   'does the dollar lead?'")
    P("    reverse : pIC(past_INST, fwd_dxy | past_dxy)    'does the instrument lead?'")
    P("    KT2 fires if |reverse| is within a factor of 2 of |forward|.")
    P(f"{'inst':<6}{'n':>9}  {'FORWARD (dollar leads)':<28}"
      f"{'REVERSE (instrument leads)':<28}{'ratio |rev|/|fwd|':>19}")
    prim: dict[str, tuple] = {}
    for i in INSTR:
        s = d5.dropna(subset=[f"past_dxy_{PRIMARY_W}", f"past_{i}_{PRIMARY_W}",
                              f"fwd_{i}_{PRIMARY_H}", f"fwd_dxy_{PRIMARY_H}", "blk"])
        f_ = S.block_boot_within_slot_partial_ic(
            s, f"past_dxy_{PRIMARY_W}", f"fwd_{i}_{PRIMARY_H}", f"past_{i}_{PRIMARY_W}",
            rng, NBOOT, slot_col="blk")
        r_ = S.block_boot_within_slot_partial_ic(
            s, f"past_{i}_{PRIMARY_W}", f"fwd_dxy_{PRIMARY_H}", f"past_dxy_{PRIMARY_W}",
            rng, NBOOT, slot_col="blk")
        prim[i] = (f_, r_)
        ratio = abs(r_[0]) / abs(f_[0]) if f_[0] else np.nan
        P(f"{i:<6}{len(s):>9,}  {S.fmt_ci(f_):<28}{S.fmt_ci(r_):<28}{ratio:>19.2f}")
    P("")

    # ---- own-momentum baseline, so the increment has a scale -------------- #
    P("--- for scale: the instrument's OWN 5-min momentum (what we control for) ---")
    for i in INSTR:
        s = d5.dropna(subset=[f"past_{i}_{PRIMARY_W}", f"fwd_{i}_{PRIMARY_H}", "blk"])
        own = S.block_boot_within_slot_ic(s, f"past_{i}_{PRIMARY_W}",
                                          f"fwd_{i}_{PRIMARY_H}", rng, NBOOT,
                                          slot_col="blk")
        P(f"  {i:<4} IC(past_{i}_5, fwd_{i}_5) = {S.fmt_ci(own)}")
    P("")

    # ---- shared-endpoint control on the OWN-momentum baseline -------------- #
    # At a 5-minute horizon the shared close at m is one bar out of five, so bid-ask
    # bounce is a far bigger share of the measured reversion than it is at 30 minutes.
    # This has to be checked before the 5-minute reversion is described as real.
    P("--- ARTIFACT CONTROL: shared-endpoint (bid-ask bounce) at the 5-min horizon ---")
    P("    `pastlag` ends at m-1 so no price is shared with the forward window.")
    P(f"{'inst':<6}{'n':>9}  {'IC(past_5, fwd_5)':<28}{'IC(pastlag_5, fwd_5)':<28}"
      f"{'retained':>10}")
    for i in INSTR:
        s = d5.dropna(subset=[f"past_{i}_5", f"pastlag_{i}_5", f"fwd_{i}_5", "blk"])
        a = S.block_boot_within_slot_ic(s, f"past_{i}_5", f"fwd_{i}_5", rng, NBOOT,
                                        slot_col="blk")
        b = S.block_boot_within_slot_ic(s, f"pastlag_{i}_5", f"fwd_{i}_5", rng, NBOOT,
                                        slot_col="blk")
        P(f"{i:<6}{len(s):>9,}  {S.fmt_ci(a):<28}{S.fmt_ci(b):<28}"
          f"{b[0] / a[0]:>10.2f}")
    s = d5.dropna(subset=["past_dxy_5", "pastlag_dxy_5", "fwd_dxy_5", "blk"])
    a = S.block_boot_within_slot_ic(s, "past_dxy_5", "fwd_dxy_5", rng, NBOOT,
                                    slot_col="blk")
    b = S.block_boot_within_slot_ic(s, "pastlag_dxy_5", "fwd_dxy_5", rng, NBOOT,
                                    slot_col="blk")
    P(f"{'DXY':<6}{len(s):>9,}  {S.fmt_ci(a):<28}{S.fmt_ci(b):<28}{b[0] / a[0]:>10.2f}")
    P("")

    # ---- KT3: staleness controls ------------------------------------------ #
    P("--- KT3 staleness controls: EUR-only basket, and dollar-fresh rows only ---")
    P("    6E is forward-filled on 0.42% of minutes vs 4.70% for the 4-leg basket.")
    P(f"{'inst':<6}{'arm':<16}{'n':>9}  {'FORWARD':<28}{'REVERSE':<28}")
    deur = build("eur", 5)
    for i in INSTR:
        for arm, src, msk in (("4leg (primary)", d5, None),
                              ("EUR only", deur, None),
                              ("4leg dxy-fresh", d5, "dxy_fresh")):
            s = src.dropna(subset=[f"past_dxy_{PRIMARY_W}", f"past_{i}_{PRIMARY_W}",
                                   f"fwd_{i}_{PRIMARY_H}", f"fwd_dxy_{PRIMARY_H}", "blk"])
            if msk:
                s = s[s[msk]]
            f_ = S.block_boot_within_slot_partial_ic(
                s, f"past_dxy_{PRIMARY_W}", f"fwd_{i}_{PRIMARY_H}",
                f"past_{i}_{PRIMARY_W}", rng, NBOOT, slot_col="blk")
            r_ = S.block_boot_within_slot_partial_ic(
                s, f"past_{i}_{PRIMARY_W}", f"fwd_dxy_{PRIMARY_H}",
                f"past_dxy_{PRIMARY_W}", rng, NBOOT, slot_col="blk")
            P(f"{i:<6}{arm:<16}{len(s):>9,}  {S.fmt_ci(f_):<28}{S.fmt_ci(r_):<28}")
    P("")

    # ---- horizon term structure (descriptive) ----------------------------- #
    P("--- horizon term structure of the FORWARD partial IC (descriptive) ---")
    P("    a real transmission lag must DECAY with H; growth points elsewhere.")
    P("    5-minute clock (W=5) then 30-minute clock (W=30), point estimates only.")
    d30 = build("4leg", 30)
    for clock, src, W in ((" 5m clock", d5, 5), ("30m clock", d30, 30)):
        P(f"  {clock}  W={W}")
        P("    " + f"{'inst':<6}" + "".join(f"{'H=' + str(h):>12}" for h in HORIZONS))
        for i in INSTR:
            row = []
            for H in HORIZONS:
                s = src.dropna(subset=[f"past_dxy_{W}", f"past_{i}_{W}",
                                       f"fwd_{i}_{H}", "blk"])
                row.append(S.within_slot_partial_ic(
                    s[f"past_dxy_{W}"].to_numpy(float), s[f"fwd_{i}_{H}"].to_numpy(float),
                    s[f"past_{i}_{W}"].to_numpy(float), s["blk"].to_numpy(float)))
            P("    " + f"{i:<6}" + "".join(f"{v:>+12.4f}" for v in row))
    P("")

    # ---- era split --------------------------------------------------------- #
    P("--- era split of the primary FORWARD partial IC ---")
    for i in INSTR:
        s = d5.dropna(subset=[f"past_dxy_{PRIMARY_W}", f"past_{i}_{PRIMARY_W}",
                              f"fwd_{i}_{PRIMARY_H}", "blk"])
        for era, m in (("2011-2018", s["date"].dt.year <= 2018),
                       ("2019-2026", s["date"].dt.year >= 2019)):
            v = S.block_boot_within_slot_partial_ic(
                s[m], f"past_dxy_{PRIMARY_W}", f"fwd_{i}_{PRIMARY_H}",
                f"past_{i}_{PRIMARY_W}", rng, NBOOT, slot_col="blk")
            P(f"  {i:<4}{era:<12}{int(m.sum()):>9,}  {S.fmt_ci(v)}")
    P("")

    # ---- economic units ---------------------------------------------------- #
    P("--- economic size (rule 19/21): forward move by quintile of the trailing ---")
    P("--- dollar return, WITHIN quintiles of the instrument's own trailing move ---")
    P("    (double sort, so the number is the dollar's marginal contribution)")
    panel = load("4leg")
    for i in INSTR:
        s = d5.dropna(subset=[f"past_dxy_{PRIMARY_W}", f"past_{i}_{PRIMARY_W}",
                              f"fwd_{i}_{PRIMARY_H}"]).copy()
        s["qo"] = s.groupby("blk")[f"past_{i}_{PRIMARY_W}"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
        s["qd"] = s.groupby(["blk", "qo"])[f"past_dxy_{PRIMARY_W}"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
        m = s.groupby("qd")[f"fwd_{i}_{PRIMARY_H}"].mean()
        spread = float(m.iloc[-1] - m.iloc[0])

        def _sp(qd, ff):
            return float(np.nanmean(ff[qd == qd.max()]) - np.nanmean(ff[qd == qd.min()]))

        lo, hi = np.nanpercentile(
            S._block_boot(s, ["qd", f"fwd_{i}_{PRIMARY_H}"], _sp, rng, 200), [5, 95])
        px = float(np.exp(panel[f"lp_{i}"]).median())
        tick, dv = TICK[i]
        pts = spread * px
        P(f"  {i:<4} top-vs-bottom dollar quintile => forward 5-min move "
          f"{1e4 * spread:+7.2f} bp [{1e4 * lo:+6.2f},{1e4 * hi:+6.2f}]  "
          f"= {pts / tick:+6.2f} ticks = ${pts / tick * dv:+7.2f}/contract "
          f"(round trip approx ${2 * dv:.2f})")
    P("")

    txt = "\n".join(L)
    print(txt)
    (OUT / "lead_lag.txt").write_text(txt, encoding="utf-8")
    print(f"\nwrote {OUT / 'lead_lag.txt'}")


if __name__ == "__main__":
    main()
