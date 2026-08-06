"""Hand-computed fill checks for the triple-barrier bracket.

Pins the rule-3 adverse tiebreak, the rule-5 gap-through on both barriers, adverse
slippage on the stop only, the short-side mirror, and the timeout exit. A bracket
on coarse bars is exactly where a fake edge crept in before, so these are not
optional. Every path has width == horizon + 1 (a timeout exits at O[:, horizon]).

Run:
    python -u _test_bracket_engine.py
"""

from __future__ import annotations

import numpy as np

from _bracket_engine import simulate_bracket

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


def approx(a, b, tol=1e-6):
    return abs(float(a) - float(b)) <= tol


def path(rows):
    arr = np.array(rows, float)[None, :, :]
    return {"open": arr[:, :, 0], "high": arr[:, :, 1], "low": arr[:, :, 2]}


# 1. Pure target (long): high reaches +10 pip at bar 2, stop never touched.
p = path([(1.0000, 1.0002, 0.9999),
          (1.0001, 1.0004, 0.9999),
          (1.0005, 1.0011, 1.0003),   # target 1.0010 touched
          (1.0006, 1.0007, 1.0002)])
pnl, kind = simulate_bracket(p, [1.0], tp_dist=10, sl_dist=10, horizon=3)
check("long pure target -> +10 pip", approx(pnl[0], 10.0) and kind[0] == 1)

# 2. Pure stop (long): low reaches -10 pip at bar 1.
p = path([(1.0000, 1.0002, 0.9999),
          (0.9999, 1.0000, 0.9989),   # stop 0.9990 touched
          (0.9995, 1.0000, 0.9990)])
pnl, kind = simulate_bracket(p, [1.0], tp_dist=10, sl_dist=10, horizon=2)
check("long pure stop -> -10 pip", approx(pnl[0], -10.0) and kind[0] == -1)

# 3. Both touched in the SAME bar -> adverse tiebreak = stop.
p = path([(1.0000, 1.0002, 0.9999),
          (1.0000, 1.0011, 0.9989),   # bar1 spans target 1.0010 and stop 0.9990
          (1.0000, 1.0000, 1.0000)])
pnl, kind = simulate_bracket(p, [1.0], tp_dist=10, sl_dist=10, horizon=2)
check("both same bar -> stop (adverse)", approx(pnl[0], -10.0) and kind[0] == -1)

# 4. Gap through the stop -> fill at the (worse) open, not the stop level.
p = path([(1.0000, 1.0002, 0.9999),
          (0.9985, 0.9990, 0.9980),   # opens below stop 0.9990
          (1.0000, 1.0000, 1.0000)])
pnl, kind = simulate_bracket(p, [1.0], tp_dist=10, sl_dist=10, horizon=2)
check("gap through stop -> fill at open (-15 pip)", approx(pnl[0], -15.0) and kind[0] == -1)

# 5. Adverse slippage applies to the stop (1 pip worse).
p = path([(1.0000, 1.0002, 0.9999),
          (0.9999, 1.0000, 0.9989),
          (1.0000, 1.0000, 1.0000)])
pnl, _ = simulate_bracket(p, [1.0], tp_dist=10, sl_dist=10, horizon=2, slippage_pips=1.0)
check("stop with 1-pip slippage -> -11 pip", approx(pnl[0], -11.0))

# 5b. The target ignores slippage (passive limit).
p = path([(1.0000, 1.0002, 0.9999),
          (1.0005, 1.0011, 1.0003),
          (1.0000, 1.0000, 1.0000)])
pnl, _ = simulate_bracket(p, [1.0], tp_dist=10, sl_dist=10, horizon=2, slippage_pips=1.0)
check("target ignores slippage -> +10 pip", approx(pnl[0], 10.0))

# 6. Timeout: neither barrier touched, exit at O[:, horizon].
p = path([(1.0000, 1.0002, 0.9999),
          (1.0001, 1.0003, 0.9999),
          (1.0002, 1.0004, 1.0000),
          (1.0003, 1.0005, 1.0001)])   # O[:,3] = 1.0003 -> +3 pip
pnl, kind = simulate_bracket(p, [1.0], tp_dist=10, sl_dist=10, horizon=3)
check("timeout -> exit at open(horizon), +3 pip", approx(pnl[0], 3.0) and kind[0] == 0)

# 7. Short-side target: low reaches target below entry.
p = path([(1.0000, 1.0001, 0.9998),
          (0.9999, 1.0000, 0.9996),
          (0.9995, 0.9997, 0.9989),   # short target 0.9990 touched
          (0.9995, 0.9997, 0.9993)])
pnl, kind = simulate_bracket(p, [-1.0], tp_dist=10, sl_dist=10, horizon=3)
check("short pure target -> +10 pip", approx(pnl[0], 10.0) and kind[0] == 1)

# 8. Short-side stop: high reaches stop above entry.
p = path([(1.0000, 1.0001, 0.9998),
          (1.0001, 1.0011, 0.9999),   # short stop 1.0010 touched
          (1.0000, 1.0000, 1.0000)])
pnl, kind = simulate_bracket(p, [-1.0], tp_dist=10, sl_dist=10, horizon=2)
check("short pure stop -> -10 pip", approx(pnl[0], -10.0) and kind[0] == -1)

# 9. Asymmetric bracket tp20/sl10, long target at +20.
p = path([(1.0000, 1.0002, 0.9999),
          (1.0010, 1.0021, 1.0005),   # +20 target touched
          (1.0000, 1.0000, 1.0000)])
pnl, kind = simulate_bracket(p, [1.0], tp_dist=20, sl_dist=10, horizon=2)
check("asymmetric tp20/sl10 target -> +20 pip", approx(pnl[0], 20.0) and kind[0] == 1)

# 10. Vectorised: one target, one stop, resolved independently.
o = np.array([[1.0000, 1.0005, 1.0000],
              [1.0000, 0.9999, 1.0000]])
hi = np.array([[1.0002, 1.0011, 1.0000],
               [1.0002, 1.0000, 1.0000]])
lo = np.array([[0.9999, 1.0003, 1.0000],
               [0.9999, 0.9989, 1.0000]])
pnl, kind = simulate_bracket({"open": o, "high": hi, "low": lo},
                             [1.0, 1.0], tp_dist=10, sl_dist=10, horizon=2)
check("vectorised target+stop", approx(pnl[0], 10.0) and approx(pnl[1], -10.0)
      and kind[0] == 1 and kind[1] == -1)


if __name__ == "__main__":
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
