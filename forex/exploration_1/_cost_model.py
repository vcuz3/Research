"""Parametrised, causal, time-of-day-conditioned round-trip cost for spot FX.

No bid/ask feed exists in this project: the data are midpoint OHLC with
``volume == -1`` throughout (see MEMORY.md). Every prior report therefore stops
at the same wall -- the real spread has never been measured -- and the whole
GO/NO-GO flips between a 0.2 pip round trip (net positive) and 0.5 pip (net
negative). Because the number is unknown, the honest object is not a single net
figure but a CURVE over cost plus a BREAKEVEN pip. This module supplies the cost
side of that curve.

Nothing here is measured. Every constant is a declared MODELLING ASSUMPTION, and
the runs that consume it sweep the ``scenario`` and report the breakeven round
trip so the reader sees exactly how much spread the edge can survive.

The round trip is built as::

    round_trip_pips = 2 * half_spread_eff + commission_pips

    half_spread_eff = HALF_SPREAD_BASE[pair]
                      * HOUR_MULT[utc_hour]          # liquidity by time of day
                      * ERA_MULT[era]                # spreads compressed 2012->2023
                      * SCENARIO_MULT[scenario]      # optimistic / base / pessimistic
                      * (1 + VOL_BETA * (vol_ratio - 1))   # rule 19: widen with vol

``vol_ratio`` is the trade's realised volatility divided by the pair's own median
(a value of 1.0 disables the vol term). A market round trip crosses the spread
once (half on entry, half on exit -> one full spread == ``2 * half_spread``), then
pays commission both sides.

Design choices worth stating because they drive the verdict:

* The tightest hours are the 12:00-16:00 UTC London/NY overlap; the widest is the
  ~21:00 UTC FX rollover (17:00 New York), where liquidity is thinnest. This
  MATTERS because this project's edge concentrates in the 16:00-24:00 UTC block --
  i.e. partly in exactly the hours the model prices as most expensive.
* Commission is FTMO-style: a per-side, per-standard-lot USD charge converted to
  pips at the pair's pip value. On EURUSD one pip is ~$10/lot, so a $3.5/side
  commission is ~0.7 pip round trip -- a large, honest cost that a spread-only
  model would hide.
* The vol term (rule 19) makes a flat pip cost consume a *smaller* share of a
  large move but a *larger* absolute pip amount when volatility is high; since the
  edge lives in high-vol states, omitting it would flatter those states.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# --- Assumptions (pips unless noted) -----------------------------------------

# Typical raw half-spread in the tightest hour, base scenario, late era. EURUSD is
# the tightest major; GBP/AUD/NZD are progressively wider. (Modelling assumption.)
HALF_SPREAD_BASE = {
    "EURUSD": 0.05,
    "GBPUSD": 0.09,
    "AUDUSD": 0.10,
    "NZDUSD": 0.15,
}

# Multiplier on the half-spread by UTC hour. 1.0 at the London/NY overlap; a broad
# liquidity smile rising into the Asia session and peaking at the 21:00 rollover.
HOUR_MULT = np.array([
    3.0,  # 00
    2.5,  # 01
    2.5,  # 02
    2.5,  # 03
    2.5,  # 04
    2.2,  # 05
    1.8,  # 06
    1.4,  # 07  London open
    1.2,  # 08
    1.1,  # 09
    1.1,  # 10
    1.05, # 11
    1.0,  # 12  overlap
    1.0,  # 13
    1.0,  # 14
    1.0,  # 15
    1.1,  # 16  London close
    1.2,  # 17
    1.3,  # 18
    1.5,  # 19
    2.0,  # 20
    5.0,  # 21  FX rollover (17:00 NY) -- thinnest liquidity
    4.0,  # 22
    3.5,  # 23
], dtype=float)

# Spreads were structurally wider in the early era; compression by the late era.
ERA_MULT = {"early": 1.5, "late": 1.0}

# Whole-model scenario multiplier on the half-spread.
SCENARIO_MULT = {"optimistic": 0.7, "base": 1.0, "pessimistic": 1.5}

# Elasticity of the half-spread to realised volatility (rule 19). At twice the
# median vol (vol_ratio == 2) the half-spread is (1 + VOL_BETA) times wider.
VOL_BETA = 0.5

# FTMO-style commission, USD per side per standard (100k) lot, and the pip value
# in USD per standard lot for each pair (all quote USD, so ~$10/pip).
COMMISSION_USD_PER_SIDE = 3.5
PIP_VALUE_USD = {p: 10.0 for p in HALF_SPREAD_BASE}


@dataclass(frozen=True)
class CostParams:
    """A single point in the cost-assumption space, swept by the runs."""

    scenario: str = "base"
    include_commission: bool = True
    include_vol: bool = True
    commission_usd_per_side: float = COMMISSION_USD_PER_SIDE
    vol_beta: float = VOL_BETA


def commission_pips(pair: str, usd_per_side: float = COMMISSION_USD_PER_SIDE) -> float:
    """Round-trip commission in pips (both sides) at the pair's pip value."""
    return 2.0 * usd_per_side / PIP_VALUE_USD[pair]


def half_spread_pips(pair, utc_hour, era, vol_ratio=1.0, params: CostParams = CostParams()):
    """Effective one-side half-spread in pips. Scalars or numpy arrays.

    ``utc_hour`` is an integer 0-23 (or array); ``era`` is 'early'/'late' (or an
    array of them); ``vol_ratio`` is realised vol / pair-median (>=0).
    """
    hour = np.asarray(utc_hour)
    base = HALF_SPREAD_BASE[pair]
    hmult = HOUR_MULT[hour.astype(int)]

    era_arr = np.asarray(era)
    if era_arr.ndim == 0:
        emult = ERA_MULT[str(era_arr)]
    else:
        emult = np.where(era_arr == "early", ERA_MULT["early"], ERA_MULT["late"])

    smult = SCENARIO_MULT[params.scenario]

    if params.include_vol:
        vr = np.asarray(vol_ratio, float)
        vfac = 1.0 + params.vol_beta * (vr - 1.0)
        vfac = np.maximum(vfac, 0.1)   # a spread never goes to zero or negative
    else:
        vfac = 1.0

    return base * hmult * emult * smult * vfac


def round_trip_pips(pair, utc_hour, era, vol_ratio=1.0, params: CostParams = CostParams()):
    """Modelled round-trip cost in pips: full spread once plus round-trip commission."""
    spread = 2.0 * half_spread_pips(pair, utc_hour, era, vol_ratio, params)
    comm = commission_pips(pair, params.commission_usd_per_side) if params.include_commission else 0.0
    return spread + comm


def vol_ratio_from_frame(d, pair_median_sigma):
    """Per-trade realised-vol ratio from a trade frame's ``sigma_pips`` column.

    ``pair_median_sigma`` is the median ``sigma_pips`` over the pair's own trades,
    computed once causally-agnostic (it is a scale reference, not a signal), so
    the vol term is a *shape* over trades rather than an absolute level.
    """
    sig = np.asarray(d["sigma_pips"], float)
    if not np.isfinite(pair_median_sigma) or pair_median_sigma <= 0:
        return np.ones_like(sig)
    return sig / pair_median_sigma


def utc_hour_of(d):
    """UTC hour array for a trade frame carrying a tz-aware ``time`` column."""
    return d["time"].dt.tz_convert("UTC").dt.hour.to_numpy()
