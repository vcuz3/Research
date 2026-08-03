"""HYP-0006 / EXP-0006 — does RSI(14) add anything to the trailing return it is made of?

RSI(n) = 50 + 50 * A_n(dp) / A_n(|dp|) exactly. On this grid `dp` IS `past_30`, so
RSI(14) is a differently-NORMALISED sibling of finding B's incumbent. The run
therefore scores it against (a) its own bare numerator -- the degenerate control
that answers "is the ratio doing anything" -- and (b) the project incumbent, both
at a MATCHED selection rate, because an unmatched comparison reads a selectivity
dial rather than a signal.

Run:  python -u -m futures.forex.vwap_exploration.scripts.hyp_0006_rsi [6E|6B|6J]
Out:  artifacts/runs/EXP-0006/rsi_<product>.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import frame as F
from futures.forex.vwap_exploration.core import rsi as R
from futures.forex.vwap_exploration.core import stats as S
from futures.forex.vwap_exploration.core import vwap as V

RUN = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0006"

N = R.DEFAULT_N
HI, LO = 70.0, 30.0
BLOCKS = ("asia", "ldn_am", "overlap", "ny_pm")
NBOOT = 400


def _panel(product: str) -> pd.DataFrame:
    panel = F.build_panel(product, scope="explore")
    panel["y30"] = panel["fwd_30_pip"]
    sc = V.causal_slot_scale(panel, "past_30", lookback=V.SLOT_LOOKBACK,
                             min_frac=V.SLOT_MIN_FRAC)
    with np.errstate(invalid="ignore", divide="ignore"):
        panel["dev_past30_z"] = np.where(sc > 0, panel["past_30"].to_numpy() / sc,
                                         np.nan)
    for n in (N, *R.NEIGHBOURS):
        panel = panel.merge(R.rsi_frame(panel, n), on=["sdate", "mfo"], how="left")
    # the conservative gap policy, kept only to SIZE what bridging is worth
    rr = R.rsi_frame(panel, N, gap_policy="reset")
    panel = panel.merge(rr[["sdate", "mfo", f"rsi_{N}"]].rename(
        columns={f"rsi_{N}": f"rsi_{N}_reset"}), on=["sdate", "mfo"], how="left")
    return panel


def _fade(sig: np.ndarray, y: np.ndarray, sel: np.ndarray) -> np.ndarray:
    """P&L of fading `sig`'s sign on the selected rows."""
    return -np.sign(sig[sel]) * y[sel]


def _matched_sel(sig: np.ndarray, rate: float, centre: float = 0.0) -> np.ndarray:
    """Select the `rate` fraction most extreme |sig - centre| (two-sided)."""
    x = np.abs(np.asarray(sig, float) - centre)
    ok = np.isfinite(x)
    if ok.sum() == 0 or rate <= 0:
        return np.zeros(x.shape, bool)
    thr = np.quantile(x[ok], 1.0 - rate)
    return ok & (x >= thr)


def _cell(pnl: np.ndarray, sdate: np.ndarray, rng, nboot: int = 0) -> dict:
    m, se, t, n = S.cluster_t(pnl, sdate)
    lo = hi = np.nan
    if nboot and n > 50:
        df = pd.DataFrame({"pnl": pnl, "sdate": sdate}).dropna()
        samp = S.block_bootstrap(df, ["pnl"], lambda a: float(np.nanmean(a)), rng,
                                 nboot=nboot)
        lo, hi = S.ci(samp)
    return dict(mean=m, t=t, n=n, lo=lo, hi=hi)


