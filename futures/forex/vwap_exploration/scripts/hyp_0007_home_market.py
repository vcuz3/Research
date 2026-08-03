"""HYP-0007 / EXP-0007 — does reversion track the COUNTER CURRENCY's home-market hours?

EXP-0005 left finding C's mechanism open and the surviving account was post-hoc,
read off 12 cells of three products. This tests it on FOUR PRODUCTS THAT HAVE
NEVER BEEN LOADED (6A, 6C, 6N, 6S), whose home time zones make sharply differing
predictions: 6C's home market is shut all night (predict strong `asia` reversion)
while 6A's and 6N's are open then (predict weak `asia` reversion).

The primary statistic is computed on the FRESH FOUR ONLY. 6E/6B/6J generated the
hypothesis and cannot test it (rule 26); they are reported for continuity.

Run:  python -u -m futures.forex.vwap_exploration.scripts.hyp_0007_home_market
Out:  artifacts/runs/EXP-0007/homemkt.txt
"""
from __future__ import annotations

import sys
from itertools import permutations
from pathlib import Path

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import home as H
from futures.forex.vwap_exploration.core import stats as S
from futures.forex.vwap_exploration.scripts.hyp_0004_vol_stratified_blocks import (
    BLOCKS, RV, _bets, build_run_panel,
)

RUN = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0007"

CONSUMED = ("6E", "6B", "6J")
FRESH = ("6A", "6C", "6N", "6S")
ALL = CONSUMED + FRESH
MIN_SLOT_N = 100
NDRAW = 20000
# EXP-0005 risk-equalised block profiles, for the rule-23 reproduction check.
EXP5 = {"6E": (0.0522, 0.0119, -0.0153, 0.0069),
        "6B": (0.0202, 0.0002, -0.0159, 0.0104),
        "6J": (-0.0024, -0.0021, -0.0151, 0.0207)}


def _demean(v: np.ndarray) -> np.ndarray:
    return v - np.nanmean(v)


