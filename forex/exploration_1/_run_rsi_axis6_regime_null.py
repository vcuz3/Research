"""Block/circular-shift NULL for the risk-off hysteresis regime (axis 6, item 20 v2).

The item-20 v2 finding: mean-reversion is a risk-ON edge; risk-OFF fades are
flat-to-negative (risk_on > risk_off mean_R on 4/4 pairs). The believability hinges
on ONE thing -- risk-off is only ~28 distinct episodes over 12 years, so the trades
in it are highly correlated and the naive cluster-t is weak (-0.43). This null asks:
does the real risk_on - risk_off asymmetry exceed what those 28 CLUSTERED episodes
produce when their alignment with the fade P&L is destroyed but their autocorrelation
structure is preserved?

NULL = CIRCULAR SHIFT of the daily risk-off state around the VIX calendar (LEARNINGS
2026-08-03: for an autocorrelated cyclical regime label, a circular shift preserves
run-lengths/episode structure and destroys only the alignment; a free permutation
would destroy the autocorrelation and be anti-conservative). The per-trade fade P&L
is FIXED; only the risk-off LABELS are rotated. Statistics per pair, both exits:
  T     = mean_R(risk_on) - mean_R(risk_off)   (the asymmetry; real should be HIGH)
  S_off = mean_R(risk_off)                     (real should be LOW vs rotations)
frac_ge_real(T) and frac_le_real(S_off) are one-sided p-values.

Measured on the DEPLOYABLE book: the combined news blackout (veto entry within +-30
min of a High-impact release OR whose 240-min hold spans one) is applied first, so
the final risk-on book carries BOTH adopted constraints. The no-blackout universe is
reported alongside for comparison.

Consumed history; 2024+ sealed. Reproduce:  python -u _run_rsi_axis6_regime_null.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    build_features, extract, ohlc_arrays, select_events, shift_paths, simulate,
)
from _run_rsi_exit_horizon import EXTRA, HORIZON, SCALE, SLIPPAGE, STOP_K, target_exit_idx
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_axis6_risk import load_vix_daily
from _run_rsi_axis6_regime import hysteresis_state, episodes
from _run_rsi_news_blackout import nearest_and_holdspan
from _run_rsi_axis6_calendar import high_impact_times
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_axis6_regime_null_results.json"

K = 3.0
N_SHIFTS = 2000
MIN_SHIFT_DAYS = 30          # exclude near-real alignments
SEED = 20260807


def trade_pnl(pair, vix_dates, off):
    """Per-trade R, risk-off label, and news-blackout keep flag at the k=3.0 op point."""
    f = add_twap_z(build_features(pair))
    ev = high_impact_times(pair)
    arrays = ohlc_arrays(f)
    z = f.z_twap
    cond = (z.le(-K) | z.ge(K)).fillna(False).to_numpy()
    side_all = np.where(z.le(-K).fillna(False), 1.0,
                        np.where(z.ge(K).fillna(False), -1.0, 0.0))
    idx = select_events(f, cond, horizon=HORIZON)
    d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
    side = side_all[idx]
    zp_full = f.z_twap.to_numpy()[(idx[:, None] + 1) + np.arange(HORIZON + 1 + EXTRA)[None, :]]

    pp = shift_paths(paths, 0, horizon=HORIZON)
    entry = pp["open"][:, 0]
    sgH = f.rv_30m.to_numpy()[idx] * SCALE * 1e4 * entry
    stop = STOP_K * sgH
    pnl_t, _, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)
    ex, _ = target_exit_idx(zp_full[:, :HORIZON + 1], side, HORIZON)
    pnl_g, _, _ = simulate(pp, side, stop, ex, SLIPPAGE)
    R = {"time": pnl_t / sgH, "target": pnl_g / sgH}

    entry_t = f.time.to_numpy()[idx]
    pos = np.searchsorted(vix_dates, entry_t.astype("datetime64[ns]"), side="right") - 1
    pos = np.clip(pos, 0, len(off) - 1)
    nearest, holds = nearest_and_holdspan(entry_t, ev)
    keep_blk = (nearest >= 30) & (~holds)
    return R, pos, keep_blk


def stats(R, pos, off, keep):
    """Real T, S_off on the kept trades."""
    ro = off[pos] & keep
    rn = (~off[pos]) & keep
    out = {}
    for ex in ("time", "target"):
        x = R[ex]
        moff = float(np.nanmean(x[ro])) if ro.sum() else np.nan
        mon = float(np.nanmean(x[rn])) if rn.sum() else np.nan
        out[ex] = {"mean_on": mon, "mean_off": moff, "T": mon - moff,
                   "n_on": int(rn.sum()), "n_off": int(ro.sum())}
    return out


def null_dist(R, pos, off, keep, rng):
    n = len(off)
    shifts = rng.integers(MIN_SHIFT_DAYS, n - MIN_SHIFT_DAYS, size=N_SHIFTS)
    res = {ex: {"T": np.empty(N_SHIFTS), "S_off": np.empty(N_SHIFTS)} for ex in ("time", "target")}
    kb = keep
    for i, s in enumerate(shifts):
        offs = np.roll(off, s)[pos]
        ro = offs & kb
        rn = (~offs) & kb
        for ex in ("time", "target"):
            x = R[ex]
            moff = np.nanmean(x[ro]) if ro.sum() else np.nan
            mon = np.nanmean(x[rn]) if rn.sum() else np.nan
            res[ex]["T"][i] = mon - moff
            res[ex]["S_off"][i] = moff
    return res


def analyse(pair, vix_dates, off, rng):
    R, pos, keep_blk = trade_pnl(pair, vix_dates, off)
    keep_all = np.ones(len(pos), bool)
    result = {"pair": pair}
    for uni, keep in [("no_blackout", keep_all), ("blackout", keep_blk)]:
        real = stats(R, pos, off, keep)
        nul = null_dist(R, pos, off, keep, rng)
        cells = {}
        for ex in ("time", "target"):
            T0 = real[ex]["T"]
            S0 = real[ex]["mean_off"]
            Tn = nul[ex]["T"]
            Sn = nul[ex]["S_off"]
            frac_T = float(np.mean(Tn >= T0))          # asymmetry unusually LARGE?
            frac_S = float(np.mean(Sn <= S0))          # risk-off unusually LOW?
            cells[ex] = {**real[ex],
                         "null_T_mean": float(np.nanmean(Tn)),
                         "null_T_sd": float(np.nanstd(Tn)),
                         "frac_ge_real_T": frac_T,
                         "z_T": float((T0 - np.nanmean(Tn)) / (np.nanstd(Tn) + 1e-12)),
                         "null_Soff_mean": float(np.nanmean(Sn)),
                         "frac_le_real_Soff": frac_S}
        result[uni] = cells
    return result


def main():
    print("Loading VIX + hysteresis state ...", flush=True)
    vix = load_vix_daily()
    off = hysteresis_state(vix)
    vix_dates = vix.index.values.astype("datetime64[ns]")
    print(f"   {len(off)} daily closes; risk-off day share {off.mean():.3f}; "
          f"{episodes(off)} episodes; {N_SHIFTS} circular shifts "
          f"(min |s|={MIN_SHIFT_DAYS}d)", flush=True)
    rng = np.random.default_rng(SEED)

    rows = [analyse(p, vix_dates, off, rng) for p in PAIRS]

    for uni in ("no_blackout", "blackout"):
        for ex in ("time", "target"):
            print(f"\n================ {uni.upper()} | {ex} exit ================")
            print(f"{'pair':7s} {'n_on':>6s} {'n_off':>6s} {'mean_on':>8s} "
                  f"{'mean_off':>8s} {'T=on-off':>9s} {'nullT':>8s} "
                  f"{'z_T':>6s} {'frac>=T':>8s} {'frac<=Soff':>10s}")
            passes = 0
            for r in rows:
                c = r[uni][ex]
                print(f"{r['pair']:7s} {c['n_on']:6d} {c['n_off']:6d} "
                      f"{c['mean_on']:+8.4f} {c['mean_off']:+8.4f} {c['T']:+9.4f} "
                      f"{c['null_T_mean']:+8.4f} {c['z_T']:+6.2f} "
                      f"{c['frac_ge_real_T']:8.3f} {c['frac_le_real_Soff']:10.3f}")
                if c['frac_ge_real_T'] < 0.05:
                    passes += 1
            print(f"   -> asymmetry T passes (frac<0.05): {passes}/4 pairs")

    OUT.write_text(json.dumps({
        "metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                     "test": "circular-shift block null on daily risk-off state (25/20 hysteresis)",
                     "k": K, "n_shifts": N_SHIFTS, "min_shift_days": MIN_SHIFT_DAYS,
                     "n_episodes": episodes(off), "risk_off_day_share": float(off.mean()),
                     "statistics": "T=mean_R(on)-mean_R(off); S_off=mean_R(off)",
                     "blackout": "veto entry within +-30min of High release OR hold spans one"},
        "pairs": rows}, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
