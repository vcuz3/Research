"""Unit tests for the directional-efficiency features (causality + correctness)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _efficiency_features import (
    ADX_LEN,
    KER_WIN,
    _rma_leading_nan,
    kaufman_er,
    wilder_adx,
)
from _run_rsi_broad_regime_sweep import recursive_wilder

CHECKS = []


def check(name, ok):
    CHECKS.append((name, bool(ok)))
    print(f"   [{'PASS' if ok else 'FAIL'}] {name}")


def contiguous_time(n, start="2015-06-01 08:00"):
    return pd.Series(pd.date_range(start, periods=n, freq="1min", tz="UTC"))


def main():
    n = 200
    time = contiguous_time(n)
    one = time.diff().eq(pd.Timedelta(minutes=1))

    # --- KER: a straight-line path is perfectly efficient (== 1) ---
    logc = pd.Series(np.arange(n) * 0.001)
    ker = kaufman_er(logc, time, KER_WIN)
    check("KER == 1.0 on a straight line (contiguous window)",
          np.allclose(ker.iloc[KER_WIN:].to_numpy(), 1.0, atol=1e-9))

    # --- KER: a zero-net zigzag is maximally inefficient (== 0) ---
    zig = pd.Series(np.where(np.arange(n) % 2 == 0, 0.0, 0.001))  # net 0 over even win
    kz = kaufman_er(zig, time, KER_WIN)
    check("KER == 0.0 on a zero-net zigzag",
          np.allclose(kz.iloc[KER_WIN::2].to_numpy(), 0.0, atol=1e-9))

    # --- KER is undefined across a session gap (exact-contiguous) ---
    tg = time.copy()
    tg.iloc[100:] = tg.iloc[100:] + pd.Timedelta(minutes=60)   # a 1h hole before 100
    kg = kaufman_er(logc, tg, KER_WIN)
    check("KER is NaN for the first KER_WIN bars after a gap",
          bool(kg.iloc[100:100 + KER_WIN].isna().all()))

    # --- KER causality: a future value cannot change a past KER ---
    logc2 = logc.copy()
    logc2.iloc[150] += 5.0
    ker2 = kaufman_er(logc2, time, KER_WIN)
    check("KER causal: bars < 150 unchanged when bar 150 is perturbed",
          np.allclose(ker.iloc[:120].to_numpy(), ker2.iloc[:120].to_numpy(),
                      atol=1e-12, equal_nan=True))

    # --- _rma_leading_nan matches recursive_wilder when there is no leading NaN ---
    x = np.abs(np.sin(np.arange(n) * 0.3)) + 0.1
    check("_rma_leading_nan == recursive_wilder with no leading NaN",
          np.allclose(_rma_leading_nan(x, one.to_numpy(), ADX_LEN),
                      recursive_wilder(x, one.to_numpy(), ADX_LEN),
                      atol=1e-12, equal_nan=True))

    # --- _rma_leading_nan skips a NaN warmup and still seeds correctly ---
    xln = x.copy()
    xln[:ADX_LEN] = np.nan                      # warmup NaNs like DX
    r = _rma_leading_nan(xln, one.to_numpy(), ADX_LEN)
    # seed lands at first_valid + length - 1 == ADX_LEN + ADX_LEN - 1
    seed_idx = ADX_LEN + ADX_LEN - 1
    check("_rma_leading_nan seeds at first-valid + length - 1",
          bool(np.isnan(r[seed_idx - 1]) and np.isfinite(r[seed_idx])
               and np.isclose(r[seed_idx], np.mean(x[ADX_LEN:2 * ADX_LEN]))))

    # --- ADX high on a clean trend, low on chop ---
    trend = np.arange(n) * 1.0
    high = trend + 0.5
    low = trend - 0.5
    close = trend
    adx_tr = wilder_adx(high, low, close, one.to_numpy(), ADX_LEN)
    check("ADX -> high (>60) on a monotone trend",
          bool(np.nanmean(adx_tr[3 * ADX_LEN:]) > 60))

    base = 100.0 + np.where(np.arange(n) % 2 == 0, 0.0, 0.3)   # oscillate, no trend
    hi_c = base + 0.5
    lo_c = base - 0.5
    adx_ch = wilder_adx(hi_c, lo_c, base, one.to_numpy(), ADX_LEN)
    check("ADX chop < ADX trend, and chop is low (<40)",
          bool(np.nanmean(adx_ch[3 * ADX_LEN:]) < 40
               and np.nanmean(adx_ch[3 * ADX_LEN:]) < np.nanmean(adx_tr[3 * ADX_LEN:])))

    # --- ADX causality: a future spike cannot change past ADX ---
    hi2, lo2, cl2 = high.copy(), low.copy(), close.copy()
    hi2[170] += 50
    lo2[170] += 50
    cl2[170] += 50
    adx_tr2 = wilder_adx(hi2, lo2, cl2, one.to_numpy(), ADX_LEN)
    check("ADX causal: bars < 170 unchanged when bar 170 is perturbed",
          np.allclose(adx_tr[:150], adx_tr2[:150], atol=1e-10, equal_nan=True))

    # --- ADX resets per session (does not smooth across a gap) ---
    two_sessions = one.to_numpy().copy()
    two_sessions[100] = False                    # start a new session at 100
    adx_split = wilder_adx(high, low, close, two_sessions, ADX_LEN)
    check("ADX is NaN in the warmup of a new session after a reset",
          bool(np.isnan(adx_split[100])))

    n_pass = sum(ok for _, ok in CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} checks passed")
    if n_pass != len(CHECKS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
