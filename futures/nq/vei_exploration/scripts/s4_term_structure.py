"""Study F -- momentum TERM STRUCTURE by VEI regime, and the TIME-OF-DAY audit of Study D.

Study D (EXP-0003) found corr(past 30m ret, next 30m ret) ~0 in low/calm VEI but +0.10
when VEI>1.10, on both NQ and ES; EXP-0004 then showed the effect STRENGTHENS from a
30-min to a 60-min hold and stopped there. Two things were never checked, and both bear
directly on whether that finding means what it says:

  1. WHERE DOES THE EFFECT PEAK? Only one horizon (30 min) was ever measured in D, and
     only {15,30,60} in E. F1 maps the full decay curve, F2 corroborates it with a
     Lo-MacKinlay variance ratio -- an independent momentum/MR read that does NOT share
     the past->forward correlation estimator (Study D's own docstring promised VR by
     regime and never computed it).

  2. IS IT A VOLATILITY REGIME, OR JUST A CLOCK? Wilder VEI has a strong deterministic
     time-of-day profile: the within-session ATR(50) is anchored to the volatile open,
     so VEI drifts UP all day and `VEI>1.10` is a ~1% event in the morning but routine
     late. No script in this project has ever grouped by time of day. F3 measures the
     per-slot profile, the per-slot unconditional correlation, the TIME-OF-DAY-MATCHED
     high-vs-rest contrast (the actual audit), and puts the raw level head to head with
     a causal same-slot percentile rank AT MATCHED SELECTION COUNT -- comparing two
     normalisations at equal threshold only reads a selectivity dial, not a reshape.

  F4 de-confounds the trailing-return window from the regime window (both hardwired at
  30) and carries a small (short,long) robustness column.

DESCRIPTIVE ONLY -- no trading, no fills, no costs, and therefore no Null C. Every
number is a measurement of the tape. The kill test is stated in HYP-0002.md: if the
time-of-day-matched contrast (F3c) collapses to ~0 on either market, Study D is
substantially a clock effect and FINDINGS.md/MEMORY.md must say so.

Usage:
  python -u -m futures.nq.vei_exploration.scripts.s4_term_structure {NQ|ES} [--quick]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import loaders as L
from ..core import vei as V
from ..core import analysis as A

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "F_term_structure"
SEED = 74000
DM = A.DM
VEI_KW = dict(short=10, long=50, atr_method="wilder", smooth=0)
T_HIGH = 1.10                    # the Study D / HYP-0001 regime cut, carried over
REGIMES = [("low(<0.90)", -np.inf, 0.90),
           ("calm(0.90-1.10)", 0.90, 1.10),
           ("high(>1.10)", 1.10, np.inf)]
HORIZONS = [5, 10, 15, 30, 60, 90, 120, "close"]
VR_Q = [2, 5, 10, 30]
VR_WINDOW = 60                   # minutes of forward path used for the variance ratio
PAST_WINS = [10, 30, 60]
VEI_VARIANTS = [("5_20", dict(short=5, long=20, atr_method="wilder", smooth=0)),
                ("10_50", dict(short=10, long=50, atr_method="wilder", smooth=0)),
                ("10_100", dict(short=10, long=100, atr_method="wilder", smooth=0))]
PCT_LOOKBACK, PCT_MIN_OBS = 90, 60


def clock(m: int) -> str:
    """Decision minute-from-open -> the ET wall clock of the following bar's open."""
    t = 570 + m + 1
    return f"{t // 60:02d}:{t % 60:02d}"


def regime_of(v: pd.Series) -> pd.Series:
    out = pd.Series(index=v.index, dtype=object)
    for name, lo, hi in REGIMES:
        out[(v >= lo) & (v < hi)] = name
    return out


MIN_CELL = 30          # a (slot, group) cell below this is too thin to correlate


