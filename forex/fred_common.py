"""
Shared FRED / ALFRED plumbing used by the AUDUSD data downloaders.

Two data philosophies live here and it matters which one you use:

  * ALFRED real-time *vintages* (`download_alfred_revisions` + `value_as_of`)
    give point-in-time (PIT) macro data: the value that had actually been
    *released* by a given signal date, revisions and all. Use this for revised
    macro releases (GDP, CPI, unemployment...) where hindsight bias is real.

  * Latest-vintage series (`download_fred_latest`) return today's revised
    numbers. This is fine for *market prices* (FX, equities, yields, commodity
    spot) because those are observed, not revised -- the print on date d was
    already known on date d. Do NOT use it for revised macro releases.

The vintage diagnostic (`vintage_report`) exists because many OECD-sourced
series on FRED have NO real vintage history: ALFRED hands back a single
`realtime_start`, so `value_as_of` silently degrades to revised data. Always
eyeball the report before trusting a PIT backtest.
"""

from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import json
import os

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# API key / .env loading
# --------------------------------------------------------------------------- #

def load_env_file(env_path):
    """Minimal .env loader (no python-dotenv dependency).

    Only sets keys that are not already present in the real environment, so an
    explicitly exported variable always wins.
    """
    env_path = Path(env_path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_fred_api_key(env_path=None):
    """Return the FRED API key, loading a local .env first if provided."""
    if env_path is not None:
        load_env_file(env_path)
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "FRED_API_KEY is not set. Get a free St. Louis Fed key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html and put it in "
            "AUDUSD/.env as FRED_API_KEY=... (or export it)."
        )
    return key


# --------------------------------------------------------------------------- #
# Raw API access
# --------------------------------------------------------------------------- #

def fred_api(endpoint, params, api_key):
    base_url = f"https://api.stlouisfed.org/fred/{endpoint}"
    params = dict(params)
    params["api_key"] = api_key
    params["file_type"] = "json"
    url = base_url + "?" + urlencode(params)

    with urlopen(url) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if "error_message" in payload:
        raise RuntimeError(f"{endpoint} {params.get('series_id', '')}: "
                           f"{payload['error_message']}")
    return payload


def download_alfred_revisions(series_id, api_key, observation_start="1980-01-01"):
    """Full ALFRED real-time revision history for one series."""
    print(f"  ALFRED vintages: {series_id}")
    rows = []
    offset = 0
    limit = 100000

    while True:
        payload = fred_api(
            "series/observations",
            {
                "series_id": series_id,
                "realtime_start": "1776-07-04",
                "realtime_end": pd.Timestamp.today().date().isoformat(),
                "observation_start": observation_start,
                "limit": limit,
                "offset": offset,
                "sort_order": "asc",
            },
            api_key,
        )
        rows.extend(payload["observations"])
        offset += limit
        if offset >= int(payload["count"]):
            break

    data = pd.DataFrame(rows)
    data["date"] = pd.to_datetime(data["date"])
    data["realtime_start"] = pd.to_datetime(data["realtime_start"])
    data["realtime_end"] = pd.to_datetime(
        data["realtime_end"].replace([".", "9999-12-31"], pd.NA),
        errors="coerce",
    )
    data["value"] = pd.to_numeric(data["value"].replace(".", pd.NA), errors="coerce")
    return data[["date", "realtime_start", "realtime_end", "value"]]


def download_fred_latest(series_id, observation_start=None):
    """Latest-vintage series via the public graph CSV endpoint (no key needed).

    Returns a Series indexed by observation date. Use only for market prices or
    where revisions do not matter -- this is NOT point-in-time.
    """
    print(f"  FRED latest: {series_id}")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    if observation_start:
        url += f"&cosd={observation_start}"
    data = pd.read_csv(url)
    data.columns = ["date", "value"]
    data["date"] = pd.to_datetime(data["date"])
    data["value"] = pd.to_numeric(data["value"].replace(".", np.nan), errors="coerce")
    return data.set_index("date")["value"].sort_index()


# --------------------------------------------------------------------------- #
# Point-in-time reconstruction
# --------------------------------------------------------------------------- #

def value_as_of(revisions, as_of_date):
    """Latest *released* (value, observation_date) known at `as_of_date`.

    Returns the observation date too so callers can compute native-frequency
    changes (see native_transform) instead of operating on monthly step
    functions.
    """
    live = revisions[
        (revisions["date"] <= as_of_date)
        & (revisions["realtime_start"] <= as_of_date)
        & (revisions["realtime_end"].isna() | (revisions["realtime_end"] >= as_of_date))
    ]
    if live.empty:
        return np.nan, pd.NaT

    live = live.sort_values(["date", "realtime_start"])
    row = live.iloc[-1]
    return row["value"], row["date"]


