"""
HYP-0005 — Cross-asset conditioning: condition GC direction on the contemporaneous
ES noise-VWAP state, validated with a re-pairing null (Rule 18).

Thesis (EXP-0002): the GC noise-VWAP edge lives only in the equity cash session and
dies in gold's own pit hours => it is equity-session momentum bleeding into gold. If
so, the CONTEMPORANEOUS ES noise-VWAP state should condition the correct GC direction.

Design (single-variable overlay on the frozen EXP-0005 decision-clock baseline):
  * es_state at each GC decision (date, tod) in {+1,-1,0}, built from ES's OWN bars,
    ES's OWN cumulative RTH VWAP, and ES's OWN 90-session noise bands, through the
    SAME audited `core.data.load_rth` / `noise_bands` code (ES is just another inst).
  * cond_mode overlays (engine `want` modifier; entries/exits/flips/fills otherwise
    identical to baseline):
        agree  -> take GC signal only if ES agrees          (primary)
        gate   -> take GC signal only if ES in ANY breakout  (secondary)
        es_dir -> enter GC in ES's direction                 (secondary)
  * Both baseline and variants run on the COMMON GC∩ES date set (calendar held fixed).

Gate (memory gate-nullc-on-success-metric): the re-pairing null is spent ONLY if the
best real variant lifts net daily Sharpe by >= +0.05 over the common-set baseline.

Re-pairing null (Rule 18): pair each GC session with a RANDOM OTHER ES date's state
series (same tods), donors stratified by calendar YEAR. Destroys the contemporaneous
cross-information; preserves each leg's own dynamics. >=200 draws; real uplift vs the
null-uplift distribution.

Usage:
    python -m futures.gc.noise_vwap.scripts.hyp_0005_es_conditioning GC 90 0.50 [ndraw]
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, TICK, POINT_VALUE
from ..core.engine import run, DECISION_TODS
from ..core.metrics import summarize, fmt

DEC_SET = [int(t) for t in DECISION_TODS]


def es_state_map(lookback: int) -> dict:
    """{date -> {tod -> es_state in {+1,-1,0}}} at the GC decision tods, from ES's own
    bars/VWAP/noise-bands (built by the SAME audited code used for GC)."""
    esb = load_rth("ES")
    esbands = noise_bands(esb, lookback)

    bars = esb[esb["tod"].isin(DEC_SET)][["date", "tod", "close", "vwap"]]
    bands = esbands[esbands["tod"].isin(DEC_SET)][["date", "tod", "upper", "lower"]]
    m = bars.merge(bands, on=["date", "tod"], how="inner")
    long = ((m["close"] > m["upper"]) & (m["close"] > m["vwap"]))
    short = ((m["close"] < m["lower"]) & (m["close"] < m["vwap"]))
    m["state"] = np.where(long, 1, np.where(short, -1, 0)).astype(int)

    out: dict = {}
    for d, g in m.groupby("date", sort=False):
        out[d] = dict(zip(g["tod"].astype(int), g["state"].astype(int)))
    return out


def sharpe_net(trades: pd.DataFrame, inst: str, cost: float) -> float:
    s = summarize(trades, inst, cost)
    return float(s.get("sharpe_net_daily", 0.0)) if s.get("n_trades", 0) else 0.0


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "GC"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    ticks = float(sys.argv[3]) if len(sys.argv) > 3 else 0.50
    ndraw = int(sys.argv[4]) if len(sys.argv) > 4 else 200

    fees_pt = 2.25 / POINT_VALUE[inst]
    cost = fees_pt + ticks * TICK[inst]
    GATE = 0.05

    print(f"=== HYP-0005 ES-conditioning {inst} lookback={lookback} "
          f"cost={ticks}tick/side ({cost:.4f}pt) ===")

    # --- GC baseline machinery (frozen) ---
    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)

    # parity guard: unconditioned run must equal the frozen baseline (2692 / 974.60)
    base_full = run(bars, bands)
    g = base_full["points"].sum()
    print(f"parity check (full, unconditioned): trades={len(base_full)} gross={g:.2f}pt")
    assert len(base_full) == 2692 and abs(g - 974.60) < 0.05, \
        f"parity broken: {len(base_full)} trades / {g:.2f} pt (expected 2692 / 974.60)"

    # --- ES state + common date set ---
    esmap = es_state_map(lookback)
    gc_dates = set(bars["date"].unique())
    es_dates = set(esmap.keys())
    common = sorted(gc_dates & es_dates)
    print(f"GC dates={len(gc_dates)} ES-state dates={len(es_dates)} "
          f"common={len(common)}")

    cset = set(common)
    bars_c = bars[bars["date"].isin(cset)].reset_index(drop=True)
    bands_c = bands[bands["date"].isin(cset)].reset_index(drop=True)
    esmap_c = {d: esmap[d] for d in common}

    # es_state marginals over the traded decision grid
    allstates = [s for d in common for s in esmap_c[d].values()]
    arr = np.array(allstates)
    print(f"ES decision-bar state marginals over common set (n={len(arr)}): "
          f"long={np.mean(arr==1):.3f} short={np.mean(arr==-1):.3f} "
          f"flat={np.mean(arr==0):.3f}")

    # --- baseline on common set ---
    base = run(bars_c, bands_c)
    sb = summarize(base, inst, cost, "baseline(common)")
    base_sh = sharpe_net(base, inst, cost)
    print("\n--- BASELINE (common date set) ---")
    print(fmt(sb))

    # --- conditioning variants ---
    print("\n--- CONDITIONING VARIANTS ---")
    results = {}
    for mode in ("agree", "gate", "es_dir"):
        tr = run(bars_c, bands_c, ext_state_by_date=esmap_c, cond_mode=mode)
        s = summarize(tr, inst, cost, f"cond:{mode}")
        results[mode] = (tr, s, sharpe_net(tr, inst, cost))
        print(fmt(s))

    print("\n--- UPLIFT vs common-set baseline (net daily Sharpe) ---")
    uplift = {m: results[m][2] - base_sh for m in results}
    for m in results:
        print(f"  {m:<8s} Sharpe {results[m][2]:+.3f}  uplift {uplift[m]:+.3f}  "
              f"trades {results[m][1]['n_trades']} (base {sb['n_trades']})")

    best = max(uplift, key=uplift.get)
    print(f"\nbest variant = {best}  uplift = {uplift[best]:+.3f}  (gate = +{GATE})")

    if uplift[best] < GATE:
        print(f"\nVERDICT: REJECT — best net-Sharpe uplift {uplift[best]:+.3f} < "
              f"+{GATE} gate. Re-pairing null NOT spent (real pass fails primary "
              f"metric; gate-nullc-on-success-metric).")
        return

    # --- re-pairing null (Rule 18), only if the gate passed ---
    print(f"\n=== RE-PAIRING NULL on '{best}' (Rule 18), {ndraw} draws, "
          f"year-stratified donors ===")
    real_up = uplift[best]

    # donor pools by calendar year
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
            paired[d] = esmap_c[donor]
        tr = run(bars_c, bands_c, ext_state_by_date=paired, cond_mode=best)
        null_up[k] = sharpe_net(tr, inst, cost) - base_sh
        if (k + 1) % 50 == 0:
            print(f"  draw {k+1}/{ndraw}  null-uplift mean so far "
                  f"{null_up[:k+1].mean():+.3f}")

    mu, sd = null_up.mean(), null_up.std(ddof=1)
    z = (real_up - mu) / sd if sd > 0 else 0.0
    frac_beat = float(np.mean(null_up >= real_up))
    print(f"\nreal uplift        = {real_up:+.4f}")
    print(f"null uplift mean/sd = {mu:+.4f} / {sd:.4f}")
    print(f"z = {z:+.2f}   frac(null >= real) = {frac_beat:.3f}")
    verdict = ("ACCEPT (survives re-pairing null)" if (z > 2.0 and frac_beat < 0.05)
               else "REJECT (uplift reproduced by unrelated ES days = rarity filter, "
                    "not cross-asset info)")
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    main()
