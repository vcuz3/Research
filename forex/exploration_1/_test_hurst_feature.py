"""Unit tests for the generalized Hurst feature (correctness + causality)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _hurst_feature import HURST_WIN, TAUS, generalized_hurst

CHECKS = []


def check(name, ok):
    CHECKS.append((name, bool(ok)))
    print(f"   [{'PASS' if ok else 'FAIL'}] {name}")


def contiguous_time(n, start="2015-06-01 08:00"):
    return pd.Series(pd.date_range(start, periods=n, freq="1min", tz="UTC"))


def main():
    n = 800
    time = contiguous_time(n)
    interior = slice(HURST_WIN + max(TAUS) + 5, n)   # rows with a fully-populated window

    # --- linear ramp: |increment| ~ tau, slope of log-log == 1 -> H == 1 ---
    ramp = pd.Series(np.arange(n) * 1e-4)
    h_ramp = generalized_hurst(ramp, time)
    check("H == 1 on a linear ramp (deterministic)",
          np.allclose(h_ramp.iloc[interior].to_numpy(), 1.0, atol=1e-6))

    # --- random walk: increments iid, H ~ 0.5 ---
    rng = np.random.default_rng(0)
    rw = pd.Series(np.cumsum(rng.standard_normal(n)) * 1e-4)
    h_rw_series = generalized_hurst(rw, time)
    h_rw = float(np.nanmean(h_rw_series.iloc[interior].to_numpy()))
    check(f"H ~ 0.5 on a random walk (got {h_rw:.3f})", abs(h_rw - 0.5) < 0.07)

    # --- anti-persistent: iid LEVEL (not integrated) -> |increment| flat in tau -> H << 0.5 ---
    noise = pd.Series(rng.standard_normal(n) * 1e-4)
    h_ap = float(np.nanmean(generalized_hurst(noise, time).iloc[interior].to_numpy()))
    check(f"H << 0.5 on an iid level / anti-persistent series (got {h_ap:.3f})", h_ap < 0.30)

    # --- persistent: drift-dominated -> H > 0.5 ---
    trend = pd.Series(np.arange(n) * 5e-5 + np.cumsum(rng.standard_normal(n)) * 1e-5)
    h_tr = float(np.nanmean(generalized_hurst(trend, time).iloc[interior].to_numpy()))
    check(f"H > 0.5 on a drift-dominated series (got {h_tr:.3f})", h_tr > 0.55)

    # --- causality: a future bar cannot change a past H ---
    rw2 = rw.copy()
    rw2.iloc[600] += 10.0
    h2 = generalized_hurst(rw2, time)
    check("H causal: bars < 600 - max(tau) unchanged when bar 600 is perturbed",
          np.allclose(h_rw_series.iloc[:600 - max(TAUS)].to_numpy(),
                      h2.iloc[:600 - max(TAUS)].to_numpy(), atol=1e-10, equal_nan=True))

    # --- undefined across a session gap ---
    tg = time.copy()
    tg.iloc[400:] = tg.iloc[400:] + pd.Timedelta(minutes=90)     # a 90-min hole before 400
    hg = generalized_hurst(ramp, tg)
    check("H is NaN for the first HURST_WIN bars after a gap",
          bool(hg.iloc[400:400 + HURST_WIN].isna().all()))

    # --- undefined until the window is first populated ---
    check("H is NaN before the trailing window is full",
          bool(generalized_hurst(ramp, time).iloc[:HURST_WIN].isna().all()))

    n_pass = sum(ok for _, ok in CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} checks passed")
    if n_pass != len(CHECKS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
