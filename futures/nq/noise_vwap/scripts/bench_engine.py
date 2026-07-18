"""
Parity + benchmark harness for the Numba port of the Noise-Area + VWAP engine.

  python -m futures.nq.noise_vwap.scripts.bench_engine parity   # exact trade equality
  python -m futures.nq.noise_vwap.scripts.bench_engine bench     # timing + 1s scaling

`parity` runs the pandas engine (core.engine2) and the Numba engine
(core.engine2_nb) on an identical set of configs spanning every behavioural axis
and asserts the trade frames are equal to float tolerance. `bench` times both on
the full NQ history and projects the expected cost at 1-second resolution.
"""
from __future__ import annotations

import sys
import time
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E_PD
from ..core import engine2_nb as E_NB


# --------------------------------------------------------------------------- #
def _prep(inst="NQ"):
    """Load RTH + ETH sessions, their bands, and attach a synthetic causal EMA
    (for the trend_gate axis) and an entry-gate set (for the Design-C axis)."""
    out = {}
    for sess in ("RTH", "ETH"):
        bars = S.load_session(inst, sess)
        bands = S.noise_bands(bars, 90)
        # synthetic causal EMA: strictly-prior per-session rolling mean of close.
        # Economically irrelevant -- it only has to exercise the finite/NaN branches
        # of the gate identically in both engines.
        bars = bars.sort_values(["sdate", "mfo"]).reset_index(drop=True)
        ema = (bars.groupby("sdate")["close"].transform(
            lambda s: s.shift(1).rolling(20, min_periods=20).mean()))
        bars["ema"] = ema.to_numpy()
        out[sess] = (bars, bands)
    return out