def build_pit_frame(revisions, signal_dates):
    """PIT monthly value + the observation date it corresponds to.

    Returns a DataFrame indexed by signal_dates with columns ['value', 'obs'].
    """
    values, obs = [], []
    for d in signal_dates:
        v, o = value_as_of(revisions, d)
        values.append(v)
        obs.append(o)
    return pd.DataFrame({"value": values, "obs": obs}, index=signal_dates)


def vintage_report(revisions_by_name):
    """Flag series that have no real ALFRED vintage history.

    A PIT proxy is only trustworthy if the series actually carries multiple
    `realtime_start` values. Series with a single vintage are effectively
    latest-revision data wearing a point-in-time label.
    """
    rows = []
    for name, rev in revisions_by_name.items():
        rev = rev.dropna(subset=["value"])
        n_vintages = rev["realtime_start"].nunique()
        n_obs = rev["date"].nunique()
        # avg distinct vintages per observation date -> >1 means genuine revisions
        revisions_per_obs = (0.0 if n_obs == 0
                             else rev.groupby("date")["realtime_start"].nunique().mean())
        first_rt = rev["realtime_start"].min()

        # Two distinct failure modes:
        #  * no_vintages  -> only one vintage exists overall = purely revised data.
        #    (One vintage PER observation with a long history is fine: that's how a
        #    non-revised market rate like TB3MS looks, so we don't flag that.)
        #  * PIT is only valid AFTER first_realtime_start; earlier signal dates get
        #    NaN (no lookahead) but it caps the usable sample. pit_valid_from makes
        #    that cap explicit -- often the binding constraint, not point_in_time_ok.
        no_vintages = n_vintages <= 1
        rows.append({
            "series": name,
            "distinct_vintages": n_vintages,
            "revisions_per_obs": round(revisions_per_obs, 2),
            "pit_valid_from": (first_rt.date() if pd.notna(first_rt) else None),
            "point_in_time_ok": not no_vintages,
        })
    report = pd.DataFrame(rows).sort_values(["point_in_time_ok", "pit_valid_from"])
    return report


# --------------------------------------------------------------------------- #
# Native-frequency, PIT-safe transforms
# --------------------------------------------------------------------------- #
#
# A quarterly series sampled onto a monthly grid is a step function; each
# quarter's value repeats ~3x. Applying rolling(12)/pct_change(12)/diff(3) to
# that step function weights quarters by how many monthly stamps they happen to
# occupy (release-timing dependent), which is an artifact. These helpers instead
# collapse the monthly PIT frame to one row per *distinct release* (native
# cadence) using the observation date, compute the transform there, then
# forward-fill back to the monthly grid. No lookahead: each point uses only the
# value known as of that month.

def _native_release_series(pit_frame):
    """Collapse the PIT frame to one value per distinct observation date."""
    df = pit_frame.dropna(subset=["value", "obs"]).copy()
    if df.empty:
        return pd.Series(dtype=float)
    new_release = df["obs"] != df["obs"].shift()
    native = df[new_release]
    # index by the signal date at which each release first appeared
    return native["value"]


def _infer_native_months(native_index):
    """Median spacing between releases, in months (1 monthly, 3 quarterly...)."""
    if len(native_index) < 3:
        return 1.0
    diffs = native_index.to_series().diff().dropna().dt.days
    return max(1.0, round(float(diffs.median()) / 30.44))


def native_transform(pit_frame, signal_dates, months, kind):
    """Native-frequency change of a PIT series, reindexed to the monthly grid.

    months : the economic horizon of the change (e.g. 12 for YoY, 3 for a
             quarterly change). Converted to the right number of *native*
             periods based on the series' own release cadence, so AU (quarterly)
             and US (monthly) legs of a relative factor are comparable.
    kind   : 'pct' (percent change *100), 'diff' (level change), or
             'yoy_mean' (rolling mean of the value over `months`).
    """
    native = _native_release_series(pit_frame)
    if native.empty:
        return pd.Series(np.nan, index=signal_dates)

    native_months = _infer_native_months(native.index)
    periods = max(1, int(round(months / native_months)))

    if kind == "pct":
        out = native.pct_change(periods) * 100.0
    elif kind == "diff":
        out = native.diff(periods)
    elif kind == "mean":
        out = native.rolling(periods, min_periods=periods).mean()
    else:
        raise ValueError(f"unknown kind={kind!r}")

    return out.reindex(signal_dates).ffill()


def zero_neutral_zscore(factors, min_periods=36, clip=3.0):
    """Expanding, zero-neutral z-score (Macrosynergy 'zn' convention).

    Relative (AU-US) factors are conceptually centred on zero, so we scale by an
    expanding standard deviation WITHOUT subtracting a mean. The expanding
    window uses only past+current rows (no lookahead) and scores are winsorized
    at +/- `clip`. If you feed a factor that is NOT naturally zero-centred, add a
    de-meaning step first -- this helper assumes zero neutral.
    """
    std = factors.expanding(min_periods=min_periods).std()
    scores = (factors / std).clip(lower=-clip, upper=clip)
    return scores
