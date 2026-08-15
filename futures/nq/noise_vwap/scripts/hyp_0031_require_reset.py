"""Test HYP-0031: the `require_reset` same-side re-entry lock.

Rule (user-supplied external spec, `Require reset rule.md`): after a STOP exit on
one side, do not allow another entry on that same side until price has first been
observed back INSIDE the Noise Area. Opposite-side entries are never blocked.

Single-variable change on the frozen baseline via the default-off `reentry`
argument on `core.engine2` (bands lb90, RTH, 30-min Concretum clock, VWAP entry
gate, band/VWAP stop, next-open fills, explicit costs). Nothing else moves.

Cells reported (all 8; the PRIMARY is declared in HYP-0031 as NQ x continuous
stop x every-bar reset):
  * stop book:     every_bar (this project's deployed continuous stop)
                   decision  (the source spec's run-18 cadence)
  * reset cadence: decision  (the source spec: resets seen only at checkpoints)
                   every_bar (matched to the continuous stop)
  * instruments:   NQ (primary), ES (transfer / sibling-market mechanism test)

Because the rule can only ever REMOVE trades, and this project has five times
found "fewer trades -> higher Sharpe" to be machinery, the decisive control is a
MATCHED-COUNT RANDOM DROP FROM THE SAME POOL: block an equal number of post-stop
same-side re-entry candidates chosen at random, re-run statefully through the
engine, and ask whether the real lock beats that. Also reported: the expectancy
of the removed trades (EXP-0024 diagnostic) and gross-per-trade on the kept ones.

Per the standing rule the drift-preserving Null C is spent only if the real
primary cell clears dSharpe >= +0.10 AND net R >= baseline.

Examples:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0031_require_reset real NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0031_require_reset real ES
  python -u -m futures.nq.noise_vwap.scripts.hyp_0031_require_reset null NQ 40
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .studies import _null_c_frame, diffusivity
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, common_dates, round_trip_cost_points,
    LOOKBACK, PERIOD, UPLIFT_GATE,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0043"

STOP_BOOKS = ("every_bar", "decision")
RESET_CADENCES = ("every_bar", "decision")
PRIMARY = ("every_bar", "every_bar")       # (stop book, reset cadence)
RAND_DRAWS = 200
RAND_SEED0 = 43000
NULLC_SEED0 = 43500


# --------------------------------------------------------------------------- #
# engine helpers
# --------------------------------------------------------------------------- #
def run_book(bars, bands, dm, stop_book, reentry="later_decision",
             reset_check="decision", entry_gate=None, audit_out=None,
             reset_hazard=None, reset_seed=0):
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                 exit_check=stop_book, reentry=reentry, reset_check=reset_check,
                 entry_gate=entry_gate, audit_out=audit_out,
                 reset_hazard=reset_hazard, reset_seed=reset_seed)


def assert_parity(bars, bands, dm) -> None:
    """The new argument must be inert at its default (rule 23)."""
    for book in STOP_BOOKS:
        a = E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                  exit_check=book)
        b = run_book(bars, bands, dm, book, reentry="later_decision")
        assert a.equals(b), f"reentry default is not bit-exact on book {book}"


def exp_r(sc: Score) -> float:
    return sc.net_r / sc.trades if sc.trades else np.nan


def gross_pt(sc: Score, inst: str) -> float:
    return sc.net_pt_per_trade + round_trip_cost_points(inst)


def trade_key(t: pd.DataFrame) -> set:
    return set(zip(t["date"], t["entry_mfo"].astype(int), t["side"].astype(int)))


def per_trade_r(t: pd.DataFrame, bars: pd.DataFrame, inst: str) -> pd.Series:
    """Net R per trade (points net of one round trip, scaled by the session ATR)."""
    atr = bars.groupby("sdate")["atr"].first()
    a = t["date"].map(atr)
    return (t["points"] - round_trip_cost_points(inst)) / a


# --------------------------------------------------------------------------- #
# the 2 x 2 cell grid
# --------------------------------------------------------------------------- #
def cell_table(inst, bars, bands, dm, dates) -> tuple[pd.DataFrame, dict]:
    rows, scores = [], {}
    for book in STOP_BOOKS:
        base = score_candidate(run_book(bars, bands, dm, book), bars, dates, inst,
                               f"base_{book}")
        scores[(book, "baseline")] = base
        rows.append(dict(stop_book=book, reset="(baseline)", n=base.trades,
                         retain=1.0, gross_pt=gross_pt(base, inst),
                         expR=exp_r(base), sumR=base.net_r, sharpe=base.sharpe,
                         d_sharpe=0.0, d_sumR=0.0, max_dd=base.max_dd,
                         recent_sharpe=base.recent_sharpe))
        for cad in RESET_CADENCES:
            sc = score_candidate(
                run_book(bars, bands, dm, book, reentry="require_reset",
                         reset_check=cad), bars, dates, inst, f"rr_{book}_{cad}")
            scores[(book, cad)] = sc
            rows.append(dict(stop_book=book, reset=cad, n=sc.trades,
                             retain=sc.trades / base.trades if base.trades else np.nan,
                             gross_pt=gross_pt(sc, inst), expR=exp_r(sc),
                             sumR=sc.net_r, sharpe=sc.sharpe,
                             d_sharpe=sc.sharpe - base.sharpe,
                             d_sumR=sc.net_r - base.net_r, max_dd=sc.max_dd,
                             recent_sharpe=sc.recent_sharpe))
    return pd.DataFrame(rows), scores


# --------------------------------------------------------------------------- #
# control 2: what does the lock actually remove?  (EXP-0024 diagnostic)
# --------------------------------------------------------------------------- #
def removed_added(inst, bars, bands, dm, dates, book, cad) -> dict:
    """Set-difference decomposition of the two books' trade tapes.

    NOT causal -- blocking an entry changes the state the rest of the session is
    simulated from, so `removed` is not simply "the trades the rule deleted". It
    still answers the question that matters: is the population the lock trades
    away a profitable one?
    """
    b = run_book(bars, bands, dm, book)
    t = run_book(bars, bands, dm, book, reentry="require_reset", reset_check=cad)
    di = pd.Index(pd.to_datetime(dates))
    b, t = b[b["date"].isin(di)].copy(), t[t["date"].isin(di)].copy()
    kb, kt = trade_key(b), trade_key(t)
    b["key"] = list(zip(b["date"], b["entry_mfo"].astype(int), b["side"].astype(int)))
    t["key"] = list(zip(t["date"], t["entry_mfo"].astype(int), t["side"].astype(int)))
    rem, add = b[~b["key"].isin(kt)], t[~t["key"].isin(kb)]
    kept = b[b["key"].isin(kt)]
    out = {}
    for name, frame in (("removed", rem), ("added", add), ("kept_common", kept)):
        r = per_trade_r(frame, bars, inst) if len(frame) else pd.Series(dtype=float)
        out[name] = dict(
            n=int(len(frame)),
            mean_netR=float(r.mean()) if len(r) else float("nan"),
            gross_pt=float(frame["points"].mean()) if len(frame) else float("nan"),
            hit=float((r > 0).mean()) if len(r) else float("nan"),
        )
    return out


# --------------------------------------------------------------------------- #
# control 1 (DECISIVE): matched-count random drop from the SAME pool
# --------------------------------------------------------------------------- #
def matched_count_null(inst, bars, bands, dm, dates, book, cad, base: Score,
                       treat: Score, ndraw: int = RAND_DRAWS):
    """Block K random post-stop same-side re-entry CANDIDATES instead of the K the
    reset rule blocks, and re-run the stateful engine (rule 18, never a post-hoc
    trade drop). The pool comes from the BASELINE book's audit channel, so it is
    exactly the population the rule operates on.
    """
    pool_a = []
    run_book(bars, bands, dm, book, audit_out=pool_a)
    di = set(pd.to_datetime(dates))
    pool = [(r["sdate"], int(r["mfo"]), int(r["side"])) for r in pool_a
            if r["sdate"] in di]
    # The count that must be MATCHED is the EXPOSURE the rule removes, i.e. the
    # net fall in trade count -- NOT the number of times the lock fires. Those
    # differ badly: the lock re-blocks the same suppressed breakout at every
    # later checkpoint while price stays outside the band, and conversely a
    # blocked entry key can be recovered by re-entering at the next checkpoint,
    # so one blocked key removes well under one trade. Matching on fire count
    # made the random arm cut ~1.5x more exposure than the rule, which flatters
    # it (fewer trades -> higher Sharpe is this book's known machinery bias).
    need = base.trades - treat.trades
    if not pool or need <= 0:
        return pd.DataFrame(), 0, len(pool)

    # An entry_gate is an ALLOW-list, so "block these K" = allow every candidate
    # signal key except them. Keys not in the pool must stay allowed, hence the
    # gate is built over the full (date, mfo, side) grid.
    all_keys = {(d, int(m), s) for d in pd.to_datetime(dates)
                for m in dm for s in (1, -1)}
    rng = np.random.default_rng(RAND_SEED0)
    idx = np.arange(len(pool))

    def draw(k, seed_rng):
        drop = {pool[j] for j in seed_rng.choice(idx, size=k, replace=False)}
        return score_candidate(run_book(bars, bands, dm, book,
                                        entry_gate=all_keys - drop),
                               bars, dates, inst, "rand")

    # Calibrate K on a pilot: measure how many trades one blocked key actually
    # removes, then solve for the K that reproduces the rule's trade count.
    pilot_rng = np.random.default_rng(RAND_SEED0 - 1)
    k0 = min(len(pool), max(1, need))
    removed0 = np.mean([base.trades - draw(k0, pilot_rng).trades for _ in range(5)])
    rate = removed0 / k0 if k0 else 1.0
    K = int(min(len(pool), max(1, round(need / rate)))) if rate > 0 else k0
    print(f"  exposure calibration: rule removes {need} trades; one blocked key "
          f"removes {rate:.3f} trades -> K={K} of pool={len(pool)}")
    if K >= len(pool):
        # DEGENERATE: matching the rule's exposure needs the whole pool, so every
        # "draw" is the same deterministic blocklist (sd=0) and any frac it prints
        # is meaningless. Bail loudly rather than emit a false pass; control 1b
        # (random unlock) is the design that can match a persistent lock.
        print(f"  DEGENERATE (K == pool): a one-shot blocklist cannot match a "
              f"PERSISTENT lock -- blocking the entire pool once removes only "
              f"{removed0:.0f} trades vs the rule's {need}. Control 1 not usable "
              f"on this cell; see control 1b.")
        return pd.DataFrame(), K, len(pool)

    rows = []
    for i in range(ndraw):
        sc = draw(K, rng)
        rows.append({"draw": i + 1, "sharpe": sc.sharpe, "sumR": sc.net_r,
                     "n": sc.trades,
                     "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  matched-exposure random drop {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows), K, len(pool)


# --------------------------------------------------------------------------- #
# drift-preserving Null C (gated on the primary metric)
# --------------------------------------------------------------------------- #
def random_reset_null(inst, bars, bands, dm, dates, book, cad, base: Score,
                      treat: Score, ndraw: int = RAND_DRAWS):
    """Control 1b (the DECISIVE one): keep the lock, randomise the UNLOCK.

    A one-shot entry blocklist cannot imitate this rule -- the lock persists and
    re-blocks the same breakout at every later checkpoint, so blocking even 100%
    of the candidate pool once removes FEWER trades than the rule does (the
    matched-exposure control went degenerate at K == pool). This control instead
    keeps the lock machinery exactly and replaces its trigger: after a stop, the
    lock clears on a coin flip at hazard p per checked bar instead of on "price
    is back inside the band". Same side-scoping, same cadence, same persistence,
    same (calibrated) exposure -- ONLY the information is destroyed.
    """
    def run_h(p, seed):
        return score_candidate(
            run_book(bars, bands, dm, book, reentry="random_reset",
                     reset_check=cad, reset_hazard=p, reset_seed=seed),
            bars, dates, inst, "rr_null")

    # Calibrate the hazard so the random lock removes the same number of trades.
    # Monotone in p (higher p -> unlocks sooner -> more trades), so bisect.
    lo, hi = 1e-4, 1.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if run_h(mid, 999).trades < treat.trades:
            lo = mid
        else:
            hi = mid
    p = (lo + hi) / 2
    print(f"  hazard calibration: p={p:.4f} -> n={run_h(p, 999).trades} "
          f"(rule n={treat.trades}, baseline n={base.trades})")

    rows = []
    for i in range(ndraw):
        sc = run_h(p, RAND_SEED0 + i)
        rows.append({"draw": i + 1, "hazard": p, "n": sc.trades,
                     "sharpe": sc.sharpe, "sumR": sc.net_r,
                     "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  random-unlock null {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows), p


def nullc(inst, real_bars, book, cad, ndraw: int) -> pd.DataFrame:
    rows = []
    for i in range(ndraw):
        nb = _null_c_frame(real_bars, seed=NULLC_SEED0 + i)
        bands = S.noise_bands(nb, LOOKBACK)
        dm = S.decision_mfos(PERIOD, int(nb["mfo"].max()))
        dates = common_dates(nb)
        base = score_candidate(run_book(nb, bands, dm, book), nb, dates, inst, "nb")
        sc = score_candidate(run_book(nb, bands, dm, book, reentry="require_reset",
                                      reset_check=cad), nb, dates, inst, "nt")
        rows.append({"draw": i + 1, "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  Null-C draw {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def real(inst: str, run_null: bool = False, ndraw: int = 40,
         cell: tuple[str, str] = PRIMARY) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    assert_parity(bars, bands, dm)

    print(f"\n=== HYP-0031 require_reset re-entry lock — {inst} ===")
    print(f"sessions={len(dates)}  {pd.Timestamp(dates[0]).date()} -> "
          f"{pd.Timestamp(dates[-1]).date()}  (lb{LOOKBACK}, {PERIOD}m clock, "
          f"VWAP gate, next-open fills)")
    print("default-off parity: PASS (reentry='later_decision' is bit-exact on both books)")

    tab, scores = cell_table(inst, bars, bands, dm, dates)
    tab.to_csv(OUT / f"cells_{inst}.csv", index=False)
    print("\n--- 2x2 cell grid (stop book x reset cadence) ---")
    print(tab.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    book, cad = cell
    is_primary = (cell == PRIMARY)
    sfx = "" if is_primary else f"_{book}_{cad}"
    base, treat = scores[(book, "baseline")], scores[(book, cad)]
    d_sh, d_r = treat.sharpe - base.sharpe, treat.net_r - base.net_r
    tag = ("PRIMARY cell (declared in HYP-0031)" if is_primary else
           "SECONDARY cell (SEARCHED, not preregistered -- report as such)")
    print(f"\n{tag}: stop={book} reset={cad}")
    print(f"  baseline  n={base.trades} Sharpe={base.sharpe:.4f} netR={base.net_r:+.2f} "
          f"grossPt/t={gross_pt(base, inst):+.4f} maxDD={base.max_dd:.2f}")
    print(f"  require_reset n={treat.trades} Sharpe={treat.sharpe:.4f} "
          f"netR={treat.net_r:+.2f} grossPt/t={gross_pt(treat, inst):+.4f} "
          f"maxDD={treat.max_dd:.2f}")
    print(f"  dSharpe={d_sh:+.4f}  dNetR={d_r:+.2f}  "
          f"dGrossPt/t={gross_pt(treat, inst) - gross_pt(base, inst):+.4f}  "
          f"retain={treat.trades / base.trades:.3f}")
    real_gate = bool(d_sh >= UPLIFT_GATE and treat.net_r >= base.net_r)
    print(f"  REAL GATE (dSharpe>=+{UPLIFT_GATE:.2f} AND netR>=base): "
          f"{'PASS' if real_gate else 'REJECT'}")

    print("\n--- control 2: what the lock trades away (set difference, descriptive) ---")
    dec = removed_added(inst, bars, bands, dm, dates, book, cad)
    for k, v in dec.items():
        print(f"  {k:<12s} n={v['n']:>5d}  mean_netR={v['mean_netR']:+.4f}  "
              f"gross_pt={v['gross_pt']:+.3f}  hit={v['hit']:.3f}")
    with open(OUT / f"decomposition_{inst}{sfx}.json", "w") as f:
        json.dump(dec, f, indent=2)

    print("\n--- control 1 (DECISIVE): matched-count random drop from the same pool ---")
    rnd, K, pooln = matched_count_null(inst, bars, bands, dm, dates, book, cad,
                                       base, treat)
    p_sh = p_r = float("nan")
    if len(rnd):
        rnd.to_csv(OUT / f"random_null_{inst}{sfx}.csv", index=False)
        p_sh = float((rnd["d_sharpe"] >= d_sh).mean())
        p_r = float((rnd["d_sumR"] >= d_r).mean())
        print(f"  blocked K={K} of pool={pooln} post-stop same-side re-entry candidates, "
              f"{len(rnd)} draws")
        print(f"  EXPOSURE MATCH: real n={treat.trades}  random n mean="
              f"{rnd['n'].mean():.0f} [{rnd['n'].min()}, {rnd['n'].max()}]  "
              f"(baseline {base.trades})")
        print(f"  real  dSharpe={d_sh:+.4f}  dSumR={d_r:+.2f}")
        print(f"  rand  dSharpe mean={rnd['d_sharpe'].mean():+.4f} "
              f"sd={rnd['d_sharpe'].std(ddof=1):.4f}  "
              f"dSumR mean={rnd['d_sumR'].mean():+.2f}")
        print(f"  frac(rand>=real): Sharpe={p_sh:.3f}  sumR={p_r:.3f}  "
              f"(<0.05 = the rule beats dropping the same number at random)")

    print("\n--- control 1b (DECISIVE): same lock, RANDOM unlock ---")
    rr, hz = random_reset_null(inst, bars, bands, dm, dates, book, cad, base, treat)
    rr.to_csv(OUT / f"random_reset_null_{inst}{sfx}.csv", index=False)
    q_sh = float((rr["d_sharpe"] >= d_sh).mean())
    q_r = float((rr["d_sumR"] >= d_r).mean())
    print(f"  EXPOSURE MATCH: real n={treat.trades}  random-unlock n mean="
          f"{rr['n'].mean():.0f} [{rr['n'].min()}, {rr['n'].max()}]")
    print(f"  real     dSharpe={d_sh:+.4f}  dSumR={d_r:+.2f}")
    print(f"  rand-unlock dSharpe mean={rr['d_sharpe'].mean():+.4f} "
          f"sd={rr['d_sharpe'].std(ddof=1):.4f}  dSumR mean={rr['d_sumR'].mean():+.2f}")
    print(f"  frac(rand-unlock>=real): Sharpe={q_sh:.3f}  sumR={q_r:.3f}  "
          f"(<0.05 = 'price returned to the band' beats waiting a random spell)")

    verdict = {
        "inst": inst, "primary_stop_book": book, "primary_reset": cad,
        "rr_null_hazard": hz, "rr_null_n_mean": float(rr["n"].mean()),
        "rr_null_dSharpe_mean": float(rr["d_sharpe"].mean()),
        "rr_null_dSharpe_sd": float(rr["d_sharpe"].std(ddof=1)),
        "rr_null_frac_ge_real_sharpe": q_sh, "rr_null_frac_ge_real_sumR": q_r,
        "sessions": int(len(dates)),
        "base": {"n": base.trades, "sharpe": base.sharpe, "netR": base.net_r,
                 "gross_pt": gross_pt(base, inst), "max_dd": base.max_dd,
                 "recent_sharpe": base.recent_sharpe},
        "require_reset": {"n": treat.trades, "sharpe": treat.sharpe,
                          "netR": treat.net_r, "gross_pt": gross_pt(treat, inst),
                          "max_dd": treat.max_dd,
                          "recent_sharpe": treat.recent_sharpe},
        "d_sharpe": d_sh, "d_sumR": d_r, "real_gate_passed": real_gate,
        "decomposition": dec,
        "matched_K": int(K), "cand_pool": int(pooln),
        "rand_frac_ge_real_sharpe": p_sh, "rand_frac_ge_real_sumR": p_r,
        "rand_dSharpe_mean": float(rnd["d_sharpe"].mean()) if len(rnd) else None,
        "rand_n_mean": float(rnd["n"].mean()) if len(rnd) else None,
        "cells": tab.to_dict(orient="records"),
    }

    if run_null and real_gate:
        print(f"\n--- drift-preserving Null C ({ndraw} draws) ---")
        print(f"  real diffusivity={diffusivity(bars):.6f}")
        nc = nullc(inst, bars, book, cad, ndraw)
        nc.to_csv(OUT / f"nullc_{inst}{sfx}.csv", index=False)
        sd = nc["d_sharpe"].std(ddof=1)
        z = (d_sh - nc["d_sharpe"].mean()) / sd if sd > 0 else np.nan
        p = float((nc["d_sharpe"] >= d_sh).mean())
        verdict.update(nullc_z=float(z), nullc_frac_ge_real=p,
                       nullc_dSharpe_mean=float(nc["d_sharpe"].mean()))
        print(f"  Null-C dSharpe mean={nc['d_sharpe'].mean():+.4f} sd={sd:.4f} "
              f"z={z:+.2f} frac(null>=real)={p:.3f}")
    elif run_null:
        print("\nReal gate did not pass -> Null C skipped (standing project rule).")

    with open(OUT / f"verdict_{inst}{sfx}.json", "w") as f:
        json.dump(verdict, f, indent=2, default=float)
    print(f"\nartifacts -> {OUT}")
    return verdict


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    inst = sys.argv[2] if len(sys.argv) > 2 else "NQ"
    ndraw = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    # optional target cell: <stop_book> <reset_cadence>; defaults to the
    # preregistered primary. A non-primary cell is SEARCHED, and is labelled as
    # such in the output and written to suffixed artifacts.
    cell = (sys.argv[4], sys.argv[5]) if len(sys.argv) > 5 else PRIMARY
    if cell[0] not in STOP_BOOKS or cell[1] not in RESET_CADENCES:
        raise SystemExit(f"bad cell {cell}; stop in {STOP_BOOKS}, reset in {RESET_CADENCES}")
    real(inst, run_null=(mode == "null"), ndraw=ndraw, cell=cell)


if __name__ == "__main__":
    main()
