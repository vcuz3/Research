"""Test HYP-0018: condition the partial-take-profit on entry-bar Hurst.

Follow-on from EXP-0026. The Hurst LEVEL is an established, cross-market, per-trade
CONTINUATION signal (persistent tape -> breakout continues; chop tape -> breakout
reverts) that did NOT monetize as an entry GATE because gating cuts exposure. This
applies the SAME signal where it costs no exposure: the EXIT horizon. Entries and
the trade population are UNCHANGED; only the partial-take-profit is modulated.

For a threshold T (sweep over H_GRID): a trade whose causal session-to-date entry
Hurst H <= T gets the `tp1.0_50` partial (bank 50% at +1 ATR, runner trails); a
trade with H > T runs to the band/VWAP stop (baseline runner). The sweep endpoints
recover the two unconditional references:
  * no-tp  (continuous-stop baseline)      == T below every H
  * all-tp (unconditional tp1.0_50)        == T above every H
so an interior T that beats BOTH endpoints is the value of CONDITIONING on H. A
MIRROR control banks the HIGH-H trades (tp_gate = {H >= T}); the mechanism predicts
the mirror is worse (banking early on trend gives up the runner).

Implemented via the default-off `tp_gate` on core.engine2 (parity: tp_gate=None or
tp_gate=all-entry-keys both reproduce unconditional tp1.0_50 bit-exact).

Primary metric = full-sample zero-trade-day daily net-ATR-R Sharpe of the best
conditional cell; the load-bearing quantity is the CONDITIONING UPLIFT = Sharpe
(best conditional) - Sharpe(unconditional tp1.0_50). Per the standing rule the
paired Null-C runs ONLY if the best conditional clears dSharpe>=+0.10 over the
no-tp baseline AND net R>=baseline AND Sharpe > both unconditional references.

Examples:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0018_hurst_exit real NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0018_hurst_exit real ES
  python -u -m futures.nq.noise_vwap.scripts.hyp_0018_hurst_exit null NQ 30
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .studies import _null_c_frame
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, common_dates, LOOKBACK, PERIOD, UPLIFT_GATE,
)
from .hyp_0017_hurst_filter import hurst_features

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0027"

H_GRID = np.array([0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65])
TP_ATR, TP_FRAC = 1.0, 0.5           # the adopted tp1.0_50 partial
NULLC_SEED0 = 27000


# --------------------------------------------------------------------------- #
# engine helpers
# --------------------------------------------------------------------------- #
def run_tp(bars, bands, dm, tp_gate="ALL"):
    """tp_gate: 'ALL' -> unconditional tp1.0_50; None -> no tp (baseline);
    a set -> partial fires only on those (date, entry_mfo) keys."""
    if tp_gate is None:                                  # no partial at all
        return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                     exit_check="every_bar")
    gate = None if tp_gate == "ALL" else tp_gate
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar", tp_atr=TP_ATR, tp_frac=TP_FRAC, tp_gate=gate)


def entry_gate_keys(feats: pd.DataFrame, thr: float, direction: str) -> set:
    """(date, entry_mfo) keys where the partial fires. entry_mfo = decision_mfo+1
    (next-open fill). direction 'low' -> bank H<=T (conditional); 'high' -> mirror."""
    sub = feats[feats["H"] <= thr] if direction == "low" else feats[feats["H"] >= thr]
    return set(zip(sub["date"], (sub["mfo"].astype(int) + 1)))


def assert_parity(bars, bands, dm, feats) -> None:
    all_keys = set(zip(feats["date"], feats["mfo"].astype(int) + 1))
    a = run_tp(bars, bands, dm, "ALL")
    b = run_tp(bars, bands, dm, all_keys)
    assert len(a) == len(b) and abs(a["points"].sum() - b["points"].sum()) < 1e-9, \
        "tp_gate=all-keys must reproduce unconditional tp"


def exp_r(sc: Score) -> float:
    return sc.net_r / sc.trades if sc.trades else np.nan


# --------------------------------------------------------------------------- #
# sweep
# --------------------------------------------------------------------------- #
def sweep(bars, bands, dm, dates, inst, feats, no_tp: Score, all_tp: Score,
          direction: str) -> pd.DataFrame:
    rows = []
    for thr in H_GRID:
        gate = entry_gate_keys(feats, thr, direction)
        sc = score_candidate(run_tp(bars, bands, dm, gate), bars, dates, inst,
                             f"{direction}{thr:.2f}")
        rows.append({
            "dir": direction, "thr": float(thr),
            "banked_frac": len(gate) / len(feats) if len(feats) else np.nan,
            "n": sc.trades, "sumR": sc.net_r, "sharpe": sc.sharpe,
            "exp_netR": exp_r(sc),
            "d_sh_vs_notp": sc.sharpe - no_tp.sharpe,
            "d_sh_vs_alltp": sc.sharpe - all_tp.sharpe,
            "d_sumR_vs_notp": sc.net_r - no_tp.net_r,
            "recent_sharpe": sc.recent_sharpe, "max_dd": sc.max_dd,
        })
    return pd.DataFrame(rows)


def fmt(df: pd.DataFrame) -> str:
    cols = ["thr", "banked_frac", "n", "sumR", "sharpe", "exp_netR",
            "d_sh_vs_notp", "d_sh_vs_alltp", "d_sumR_vs_notp", "recent_sharpe", "max_dd"]
    return df[cols].to_string(index=False, float_format=lambda v: f"{v:.4f}")


# --------------------------------------------------------------------------- #
# paired Null-C on the conditioning uplift (best-T re-searched per draw)
# --------------------------------------------------------------------------- #
def best_conditional_uplift(bars, bands, dm, dates, inst, feats):
    """Return (best conditional Sharpe - unconditional all-tp Sharpe) over the
    H_GRID, direction 'low' (bank chop). Used for both real and null."""
    all_tp = score_candidate(run_tp(bars, bands, dm, "ALL"), bars, dates, inst, "alltp")
    best = -np.inf
    for thr in H_GRID:
        gate = entry_gate_keys(feats, thr, "low")
        sc = score_candidate(run_tp(bars, bands, dm, gate), bars, dates, inst, "c")
        best = max(best, sc.sharpe)
    return best - all_tp.sharpe


def nullc(inst, ndraw: int) -> pd.DataFrame:
    rows = []
    for i in range(ndraw):
        nb = _null_c_frame(S.load_session(inst, "RTH"), seed=NULLC_SEED0 + i)
        bands = S.noise_bands(nb, LOOKBACK)
        dm = S.decision_mfos(PERIOD, int(nb["mfo"].max()))
        dates = common_dates(nb)
        feats = hurst_features(nb, dm)
        up = best_conditional_uplift(nb, bands, dm, dates, inst, feats)
        rows.append({"draw": i + 1, "cond_uplift": up})
        print(f"  Null-C draw {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def real(inst: str, run_null: bool = False, ndraw: int = 30) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    feats = hurst_features(bars, dm)
    assert_parity(bars, bands, dm, feats)

    no_tp = score_candidate(run_tp(bars, bands, dm, None), bars, dates, inst, "no_tp")
    all_tp = score_candidate(run_tp(bars, bands, dm, "ALL"), bars, dates, inst, "all_tp")
    print(f"\n=== HYP-0018 Hurst-conditioned partial-TP — {inst} ===")
    print(f"REFERENCES  no-tp (continuous-stop baseline): Sharpe={no_tp.sharpe:.4f} "
          f"netR={no_tp.net_r:.2f} expR/t={exp_r(no_tp):+.4f} n={no_tp.trades}")
    print(f"            all-tp (unconditional tp1.0_50) : Sharpe={all_tp.sharpe:.4f} "
          f"netR={all_tp.net_r:.2f} expR/t={exp_r(all_tp):+.4f} n={all_tp.trades}")

    cond = sweep(bars, bands, dm, dates, inst, feats, no_tp, all_tp, "low")
    mirr = sweep(bars, bands, dm, dates, inst, feats, no_tp, all_tp, "high")
    print("\n--- CONDITIONAL: bank tp on LOW-Hurst (H<=T) trades, hold high-H runner ---")
    print(fmt(cond))
    print("\n--- MIRROR (wrong-way control): bank tp on HIGH-Hurst (H>=T) trades ---")
    print(fmt(mirr))
    cond.to_csv(OUT / f"conditional_{inst}.csv", index=False)
    mirr.to_csv(OUT / f"mirror_{inst}.csv", index=False)

    best = cond.loc[cond["sharpe"].idxmax()]
    ref = max(no_tp.sharpe, all_tp.sharpe)
    cond_uplift = float(best["sharpe"] - all_tp.sharpe)
    print(f"\nBEST CONDITIONAL: T={best['thr']:.2f} banked_frac={best['banked_frac']:.3f} "
          f"Sharpe={best['sharpe']:.4f} netR={best['sumR']:.2f}")
    print(f"  vs no-tp   dSharpe={best['sharpe']-no_tp.sharpe:+.4f} "
          f"dNetR={best['sumR']-no_tp.net_r:+.2f}")
    print(f"  vs all-tp  dSharpe={cond_uplift:+.4f}  (CONDITIONING UPLIFT)")
    print(f"  mirror best Sharpe={mirr['sharpe'].max():.4f} "
          f"(mechanism wants this < conditional)")

    real_gate = bool(best["sharpe"] - no_tp.sharpe >= UPLIFT_GATE
                     and best["sumR"] >= no_tp.net_r
                     and best["sharpe"] > ref)
    print(f"\nREAL GATE (dSharpe>=+{UPLIFT_GATE:.2f} vs no-tp AND netR>=base AND "
          f"Sharpe>both refs): {'PASS' if real_gate else 'REJECT'}")

    verdict = {
        "inst": inst,
        "no_tp": {"sharpe": no_tp.sharpe, "netR": no_tp.net_r, "n": no_tp.trades},
        "all_tp": {"sharpe": all_tp.sharpe, "netR": all_tp.net_r, "n": all_tp.trades},
        "best_conditional": {k: (float(v) if isinstance(v, (int, float, np.floating))
                                 else v) for k, v in best.to_dict().items()},
        "cond_uplift_vs_alltp": cond_uplift,
        "mirror_best_sharpe": float(mirr["sharpe"].max()),
        "real_gate_passed": real_gate,
    }

    if run_null and real_gate:
        nc = nullc(inst, ndraw)
        nc.to_csv(OUT / f"nullc_{inst}.csv", index=False)
        m, sd = nc["cond_uplift"].mean(), nc["cond_uplift"].std(ddof=1)
        z = (cond_uplift - m) / sd if sd > 0 else np.nan
        p = float((nc["cond_uplift"] >= cond_uplift).mean())
        verdict.update(nullc_mean=float(m), nullc_sd=float(sd), nullc_z=float(z),
                       nullc_frac_ge_real=p)
        print(f"\nNull-C conditioning uplift: real={cond_uplift:+.4f} "
              f"null mean={m:+.4f} sd={sd:.4f} z={z:+.2f} frac(null>=real)={p:.3f}")
    elif run_null:
        print("\nReal gate did not pass -> Null-C skipped (standing rule).")

    (OUT / f"verdict_{inst}.json").write_text(json.dumps(verdict, indent=2) + "\n")
    print(f"\nartifacts -> {OUT}")
    return verdict


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    inst = sys.argv[2] if len(sys.argv) > 2 else "NQ"
    ndraw = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    real(inst, run_null=(mode == "null"), ndraw=ndraw)


if __name__ == "__main__":
    main()
