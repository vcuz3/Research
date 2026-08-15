"""EXP-0002 - follow-up to HYP-0001.

DISCOVERY, NOT CONFIRMATORY. The 1-hour horizon was chosen after seeing the
EXP-0001 surface. Everything here is labelled accordingly and carries a
selection-aware null.

Fixes two defects in EXP-0001:

1. The minimum-detectable-effect estimate injected an effect on top of the
   effect already present, so it reported "detected" when real+injected
   cleared t=2. MDE is now computed on de-meaned returns.
2. The entry-delay (boundary-artifact) control anchored the exit at
   reopen+h, so delaying entry shortened the hold. At h=60 with d=60 the
   trade had zero duration. Exits are now anchored at entry+H, holding
   duration constant across delays.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gap_lib import (CALENDAR_REF, PAIRS, PIP, build_events,  # noqa: E402
                      load_pair, session_calendar)
from _run_gap_study import (cluster_stats, fade_R, sel,  # noqa: E402
                            weekday_calendar)

DELAYS = [1, 5, 15, 60]
HOLDS = [60, 240, 1440]
# exits anchored at entry+H  =>  reopen + d + H
HORIZONS = sorted({d + H for d in DELAYS for H in HOLDS} | {60, 240, 1440})
KS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
OUT = Path(__file__).resolve().parent / "artifacts" / "runs" / "EXP-0002"
pd.set_option("display.width", 250, "display.max_columns", 60)
RNG = np.random.default_rng(20260812)


def hold_R(ev, d, H):
    return fade_R(ev, d, d + H)


def hold_pips(ev, d, H):
    side = -np.sign(ev["gap_ret"])
    return side * (ev[f"exit_{d+H}"] - ev[f"entry_{d}"]) / ev["pair"].map(PIP)


def build_all(cal, tag):
    frames = []
    for p in PAIRS:
        frames.append(build_events(p, load_pair(p), HORIZONS, DELAYS, cal))
        print(f"    {p} done", flush=True)
    ev = pd.concat(frames, ignore_index=True)
    ev["year"] = ev["t_open"].dt.year
    ev["arm"] = tag
    return ev[ev["sigma_ret"].notna() & (ev["sigma_ret"] > 0)].copy()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = []

    def say(*a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        log.append(s)

    ref_idx = load_pair(CALENDAR_REF).index
    cal = session_calendar(ref_idx)
    say("Building weekend events (exits anchored at entry+H) ...")
    ev = build_all(cal, "weekend")
    ev.to_parquet(OUT / "events.parquet", index=False)

    say("\n" + "=" * 78)
    say("A. HONEST POWER: minimum detectable effect, de-meaned")
    say("=" * 78)
    say("   MDE = 2 x clustered SE. The observed effect is detectable only if")
    say("   it exceeds this. (EXP-0001 reported 0.05 sigma; that was wrong -")
    say("   it injected on top of the existing effect.)")
    say(f"{'k':>5} {'H(min)':>7} {'n':>6} {'mean R':>9} {'se':>7} {'MDE':>7} {'t':>7} {'detected':>9}")
    pw = []
    for k in [1.5, 2.0]:
        s = sel(ev, k)
        for H in HOLDS:
            st = cluster_stats(hold_R(s, 5, H), s["weekend"])
            mde = 2 * st["se"]
            pw.append({"k": k, "H": H, **st, "mde": mde})
            say(f"{k:>5.1f} {H:>7} {st['n']:>6,} {st['mean']:>+9.4f} {st['se']:>7.4f} "
                f"{mde:>7.4f} {st['t']:>+7.2f} {str(abs(st['t'])>=2):>9}")
    pd.DataFrame(pw).to_csv(OUT / "power.csv", index=False)

    say("\n" + "=" * 78)
    say("B. FULL SURFACE with hold anchored at entry (d=5), pooled mean R")
    say("=" * 78)
    say(f"{'k':>5} " + " ".join(f"{('H='+str(H)):>18}" for H in HOLDS) + f"{'n':>8}")
    surf = []
    for k in KS:
        s = sel(ev, k)
        cells = []
        for H in HOLDS:
            st = cluster_stats(hold_R(s, 5, H), s["weekend"])
            surf.append({"k": k, "H": H, **st})
            cells.append(f"{st['mean']:+.3f}/t{st['t']:+.2f}")
        say(f"{k:>5.1f} " + " ".join(f"{c:>18}" for c in cells) + f"{len(s):>8,}")
    pd.DataFrame(surf).to_csv(OUT / "surface.csv", index=False)

    say("\n" + "=" * 78)
    say("C. BOUNDARY-ARTIFACT CONTROL, corrected (hold duration held constant)")
    say("=" * 78)
    say("   Paired: identical weekends across all delays. On this archive")
    say("   open[t]==close[t-1] ~always, so a noisy reopen print inflates the")
    say("   measured gap AND flatters the fade from the next bar.")
    for k in [1.5, 2.0]:
        s = sel(ev, k)
        need = [f"entry_{d}" for d in DELAYS] + [f"exit_{d+H}" for d in DELAYS for H in HOLDS]
        s = s.dropna(subset=need)
        say(f"\n   k={k}  (paired n={len(s):,})")
        say(f"{'delay':>8} " + " ".join(f"{('H='+str(H)):>18}" for H in HOLDS))
        rows = {}
        for d in DELAYS:
            cells = []
            for H in HOLDS:
                st = cluster_stats(hold_R(s, d, H), s["weekend"])
                rows[(d, H)] = st["mean"]
                cells.append(f"{st['mean']:+.3f}/t{st['t']:+.2f}")
            say(f"{d:>6}min " + " ".join(f"{c:>18}" for c in cells))
        say("   retention (d=60 / d=1): " + ", ".join(
            f"H={H}: {rows[(60,H)]/rows[(1,H)]:.2f}" if rows[(1, H)] else f"H={H}: n/a"
            for H in HOLDS))

    say("\n" + "=" * 78)
    say("D. WEEKNIGHT PLACEBO at every hold (same clock, no weekend)")
    say("=" * 78)
    wcal = weekday_calendar(ref_idx, cal)
    pl = build_all(wcal, "weeknight")
    pl.to_parquet(OUT / "events_weeknight.parquet", index=False)
    say(f"{'k':>5} {'arm':>10} {'n':>7} " + " ".join(f"{('H='+str(H)):>18}" for H in HOLDS))
    for k in [1.5, 2.0]:
        for name, dat in (("weekend", ev), ("weeknight", pl)):
            s = sel(dat, k)
            cells = []
            for H in HOLDS:
                st = cluster_stats(hold_R(s, 5, H), s["weekend"])
                cells.append(f"{st['mean']:+.3f}/t{st['t']:+.2f}")
            say(f"{k:>5.1f} {name:>10} {len(s):>7,} " + " ".join(f"{c:>18}" for c in cells))

    say("\n" + "=" * 78)
    say("E. SELECTION-AWARE NULL: randomise the gap SIGN")
    say("=" * 78)
    say("   Preserves selection, paths, volatility and counts; destroys only the")
    say("   link between gap DIRECTION and subsequent direction - which is the")
    say("   whole claim. Compares the real MAX |t| over the 6x3 surface against")
    say("   the null distribution of that same maximum (selection reproduced).")
    real_max = max(abs(r["t"]) for r in surf if not np.isnan(r["t"]))
    null_max = []
    for i in range(400):
        e = ev.copy()
        flip = RNG.choice([-1.0, 1.0], size=len(e))
        e["gap_ret"] = e["gap_ret"] * flip
        e["z"] = e["gap_ret"] / e["sigma_ret"]
        mx = 0.0
        for k in KS:
            s = sel(e, k)
            if len(s) < 50:
                continue
            for H in HOLDS:
                st = cluster_stats(hold_R(s, 5, H), s["weekend"])
                if not np.isnan(st["t"]):
                    mx = max(mx, abs(st["t"]))
        null_max.append(mx)
        if (i + 1) % 100 == 0:
            say(f"   ... {i+1}/400 draws")
    null_max = np.array(null_max)
    frac = float((null_max >= real_max).mean())
    say(f"   real max |t| over the surface = {real_max:.2f}")
    say(f"   null max |t|: mean {null_max.mean():.2f}  p50 {np.percentile(null_max,50):.2f}  "
        f"p95 {np.percentile(null_max,95):.2f}  max {null_max.max():.2f}  sd {null_max.std():.3f}")
    say(f"   frac(null >= real) = {frac:.4f}   (non-degenerate: sd>0 = {null_max.std()>0})")
    np.save(OUT / "null_max_t.npy", null_max)

    say("\n" + "=" * 78)
    say("F. THE 1-HOUR CELL IN TRADABLE UNITS (discovery cell - not preregistered)")
    say("=" * 78)
    for k in [1.5, 2.0]:
        s = sel(ev, k)
        say(f"\n   k={k}")
        say(f"{'pair':>8} {'n':>5} {'mean R':>9} {'t':>7} {'gross pips':>11} "
            f"{'reopen rng':>11} {'net@1x':>8} {'net@2x':>8}")
        rows = []
        for p in PAIRS:
            sp = s[s["pair"] == p]
            st = cluster_stats(hold_R(sp, 5, 60), sp["weekend"])
            gp = hold_pips(sp, 5, 60).mean()
            df = load_pair(p)
            ro = df.loc[df.index.isin(sp["t_open"])]
            rng = float(((ro["high"] - ro["low"]) / PIP[p]).median())
            rows.append({"pair": p, "k": k, "n": st["n"], "mean_R": st["mean"],
                         "t": st["t"], "gross_pips": gp, "reopen_range_pips": rng,
                         "net_1x": gp - rng, "net_2x": gp - 2 * rng})
            say(f"{p:>8} {st['n']:>5} {st['mean']:>+9.4f} {st['t']:>+7.2f} {gp:>+11.3f} "
                f"{rng:>11.2f} {gp-rng:>+8.2f} {gp-2*rng:>+8.2f}")
        r = pd.DataFrame(rows)
        pooled_gp = hold_pips(s, 5, 60).mean()
        say(f"   POOLED gross {pooled_gp:+.3f} pips | pairs positive "
            f"{int((r['mean_R']>0).sum())}/9 | net@1x reopen-range "
            f"{int((r['net_1x']>0).sum())}/9 positive")
        r.to_csv(OUT / f"tradable_k{k}.csv", index=False)

    say("\n" + "=" * 78)
    say("G. ERA STABILITY of the 1-hour cell (k=1.5, H=60)")
    say("=" * 78)
    s = sel(ev, 1.5)
    s = s.assign(block=pd.cut(s["year"], [2010, 2014, 2018, 2022, 2027],
                              labels=["2011-14", "2015-18", "2019-22", "2023-26"]))
    for b, g in s.groupby("block", observed=True):
        st = cluster_stats(hold_R(g, 5, 60), g["weekend"])
        say(f"   {b}: mean {st['mean']:+.4f}  t {st['t']:+.2f}  n={st['n']:,}  "
            f"gross {hold_pips(g,5,60).mean():+.2f} pips")

    (OUT / "run_log.txt").write_text("\n".join(log), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(
        dict(real_max_t=real_max, null_frac=frac,
             null_p95=float(np.percentile(null_max, 95))), indent=2))
    say(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
