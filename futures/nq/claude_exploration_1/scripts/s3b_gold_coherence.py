"""EXP-0005 -- follow-up on EXP-0003's one live cell: gold's coherence contrast.

    python -u -m futures.nq.claude_exploration_1.scripts.s3b_gold_coherence [ndraws]

EXP-0003 fired HYP-0003's KT1 on both PRIMARY markets (ES, NQ) but the declared third
market, GC, produced a contrast of +0.0496 [+0.0077,+0.0945] whose re-pairing null
centred at zero. That is a screen on a secondary market, not a pass -- and before it is
worth anything at all it has to survive the one confound EXP-0003 left open.

The confound is visible in EXP-0003's own cell table: high-coherence decisions are also
HIGH-VOLATILITY decisions (ES mean trailing RV 21.6 bp versus 14.7 bp). This workspace
has rejected five volatility overlays on this family, so "coherence" that is really
volatility would be the sixth rejection wearing a new label.

Arms:
  * `slot`      -- EXP-0003's split (matched on time of day only). Reproduction.
  * `slot x rv` -- the same split made WITHIN volatility quintiles, so the high and low
                   coherence cells hold identical volatility composition as well as
                   identical time-of-day composition. This is the confound-free number.
  * the MIRROR  -- volatility split within coherence quintiles. If volatility still
                   contrasts once coherence is held fixed, both are live; if it goes to
                   zero, coherence is the carrier.
  * a longer rule-18 re-pairing null on the vol-neutral arm.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import features as F
from ..core import stats as S
from .build_panel import load
from .s3_factor_coherence import repaired_panel

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0005"
INSTR = ("GC", "ES", "NQ")
W, H, RATE = 30, 30, 0.30
NBOOT = 400


def add_keys(d: pd.DataFrame, inst: str, nq: int = 5) -> pd.DataFrame:
    """Composite grouping keys.

    `key_slot`    = the decision slot (EXP-0003's grouping).
    `key_slot_rv` = slot x within-slot volatility quintile. Using it as the "slot" for
                    both the top/bottom split AND the within-slot correlation makes the
                    two coherence cells identical in time-of-day AND volatility
                    composition, so any surviving contrast is not either of those.
    `key_slot_coh`= slot x coherence quintile, for the mirror control.
    """
    d = d.copy()
    d["key_slot"] = d["mfo"].astype(float)

    def _q(col):
        return d.groupby("mfo")[col].transform(
            lambda x: pd.qcut(x, nq, labels=False, duplicates="drop"))

    d["_qrv"] = _q(f"rvz_{inst}")
    d["_qcoh"] = _q(f"cohz_{inst}")
    d["key_slot_rv"] = d["mfo"] * 10 + d["_qrv"]
    d["key_slot_coh"] = d["mfo"] * 10 + d["_qcoh"]
    return d


def contrast(d: pd.DataFrame, inst: str, sel: str, key: str, rate=RATE) -> float:
    s = d.dropna(subset=[f"past_{inst}_{W}", f"fwd_{inst}_{H}", sel, key])
    return S.regime_contrast(s[f"past_{inst}_{W}"].to_numpy(float),
                             s[f"fwd_{inst}_{H}"].to_numpy(float),
                             s[sel].to_numpy(float), s[key].to_numpy(float), rate=rate)


def main(ndraw: int = 100) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260731)
    panel = load("4leg")
    d0 = F.decision_frame(panel, instruments=INSTR)
    L: list[str] = []
    P = L.append

    P("=" * 78)
    P("EXP-0005  follow-up: is gold's coherence contrast just VOLATILITY?")
    P("=" * 78)
    P(f"rows {len(d0):,}  sessions {d0['date'].nunique():,}  "
      f"rate={RATE:.0%}  nboot={NBOOT}  null draws={ndraw}")
    P("EXP-0003 result being followed up: GC cohz contrast +0.0496 [+0.0077,+0.0945],")
    P("re-pairing null centred at -0.0029, frac>=real 0.067 on 30 draws.")
    P("GC was a DECLARED SECONDARY market in HYP-0003. This is a screen, not a pass.")
    P("")

    # ---- how entangled are coherence and volatility? ---------------------- #
    P("--- how entangled are the two labels? ---")
    P(f"{'inst':<6}{'corr(cohz,rvz)':>17}{'rank corr':>12}"
      f"{'mean rv|high coh':>19}{'mean rv|low coh':>18}{'ratio':>8}")
    for i in INSTR:
        s = d0.dropna(subset=[f"cohz_{i}", f"rvz_{i}", f"rv_{i}", "mfo"])
        pc = float(np.corrcoef(s[f"cohz_{i}"], s[f"rvz_{i}"])[0, 1])
        rc = S.spearman(s[f"cohz_{i}"].to_numpy(float), s[f"rvz_{i}"].to_numpy(float))
        hi, lo = S._split_by_rate(s[f"cohz_{i}"].to_numpy(float),
                                  s["mfo"].to_numpy(float), RATE)
        a, b = 1e4 * s[f"rv_{i}"][hi].mean(), 1e4 * s[f"rv_{i}"][lo].mean()
        P(f"{i:<6}{pc:>17.4f}{rc:>12.4f}{a:>19.2f}{b:>18.2f}{a / b:>8.2f}")
    P("")

    # ---- the three arms ---------------------------------------------------- #
    P("--- the contrast under progressively stricter matching ---")
    P("    slot        : matched on time of day only (EXP-0003's number)")
    P("    slot x rv   : ALSO matched on volatility quintile  <- confound-free")
    P("    mirror      : volatility selector, matched on slot x coherence quintile")
    P(f"{'inst':<6}{'arm':<24}{'selector':<10}{'n':>8}  {'contrast':<28}")
    prim: dict[tuple[str, str], float] = {}
    for i in INSTR:
        d = add_keys(d0, i)
        for arm, sel, key in (("slot (reproduction)", f"cohz_{i}", "key_slot"),
                              ("slot x rv (primary)", f"cohz_{i}", "key_slot_rv"),
                              ("mirror: vol|coherence", f"rvz_{i}", "key_slot_coh")):
            s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", sel, key])
            v = S.block_boot_regime_contrast(s, f"past_{i}_{W}", f"fwd_{i}_{H}", sel,
                                             rng, NBOOT, rate=RATE, slot_col=key)
            prim[(i, arm)] = v[0]
            P(f"{i:<6}{arm:<24}{sel:<10}{len(s):>8,}  {S.fmt_ci(v):<28}")
    P("")

    # ---- what the vol-neutral cells contain -------------------------------- #
    P("--- vol-neutral cells: confirming volatility really is matched ---")
    P(f"{'inst':<6}{'cell':<7}{'n':>8}{'mean coh':>10}{'mean rv bp':>12}"
      f"{'mean |past| bp':>16}{'corr(past,fwd)':>16}")
    for i in INSTR:
        d = add_keys(d0, i)
        s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", f"cohz_{i}", "key_slot_rv"])
        hi, lo = S._split_by_rate(s[f"cohz_{i}"].to_numpy(float),
                                  s["key_slot_rv"].to_numpy(float), RATE)
        for nm, m in (("high", hi), ("low", lo)):
            g = s[m]
            P(f"{i:<6}{nm:<7}{len(g):>8,}{g[f'coh_{i}'].mean():>10.3f}"
              f"{1e4 * g[f'rv_{i}'].mean():>12.2f}"
              f"{1e4 * g[f'past_{i}_{W}'].abs().mean():>16.2f}"
              f"{S.within_slot_corr(g[f'past_{i}_{W}'].to_numpy(float), g[f'fwd_{i}_{H}'].to_numpy(float), g['key_slot_rv'].to_numpy(float)):>+16.4f}")
    P("")

    # ---- economic dose-response ------------------------------------------- #
    P("--- economic dose-response (rules 19/21): a naive causal momentum tilt ---")
    P("    side = sign(trailing 30-min move); pnl = side * next 30-min move.")
    P("    Non-overlapping decisions, no costs applied -- this is GROSS expectancy,")
    P("    reported so the contrast can be read in ticks rather than correlation.")
    TICK = {"GC": (0.10, 10.0), "ES": (0.25, 12.50), "NQ": (0.25, 5.0)}
    P(f"{'inst':<6}{'cell':<20}{'n':>8}{'gross bp/bet':>14}{'ticks':>9}"
      f"{'$/contract':>13}{'t (session-clustered)':>23}")
    for i in INSTR:
        d = add_keys(d0, i)
        s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", f"cohz_{i}",
                             "key_slot_rv"]).copy()
        s["pnl"] = np.sign(s[f"past_{i}_{W}"]) * s[f"fwd_{i}_{H}"]
        hi, lo = S._split_by_rate(s[f"cohz_{i}"].to_numpy(float),
                                  s["key_slot_rv"].to_numpy(float), RATE)
        px = float(np.exp(panel[f"lp_{i}"]).median())
        tick, dv = TICK[i]
        for nm, m in (("high coh (vol-ntl)", hi), ("low coh (vol-ntl)", lo),
                      ("all", np.ones(len(s), bool))):
            g = s[m]
            per = g.groupby("date")["pnl"].mean()
            t = float(per.mean() / (per.std(ddof=1) / np.sqrt(len(per))))
            bp = 1e4 * g["pnl"].mean()
            pts = g["pnl"].mean() * px
            P(f"{i:<6}{nm:<20}{len(g):>8,}{bp:>14.3f}{pts / tick:>9.3f}"
              f"{pts / tick * dv:>13.2f}{t:>23.2f}")
    P("")

    # ---- longer re-pairing null on the vol-neutral arm --------------------- #
    P(f"--- rule-18 re-pairing null, {ndraw} draws, on the VOL-NEUTRAL arm ---")
    sess = pd.DatetimeIndex(F.sessions_of(panel))
    draws = {i: [] for i in INSTR}
    for k in range(ndraw):
        perm = S.repair_sessions(sess, rng)
        dn = F.decision_frame(repaired_panel(panel, perm), instruments=INSTR)
        for i in INSTR:
            draws[i].append(contrast(add_keys(dn, i), i, f"cohz_{i}", "key_slot_rv"))
        if (k + 1) % 20 == 0:
            print(f"  null draw {k + 1}/{ndraw}")
    P(f"{'inst':<6}{'real':>10}{'null mean':>12}{'null sd':>10}{'null p05':>10}"
      f"{'null p95':>10}{'z':>8}{'frac >= real':>14}")
    for i in INSTR:
        a = np.array(draws[i], float)
        r = prim[(i, "slot x rv (primary)")]
        z = (r - a.mean()) / a.std(ddof=1)
        P(f"{i:<6}{r:>+10.4f}{a.mean():>+12.4f}{a.std(ddof=1):>10.4f}"
          f"{np.percentile(a, 5):>+10.4f}{np.percentile(a, 95):>+10.4f}"
          f"{z:>8.2f}{float((a >= r).mean()):>14.3f}")
    P("")

    txt = "\n".join(L)
    print(txt)
    (OUT / "gold_coherence.txt").write_text(txt, encoding="utf-8")
    print(f"\nwrote {OUT / 'gold_coherence.txt'}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
