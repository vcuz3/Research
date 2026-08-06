"""Executable checks on the compulsory-stop simulation before either arm runs.

An error here would silently corrupt both arms, so the fill rules that RULES.md
3 and 5 actually turn on are pinned with hand-computed cases.

Run:  python -u _test_rsi_stop_engine.py
"""

from __future__ import annotations

import numpy as np

from _rsi_stop_engine import PIP, drawdown_R, simulate

FAILURES = []


def check(name, got, want, tol=1e-9):
    ok = np.allclose(np.asarray(got, float), np.asarray(want, float), atol=tol, equal_nan=True)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got {np.round(np.asarray(got, float), 6)} "
          f"want {np.round(np.asarray(want, float), 6)}")
    if not ok:
        FAILURES.append(name)


def paths_from(rows):
    """rows: list of per-bar (open, high, low) tuples for one trade."""
    a = np.array(rows, float)[None, :, :]
    return {"open": a[:, :, 0], "high": a[:, :, 1], "low": a[:, :, 2],
            "close": a[:, :, 0]}


P = PIP
E = 1.1000

# bar 0 entry at E; bar 1 dips 12 pips; bar 2 back up; bar 3 is the exit open
DIP = paths_from([
    (E,          E + 2 * P,  E - 1 * P),
    (E + 1 * P,  E + 1 * P,  E - 12 * P),
    (E,          E + 3 * P,  E - 2 * P),
    (E + 5 * P,  E + 5 * P,  E + 5 * P),
])
side_long = np.array([1.0])
side_short = np.array([-1.0])

# 1. no stop: pure open-to-open
pnl, stopped, _ = simulate(DIP, side_long, np.inf, 3)
check("no stop, long, exit at bar 3", pnl, [5.0])
check("no stop never stops", stopped.astype(float), [0.0])

# 2. stop at 10 pips is breached by bar 1's low of -12; fill AT the level
pnl, stopped, bar = simulate(DIP, side_long, 10.0, 3)
check("10-pip stop fills at the level", pnl, [-10.0])
check("stop bar index", bar.astype(float), [1.0])

# 3. stop at 15 pips is not reached
pnl, stopped, _ = simulate(DIP, side_long, 15.0, 3)
check("15-pip stop survives", pnl, [5.0])

# 4. rule 5 gap-through: a bar that OPENS beyond the stop fills at that open
GAP = paths_from([
    (E,          E + 1 * P,  E - 1 * P),
    (E - 18 * P, E - 17 * P, E - 25 * P),   # opens 18 pips down, stop is at 10
    (E,          E + 1 * P,  E - 1 * P),
    (E,          E,          E),
])
pnl, _, _ = simulate(GAP, side_long, 10.0, 3)
check("gap-through fills at the open, not the stop", pnl, [-18.0])

# 5. slippage is adverse on top of the fill
pnl, _, _ = simulate(DIP, side_long, 10.0, 3, slippage_pips=1.0)
check("1-pip slippage on a level fill", pnl, [-11.0])
pnl, _, _ = simulate(GAP, side_long, 10.0, 3, slippage_pips=1.0)
check("1-pip slippage on a gap fill", pnl, [-19.0])

# 6. short side mirrors exactly
SHORT = paths_from([
    (E,          E + 1 * P,  E - 2 * P),
    (E,          E + 12 * P, E - 1 * P),    # 12 pips against a short
    (E,          E + 1 * P,  E - 1 * P),
    (E - 5 * P,  E - 5 * P,  E - 5 * P),
])
pnl, _, _ = simulate(SHORT, side_short, np.inf, 3)
check("no stop, short", pnl, [5.0])
pnl, _, _ = simulate(SHORT, side_short, 10.0, 3)
check("short stop fills at the level", pnl, [-10.0])

# 7. the exit bar is NOT lived through: a breach at bar N must not stop a trade
#    that exits at open(N)
LATE = paths_from([
    (E,          E + 1 * P,  E - 1 * P),
    (E + 2 * P,  E + 3 * P,  E + 1 * P),
    (E + 4 * P,  E + 4 * P,  E - 50 * P),   # huge dip, but we exit at its OPEN
    (E,          E,          E),
])
pnl, stopped, _ = simulate(LATE, side_long, 10.0, 2)
check("breach at the exit bar does not fire", pnl, [4.0])
check("...and is not marked stopped", stopped.astype(float), [0.0])
pnl, stopped, _ = simulate(LATE, side_long, 10.0, 3)
check("the same breach fires when the trade is still live", pnl, [-10.0])

# 8. per-trade exit indices and stop distances broadcast independently
TWO = {k: np.repeat(v, 2, axis=0) for k, v in LATE.items()}
pnl, _, _ = simulate(TWO, np.array([1.0, 1.0]), np.array([10.0, 10.0]), np.array([2, 3]))
check("vector exit index", pnl, [4.0, -10.0])
pnl, _, _ = simulate(TWO, np.array([1.0, 1.0]), np.array([10.0, 60.0]), np.array([3, 3]))
check("vector stop distance", pnl, [-10.0, 0.0])

# 9. drawdown of a cumulative R curve
check("max drawdown", drawdown_R([1.0, -0.5, -0.5, 2.0]), 1.0)
check("monotone curve has no drawdown", drawdown_R([1.0, 1.0, 1.0]), 0.0)

print()
if FAILURES:
    raise SystemExit(f"{len(FAILURES)} FAILED: {FAILURES}")
print("all engine checks passed")
