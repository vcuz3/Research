"""HYP-0002 / EXP-0002 — does deviation from a session anchor predict forward return?

Entry-information only: no stop, no target, no barrier (rule 15). Entry is the
open of the bar AFTER the decision bar closes (rules 1, 2), exit is a bar close.

The deployable estimand is a per-bet mean with a session cluster-robust SE. The
signal is CAUSAL by construction -- `|dev_z| >= Z_ENTRY` where `dev_z` is scaled
by a trailing same-slot dispersion using only prior sessions -- so no full-sample
quantile ever decides what was tradable (rule 8). Quintiles are reported only as
a descriptive profile.

Run:  python -u -m futures.forex.vwap_exploration.scripts.hyp_0002_entry_information [6E|6B]
Out:  artifacts/runs/EXP-0002/entryinfo_<product>.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import frame as F
from futures.forex.vwap_exploration.core import stats as S
from futures.forex.vwap_exploration.core import vwap as V

RUN = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0002"

Z_ENTRY = 1.0
HORIZONS = ("30", "60", "120", "close")
BLOCKS = ("asia", "ldn_am", "overlap", "ny_pm")
NBOOT = 300


def _bet(df: pd.DataFrame, zcol: str, ycol: str, z_entry: float = Z_ENTRY):
    """The reversion bet: FADE the displacement. Returns the per-bet P&L frame."""
    d = df.dropna(subset=[zcol, ycol])
    sel = d[zcol].abs() >= z_entry
    d = d.loc[sel]
    out = d[["sdate", "mfo", "block", "year"]].copy()
    out["pnl"] = -np.sign(d[zcol].to_numpy()) * d[ycol].to_numpy()
    return out


def _cell(df: pd.DataFrame, zcol: str, ycol: str, rng, nboot: int = 0):
    """One (anchor, horizon, block) cell: per-bet mean + rank IC + contrast."""
    b = _bet(df, zcol, ycol)
    if len(b) < 200:
        return None
    m, se, t, n = S.cluster_t(b["pnl"].to_numpy(), b["sdate"].to_numpy())
    d = df.dropna(subset=[zcol, ycol])
    ic = S.spearman(d[zcol].to_numpy(), d[ycol].to_numpy())
    spread, prof = S.quantile_spread(d[zcol].to_numpy(), d[ycol].to_numpy(), 5)
    mcc = S.mean_count_corr(b["pnl"].to_numpy(), b["sdate"].to_numpy())
    bm, bt, nb = S.block_mean_t(b["pnl"].to_numpy(), b["sdate"].to_numpy())
    lo = hi = np.nan
    if nboot:
        samp = S.block_bootstrap(b, ["pnl"], lambda a: float(np.nanmean(a)), rng,
                                 nboot=nboot)
        lo, hi = S.ci(samp)
    return dict(n=n, mean=m, t=t, lo=lo, hi=hi, ic=ic, spread=spread, prof=prof,
                mcc=mcc, sess_mean=bm, sess_t=bt, nsess=nb)


def run(product: str) -> dict:
    lines: list[str] = []
    rng = np.random.default_rng(20260802)

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 96)
    p(f"EXP-0002  HYP-0002  anchor deviation -> forward return   {product}  "
      f"({D.CONTRACT[product]['name']})")
    p("=" * 96)
    p(f"entry |dev_z| >= {Z_ENTRY}, FADE the displacement; entry = open(m+1), "
      f"exit = close(m+H). P&L in pips (${D.usd_per_pip(product):.2f}/pip).")

    panel = F.build_panel(product, scope="explore")
    p(f"decisions {len(panel):,}   sessions {panel['sdate'].nunique():,}   "
      f"{panel['sdate'].min().date()} -> {panel['sdate'].max().date()}   "
      f"(holdout {D.HOLDOUT_YEARS} sealed)")
    for h in HORIZONS:
        panel[f"y{h}"] = panel[f"fwd_{h}_pip"]

    # The NO-ANCHOR degenerate arm: fade the trailing 30-minute return itself,
    # z-scored by the identical causal same-slot construction. This is the "score
    # the bare numerator" control (LEARNINGS 2026-07-27) for an anchor study --
    # `past_30` uses no session anchor, no averaging and no volume whatsoever, so
    # if it matches or beats the anchors, the anchor machinery is decoration on a
    # plain short-horizon reversal.
    sc = V.causal_slot_scale(panel, "past_30", lookback=V.SLOT_LOOKBACK,
                             min_frac=V.SLOT_MIN_FRAC)
    with np.errstate(invalid="ignore", divide="ignore"):
        panel["dev_past30_z"] = np.where(sc > 0, panel["past_30"].to_numpy() / sc,
                                         np.nan)

    # ------------------------------------------------------------ PRIMARY cell
    p("")
    p("-- PRIMARY (declared in HYP-0002): anchor=vwap, H=30min, pooled ----------")
    prim = _cell(panel, "dev_vwap_z", "y30", rng, nboot=NBOOT)
    p(f"   per-bet mean    {prim['mean']:+.4f} pip   cluster-t {prim['t']:+.2f}   "
      f"n {prim['n']:,}   boot95 [{prim['lo']:+.4f}, {prim['hi']:+.4f}]")
    p(f"   rank IC (dev_z vs fwd)  {prim['ic']:+.5f}       "
      f"quintile mean spread q5-q1  {prim['spread']:+.4f} pip")
    p(f"   quintile profile of fwd_30 by dev_z:  "
      + "  ".join(f"q{i + 1} {v:+.3f}" for i, v in enumerate(prim['prof'])))
    p("")
    p("   ESTIMAND CONTRAST (LEARNINGS 2026-08-01) -- reported, not used:")
    p(f"     per-bet mean {prim['mean']:+.4f} (t {prim['t']:+.2f}, n {prim['n']:,})  vs  "
      f"session-averaged {prim['sess_mean']:+.4f} (t {prim['sess_t']:+.2f}, "
      f"{prim['nsess']:,} sessions)")
    p(f"     corr(session mean, session count) = {prim['mcc']:+.4f}   "
      "[non-zero => the two estimands are not the same quantity]")

    # ------------------------------------------------------------ anchor x horizon
    p("")
    p("-- CONTROL A: all four anchors x all horizons, pooled --------------------")
    p("   `open` and `pclose` are DEGENERATE anchors (no averaging at all). If they")
    p("   match `vwap`, the effect is about displacement from any fixed reference.")
    p("")
    p("   `past30` is the NO-ANCHOR degenerate arm: fade the trailing 30-min return,")
    p("   z-scored identically. No anchor, no averaging, no volume.")
    p("")
    p("   anchor    H       n       per-bet pip   cl-t     rank IC    q5-q1 pip")
    anchor_tbl = {}
    for a in (*V.ANCHORS, "past30"):
        for h in HORIZONS:
            c = _cell(panel, f"dev_{a}_z", f"y{h}", rng,
                      nboot=NBOOT if h == "30" else 0)
            if c is None:
                continue
            anchor_tbl[(a, h)] = c
            ci_s = (f"  [{c['lo']:+.3f},{c['hi']:+.3f}]"
                    if np.isfinite(c["lo"]) else "")
            p(f"   {a:<8} {h:<6} {c['n']:8,}   {c['mean']:+11.4f}   "
              f"{c['t']:+6.2f}   {c['ic']:+8.5f}   {c['spread']:+9.4f}{ci_s}")

    # ------------------------------------------------------------ blocks
    p("")
    p("-- CONTROL B: liquidity block (the SHAPE the mechanism predicts) ---------")
    p("   HYP-0002 predicts reversion STRONGEST in `asia`, weakest in `overlap`.")
    p("")
    p("   anchor   block      H=30 per-bet     cl-t      n        rank IC")
    block_tbl = {}
    for a in ("vwap", "twap", "open", "past30"):
        for b in BLOCKS:
            sub = panel[panel["block"] == b]
            c = _cell(sub, f"dev_{a}_z", "y30", rng,
                      nboot=NBOOT if a == "vwap" else 0)
            if c is None:
                continue
            block_tbl[(a, b)] = c
            ci_s = (f"   boot95 [{c['lo']:+.3f},{c['hi']:+.3f}]"
                    if np.isfinite(c["lo"]) else "")
            p(f"   {a:<8} {b:<9} {c['mean']:+12.4f}   {c['t']:+6.2f}  "
              f"{c['n']:8,}   {c['ic']:+8.5f}{ci_s}")

    # ------------------------------------------------------------ partial-out
    p("")
    p("-- CONTROL C: is this just a plain reversal? partial out trailing return --")
    p("   partial_spearman(dev_z, fwd_30 | past_30): if the anchor adds nothing")
    p("   beyond the last 30 minutes of price change, this collapses toward zero.")
    p("")
    p("   anchor    raw IC     IC | past_30    corr(dev_z, past_30)")
    for a in V.ANCHORS:
        d = panel.dropna(subset=[f"dev_{a}_z", "y30", "past_30_pip"])
        raw = S.spearman(d[f"dev_{a}_z"].to_numpy(), d["y30"].to_numpy())
        par = S.partial_spearman(d[f"dev_{a}_z"].to_numpy(), d["y30"].to_numpy(),
                                 d["past_30_pip"].to_numpy())
        cc = S.spearman(d[f"dev_{a}_z"].to_numpy(), d["past_30_pip"].to_numpy())
        p(f"   {a:<8} {raw:+9.5f}   {par:+12.5f}    {cc:+18.5f}")
    d = panel.dropna(subset=["past_30_pip", "y30"])
    p(f"   for reference, past_30 itself:  IC(past_30, fwd_30) = "
      f"{S.spearman(d['past_30_pip'].to_numpy(), d['y30'].to_numpy()):+.5f}")

    # ------------------------------------------------------------ shared-bar
    p("")
    p("-- CONTROL D: size the shared-decision-bar artifact on this data ---------")
    p("   The honest target enters at open(m+1). The naive one enters at close(m),")
    p("   which shares a print with the feature and manufactures reversion.")
    pn = panel.copy()
    pn["y30_shared"] = ((pn["fwd_30"] + pn["entry_px"] - pn["close"]) / D.PIP)
    hon = _cell(pn, "dev_vwap_z", "y30", rng)
    nai = _cell(pn, "dev_vwap_z", "y30_shared", rng)
    p(f"   honest  entry=open(m+1)  per-bet {hon['mean']:+.4f} pip  t {hon['t']:+.2f}"
      f"   IC {hon['ic']:+.5f}")
    p(f"   naive   entry=close(m)   per-bet {nai['mean']:+.4f} pip  t {nai['t']:+.2f}"
      f"   IC {nai['ic']:+.5f}")
    if abs(nai["mean"]) > 1e-9:
        p(f"   -> the honest estimate retains {hon['mean'] / nai['mean']:.1%} of the "
          "naive one; the remainder is the shared-print artifact")

    # ------------------------------------------------------------ era
    p("")
    p("-- CONTROL E: era stability (vwap, H=30, pooled) -------------------------")
    p("   year      n      per-bet pip    cl-t      rank IC")
    era = {}
    for y, g in panel.groupby("year"):
        c = _cell(g, "dev_vwap_z", "y30", rng)
        if c is None:
            continue
        era[y] = c
        p(f"   {y}  {c['n']:7,}   {c['mean']:+11.4f}   {c['t']:+6.2f}   {c['ic']:+8.5f}")
    signs = [np.sign(c["mean"]) for c in era.values()]
    p(f"   sign stability: {int(sum(s < 0 for s in signs))}/{len(signs)} years negative "
      "(reversion)")

    # ------------------------------------------------------------ costs
    p("")
    p("-- CONTROL F: costs, in the units actually traded (rules 19, 20) ---------")
    for lo, hi in (("2010", "2015"), ("2016", "2023")):
        yrs = range(int(lo), int(hi) + 1)
        ts = D.tick_size(product, int(lo))
        tick_pip = ts / D.PIP
        sub = panel[panel["year"].isin(yrs)]
        c = _cell(sub, "dev_vwap_z", "y30", rng)
        if c is None:
            continue
        rt_pip = 2 * tick_pip                     # 1 tick each way, optimistic
        p(f"   {lo}-{hi}: tick {ts:.5f} = {tick_pip:.1f} pip = "
          f"${tick_pip * D.usd_per_pip(product):.2f};  "
          f"gross {c['mean']:+.4f} pip/bet, optimistic round trip {rt_pip:.1f} pip"
          f"  -> net {c['mean'] - rt_pip:+.4f} pip "
          f"(${(c['mean'] - rt_pip) * D.usd_per_pip(product):+.2f}/bet)")
    p("   [a bet is one contract; the round trip assumes a 1-tick-wide market and a")
    p("    fill at the touch on both sides, i.e. the most optimistic model available]")

    # ------------------------------------------------------------ verdict
    p("")
    p("-- KILL TEST (declared in HYP-0002 before the run) -----------------------")
    k1 = prim["mean"] > 0                # fading the displacement pays <=> reversion
    k2 = abs(prim["t"]) >= 2.0 and not (prim["lo"] <= 0 <= prim["hi"])
    asia = block_tbl.get(("vwap", "asia"))
    ovl = block_tbl.get(("vwap", "overlap"))
    k3 = (asia["mean"] > ovl["mean"]) if (asia and ovl) else False
    open_c = anchor_tbl.get(("open", "30"))
    k4 = not (prim["lo"] <= open_c["mean"] <= prim["hi"]) if open_c else False
    p(f"   1. sign     reversion (fade P&L > 0)?          {'PASS' if k1 else 'FAIL'}"
      f"   (per-bet {prim['mean']:+.4f})")
    p(f"   2. signif.  |t|>=2 and CI excludes 0?          {'PASS' if k2 else 'FAIL'}"
      f"   (t {prim['t']:+.2f}, CI [{prim['lo']:+.4f},{prim['hi']:+.4f}])")
    if asia and ovl:
        p(f"   3. shape    asia > overlap?                    {'PASS' if k3 else 'FAIL'}"
          f"   (asia {asia['mean']:+.4f} vs overlap {ovl['mean']:+.4f})")
    if open_c:
        p(f"   4. anchor   `open` outside vwap's CI?          {'PASS' if k4 else 'FAIL'}"
          f"   (open {open_c['mean']:+.4f} vs vwap CI "
          f"[{prim['lo']:+.4f},{prim['hi']:+.4f}])")
    past_c = anchor_tbl.get(("past30", "30"))
    if past_c:
        beats = past_c["mean"] >= prim["mean"]
        p(f"   4b. degenerate `past30` (NO anchor at all) {past_c['mean']:+.4f} pip, "
          f"t {past_c['t']:+.2f}  -> "
          + ("BEATS the VWAP arm: the anchor machinery is decoration"
             if beats else "below the VWAP arm"))

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / f"entryinfo_{product}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RUN / f'entryinfo_{product}.txt'}")
    return {"product": product, "prim": prim, "k": (k1, k2, k3, k4),
            "anchor": anchor_tbl, "block": block_tbl}


def main(argv):
    prods = [argv[1]] if len(argv) > 1 else list(D.PRODUCTS)
    out = [run(p) for p in prods]
    if len(out) > 1:
        print("\n" + "=" * 96)
        print("SUMMARY  (kill-test arms: sign / significance / shape / anchor-specific)")
        for r in out:
            k = r["k"]
            print(f"  {r['product']}  per-bet {r['prim']['mean']:+.4f} pip  "
                  f"t {r['prim']['t']:+.2f}  IC {r['prim']['ic']:+.5f}   "
                  f"arms {['PASS' if x else 'FAIL' for x in k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