def _configs(data):
    """A grid touching every feature axis the engine supports."""
    max_rth = int(data["RTH"][0]["mfo"].max())
    max_eth = int(data["ETH"][0]["mfo"].max())
    dm = lambda p, mx: S.decision_mfos(p, mx)

    # an entry gate = keep only ~60% of RTH decision (date, mfo) signal bars
    rbars = data["RTH"][0]
    dset = set(dm(30, max_rth))
    dec = rbars[rbars["mfo"].isin(dset)][["sdate", "mfo"]]
    rng = np.random.default_rng(0)
    keep = rng.random(len(dec)) < 0.6
    gate = set(map(tuple, dec.to_numpy()[keep]))

    C = []
    C.append(("RTH clock30 baseline", "RTH", dict(decision_mfos=dm(30, max_rth))))
    C.append(("RTH clock5", "RTH", dict(decision_mfos=dm(5, max_rth))))
    C.append(("RTH clock15", "RTH", dict(decision_mfos=dm(15, max_rth))))
    C.append(("RTH clock60", "RTH", dict(decision_mfos=dm(60, max_rth))))
    C.append(("ETH clock30", "ETH", dict(decision_mfos=dm(30, max_eth))))
    C.append(("RTH clk30 every_bar", "RTH", dict(decision_mfos=dm(30, max_rth), exit_check="every_bar")))
    C.append(("ETH clk30 every_bar", "ETH", dict(decision_mfos=dm(30, max_eth), exit_check="every_bar")))
    C.append(("RTH signal_close fill", "RTH", dict(decision_mfos=dm(30, max_rth), fill_mode="signal_close")))
    C.append(("RTH no-vwap gate", "RTH", dict(decision_mfos=dm(30, max_rth), require_vwap=False)))
    C.append(("RTH threshold X=0.0", "RTH", dict(decision_mfos=dm(30, max_rth), entry_mode="threshold",
                                                 entry_buf_atr=0.0, exit_check="every_bar")))
    C.append(("RTH threshold X=0.25", "RTH", dict(decision_mfos=dm(30, max_rth), entry_mode="threshold",
                                                  entry_buf_atr=0.25, exit_check="every_bar")))
    C.append(("RTH threshold persist=3", "RTH", dict(decision_mfos=dm(30, max_rth), entry_mode="threshold",
                                                     entry_buf_atr=0.10, entry_persist=3, exit_check="every_bar")))
    C.append(("RTH threshold sig_close", "RTH", dict(decision_mfos=dm(30, max_rth), entry_mode="threshold",
                                                    entry_buf_atr=0.25, exit_check="every_bar",
                                                    fill_mode="signal_close")))
    C.append(("RTH delay=5", "RTH", dict(decision_mfos=dm(30, max_rth), entry_mode="delay",
                                         entry_buf_atr=0.10, entry_delay=5, exit_check="every_bar")))
    C.append(("RTH delay=10", "RTH", dict(decision_mfos=dm(30, max_rth), entry_mode="delay",
                                          entry_buf_atr=0.0, entry_delay=10, exit_check="every_bar")))
    C.append(("RTH partial tp1.0_50", "RTH", dict(decision_mfos=dm(30, max_rth), exit_check="every_bar",
                                                  tp_atr=1.0, tp_frac=0.5)))
    C.append(("RTH partial tp0.75_67", "RTH", dict(decision_mfos=dm(30, max_rth), exit_check="every_bar",
                                                   tp_atr=0.75, tp_frac=0.67)))
    C.append(("RTH break-even be1.0", "RTH", dict(decision_mfos=dm(30, max_rth), exit_check="every_bar",
                                                  be_atr=1.0)))
    C.append(("RTH trail 1.0/1.0", "RTH", dict(decision_mfos=dm(30, max_rth), exit_check="every_bar",
                                               trail_step_atr=1.0, trail_start_atr=1.0)))
    C.append(("RTH trail 0.5/1.5", "RTH", dict(decision_mfos=dm(30, max_rth), exit_check="every_bar",
                                               trail_step_atr=0.5, trail_start_atr=1.5)))
    C.append(("RTH stop_ref vwap", "RTH", dict(decision_mfos=dm(30, max_rth), stop_ref="vwap")))
    C.append(("RTH stop_ref band", "RTH", dict(decision_mfos=dm(30, max_rth), stop_ref="band")))
    C.append(("RTH stop_buf +0.25", "RTH", dict(decision_mfos=dm(30, max_rth), stop_buf_atr=0.25)))
    C.append(("RTH stop_buf -0.25", "RTH", dict(decision_mfos=dm(30, max_rth), stop_buf_atr=-0.25)))
    C.append(("RTH trend_gate", "RTH", dict(decision_mfos=dm(30, max_rth), trend_gate=True)))
    C.append(("RTH entry_gate", "RTH", dict(decision_mfos=dm(30, max_rth), entry_gate=gate)))
    C.append(("RTH combo tp+trail+be", "RTH", dict(decision_mfos=dm(30, max_rth), exit_check="every_bar",
                                                   tp_atr=1.0, tp_frac=0.5, be_atr=1.5,
                                                   trail_step_atr=0.75, trail_start_atr=1.0)))
    return C


def _assert_equal(name, a: pd.DataFrame, b: pd.DataFrame):
    if a.empty and b.empty:
        print(f"  OK  {name:<28s} (0 trades)")
        return True
    if a.empty != b.empty:
        print(f"  FAIL {name:<28s} one empty: pd={len(a)} nb={len(b)}")
        return False
    a = a.reset_index(drop=True)
    b = b.reset_index(drop=True)[a.columns]
    try:
        pd.testing.assert_frame_equal(a, b, check_dtype=False, rtol=0, atol=1e-9)
        print(f"  OK  {name:<28s} n={len(a):>5d}  gross={a['points'].mean():+.4f}")
        return True
    except AssertionError as e:
        print(f"  FAIL {name:<28s}\n{str(e)[:600]}")
        return False


def parity():
    data = _prep("NQ")
    print("=== PARITY: core.engine2 (pandas) vs core.engine2_nb (numba) ===")
    print(f"RTH bars={len(data['RTH'][0])} sessions={data['RTH'][0]['sdate'].nunique()} | "
          f"ETH bars={len(data['ETH'][0])} sessions={data['ETH'][0]['sdate'].nunique()}")
    ok_all = True
    for name, sess, kw in _configs(data):
        bars, bands = data[sess]
        t_pd = E_PD.run(bars, bands, **kw)
        t_nb = E_NB.run(bars, bands, **kw)
        ok_all &= _assert_equal(name, t_pd, t_nb)
    print("\nALL PARITY PASSED" if ok_all else "\n*** PARITY FAILURES ***")
    return ok_all