def _spearman_small(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman without `stats.spearman`'s n>=10 guard, for the 4-block cells."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return np.nan
    rx = pd.Series(x[ok]).rank().to_numpy()
    ry = pd.Series(y[ok]).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def _pooled_rho(per: dict, key_y: str, key_x: str) -> float:
    """Within-product-demeaned Spearman, pooled over products."""
    xs, ys = [], []
    for d in per.values():
        r_x = pd.Series(d[key_x]).rank().to_numpy()
        r_y = pd.Series(d[key_y]).rank().to_numpy()
        xs.append(_demean(r_x))
        ys.append(_demean(r_y))
    x, y = np.concatenate(xs), np.concatenate(ys)
    ok = np.isfinite(x) & np.isfinite(y)
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def _null_pooled(per: dict, key_y: str, key_x: str, rng, mode: str,
                 ndraw: int = NDRAW) -> np.ndarray:
    """Null distribution of the pooled rho.

    `circular` shifts each product's slot labels round the 46-slot clock, which
    preserves the autocorrelation of BOTH series and destroys only their
    alignment. `shuffle` permutes freely, which destroys the autocorrelation too
    and is therefore ANTI-CONSERVATIVE -- reported for contrast only.
    """
    out = np.empty(ndraw)
    keys = list(per)
    for i in range(ndraw):
        shuffled = {}
        for k in keys:
            d = per[k]
            n = len(d[key_x])
            if mode == "circular":
                s = rng.integers(0, n)
                shuffled[k] = {key_x: np.roll(d[key_x], s), key_y: d[key_y]}
            else:
                shuffled[k] = {key_x: rng.permutation(d[key_x]), key_y: d[key_y]}
        out[i] = _pooled_rho(shuffled, key_y, key_x)
    return out


def run() -> int:
    lines: list[str] = []
    rng = np.random.default_rng(20260803)

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 100)
    p("EXP-0007  HYP-0007  does reversion track the COUNTER CURRENCY's home market?")
    p("=" * 100)
    p("Every contract is USD-quoted on a US venue, so the USD leg and the venue")
    p("calendar are common to all seven. The only thing that varies is the OTHER")
    p("currency's home time zone. That is the lever.")
    p("")
    p("PRIMARY IS THE FRESH FOUR ONLY (6A/6C/6N/6S). 6E/6B/6J generated this")
    p("hypothesis from inspected data and cannot test it (rule 26).")

    panels, bets, slot, blk, opens = {}, {}, {}, {}, {}
    for prod in ALL:
        pan = build_run_panel(prod)
        pan["home_open"] = H.is_home_open(
            pd.to_datetime(pan["et"]).dt.tz_convert("UTC"), prod)
        panels[prod] = pan
        b = _bets(pan, "dev_vwap_z")
        b = b.merge(pan[["sdate", "mfo", "home_open"]], on=["sdate", "mfo"],
                    how="left")
        bets[prod] = b
        g = b.groupby("mfo").agg(y=("pnl_r", "mean"), n=("pnl_r", "size"),
                                 open=("home_open", "mean"))
        g = g[(g["n"] >= MIN_SLOT_N) & np.isfinite(g["y"])]
        slot[prod] = g
        blk[prod] = b.groupby("block")["pnl_r"].mean()
        opens[prod] = H.openness_by_block(pan, prod)

    # ------------------------------------------------------------ rule 9a
    p("")
    p("-- RULE 9a: four never-before-loaded archives, gated BEFORE any contrast --")
    p("   product  sessions  decisions  bar cov  rv_60 cov  scale cov  slots used")
    for prod in ALL:
        pan = panels[prod]
        tag = "" if prod in CONSUMED else "  <- FRESH"
        p(f"   {prod:<8} {pan['sdate'].nunique():8,}  {len(pan):9,}   "
          f"{float(np.isfinite(pan['close']).mean()):.4f}   "
          f"{float(np.isfinite(pan[RV]).mean()):.4f}     "
          f"{float(np.isfinite(pan['dev_vwap_z']).mean()):.4f}     "
          f"{len(slot[prod]):3d}{tag}")
    p("   (all seven share the CME FX session and the 17:00-18:00 ET halt is empty;")
    p("    roll and short sessions are dropped by the same loader rule)")

    # ------------------------------------------------------------ rule 23
    p("")
    p("-- RULE 23: the three consumed products must reproduce EXP-0005 ----------")
    p("   product   asia     ldn_am   overlap  ny_pm    vs EXP-0005")
    ok_all = True
    for prod in CONSUMED:
        got = tuple(float(blk[prod].get(b, np.nan)) for b in BLOCKS)
        ref = EXP5[prod]
        ok = all(abs(a - b) < 1e-4 for a, b in zip(got, ref))
        ok_all &= ok
        p(f"   {prod:<8} " + "  ".join(f"{v:+7.4f}" for v in got)
          + f"   {'PASS' if ok else '*** FAIL'}")
    p(f"   -> {'reproduced to 4dp' if ok_all else '*** REPRODUCTION FAILED'}")

    # ------------------------------------------------------------ the prediction
    p("")
    p("-- THE PREREGISTERED PREDICTION: home-market openness by block ------------")
    p("   Uniform 08:00-17:00 LOCAL, Mon-Fri, from each currency's OWN tz with real")
    p("   DST. No per-product schedule, so no free parameters.")
    p("")
    p("   product  home market        asia   ldn_am  overlap  ny_pm   predicted best")
    for prod in ALL:
        o = opens[prod]
        best = o.sort_values().index[0]
        p(f"   {prod:<8} {H.HOME[prod][1]:<17} "
          + "  ".join(f"{float(o.get(b, np.nan)):6.3f}" for b in BLOCKS)
          + f"   {best}")

    # ------------------------------------------------------------ observed
    p("")
    p("-- OBSERVED risk-equalised reversion by block ----------------------------")
    p("   product      asia   ldn_am  overlap   ny_pm   observed best  PREDICTED  hit")
    hits = {}
    for prod in ALL:
        o, bb = opens[prod], blk[prod]
        pred = o.sort_values().index[0]
        obs = bb.reindex(list(BLOCKS)).idxmax()
        hit = (pred == obs)
        hits[prod] = hit
        tag = "" if prod in CONSUMED else " FRESH"
        p(f"   {prod:<8} " + "  ".join(f"{float(bb.get(b, np.nan)):+7.4f}" for b in BLOCKS)
          + f"   {obs:<12} {pred:<10} {'YES' if hit else 'no'}{tag}")
    fh = sum(hits[q] for q in FRESH)
    ch = sum(hits[q] for q in CONSUMED)
    p(f"   argmax agreement: FRESH {fh}/4   consumed {ch}/3   "
      f"(p=1/4 per product under a uniform null)")
    # The uniform null is too generous: if one block is the modal winner across
    # products, "predicting" it is nearly free. Score against the OBSERVED
    # marginal instead.
    obs_best = pd.Series([blk[q].reindex(list(BLOCKS)).idxmax() for q in ALL])
    marg = obs_best.value_counts(normalize=True)
    p("   observed BEST-block marginal across all seven: "
      + ", ".join(f"{k} {v:.0%}" for k, v in marg.items()))
    exp_hits = sum(float(marg.get(opens[q].sort_values().index[0], 0.0))
                   for q in FRESH)
    p(f"   expected FRESH hits under that marginal: {exp_hits:.2f} vs {fh} observed")
    p("   [if one block wins for most products, an argmax 'hit' on it is nearly")
    p("    free and the uniform 1/4 null materially overstates the evidence]")

    # ------------------------------------------------------------ PRIMARY
    p("")
    p("-- PRIMARY (declared in HYP-0007): fresh four, slot level ----------------")
    p("   Pooled within-product-demeaned Spearman(home_open, per-bet reversion)")
    p("   across the 46 decision slots. Negative = reversion falls as the home")
    p("   market opens = H_home supported.")
    p("")

    def _per(products):
        return {q: {"x": slot[q]["open"].to_numpy(),
                    "y": slot[q]["y"].to_numpy()} for q in products}

    per_fresh = _per(FRESH)
    rho_fresh = _pooled_rho(per_fresh, "y", "x")
    circ = _null_pooled(per_fresh, "y", "x", rng, "circular")
    shuf = _null_pooled(per_fresh, "y", "x", rng, "shuffle")
    p_circ = float((circ <= rho_fresh).mean())
    p_shuf = float((shuf <= rho_fresh).mean())
    p(f"   rho_fresh = {rho_fresh:+.4f}")
    p(f"     circular-shift null  mean {circ.mean():+.4f}  sd {circ.std():.4f}   "
      f"p(null <= real) = {p_circ:.4f}   <- PRIMARY NULL")
    p(f"     plain-shuffle null   mean {shuf.mean():+.4f}  sd {shuf.std():.4f}   "
      f"p = {p_shuf:.4f}   [anti-conservative, contrast only]")

    # ------------------------------------------------------------ secondaries
    p("")
    p("-- SECONDARIES (declared, reported, not part of the kill test) -----------")
    per_all = _per(ALL)
    rho_all = _pooled_rho(per_all, "y", "x")
    circ_all = _null_pooled(per_all, "y", "x", rng, "circular")
    p(f"   all seven products      rho {rho_all:+.4f}   circular p "
      f"{float((circ_all <= rho_all).mean()):.4f}   "
      "[3 of 7 are consumed data]")
    per_cons = _per(CONSUMED)
    rho_cons = _pooled_rho(per_cons, "y", "x")
    p(f"   consumed three only     rho {rho_cons:+.4f}   "
      "[the sample that generated the hypothesis]")
    p("")
    p("   per-product Spearman(openness, reversion) at BLOCK level, exact 24-perm null:")
    p("   product   rho      p(exact)   n blocks")
    for prod in ALL:
        o = opens[prod].reindex(list(BLOCKS)).to_numpy()
        b_ = blk[prod].reindex(list(BLOCKS)).to_numpy()
        m = np.isfinite(o) & np.isfinite(b_)
        if m.sum() < 4:
            continue
        r = _spearman_small(o[m], b_[m])
        perms = [_spearman_small(np.array(q), b_[m]) for q in permutations(o[m])]
        pe = float(np.mean([q <= r for q in perms]))
        tag = "" if prod in CONSUMED else "  FRESH"
        p(f"   {prod:<8} {r:+7.4f}  {pe:8.4f}   {int(m.sum())}{tag}")
    p("")
    p("   per-product Spearman at SLOT level (46 slots, circular-shift p):")
    p("   product   rho      p(circ)")
    for prod in ALL:
        d = slot[prod]
        r = S.spearman(d["open"].to_numpy(), d["y"].to_numpy())
        n = len(d)
        sh = np.array([S.spearman(np.roll(d["open"].to_numpy(), k),
                                  d["y"].to_numpy()) for k in range(n)])
        tag = "" if prod in CONSUMED else "  FRESH"
        p(f"   {prod:<8} {r:+7.4f}  {float((sh <= r).mean()):7.4f}{tag}")

    # ------------------------------------------------------------ vol control
    p("")
    p("-- CONTROL: partial out per-slot volatility (EXP-0004's confound) --------")
    for label, prods in (("fresh four", FRESH), ("all seven", ALL)):
        xs, ys, zs = [], [], []
        for q in prods:
            d = slot[q]
            rv = bets[q].groupby("mfo")[RV].mean().reindex(d.index).to_numpy()
            xs.append(_demean(pd.Series(d["open"].to_numpy()).rank().to_numpy()))
            ys.append(_demean(pd.Series(d["y"].to_numpy()).rank().to_numpy()))
            zs.append(_demean(pd.Series(rv).rank().to_numpy()))
        x, y, z = (np.concatenate(v) for v in (xs, ys, zs))
        m = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        p(f"   {label:<11} raw {float(np.corrcoef(x[m], y[m])[0, 1]):+.4f}   "
          f"| volatility {S.partial_spearman(x[m], y[m], z[m]):+.4f}")

    # ------------------------------------------------------------ costs
    p("")
    p("-- COSTS (rules 19, 20): six of seven products changed tick mid-sample ---")
    p("   product  era        tick     best block gross  optimistic RT   net $/bet")
    for prod in ALL:
        bb = blk[prod]
        best = bb.reindex(list(BLOCKS)).idxmax()
        g = float(bb[best])
        sub = bets[prod][bets[prod]["block"] == best]
        gross_u = float(sub["pnl"].mean())
        for lo_y, hi_y in (("2010", "2015"), ("2016", "2023")):
            ts = D.tick_size(prod, int(hi_y))
            rt = 2 * ts / D.pip_size(prod)
            if lo_y == "2016":
                p(f"   {prod:<8} {lo_y}-{hi_y}  {ts:<8g} {gross_u:+15.4f}  "
                  f"{rt:12.1f}   "
                  f"{(gross_u - rt) * D.usd_per_pip(prod):+9.2f}")
    p("   [gross is the product's BEST block in native units; RT assumes a 1-tick")
    p("    market and a fill at the touch both sides -- the most optimistic model]")

    # ------------------------------------------------------------ KILL TEST
    p("")
    p("-- KILL TEST (declared before the fresh archives were loaded) ------------")
    k1 = rho_fresh < 0
    k2 = p_circ < 0.05
    p(f"   1. sign   rho_fresh < 0 ?                {'PASS' if k1 else 'FAIL'}"
      f"   (rho {rho_fresh:+.4f})")
    p(f"   2. null   circular-shift p < 0.05 ?      {'PASS' if k2 else 'FAIL'}"
      f"   (p {p_circ:.4f})")
    p("")
    if k1 and k2:
        p("   => H_home SUPPORTED on four products that never generated it.")
    else:
        p("   => H_home REJECTED. The post-hoc pattern from EXP-0005 does not")
        p("      survive on fresh products, and finding C's mechanism stays OPEN.")

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "homemkt.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RUN / 'homemkt.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
