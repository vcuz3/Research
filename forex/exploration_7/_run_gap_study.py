"""EXP-0001 - weekend gap mean reversion, 9 FX pairs.

Executes HYP-0001 exactly as frozen: validity gate first, then the primary
specification and its five kill-test conditions, then controls.

Run:  python _run_gap_study.py
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

HORIZONS = [15, 60, 240, 1440, 2880, 7200]
DELAYS = [1, 5, 15, 60]
KS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
PRIMARY = dict(k=1.5, d=5, h=1440)

OUT = Path(__file__).resolve().parent / "artifacts" / "runs" / "EXP-0001"
pd.set_option("display.width", 250, "display.max_columns", 60)


# ---------------------------------------------------------------- inference
def cluster_stats(x: pd.Series, cluster: pd.Series) -> dict:
    """Mean with SE clustered on `cluster` (weekend date).

    All nine pairs share each weekend, so events are not independent; a plain
    SE would overstate precision by roughly the square root of the bloc size.
    """
    x = pd.Series(x).astype(float)
    m = x.notna()
    x, g = x[m], pd.Series(cluster)[m]
    n = len(x)
    if n < 10 or g.nunique() < 5:
        return dict(n=n, n_clusters=int(g.nunique()), mean=np.nan, se=np.nan, t=np.nan)
    xbar = x.mean()
    dev = x - xbar
    gsum = dev.groupby(g.values).sum()
    var = (gsum ** 2).sum() / (n ** 2)
    # small-cluster correction
    G = g.nunique()
    var *= G / max(G - 1, 1)
    se = float(np.sqrt(var))
    return dict(n=n, n_clusters=int(G), mean=float(xbar), se=se,
                t=float(xbar / se) if se > 0 else np.nan)


def fade_R(ev: pd.DataFrame, d: int, h: int, exit_override=None) -> pd.Series:
    entry = ev[f"entry_{d}"]
    exit_ = ev[f"exit_{h}"] if exit_override is None else exit_override
    side = -np.sign(ev["gap_ret"])
    return side * np.log(exit_ / entry) / ev["sigma_ret"]


def fade_pips(ev: pd.DataFrame, d: int, h: int) -> pd.Series:
    side = -np.sign(ev["gap_ret"])
    px = ev["pair"].map(PIP)
    return side * (ev[f"exit_{h}"] - ev[f"entry_{d}"]) / px


def sel(ev: pd.DataFrame, k: float) -> pd.DataFrame:
    return ev[ev["z"].abs() >= k]


# ---------------------------------------------------------------- build
def build_all(calendar: pd.DataFrame, tag: str) -> pd.DataFrame:
    frames = []
    for pair in PAIRS:
        df = load_pair(pair)
        frames.append(build_events(pair, df, HORIZONS, DELAYS, calendar))
        print(f"    {pair} done", flush=True)
    ev = pd.concat(frames, ignore_index=True)
    ev["year"] = ev["t_open"].dt.year
    ev["arm"] = tag
    return ev


def weekday_calendar(ref_idx: pd.DatetimeIndex, wk: pd.DataFrame) -> pd.DataFrame:
    """Placebo: ordinary weeknight breaks at the same time-of-day.

    For each Mon-Thu, use the same UTC time-of-day as that week's real weekend
    close, so the placebo is matched on clock and on session phase and differs
    only in that no weekend intervenes.
    """
    rows = []
    for _, r in wk.iterrows():
        close_t = pd.Timestamp(r["week_close"])
        # the four weeknights preceding this Friday close
        for back in (1, 2, 3, 4):
            t = close_t - pd.Timedelta(days=back)
            if t.dayofweek > 4:
                continue
            p_prev = ref_idx.searchsorted(t, side="right") - 1
            p_next = ref_idx.searchsorted(t, side="right")
            if p_prev < 0 or p_next >= len(ref_idx):
                continue
            rows.append({"week_close": ref_idx[p_prev], "week_open": ref_idx[p_next],
                         "break_hours": (ref_idx[p_next] - ref_idx[p_prev]).total_seconds() / 3600})
    cal = pd.DataFrame(rows).drop_duplicates("week_close").reset_index(drop=True)
    return cal.sort_values("week_close").reset_index(drop=True)


# ---------------------------------------------------------------- report
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log = []

    def say(*a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        log.append(s)

    ref_idx = load_pair(CALENDAR_REF).index
    cal = session_calendar(ref_idx)

    say("Building weekend events ...")
    ev = build_all(cal, "weekend")
    ev.to_parquet(OUT / "events.parquet", index=False)
    say(f"weekend events: {len(ev):,} pair-weekends, "
        f"{ev['weekend'].nunique()} weekends, {ev['sigma_ret'].notna().sum():,} with sigma")

    ev = ev[ev["sigma_ret"].notna() & (ev["sigma_ret"] > 0)].copy()

    # ============================================================ VALIDITY GATE
    say("\n" + "=" * 78)
    say("VALIDITY GATE (runs before the verdict)")
    say("=" * 78)

    # G1a plumbing: force the exit to be exactly the Friday close. The fade
    # return must then equal the full gap size in sigma units, i.e. mean |z|.
    s = sel(ev, PRIMARY["k"])
    r_closed = fade_R(s, PRIMARY["d"], PRIMARY["h"], exit_override=s["fri_close"])
    say(f"G1a plumbing  : exit forced to Friday close -> mean fade R = {r_closed.mean():.4f}")
    say(f"                mean |z| over the same events = {s['z'].abs().mean():.4f}")
    ok_plumb = abs(r_closed.mean() - s["z"].abs().mean()) < 0.05 * s["z"].abs().mean()
    say(f"                agreement within 5%: {ok_plumb}  "
        f"(validates sign convention, sigma scaling and units end to end)")

    # G1b power: inject a known reversion of m sigma into the exit price.
    say("\nG1b power     : inject a known reversion of m sigma, recover it")
    say(f"{'m_injected':>11} {'m_recovered':>12} {'t':>8} {'detected(t>=2)':>15}")
    mde = None
    for m in [0.0, 0.02, 0.05, 0.10, 0.20]:
        side = -np.sign(s["gap_ret"])
        bump = np.exp(side * m * s["sigma_ret"])
        r = fade_R(s, PRIMARY["d"], PRIMARY["h"], exit_override=s[f"exit_{PRIMARY['h']}"] * bump)
        st = cluster_stats(r, s["weekend"])
        det = st["t"] >= 2.0
        say(f"{m:>11.2f} {st['mean']:>12.4f} {st['t']:>8.2f} {str(det):>15}")
        if det and mde is None and m > 0:
            mde = m
    say(f"                minimum detectable effect at this n: ~{mde} sigma "
        f"(any true effect smaller than this is invisible here)")

    # G2 non-degeneracy: counts per arm
    say("\nG2 counts     : selected events by pair at k=%.1f" % PRIMARY["k"])
    cnt = s.groupby("pair").size().reindex(PAIRS)
    say("                " + ", ".join(f"{p}={int(c)}" for p, c in cnt.items()))
    say(f"                pooled n={len(s):,}, weekend clusters={s['weekend'].nunique()}")

    gate_pass = bool(ok_plumb) and mde is not None
    say(f"\nVALIDITY GATE: {'PASS' if gate_pass else 'FAIL -> result would be INCONCLUSIVE'}")

    # ============================================================ PRIMARY
    say("\n" + "=" * 78)
    say(f"PRIMARY SPECIFICATION  k={PRIMARY['k']} d={PRIMARY['d']}min h={PRIMARY['h']}min (gross)")
    say("=" * 78)
    r = fade_R(s, PRIMARY["d"], PRIMARY["h"])
    st = cluster_stats(r, s["weekend"])
    pips = fade_pips(s, PRIMARY["d"], PRIMARY["h"])
    say(f"pooled mean R = {st['mean']:+.4f}  se {st['se']:.4f}  clustered t = {st['t']:+.2f}"
        f"   n={st['n']:,} over {st['n_clusters']} weekends")
    say(f"pooled mean   = {pips.mean():+.3f} pips (median {pips.median():+.3f})")
    p1 = (st["mean"] > 0) and (abs(st["t"]) >= 2.0)
    say(f"P1 sign+significance: {'PASS' if p1 else 'FAIL'}")

    # per pair
    say("\nPer pair (primary spec):")
    rows = []
    for p in PAIRS:
        sp = s[s["pair"] == p]
        stp = cluster_stats(fade_R(sp, PRIMARY["d"], PRIMARY["h"]), sp["weekend"])
        rows.append({"pair": p, "n": stp["n"], "mean_R": stp["mean"], "t": stp["t"],
                     "mean_pips": fade_pips(sp, PRIMARY["d"], PRIMARY["h"]).mean(),
                     "hit_rate": float((fade_R(sp, PRIMARY["d"], PRIMARY["h"]) > 0).mean())})
    per_pair = pd.DataFrame(rows)
    say(per_pair.round(4).to_string(index=False))
    n_pos = int((per_pair["mean_R"] > 0).sum())
    p2 = n_pos >= 6
    say(f"P2 breadth: {n_pos}/9 pairs positive -> {'PASS' if p2 else 'FAIL'}")
    audjpy = float(per_pair.loc[per_pair["pair"] == "AUDJPY", "mean_R"].iloc[0])
    p3 = audjpy > 0
    say(f"P3 origin pair AUDJPY mean_R = {audjpy:+.4f} -> {'PASS' if p3 else 'FAIL'}")

    # P4 paired embargo
    say("\nP4 boundary-artifact control (paired, identical weekends):")
    both = s[s["entry_1"].notna() & s["entry_60"].notna() & s[f"exit_{PRIMARY['h']}"].notna()]
    say(f"{'entry delay':>12} {'mean R':>9} {'t':>7} {'n':>7}")
    d_vals = {}
    for d in DELAYS:
        stt = cluster_stats(fade_R(both, d, PRIMARY["h"]), both["weekend"])
        d_vals[d] = stt["mean"]
        say(f"{d:>10}min {stt['mean']:>+9.4f} {stt['t']:>+7.2f} {stt['n']:>7,}")
    retain = d_vals[60] / d_vals[1] if d_vals[1] not in (0, np.nan) else np.nan
    p4 = (d_vals[1] > 0) and (retain >= 0.5)
    say(f"retention d60/d1 = {retain:.2f} -> P4 {'PASS' if p4 else 'FAIL'}")

    # P5 cost
    say("\nP5 cost: reopen-minute range as a spread proxy (mid-only data)")
    say(f"{'pair':>8} {'reopen rng':>11} {'midsess rng':>12} {'ratio':>7} {'gross pips':>11} {'breakeven':>10}")
    cost_rows = []
    for p in PAIRS:
        df = load_pair(p)
        sp = s[s["pair"] == p]
        ropen = df.loc[df.index.isin(sp["t_open"])]
        rng_open = float(((ropen["high"] - ropen["low"]) / PIP[p]).median())
        mid = df[(df.index.dayofweek < 5) & (df.index.hour.isin([13, 14, 15]))]
        rng_mid = float(((mid["high"] - mid["low"]) / PIP[p]).median())
        gp = fade_pips(sp, PRIMARY["d"], PRIMARY["h"]).mean()
        cost_rows.append({"pair": p, "reopen_range_pips": rng_open,
                          "midsession_range_pips": rng_mid,
                          "ratio": rng_open / rng_mid if rng_mid else np.nan,
                          "gross_pips": gp})
        say(f"{p:>8} {rng_open:>11.2f} {rng_mid:>12.2f} {rng_open/rng_mid:>7.2f} {gp:>+11.3f} "
            f"{'n/a (gross<=0)' if gp <= 0 else f'{gp:>10.2f}'}")
    cost = pd.DataFrame(cost_rows)
    pooled_gross_pips = pips.mean()
    p5 = pooled_gross_pips > 0
    say(f"pooled gross = {pooled_gross_pips:+.3f} pips; a round-trip reopen spread is "
        f"typically 2-10x the mid-session spread")
    say(f"P5 net positive before any spread charge: {'PASS' if p5 else 'FAIL'}")

    verdict = dict(P1=p1, P2=p2, P3=p3, P4=bool(p4), P5=bool(p5))
    overall = "GO" if all(verdict.values()) else ("INCONCLUSIVE" if not gate_pass else "NO-GO")
    say(f"\nKILL TEST: {verdict}")
    say(f"VERDICT: {overall}")

    # ============================================================ CONTROLS
    say("\n" + "=" * 78)
    say("CONTROLS")
    say("=" * 78)

    say("\nC3 threshold x horizon surface, pooled mean R (d=5). n in brackets.")
    grid = []
    hdr = f"{'k':>5} " + " ".join(f"{('h'+str(h)):>16}" for h in HORIZONS)
    say(hdr)
    for k in KS:
        sk = sel(ev, k)
        cells = []
        for h in HORIZONS:
            stt = cluster_stats(fade_R(sk, 5, h), sk["weekend"])
            cells.append(f"{stt['mean']:+.3f}/t{stt['t']:+.1f}")
            grid.append({"k": k, "h": h, **stt})
        say(f"{k:>5.1f} " + " ".join(f"{c:>16}" for c in cells) + f"   [n={len(sk):,}]")
    pd.DataFrame(grid).to_csv(OUT / "grid.csv", index=False)

    say("\nC2 continuation view: mean SIGNED return in gap direction "
        "(positive = gap continues, negative = reverts)")
    for h in HORIZONS:
        cont = -fade_R(s, PRIMARY["d"], h)
        stt = cluster_stats(cont, s["weekend"])
        say(f"   h={h:>5}min  mean {stt['mean']:+.4f}  t {stt['t']:+.2f}")

    say("\nC4 era split (primary spec):")
    ev_y = s.copy()
    ev_y["block"] = pd.cut(ev_y["year"], [2010, 2014, 2018, 2022, 2027],
                           labels=["2011-14", "2015-18", "2019-22", "2023-26"])
    for b, g in ev_y.groupby("block", observed=True):
        stt = cluster_stats(fade_R(g, PRIMARY["d"], PRIMARY["h"]), g["weekend"])
        say(f"   {b}: mean {stt['mean']:+.4f}  t {stt['t']:+.2f}  n={stt['n']:,}")
    padded = ev_y[(ev_y["pair"].isin(["USDJPY", "NZDJPY", "EURJPY"]))
                  & ev_y["year"].between(2021, 2023)]
    stt = cluster_stats(fade_R(padded, PRIMARY["d"], PRIMARY["h"]), padded["weekend"])
    say(f"   padded JPY vintage 2021-23: mean {stt['mean']:+.4f} t {stt['t']:+.2f} n={stt['n']:,}")

    # C1 weekday placebo
    say("\nC1 weeknight-break placebo (same clock, no weekend):")
    wcal = weekday_calendar(ref_idx, cal)
    say(f"   placebo calendar: {len(wcal)} weeknight breaks, "
        f"median break {wcal['break_hours'].median()*60:.0f} min")
    pl = build_all(wcal, "weeknight")
    pl = pl[pl["sigma_ret"].notna() & (pl["sigma_ret"] > 0)]
    ps = sel(pl, PRIMARY["k"])
    stt = cluster_stats(fade_R(ps, PRIMARY["d"], PRIMARY["h"]), ps["weekend"])
    say(f"   placebo mean R = {stt['mean']:+.4f}  t {stt['t']:+.2f}  n={stt['n']:,}")
    say(f"   weekend  mean R = {st['mean']:+.4f}  t {st['t']:+.2f}  n={st['n']:,}")
    say("   (counts differ by design - weeknights are ~4x more numerous; compare "
        "means and signs, not significance)")
    pl.to_parquet(OUT / "events_weeknight.parquet", index=False)

    per_pair.to_csv(OUT / "per_pair.csv", index=False)
    cost.to_csv(OUT / "cost_proxy.csv", index=False)
    (OUT / "verdict.json").write_text(json.dumps(
        dict(hypothesis="HYP-0001", primary=PRIMARY, gate_pass=gate_pass,
             mde_sigma=mde, kill_test=verdict, verdict=overall,
             pooled=st, pooled_gross_pips=float(pooled_gross_pips),
             pairs_positive=n_pos), indent=2, default=str))
    (OUT / "run_log.txt").write_text("\n".join(log), encoding="utf-8")
    say(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
