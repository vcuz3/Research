"""The WM/Reuters 16:00 London fix clock.

The fix minute is derived from the **Europe/London** wall clock, not hardcoded to
11:00 ET.  US and UK daylight-saving transitions are about three weeks apart:

  * mid-March .. end-March  -- US on EDT (UTC-4), UK still on GMT (UTC+0)
  * late-Oct .. early-Nov   -- UK back on GMT (UTC+0), US still on EDT (UTC-4)

During those shoulder windows the offset is 4 hours instead of 5, so London 16:00
lands at **12:00 ET**.  Roughly 15 sessions a year.  Hardcoding 11:00 would push
those sessions' fix flow into what the study treats as a placebo hour and dilute
both arms of the comparison.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# WM widened the fix calculation window from 1 minute (15:59:30-16:00:30) to
# 5 minutes (15:57:30-16:02:30) on this date, following the FSB's 2014
# Foreign Exchange Benchmarks report.
WINDOW_WIDENED = pd.Timestamp("2015-02-15")

FIX_HOUR_LONDON = 16


def fix_mod_et(dates: pd.Series) -> pd.Series:
    """ET minute-of-day of the 16:00 Europe/London fix, per calendar date."""
    d = pd.to_datetime(pd.Series(dates).to_numpy()).normalize()
    naive = pd.DatetimeIndex(d) + pd.Timedelta(hours=FIX_HOUR_LONDON)
    ldn = naive.tz_localize("Europe/London", nonexistent="shift_forward",
                            ambiguous=True)
    et = ldn.tz_convert("America/New_York")
    return pd.Series(et.hour * 60 + et.minute, index=pd.Series(dates).index)


def month_end_sessions(sdates: np.ndarray) -> np.ndarray:
    """Boolean mask: is this the LAST trading session of its calendar month?"""
    s = pd.Series(pd.to_datetime(sdates)).sort_values()
    ym = s.dt.year * 100 + s.dt.month
    last = s.groupby(ym.to_numpy()).transform("max")
    flag = (s == last)
    return flag.reindex(pd.Series(pd.to_datetime(sdates)).index).to_numpy()
