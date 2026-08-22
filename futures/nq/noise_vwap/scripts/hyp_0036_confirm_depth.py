"""HYP-0036 (EXP-0048): entry confirmation-depth gate.

Require the decision-bar close to be beyond the noise band by at least k ATR
(`ext_atr >= k`, a causal feature from wfo.candidate_signals) before entering.
Motivated by the 2026 hit-rate collapse (shallow breaks fail to follow through)
and the anticipatory-entry sweep (per-trade edge rises with break depth). Tested
under the project's turnover-lever discipline: the decisive control is the
matched-count random-drop null, not raw Sharpe.

Protocol (preregistered, HYP-0036.md):
  1. Split NQ common sessions: TRAIN = first 60%, TEST = last 40%.
  2. Sweep k on NQ TRAIN; select k* = argmax TRAIN dSharpe subject to retain>=0.50.
     If no retain>=0.50 cell has dSharpe>0 -> NO-GO on TRAIN.
  3. NQ TEST kill test (ALL): dSharpe>=+0.10 AND netR not fall; beats matched-count
     random-drop null (frac<0.05, 200 draws); ES TEST same-sign transfer.
  4. If pass: Null C on NQ TEST (40 draws) + ES transfer.

Usage:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0036_confirm_depth NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0036_confirm_depth ES <k*>
  python -u -m futures.nq.noise_vwap.scripts.hyp_0036_confirm_depth null NQ <k*> 40
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import engine2_nb as NB
from ..core import session as S
from .studies import _null_c_frame
from .wfo import candidate_signals
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, common_dates, round_trip_cost_points,
    LOOKBACK, PERIOD,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0048"

SPLIT_FRAC = 0.60
KGRID = [0.00, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
RETAIN_FLOOR = 0.50
RAND_DRAWS = 200
RAND_SEED0 = 48000
NULLC_SEED0 = 48500
GATE = 0.10


def split_dates(dates):
    k = int(round(len(dates) * SPLIT_FRAC))
    return dates[:k], dates[k:]


def run_gated(bars, bands, dm, gate):
    return NB.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                  exit_check="every_bar", entry_gate=gate)


def assert_parity(bars, bands, dm):
    a = NB.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
               exit_check="every_bar")
    b = E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
              exit_check="every_bar")
    assert len(a) == len(b) and abs(a["points"].sum() - b["points"].sum()) < 1e-6
    # k=0 gate == baseline (all candidate signals kept) -> bit-exact trade count
    cand = candidate_signals(bars, bands, dm)
    g0 = set(zip(cand["date"], cand["signal_mfo"].astype(int)))
    c = run_gated(bars, bands, dm, g0)
    assert len(c) == len(a) and abs(c["points"].sum() - a["points"].sum()) < 1e-6, \
        (len(c), len(a))


def gate_from(cand, k):
    sub = cand[cand["ext_atr"] >= k]
    return set(zip(sub["date"], sub["signal_mfo"].astype(int)))


def exp_r(sc):
    return sc.net_r / sc.trades if sc.trades else np.nan


# --------------------------------------------------------------------------- #
def sweep_train(inst, bars, bands, dm, cand, train, base_tr):
    rt = round_trip_cost_points(inst)
    rows = []
    for k in KGRID:
        gate = gate_from(cand, k)
        sc = score_candidate(run_gated(bars, bands, dm, gate), bars, list(train), inst, f"k{k}")
        rows.append({"k": k, "n": sc.trades,
                     "retain": sc.trades / base_tr.trades if base_tr.trades else np.nan,
                     "gross_pt_per_trade": sc.net_pt_per_trade + rt,
                     "exp_netR_per_trade": exp_r(sc), "sumR": sc.net_r,
                     "sharpe": sc.sharpe, "d_sharpe": sc.sharpe - base_tr.sharpe,
                     "d_sumR": sc.net_r - base_tr.net_r})
    return pd.DataFrame(rows)


def matched_count_null(inst, bars, bands, dm, cand, dates, base, k, ndraw=RAND_DRAWS):
    pool = list(zip(cand["date"], cand["signal_mfo"].astype(int)))
    gate = gate_from(cand, k)
    K = sum(1 for key in pool if key in gate)
    rng = np.random.default_rng(RAND_SEED0)
    idx = np.arange(len(pool))
    rows = []
    for i in range(ndraw):
        pick = rng.choice(idx, size=K, replace=False)
        gate_r = {pool[j] for j in pick}
        sc = score_candidate(run_gated(bars, bands, dm, gate_r), bars, list(dates), inst, f"rand{i}")
        rows.append({"draw": i + 1, "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  matched-count random null {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows), K, len(pool)


def nullc(inst, k, ndraw):
    rows = []
    for i in range(ndraw):
        nb = _null_c_frame(S.load_session(inst, "RTH"), seed=NULLC_SEED0 + i)
        bands = S.noise_bands(nb, LOOKBACK)
        dm = S.decision_mfos(PERIOD, int(nb["mfo"].max()))
        dates = common_dates(nb)
        _, test = split_dates(dates)
        cand = candidate_signals(nb, bands, dm)
        base = score_candidate(run_gated(nb, bands, dm, None), nb, list(test), inst, "nbase")
        gate = gate_from(cand, k)
        sc = score_candidate(run_gated(nb, bands, dm, gate), nb, list(test), inst, "ntreat")
        rows.append({"draw": i + 1, "d_sharpe": sc.sharpe - base.sharpe,
                     "d_sumR": sc.net_r - base.net_r})
        print(f"  Null-C draw {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
def fmt(df):
    return df.to_string(index=False, float_format=lambda v: f"{v:.4f}")


def select_and_test(inst):
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    assert_parity(bars, bands, dm)
    cand = candidate_signals(bars, bands, dm)
    train, test = split_dates(dates)

    base_tr = score_candidate(run_gated(bars, bands, dm, None), bars, list(train), inst, "base_tr")
    base_te = score_candidate(run_gated(bars, bands, dm, None), bars, list(test), inst, "base_te")
    print(f"\n=== HYP-0036 confirmation-depth gate — {inst} ===")
    print(f"TRAIN baseline: n={base_tr.trades} Sharpe={base_tr.sharpe:.4f} netR={base_tr.net_r:.2f}")
    print(f"TEST  baseline: n={base_te.trades} Sharpe={base_te.sharpe:.4f} netR={base_te.net_r:.2f}")

    sw = sweep_train(inst, bars, bands, dm, cand, train, base_tr)
    print("\n-- TRAIN sweep --")
    print(fmt(sw))
    sw.to_csv(OUT / f"train_sweep_{inst}.csv", index=False)

    elig = sw[(sw["retain"] >= RETAIN_FLOOR) & (sw["k"] > 0)]
    if elig.empty or elig["d_sharpe"].max() <= 0:
        print(f"\nNO-GO on TRAIN: no retain>={RETAIN_FLOOR} cell with dSharpe>0.")
        json.dump({"verdict": "NO-GO-train", "inst": inst},
                  open(OUT / f"verdict_{inst}.json", "w"), indent=2)
        return
    kstar = float(elig.loc[elig["d_sharpe"].idxmax(), "k"])
    print(f"\nSelected k* = {kstar} (argmax TRAIN dSharpe with retain>={RETAIN_FLOOR})")

    # ---- NQ/ES TEST evaluation ----
    gate = gate_from(cand, kstar)
    sc_te = score_candidate(run_gated(bars, bands, dm, gate), bars, list(test), inst, f"k{kstar}_test")
    d_sh = sc_te.sharpe - base_te.sharpe
    d_nr = sc_te.net_r - base_te.net_r
    print(f"\n-- TEST k*={kstar} -- Sharpe {base_te.sharpe:.4f} -> {sc_te.sharpe:.4f} "
          f"(dSharpe {d_sh:+.4f}), netR {base_te.net_r:.2f} -> {sc_te.net_r:.2f} (d {d_nr:+.2f}), "
          f"n {base_te.trades}->{sc_te.trades} (retain {sc_te.trades/base_te.trades:.3f})")
    real_gate = (d_sh >= GATE) and (d_nr >= 0)
    print(f"real gate (dSharpe>=+{GATE} AND netR not fall): {'PASS' if real_gate else 'FAIL'}")

    rnd, K, pooln = matched_count_null(inst, bars, bands, dm, cand, test, base_te, kstar)
    rnd.to_csv(OUT / f"random_null_test_{inst}.csv", index=False)
    frac = float((rnd["d_sharpe"] >= d_sh).mean())
    print(f"matched-count random-drop null (keep {K} of {pooln}, {RAND_DRAWS} draws): "
          f"real dSharpe {d_sh:+.4f} vs null mean {rnd['d_sharpe'].mean():+.4f} "
          f"sd {rnd['d_sharpe'].std(ddof=1):.4f}, frac(random>=real) {frac:.3f} "
          f"({'PASS' if frac < 0.05 else 'FAIL'} <0.05)")

    verdict = "PASS-test" if (real_gate and frac < 0.05) else "NO-GO"
    print(f"\n{inst} TEST verdict (pre-ES, pre-NullC): {verdict}")
    json.dump({"inst": inst, "kstar": kstar, "test_dSharpe": d_sh, "test_dNetR": d_nr,
               "test_retain": sc_te.trades / base_te.trades, "real_gate": real_gate,
               "rand_frac": frac, "verdict": verdict},
              open(OUT / f"verdict_{inst}.json", "w"), indent=2)


def null_run(inst, k, ndraw):
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    _, test = split_dates(dates)
    cand = candidate_signals(bars, bands, dm)
    base = score_candidate(run_gated(bars, bands, dm, None), bars, list(test), inst, "base_te")
    gate = gate_from(cand, k)
    sc = score_candidate(run_gated(bars, bands, dm, gate), bars, list(test), inst, f"k{k}")
    real = sc.sharpe - base.sharpe
    nc = nullc(inst, k, ndraw)
    nc.to_csv(OUT / f"nullc_test_{inst}.csv", index=False)
    frac = float((nc["d_sharpe"] >= real).mean())
    print(f"\nNull C {inst} TEST k={k}: real dSharpe {real:+.4f} vs null mean "
          f"{nc['d_sharpe'].mean():+.4f} sd {nc['d_sharpe'].std(ddof=1):.4f}, "
          f"frac(null>=real) {frac:.3f} ({'PASS' if frac < 0.05 else 'FAIL'} <0.05); "
          f"null center {'POSITIVE=variance-amp' if nc['d_sharpe'].mean() > 0 else 'NEGATIVE=tied-to-cut'}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "null":
        null_run(a[1], float(a[2]), int(a[3]) if len(a) > 3 else 40)
    elif len(a) >= 2:
        # ES transfer with a frozen k*
        inst, kstar = a[0], float(a[1])
        OUT.mkdir(parents=True, exist_ok=True)
        bars = S.load_session(inst, "RTH")
        bands = S.noise_bands(bars, LOOKBACK)
        dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
        dates = common_dates(bars)
        cand = candidate_signals(bars, bands, dm)
        _, test = split_dates(dates)
        base_te = score_candidate(run_gated(bars, bands, dm, None), bars, list(test), inst, "base_te")
        gate = gate_from(cand, kstar)
        sc_te = score_candidate(run_gated(bars, bands, dm, gate), bars, list(test), inst, f"k{kstar}")
        d_sh = sc_te.sharpe - base_te.sharpe
        rnd, K, pooln = matched_count_null(inst, bars, bands, dm, cand, test, base_te, kstar)
        rnd.to_csv(OUT / f"random_null_test_{inst}.csv", index=False)
        frac = float((rnd["d_sharpe"] >= d_sh).mean())
        print(f"\n=== {inst} TEST transfer k*={kstar} ===")
        print(f"Sharpe {base_te.sharpe:.4f} -> {sc_te.sharpe:.4f} (dSharpe {d_sh:+.4f}), "
              f"netR {base_te.net_r:.2f}->{sc_te.net_r:.2f}, retain {sc_te.trades/base_te.trades:.3f}")
        print(f"random-drop null frac(random>=real) {frac:.3f} "
              f"({'PASS' if frac < 0.05 else 'FAIL'})")
    else:
        select_and_test(a[0] if a else "NQ")
