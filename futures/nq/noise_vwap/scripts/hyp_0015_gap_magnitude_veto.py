"""HYP-0015 — symmetric overnight-gap MAGNITUDE whole-day veto.

Distinct from EXP-0016 (directional gap-vs-signal + low-RVOL per-signal veto) and
EXP-0017 (gap/RVOL sizing): here we SKIP THE WHOLE DAY when the causal overnight
gap magnitude, normalised by the session's causal ATR, exceeds a threshold T.

    gap_atr[day] = |rth_open - prior_close| / atr_pts        (all causal)
    skip day  iff  gap_atr > T

Mechanism claim: a large gap mis-anchors the same-slot band / VWAP the breakout
is measured against, so the earliest breakouts on a gap day are mis-sized noise.

Reads (in order of importance, per the standing learnings):
  1. Real family gate: family-max daily Sharpe uplift >= +0.10 AND net R >= base.
  2. Gross points-per-trade on KEPT trades: rising = real selection info;
     flat/falling with Sharpe up = rarity/variance filter (cutting exposure).
  3. Matched-count random-day-drop null: does dropping the SAME NUMBER of whole
     days at random do as well? (the rarity-filter discriminator).
  4. ES sibling: does the sign transfer? (the anchor-contamination mechanism test)
  5. Removed-trade mean-R BY ENTRY SLOT: early-slot concentration = mechanism.
  6. Paired drift-preserving Null-C — only if the real gate (1) passes.

Run:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0015_gap_magnitude_veto real NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0015_gap_magnitude_veto real ES
  python -u -m futures.nq.noise_vwap.scripts.hyp_0015_gap_magnitude_veto null NQ [ndraw]
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .studies import _null_c_frame
from .wfo import add_pnl, score
from .wfo_data import LOOKBACK

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0024"
T_GRID = (0.50, 0.75, 1.00, 1.50, 2.00)
RAND_DRAWS = 200
RAND_SEED0 = 24000
NULLC_SEED0 = 24500


def day_gap_atr(bars: pd.DataFrame, bands: pd.DataFrame) -> pd.Series:
    """Causal overnight-gap magnitude in ATR units, one value per trade-date.

    rth_open / prior_close come from the band frame (both strictly causal:
    rth_open is the session's own mfo==0 open, prior_close is the *prior*
    session's last close). atr_pts is the session's prior-14-session mean RTH
    range (first value of the causal `atr` column). Index = sdate."""
    g = (bands.groupby("sdate")[["rth_open", "prior_close"]].first())
    atr = bars.groupby("sdate")["atr"].first()
    gap_pts = (g["rth_open"] - g["prior_close"]).abs()
    out = (gap_pts / atr).rename("gap_atr")
    return out.dropna()


def skip_days_frame(base: pd.DataFrame, skip_days: set) -> pd.DataFrame:
    """Whole-day skip == remove that day's trades. Sessions are INDEPENDENT in
    this engine (each flattens at the close, no cross-day state), so gating out
    every decision key on a day is EXACTLY equivalent to dropping that day's
    trades from the ungated baseline. Verified once against the engine's
    entry_gate path in `_verify_equivalence` below."""
    if not skip_days:
        return base
    return base[~base["date"].isin(skip_days)]


def _verify_equivalence(bars, bands, dm, atr_by_date, base, gap) -> None:
    """One-time proof (rule: assert invariants in code) that the whole-day
    entry_gate path and the trade-filter path are identical, for the T=1.0 skip.
    Justifies using cheap trade-filtering instead of 200+ engine re-runs."""
    skip = set(gap.index[gap > 1.0])
    keep = [d for d in bars["sdate"].drop_duplicates() if d not in skip]
    gate = set(itertools.product(keep, [int(m) for m in dm]))
    engine = add_pnl(E.run(bars, bands, dm, exit_check="every_bar",
                           entry_gate=gate), atr_by_date)
    filt = skip_days_frame(base, skip)
    assert len(engine) == len(filt), (len(engine), len(filt))
    a = engine.sort_values(["date", "entry_mfo"])["points"].to_numpy()
    b = filt.sort_values(["date", "entry_mfo"])["points"].to_numpy()
    assert np.allclose(a, b), "gate vs filter mismatch"


def gross_per_trade(trades: pd.DataFrame) -> float:
    return float(trades["points"].mean()) if len(trades) else float("nan")


def summarise(base, treat, label) -> dict:
    sb, st = score(base), score(treat)
    return {
        "label": label,
        "base_n": sb["n"], "treat_n": st["n"],
        "retain": (st["n"] / sb["n"]) if sb["n"] else np.nan,
        "base_sharpe": sb["sharpe"], "treat_sharpe": st["sharpe"],
        "d_sharpe": st["sharpe"] - sb["sharpe"],
        "base_sumR": sb["sumR"], "treat_sumR": st["sumR"],
        "d_sumR": st["sumR"] - sb["sumR"],
        "base_gross": gross_per_trade(base), "treat_gross": gross_per_trade(treat),
    }


def real_sweep(inst: str) -> dict:
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    atr_by_date = bars.groupby("sdate")["atr"].first()
    gap = day_gap_atr(bars, bands)                      # index=sdate
    n_days = gap.shape[0]

    base = add_pnl(E.run(bars, bands, dm, exit_check="every_bar"), atr_by_date)
    _verify_equivalence(bars, bands, dm, atr_by_date, base, gap)
    rows = []
    per_T_skip = {}
    for T in T_GRID:
        skip = set(gap.index[gap > T])
        per_T_skip[T] = skip
        treat = skip_days_frame(base, skip)
        r = summarise(base, treat, f"T={T:.2f}")
        r["T"] = T
        r["days_skipped"] = len(skip)
        r["frac_days_skipped"] = len(skip) / n_days if n_days else np.nan
        rows.append(r)
    sweep = pd.DataFrame(rows)

    # best cell by daily Sharpe uplift (the primary), among cells that skip >0 days
    cand = sweep[sweep["days_skipped"] > 0]
    best = cand.loc[cand["d_sharpe"].idxmax()] if len(cand) else sweep.iloc[-1]
    bestT = float(best["T"])
    skip_best = per_T_skip[bestT]

    # ---- diagnostic: removed-trade mean net_atr BY ENTRY SLOT (mechanism test) --
    removed = base[base["date"].isin(skip_best)].copy()
    kept = base[~base["date"].isin(skip_best)].copy()
    slot = (removed.groupby("entry_mfo")["net_atr"].agg(["mean", "count"])
            if len(removed) else pd.DataFrame())
    slot_split = {
        "removed_early_meanR": float(
            removed.loc[removed["entry_mfo"] <= 149, "net_atr"].mean())
            if len(removed) else np.nan,
        "removed_late_meanR": float(
            removed.loc[removed["entry_mfo"] > 149, "net_atr"].mean())
            if len(removed) else np.nan,
        "kept_meanR": float(kept["net_atr"].mean()) if len(kept) else np.nan,
        "removed_meanR": float(removed["net_atr"].mean()) if len(removed) else np.nan,
        "removed_n": int(len(removed)),
    }

    return dict(inst=inst, bars=bars, bands=bands, dm=dm, atr=atr_by_date, gap=gap,
                base=base, sweep=sweep, bestT=bestT, skip_best=skip_best,
                slot=slot, slot_split=slot_split, n_days=n_days)


def matched_count_null(res: dict, ndraw: int = RAND_DRAWS) -> pd.DataFrame:
    """Drop the SAME NUMBER of whole days at random (not the gapped ones). If a
    random drop of k days lifts Sharpe/net R as much as the real gap gate, the
    gate is a rarity/variance filter, not information."""
    bars = res["bars"]
    k = len(res["skip_best"])
    all_days = np.array(sorted(bars["sdate"].drop_duplicates()))
    base = res["base"]
    sb = score(base)
    rows = []
    for i in range(ndraw):
        rng = np.random.default_rng(RAND_SEED0 + i)
        skip = set(all_days[rng.choice(len(all_days), size=k, replace=False)])
        treat = skip_days_frame(base, skip)
        st = score(treat)
        rows.append({"draw": i + 1, "d_sharpe": st["sharpe"] - sb["sharpe"],
                     "d_sumR": st["sumR"] - sb["sumR"],
                     "treat_gross": gross_per_trade(treat)})
        print(f"  matched-count random null {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


def nullc(res: dict, ndraw: int) -> pd.DataFrame:
    """Paired drift-preserving Null-C: recompute bands, gaps, gate on a shuffled
    frame. Only run if the real gate passes (standing rule)."""
    bars = res["bars"]; T = res["bestT"]
    rows = []
    for i in range(ndraw):
        nb = _null_c_frame(bars, seed=NULLC_SEED0 + i)
        bands = S.noise_bands(nb, LOOKBACK)
        dm = S.decision_mfos(30, int(nb["mfo"].max()))
        atr = nb.groupby("sdate")["atr"].first()
        gap = day_gap_atr(nb, bands)
        skip = set(gap.index[gap > T])
        nbase = add_pnl(E.run(nb, bands, dm, exit_check="every_bar"), atr)
        ntreat = skip_days_frame(nbase, skip)
        nsb, nst = score(nbase), score(ntreat)
        rows.append({"draw": i + 1, "d_sharpe": nst["sharpe"] - nsb["sharpe"],
                     "d_sumR": nst["sumR"] - nsb["sumR"], "days_skipped": len(skip)})
        print(f"  Null-C draw {i + 1}/{ndraw}", end="\r")
    print()
    return pd.DataFrame(rows)


def fmt_sweep(sweep: pd.DataFrame) -> str:
    cols = ["T", "days_skipped", "frac_days_skipped", "retain",
            "base_sharpe", "treat_sharpe", "d_sharpe",
            "base_sumR", "treat_sumR", "d_sumR", "base_gross", "treat_gross"]
    return sweep[cols].to_string(index=False,
                                 float_format=lambda v: f"{v:.4f}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    inst = sys.argv[2] if len(sys.argv) > 2 else "NQ"
    OUT.mkdir(parents=True, exist_ok=True)

    res = real_sweep(inst)
    print(f"\n=== HYP-0015 gap-magnitude whole-day veto — {inst} ===")
    print(f"eligible days = {res['n_days']}  baseline trades = {score(res['base'])['n']}")
    print(fmt_sweep(res["sweep"]))
    print(f"\nbest-by-dSharpe cell: T={res['bestT']:.2f}, "
          f"days skipped={len(res['skip_best'])}")
    print("removed-trade mean-R by slot (early<=149 / late>149) & kept:")
    print(json.dumps(res["slot_split"], indent=2))

    # matched-count random-day null (cheap, always run — the key discriminator)
    rnd = matched_count_null(res)
    best = res["sweep"].set_index("T").loc[res["bestT"]]
    real_dSh, real_dR = float(best["d_sharpe"]), float(best["d_sumR"])
    rnd_sh_mean, rnd_sh_sd = rnd["d_sharpe"].mean(), rnd["d_sharpe"].std(ddof=1)
    rnd_r_mean = rnd["d_sumR"].mean()
    p_sh = float((rnd["d_sharpe"] >= real_dSh).mean())
    p_r = float((rnd["d_sumR"] >= real_dR).mean())
    print("matched-count random-day-drop null:")
    print(f"  real  dSharpe={real_dSh:+.4f} dSumR={real_dR:+.3f}")
    print(f"  rand  dSharpe mean={rnd_sh_mean:+.4f} sd={rnd_sh_sd:.4f}  "
          f"dSumR mean={rnd_r_mean:+.3f}")
    print(f"  frac(rand>=real): Sharpe={p_sh:.3f}  sumR={p_r:.3f}")

    real_gate = bool(real_dSh >= 0.10 and best["treat_sumR"] >= best["base_sumR"])
    print(f"\nREAL GATE (dSharpe>=+0.10 AND netR>=base): "
          f"{'PASS' if real_gate else 'REJECT'}")

    verdict = {
        "inst": inst, "bestT": res["bestT"],
        "days_skipped": len(res["skip_best"]),
        "real_dSharpe": real_dSh, "real_dSumR": real_dR,
        "base_sharpe": float(best["base_sharpe"]),
        "treat_sharpe": float(best["treat_sharpe"]),
        "base_gross": float(best["base_gross"]),
        "treat_gross": float(best["treat_gross"]),
        "slot_split": res["slot_split"],
        "rand_dSharpe_mean": float(rnd_sh_mean), "rand_dSharpe_sd": float(rnd_sh_sd),
        "rand_dSumR_mean": float(rnd_r_mean),
        "rand_frac_ge_real_sharpe": p_sh, "rand_frac_ge_real_sumR": p_r,
        "real_gate_passed": real_gate,
    }

    res["sweep"].to_csv(OUT / f"real_sweep_{inst}.csv", index=False)
    rnd.to_csv(OUT / f"random_day_null_{inst}.csv", index=False)
    if len(res["slot"]):
        res["slot"].to_csv(OUT / f"removed_by_slot_{inst}.csv")

    if mode == "null" and real_gate:
        ndraw = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        nc = nullc(res, ndraw)
        nc.to_csv(OUT / f"nullc_{inst}.csv", index=False)
        p = float((nc["d_sumR"] >= real_dR).mean())
        z = ((real_dR - nc["d_sumR"].mean()) / nc["d_sumR"].std(ddof=1)
             if nc["d_sumR"].std(ddof=1) > 0 else np.nan)
        verdict["nullc_dSumR_mean"] = float(nc["d_sumR"].mean())
        verdict["nullc_z"] = float(z)
        verdict["nullc_frac_ge_real"] = p
        print(f"\nNull-C dSumR mean={nc['d_sumR'].mean():+.3f} z={z:+.2f} "
              f"frac(null>=real)={p:.3f}")
    elif mode == "null":
        print("\nReal gate did not pass -> Null-C skipped (standing rule).")

    (OUT / f"verdict_{inst}.json").write_text(json.dumps(verdict, indent=2) + "\n")
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
