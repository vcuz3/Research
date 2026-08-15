"""Stage 1d — (A) is the tiny 5-min negative IC just move-size?  (B) absorption.

(A) Confound control: z_V and z_R are positively correlated, so "high-volume
    displacements revert more" may just be "bigger displacements revert more".
    Recompute IC(z_V, dir) WITHIN narrow |z_R| bands.  If it vanishes, the
    residual is move-size, not volume.

(B) Effort-vs-result / absorption: the other reading of "unusual volume-price".
    2x2 of (quiet |z_R|<0.5  vs  displaced |z_R|>=1.5) x (z_V lo/hi tercile).
    Report forward directional return (dir=sign(R)*fwd) AND forward magnitude
    (|fwd|) -- does high-volume-but-no-move ("coiling") predict a bigger or
    directional forward move?  All embargo=1, W=5, hold=5min, pooled.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from _stage1b_decisive import bars_with_z, fwd_return

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]


def frame(pair: str, W: int, step: int) -> pd.DataFrame:
    b = bars_with_z(pair, W)
    b["fwd"] = fwd_return(b, W, step, embargo=1)
    b = b.dropna(subset=["z_R", "z_V", "fwd"])
    b["dir"] = np.sign(b["R"]) * b["fwd"]
    b["absfwd"] = b["fwd"].abs()
    b["pair"] = pair
    return b[["z_R", "z_V", "R", "fwd", "dir", "absfwd", "pair"]]


def main():
    W, step = 5, 1
    pooled = pd.concat([frame(p, W, step) for p in PAIRS], ignore_index=True)

    print(f"=== (A) IC(z_V, dir) within narrow |z_R| bands (embargo=1, W={W}, hold={W*step}min) ===")
    bands = [(1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 10.0)]
    for lo, hi in bands:
        m = (pooled["z_R"].abs() >= lo) & (pooled["z_R"].abs() < hi)
        sub = pooled[m]
        ic = spearmanr(sub["z_V"], sub["dir"]).correlation
        print(
            f"  |z_R| in [{lo:.1f},{hi:.1f}): n={len(sub):>7,}  "
            f"IC(z_V,dir)={ic:+.4f}  mean dir={sub['dir'].mean():+.3f} pips"
        )

    print("\n=== (B) effort-vs-result 2x2 (quiet vs displaced) x (volume lo/hi) ===")
    # define volume terciles on the WHOLE pooled sample per regime for balance
    for reg, mask in [
        ("quiet  |z_R|<0.5 ", pooled["z_R"].abs() < 0.5),
        ("disp   |z_R|>=1.5", pooled["z_R"].abs() >= 1.5),
    ]:
        sub = pooled[mask].copy()
        terc = pd.qcut(sub["z_V"], 3, labels=["Vlo", "Vmid", "Vhi"])
        agg = sub.groupby(terc, observed=True).agg(
            n=("fwd", "size"),
            dir_mean=("dir", "mean"),
            absfwd_mean=("absfwd", "mean"),
        )
        print(f"\n  {reg}:")
        for lab in ["Vlo", "Vmid", "Vhi"]:
            r = agg.loc[lab]
            print(
                f"    {lab}: n={int(r['n']):>7,}  dir={r['dir_mean']:+.3f} pips  "
                f"|fwd|={r['absfwd_mean']:.3f} pips"
            )

    # magnitude edge check: does z_V predict |fwd| among quiet bars? (coiling)
    q = pooled[pooled["z_R"].abs() < 0.5]
    ic_mag = spearmanr(q["z_V"], q["absfwd"]).correlation
    print(
        f"\n  IC(z_V, |fwd|) among QUIET bars = {ic_mag:+.4f}  "
        f"(volume predicting forward *magnitude*, not direction)"
    )


if __name__ == "__main__":
    main()
