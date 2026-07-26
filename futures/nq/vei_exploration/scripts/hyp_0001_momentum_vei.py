"""EXP-0004 / HYP-0001 -- momentum works only when VEI is high?

Promotes Study D to a preregistered causal strategy test. Momentum rule: go with the
trailing 30-min move; fill next-open; hold 30 min; flat at close. Gate on VEI regime.
Preregistered primary cell = `high` (VEI>1.10), horizon 30. Dose-response controls
`all` / `low`; T sensitivity sweep; matched-count random null; path-preserving Null C.

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0001_momentum_vei real NQ
  python -u -m futures.nq.vei_exploration.scripts.hyp_0001_momentum_vei null NQ 30
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import loaders as L
from ..core import vei as V
from ..core import strategy as ST
from ..core import nulls as N

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0004"
PERIOD = 30
DM = [j * PERIOD - 1 for j in range(1, 14)]     # 29..389
PAST_WIN = 30
HORIZON = 30
VEI_KW = dict(short=10, long=50, atr_method="wilder", smooth=0)
T_PRIMARY = 1.10
TSWEEP = [0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20]
HORIZONS = [15, 30, 60]
RAND_DRAWS = 200
RAND_SEED0 = 40000
NULLC_SEED0 = 41000
DAY_T_GATE = 2.0


def build(inst):
    bars = L.load_1m_rth(inst)
    vei = V.vei_series(bars, **VEI_KW).to_numpy()
    atr = L.daily_atr(bars, 14)
    dates = np.sort(bars["sdate"].unique())
    cost = ST.round_trip_cost_points(inst)
    return bars, vei, atr, dates, cost


def sc_of(bars, vei, atr, dates, cost, mode, thr, horizon, name, gate_keys=None,
          allow_overlap=False):
    tr = ST.simulate(bars, DM, vei, mode=mode, thr=thr, horizon=horizon,
                     cost_pts=cost, past_win=PAST_WIN, gate_keys=gate_keys,
                     allow_overlap=allow_overlap)
    return ST.score(tr, dates, atr, name), tr


def decision_pool(bars, vei):
    """All decision bars that produce a valid momentum bet (any VEI) -- the random
    null pool. Returns list of (date, mfo) and count of high-VEI members."""
    tr_all = ST.simulate(bars, DM, vei, mode="all", thr=0.0, horizon=HORIZON,
                         cost_pts=0.0, past_win=PAST_WIN)
    return list(zip(tr_all["date"], tr_all["mfo"].astype(int)))


def real(inst, run_null=False, ndraw=30):
    OUT.mkdir(parents=True, exist_ok=True)
    bars, vei, atr, dates, cost = build(inst)
    print(f"\n================ EXP-0004 momentum-in-VEI — {inst} ================")
    print(f"VEI={VEI_KW}  clock={PERIOD}m past_win={PAST_WIN} horizon={HORIZON} "
          f"cost={cost:.3f}pt  sessions={len(dates)}")

    # ---- dose-response: all / low / high at the preregistered T ----
    print("\n--- dose-response (preregistered T=1.10) ---")
    base_all, _ = sc_of(bars, vei, atr, dates, cost, "all", 0.0, HORIZON, "momo_all")
    base_low, _ = sc_of(bars, vei, atr, dates, cost, "low", T_PRIMARY, HORIZON, "momo_low<=1.10")
    prim, tr_hi = sc_of(bars, vei, atr, dates, cost, "high", T_PRIMARY, HORIZON, "momo_high>1.10")
    for s in (base_all, base_low, prim):
        print(ST.fmt(s))

    # ---- HYP-0003: rule-23 reproduction + threshold confound control ----------- #
    #
    # The Wilder ATR warm-up was repaired (core/vei.py seed='sma'); this run therefore
    # uses a DIFFERENT feature from the one EXP-0004 published. Two rows are needed to
    # keep the comparison honest: the LEGACY feature at the same absolute cut (which
    # must reproduce EXP-0004), and the repaired feature at the legacy SELECTION RATE
    # (so a changed result cannot be a side effect of the distribution shifting under
    # a fixed 1.10 line). EXP-0004's REJECT verdict stands regardless of these rows --
    # see HYP-0003's multiple-testing note.
    print("\n--- HYP-0003 reproduction + threshold control ---")
    vei_legacy = V.vei_series(bars, **{**VEI_KW, "seed": V.SEED_FIRST}).to_numpy()
    dec = np.isin(bars["mfo"].to_numpy(), DM)
    share_legacy = float(np.nanmean(vei_legacy[dec] > T_PRIMARY))
    t_match = float(np.nanquantile(vei[dec], 1.0 - share_legacy))
    print(f"  legacy share > {T_PRIMARY} = {share_legacy:.4f}  ->  matched-rate cut on "
          f"repaired VEI = {t_match:.4f}")
    leg, _ = sc_of(bars, vei_legacy, atr, dates, cost, "high", T_PRIMARY, HORIZON,
                   "LEGACY_high>1.10")
    mat, _ = sc_of(bars, vei, atr, dates, cost, "high", t_match, HORIZON,
                   f"repaired_matched>{t_match:.3f}")
    for s in (leg, prim, mat):
        print(ST.fmt(s))
    print("  LEGACY row must match EXP-0004's published high>1.10 cell (rule 23).")
    pd.DataFrame([{"cut": n, **s.__dict__} for n, s in
                  (("legacy_abs_1.10", leg), ("repaired_abs_1.10", prim),
                   (f"repaired_matched_{t_match:.3f}", mat))]
                 ).to_csv(OUT / f"threshold_control_{inst}.csv", index=False)

    # ---- T sensitivity sweep (high & low) ----
    print("\n--- T sensitivity sweep ---")
    sweep_rows = []
    for mode in ("high", "low"):
        for T in TSWEEP:
            s, _ = sc_of(bars, vei, atr, dates, cost, mode, T, HORIZON, f"{mode}_{T}")
            sweep_rows.append({"mode": mode, "T": T, "n": s.trades, "netR": s.net_r,
                               "sharpe": s.sharpe, "day_t": s.day_t, "hit": s.hit,
                               "net_pt_per_trade": s.net_pt_per_trade})
    sw = pd.DataFrame(sweep_rows)
    print(sw.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    sw.to_csv(OUT / f"sweep_{inst}.csv", index=False)

    # ---- horizon check on the primary gate ----
    print("\n--- horizon check (high>1.10) ---")
    hz_rows = []
    for H in HORIZONS:
        s, _ = sc_of(bars, vei, atr, dates, cost, "high", T_PRIMARY, H, f"H{H}")
        print(ST.fmt(s))
        hz_rows.append({"horizon": H, "n": s.trades, "netR": s.net_r,
                        "sharpe": s.sharpe, "day_t": s.day_t,
                        "book": "1-unit (non-overlapping)"})

    # ---- ERRATUM (EXP-0005): the H=60 estimand ----
    # A 60-min hold on a 30-min decision clock fills a second bet before the first
    # exits. The originally published H=60 row therefore describes a book running up
    # to TWO concurrent positions, while HYP-0001 declares non-overlapping
    # single-position bets and `score()` sums per-bet R per day as one unit (rule 13).
    # `simulate` now enforces non-overlap by default; the rows below make the three
    # estimands explicit side by side. H<=30 is unaffected (the guard is a no-op when
    # the hold does not exceed the decision spacing).
    print("\n--- H=60 estimand check (erratum, EXP-0005) ---")
    over, _ = sc_of(bars, vei, atr, dates, cost, "high", T_PRIMARY, 60,
                    "H60_overlap2u", allow_overlap=True)
    tight, _ = sc_of(bars, vei, atr, dates, cost, "high", T_PRIMARY, 60, "H60_1unit")
    trc = ST.simulate(bars, [j * 60 - 1 for j in range(1, 7)], vei, mode="high",
                      thr=T_PRIMARY, horizon=60, cost_pts=cost, past_win=PAST_WIN)
    clk = ST.score(trc, dates, atr, "H60_clock60")
    for s in (over, tight, clk):
        print(ST.fmt(s))
    print("  H60_overlap2u = as originally published (up to 2 concurrent positions);")
    print("  H60_1unit     = same clock, one position at a time (declared estimand);")
    print("  H60_clock60   = 60-min decision clock, non-overlapping by construction.")
    for s, book in ((over, "2-unit (overlapping, as originally published)"),
                    (tight, "1-unit (30-min clock, guard on)"),
                    (clk, "1-unit (60-min clock)")):
        hz_rows.append({"horizon": 60, "n": s.trades, "netR": s.net_r,
                        "sharpe": s.sharpe, "day_t": s.day_t, "book": book})
    pd.DataFrame(hz_rows).to_csv(OUT / f"horizon_{inst}.csv", index=False)

    # ---- KILL TEST gate 1 ----
    gate1 = (prim.net_r > 0 and prim.sharpe > 0 and prim.day_t >= DAY_T_GATE
             and prim.net_r > base_low.net_r and prim.sharpe > base_low.sharpe)
    print(f"\nKILL-TEST 1 (real gate: high netR>0 & Sh>0 & day_t>={DAY_T_GATE} & "
          f"high>low): {'PASS' if gate1 else 'REJECT'}")

    verdict = {"inst": inst, "cost_pt": cost,
               "all": base_all.__dict__, "low": base_low.__dict__,
               "high_primary": prim.__dict__, "gate1_passed": bool(gate1)}

    if not gate1:
        print("Real gate failed -> nulls skipped (standing rule).")
        (OUT / f"verdict_{inst}.json").write_text(json.dumps(verdict, indent=2, default=float) + "\n")
        print(f"\nartifacts -> {OUT}")
        return verdict

    # ---- KILL TEST gate 2: matched-count random-decision-bar null ----
    pool = decision_pool(bars, vei)
    K = prim.trades
    rng = np.random.default_rng(RAND_SEED0)
    ridx = np.arange(len(pool))
    rr = []
    for i in range(RAND_DRAWS):
        pick = rng.choice(ridx, size=K, replace=False)
        gk = {pool[j] for j in pick}
        s, _ = sc_of(bars, vei, atr, dates, cost, "all", 0.0, HORIZON,
                     f"rand{i}", gate_keys=gk)
        rr.append({"draw": i + 1, "netR": s.net_r, "sharpe": s.sharpe})
        print(f"  matched-count random null {i+1}/{RAND_DRAWS}", end="\r")
    print()
    rr = pd.DataFrame(rr); rr.to_csv(OUT / f"random_null_{inst}.csv", index=False)
    p_sh = float((rr["sharpe"] >= prim.sharpe).mean())
    p_r = float((rr["netR"] >= prim.net_r).mean())
    print(f"matched-count random null (K={K} of {len(pool)} pool, {RAND_DRAWS} draws): "
          f"real Sh={prim.sharpe:+.3f} netR={prim.net_r:+.2f}; "
          f"rand Sh mean={rr['sharpe'].mean():+.3f} netR mean={rr['netR'].mean():+.2f}; "
          f"frac(rand>=real) Sh={p_sh:.3f} netR={p_r:.3f}")
    gate2 = (p_sh < 0.05 and p_r < 0.05)
    print(f"KILL-TEST 2 (VEI selection beats random equal-count): "
          f"{'PASS' if gate2 else 'REJECT as alpha (rarity/turnover lever)'}")
    verdict.update(rand_frac_ge_sharpe=p_sh, rand_frac_ge_netR=p_r,
                   rand_sharpe_mean=float(rr["sharpe"].mean()),
                   rand_netR_mean=float(rr["netR"].mean()), matched_K=int(K),
                   pool=int(len(pool)), gate2_passed=bool(gate2))

    # ---- KILL TEST gate 3: path-preserving Null C ----
    if run_null:
        real_diff = N.diffusivity(bars)
        rows = []
        for i in range(ndraw):
            nb = N.null_c(bars, seed=NULLC_SEED0 + i)
            nv = V.vei_series(nb, **VEI_KW).to_numpy()
            natr = L.daily_atr(nb, 14)
            ndates = np.sort(nb["sdate"].unique())
            s, _ = sc_of(nb, nv, natr, ndates, cost, "high", T_PRIMARY, HORIZON, "nc")
            rows.append({"draw": i + 1, "netR": s.net_r, "sharpe": s.sharpe,
                         "diff": N.diffusivity(nb)})
            print(f"  Null-C draw {i+1}/{ndraw}", end="\r")
        print()
        nc = pd.DataFrame(rows); nc.to_csv(OUT / f"nullc_{inst}.csv", index=False)
        z = ((prim.net_r - nc["netR"].mean()) / nc["netR"].std(ddof=1)
             if nc["netR"].std(ddof=1) > 0 else np.nan)
        p = float((nc["netR"] >= prim.net_r).mean())
        print(f"diffusivity real={real_diff:.5f} null_mean={nc['diff'].mean():.5f} "
              f"(rule 17-bis gate ~equal)")
        print(f"Null C (high>1.10): real netR={prim.net_r:+.2f} Sh={prim.sharpe:+.3f}; "
              f"null netR mean={nc['netR'].mean():+.2f} sd={nc['netR'].std(ddof=1):.2f} "
              f"center={'POS' if nc['netR'].mean()>0 else 'NEG'}; z={z:+.2f} "
              f"frac(null>=real)={p:.3f}")
        gate3 = (p <= 0.05)
        print(f"KILL-TEST 3 (real momentum beats path-preserving null): "
              f"{'PASS' if gate3 else 'REJECT (machinery)'}")
        verdict.update(nullc_z=float(z), nullc_frac_ge_real=p,
                       nullc_netR_mean=float(nc["netR"].mean()),
                       real_diff=float(real_diff),
                       nullc_diff_mean=float(nc["diff"].mean()),
                       gate3_passed=bool(gate3))
        verdict["VERDICT"] = ("CANDIDATE EDGE (holdout-pending)"
                              if (gate1 and gate2 and gate3) else "REJECT")
        print(f"\n=== VERDICT {inst}: {verdict['VERDICT']} ===")

    (OUT / f"verdict_{inst}.json").write_text(json.dumps(verdict, indent=2, default=float) + "\n")
    print(f"\nartifacts -> {OUT}")
    return verdict


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    inst = sys.argv[2] if len(sys.argv) > 2 else "NQ"
    ndraw = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    real(inst, run_null=(mode == "null"), ndraw=ndraw)


if __name__ == "__main__":
    main()
