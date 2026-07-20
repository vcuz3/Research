"""
HYP-0010 — Cross-market confirmation: gate NQ noise-VWAP entries on the
contemporaneous ES noise-VWAP state, validated with a re-pairing null (Rule 18).

Thesis (user): NQ and ES are tightly coupled, so the "noise area" carries shared
information. A real breakout should show up on BOTH indices at once; an NQ break
with no ES confirmation is just noise outside the noise area. So gating NQ entries
on ES confirmation should keep the informative breaks and drop the noise ones.

Design (single-variable overlay on the frozen faithful NQ baseline). At each NQ
decision (date, tod) we read TWO contemporaneous ES states, both from ES's OWN
bars / ES's OWN cumulative RTH VWAP / ES's OWN 90-session noise bands through the
SAME audited `core.data.load_rth` / `noise_bands` code (ES is just another inst):
    es_break in {+1,-1,0}: +1 if ES close>upper & >vwap, -1 if <lower & <vwap, else 0
    es_vwap  in {+1,-1}   : sign(ES close - ES vwap)   (the softer VWAP-side gate)

Conditioning modes (engine `want` modifier; entries/exits/flips/fills otherwise
identical to baseline). PRIMARY is the user's stated thesis; the rest are secondary
diagnostics that discriminate information from a rarity/turnover filter:
    agree   (PRIMARY) take NQ signal only if ES has broken out the SAME way (es_break==want)
    gate              take NQ signal only if ES is in ANY breakout (es_break!=0)
    vwap    ("don't go long if ES under its VWAP") take NQ signal only if es_vwap==want
    es_dir            enter NQ in ES's breakout direction   (does ES *lead* NQ?)
    es_opp            enter NQ OPPOSITE ES's breakout        (mirror-trap check, Rule 16)
    disagree          take NQ signal only if ES disagrees    (GC's weak-survivor control)

Both baseline and variants run on the COMMON NQ∩ES date set (calendar held fixed).

Gate (memory gate-nullc-on-success-metric): the expensive re-pairing null is spent
ONLY if the PRIMARY variant (agree) lifts net daily Sharpe by >= +0.05 over the
common-set baseline. If agree misses but another variant clears, we null THAT one
but label it post-hoc/secondary (family=6, consumed-history, holdout-pending).

Rarity-filter discriminator (GC EXP-0007 learning): a Sharpe that holds only because
the trade count collapsed while GROSS-per-trade on the kept trades FALLS is selecting
the WORSE trades = a rarity filter, not information. We print gross/kept alongside
Sharpe. The re-pairing null's CENTER is the decisive test: ~0 => real cross-info;
~=real uplift => rarity filter (unrelated ES days reproduce it).

Re-pairing null (Rule 18): pair each NQ session with a RANDOM OTHER ES date's state
series (same tods), donors stratified by calendar YEAR. Destroys the contemporaneous
cross-information; preserves each leg's own dynamics. >=200 draws; real uplift vs the
null-uplift distribution.

Usage:
    python -m futures.nq.noise_vwap.scripts.hyp_0010_es_confirm [NQ] [90] [0.50] [ndraw]
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, TICK, POINT_VALUE
from ..core.engine import run, DECISION_TODS
from ..core.metrics import summarize, fmt

DEC_SET = [int(t) for t in DECISION_TODS]

# Frozen full-sample NQ parity anchor (faithful baseline, unconditioned). Locked
# from the first run below; guards that the overlay is a true no-op (cond_mode=None).
PARITY_TRADES = 2923          # faithful core.engine baseline (next-open, :59/:29 clock)
PARITY_GROSS = 14454.25       # full-sample gross points, unconditioned


def es_states(lookback: int) -> tuple[dict, dict]:
    """Return (break_map, vwap_map): date -> {tod -> state}, at the NQ decision tods,
    from ES's own bars / VWAP / noise-bands (same audited code path used for NQ).
      break_map state in {+1,-1,0}: full noise-VWAP breakout state.
      vwap_map  state in {+1,-1}  : sign(close - vwap) (ES side of its own VWAP)."""
    esb = load_rth("ES")
    esbands = noise_bands(esb, lookback)

    bars = esb[esb["tod"].isin(DEC_SET)][["date", "tod", "close", "vwap"]]
    bands = esbands[esbands["tod"].isin(DEC_SET)][["date", "tod", "upper", "lower"]]
    m = bars.merge(bands, on=["date", "tod"], how="inner")
    long = ((m["close"] > m["upper"]) & (m["close"] > m["vwap"]))
    short = ((m["close"] < m["lower"]) & (m["close"] < m["vwap"]))
    m["brk"] = np.where(long, 1, np.where(short, -1, 0)).astype(int)
    m["vws"] = np.where(m["close"] >= m["vwap"], 1, -1).astype(int)

    bmap: dict = {}
    vmap: dict = {}
    for d, g in m.groupby("date", sort=False):
        tods = g["tod"].astype(int)
        bmap[d] = dict(zip(tods, g["brk"].astype(int)))
        vmap[d] = dict(zip(tods, g["vws"].astype(int)))
    return bmap, vmap


def sharpe_net(trades: pd.DataFrame, inst: str, cost: float) -> float:
    s = summarize(trades, inst, cost)
    return float(s.get("sharpe_net_daily", 0.0)) if s.get("n_trades", 0) else 0.0


# (state_map, cond_mode) for each variant. vwap uses the "agree" semantics on the
# VWAP-side channel (want kept only if ES is on the same side of its own VWAP).
def variant_specs(bmap_c, vmap_c):
    return {
        "agree":    (bmap_c, "agree"),
        "gate":     (bmap_c, "gate"),
        "vwap":     (vmap_c, "agree"),
        "es_dir":   (bmap_c, "es_dir"),
        "es_opp":   (bmap_c, "es_opp"),
        "disagree": (bmap_c, "disagree"),
    }


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    ticks = float(sys.argv[3]) if len(sys.argv) > 3 else 0.50
    ndraw = int(sys.argv[4]) if len(sys.argv) > 4 else 200

    fees_pt = 2.25 / POINT_VALUE[inst]
    cost = fees_pt + ticks * TICK[inst]
    GATE = 0.05
    PRIMARY = "agree"

    print(f"=== HYP-0010 ES-confirmation {inst} lookback={lookback} "
          f"cost={ticks}tick/side ({cost:.4f}pt) ===")

    # --- NQ baseline machinery (frozen) ---
    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)

    # parity guard: unconditioned run must equal the frozen faithful baseline.
    base_full = run(bars, bands)
    g_full = base_full["points"].sum()
    print(f"parity check (full, unconditioned): trades={len(base_full)} "
          f"gross={g_full:.2f}pt")
    assert len(base_full) == PARITY_TRADES, \
        f"parity broken: {len(base_full)} trades (expected {PARITY_TRADES})"
    if PARITY_GROSS is not None:
        assert abs(g_full - PARITY_GROSS) < 0.05, \
            f"parity broken: gross {g_full:.2f} (expected {PARITY_GROSS})"

    # --- ES states + common date set ---
    bmap, vmap = es_states(lookback)
    nq_dates = set(bars["date"].unique())
    es_dates = set(bmap.keys())
    common = sorted(nq_dates & es_dates)
    print(f"NQ dates={len(nq_dates)} ES-state dates={len(es_dates)} "
          f"common={len(common)}")

    cset = set(common)
    bars_c = bars[bars["date"].isin(cset)].reset_index(drop=True)
    bands_c = bands[bands["date"].isin(cset)].reset_index(drop=True)
    bmap_c = {d: bmap[d] for d in common}
    vmap_c = {d: vmap[d] for d in common}

    # ES state marginals over the traded decision grid
    barr = np.array([s for d in common for s in bmap_c[d].values()])
    varr = np.array([s for d in common for s in vmap_c[d].values()])
    print(f"ES breakout-state marginals (n={len(barr)}): "
          f"long={np.mean(barr==1):.3f} short={np.mean(barr==-1):.3f} "
          f"flat={np.mean(barr==0):.3f}")
    print(f"ES vwap-side marginals: above={np.mean(varr==1):.3f} "
          f"below={np.mean(varr==-1):.3f}")

    # --- baseline on common set ---
    base = run(bars_c, bands_c)
    sb = summarize(base, inst, cost, "baseline(common)")
    base_sh = sharpe_net(base, inst, cost)
    base_gross_kept = float(base["points"].mean())
    print("\n--- BASELINE (common date set) ---")
    print(fmt(sb))

    # --- conditioning variants ---
    print("\n--- CONDITIONING VARIANTS ---")
    specs = variant_specs(bmap_c, vmap_c)
    results = {}
    for mode, (smap, cmode) in specs.items():
        tr = run(bars_c, bands_c, ext_state_by_date=smap, cond_mode=cmode)
        s = summarize(tr, inst, cost, f"cond:{mode}")
        results[mode] = (tr, s, sharpe_net(tr, inst, cost))
        print(fmt(s))

    # --- uplift + rarity-filter diagnostic (gross on KEPT trades) ---
    print("\n--- UPLIFT vs common-set baseline (net daily Sharpe) + kept-trade gross ---")
    print(f"  {'variant':<9s} {'Sharpe':>7s} {'uplift':>7s} {'trades':>7s} "
          f"{'kept%':>6s} {'gross/kept':>10s} (base gross/kept {base_gross_kept:+.3f})")
    uplift = {}
    for m in results:
        tr, s, sh = results[m]
        uplift[m] = sh - base_sh
        kept = s["n_trades"] / sb["n_trades"]
        gk = float(tr["points"].mean()) if len(tr) else float("nan")
        flag = ""
        # rarity-filter tell: fewer trades AND gross/kept fell below baseline
        if kept < 0.98 and gk < base_gross_kept:
            flag = "  <- gross/kept FELL (selecting worse trades = rarity tell)"
        print(f"  {m:<9s} {sh:>+7.3f} {uplift[m]:>+7.3f} {s['n_trades']:>7d} "
              f"{kept:>6.2f} {gk:>+10.3f}{flag}")

    print(f"\nPRIMARY variant = {PRIMARY}  uplift = {uplift[PRIMARY]:+.3f}  "
          f"(gate = +{GATE})")
    best = max(uplift, key=uplift.get)
    print(f"best variant    = {best}  uplift = {uplift[best]:+.3f}")

    # Gate: prefer the PRIMARY thesis; fall back to best only as a labelled post-hoc.
    if uplift[PRIMARY] >= GATE:
        null_target, label = PRIMARY, "PRIMARY thesis"
    elif uplift[best] >= GATE:
        null_target, label = best, ("SECONDARY/post-hoc (family=6, consumed history, "
                                    "holdout-pending)")
    else:
        print(f"\nVERDICT: REJECT — no variant lifts net Sharpe by +{GATE}. "
              f"PRIMARY(agree)={uplift[PRIMARY]:+.3f}, best({best})={uplift[best]:+.3f}. "
              f"Re-pairing null NOT spent (real pass fails primary metric; "
              f"gate-nullc-on-success-metric).")
        return

    # --- re-pairing null (Rule 18), only if the gate passed ---
    smap_t, cmode_t = specs[null_target]
    print(f"\n=== RE-PAIRING NULL on '{null_target}' [{label}] (Rule 18), "
          f"{ndraw} draws, year-stratified donors ===")
    real_up = uplift[null_target]

    by_year: dict[int, list] = {}
    for d in common:
        by_year.setdefault(pd.Timestamp(d).year, []).append(d)

    null_up = np.empty(ndraw)
    for k in range(ndraw):
        rng = np.random.default_rng(10_000 + k)
        paired = {}
        for d in common:
            pool = by_year[pd.Timestamp(d).year]
            if len(pool) > 1:
                donor = d
                while donor == d:
                    donor = pool[rng.integers(len(pool))]
            else:
                donor = pool[0]
            paired[d] = smap_t[donor]
        tr = run(bars_c, bands_c, ext_state_by_date=paired, cond_mode=cmode_t)
        null_up[k] = sharpe_net(tr, inst, cost) - base_sh
        if (k + 1) % 50 == 0:
            print(f"  draw {k+1}/{ndraw}  null-uplift mean so far "
                  f"{null_up[:k+1].mean():+.3f}")

    mu, sd = null_up.mean(), null_up.std(ddof=1)
    z = (real_up - mu) / sd if sd > 0 else 0.0
    frac_beat = float(np.mean(null_up >= real_up))
    print(f"\nreal uplift        = {real_up:+.4f}")
    print(f"null uplift mean/sd = {mu:+.4f} / {sd:.4f}   (CENTER is the discriminator)")
    print(f"z = {z:+.2f}   frac(null >= real) = {frac_beat:.3f}")
    if mu > 0.5 * real_up:
        print("  null CENTER ~ real uplift => unrelated ES days reproduce it "
              "= RARITY/turnover filter, not cross-market information.")
    elif abs(mu) < 0.02:
        print("  null CENTER ~ 0 => contemporaneous ES pairing carries the uplift "
              "= genuine cross-market information.")
    verdict = ("ACCEPT (survives re-pairing null; real cross-market info)"
               if (z > 2.0 and frac_beat < 0.05)
               else "REJECT (uplift reproduced by unrelated ES days = rarity filter, "
                    "not cross-market confirmation)")
    print(f"\nVERDICT: {verdict}")
    if null_target != PRIMARY:
        print("NOTE: this is a SECONDARY/post-hoc survivor (family of 6, consumed "
              "history) — at most a forward-shadow candidate, not the stated thesis.")


if __name__ == "__main__":
    main()