# --------------------------------------------------------------------------- #
def _time(fn, n=3):
    best = np.inf
    out = None
    for _ in range(n):
        t0 = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t0)
    return best, out


def bench():
    data = _prep("NQ")
    bars, bands = data["RTH"]
    max_rth = int(bars["mfo"].max())
    dm = S.decision_mfos(30, max_rth)
    nbars = len(bars)
    nsess = bars["sdate"].nunique()

    # a config that exercises the full exit machinery every bar (worst case)
    kw = dict(decision_mfos=dm, exit_check="every_bar",
              tp_atr=1.0, tp_frac=0.5, trail_step_atr=0.75, trail_start_atr=1.0, be_atr=1.5)

    print("=== BENCHMARK (NQ RTH, every-bar exit + tp + trail + be) ===")
    print(f"bars={nbars:,}  sessions={nsess:,}  (~{nbars/nsess:.0f} 1-min bars/session)\n")

    # warm the JIT (compile) first, off the clock
    _ = E_NB.run(bars, bands, **kw)

    t_pd, r_pd = _time(lambda: E_PD.run(bars, bands, **kw))
    t_nb, r_nb = _time(lambda: E_NB.run(bars, bands, **kw))

    assert len(r_pd) == len(r_nb), (len(r_pd), len(r_nb))
    print(f"pandas  engine2   : {t_pd*1000:8.1f} ms   ({nbars/t_pd/1e6:6.2f} M bars/s)")
    print(f"numba   engine2_nb: {t_nb*1000:8.1f} ms   ({nbars/t_nb/1e6:6.2f} M bars/s)")
    print(f"speedup           : {t_pd/t_nb:6.1f}x   (trades: {len(r_pd)})")

    # split the numba time into preprocessing (pandas, vectorized) vs the kernel,
    # since only the kernel scales with bar count the same way the pandas loop does.
    print("\n--- 1-SECOND SCALING PROJECTION ---")
    per_bar_pd = t_pd / nbars
    per_bar_nb = t_nb / nbars
    # 1s data at ~60x the bar count. RTH session = 6.5h = 23,400 s-bars vs 390 m-bars.
    factor = 60.0
    nbars_1s = nbars * factor
    print(f"1-min bars: {nbars:,}   ->  1-sec bars (x60): {int(nbars_1s):,}")
    print(f"pandas  projected @1s: {per_bar_pd*nbars_1s:8.2f} s   "
          f"(linear in bars; Python per-bar overhead dominates)")
    print(f"numba   projected @1s: {per_bar_nb*nbars_1s:8.3f} s   "
          f"(kernel is O(bars), branch-light; JIT compile is one-off)")
    print("\nNote: both engines are O(bars), so the projection scales linearly and the "
          "measured\nspeedup (~{:.0f}x) holds at 1s -- the win is the CONSTANT: pandas "
          "runs an interpreted\nPython loop with a per-session dict+closure, numba runs "
          "one compiled pass over flat\narrays. That turns a ~{:.0f}-min 1s backtest into "
          "~{:.0f}s, which is what makes a 1s\nparameter sweep tractable at all. (A sweep "
          "can go further: the pandas preprocessing\n-- band merge / ffill / factorize -- "
          "is identical across configs and can be hoisted\nout of the loop so only the "
          "kernel re-runs.)".format(
              t_pd / t_nb, per_bar_pd * nbars_1s / 60.0, per_bar_nb * nbars_1s))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "parity"
    if cmd == "parity":
        ok = parity()
        sys.exit(0 if ok else 1)
    elif cmd == "bench":
        bench()
    else:
        print("usage: bench_engine.py [parity|bench]")


if __name__ == "__main__":
    main()
