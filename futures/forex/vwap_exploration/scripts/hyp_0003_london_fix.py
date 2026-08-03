"""HYP-0003 / EXP-0003 — the WM/Reuters 16:00 London fix.

Tests whether the one moment in the FX day at which a volume-weighted average
price is a CONTRACTUAL obligation leaves a tradable reversal signature, against
the four pre-declared arms in `experiments/hypotheses/HYP-0003.md`.

Run:  python -u -m futures.forex.vwap_exploration.scripts.hyp_0003_london_fix [6E|6B]
Out:  artifacts/runs/EXP-0003/fix_<product>.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import fix as FX
from futures.forex.vwap_exploration.core import frame as F
from futures.forex.vwap_exploration.core import stats as S

RUN = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0003"

PRE_MIN = 30            # drift window into the fix
POST_MIN = 30           # holding window after the fix
ENTRY_LAG = 2           # first minute whose open is outside the widest fix window
Z_ENTRY = 1.0
LOOKBACK = 90
MIN_OBS = 45
NBOOT = 400


def _matrices(product: str):
    bars, _ = D.load_bars(product, scope="explore")
    close = bars.pivot_table(index="sdate", columns="mfo", values="close",
                             aggfunc="last").reindex(
        columns=np.arange(D.SESSION_MINUTES))
    openp = bars.pivot_table(index="sdate", columns="mfo", values="open",
                             aggfunc="last").reindex(
        columns=np.arange(D.SESSION_MINUTES))
    return close.to_numpy(float), openp.to_numpy(float), close.index


def _events(close, openp, sdates, anchor_mod: np.ndarray):
    """pre/post around an ET minute-of-day given per-session (so DST-correct)."""
    mfo = (anchor_mod - D.SESSION_OPEN_MOD) % 1440
    n = len(sdates)
    rows = np.arange(n)
    def at(mat, off):
        j = mfo + off
        ok = (j >= 0) & (j < D.SESSION_MINUTES)
        out = np.full(n, np.nan)
        out[ok] = mat[rows[ok], j[ok]]
        return out
    pre = at(close, 0) - at(close, -PRE_MIN)
    entry = at(openp, ENTRY_LAG)
    post = at(close, ENTRY_LAG + POST_MIN) - entry
    return pre, post


def _causal_scale(sdates, pre):
    """Trailing mean |pre| over the previous LOOKBACK sessions (strictly causal)."""
    s = pd.Series(np.abs(pre), index=pd.Index(sdates))
    return s.shift(1).rolling(LOOKBACK, min_periods=MIN_OBS).mean().to_numpy()


def _bet_stats(pre, post, sdates, rng, nboot=0, min_events: int = 25, mask=None):
    """Per-bet stats for the fade.

    `mask` selects a SUBSET of sessions (month-end, an era, ...). It is applied
    AFTER the causal scale is computed on the full series, never before: the scale
    is a 90-session trailing window, so masking first would leave a scattered
    subset like month-end with an almost entirely NaN window and silently return
    "too few events". That bug is why the month-end arm did not compute on the
    first pass.
    """
    scale = _causal_scale(sdates, pre)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(scale > 0, pre / scale, np.nan)
    sel = np.isfinite(z) & np.isfinite(post) & (np.abs(z) >= Z_ENTRY)
    if mask is not None:
        sel = sel & np.asarray(mask, bool)
    if sel.sum() < min_events:
        return None
    pnl = (-np.sign(z[sel]) * post[sel]) / D.PIP
    sd = np.asarray(sdates)[sel]
    m, se, t, n = S.cluster_t(pnl, sd)
    lo = hi = np.nan
    if nboot:
        samp = S.block_bootstrap(pd.DataFrame({"sdate": sd, "pnl": pnl}), ["pnl"],
                                 lambda a: float(np.nanmean(a)), rng, nboot=nboot)
        lo, hi = S.ci(samp)
    return dict(mean=m, t=t, n=n, lo=lo, hi=hi, pnl=pnl, sel=sel, z=z)


def run(product: str) -> dict:
    global ENTRY_LAG, POST_MIN          # the two sensitivity sweeps rebind these
    lines: list[str] = []
    rng = np.random.default_rng(20260802)

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 92)
    p(f"EXP-0003  HYP-0003  WM/Reuters 16:00 London fix   {product}  "
      f"({D.CONTRACT[product]['name']})")
    p("=" * 92)

    close, openp, sdates = _matrices(product)
    p(f"sessions {len(sdates):,}   {sdates.min().date()} -> {sdates.max().date()}"
      f"   (holdout {D.HOLDOUT_YEARS} sealed)")

    # ------------------------------------------------------------ the fix clock
    fix_mod = FX.fix_mod_et(pd.Series(sdates)).to_numpy()
    vc = pd.Series(fix_mod).value_counts().sort_index()
    p("")
    p("-- the fix clock (Europe/London 16:00 expressed in ET) -------------------")
    for m, c in vc.items():
        p(f"   ET {m // 60:02d}:{m % 60:02d}   {c:5,} sessions  ({c / len(sdates):.2%})")
    p("   [the 12:00 ET sessions are the US/UK daylight-saving shoulder weeks;")
    p("    hardcoding 11:00 ET would file them under a placebo hour]")

    pre, post = _events(close, openp, sdates, fix_mod)
    ok = np.isfinite(pre) & np.isfinite(post)
    p(f"   usable fix events {int(ok.sum()):,} / {len(sdates):,}")

    # ------------------------------------------------------------ descriptive
    p("")
    p("-- unconditional behaviour around the fix -------------------------------")
    p(f"   pre-fix drift  ({PRE_MIN}min into the fix): mean {np.nanmean(pre) / D.PIP:+.3f} pip, "
      f"sd {np.nanstd(pre) / D.PIP:.2f}, mean|.| {np.nanmean(np.abs(pre)) / D.PIP:.2f}")
    p(f"   post-fix move  ({POST_MIN}min after):        mean {np.nanmean(post) / D.PIP:+.3f} pip, "
      f"sd {np.nanstd(post) / D.PIP:.2f}")
    both = np.isfinite(pre) & np.isfinite(post)
    p(f"   corr(pre, post)   pearson {np.corrcoef(pre[both], post[both])[0, 1]:+.4f}"
      f"   spearman {S.spearman(pre[both], post[both]):+.4f}   "
      "[negative = reversal]")

    # ------------------------------------------------------------ ARM 1
    p("")
    p("-- ARM 1: does fading the pre-fix drift pay? ----------------------------")
    prim = _bet_stats(pre, post, sdates, rng, nboot=NBOOT)
    p(f"   per-bet {prim['mean']:+.4f} pip   cluster-t {prim['t']:+.2f}   "
      f"n {prim['n']:,}   boot95 [{prim['lo']:+.4f}, {prim['hi']:+.4f}]")

    # ------------------------------------------------------------ ARM 2 placebo
    p("")
    p("-- ARM 2 (DECISIVE): is the fix hour special, or an ordinary hour? -------")
    p("   The identical construction at every other candidate hour of the session.")
    p("   EXP-0002 already found a general short-horizon reversal on this data, so")
    p("   the fix must beat that background, not merely be positive.")
    p("")
    p("   ET hour   per-bet pip    cl-t       n")
    placebo = {}
    for h in range(24):
        if 17 <= h < 18:
            continue                        # maintenance halt
        am = np.full(len(sdates), h * 60)
        pr, po = _events(close, openp, sdates, am)
        st = _bet_stats(pr, po, sdates, rng)
        if st is None:
            continue
        placebo[h] = st["mean"]
        mark = ""
        if h in (11, 12):
            share = (fix_mod == h * 60).mean()
            mark = f"   <-- fix hour on {share:.0%} of sessions"
        p(f"   {h:02d}:00   {st['mean']:+11.4f}   {st['t']:+6.2f}  {st['n']:7,}{mark}")
    pv = np.array(list(placebo.values()))
    others = np.array([v for h, v in placebo.items() if h not in (11, 12)])
    q90 = float(np.percentile(others, 90))
    rank = float((others < prim["mean"]).mean())
    p("")
    p(f"   fix per-bet {prim['mean']:+.4f}  vs placebo hours (excl. 11,12): "
      f"median {np.median(others):+.4f}, p90 {q90:+.4f}, max {others.max():+.4f}")
    p(f"   the fix beats {rank:.0%} of placebo hours   "
      f"(arm 2 needs > 90%)")

    # ------------------------------------------------------------ era placebo
    p("")
    p("-- ARM 2b: the placebo distribution SPLIT BY ERA -------------------------")
    p("   Arm 4 asks whether the fix effect concentrates in one era. That is only")
    p("   readable against the background reversal IN THAT ERA -- if every hour got")
    p("   more reversionary after 2015, the fix did not.")
    p("")
    p("   era                    fix per-bet   placebo median   placebo p90   beats")
    era_masks = ((f"before {FX.WINDOW_WIDENED.date()}",
                  pd.Index(sdates) < FX.WINDOW_WIDENED),
                 (f"after  {FX.WINDOW_WIDENED.date()}",
                  pd.Index(sdates) >= FX.WINDOW_WIDENED))
    for lab, mask in era_masks:
        f_st = _bet_stats(pre, post, sdates, rng, mask=mask)
        vals = []
        for h in range(24):
            if 17 <= h < 18 or h in (11, 12):
                continue
            pr, po = _events(close, openp, sdates, np.full(len(sdates), h * 60))
            st = _bet_stats(pr, po, sdates, rng, mask=mask)
            if st is not None:
                vals.append(st["mean"])
        v = np.array(vals)
        if f_st is None or not len(v):
            continue
        p(f"   {lab:<22} {f_st['mean']:+11.4f}   {np.median(v):+14.4f}   "
          f"{np.percentile(v, 90):+11.4f}   {(v < f_st['mean']).mean():5.0%}")

    # ------------------------------------------------------------ entry-lag
    p("")
    p("-- CONTROL (CRITICAL): entry-lag sensitivity ----------------------------")
    p("   Since 2015-02-15 the fix window runs to 16:02:30 London, so an entry at")
    p("   f+2 is still INSIDE the benchmark window. If the result is the tail of")
    p("   the fix flow rather than a post-fix reversal, it dies as the lag grows.")
    p("")
    p("   entry lag   all         t       before 2015    after 2015")
    saved_lag = ENTRY_LAG
    for lag in (2, 3, 5, 10, 15, 30):
        ENTRY_LAG = lag
        pr_l, po_l = _events(close, openp, sdates, fix_mod)
        st = _bet_stats(pr_l, po_l, sdates, rng)
        e_st = _bet_stats(pr_l, po_l, sdates, rng,
                          mask=pd.Index(sdates) < FX.WINDOW_WIDENED)
        l_st = _bet_stats(pr_l, po_l, sdates, rng,
                          mask=pd.Index(sdates) >= FX.WINDOW_WIDENED)
        p(f"   f+{lag:<9} {st['mean']:+8.4f}  {st['t']:+6.2f}   "
          f"{e_st['mean'] if e_st else float('nan'):+11.4f}   "
          f"{l_st['mean'] if l_st else float('nan'):+11.4f}")
    ENTRY_LAG = saved_lag

    # The f+2 and f+3 bets share 29 of their 30 minutes, so the whole gap between
    # them is ONE minute. Hold the entry at f+2 and shorten the horizon instead:
    # if the 1-minute bet already equals the 30-minute bet, the result is a single
    # minute of price action and nothing that follows it.
    p("")
    p("   holding-horizon decomposition at a FIXED f+2 entry:")
    p("   hold        all         t       before 2015    after 2015")
    saved_post = POST_MIN
    for hold in (1, 2, 3, 5, 10, 30):
        POST_MIN = hold
        pr_h, po_h = _events(close, openp, sdates, fix_mod)
        st = _bet_stats(pr_h, po_h, sdates, rng)
        e_st = _bet_stats(pr_h, po_h, sdates, rng,
                          mask=pd.Index(sdates) < FX.WINDOW_WIDENED)
        l_st = _bet_stats(pr_h, po_h, sdates, rng,
                          mask=pd.Index(sdates) >= FX.WINDOW_WIDENED)
        p(f"   {hold:>3}min     {st['mean']:+8.4f}  {st['t']:+6.2f}   "
          f"{e_st['mean'] if e_st else float('nan'):+11.4f}   "
          f"{l_st['mean'] if l_st else float('nan'):+11.4f}")
    POST_MIN = saved_post

    # ------------------------------------------------------------ ARM 3 month-end
    p("")
    p("-- ARM 3: month-end amplification (the index-rebalancing mechanism) ------")
    me = FX.month_end_sessions(sdates)
    p(f"   month-end sessions {int(me.sum()):,}   other {int((~me).sum()):,}")
    res_me = {}
    for lab, mask in (("month-end", me), ("other", ~me)):
        st = _bet_stats(pre, post, sdates, rng, mask=mask,
                        nboot=NBOOT if lab == "month-end" else 0)
        if st is None:
            p(f"   {lab:<12} (too few events)")
            continue
        res_me[lab] = st
        ci_s = (f"   boot95 [{st['lo']:+.3f},{st['hi']:+.3f}]"
                if np.isfinite(st["lo"]) else "")
        p(f"   {lab:<12} per-bet {st['mean']:+9.4f}  t {st['t']:+6.2f}  "
          f"n {st['n']:5,}{ci_s}")
    # is the pre-fix drift itself bigger at month end?
    p(f"   pre-fix mean|drift|:  month-end {np.nanmean(np.abs(pre[me])) / D.PIP:.2f} pip"
      f"   other {np.nanmean(np.abs(pre[~me])) / D.PIP:.2f} pip")

    # ------------------------------------------------------------ ARM 4 the break
    p("")
    p("-- ARM 4: the 2015-02-15 window widening (1min -> 5min) ------------------")
    early = pd.Index(sdates) < FX.WINDOW_WIDENED
    res_era = {}
    for lab, mask in ((f"before {FX.WINDOW_WIDENED.date()}", early),
                      (f"after  {FX.WINDOW_WIDENED.date()}", ~early)):
        st = _bet_stats(pre, post, sdates, rng, mask=mask, nboot=NBOOT)
        if st is None:
            continue
        res_era[lab] = st
        p(f"   {lab:<22} per-bet {st['mean']:+9.4f}  t {st['t']:+6.2f}  "
          f"n {st['n']:5,}  boot95 [{st['lo']:+.3f},{st['hi']:+.3f}]")

    # ------------------------------------------------------------ DST control
    p("")
    p("-- CONTROL: does the DST-correct fix clock matter? -----------------------")
    naive = _bet_stats(*_events(close, openp, sdates,
                                np.full(len(sdates), 11 * 60)), sdates, rng)
    p(f"   DST-correct (Europe/London) per-bet {prim['mean']:+.4f}  t {prim['t']:+.2f}")
    p(f"   naive hardcoded 11:00 ET    per-bet {naive['mean']:+.4f}  t {naive['t']:+.2f}")

    # ------------------------------------------------------------ costs
    p("")
    p("-- CONTROL: costs (rules 19, 20) ----------------------------------------")
    for lo_y, hi_y in ((2010, 2015), (2016, 2023)):
        yrs = (pd.Index(sdates).year >= lo_y) & (pd.Index(sdates).year <= hi_y)
        st = _bet_stats(pre, post, sdates, rng, mask=yrs)
        if st is None:
            continue
        ts = D.tick_size(product, lo_y)
        rt = 2 * ts / D.PIP
        p(f"   {lo_y}-{hi_y}: gross {st['mean']:+.4f} pip/bet (t {st['t']:+.2f}, "
          f"n {st['n']:,}); optimistic round trip {rt:.1f} pip -> "
          f"net {st['mean'] - rt:+.4f} pip "
          f"(${(st['mean'] - rt) * D.usd_per_pip(product):+.2f})")

    # ------------------------------------------------------------ verdict
    a1 = (prim["mean"] > 0) and abs(prim["t"]) >= 2.0
    a2 = rank > 0.90
    a3 = ("month-end" in res_me and "other" in res_me
          and res_me["month-end"]["mean"] > res_me["other"]["mean"])
    keys = list(res_era)
    a4 = (len(keys) == 2 and res_era[keys[0]]["mean"] > res_era[keys[1]]["mean"])
    p("")
    p("-- KILL TEST (declared in HYP-0003 before the run) -----------------------")
    p(f"   1. reversal   fade pays, |t|>=2?           {'PASS' if a1 else 'FAIL'}"
      f"   ({prim['mean']:+.4f} pip, t {prim['t']:+.2f})")
    p(f"   2. special    beats >90% of placebo hours? {'PASS' if a2 else 'FAIL'}"
      f"   (beats {rank:.0%})")
    if res_me:
        p(f"   3. month-end  larger than other days?      {'PASS' if a3 else 'FAIL'}"
          f"   ({res_me.get('month-end', {}).get('mean', float('nan')):+.4f} vs "
          f"{res_me.get('other', {}).get('mean', float('nan')):+.4f})")
    if len(keys) == 2:
        p(f"   4. 2015 break larger before the widening?  {'PASS' if a4 else 'FAIL'}"
          f"   ({res_era[keys[0]]['mean']:+.4f} vs {res_era[keys[1]]['mean']:+.4f})")

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / f"fix_{product}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RUN / f'fix_{product}.txt'}")
    return {"product": product, "arms": (a1, a2, a3, a4), "prim": prim,
            "rank": rank}


def main(argv):
    prods = [argv[1]] if len(argv) > 1 else list(D.PRODUCTS)
    out = [run(p) for p in prods]
    if len(out) > 1:
        print("\n" + "=" * 92)
        print("SUMMARY  (arms: reversal / special / month-end / 2015-break)")
        for r in out:
            print(f"  {r['product']}  per-bet {r['prim']['mean']:+.4f} pip  "
                  f"t {r['prim']['t']:+.2f}  beats {r['rank']:.0%} of placebo hours  "
                  f"arms {['PASS' if x else 'FAIL' for x in r['arms']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
