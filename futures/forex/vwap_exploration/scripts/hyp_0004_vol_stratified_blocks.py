"""HYP-0004 / EXP-0004 — is finding C's liquidity-block shape a VOLATILITY gradient?

Finding C says anchor displacement REVERTS in the thin blocks and CONTINUES in
the London/NY overlap.  That split is matched on time of day only -- trivially,
since the blocks ARE time-of-day windows -- and LEARNINGS 2026-07-31c showed an
exactly slot-matched split can still inherit a volatility gradient that is doing
all the work.  This run recomputes the block contrast WITHIN strata of a causal
absolute realised volatility, and reports the cells' volatility ratio before and
after so a collapse can be attributed rather than guessed at.

Nothing about the feature, target, threshold, entry convention or horizon changes
(rules 1, 2, 15).  The single variable is the estimand's conditioning set.

Run:  python -u -m futures.forex.vwap_exploration.scripts.hyp_0004_vol_stratified_blocks [6E|6B]
Out:  artifacts/runs/EXP-0004/volstrat_<product>.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import frame as F
from futures.forex.vwap_exploration.core import stats as S
from futures.forex.vwap_exploration.core import vol as VOL
from futures.forex.vwap_exploration.core import vwap as V

RUN = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0004"

Z_ENTRY = 1.0
BLOCKS = ("asia", "ldn_am", "overlap", "ny_pm")
CELL_A, CELL_B = "asia", "overlap"          # the finding-C contrast
NBINS_PRIMARY = 5
NBINS_ROBUST = (3, 10)
MIN_CELL = 30
NBOOT = 400
MIN_FRAC_LOOSE = 0.25
RV = f"rv_{VOL.WINDOW}"
RV_LAG = f"rv_lag_{VOL.WINDOW}"
RV_LOOSE = f"rv_{VOL.WINDOW}_loose"


def build_run_panel(product: str, scope: str = "explore") -> pd.DataFrame:
    """The decision panel plus the no-anchor arm and the volatility conditioners.

    Shared with HYP-0005 so both runs measure the same thing on the same rows.
    """
    panel = F.build_panel(product, scope=scope)
    panel["y30"] = panel["fwd_30_pip"]
    sc = V.causal_slot_scale(panel, "past_30", lookback=V.SLOT_LOOKBACK,
                             min_frac=V.SLOT_MIN_FRAC)
    with np.errstate(invalid="ignore", divide="ignore"):
        panel["dev_past30_z"] = np.where(sc > 0, panel["past_30"].to_numpy() / sc,
                                         np.nan)
    panel = panel.merge(VOL.realized_vol(product, scope=scope),
                        on=["sdate", "mfo"], how="left")
    # A more permissive coverage floor for the rule-9a sensitivity arm. The mean
    # of |1-minute change| over the PRESENT pairs is still an unbiased estimate of
    # the per-minute volatility with far fewer than 30 pairs, so the 0.5 floor is
    # a defensible default but not a forced one.
    loose = VOL.realized_vol(product, scope=scope, min_frac=MIN_FRAC_LOOSE)
    return panel.merge(loose[["sdate", "mfo", RV]].rename(columns={RV: RV_LOOSE}),
                       on=["sdate", "mfo"], how="left")


def _bets(panel: pd.DataFrame, zcol: str) -> pd.DataFrame:
    """The EXP-0002 bet, unchanged: fade |z| >= 1, enter open(m+1), exit close(m+30)."""
    d = panel.dropna(subset=[zcol, "y30"])
    d = d.loc[d[zcol].abs() >= Z_ENTRY]
    out = d[["sdate", "mfo", "block", "year", RV, RV_LAG, RV_LOOSE]].copy()
    out["pnl"] = -np.sign(d[zcol].to_numpy()) * d["y30"].to_numpy()
    # Risk-equalised P&L for cross-product comparison (rule 12: equal-risk bets
    # are sized inversely to the product's own dispersion). `scale_vwap` is the
    # causal same-slot displacement scale in PRICE units; dividing by it makes the
    # P&L a unit-free fraction of a typical displacement, so 6E, 6B and 6J can be
    # placed side by side without ever comparing two products' "pips".
    scale_pip = d["scale_vwap"].to_numpy() / D.pip_size(d["product"].iloc[0])
    with np.errstate(invalid="ignore", divide="ignore"):
        out["pnl_r"] = np.where(scale_pip > 0, out["pnl"].to_numpy() / scale_pip,
                                np.nan)
    return out


def _contrast(bets: pd.DataFrame, covcol: str, nbins: int, rng,
              nboot: int = 0, a: str = CELL_A, b: str = CELL_B,
              pnlcol: str = "pnl") -> dict:
    """Raw and volatility-stratified `a - b` contrast, with a session-block CI."""
    d = bets.dropna(subset=[pnlcol, covcol])
    d = d.loc[d["block"].isin([a, b])].reset_index(drop=True)
    bins, edges = S.quantile_bins(d[covcol].to_numpy(), nbins)
    out = S.stratified_contrast(d[pnlcol].to_numpy(), d["block"].to_numpy(), bins,
                                a, b, cov=d[covcol].to_numpy(), min_cell=MIN_CELL)
    out["nbins"] = nbins
    out["lo_raw"] = out["hi_raw"] = out["lo_adj"] = out["hi_adj"] = np.nan
    if nboot:
        # Resample whole SESSIONS; the bin EDGES are held fixed so the bootstrap
        # resamples the data and not the stratification.
        work = d.assign(_bin=bins).rename(columns={pnlcol: "_pnl"})

        def _stat(pnl, blk, bn):
            r = S.stratified_contrast(pnl, blk, bn, a, b, min_cell=MIN_CELL)
            return r["raw"], r["adj"]

        keys, inv = np.unique(work["sdate"].to_numpy(), return_inverse=True)
        order = np.argsort(inv, kind="mergesort")
        inv_s = inv[order]
        starts = np.r_[0, np.flatnonzero(np.diff(inv_s)) + 1, len(inv_s)]
        slices = [order[starts[i]:starts[i + 1]] for i in range(len(keys))]
        pnl = work["_pnl"].to_numpy()
        blk = work["block"].to_numpy()
        bn = work["_bin"].to_numpy()
        raws, adjs = np.empty(nboot), np.empty(nboot)
        for i in range(nboot):
            pick = rng.integers(0, len(slices), len(slices))
            idx = np.concatenate([slices[p] for p in pick])
            raws[i], adjs[i] = _stat(pnl[idx], blk[idx], bn[idx])
        out["lo_raw"], out["hi_raw"] = S.ci(raws)
        out["lo_adj"], out["hi_adj"] = S.ci(adjs)
    return out


def run(product: str) -> dict:
    lines: list[str] = []
    rng = np.random.default_rng(20260803)

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 100)
    p(f"EXP-0004  HYP-0004  is finding C a VOLATILITY gradient?   {product}  "
      f"({D.CONTRACT[product]['name']})")
    p("=" * 100)
    p("Finding C: anchor displacement REVERTS in the thin blocks, CONTINUES in the")
    p("London/NY overlap. The split is matched on time of day only. This run asks")
    p("whether it survives being taken WITHIN strata of absolute realised volatility.")
    p("")
    p(f"bet unchanged from EXP-0002: fade |z| >= {Z_ENTRY}, entry open(m+1), exit "
      f"close(m+30), pips (${D.usd_per_pip(product):.2f}/pip).")

    panel = build_run_panel(product)
    p(f"decisions {len(panel):,}   sessions {panel['sdate'].nunique():,}   "
      f"{panel['sdate'].min().date()} -> {panel['sdate'].max().date()}   "
      f"(holdout {D.HOLDOUT_YEARS} sealed)")

    # ------------------------------------------------------------ rule 9a first
    p("")
    p("-- RULE 9a: coverage of the volatility measure, BY BLOCK ------------------")
    p("   A confounder that is missing preferentially in the thin blocks would")
    p("   re-create finding G's hidden filter inside the very control meant to")
    p("   remove a bias. Read this before any contrast below.")
    p("")
    p(f"   block      decisions   {RV} present   {RV_LAG} present   loose present"
      f"   mean {RV} (pip/min)")
    cov_ok = True
    for b in BLOCKS:
        sub = panel[panel["block"] == b]
        c1 = float(np.isfinite(sub[RV]).mean())
        c2 = float(np.isfinite(sub[RV_LAG]).mean())
        c3 = float(np.isfinite(sub[RV_LOOSE]).mean())
        p(f"   {b:<9}  {len(sub):9,}      {c1:7.4f}        {c2:7.4f}       "
          f"{c3:7.4f}          {np.nanmean(sub[RV]):8.4f}")
        if c1 < 0.90:
            cov_ok = False
    spread = (panel.groupby("block")[RV].apply(lambda s: float(np.isfinite(s).mean())))
    sp_loose = (panel.groupby("block")[RV_LOOSE]
                .apply(lambda s: float(np.isfinite(s).mean())))
    p(f"   across-block coverage spread: {spread.max() - spread.min():.4f}"
      f"  (loose floor {MIN_FRAC_LOOSE}: {sp_loose.max() - sp_loose.min():.4f})   "
      + ("OK" if cov_ok and (spread.max() - spread.min()) < 0.10
         else "*** NON-UNIFORM: the sensitivity arm below is the test of whether "
              "it matters"))
    if not cov_ok:
        p("   Cause: rv needs BOTH minutes of a 1-minute change, so pairwise coverage")
        p("   is roughly the square of the per-minute coverage. On thin 6B Asia hours")
        p("   that lands near the 0.5 floor. The deletion is SELECTIVE -- it removes")
        p("   the QUIETEST decisions of the thinnest block, i.e. one tail of the very")
        p("   variable being conditioned on. Finding G on a new statistic.")

    # ------------------------------------------------------------ the confound
    p("")
    p("-- THE CONFOUND, sized before it is removed -----------------------------")
    p("   Mean absolute 1-minute change over the 60 minutes ending at close(m).")
    p("")
    p("   block      mean rv (pip/min)   vs asia")
    base = float(np.nanmean(panel.loc[panel["block"] == "asia", RV]))
    for b in BLOCKS:
        mv = float(np.nanmean(panel.loc[panel["block"] == b, RV]))
        p(f"   {b:<9}  {mv:12.4f}        {mv / base:6.2f}x")

    # ------------------------------------------------------------ reproduce C
    p("")
    p("-- RULE 23: reproduce finding C's unadjusted block table -----------------")
    p("   anchor    block       per-bet pip    cl-t        n       mean rv")
    raw_tbl = {}
    for a in ("vwap", "past30"):
        bt = _bets(panel, f"dev_{a}_z")
        for b in BLOCKS:
            sub = bt[bt["block"] == b]
            m, se, t, n = S.cluster_t(sub["pnl"].to_numpy(), sub["sdate"].to_numpy())
            raw_tbl[(a, b)] = m
            p(f"   {a:<8}  {b:<9}  {m:+11.4f}   {t:+7.2f}  {n:8,}   "
              f"{np.nanmean(sub[RV]):8.4f}")

    # ------------------------------------------------------------ PRIMARY
    p("")
    p("-- PRIMARY (declared in HYP-0004): vwap, asia - overlap, rv_60, 5 strata --")
    bets_v = _bets(panel, "dev_vwap_z")
    prim = _contrast(bets_v, RV, NBINS_PRIMARY, rng, nboot=NBOOT)
    p(f"   C_raw  {prim['raw']:+.4f} pip   boot95 [{prim['lo_raw']:+.4f}, "
      f"{prim['hi_raw']:+.4f}]     (n_asia {prim['n_a']:,}  n_overlap {prim['n_b']:,})")
    p(f"   C_adj  {prim['adj']:+.4f} pip   boot95 [{prim['lo_adj']:+.4f}, "
      f"{prim['hi_adj']:+.4f}]")
    p(f"   retained  {prim['adj'] / prim['raw']:.1%} of the unadjusted contrast")
    p("")
    p("   Did the control remove a confound, or merely weaken the split?")
    p(f"     volatility ratio asia/overlap   RAW {prim['cov_ratio_raw']:.4f}"
      f"  ->  ADJUSTED {prim['cov_ratio_adj']:.4f}   (1.0 = perfectly matched)")
    p(f"     effective bet count             n_eff {prim['n_eff']:,.1f} vs pooled "
      f"harmonic {prim['n_harm']:,.1f}  = {prim['retention']:.1%} retained")
    p("")
    p("   per-stratum detail (the estimate lives only where BOTH cells are populated):")
    p("      q   n_asia  n_overlap    mean_asia  mean_overlap    rv_asia  rv_overlap"
      "      weight")
    for r in prim["rows"]:
        p(f"     q{r['q'] + 1}  {r['n_a']:7,} {r['n_b']:10,}   {r['mean_a']:+10.4f}  "
          f"{r['mean_b']:+12.4f}   {r['cov_a']:8.4f}  {r['cov_b']:10.4f}  "
          f"{r['w']:10.1f}")

    # ------------------------------------------------------------ MIRROR
    p("")
    p("-- MIRROR ARM (mandatory): the OTHER label conditioned on this one -------")
    p("   Volatility contrast q5 - q1, taken WITHIN blocks and standardised across")
    p("   them. If block dies within volatility and volatility survives within")
    p("   block, the operative variable is volatility; if both die, neither label")
    p("   carries anything.")
    bv = bets_v.dropna(subset=["pnl", RV]).reset_index(drop=True)
    qb, _ = S.quantile_bins(bv[RV].to_numpy(), NBINS_PRIMARY)
    bv = bv.assign(_q=qb)
    hi_lo = bv[bv["_q"].isin([0, NBINS_PRIMARY - 1])].copy()
    hi_lo["_vg"] = np.where(hi_lo["_q"] == NBINS_PRIMARY - 1, "hi", "lo")
    blk_codes = pd.factorize(hi_lo["block"])[0]
    mir = S.stratified_contrast(hi_lo["pnl"].to_numpy(), hi_lo["_vg"].to_numpy(),
                                blk_codes, "hi", "lo", cov=hi_lo[RV].to_numpy(),
                                min_cell=MIN_CELL)
    p("")
    p(f"   volatility contrast (q5 - q1)   raw {mir['raw']:+.4f} pip   "
      f"within-block-standardised {mir['adj']:+.4f} pip   "
      f"retained {mir['retention']:.1%}")
    p("      block      n_hi    n_lo     mean_hi    mean_lo")
    names = dict(enumerate(pd.factorize(hi_lo["block"])[1]))
    for r in mir["rows"]:
        p(f"      {names[r['q']]:<9} {r['n_a']:7,} {r['n_b']:7,}  {r['mean_a']:+10.4f} "
          f"{r['mean_b']:+10.4f}")

    # ------------------------------------------------------------ robustness
    p("")
    p("-- ROBUSTNESS: 2 anchors x 3 volatility measures x 3 stratum counts ------")
    p("   `rv_lag_60` covers minutes (m-90, m-30], so it shares NO minute with the")
    p("   30-minute signal window and cannot attenuate the past30 arm mechanically.")
    p(f"   `{RV_LOOSE}` is the rule-9a sensitivity arm: identical statistic at a")
    p(f"   {MIN_FRAC_LOOSE} coverage floor instead of {VOL.MIN_FRAC}, which restores most of the")
    p("   deleted thin-block decisions. If the contrast moves materially between the")
    p("   two floors, the answer is a function of the coverage rule, not the market.")
    p("")
    p("   anchor   cov          bins    C_raw      C_adj    adj/raw   rv ratio "
      "raw->adj   n_eff%")
    rob = {}
    for a in ("vwap", "past30"):
        bt = _bets(panel, f"dev_{a}_z")
        for covcol in (RV, RV_LAG, RV_LOOSE):
            for nb in (NBINS_PRIMARY, *NBINS_ROBUST):
                c = _contrast(bt, covcol, nb, rng)
                rob[(a, covcol, nb)] = c
                ratio = c["adj"] / c["raw"] if c["raw"] else np.nan
                p(f"   {a:<8} {covcol:<12} {nb:<5} {c['raw']:+9.4f} {c['adj']:+10.4f} "
                  f"{ratio:+9.2f}   {c['cov_ratio_raw']:.3f} -> "
                  f"{c['cov_ratio_adj']:.3f}    {c['retention']:6.1%}")

    # ------------------------------------------------------------ per-slot view
    p("")
    p("-- BLOCK-FREE VIEW: across the 46 decision slots, does P&L track vol? ----")
    p("   This does not use the four-block partition at all.")
    slot = bets_v.groupby("mfo").agg(pnl=("pnl", "mean"), rv=(RV, "mean"),
                                     n=("pnl", "size")).reset_index()
    slot = slot[slot["n"] >= 100].dropna(subset=["pnl", "rv"])
    sp = S.spearman(slot["rv"].to_numpy(), slot["pnl"].to_numpy())
    pe = float(np.corrcoef(slot["rv"], slot["pnl"])[0, 1])
    p(f"   {len(slot)} slots   Spearman(mean rv, mean per-bet pip) {sp:+.4f}   "
      f"Pearson {pe:+.4f}")
    bt30 = _bets(panel, "dev_past30_z")
    slot2 = bt30.groupby("mfo").agg(pnl=("pnl", "mean"), rv=(RV, "mean"),
                                    n=("pnl", "size")).reset_index()
    slot2 = slot2[slot2["n"] >= 100].dropna(subset=["pnl", "rv"])
    p(f"   past30: {len(slot2)} slots   Spearman "
      f"{S.spearman(slot2['rv'].to_numpy(), slot2['pnl'].to_numpy()):+.4f}   "
      f"Pearson {float(np.corrcoef(slot2['rv'], slot2['pnl'])[0, 1]):+.4f}")

    # ------------------------------------------------------------ KILL TEST
    p("")
    p("-- KILL TEST (declared in HYP-0004 before the run) -----------------------")
    k1 = prim["adj"] > 0
    k2 = prim["adj"] >= 0.50 * prim["raw"]
    k3 = not (prim["lo_adj"] <= 0 <= prim["hi_adj"])
    k4 = (abs(prim["cov_ratio_adj"] - 1.0) < 0.5 * abs(prim["cov_ratio_raw"] - 1.0)
          and prim["retention"] >= 0.50)
    p(f"   1. sign       C_adj > 0?                        "
      f"{'PASS' if k1 else 'FAIL'}   (C_adj {prim['adj']:+.4f})")
    p(f"   2. magnitude  C_adj >= 0.50 * C_raw?            "
      f"{'PASS' if k2 else 'FAIL'}   ({prim['adj']:+.4f} vs "
      f"{0.50 * prim['raw']:+.4f})")
    p(f"   3. signif.    C_adj CI excludes 0?              "
      f"{'PASS' if k3 else 'FAIL'}   ([{prim['lo_adj']:+.4f},{prim['hi_adj']:+.4f}])")
    p(f"   4. control    vol ratio moved to 1 AND n_eff>=50%?  "
      f"{'PASS' if k4 else 'FAIL'}   (|{prim['cov_ratio_adj']:.3f}-1| vs "
      f"0.5*|{prim['cov_ratio_raw']:.3f}-1|, n_eff {prim['retention']:.1%})")
    p("")
    p("   Arms 1-2 are the REJECT gate (finding C invalidated as a liquidity")
    p("   effect). Arms 3-4 gate the UPGRADE from provisional to confirmed; arm 4")
    p("   failing alone means the control was uninformative, not that C is dead.")
    sec = prim["adj"] > 0 and rob[("past30", RV, NBINS_PRIMARY)]["adj"] <= 0
    p(f"   SECONDARY (not part of the kill): dissociation survives? "
      f"{'YES' if sec else 'NO'}   "
      f"(vwap C_adj {prim['adj']:+.4f}, past30 C_adj "
      f"{rob[('past30', RV, NBINS_PRIMARY)]['adj']:+.4f})")

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / f"volstrat_{product}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RUN / f'volstrat_{product}.txt'}")
    return {"product": product, "prim": prim, "k": (k1, k2, k3, k4),
            "mirror": mir, "rob": rob, "raw_tbl": raw_tbl, "sec": sec,
            "slot_ic": sp}


def main(argv):
    prods = [argv[1]] if len(argv) > 1 else list(D.PRODUCTS)
    out = [run(pr) for pr in prods]
    if len(out) > 1:
        print("\n" + "=" * 100)
        print("SUMMARY  (arms: sign / magnitude / significance / control-worked)")
        for r in out:
            pm = r["prim"]
            print(f"  {r['product']}  C_raw {pm['raw']:+.4f} -> C_adj {pm['adj']:+.4f} "
                  f"[{pm['lo_adj']:+.4f},{pm['hi_adj']:+.4f}]  "
                  f"rv ratio {pm['cov_ratio_raw']:.3f}->{pm['cov_ratio_adj']:.3f}  "
                  f"arms {['PASS' if x else 'FAIL' for x in r['k']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
