"""
A/B: equal-weight Noise-Area band (baseline) vs two VOLUME-WEIGHTED variants,
on the IDENTICAL engine/fills/costs, plus a Null-C machinery check on each.

  base      core.data.noise_bands            equal-weight cross-day excursion mean
  v3_share  volshare-weighted cross-day mean (WIDTH-matched to base)
  v2_vwap   VWAP +/- mult*sigma_vw           (FREQUENCY-matched to base)

Why two different match modes:
  * v3 shares base's static open/prior_close reference, so matching median band
    half-width is the right control: it strips the known non-predictive width dial
    (WFO net-R z=-2.55) and leaves only the effect of the volume RE-WEIGHTING.
  * v2's band is centered on the DRIFTING VWAP, so a half-width match leaves it
    almost untradeable (VWAP chases price; price is rarely N pts above its own
    VWAP). The fair control is to tune `mult` so v2 trades at ~base's frequency,
    then ask if a VWAP-anchored band of comparable activity carries information.

The match scalar is computed on REAL data and held FIXED across the null
(identical-pipeline, rule 17). Null-C then says whether band SHAPE/location is
signal or machinery.

Usage: python -u -m futures.nq.noise_vwap.scripts.vol_noise_ab NQ 90 15
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run
from ..core.metrics import summarize, fmt
from ..core.nulls import null_c_returns, diffusivity
from ..core.vol_bands import vwap_sigma_bands, noise_bands_volshare, median_halfwidth


def day_net_series(trades: pd.DataFrame, inst: str, cost_pts: float) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    net = trades["points"] - 2.0 * cost_pts
    return net.groupby(trades["date"]).sum() * POINT_VALUE[inst]


def trades_per_day(bars, band_fn) -> float:
    t = run(bars, band_fn(bars))
    return (len(t) / bars["date"].nunique()) if not t.empty else 0.0


def tune_mult_for_freq(bars, target_tpd, lo=0.2, hi=4.0, iters=7):
    """Bisection: trades/day is DECREASING in mult (tighter band -> more breakouts).
    Find mult so v2 trades ~ target_tpd."""
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        tpd = trades_per_day(bars, lambda b: vwap_sigma_bands(b, mult=mid))
        print(f"    tune v2: mult={mid:.3f} -> {tpd:.3f} tpd", flush=True)
        if tpd > target_tpd:   # too many trades -> band too tight -> raise mult
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def run_variant(name, bars, band_fn, inst, cost, seeds):
    """Run real + Null-C for one band builder. band_fn(bars)->bands long frame."""
    bands = band_fn(bars)
    real = run(bars, bands)
    real_day = day_net_series(real, inst, cost)
    summ = summarize(real, inst, cost, name)
    hw = median_halfwidth(bands)

    null_means, null_gross = [], []
    for k, sd in enumerate(seeds):
        nbar = null_c_returns(bars, seed=sd)
        nt = run(nbar, band_fn(nbar))
        null_means.append(day_net_series(nt, inst, cost).mean() if not nt.empty else 0.0)
        null_gross.append(nt["points"].mean() if not nt.empty else 0.0)
        print(f"    {name} null {k:2d}: day$net={null_means[-1]:+.1f}", flush=True)
    nm = np.array(null_means)
    z = (real_day.mean() - nm.mean()) / nm.std() if nm.std() > 0 else np.inf
    mach = (nm.mean() / real_day.mean()) if real_day.mean() != 0 else np.nan
    return dict(name=name, summ=summ, hw=hw, real_day=real_day.mean(),
                real_gross=real["points"].mean(),
                null_day_mean=nm.mean(), null_day_std=nm.std(),
                null_gross=float(np.mean(null_gross)), z=z, mach=mach, n=len(real))


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    n_null = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    cost = 2.25 / POINT_VALUE[inst] + 0.50 * TICK[inst]
    seeds = [1000 + s for s in range(n_null)]

    bars = load_rth(inst)
    print(f"=== {inst} lookback={lookback} vol-band A/B  Null-C x{n_null} "
          f"(cost={cost:.4f}pt/side) ===", flush=True)
    print(f"sessions={bars['date'].nunique()} "
          f"{bars['date'].min().date()}->{bars['date'].max().date()}", flush=True)
    print(f"REAL diffusivity |next_open-close| median = {diffusivity(bars):.4f} pt\n",
          flush=True)

    base_bands = noise_bands(bars, lookback)
    base_hw = median_halfwidth(base_bands)
    base_tpd = len(run(bars, base_bands)) / bars["date"].nunique()

    # v3: match median half-width via one scalar
    v3_scale = base_hw / median_halfwidth(noise_bands_volshare(bars, lookback, 1.0))
    # v2: match trades/day via mult
    print(f"width-match target: base half-width={base_hw:.2f}pt, base tpd={base_tpd:.3f}",
          flush=True)
    print(f"  v3_share scale={v3_scale:.4f}", flush=True)
    v2_mult = tune_mult_for_freq(bars, base_tpd)
    print(f"  v2_vwap freq-matched mult={v2_mult:.3f}\n", flush=True)

    builders = {
        "base":     lambda b: noise_bands(b, lookback),
        "v3_share": lambda b: noise_bands_volshare(b, lookback, scale=v3_scale),
        "v2_vwap":  lambda b: vwap_sigma_bands(b, mult=v2_mult),
    }

    results = {}
    for name, fn in builders.items():
        print(f"[{name}] running real + {n_null} nulls...", flush=True)
        results[name] = run_variant(name, bars, fn, inst, cost, seeds)

    print("\n--- REAL (net at mid cost) ---", flush=True)
    for name in builders:
        print(fmt(results[name]["summ"]), flush=True)

    print("\n--- NULL-C (machinery) ---", flush=True)
    print(f"{'variant':<10s} {'hw_pt':>7s} {'real$':>8s} {'null$':>8s} "
          f"{'null_sd':>8s} {'z':>7s} {'mach%':>7s} {'realGr':>8s} {'nullGr':>8s}",
          flush=True)
    for name in builders:
        r = results[name]
        print(f"{name:<10s} {r['hw']:>7.2f} {r['real_day']:>8.1f} "
              f"{r['null_day_mean']:>8.1f} {r['null_day_std']:>8.1f} "
              f"{r['z']:>+7.2f} {r['mach']*100:>6.1f}% "
              f"{r['real_gross']:>+8.3f} {r['null_gross']:>+8.3f}", flush=True)


if __name__ == "__main__":
    main()
