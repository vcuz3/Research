"""HYP-0001 / EXP-0001 — is the VOLUME weighting in VWAP load-bearing on FX futures?

Measures the separation between VWAP and its exact constant-volume degenerate
limit (TWAP), against the pre-declared kill test in
`experiments/hypotheses/HYP-0001.md`.

Run:  python -u -m futures.forex.vwap_exploration.scripts.hyp_0001_anatomy [6E|6B]
Out:  artifacts/runs/EXP-0001/anatomy_<product>.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from futures.forex.vwap_exploration.core import data as D
from futures.forex.vwap_exploration.core import frame as F
from futures.forex.vwap_exploration.core import stats as S

RUN = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0001"

KILL_RSEP = 0.10
KILL_CORR = 0.99
PASS_RSEP = 0.25


def run(product: str) -> dict:
    lines: list[str] = []

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 78)
    p(f"EXP-0001  HYP-0001  VWAP vs TWAP anatomy   {product}  "
      f"({D.CONTRACT[product]['name']})")
    p("=" * 78)

    panel = F.build_panel(product, scope="explore")
    p(f"decisions {len(panel):,}   sessions {panel['sdate'].nunique():,}   "
      f"{panel['sdate'].min().date()} -> {panel['sdate'].max().date()}   "
      f"(holdout {D.HOLDOUT_YEARS} sealed)")

    # ---------------------------------------------------------------- 1. profile
    p("")
    p("-- 1. intraday volume profile (share of session volume by 30-min slot) ----")
    vs = F.session_volume_shares(product, scope="explore")
    prof = vs.groupby("slot")["share"].mean()
    mod = (prof.index.to_numpy() + D.SESSION_OPEN_MOD) % 1440
    lab = [f"{m // 60:02d}:{m % 60:02d}" for m in mod]
    p("   ET     share    ET     share    ET     share    ET     share")
    cells = [f"  {lab[i]}  {prof.iloc[i]:6.2%}" for i in range(len(prof))]
    for i in range(0, len(cells), 4):
        p("  " + "".join(f"{c:<22}" for c in cells[i:i + 4]))
    top = prof.sort_values(ascending=False)
    tm = (top.index.to_numpy() + D.SESSION_OPEN_MOD) % 1440
    p(f"   flat profile would be {1 / len(prof):.2%} per slot; "
      f"observed max {top.iloc[0]:.2%} at ET {tm[0] // 60:02d}:{tm[0] % 60:02d}, "
      f"min {top.iloc[-1]:.2%}")
    hhi = float((prof ** 2).sum())
    p(f"   concentration: top-4 slots hold {top.head(4).sum():.1%} of session volume; "
      f"HHI {hhi:.4f} vs {1 / len(prof):.4f} if flat "
      f"(= {hhi * len(prof):.2f}x)")

    # ---------------------------------------------------------------- 2. separation
    d = panel.dropna(subset=["vwap", "twap", "scale_vwap"]).copy()
    d["sep_pip"] = (d["vwap"] - d["twap"]) / D.PIP
    d["scale_pip"] = d["scale_vwap"] / D.PIP
    d["rsep"] = d["sep_pip"].abs() / d["scale_pip"]

    p("")
    p("-- 2. |VWAP - TWAP| against the displacement it is used to measure --------")
    p("   R_sep = |VWAP - TWAP| / (causal trailing same-slot mean |close - VWAP|)")
    p("")
    p("   block      n        med |sep| pip   med scale pip   med R_sep   p90 R_sep")
    for b in ("asia", "ldn_am", "overlap", "ny_pm"):
        g = d[d["block"] == b]
        if not len(g):
            continue
        p(f"   {b:<9} {len(g):8,}   {g['sep_pip'].abs().median():12.3f}   "
          f"{g['scale_pip'].median():13.3f}   {g['rsep'].median():9.3f}   "
          f"{g['rsep'].quantile(.90):9.3f}")
    rsep_pooled = float(d["rsep"].median())
    last = d[d["mod"] == 16 * 60 + 29]
    rsep_last = float(last["rsep"].median()) if len(last) else np.nan
    p(f"   {'POOLED':<9} {len(d):8,}   {d['sep_pip'].abs().median():12.3f}   "
      f"{d['scale_pip'].median():13.3f}   {rsep_pooled:9.3f}   "
      f"{d['rsep'].quantile(.90):9.3f}")
    p(f"   16:29 ET   {len(last):8,}   {last['sep_pip'].abs().median():12.3f}   "
      f"{last['scale_pip'].median():13.3f}   {rsep_last:9.3f}   "
      f"{last['rsep'].quantile(.90):9.3f}")

    # separation must grow through the session if the construction is right
    by_slot = d.groupby("mod")["sep_pip"].apply(lambda s: s.abs().median())
    early = by_slot[by_slot.index < 3 * 60].mean()
    late = by_slot[(by_slot.index >= 12 * 60) & (by_slot.index < 17 * 60)].mean()
    p(f"   shape control: median |sep| is {early:.3f} pip in the Asia block and "
      f"{late:.3f} pip in ny_pm ({late / early:.2f}x)")

    # ---------------------------------------------------------------- 3. correlation
    p("")
    p("-- 3. do the two deviations carry the same numbers? ----------------------")
    dd = panel.dropna(subset=["dev_vwap", "dev_twap"])
    r_p = float(np.corrcoef(dd["dev_vwap"], dd["dev_twap"])[0, 1])
    r_s = S.spearman(dd["dev_vwap"].to_numpy(), dd["dev_twap"].to_numpy())
    dz = panel.dropna(subset=["dev_vwap_z", "dev_twap_z"])
    r_z = float(np.corrcoef(dz["dev_vwap_z"], dz["dev_twap_z"])[0, 1])
    p(f"   corr(dev_vwap, dev_twap)      pearson {r_p:.5f}   spearman {r_s:.5f}")
    p(f"   corr(dev_vwap_z, dev_twap_z)  pearson {r_z:.5f}")
    for b in ("asia", "ldn_am", "overlap", "ny_pm"):
        g = dd[dd["block"] == b]
        p(f"     {b:<9} pearson {np.corrcoef(g['dev_vwap'], g['dev_twap'])[0, 1]:.5f}"
          f"   n {len(g):,}")
    # sign disagreement is the operationally relevant number: how often would a
    # "price above/below VWAP" gate answer differently?
    sgn = float((np.sign(dd["dev_vwap"]) != np.sign(dd["dev_twap"])).mean())
    p(f"   the two anchors put price on OPPOSITE sides {sgn:.2%} of the time "
      "(a VWAP gate and a TWAP gate would disagree this often)")

    # ---------------------------------------------------------------- 4. era
    p("")
    p("-- 4. era control ---------------------------------------------------------")
    p("   year      n     med |sep| pip   med R_sep   corr(dev,dev)   med vol/bar")
    for y, g in d.groupby("year"):
        gg = dd[dd["year"] == y]
        p(f"   {y}  {len(g):7,}   {g['sep_pip'].abs().median():12.3f}   "
          f"{g['rsep'].median():9.3f}   "
          f"{np.corrcoef(gg['dev_vwap'], gg['dev_twap'])[0, 1]:13.5f}   "
          f"{g['volume'].median():11.0f}")

    # ---------------------------------------------------------------- verdict
    killed_rsep = rsep_pooled < KILL_RSEP
    killed_corr = r_p > KILL_CORR
    p("")
    p("-- KILL TEST (declared in HYP-0001 before the run) ------------------------")
    p(f"   R_sep pooled median   {rsep_pooled:.4f}   "
      f"(kill if < {KILL_RSEP};  'materially different' if > {PASS_RSEP})")
    p(f"   corr(dev_vwap,dev_twap) {r_p:.5f}   (kill if > {KILL_CORR})")
    p(f"   -> R_sep kill triggered:  {killed_rsep}")
    p(f"   -> corr  kill triggered:  {killed_corr}")

    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / f"anatomy_{product}.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RUN / f'anatomy_{product}.txt'}")
    return {"product": product, "rsep": rsep_pooled, "rsep_last": rsep_last,
            "corr": r_p, "corr_z": r_z, "sign_disagree": sgn,
            "killed": killed_rsep or killed_corr}


def main(argv):
    prods = [argv[1]] if len(argv) > 1 else list(D.PRODUCTS)
    out = [run(p) for p in prods]
    if len(out) > 1:
        print("\n" + "=" * 78)
        print("SUMMARY")
        for r in out:
            print(f"  {r['product']}  R_sep {r['rsep']:.4f}  (16:29 {r['rsep_last']:.4f})"
                  f"  corr {r['corr']:.5f}  sign-disagree {r['sign_disagree']:.2%}"
                  f"  killed={r['killed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
