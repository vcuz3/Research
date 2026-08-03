"""When is the COUNTER CURRENCY's own home market open?

The hypothesis under test (HYP-0007) is that this project's reversion sits where
the dealers who warehouse the non-USD leg are absent -- not in a fixed ET block.
Every contract here is quoted against USD on a US venue, so the USD leg and the
venue calendar are common to all seven; the only thing that varies across products
is the *other* currency's home time zone.  That is the lever.

Definition, chosen to have NO free parameters
---------------------------------------------
The home market is open **08:00-17:00 local time, Monday-Friday**, the same nine
hours for every product.  A per-product schedule (Tokyo's lunch break, London's
16:30 equity close, Sydney's summer hours) would be more realistic and would also
be seven free parameters fitted by hand to the very products under test, so it is
deliberately not used.  If the effect only appears under a tuned schedule it is
not the effect claimed.

The clock is derived from each currency's OWN time zone with real DST, never from
a fixed ET offset.  This matters: Tokyo does not observe DST while New York does,
so the Tokyo-ET offset moves by an hour twice a year, and the northern and
southern hemispheres shift in opposite directions.  Hardcoding an offset already
cost this workspace a 35% understatement on the London fix (LEARNINGS 2026-08-02).

`openness(product, block)` is then the fraction of that product's decisions in
that ET block for which the home market was open -- a number in [0, 1] computed
from the decision timestamps themselves, so it reflects the actual sample.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# currency -> (home time zone, human label)
HOME = {
    "6E": ("Europe/Berlin", "Frankfurt (EUR)"),
    "6B": ("Europe/London", "London (GBP)"),
    "6J": ("Asia/Tokyo", "Tokyo (JPY)"),
    "6A": ("Australia/Sydney", "Sydney (AUD)"),
    "6C": ("America/Toronto", "Toronto (CAD)"),
    "6N": ("Pacific/Auckland", "Wellington (NZD)"),
    "6S": ("Europe/Zurich", "Zurich (CHF)"),
}

OPEN_HOUR, CLOSE_HOUR = 8, 17


def is_home_open(ts_utc: pd.Series, product: str) -> np.ndarray:
    """True where the home market is open at each UTC timestamp.

    `ts_utc` must be tz-aware UTC. Converted with real DST via the home zone.
    """
    tz, _ = HOME[product]
    loc = pd.to_datetime(ts_utc).dt.tz_convert(tz)
    hh = loc.dt.hour + loc.dt.minute / 60.0
    return ((loc.dt.dayofweek < 5)
            & (hh >= OPEN_HOUR) & (hh < CLOSE_HOUR)).to_numpy()


def openness_by_block(panel: pd.DataFrame, product: str,
                      ts_col: str = "et") -> pd.Series:
    """Fraction of each ET block's decisions during which the home market is open."""
    ts = pd.to_datetime(panel[ts_col]).dt.tz_convert("UTC")
    op = is_home_open(ts, product)
    return pd.Series(op, index=panel.index).groupby(panel["block"]).mean()
