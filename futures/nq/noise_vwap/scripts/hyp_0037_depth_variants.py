"""HYP-0037 (EXP-0049): smarter depth entry gate — three arms.

A: side-asymmetric depth (k_long vs k_short, clock gate on ext_atr).
B: always-fire deeper threshold (entry_mode="threshold"), era-resolved, vs the
   deployed clock baseline (NOT the over-firing buf=0 arm).
C: band-relative depth (gate on ext_sigma = break depth in per-slot band-halfwidth
   units) instead of session-ATR units, plus the per-slot fire-rate CV diagnostic.

All arms: deployed clock baseline reference, TRAIN first 60% / TEST last 40%,
matched-count random-drop null as the decisive control. No core engine change.

Usage:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0037_depth_variants NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0037_depth_variants ES
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .wfo import candidate_signals
from .hyp_0012_diffusion_cone import (
    score_candidate, common_dates, round_trip_cost_points, LOOKBACK, PERIOD,
)
from .hyp_0036_confirm_depth import run_gated, split_dates, RAND_DRAWS, RAND_SEED0, GATE

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0049"
KL_GRID = [0.00, 0.05, 0.10, 0.15, 0.20]
KS_GRID = [0.00, 0.05, 0.10, 0.15, 0.20]
KSIG_GRID = [0.00, 0.10, 0.20, 0.30, 0.50, 0.75, 1.00, 1.50]
BUFS = [0.00, 0.05, 0.10, 0.15, 0.20, 0.30]
RETAIN_FLOOR = 0.50


def load(inst):
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    cand = candidate_signals(bars, bands, dm)
    # band-relative depth: break beyond the band expressed in per-slot half-band
    # units. close-ref = ext_atr*atr (price); half-band = (upper-lower)/2 (price).
    cand["ext_sigma"] = cand["ext_atr"] * cand["atr"] / (0.5 * (cand["upper"] - cand["lower"]))
    return bars, bands, dm, dates, cand


def keys(sub):
    return set(zip(sub["date"], sub["signal_mfo"].astype(int)))


def sc_gate(inst, bars, dates, gate, name):
    return score_candidate(run_gated(bars, *_bd(bars), gate), bars, list(dates), inst, name)


# small helper so we don't recompute bands/dm each call
_BD = {}
def _bd(bars):
    k = id(bars)
    if k not in _BD:
        _BD[k] = (S.noise_bands(bars, LOOKBACK), S.decision_mfos(PERIOD, int(bars["mfo"].max())))
    return _BD[k]


def matched_null(inst, bars, dm, cand, dates, base, K, ndraw=RAND_DRAWS, tag=""):
    pool = list(zip(cand["date"], cand["signal_mfo"].astype(int)))
    rng = np.random.default_rng(RAND_SEED0)
    idx = np.arange(len(pool))
    out = []
    bands, _ = _bd(bars)
    for i in range(ndraw):
        pick = rng.choice(idx, size=K, replace=False)
        g = {pool[j] for j in pick}
        s = score_candidate(run_gated(bars, bands, dm, g), bars, list(dates), inst, "r")
        out.append(s.sharpe - base.sharpe)
        print(f"  {tag} random null {i + 1}/{ndraw}", end="\r")
    print()
    return np.array(out)


def fmt(df):
    return df.to_string(index=False, float_format=lambda v: f"{v:.4f}")


# --------------------------------------------------------------------------- #
def arm_A(inst, bars, dm, cand, train, test, base_tr, base_te, rt):
    print("\n===== ARM A: side-asymmetric depth (clock gate) =====")
    bands, _ = _bd(bars)
    rows = []
    for kl in KL_GRID:
        for ks in KS_GRID:
            sub = cand[((cand["side"] == 1) & (cand["ext_atr"] >= kl)) |
                       ((cand["side"] == -1) & (cand["ext_atr"] >= ks))]
            s = score_candidate(run_gated(bars, bands, dm, keys(sub)), bars, list(train), inst, "A")
            rows.append({"k_long": kl, "k_short": ks, "n": s.trades,
                         "retain": s.trades / base_tr.trades,
                         "sharpe": s.sharpe, "d_sharpe": s.sharpe - base_tr.sharpe,
                         "d_sumR": s.net_r - base_tr.net_r})
    tr = pd.DataFrame(rows)
    print("-- TRAIN grid (d_sharpe vs baseline) --")
    piv = tr.pivot(index="k_long", columns="k_short", values="d_sharpe")
    print(piv.to_string(float_format=lambda v: f"{v:+.3f}"))
    tr.to_csv(OUT / f"armA_train_{inst}.csv", index=False)
    elig = tr[(tr["retain"] >= RETAIN_FLOOR) & ((tr["k_long"] > 0) | (tr["k_short"] > 0))]
    if elig.empty or elig["d_sharpe"].max() <= 0:
        print("Arm A NO-GO on TRAIN (no retain>=0.5 asym cell with dSharpe>0).")
        return {"arm": "A", "verdict": "NO-GO-train"}
    best = elig.loc[elig["d_sharpe"].idxmax()]
    kl, ks = float(best["k_long"]), float(best["k_short"])
    print(f"Selected k_long={kl}, k_short={ks} (TRAIN dSharpe {best['d_sharpe']:+.3f}, retain {best['retain']:.2f})")
    sub = cand[((cand["side"] == 1) & (cand["ext_atr"] >= kl)) |
               ((cand["side"] == -1) & (cand["ext_atr"] >= ks))]
    g = keys(sub)
    s = score_candidate(run_gated(bars, bands, dm, g), bars, list(test), inst, "A_te")
    d_sh, d_nr = s.sharpe - base_te.sharpe, s.net_r - base_te.net_r
    print(f"-- TEST -- Sharpe {base_te.sharpe:.4f}->{s.sharpe:.4f} (d {d_sh:+.4f}), "
          f"netR {base_te.net_r:.2f}->{s.net_r:.2f} (d {d_nr:+.2f}), retain {s.trades/base_te.trades:.3f}")
    real_gate = (d_sh >= GATE) and (d_nr >= 0)
    res = {"arm": "A", "k_long": kl, "k_short": ks, "d_sharpe": d_sh, "d_netR": d_nr,
           "real_gate": bool(real_gate)}
    if real_gate:
        K = sum(1 for k in zip(cand["date"], cand["signal_mfo"].astype(int)) if k in g)
        null = matched_null(inst, bars, dm, cand, test, base_te, K, tag="A")
        res["rand_frac"] = float((null >= d_sh).mean())
        print(f"random-drop null frac {res['rand_frac']:.3f}")
    print(f"Arm A gate: {'PASS' if real_gate else 'FAIL'}")
    return res


def arm_B(inst, bars, bands, dm, dates, cand, rt):
    print("\n===== ARM B: always-fire deeper threshold, era-resolved =====")
    train, test = split_dates(dates)
    recent = list(dates)[int(len(dates) * 0.80):]  # last 20% of sessions
    segs = {"TRAIN": list(train), "TEST": list(test), "RECENT20%": recent}
    base = {seg: score_candidate(run_gated(bars, bands, dm, None), bars, d, inst, "base")
            for seg, d in segs.items()}
    print("clock baseline: " + " | ".join(
        f"{seg} Sh {base[seg].sharpe:+.3f} n{base[seg].trades} netPt/t {base[seg].net_pt_per_trade:+.3f}"
        for seg in segs))
    rows = []
    for b in BUFS:
        tr = E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                   exit_check="every_bar", stop_ref="both", entry_mode="threshold",
                   entry_buf_atr=b, entry_persist=1)
        for seg, d in segs.items():
            s = score_candidate(tr, bars, d, inst, "thr")
            rows.append({"buf": b, "seg": seg, "n": s.trades,
                         "expo_vs_clock": s.trades / base[seg].trades,
                         "netPt_per_trade": s.net_pt_per_trade, "sharpe": s.sharpe,
                         "d_sharpe_vs_clock": s.sharpe - base[seg].sharpe})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"armB_{inst}.csv", index=False)
    for seg in segs:
        print(f"\n-- {seg} (vs clock baseline Sh {base[seg].sharpe:+.3f}, n {base[seg].trades}) --")
        print(fmt(df[df["seg"] == seg][["buf", "n", "expo_vs_clock", "netPt_per_trade",
                                        "sharpe", "d_sharpe_vs_clock"]]))
    return {"arm": "B", "note": "descriptive; threshold over-fires (no cooldown)"}


def arm_C(inst, bars, dm, cand, train, test, base_tr, base_te, rt):
    print("\n===== ARM C: band-relative (per-slot) depth normalization =====")
    bands, _ = _bd(bars)
    # ---- fire-rate CV diagnostic: ext_atr>=0.10 vs ext_sigma>=(matched rate) ----
    k_ref = 0.10
    keep_atr = cand["ext_atr"] >= k_ref
    target = keep_atr.mean()
    ks = float(np.quantile(cand["ext_sigma"], 1.0 - target))  # matched overall rate
    keep_sig = cand["ext_sigma"] >= ks
    g = cand.assign(a=keep_atr, s=keep_sig).groupby("tod")
    diag = g.agg(n=("a", "size"), fire_atr=("a", "mean"), fire_sig=("s", "mean")).reset_index()
    cv_atr = diag["fire_atr"].std() / diag["fire_atr"].mean()
    cv_sig = diag["fire_sig"].std() / diag["fire_sig"].mean()
    print(f"per-slot fire-rate CV @ matched rate {target:.3f}: "
          f"ext_atr>={k_ref} CV={cv_atr:.3f}  vs  ext_sigma>={ks:.3f} CV={cv_sig:.3f} "
          f"({'sigma flatter (ATR was a clock)' if cv_sig < cv_atr else 'no improvement'})")
    diag.to_csv(OUT / f"armC_fire_cv_{inst}.csv", index=False)

    rows = []
    for k in KSIG_GRID:
        sub = cand[cand["ext_sigma"] >= k]
        s = score_candidate(run_gated(bars, bands, dm, keys(sub)), bars, list(train), inst, "C")
        rows.append({"k_sigma": k, "n": s.trades, "retain": s.trades / base_tr.trades,
                     "gross_pt_per_trade": s.net_pt_per_trade + rt,
                     "sharpe": s.sharpe, "d_sharpe": s.sharpe - base_tr.sharpe,
                     "d_sumR": s.net_r - base_tr.net_r})
    tr = pd.DataFrame(rows)
    print("-- TRAIN sweep --")
    print(fmt(tr))
    tr.to_csv(OUT / f"armC_train_{inst}.csv", index=False)
    elig = tr[(tr["retain"] >= RETAIN_FLOOR) & (tr["k_sigma"] > 0)]
    if elig.empty or elig["d_sharpe"].max() <= 0:
        print("Arm C NO-GO on TRAIN (no retain>=0.5 cell with dSharpe>0).")
        return {"arm": "C", "verdict": "NO-GO-train", "cv_atr": cv_atr, "cv_sig": cv_sig}
    kstar = float(elig.loc[elig["d_sharpe"].idxmax(), "k_sigma"])
    print(f"Selected k_sigma*={kstar} (TRAIN retain>=0.5)")
    sub = cand[cand["ext_sigma"] >= kstar]
    g = keys(sub)
    s = score_candidate(run_gated(bars, bands, dm, g), bars, list(test), inst, "C_te")
    d_sh, d_nr = s.sharpe - base_te.sharpe, s.net_r - base_te.net_r
    print(f"-- TEST k_sigma*={kstar} -- Sharpe {base_te.sharpe:.4f}->{s.sharpe:.4f} (d {d_sh:+.4f}), "
          f"netR {base_te.net_r:.2f}->{s.net_r:.2f} (d {d_nr:+.2f}), retain {s.trades/base_te.trades:.3f}")
    real_gate = (d_sh >= GATE) and (d_nr >= 0)
    res = {"arm": "C", "k_sigma": kstar, "d_sharpe": d_sh, "d_netR": d_nr,
           "real_gate": bool(real_gate), "cv_atr": cv_atr, "cv_sig": cv_sig}
    if real_gate:
        K = sum(1 for k in zip(cand["date"], cand["signal_mfo"].astype(int)) if k in g)
        null = matched_null(inst, bars, dm, cand, test, base_te, K, tag="C")
        res["rand_frac"] = float((null >= d_sh).mean())
        print(f"random-drop null frac {res['rand_frac']:.3f}")
    print(f"Arm C gate: {'PASS' if real_gate else 'FAIL'}")
    return res


def main(inst):
    OUT.mkdir(parents=True, exist_ok=True)
    bars, bands, dm, dates, cand = load(inst)
    rt = round_trip_cost_points(inst)
    train, test = split_dates(dates)
    base_tr = score_candidate(run_gated(bars, bands, dm, None), bars, list(train), inst, "b_tr")
    base_te = score_candidate(run_gated(bars, bands, dm, None), bars, list(test), inst, "b_te")
    print(f"\n### HYP-0037 depth variants — {inst} ###")
    print(f"TRAIN baseline Sh {base_tr.sharpe:.4f} n{base_tr.trades} netR {base_tr.net_r:.2f} | "
          f"TEST baseline Sh {base_te.sharpe:.4f} n{base_te.trades} netR {base_te.net_r:.2f}")
    res = {"inst": inst}
    res["A"] = arm_A(inst, bars, dm, cand, train, test, base_tr, base_te, rt)
    res["B"] = arm_B(inst, bars, bands, dm, dates, cand, rt)
    res["C"] = arm_C(inst, bars, dm, cand, train, test, base_tr, base_te, rt)
    json.dump(res, open(OUT / f"verdict_{inst}.json", "w"), indent=2, default=float)
    print(f"\nwrote {OUT / f'verdict_{inst}.json'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