def run(product: str) -> dict:
    lines: list[str] = []
    rng = np.random.default_rng(20260803)

    def p(s=""):
        print(s)
        lines.append(s)

    unit = D.pip_size(product)
    p("=" * 100)
    p(f"EXP-0006  HYP-0006  RSI({N}) vs the trailing return it is built from   "
      f"{product}  ({D.CONTRACT[product]['name']})")
    p("=" * 100)
    p(f"RSI(n) = 50 + 50*A_n(dp)/A_n(|dp|) EXACTLY. On this grid dp IS past_30, so")
    p(f"RSI({N}) is a re-NORMALISED sibling of finding B's incumbent, not a new idea.")
    p("")
    p(f"bet: fade the extreme (short >= {HI:.0f}, long <= {LO:.0f}), entry open(m+1),")
    p(f"exit close(m+30). Unit = {unit:g} of quote = ${D.usd_per_pip(product):.2f}.")

    panel = _panel(product)
    p(f"decisions {len(panel):,}   sessions {panel['sdate'].nunique():,}   "
      f"{panel['sdate'].min().date()} -> {panel['sdate'].max().date()}   "
      f"(holdout {D.HOLDOUT_YEARS} sealed)")

    rcol, ncol, dcol = f"rsi_{N}", f"rsi_num_{N}", f"rsi_den_{N}"

    # ------------------------------------------------------------ rule 9a
    p("")
    p("-- RULE 9a: where is RSI undefined, and does it track liquidity? ----------")
    p("   A 14-period feature that resets at session-sequence breaks deletes")
    p("   decisions. If the deletion tracks time-of-day liquidity it is a hidden")
    p("   filter (finding G).")
    p("")
    p("   A recursive feature does not merely drop the bar it is missing: under a")
    p("   RESET policy the run needs n fresh increments, and on a 30-minute grid")
    p("   n=14 is ~7 HOURS, so the deletion lands in a DIFFERENT BLOCK from the gap")
    p("   that caused it. Both policies are reported; `bridge` is used throughout.")
    p("")
    p("   block      decisions  missing bar   rsi BRIDGE   rsi RESET   reset cost")
    for b in BLOCKS:
        sub = panel[panel["block"] == b]
        miss = float((~np.isfinite(sub["close"])).mean())
        c1 = float(np.isfinite(sub[rcol]).mean())
        c2 = float(np.isfinite(sub[f"rsi_{N}_reset"]).mean())
        p(f"   {b:<9}  {len(sub):9,}   {miss:10.4f}   {c1:10.4f}  {c2:10.4f}   "
          f"{c1 - c2:+.4f}")
    cb = panel.groupby("block")[rcol].apply(lambda s: float(np.isfinite(s).mean()))
    cr = panel.groupby("block")[f"rsi_{N}_reset"].apply(
        lambda s: float(np.isfinite(s).mean()))
    p(f"   across-block coverage spread   BRIDGE {cb.max() - cb.min():.4f}   "
      f"RESET {cr.max() - cr.min():.4f}")
    p("   NOTE the displacement: the block with the most missing bars is NOT the")
    p("   block whose RSI coverage collapses under `reset`.")

    # ------------------------------------------------------------ the identity
    p("")
    p("-- THE DECOMPOSITION, on real bars ---------------------------------------")
    d = panel.dropna(subset=[rcol, ncol, dcol, "past_30_pip"])
    p(f"   corr(rsi, its own numerator)            {S.spearman(d[rcol].to_numpy(), d[ncol].to_numpy()):+.4f}")
    p(f"   corr(rsi, past_30)  [ONE increment]     {S.spearman(d[rcol].to_numpy(), d['past_30_pip'].to_numpy()):+.4f}")
    p(f"   corr(numerator, past_30)                {S.spearman(d[ncol].to_numpy(), d['past_30_pip'].to_numpy()):+.4f}")
    p(f"   corr(rsi, its own denominator)          {S.spearman(d[rcol].to_numpy(), d[dcol].to_numpy()):+.4f}")
    p("   [if rsi ~ numerator, the denominator is not separating anything]")

    # ------------------------------------------------------------ common sample
    # Every arm must be scored on the SAME rows, or a differing NaN pattern makes
    # the "matched" rates match on different denominators. This is the
    # common-sample discipline of LEARNINGS 2026-07-27's method note.
    SIGCOLS = [rcol, ncol, "dev_past30_z", "past_30_pip"]
    common = np.isfinite(panel["y30"]).to_numpy().copy()
    for c_ in SIGCOLS:
        common &= np.isfinite(panel[c_]).to_numpy()
    pan = panel.loc[common].reset_index(drop=True)

    sel_rsi = (((pan[rcol] >= HI) | (pan[rcol] <= LO))).to_numpy()
    rate = float(sel_rsi.mean())
    p("")
    p("-- COMMON SAMPLE and the selection rate set by the canonical 70/30 cut ----")
    p(f"   common rows (y30 and ALL four signals defined): {len(pan):,} of "
      f"{len(panel):,} decisions = {len(pan) / len(panel):.2%}")
    p(f"   70/30 fires on {int(sel_rsi.sum()):,} of {len(pan):,} = {rate:.4%}")
    p("   Every comparator below is matched to THIS rate ON THESE ROWS")
    p("   (LEARNINGS 2026-07-27): an unmatched comparison, or one taken on a")
    p("   different denominator, reads a selectivity dial rather than a signal.")

    # ------------------------------------------------------------ per-slot calib
    p("")
    p("-- CALIBRATION: is the fixed 70/30 cut a TIME-OF-DAY selector? ------------")
    p("   RSI's denominator is a TRAILING window, so it lags volatility")
    p("   transitions. The incumbent's denominator is a causal SAME-SLOT scale,")
    p("   which is the construction that exists to prevent exactly this.")
    p("")
    inc_sel = _matched_sel(pan["dev_past30_z"].to_numpy(), rate)
    tmp = pan.assign(_r=sel_rsi, _i=inc_sel)
    # Slots are counted only on the common sample, so a structurally impossible
    # slot (mfo 29 has no past_30; mfo 1379 has no fwd_30) cannot enter the CV as
    # a spurious zero.
    per = tmp.groupby("mfo")[["_r", "_i"]].agg(["mean", "size"])
    per = per[per[("_r", "size")] >= 100]
    rr, ii = per[("_r", "mean")], per[("_i", "mean")]
    cv_r = float(rr.std() / rr.mean())
    cv_i = float(ii.std() / ii.mean())
    p(f"   {len(per)} slots with >=100 common decisions")
    p(f"   per-slot selection-rate CV   RSI 70/30 {cv_r:.4f}   "
      f"incumbent same-slot z {cv_i:.4f}   ratio {cv_r / cv_i:.2f}x")
    p("   worst/best slot rate:")
    for nm, s in (("RSI 70/30", rr), ("incumbent", ii)):
        s = s.sort_values()
        p(f"     {nm:<11} min {s.iloc[0]:.4%} @ mfo {s.index[0]}   "
          f"max {s.iloc[-1]:.4%} @ mfo {s.index[-1]}   "
          f"max/min {s.iloc[-1] / s.iloc[0]:.1f}x")
    p("   selection rate by block:")
    bl = tmp.groupby("block")[["_r", "_i"]].mean()
    for b in BLOCKS:
        p(f"     {b:<9} RSI {bl.loc[b, '_r']:.4%}   incumbent {bl.loc[b, '_i']:.4%}")

    # ------------------------------------------------------------ PRIMARY + arms
    p("")
    p("-- PRIMARY and the two mandatory controls, ALL at matched selection rate --")
    p("")
    p("   signal                          n      per-bet unit    cl-t    boot95")
    y = pan["y30"].to_numpy()
    sd = pan["sdate"].to_numpy()
    arms = {}

    r_pnl = _fade((pan[rcol] - 50.0).to_numpy(), y, sel_rsi)
    arms["rsi_14 (70/30)"] = _cell(r_pnl, sd[sel_rsi], rng, NBOOT)

    for label, col, centre in (
            (f"rsi_num_{N} (bare NUMERATOR)", ncol, 0.0),
            ("dev_past30_z (INCUMBENT)", "dev_past30_z", 0.0),
            ("past_30 raw (no normaliser)", "past_30_pip", 0.0),
            (f"rsi_{N} at matched rate", rcol, 50.0)):
        s = _matched_sel(pan[col].to_numpy(), rate, centre)
        arms[label] = _cell(_fade(pan[col].to_numpy() - centre, y, s), sd[s],
                            rng, NBOOT)

    for label, c in arms.items():
        ci = (f"  [{c['lo']:+.4f},{c['hi']:+.4f}]" if np.isfinite(c["lo"]) else "")
        p(f"   {label:<30} {c['n']:7,}   {c['mean']:+12.4f}  {c['t']:+6.2f}{ci}")

    prim = arms["rsi_14 (70/30)"]
    num_arm = arms[f"rsi_num_{N} (bare NUMERATOR)"]
    inc_arm = arms["dev_past30_z (INCUMBENT)"]

    # ------------------------------------------------------------ partial IC
    p("")
    p("-- INCREMENTAL INFORMATION: partial out the trailing return --------------")
    dd = pan
    raw_ic = S.spearman(dd[rcol].to_numpy(), dd["y30"].to_numpy())
    par_ic = S.partial_spearman(dd[rcol].to_numpy(), dd["y30"].to_numpy(),
                                dd["past_30_pip"].to_numpy())
    p(f"   IC(rsi_{N}, fwd_30)              {raw_ic:+.5f}")
    p(f"   IC(rsi_{N}, fwd_30 | past_30)    {par_ic:+.5f}   "
      f"retained {par_ic / raw_ic if raw_ic else np.nan:.1%}")
    dz = pan
    p(f"   for reference, incumbent IC      "
      f"{S.spearman(dz['dev_past30_z'].to_numpy(), dz['y30'].to_numpy()):+.5f}")

    # ------------------------------------------------------------ neighbours
    p("")
    p("-- NEIGHBOURING WINDOWS (rule 18) ----------------------------------------")
    p("   n      sel rate    per-bet unit    cl-t")
    for n in (R.NEIGHBOURS[0], N, R.NEIGHBOURS[1]):
        c_ = f"rsi_{n}"
        s = (((pan[c_] >= HI) | (pan[c_] <= LO))
             & np.isfinite(pan[c_])).to_numpy()
        cc = _cell(_fade((pan[c_] - 50.0).to_numpy(), y, s), sd[s], rng)
        p(f"   {n:<6} {s.mean():9.4%}   {cc['mean']:+12.4f}  {cc['t']:+6.2f}")

    # ------------------------------------------------------------ shared bar
    p("")
    p("-- CONTROL: size the shared-decision-bar artifact on this signal ----------")
    shared = ((pan["fwd_30"] + pan["entry_px"] - pan["close"]) / unit).to_numpy()
    sc_ = _cell(_fade((pan[rcol] - 50.0).to_numpy(), shared, sel_rsi),
                sd[sel_rsi], rng)
    p(f"   honest entry=open(m+1)  {prim['mean']:+.4f}  t {prim['t']:+.2f}")
    p(f"   naive  entry=close(m)   {sc_['mean']:+.4f}  t {sc_['t']:+.2f}")
    if abs(sc_["mean"]) > 1e-12:
        p(f"   -> honest retains {prim['mean'] / sc_['mean']:.1%} of the naive estimate")

    # ------------------------------------------------------------ estimand
    p("")
    p("-- CONTROL: estimand contrast (reported, never used) ---------------------")
    bm, bt, nb = S.block_mean_t(r_pnl, sd[sel_rsi])
    mcc = S.mean_count_corr(r_pnl, sd[sel_rsi])
    p(f"   per-bet {prim['mean']:+.4f} (t {prim['t']:+.2f})  vs  session-averaged "
      f"{bm:+.4f} (t {bt:+.2f}, {nb:,} sessions)")
    p(f"   corr(session mean, session count) = {mcc:+.4f}")

    # ------------------------------------------------------------ era + cost
    p("")
    p("-- CONTROL: era stability and era-appropriate costs (rules 19, 20) -------")
    p("   year       n    per-bet unit    cl-t")
    signs = []
    for yr, g in pan[sel_rsi].groupby("year"):
        gp = _fade((g[rcol] - 50.0).to_numpy(), g["y30"].to_numpy(),
                   np.ones(len(g), bool))
        c_ = _cell(gp, g["sdate"].to_numpy(), rng)
        if c_["n"] < 30:
            continue
        signs.append(np.sign(c_["mean"]))
        p(f"   {yr}  {c_['n']:6,}   {c_['mean']:+12.4f}  {c_['t']:+6.2f}")
    p(f"   sign stability: {int(sum(s > 0 for s in signs))}/{len(signs)} years positive")
    p("")
    for lo_y, hi_y in (("2010", "2015"), ("2016", "2023")):
        ts = D.tick_size(product, int(lo_y))
        tick_u = ts / unit
        sub = pan[sel_rsi & pan["year"].isin(
            range(int(lo_y), int(hi_y) + 1)).to_numpy()]
        if len(sub) < 50:
            continue
        c_ = _cell(_fade((sub[rcol] - 50.0).to_numpy(), sub["y30"].to_numpy(),
                         np.ones(len(sub), bool)), sub["sdate"].to_numpy(), rng)
        rt = 2 * tick_u
        p(f"   {lo_y}-{hi_y}: tick {ts:g} = {tick_u:.1f} unit; gross "
          f"{c_['mean']:+.4f} vs optimistic round trip {rt:.1f} -> net "
          f"{c_['mean'] - rt:+.4f} unit "
          f"(${(c_['mean'] - rt) * D.usd_per_pip(product):+.2f}/bet)")

    # ------------------------------------------------------------ KILL TEST
    p("")
    p("-- KILL TEST (declared in HYP-0006 before RSI touched real bars) ---------")
    k1 = prim["mean"] > 0 and not (prim["lo"] <= 0 <= prim["hi"])
    k2 = prim["mean"] > num_arm["mean"]
    k3 = prim["mean"] > inc_arm["mean"]
    k4 = abs(par_ic) >= 0.5 * abs(raw_ic)
    p(f"   1. sign/signif  M>0 and CI excludes 0?     {'PASS' if k1 else 'FAIL'}"
      f"   ({prim['mean']:+.4f}, CI [{prim['lo']:+.4f},{prim['hi']:+.4f}])")
    p(f"   2. bare NUMER.  RSI beats its numerator?   {'PASS' if k2 else 'FAIL'}"
      f"   ({prim['mean']:+.4f} vs {num_arm['mean']:+.4f})")
    p(f"   3. INCUMBENT    RSI beats past30_z?        {'PASS' if k3 else 'FAIL'}"
      f"   ({prim['mean']:+.4f} vs {inc_arm['mean']:+.4f})")
    p(f"   4. incremental  partial IC >= 50% of raw?  {'PASS' if k4 else 'FAIL'}"
      f"   ({par_ic:+.5f} vs {raw_ic:+.5f})")
    p("")
    p("   Arms 2 and 3 are the ones that matter: a signal that cannot beat its own")
    p("   numerator, or the incumbent it is a re-normalisation of, has added")
    p("   nothing regardless of whether it clears zero.")

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / f"rsi_{product}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RUN / f'rsi_{product}.txt'}")
    return {"product": product, "prim": prim, "num": num_arm, "inc": inc_arm,
            "k": (k1, k2, k3, k4), "cv_r": cv_r, "cv_i": cv_i, "rate": rate,
            "raw_ic": raw_ic, "par_ic": par_ic}


def main(argv):
    prods = [argv[1]] if len(argv) > 1 else ["6E", "6B", "6J"]
    out = [run(pr) for pr in prods]
    if len(out) > 1:
        print("\n" + "=" * 100)
        print("SUMMARY  (arms: sign / beats-numerator / beats-incumbent / incremental)")
        for r in out:
            print(f"  {r['product']}  RSI {r['prim']['mean']:+.4f} (t {r['prim']['t']:+.2f})"
                  f"  numerator {r['num']['mean']:+.4f}  incumbent {r['inc']['mean']:+.4f}"
                  f"  selCV {r['cv_r']:.3f} vs {r['cv_i']:.3f}"
                  f"  arms {['PASS' if x else 'FAIL' for x in r['k']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
