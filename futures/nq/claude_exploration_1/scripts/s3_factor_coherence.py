"""HYP-0003 / EXP-0003 -- macro factor coherence as a momentum regime.

    python -u -m futures.nq.claude_exploration_1.scripts.s3_factor_coherence [ndraws]

Labels each decision by how strongly the instrument's 1-minute returns have been moving
with the dollar over the trailing hour (`cohz`, same-slot z-scored), splits the panel at
a matched 30% rate WITHIN each slot, and compares trailing-to-forward momentum between
the two cells.

Three arms decide the run:
  * the contrast itself, on ES and NQ (KT1);
  * the same contrast with the VOLATILITY LEVEL as selector -- the label this workspace
    has already shown is worthless on this tape, so a coherence label that cannot beat
    it is volatility re-badged (KT2);
  * a rule-18 re-pairing null: today's equity session is paired with a DIFFERENT
    session's dollar path from the same calendar year, and the entire feature pipeline
    (beta, coherence, z-score, split, contrast) is recomputed on it (KT3).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import features as F
from ..core import stats as S
from .build_panel import load

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0003"
INSTR = ("ES", "NQ", "GC")
PRIMARY = ("ES", "NQ")
W, H, RATE = 30, 30, 0.30
NBOOT = 400


def repaired_panel(panel: pd.DataFrame, perm: np.ndarray) -> pd.DataFrame:
    """Swap each session's dollar path for a different session's, keeping the equity
    and gold paths exactly as they were.

    The donor dollar path is a REAL dollar path -- real volatility, real
    autocorrelation, real calendar and roll structure -- that simply did not happen on
    the same day. Everything downstream (beta, coherence, z-score) is rebuilt from it,
    so this is a full-pipeline null (rule 17), not a relabelling of finished results.
    """
    p = panel.copy()
    for c in ("log_dxy", "stale_dxy"):
        m = F.to_matrix(panel, c)
        p[c] = m[perm].reshape(-1)
    p["stale_dxy"] = p["stale_dxy"].astype(bool)
    return p


def contrasts(d: pd.DataFrame, sel_tpl: str, rate: float = RATE) -> dict[str, float]:
    out = {}
    for i in INSTR:
        s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", sel_tpl.format(i), "mfo"])
        out[i] = S.regime_contrast(
            s[f"past_{i}_{W}"].to_numpy(float), s[f"fwd_{i}_{H}"].to_numpy(float),
            s[sel_tpl.format(i)].to_numpy(float), s["mfo"].to_numpy(float), rate=rate)
    return out


def main(ndraw: int = 30) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260731)
    panel = load("4leg")
    d = F.decision_frame(panel, instruments=INSTR)
    L: list[str] = []
    P = L.append

    P("=" * 78)
    P("EXP-0003  HYP-0003  macro factor coherence as a momentum regime")
    P("=" * 78)
    P(f"rows {len(d):,}  sessions {d['date'].nunique():,}  W={W} H={H} "
      f"matched rate={RATE:.0%}  nboot={NBOOT}  null draws={ndraw}")
    P("")

    # ---- the label itself -------------------------------------------------- #
    P("--- the coherence label: |corr(1-min INST, 1-min DXY)| over the trailing 60m ---")
    P(f"{'inst':<6}{'mean':>9}{'sd':>9}{'p10':>9}{'p90':>9}{'coverage':>11}"
      f"{'slot-mean spread':>19}")
    for i in INSTR:
        c = d[f"coh_{i}"]
        by = d.groupby("mfo")[f"coh_{i}"].mean()
        P(f"{i:<6}{c.mean():>9.3f}{c.std():>9.3f}{c.quantile(.1):>9.3f}"
          f"{c.quantile(.9):>9.3f}{c.notna().mean():>11.3f}"
          f"{by.max() - by.min():>19.3f}")
    P("")
    P("--- rule 9a: is a fixed cut on RAW coherence a clock? (selection rate by slot) ---")
    P("    " + f"{'mfo':<6}" + "".join(f"{i + ' raw':>11}{i + ' z':>9}" for i in PRIMARY))
    for i in PRIMARY:
        thr = d[f"coh_{i}"].quantile(1 - RATE)
    for slot, g in d.groupby("mfo"):
        cells = []
        for i in PRIMARY:
            thr = d[f"coh_{i}"].quantile(1 - RATE)
            zthr = d[f"cohz_{i}"].quantile(1 - RATE)
            cells.append(f"{(g[f'coh_{i}'] >= thr).mean():>11.3f}"
                         f"{(g[f'cohz_{i}'] >= zthr).mean():>9.3f}")
        P("    " + f"{slot:<6}" + "".join(cells))
    P("    (the z-score column is the calibrated label; the raw column is the clock)")
    P("")

    # ---- unconditional momentum, for scale -------------------------------- #
    P("--- unconditional within-slot momentum corr(past_30, fwd_30) ---")
    for i in INSTR:
        s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", "mfo"])
        v = S.within_slot_corr(s[f"past_{i}_{W}"].to_numpy(float),
                               s[f"fwd_{i}_{H}"].to_numpy(float),
                               s["mfo"].to_numpy(float))
        P(f"  {i:<4} {v:+.4f}   n={len(s):,}")
    P("")

    # ---- PRIMARY (KT1) and the degenerate control (KT2) -------------------- #
    P("--- PRIMARY contrast (KT1) and the DEGENERATE volatility-level control (KT2) ---")
    P("    contrast = within-slot corr(past,fwd) in the TOP 30% of the label")
    P("               minus the BOTTOM 30%, thresholded per slot so both cells")
    P("               have identical size and identical time-of-day composition.")
    P(f"{'inst':<6}{'selector':<26}{'n':>8}  {'contrast':<28}")
    real: dict[str, float] = {}
    for i in INSTR:
        for lab, tpl in (("cohz (coherence z)", "cohz_{}"),
                         ("coh  (raw coherence)", "coh_{}"),
                         ("rvz  (VOLATILITY, KT2)", "rvz_{}")):
            s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", tpl.format(i), "mfo"])
            v = S.block_boot_regime_contrast(s, f"past_{i}_{W}", f"fwd_{i}_{H}",
                                             tpl.format(i), rng, NBOOT, rate=RATE)
            if tpl == "cohz_{}":
                real[i] = v[0]
            P(f"{i:<6}{lab:<26}{len(s):>8,}  {S.fmt_ci(v):<28}")
    P("")

    # ---- what the cells actually look like -------------------------------- #
    P("--- inside the cells (cohz selector): what differs besides momentum? ---")
    P(f"{'inst':<6}{'cell':<8}{'n':>8}{'mean coh':>10}{'mean rv(bp)':>13}"
      f"{'corr(past,fwd)':>16}{'mean |past| bp':>16}")
    for i in PRIMARY:
        s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", f"cohz_{i}", "mfo"])
        hi, lo = S._split_by_rate(s[f"cohz_{i}"].to_numpy(float),
                                  s["mfo"].to_numpy(float), RATE)
        for nm, m in (("high", hi), ("low", lo)):
            g = s[m]
            P(f"{i:<6}{nm:<8}{len(g):>8,}{g[f'coh_{i}'].mean():>10.3f}"
              f"{1e4 * g[f'rv_{i}'].mean():>13.2f}"
              f"{S.within_slot_corr(g[f'past_{i}_{W}'].to_numpy(float), g[f'fwd_{i}_{H}'].to_numpy(float), g['mfo'].to_numpy(float)):>+16.4f}"
              f"{1e4 * g[f'past_{i}_{W}'].abs().mean():>16.2f}")
    P("")

    # ---- sensitivity: selection rate and era ------------------------------- #
    P("--- sensitivity: matched selection rate (descriptive slope, not an argmax) ---")
    P("    " + f"{'inst':<6}" + "".join(f"{'rate ' + f'{r:.0%}':>14}"
                                        for r in (0.20, 0.30, 0.40)))
    for i in INSTR:
        s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", f"cohz_{i}", "mfo"])
        row = [S.regime_contrast(s[f"past_{i}_{W}"].to_numpy(float),
                                 s[f"fwd_{i}_{H}"].to_numpy(float),
                                 s[f"cohz_{i}"].to_numpy(float),
                                 s["mfo"].to_numpy(float), rate=r)
               for r in (0.20, 0.30, 0.40)]
        P("    " + f"{i:<6}" + "".join(f"{v:>+14.4f}" for v in row))
    P("")
    P("--- era split (cohz selector, rate 30%) ---")
    for i in INSTR:
        s = d.dropna(subset=[f"past_{i}_{W}", f"fwd_{i}_{H}", f"cohz_{i}", "mfo"])
        for era, m in (("2011-2018", s["date"].dt.year <= 2018),
                       ("2019-2026", s["date"].dt.year >= 2019)):
            v = S.block_boot_regime_contrast(s[m], f"past_{i}_{W}", f"fwd_{i}_{H}",
                                             f"cohz_{i}", rng, NBOOT, rate=RATE)
            P(f"  {i:<4}{era:<12}{int(m.sum()):>8,}  {S.fmt_ci(v)}")
    P("")

    # ---- KT3: rule-18 re-pairing null -------------------------------------- #
    P("--- KT3: rule-18 re-pairing null (dollar path swapped to another session ---")
    P("---      of the same calendar year; whole pipeline recomputed) ---")
    sess = pd.DatetimeIndex(F.sessions_of(panel))
    draws = {i: [] for i in INSTR}
    for k in range(ndraw):
        perm = S.repair_sessions(sess, rng)
        dn = F.decision_frame(repaired_panel(panel, perm), instruments=INSTR)
        c = contrasts(dn, "cohz_{}")
        for i in INSTR:
            draws[i].append(c[i])
        if (k + 1) % 10 == 0:
            print(f"  null draw {k + 1}/{ndraw}")
    P(f"{'inst':<6}{'real':>10}{'null mean':>12}{'null sd':>10}{'null p05':>10}"
      f"{'null p95':>10}{'z':>8}{'frac >= real':>14}")
    for i in INSTR:
        a = np.array(draws[i], float)
        z = (real[i] - a.mean()) / a.std(ddof=1) if a.std(ddof=1) > 0 else np.nan
        P(f"{i:<6}{real[i]:>+10.4f}{a.mean():>+12.4f}{a.std(ddof=1):>10.4f}"
          f"{np.percentile(a, 5):>+10.4f}{np.percentile(a, 95):>+10.4f}"
          f"{z:>8.2f}{float((a >= real[i]).mean()):>14.3f}")
    P("")
    P("    Reading the null (workspace convention): a null CENTRED AT THE REAL VALUE")
    P("    means the label is a rarity/turnover filter -- any similar-shaped label")
    P("    would do as well. A null centred at ZERO with the real value outside the")
    P("    band means genuine contemporaneous cross-asset information.")
    P("")

    txt = "\n".join(L)
    print(txt)
    (OUT / "factor_coherence.txt").write_text(txt, encoding="utf-8")
    print(f"\nwrote {OUT / 'factor_coherence.txt'}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
