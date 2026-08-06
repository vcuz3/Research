"""Hand-computed checks for the modelled FX round-trip cost.

The cost model decides the whole GO/NO-GO, so its properties are pinned here:
monotonic in spread drivers (hour, era, scenario, vol), commission additive and
correctly converted, vectorised path identical to the scalar path, and the pairs
ordered EURUSD < GBPUSD < AUDUSD < NZDUSD. Nothing is measured; these assert the
model behaves as its docstring claims.

Run:
    python -u _test_cost_model.py
"""

from __future__ import annotations

import numpy as np

from _cost_model import (
    COMMISSION_USD_PER_SIDE,
    CostParams,
    HALF_SPREAD_BASE,
    HOUR_MULT,
    commission_pips,
    half_spread_pips,
    round_trip_pips,
)

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


def approx(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


# 1. Commission conversion: $3.5/side on EURUSD ($10/pip) -> 0.70 pip round trip.
check("commission $3.5/side EURUSD == 0.70 pip",
      approx(commission_pips("EURUSD", 3.5), 0.70))

# 2. Rollover (21 UTC) is more expensive than the overlap (14 UTC), same else.
p = CostParams(include_commission=False, include_vol=False)
check("rollover hour 21 dearer than overlap hour 14",
      round_trip_pips("EURUSD", 21, "late", params=p)
      > round_trip_pips("EURUSD", 14, "late", params=p))

# 3. Scenario ordering optimistic < base < pessimistic.
opt = round_trip_pips("EURUSD", 14, "late", params=CostParams(scenario="optimistic",
                                                              include_commission=False, include_vol=False))
bas = round_trip_pips("EURUSD", 14, "late", params=CostParams(scenario="base",
                                                              include_commission=False, include_vol=False))
pes = round_trip_pips("EURUSD", 14, "late", params=CostParams(scenario="pessimistic",
                                                              include_commission=False, include_vol=False))
check("optimistic < base < pessimistic", opt < bas < pes)

# 4. Era: early spreads wider than late.
early = round_trip_pips("EURUSD", 14, "early", params=p)
late = round_trip_pips("EURUSD", 14, "late", params=p)
check("early era dearer than late era", early > late)

# 5. Vol term: higher vol_ratio -> higher cost when enabled, and IGNORED when off.
pv = CostParams(include_commission=False, include_vol=True)
lo = round_trip_pips("EURUSD", 14, "late", vol_ratio=1.0, params=pv)
hi = round_trip_pips("EURUSD", 14, "late", vol_ratio=2.0, params=pv)
check("cost rises with vol_ratio when include_vol", hi > lo)
off1 = round_trip_pips("EURUSD", 14, "late", vol_ratio=1.0, params=p)
off2 = round_trip_pips("EURUSD", 14, "late", vol_ratio=9.0, params=p)
check("vol_ratio ignored when include_vol=False", approx(off1, off2))

# 6. Vol factor is floored so an extreme low vol_ratio never yields a <=0 spread.
neg = half_spread_pips("EURUSD", 14, "late", vol_ratio=-100.0, params=pv)
check("half-spread stays positive under absurd vol_ratio", float(neg) > 0)

# 7. Commission is additive: with-commission == without + round-trip commission.
with_c = round_trip_pips("EURUSD", 14, "late",
                         params=CostParams(include_commission=True, include_vol=False))
without_c = round_trip_pips("EURUSD", 14, "late",
                            params=CostParams(include_commission=False, include_vol=False))
check("commission additive",
      approx(with_c, without_c + commission_pips("EURUSD", COMMISSION_USD_PER_SIDE)))

# 8. Round trip is exactly twice the half-spread plus commission (spread crossed once).
hs = half_spread_pips("EURUSD", 14, "late", params=p)
check("round trip == 2*half_spread + commission",
      approx(round_trip_pips("EURUSD", 14, "late",
                             params=CostParams(include_commission=True, include_vol=False)),
             2.0 * float(hs) + commission_pips("EURUSD", COMMISSION_USD_PER_SIDE)))

# 9. Pair ordering EURUSD < GBPUSD < AUDUSD < NZDUSD at identical conditions.
costs = [round_trip_pips(pair, 14, "late", params=p)
         for pair in ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]]
check("pair cost ordering EUR<GBP<AUD<NZD",
      costs[0] < costs[1] < costs[2] < costs[3])

# 10. Vectorised path matches the scalar path element-by-element.
hours = np.array([0, 7, 14, 21])
eras = np.array(["early", "late", "late", "early"])
vrs = np.array([0.5, 1.0, 2.0, 3.0])
vec = round_trip_pips("GBPUSD", hours, eras, vol_ratio=vrs, params=pv)
scal = np.array([
    float(round_trip_pips("GBPUSD", int(h), str(e), vol_ratio=float(v), params=pv))
    for h, e, v in zip(hours, eras, vrs)
])
check("vectorised == scalar loop", np.allclose(np.asarray(vec, float), scal))

# 11. Sanity on magnitudes: base EURUSD overlap round trip is a plausible sub-pip
#     spread plus the 0.70 pip commission (i.e. dominated by commission).
base_eur = float(round_trip_pips("EURUSD", 14, "late",
                                 params=CostParams(include_commission=True, include_vol=False)))
check("base EURUSD overlap round trip in (0.7, 1.0) pip",
      0.70 < base_eur < 1.0)

# 12. HOUR_MULT is well-formed: 24 entries, min at an overlap hour, max at rollover.
check("HOUR_MULT has 24 entries", HOUR_MULT.shape == (24,))
check("HOUR_MULT min at overlap (12-15)", int(np.argmin(HOUR_MULT)) in (12, 13, 14, 15))
check("HOUR_MULT max at rollover hour 21", int(np.argmax(HOUR_MULT)) == 21)


if __name__ == "__main__":
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
