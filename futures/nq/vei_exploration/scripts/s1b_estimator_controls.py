"""Study A follow-up (2026-07-26 review) -- the CONTROL CELLS EXP-0001 omitted.

EXP-0001 concluded "the ATR estimator dominates smoothing". A reviewer objected that
the comparison was confounded. Both objections check out; this script is the evidence.

C1: wilder vs sma confounds estimator TYPE with effective MEMORY. Wilder(n) has
    centre-of-mass n-1; SMA(n) has (n-1)/2. So wilder(10,50) carries ~2x the memory of
    sma(10,50), and the "estimator" comparison changes two things at once. Fixed by
    adding com-matched cells in BOTH directions: sma(19,99) and wilder(5,25).
    Also: Wilder alpha=1/n IS ewm(span=2n-1), so wilder(10,50) and ema(19,99) are the
    SAME recursion -- they differ only in min_periods, which isolates the warm-up cost.
C2: `ewm(adjust=False, min_periods=n)` seeds the recursion at the FIRST observation and
    merely masks the first n-1 values; textbook Wilder seeds with the first n-bar SMA.
    The ATR resets per session, so this recurs ~3710 times. Fixed cell:
    wilder_10_50_TEXTBOOK_INIT.

Also prints mean VEI by decision slot, which shows the mean<1 is NOT mainly an init
artifact but the session-reset ATR anchoring on the high-vol open (VEI drifts 0.75->1.17
through the day). See reports/FINDINGS.md section A.

Usage: python -u -m futures.nq.vei_exploration.scripts.s1b_estimator_controls {NQ|ES}
Artifacts: artifacts/runs/A_smoothing/estimator_controls_{NQ,ES}.txt
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

from futures.nq.vei_exploration.core import loaders as L
from futures.nq.vei_exploration.core import vei as V
from futures.nq.vei_exploration.core import analysis as A
from futures.nq.vei_exploration.scripts.s1_smoothing import (
    persistence_and_whipsaw, DM, SEED)


def wilder_textbook(bars: pd.DataFrame, n: int) -> pd.Series:
    """Textbook Wilder ATR: seed = SMA of first n TRs, then RMA recursion.
    NaN before bar n. Causal, per-session."""
    b = bars.sort_values(["sdate", "mfo"])
    tr = V.true_range(b)

    def _f(x: pd.Series) -> pd.Series:
        v = x.to_numpy(float)
        out = np.full(len(v), np.nan)
        if len(v) < n:
            return pd.Series(out, index=x.index)
        out[n - 1] = v[:n].mean()
        for i in range(n, len(v)):
            out[i] = (out[i - 1] * (n - 1) + v[i]) / n
        return pd.Series(out, index=x.index)

    return tr.groupby(b["sdate"], sort=False).transform(_f).reindex(bars.index)


def vei_textbook(bars, short, long):
    a_s = wilder_textbook(bars, short)
    a_l = wilder_textbook(bars, long)
    v = a_s / a_l
    return v.where(np.isfinite(v))


def main(inst: str) -> None:
    rng = np.random.default_rng(SEED)
    bars = L.load_1m_rth(inst)
    ff = A.forward_features(bars, DM, horizons=(30,), past_win=30)

    # SMA(n) center-of-mass = (n-1)/2 ; Wilder(n) com = n-1.
    # So Wilder(10,50) ~ SMA(19,99) in memory; EMA span 19/99 is EXACTLY Wilder(10,50).
    cells = [
        ("sma_10_50",        lambda b: V.vei_series(b, 10, 50, "sma")),
        ("sma_19_99  [com-matched]", lambda b: V.vei_series(b, 19, 99, "sma")),
        ("ema_10_50",        lambda b: V.vei_series(b, 10, 50, "ema")),
        ("ema_19_99  [alpha=wilder]", lambda b: V.vei_series(b, 19, 99, "ema")),
        ("wilder_10_50",     lambda b: V.vei_series(b, 10, 50, "wilder")),
        ("wilder_5_25 [com=sma10/50]", lambda b: V.vei_series(b, 5, 25, "wilder")),
        ("wilder_10_50_TEXTBOOK_INIT", lambda b: vei_textbook(b, 10, 50)),
    ]

    print(f"\n===== critique check — {inst} ({bars['sdate'].nunique()} sessions) =====")
    print(f"{'variant':>30} {'defined':>8} {'mean':>7} {'median':>7} "
          f"{'AC1':>7} {'whipsaw':>8} {'IC_fwdvol':>10}")
    for name, fn in cells:
        s = fn(bars)
        b2 = bars.copy(); b2["vei"] = s.to_numpy()
        feat = b2[b2["mfo"].isin(DM)][["sdate", "mfo", "vei"]].rename(
            columns={"sdate": "date"})
        ac, whip = persistence_and_whipsaw(feat)
        m = feat.merge(ff[["date", "mfo", "fwd_absvar_30"]], on=["date", "mfo"])
        ic, lo, hi = A.block_boot_ic(m, "vei", "fwd_absvar_30", rng)
        v = feat["vei"].dropna()
        print(f"{name:>30} {len(v):>8} {v.mean():>7.3f} {v.median():>7.3f} "
              f"{ac:>7.3f} {whip:>8.3f} {ic:>+10.4f}")

    # mean VEI by decision slot for the shipped wilder, to see where <1 comes from
    b2 = V.add_vei(bars, short=10, long=50, atr_method="wilder")
    f = b2[b2["mfo"].isin(DM)]
    print("\nshipped wilder_10_50 mean VEI by decision slot (mfo):")
    print(f.groupby("mfo")["vei"].mean().round(3).to_string())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