def _grouped_corr(key: np.ndarray, x: np.ndarray, y: np.ndarray, ng: int):
    """Pearson correlation of x vs y within each integer group code. Vectorised."""
    n = np.bincount(key, minlength=ng).astype(float)
    sx = np.bincount(key, weights=x, minlength=ng)
    sy = np.bincount(key, weights=y, minlength=ng)
    sxx = np.bincount(key, weights=x * x, minlength=ng)
    syy = np.bincount(key, weights=y * y, minlength=ng)
    sxy = np.bincount(key, weights=x * y, minlength=ng)
    cov = n * sxy - sx * sy
    den = np.sqrt(np.maximum(n * sxx - sx * sx, 0) * np.maximum(n * syy - sy * sy, 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        c = np.where(den > 0, cov / den, np.nan)
    return c, n


def _slot_contrast(key_hi: np.ndarray, key_rest: np.ndarray, x: np.ndarray,
                   y: np.ndarray, is_hi: np.ndarray, nslot: int):
    """Count-weighted mean of the WITHIN-SLOT correlation, high vs rest.

    Correlating inside each time-of-day slot and only then averaging removes slot
    composition entirely: a pooled contrast can differ between two groups purely
    because they sit at different times of day. Returns (corr_high, corr_rest, diff).
    """
    out = []
    for k, m in ((key_hi, is_hi), (key_rest, ~is_hi)):
        c, n = _grouped_corr(k[m], x[m], y[m], nslot)
        ok = np.isfinite(c) & (n >= MIN_CELL)
        out.append(float(np.sum(c[ok] * n[ok]) / np.sum(n[ok]))
                   if ok.any() else np.nan)
    return out[0], out[1], out[0] - out[1]


def slot_contrast_arrays(d: pd.DataFrame, hicol: str, xcol: str, ycol: str):
    """Pack a frame into the numpy arrays `_slot_contrast` consumes."""
    codes, uniq = pd.factorize(d["mfo"].to_numpy())
    return dict(key=codes.astype(np.intp), x=d[xcol].to_numpy(float),
                y=d[ycol].to_numpy(float), is_hi=d[hicol].to_numpy(bool),
                nslot=len(uniq))


def weighted_slot_contrast(a: dict) -> tuple[float, float, float]:
    return _slot_contrast(a["key"], a["key"], a["x"], a["y"], a["is_hi"], a["nslot"])


def boot_slot_contrast(d: pd.DataFrame, a: dict, rng, nboot: int
                       ) -> tuple[float, float]:
    """Session-block bootstrap 90% CI on the within-slot high-minus-rest difference."""
    order, sl = A.session_slices(d, "date")
    key = a["key"][order]; x = a["x"][order]; y = a["y"][order]
    is_hi = a["is_hi"][order]
    idx = [np.arange(s.start, s.stop) for s in sl]
    boots = np.empty(nboot)
    for b in range(nboot):
        pick = rng.integers(0, len(sl), size=len(sl))
        take = np.concatenate([idx[j] for j in pick])
        boots[b] = _slot_contrast(key[take], key[take], x[take], y[take],
                                  is_hi[take], a["nslot"])[2]
    return float(np.nanpercentile(boots, 5)), float(np.nanpercentile(boots, 95))


def run(inst: str, quick: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    nboot = 200 if quick else 1000
    nboot_slot = 200 if quick else 1000
    rng = np.random.default_rng(SEED)

    bars = L.load_1m_rth(inst)
    b = V.add_vei(bars, **VEI_KW)
    feat = (b[b["mfo"].isin(DM)][["sdate", "mfo", "vei"]]
            .rename(columns={"sdate": "date"}))
    ff = A.forward_features(bars, DM, horizons=HORIZONS, past_win=30)
    d = feat.merge(ff, on=["date", "mfo"])
    d["regime"] = regime_of(d["vei"])
    d["is_high"] = d["vei"] > T_HIGH

    print(f"\n============ Study F: VEI momentum term structure + "
          f"time-of-day audit — {inst} ============")
    print(f"VEI={VEI_KW}  clock={A.PERIOD}m  slots={len(DM)}  "
          f"sessions={bars['sdate'].nunique()}  decisions={len(d)}  nboot={nboot}")

    # ---- rule 9a: report what each construction drops, and where ---------------- #
    cov = (d.assign(defined=d["vei"].notna())
             .groupby("mfo")["defined"].agg(["size", "mean"]))
    cov.columns = ["n", "vei_defined_frac"]
    cov["fwd30_defined_frac"] = d.groupby("mfo")["fwd_ret_30"].apply(
        lambda s: float(s.notna().mean()))
    cov["fwd_close_defined_frac"] = d.groupby("mfo")["fwd_ret_close"].apply(
        lambda s: float(s.notna().mean()))
    cov.insert(0, "clock", [clock(m) for m in cov.index])
    print("\n--- coverage by decision slot (rule 9a) ---")
    print(cov.to_string(float_format=lambda v: f"{v:.4f}"))
    cov.to_csv(OUT / f"coverage_{inst}.csv")

    # ---- F1. decay curve: corr(past 30m, fwd H) by regime ---------------------- #
    #
    # A long horizon only EXISTS for early decision slots (H=120 needs a decision at
    # 14:00 or earlier), and high-VEI is rare early -- so an all-available decay curve
    # confounds the horizon with the time of day. Report it both ways: the full sample
    # per horizon, and a CONSTANT sample of decisions that admit every horizon, which
    # is the only composition-free read of "where does the effect peak".
    longest = max(h for h in HORIZONS if h != "close")
    samples = [("all available (sample varies with H)", d),
               (f"CONSTANT sample: only decisions admitting every horizon "
                f"(<= {clock(389 - longest)})", d[d["mfo"] + longest <= 389])]
    print(f"\n--- F1. momentum term structure: corr(past 30m ret, fwd H ret) "
          f"by VEI regime ---")
    f1 = []
    for label, frame in samples:
        print(f"\n  [{label}]")
        print(f"  {'H':>7} " + " ".join(f"{nm:>32}" for nm, _, _ in REGIMES))
        for H in HORIZONS:
            y = f"fwd_ret_{H}"
            cells = []
            for nm, lo, hi in REGIMES:
                s = frame[(frame["vei"] >= lo) & (frame["vei"] < hi)]
                c, clo, chi = A.block_boot_corr(s, "past_ret", y, rng, nboot)
                n = int(s[y].notna().sum())
                cells.append(f"{c:>+7.4f}[{clo:+.3f},{chi:+.3f}] n={n:<5d}")
                f1.append({"sample": label.split(":")[0], "H": H, "regime": nm,
                           "n": n, "corr": c, "ci_lo": clo, "ci_hi": chi})
            print(f"  {str(H):>7} " + " ".join(f"{c:>32}" for c in cells))
    pd.DataFrame(f1).to_csv(OUT / f"decay_{inst}.csv", index=False)

    # ---- F2. variance ratio of the forward path, by regime --------------------- #
    #
    # Same composition trap: a 60-min forward window excludes the late slots where
    # high-VEI concentrates. So the headline is the WITHIN-SLOT paired difference
    # (high minus rest, computed inside each slot then count-weighted), matching F3c's
    # method; the pooled figures are printed for context only.
    print(f"\n--- F2. Lo-MacKinlay VR(q) of the forward {VR_WINDOW}-min 1-min return "
          f"path (>1 trending, <1 reverting) ---")
    elig = d[(d["mfo"] + VR_WINDOW <= 389) & d["vei"].notna()].copy()
    wins = {}
    for key, s in (("high", elig[elig["is_high"]]), ("rest", elig[~elig["is_high"]])):
        wins[key] = {m: A.forward_return_windows(bars, zip(g["date"], g["mfo"]),
                                                 VR_WINDOW)
                     for m, g in s.groupby("mfo", sort=True)}
    print(f"  eligible slots: {clock(elig['mfo'].min())}-{clock(elig['mfo'].max())} "
          f"({elig['mfo'].nunique()} of {len(DM)}); "
          f"high windows={sum(len(w) for w in wins['high'].values())}, "
          f"rest={sum(len(w) for w in wins['rest'].values())}")
    f2, f2_slot = [], []
    print(f"  {'q':>4} {'VR high':>9} {'VR rest':>9} {'within-slot diff':>18}")
    for q in VR_Q:
        pooled = {}
        for key in ("high", "rest"):
            allw = [w for w in wins[key].values() if len(w)]
            pooled[key] = (A.variance_ratio_windows(np.vstack(allw), q)
                           if allw else np.nan)
        num = den = 0.0
        for m in sorted(set(wins["high"]) & set(wins["rest"])):
            vh = A.variance_ratio_windows(wins["high"][m], q)
            vr_ = A.variance_ratio_windows(wins["rest"][m], q)
            f2_slot.append({"q": q, "mfo": m, "clock": clock(m),
                            "n_high": len(wins["high"][m]), "vr_high": vh,
                            "n_rest": len(wins["rest"][m]), "vr_rest": vr_})
            if np.isfinite(vh) and np.isfinite(vr_):
                num += (vh - vr_) * len(wins["high"][m])
                den += len(wins["high"][m])
        diff = num / den if den else np.nan
        print(f"  {q:>4} {pooled['high']:>9.4f} {pooled['rest']:>9.4f} {diff:>+18.4f}")
        f2.append({"q": q, "vr_high_pooled": pooled["high"],
                   "vr_rest_pooled": pooled["rest"], "vr_diff_within_slot": diff})
    pd.DataFrame(f2).to_csv(OUT / f"vr_{inst}.csv", index=False)
    pd.DataFrame(f2_slot).to_csv(OUT / f"vr_by_slot_{inst}.csv", index=False)

    # ---- F3a/b. per-slot VEI profile and unconditional correlation ------------- #
    print("\n--- F3a/b. VEI profile and UNCONDITIONAL momentum by decision slot ---")
    rows = []
    for m, g in d.groupby("mfo", sort=True):
        gg = g.dropna(subset=["past_ret", "fwd_ret_30"])
        c = (np.corrcoef(gg["past_ret"], gg["fwd_ret_30"])[0, 1]
             if len(gg) > 2 else np.nan)
        rows.append({"mfo": m, "clock": clock(m), "n": len(g),
                     "vei_mean": g["vei"].mean(), "vei_median": g["vei"].median(),
                     "frac_high": float((g["vei"] > T_HIGH).mean()),
                     "frac_low": float((g["vei"] < 0.90).mean()),
                     "corr_uncond": c})
    slots = pd.DataFrame(rows)
    print(slots.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    slots.to_csv(OUT / f"by_slot_{inst}.csv", index=False)
    share = slots["frac_high"] * slots["n"]
    print(f"  high-VEI decisions are {100 * share[slots['mfo'] >= 269].sum() / share.sum():.1f}% "
          f"concentrated in the 14:00-and-later slots "
          f"(those slots are {100 * 4 / len(slots):.1f}% of the clock)")

    # ---- F3c. THE AUDIT: time-of-day-matched high-vs-rest contrast ------------- #
    print("\n--- F3c. TIME-OF-DAY-MATCHED contrast (within-slot corr, count-weighted) ---")
    dd = d.dropna(subset=["past_ret", "fwd_ret_30", "vei"]).copy()
    pooled_hi, _, _ = A.block_boot_corr(dd[dd["is_high"]], "past_ret", "fwd_ret_30",
                                        rng, nboot)
    pooled_rest, _, _ = A.block_boot_corr(dd[~dd["is_high"]], "past_ret", "fwd_ret_30",
                                          rng, nboot)
    arr = slot_contrast_arrays(dd, "is_high", "past_ret", "fwd_ret_30")
    ch, cr, diff = weighted_slot_contrast(arr)
    dlo, dhi = boot_slot_contrast(dd, arr, rng, nboot_slot)
    print(f"  POOLED (Study D style, slot composition free to differ):")
    print(f"    high>{T_HIGH}={pooled_hi:+.4f}   rest={pooled_rest:+.4f}   "
          f"difference={pooled_hi - pooled_rest:+.4f}")
    print(f"  WITHIN-SLOT (time-of-day matched):")
    print(f"    high>{T_HIGH}={ch:+.4f}   rest={cr:+.4f}   "
          f"difference={diff:+.4f} [{dlo:+.4f},{dhi:+.4f}]")
    shrink = (diff / (pooled_hi - pooled_rest)) if (pooled_hi - pooled_rest) else np.nan
    print(f"    -> the contrast retains {100 * shrink:.0f}% of its pooled size once "
          f"time of day is matched")

    per_slot = []
    for m, g in dd.groupby("mfo", sort=True):
        hi_, rest_ = g[g["is_high"]], g[~g["is_high"]]
        f = lambda s: (np.corrcoef(s["past_ret"], s["fwd_ret_30"])[0, 1]
                       if len(s) >= MIN_CELL else np.nan)
        per_slot.append({"mfo": m, "clock": clock(m), "n_high": len(hi_),
                         "corr_high": f(hi_), "n_rest": len(rest_),
                         "corr_rest": f(rest_)})
    ps = pd.DataFrame(per_slot)
    ps["diff"] = ps["corr_high"] - ps["corr_rest"]
    print("\n  per-slot detail:")
    print(ps.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    ps.to_csv(OUT / f"slot_contrast_{inst}.csv", index=False)

    # ---- F3c-b. HYP-0003 kill test 3: FEATURE effect or THRESHOLD effect? ------- #
    #
    # Repairing the Wilder ATR warm-up (seed='sma') shifts the VEI distribution upward,
    # so the fixed T_HIGH=1.10 cut no longer selects the same-sized set it did under the
    # legacy seeding. Re-run the PRIMARY statistic three ways: repaired at the absolute
    # cut, repaired at the legacy SELECTION RATE, and the legacy feature itself. A
    # result present at only one cut is a threshold effect, not a feature effect.
    print("\n--- F3c-b. threshold confound control (HYP-0003 kill test 3) ---")
    bl = V.add_vei(bars, **{**VEI_KW, "seed": V.SEED_FIRST})
    legacy = (bl[bl["mfo"].isin(DM)][["sdate", "mfo", "vei"]]
              .rename(columns={"sdate": "date", "vei": "vei_legacy"}))
    dt = dd.merge(legacy, on=["date", "mfo"], how="left")
    share_legacy = float((dt["vei_legacy"] > T_HIGH).mean())
    t_match = float(dt["vei"].quantile(1.0 - share_legacy))
    print(f"  legacy-seed selection share above {T_HIGH} = {share_legacy:.4f}  ->  "
          f"matched-rate cut on the repaired VEI = {t_match:.4f}")
    print(f"  {'cut':>34} {'n_high':>7} {'within-slot diff':>18} {'CI':>20}")
    tc = []
    for label, col, cut in [
        (f"repaired, absolute >{T_HIGH}", "vei", T_HIGH),
        (f"repaired, matched-rate >{t_match:.3f}", "vei", t_match),
        (f"LEGACY seed, absolute >{T_HIGH}", "vei_legacy", T_HIGH),
    ]:
        t = dt.dropna(subset=[col]).copy()
        t["is_hi_x"] = t[col] > cut
        a2 = slot_contrast_arrays(t, "is_hi_x", "past_ret", "fwd_ret_30")
        _, _, dfx = weighted_slot_contrast(a2)
        lo2, hi2 = boot_slot_contrast(t, a2, rng, nboot_slot)
        print(f"  {label:>34} {int(t['is_hi_x'].sum()):>7} {dfx:>+18.4f} "
              f"[{lo2:+.4f},{hi2:+.4f}]")
        tc.append({"cut": label, "n_high": int(t["is_hi_x"].sum()), "diff": dfx,
                   "ci_lo": lo2, "ci_hi": hi2})
    pd.DataFrame(tc).to_csv(OUT / f"threshold_control_{inst}.csv", index=False)
    print("  Read: HYP-0003 kill test 3 passes only if the repaired contrast holds at\n"
          "  BOTH the absolute and the matched-rate cut.")

    # ---- F3d. raw level vs causal same-slot percentile, AT MATCHED COUNT -------- #
    print(f"\n--- F3d. raw VEI level vs causal same-slot PERCENTILE, matched selection "
          f"count (lookback={PCT_LOOKBACK}, min_obs={PCT_MIN_OBS}) ---")
    d["vei_pct"] = A.causal_slot_percentile(d, "vei", lookback=PCT_LOOKBACK,
                                            min_obs=PCT_MIN_OBS)
    dp = d.dropna(subset=["past_ret", "fwd_ret_30", "vei", "vei_pct"]).copy()
    K = int((dp["vei"] > T_HIGH).sum())
    raw_sel = dp["vei"] > T_HIGH
    pct_sel = dp["vei_pct"] >= dp["vei_pct"].nlargest(K).iloc[-1]
    print(f"  matched K={K} of {len(dp)} decisions "
          f"({100 * K / len(dp):.1f}%); percentile cut = "
          f"{dp['vei_pct'].nlargest(K).iloc[-1]:.4f}")
    f3d = []
    for nm, sel in (("raw_level", raw_sel), ("slot_percentile", pct_sel)):
        c, lo_, hi_ = A.block_boot_corr(dp[sel], "past_ret", "fwd_ret_30", rng, nboot)
        print(f"  {nm:>16} n={int(sel.sum()):>6} corr={c:+.4f} [{lo_:+.4f},{hi_:+.4f}]")
        f3d.append({"scheme": nm, "n": int(sel.sum()), "corr": c,
                    "ci_lo": lo_, "ci_hi": hi_})
    pd.DataFrame(f3d).to_csv(OUT / f"norm_compare_{inst}.csv", index=False)
    # where each scheme spends its selections -- a flat residual means it only
    # changed selectivity, not what it selects
    spread = pd.DataFrame({
        "clock": [clock(m) for m in sorted(dp["mfo"].unique())],
        "raw_share": dp[raw_sel].groupby("mfo").size().reindex(
            sorted(dp["mfo"].unique()), fill_value=0).to_numpy() / K,
        "pct_share": dp[pct_sel].groupby("mfo").size().reindex(
            sorted(dp["mfo"].unique()), fill_value=0).to_numpy() / K})
    print("\n  selection share by slot (raw vs percentile):")
    print(spread.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    spread.to_csv(OUT / f"selection_share_{inst}.csv", index=False)

    # ---- F4. robustness: past_win and (short,long) ----------------------------- #
    print("\n--- F4. robustness: trailing window x VEI (short,long), matched selectivity "
          "at H=30 ---")
    # matched to Study D's own selectivity, so it must be measured on Study D's own
    # population: decisions that have a valid VEI *and* a forward 30-min window (the
    # 16:00 slot has no forward window and is 64% high-VEI, so including it would
    # inflate the target rate).
    base_rate = float((dd["vei"] > T_HIGH).mean())
    print(f"  every variant selects its top {100 * base_rate:.1f}% of decisions "
          f"(matched to VEI(10,50)>{T_HIGH}), so cells differ only in the FEATURE")
    print(f"{'vei':>8} {'past_win':>9} {'n':>7} {'corr_high':>22} {'corr_rest':>10}")
    f4 = []
    for vname, kw in VEI_VARIANTS:
        bv = V.add_vei(bars, **kw)
        fv = (bv[bv["mfo"].isin(DM)][["sdate", "mfo", "vei"]]
              .rename(columns={"sdate": "date"}))
        for pw in PAST_WINS:
            ffp = A.forward_features(bars, DM, horizons=(30,), past_win=pw)
            dv = fv.merge(ffp, on=["date", "mfo"]).dropna(
                subset=["vei", "past_ret", "fwd_ret_30"])
            thr = float(dv["vei"].quantile(1.0 - base_rate))
            hi_ = dv[dv["vei"] > thr]
            rest_ = dv[dv["vei"] <= thr]
            c, lo_, hi2 = A.block_boot_corr(hi_, "past_ret", "fwd_ret_30", rng, nboot)
            cr_ = float(np.corrcoef(rest_["past_ret"], rest_["fwd_ret_30"])[0, 1])
            print(f"{vname:>8} {pw:>9} {len(hi_):>7} "
                  f"{c:>+8.4f}[{lo_:+.3f},{hi2:+.3f}] {cr_:>+10.4f}")
            f4.append({"vei": vname, "past_win": pw, "thr": thr, "n_high": len(hi_),
                       "corr_high": c, "ci_lo": lo_, "ci_hi": hi2,
                       "corr_rest": cr_})
    pd.DataFrame(f4).to_csv(OUT / f"robustness_{inst}.csv", index=False)

    print(f"\nartifacts -> {OUT}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inst", nargs="?", default="NQ", choices=["NQ", "ES"])
    p.add_argument("--quick", action="store_true",
                   help="fewer bootstrap draws (smoke test, not for the record)")
    a = p.parse_args()
    run(a.inst, quick=a.quick)


if __name__ == "__main__":
    main()
