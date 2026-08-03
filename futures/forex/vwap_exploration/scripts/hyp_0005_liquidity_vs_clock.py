"""HYP-0005 / EXP-0005 — is finding C's block shape LIQUIDITY, or is it the ET CLOCK?

EXP-0004 showed the `asia` - `overlap` contrast is not a volatility gradient. It
could not say WHY the block label matters, because on 6E and 6B "thin book" and
"these ET hours" are the same thing -- their asia/overlap liquidity ratios agree
to three decimals (0.131 vs 0.130).

6J breaks the tie. The yen leg trades in Tokyo, so 6J's Asia block carries 2.4x
more of its session volume relative to its own overlap (ratio 0.313). If the
mechanism is book thinness, 6J's contrast should be materially SMALLER. If the
mechanism is the clock, 6J should look like the other two.

6J is a DOSE, not a reversal: even for 6J the Asia block is below flat and the
overlap is still its busiest, because the USD leg and the venue are American on
every one of these contracts. That asymmetry is declared in HYP-0005 and bounds
what a null result can mean.

Run:  python -u -m futures.forex.vwap_exploration.scripts.hyp_0005_liquidity_vs_clock
Out:  artifacts/runs/EXP-0005/liqclock.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import stats as S
from futures.forex.vwap_exploration.scripts.hyp_0004_vol_stratified_blocks import (
    BLOCKS, CELL_A, CELL_B, MIN_CELL, NBINS_PRIMARY, NBINS_ROBUST, NBOOT, RV,
    RV_LAG, RV_LOOSE, Z_ENTRY, _bets, _contrast, build_run_panel,
)

RUN = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0005"

PRODUCTS = ("6E", "6B", "6J")
NEW = "6J"
BENCH = ("6E", "6B")
GATE = 0.60                     # H_liquidity supported if R(6J) < GATE * mean(R(6E),R(6B))
BLOCK_MINUTES = {"asia": 540, "ldn_am": 300, "overlap": 240, "ny_pm": 300}


def _liquidity_shares(product: str) -> dict:
    """Per-minute share of session volume by block, normalised so flat == 1.0.

    Computed over ALL bars, matching the premise table declared in HYP-0005. Using
    the decision panel instead would sample only the 46 `:29`/`:59` minutes, which
    is a different quantity and shifted the 6B ratio by ~7%.
    """
    bars, _ = D.load_bars(product, scope="explore")
    blk = D.block_of_mod(bars["mod"].to_numpy())
    v = bars["volume"].to_numpy(float)
    tot = v.sum()
    return {b: (v[blk == b].sum() / tot) / (mins / D.SESSION_MINUTES)
            for b, mins in BLOCK_MINUTES.items()}


def run() -> int:
    lines: list[str] = []
    rng = np.random.default_rng(20260803)

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 100)
    p("EXP-0005  HYP-0005  liquidity or the clock?   6E / 6B / 6J")
    p("=" * 100)
    p("EXP-0004 established the asia-overlap contrast is not a volatility gradient.")
    p("This run asks what the BLOCK label is a proxy for. 6E and 6B cannot answer it")
    p("(identical liquidity clocks); 6J has a materially thicker Asia block.")
    p("")
    p(f"bet unchanged: fade |z| >= {Z_ENTRY}, entry open(m+1), exit close(m+30).")
    p("Cross-product magnitudes are RISK-EQUALISED (rule 12): P&L divided by that")
    p("decision's causal same-slot displacement scale, so no two products' native")
    p("units are ever compared. Native units and dollars reported alongside.")

    panels, bets, liq = {}, {}, {}
    for prod in PRODUCTS:
        panels[prod] = build_run_panel(prod)
        bets[prod] = _bets(panels[prod], "dev_vwap_z")
        liq[prod] = _liquidity_shares(prod)

    # ------------------------------------------------------------ rule 9a
    p("")
    p("-- RULE 9a: 6J is a never-before-loaded archive. Gate it BEFORE reading -----")
    p("   product  decisions  sessions   dates                    rv_60 asia cov")
    for prod in PRODUCTS:
        pl = panels[prod]
        asia_cov = float(np.isfinite(pl.loc[pl["block"] == "asia", RV]).mean())
        p(f"   {prod:<8} {len(pl):9,}  {pl['sdate'].nunique():7,}   "
          f"{pl['sdate'].min().date()} -> {pl['sdate'].max().date()}   {asia_cov:.4f}")
    p("")
    p("   6J's Asia rv coverage should BEAT 6B's if the liquidity premise is true --")
    p("   this is a check on the premise, not a formality. Per-block minute coverage")
    p("   and volume intensity (share per minute, flat = 1.00x):")
    p("")
    p("   block      " + "".join(f"{prod:>18}" for prod in PRODUCTS))
    for b in BLOCKS:
        cells = []
        for prod in PRODUCTS:
            pl = panels[prod]
            cov = float(np.isfinite(pl.loc[pl["block"] == b, RV]).mean())
            cells.append(f"{liq[prod][b]:.2f}x cov {cov:.3f}")
        p(f"   {b:<9}  " + "".join(f"{c:>18}" for c in cells))
    p("")
    ratios = {prod: liq[prod]["asia"] / liq[prod]["overlap"] for prod in PRODUCTS}
    p("   THE DOSE -- asia/overlap liquidity ratio:  "
      + "   ".join(f"{prod} {ratios[prod]:.3f}" for prod in PRODUCTS))
    p(f"   6J is {ratios[NEW] / np.mean([ratios[q] for q in BENCH]):.2f}x less thin "
      "in Asia than the 6E/6B benchmark.")

    # ------------------------------------------------------------ rule 23
    p("")
    p("-- RULE 23: 6E/6B must reproduce EXP-0004 after the 6J code changes --------")
    p("   (a per-product reporting unit touches a shared code path)")
    p("")
    p("   product   C_raw       C_adj      EXP-0004 C_adj    agree?")
    EXP4 = {"6E": (0.5300, 0.5657), "6B": (0.3776, 0.2210)}
    repro_ok = True
    prim = {}
    for prod in PRODUCTS:
        c = _contrast(bets[prod], RV, NBINS_PRIMARY, rng, nboot=NBOOT)
        prim[prod] = c
        if prod in EXP4:
            ok = (abs(c["raw"] - EXP4[prod][0]) < 1e-4
                  and abs(c["adj"] - EXP4[prod][1]) < 1e-4)
            repro_ok &= ok
            p(f"   {prod:<8} {c['raw']:+10.4f}  {c['adj']:+10.4f}   "
              f"{EXP4[prod][1]:+12.4f}      {'PASS' if ok else '*** FAIL'}")
        else:
            p(f"   {prod:<8} {c['raw']:+10.4f}  {c['adj']:+10.4f}   "
              f"{'(new)':>12}")
    p(f"   -> {'reproduced to 4dp' if repro_ok else '*** REPRODUCTION FAILED'}")

    # ------------------------------------------------------------ PRIMARY
    p("")
    p("-- PRIMARY (declared in HYP-0005): risk-equalised asia - overlap ----------")
    p("   R(p) = volatility-matched contrast in units of the same-slot displacement")
    p("   scale. Native pips and dollars shown for context only.")
    p("")
    p("   product      R_raw       R_adj        boot95 CI            native C_adj"
      "     $/bet")
    R = {}
    for prod in PRODUCTS:
        c = _contrast(bets[prod], RV, NBINS_PRIMARY, rng, nboot=NBOOT, pnlcol="pnl_r")
        R[prod] = c
        usd = prim[prod]["adj"] * D.usd_per_pip(prod)
        p(f"   {prod:<8} {c['raw']:+10.4f}  {c['adj']:+10.4f}   "
          f"[{c['lo_adj']:+.4f},{c['hi_adj']:+.4f}]   {prim[prod]['adj']:+12.4f}"
          f"  {usd:+8.2f}")
    bench = float(np.mean([R[q]["adj"] for q in BENCH]))
    p("")
    p(f"   benchmark B = mean(R(6E), R(6B)) = {bench:+.4f}")
    p(f"   gate       {GATE:.2f} * B          = {GATE * bench:+.4f}")
    p(f"   R(6J)                            = {R[NEW]['adj']:+.4f}   "
      f"= {R[NEW]['adj'] / bench:.2f} x B")
    p(f"   volatility ratio asia/overlap on 6J: {R[NEW]['cov_ratio_raw']:.3f} -> "
      f"{R[NEW]['cov_ratio_adj']:.3f}   n_eff {R[NEW]['retention']:.1%}")

    # ------------------------------------------------------------ full block table
    p("")
    p("-- The full block profile, risk-equalised (the shape, not just the contrast) --")
    p("   product   " + "".join(f"{b:>13}" for b in BLOCKS))
    prof = {}
    for prod in PRODUCTS:
        row, bt = [], bets[prod]
        for b in BLOCKS:
            sub = bt[bt["block"] == b]
            m, se, t, n = S.cluster_t(sub["pnl_r"].to_numpy(), sub["sdate"].to_numpy())
            row.append((m, t))
        prof[prod] = [r[0] for r in row]
        p(f"   {prod:<9} " + "".join(f"{m:+8.4f}(t{t:+.1f})".rjust(13)
                                     for m, t in row))

    # ------------------------------------------------------------ mirror arm
    p("")
    p("-- MIRROR ARM on all three: volatility contrast standardised WITHIN blocks --")
    p("   product   raw q5-q1    within-block    reading")
    for prod in PRODUCTS:
        bv = bets[prod].dropna(subset=["pnl_r", RV]).reset_index(drop=True)
        qb, _ = S.quantile_bins(bv[RV].to_numpy(), NBINS_PRIMARY)
        bv = bv.assign(_q=qb)
        hl = bv[bv["_q"].isin([0, NBINS_PRIMARY - 1])].copy()
        hl["_vg"] = np.where(hl["_q"] == NBINS_PRIMARY - 1, "hi", "lo")
        mir = S.stratified_contrast(hl["pnl_r"].to_numpy(), hl["_vg"].to_numpy(),
                                    pd.factorize(hl["block"])[0], "hi", "lo",
                                    min_cell=MIN_CELL)
        rd = ("volatility DIES within block" if abs(mir["adj"]) < abs(mir["raw"])
              else "volatility SURVIVES within block")
        p(f"   {prod:<9} {mir['raw']:+10.4f}   {mir['adj']:+12.4f}    {rd}")

    # ------------------------------------------------------------ block-free arm
    p("")
    p("-- BLOCK-FREE ARM: does 6J's per-slot profile follow the CLOCK or LIQUIDITY? --")
    p("   6E and 6B share a liquidity clock, so corr(6E, 6B) is the BENCHMARK for")
    p("   what agreement looks like when the clock explanation is true by")
    p("   construction. If 6J agrees just as well, the clock explains it.")
    p("")
    slotp, slotl = {}, {}
    for prod in PRODUCTS:
        bt = bets[prod]
        g = bt.groupby("mfo").agg(pnl=("pnl_r", "mean"), n=("pnl_r", "size"))
        g = g[g["n"] >= 100]
        slotp[prod] = g["pnl"]
        pl = panels[prod]
        vg = pl.groupby("mfo")["volume"].sum()
        slotl[prod] = vg / vg.sum()
    p("   per-slot P&L profile correlation (46 decision slots):")
    for i, a in enumerate(PRODUCTS):
        for b in PRODUCTS[i + 1:]:
            j = slotp[a].index.intersection(slotp[b].index)
            sp = S.spearman(slotp[a][j].to_numpy(), slotp[b][j].to_numpy())
            pe = float(np.corrcoef(slotp[a][j], slotp[b][j])[0, 1])
            tag = "  <-- BENCHMARK (same liquidity clock)" if {a, b} == set(BENCH) else ""
            p(f"     corr({a}, {b})   Spearman {sp:+.4f}   Pearson {pe:+.4f}{tag}")
    p("")
    p("   per-slot P&L vs that product's OWN per-slot liquidity share:")
    dem = []
    for prod in PRODUCTS:
        j = slotp[prod].index
        lq = slotl[prod][j]
        sp = S.spearman(lq.to_numpy(), slotp[prod].to_numpy())
        p(f"     {prod}   Spearman(liquidity share, per-bet R) {sp:+.4f}")
        dem.append(pd.DataFrame({
            "l": lq.to_numpy() - lq.to_numpy().mean(),
            "y": slotp[prod].to_numpy() - slotp[prod].to_numpy().mean()}))
    dd = pd.concat(dem)
    p(f"     POOLED, within-product demeaned:  Spearman "
      f"{S.spearman(dd['l'].to_numpy(), dd['y'].to_numpy()):+.4f}   "
      f"Pearson {float(np.corrcoef(dd['l'], dd['y'])[0, 1]):+.4f}")

    # ------------------------------------------------------------ robustness
    p("")
    p("-- ROBUSTNESS on 6J: 3 volatility measures x 3 stratum counts --------------")
    p("   cov          bins    R_raw       R_adj    adj/raw   rv ratio raw->adj  n_eff%")
    for covcol in (RV, RV_LAG, RV_LOOSE):
        for nb in (NBINS_PRIMARY, *NBINS_ROBUST):
            c = _contrast(bets[NEW], covcol, nb, rng, pnlcol="pnl_r")
            ratio = c["adj"] / c["raw"] if c["raw"] else np.nan
            p(f"   {covcol:<12} {nb:<5} {c['raw']:+10.4f} {c['adj']:+10.4f} "
              f"{ratio:+9.2f}   {c['cov_ratio_raw']:.3f} -> {c['cov_ratio_adj']:.3f}"
              f"   {c['retention']:6.1%}")

    # ------------------------------------------------------------ KILL TEST
    p("")
    p("-- KILL TEST (declared in HYP-0005 before 6J was loaded) -------------------")
    rj, lo, hi = R[NEW]["adj"], R[NEW]["lo_adj"], R[NEW]["hi_adj"]
    gate = GATE * bench
    inconclusive = (lo <= 0 <= hi) and (lo <= gate <= hi)
    liq_sup = (rj < gate) and not inconclusive
    clock_sup = (rj >= gate) and not (lo <= 0 <= hi)
    p(f"   R(6J) {rj:+.4f}  CI [{lo:+.4f}, {hi:+.4f}]   gate {GATE:.2f}*B = {gate:+.4f}")
    p("")
    p(f"   1. H_liquidity  R(6J) < 0.60*B ?              "
      f"{'SUPPORTED' if liq_sup else 'not supported'}")
    p(f"   2. H_clock      R(6J) >= 0.60*B and CI excl 0? "
      f"{'SUPPORTED' if clock_sup else 'not supported'}")
    p(f"   3. inconclusive CI contains BOTH 0 and the gate? "
      f"{'YES' if inconclusive else 'no'}")
    if rj < 0:
        p("   NOTE: R(6J) is NEGATIVE -- an INVERSION, not merely an attenuation.")
        p("   Reported separately per the hypothesis rather than folded into arm 1.")
    p("")
    if clock_sup:
        p("   => finding C keeps its SHAPE and LOSES its explanation on all three")
        p("      products; the inventory/thinness reading must be withdrawn.")
    elif liq_sup:
        p("   => the thinness mechanism survives its first asymmetric cross-product")
        p("      test: a thicker Asia really does carry a smaller contrast.")
    else:
        p("   => underpowered. Nothing is claimed in either direction (arm 3).")

    # -------------------------------------------------- POST-HOC diagnostics
    p("")
    p("=" * 100)
    p("POST-HOC (generated by this run; NOT preregistered; not evidence for HYP-0005)")
    p("=" * 100)

    p("")
    p("-- (i) The better-powered comparison the kill test did not declare ---------")
    p("   Arm 3 fired because R(6J)'s CI touches the GATE. The sharper question is")
    p("   whether R(6J) differs from the BENCHMARK -- a difference of two")
    p("   independent estimates, which deserves its own bootstrap rather than an")
    p("   eyeball of two CIs.")
    p("")
    diffs = {}
    for ref in BENCH:
        d_ref = bets[ref].dropna(subset=["pnl_r", RV])
        d_new = bets[NEW].dropna(subset=["pnl_r", RV])
        draws = np.empty(NBOOT)
        for i in range(NBOOT):
            vals = []
            for dd in (d_ref, d_new):
                keys = dd["sdate"].unique()
                pick = rng.choice(keys, size=len(keys), replace=True)
                samp = dd.set_index("sdate").loc[pick].reset_index()
                bn, _ = S.quantile_bins(samp[RV].to_numpy(), NBINS_PRIMARY)
                r = S.stratified_contrast(samp["pnl_r"].to_numpy(),
                                          samp["block"].to_numpy(), bn,
                                          CELL_A, CELL_B, min_cell=MIN_CELL)
                vals.append(r["adj"])
            draws[i] = vals[0] - vals[1]
        lo_d, hi_d = S.ci(draws)
        diffs[ref] = (float(np.nanmean(draws)), lo_d, hi_d)
        excl = not (lo_d <= 0 <= hi_d)
        p(f"   R({ref}) - R(6J) = {R[ref]['adj'] - R[NEW]['adj']:+.4f}   "
          f"boot95 [{lo_d:+.4f}, {hi_d:+.4f}]   "
          + ("DIFFERENT (CI excludes 0)" if excl else "not distinguishable"))
    p(f"   Also: R(6J)'s own CI upper bound {hi:+.4f} vs the benchmark B {bench:+.4f}"
      f"  -> B is {'OUTSIDE' if hi < bench else 'inside'} R(6J)'s interval.")

    p("")
    p("-- (ii) The pattern in the full block table, which fits all 12 cells -------")
    p("   Every product's STRONGEST reversion sits in the block where the COUNTER")
    p("   CURRENCY's own home market is SHUT, not in a fixed ET block:")
    p("")
    home = {"6E": ("Frankfurt/London", "asia"), "6B": ("London", "asia"),
            "6J": ("Tokyo", "ny_pm")}
    p("   product  counter-ccy home  its NIGHT block   R there      overlap cell")
    for prod in PRODUCTS:
        city, night = home[prod]
        bt = bets[prod]
        mn, _, tn, _ = S.cluster_t(
            bt.loc[bt["block"] == night, "pnl_r"].to_numpy(),
            bt.loc[bt["block"] == night, "sdate"].to_numpy())
        mo, _, to, _ = S.cluster_t(
            bt.loc[bt["block"] == "overlap", "pnl_r"].to_numpy(),
            bt.loc[bt["block"] == "overlap", "sdate"].to_numpy())
        best = max(BLOCKS, key=lambda b: float(np.nanmean(
            bt.loc[bt["block"] == b, "pnl_r"])))
        p(f"   {prod:<8} {city:<17} {night:<16} {mn:+.4f}(t{tn:+.1f})  "
          f"{mo:+.4f}(t{to:+.1f})   argmax={best}"
          + ("  MATCH" if best == night else "  no"))
    p("")
    p("   ET 12:00-16:59 ('ny_pm') is Tokyo 02:00-07:00; ET 18:00-02:59 ('asia') is")
    p("   London 23:00-07:59. So the two families are the SAME rule in different")
    p("   time zones, and the overlap cell -- where BOTH home markets are open -- is")
    p("   near-identical on all three products.")
    p("")
    p("   This is a POST-HOC pattern read off 12 cells after seeing them. It is a")
    p("   hypothesis, not a finding. The decisive test is the wider panel already")
    p("   downloaded (IDEA-0006): 6A/6N home markets fall INSIDE the `asia` block,")
    p("   6S inside `ldn_am`/`overlap`, 6C inside `overlap`/`ny_pm` -- which makes")
    p("   sharp, differing predictions per product. Logged, not claimed.")

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "liqclock.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RUN / 'liqclock.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
