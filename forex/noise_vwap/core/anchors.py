"""
HYP-0003 / EXP-0003 — the SESSION ANCHOR as the swept variable.

`core/session.py` hard-codes two anchors (`fxday` 17:15 ET, `active` 03:00 ET).
This module generalises the anchor to an arbitrary (timezone, hour, minute) and
keeps everything else about the Noise-Area construct identical, so that a sweep
over anchors changes exactly one thing.

WHY THIS EXISTS
---------------
The Noise-Area band measures |displacement from a session anchor| against the
trailing same-slot distribution of that displacement. On NQ the anchor is the
09:30 ET cash open — a real auction boundary. Spot FX has no such boundary, and
`fxday`'s 17:15 ET anchor was chosen for archive-defect reasons
(`reports/DATA_QUALITY.md`), not economic ones. If displacement is measured from
an arbitrary timestamp, the reference price is itself noise. That is an untested
explanation for the EXP-0001/0002 NO-GO, and it is the one input every later NQ
band study (cone, quantile, asymmetric, surround, Laplace) left fixed.

DESIGN INVARIANTS (see `experiments/hypotheses/HYP-0003.md`)
------------------------------------------------------------
* The anchor is derived from its OWN timezone with real DST. Hardcoding an ET
  offset for a London or Tokyo boundary misfiles sessions across DST transitions
  (LEARNINGS section 8). Every DST switch in America/New_York, Europe/London and
  the (DST-free) Asia/Tokyo falls inside the closed FX weekend, so no session is
  split by one.
* Session LENGTH is held at 1,425 minutes for every anchor, so the bar sample is
  near-identical and only the reference price, the session grouping and the TWAP
  move.
* The decision clock stays pinned to the ET wall clock at :29/:59, never derived
  from minutes-from-open, so the decision ROWS are the same across anchors
  (`core/session.py::decision_mfos` documents why).
* sigma[date, mfo] averages strictly PRIOR sessions (shift(1)) with the rule-9a
  fractional `min_periods`, exactly as `core/session.py::noise_bands`.
* The placebo family sits at HH:15 on the ET wall clock. `:15` matches the frozen
  `fxday` convention and keeps every anchor out of the residual `:00-:14` archive
  thinness (measured minute-of-hour coverage ratio 0.959 at `:00` for EUR/GBP/AUD).

DATA ACCESS
-----------
The canonical `forex/data/clean/*_1m_clean.parquet` have previously been
unreadable because sandbox-created replacements preserved protected owner-only
Windows ACLs. `load_prices` therefore prefers the canonical file and falls back
to the archived price-only file recorded in `futures_volume_manifest.json`, whose
SHA-256 is verified against the manifest's `spot_input_sha256`. No volume is used
anywhere in this study.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FX_CLEAN = ROOT / "data" / "clean"
FX_MANIFEST = FX_CLEAN / "futures_volume_manifest.json"
NQ_PATH = ROOT.parent / "futures" / "nq" / "data" / "NQ_1m_clean.parquet"

PAIRS = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")

SESSION_LENGTH = 1425          # minutes; matches the frozen `fxday` session
LOOKBACK = 90                  # sessions in the trailing per-slot band estimate
BAND_MIN_FRAC = 0.90           # rule-9a fractional min_periods
MIN_BAR_FRAC = 0.90            # a session must be this complete to be usable
DECISION_STEP = 30             # ET wall clock :29 / :59

PIP = 1e-4                     # all four pairs are USD-quoted majors
NQ_TICK = 0.25


EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


def utc_minutes(ts: pd.Series) -> np.ndarray:
    """Integer UTC minutes since the epoch, independent of the datetime dtype UNIT.

    `Series.astype("int64")` returns the underlying integer in whatever unit the
    dtype carries, and this project mixes units in ONE code path:

        forex/data/**            datetime64[us]        (microsecond unit)
        futures/nq/data/**       datetime64[ns, UTC]   (nanosecond unit)

    Both hold exact whole-minute timestamps -- the values are not sub-minute in
    either case, only the storage unit differs. So a hard-coded `// 60_000_000_000`
    is correct for NQ and wrong by 1000x for FX, silently collapsing 576,000
    distinct minutes onto 577 colliding values. Dividing by a Timedelta is exact
    for any unit; `tests/test_anchors.py` pins uniqueness and the mfo formula.
    """
    return ((ts - EPOCH) // pd.Timedelta("1min")).to_numpy()


@dataclass(frozen=True)
class Anchor:
    """A session anchor: `minute` past `hour` on the wall clock of `tz`."""
    name: str
    tz: str
    hour: int
    minute: int
    structural: bool = False
    note: str = ""

    @property
    def tod(self) -> int:
        return self.hour * 60 + self.minute


def placebo_family(minute: int = 15) -> list[Anchor]:
    """The 24 hourly ET anchors that form the null distribution.

    This is the LEARNINGS section 1 phase sweep applied to the anchor hour: a
    scheduled clock looks special until it is rerun at every phase of its
    interval. The incumbent `fxday` anchor (17:15 ET) is a MEMBER of this family,
    so the known EXP-0001 NO-GO calibrates the sweep.
    """
    return [Anchor(f"ET{h:02d}{minute:02d}", "America/New_York", h, minute)
            for h in range(24)]


# Structural anchors, each named with the reason it is a boundary. Defined in
# their OWN timezone so DST is handled by the tz database, not by an ET offset.
FX_STRUCTURAL = [
    Anchor("NY_ROLL", "America/New_York", 17, 15, True,
           "daily value-date/swap boundary; the one true day-break in spot FX "
           "(and the incumbent `fxday` anchor)"),
    Anchor("LON_OPEN", "Europe/London", 8, 15, True,
           "largest single liquidity regime change of the day"),
    Anchor("TOK_OPEN", "Asia/Tokyo", 9, 15, True,
           "Asian liquidity step; the only anchor whose ET offset moves with US "
           "DST, so it cannot be an ET artifact"),
    Anchor("LON_FIX", "Europe/London", 16, 15, True,
           "15 min AFTER the WM fix window closes -- deliberately outside it "
           "(LEARNINGS section 8: an entry inside the window measures the event)"),
]

NQ_STRUCTURAL = [
    Anchor("RTH_OPEN", "America/New_York", 9, 30, True,
           "the NQ cash open: a genuine auction boundary. POSITIVE CONTROL."),
]


# ----------------------------------------------------------------------------
# data loading
# ----------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_prices(inst: str) -> tuple[pd.DataFrame, str]:
    """Return `ts_utc, open, high, low, close` for an FX pair or for NQ.

    Returns (frame, provenance). For FX the canonical clean file is preferred; if
    it cannot be opened (Jupyter lock) the archived price-only file is used and
    its SHA-256 is verified against the manifest's `spot_input_sha256`, so the
    fallback is proved byte-identical rather than assumed to be.
    """
    if inst == "NQ":
        df = pd.read_parquet(NQ_PATH)
        cols = ["ts_utc", "open", "high", "low", "close"]
        if "is_roll" in df.columns:
            cols.append("is_roll")
        return df[cols].copy(), str(NQ_PATH)

    if inst not in PAIRS:
        raise ValueError(f"unknown instrument {inst!r}")

    canonical = FX_CLEAN / f"{inst}_1m_clean.parquet"
    try:
        df = pd.read_parquet(canonical, columns=["ts_utc", "open", "high", "low", "close"])
        return df, str(canonical)
    except (PermissionError, OSError):
        pass

    man = json.load(open(FX_MANIFEST))["pairs"][inst]
    archive = ROOT.parent / man["archive_path"].replace("/", "\\")
    got = _sha256(archive)
    want = man["spot_input_sha256"]
    if got != want:
        raise RuntimeError(
            f"{inst}: archive SHA-256 {got} != manifest spot_input_sha256 {want}; "
            "refusing to use unverified data")
    df = pd.read_parquet(archive, columns=["ts_utc", "open", "high", "low", "close"])
    q = man["quality"]
    if len(df) != q["spot_rows"]:
        raise RuntimeError(f"{inst}: archive rows {len(df)} != manifest {q['spot_rows']}")
    return df, f"{archive} (sha256-verified fallback; canonical file locked)"


# ----------------------------------------------------------------------------
# anchored session construction
# ----------------------------------------------------------------------------

def anchored_sessions(prices: pd.DataFrame, anchor: Anchor,
                      length: int = SESSION_LENGTH) -> pd.DataFrame:
    """Attach the anchor's session id, minutes-from-anchor and causal TWAP.

    `date` labels a session by the local calendar date on which it ENDS (the
    same convention as `core/session.py::load_session`). `utc_min` is the integer
    UTC minute, used downstream for O(1) forward-return lookups.
    """
    ts = pd.to_datetime(prices["ts_utc"], utc=True)
    local = ts.dt.tz_convert(anchor.tz)
    tod = (local.dt.hour * 60 + local.dt.minute).to_numpy()

    mfo = (tod - anchor.tod) % 1440
    keep = mfo < length

    day = local.dt.normalize().dt.tz_localize(None).to_numpy()
    rolls_over = (tod >= anchor.tod) & (anchor.tod + length > 1440)
    date = day + np.where(rolls_over, np.timedelta64(1, "D"), np.timedelta64(0, "D"))

    df = prices.loc[keep, ["open", "high", "low", "close"]].copy()
    df["utc_min"] = utc_minutes(ts)[keep]
    df["mfo"] = mfo[keep]
    df["date"] = date[keep]
    df["et_tod"] = (ts.dt.tz_convert("America/New_York").dt.hour * 60
                    + ts.dt.tz_convert("America/New_York").dt.minute).to_numpy()[keep]
    df = df.sort_values(["date", "mfo"]).reset_index(drop=True)

    # drop near-empty sessions (weekend stubs, holiday half-days)
    nb = df.groupby("date")["mfo"].transform("size")
    df = df.loc[nb >= MIN_BAR_FRAC * length].reset_index(drop=True)

    # causal cumulative session TWAP == VWAP under constant volume
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    g = df.groupby("date", sort=False)
    df["twap"] = (tp.groupby(df["date"]).cumsum() / (g.cumcount() + 1)).to_numpy()
    return df


def anchor_reference(df: pd.DataFrame) -> pd.DataFrame:
    """Per-session anchor price, prior close, and anchor STABILITY.

    The anchor price is the open of the `mfo == 0` bar. When that minute is
    absent the session is marked unstable and excluded: a session-varying anchor
    is exactly the defect the frozen 17:15 convention exists to avoid, and
    silently substituting a later bar would reintroduce it. `anchor_stability`
    (the fraction of sessions whose anchor minute is present) is reported per
    anchor cell and gates the result (rule 9a).
    """
    dates = np.sort(df["date"].unique())
    at0 = df[df["mfo"] == 0].set_index("date")["open"]
    last = df.groupby("date")["close"].last()
    ref = pd.DataFrame(index=pd.Index(dates, name="date"))
    ref["anchor_open"] = at0.reindex(dates)
    ref["prior_close"] = last.reindex(dates).shift(1)
    ref["stable"] = ref["anchor_open"].notna()
    return ref


def decision_rows(df: pd.DataFrame, length: int = SESSION_LENGTH,
                  step: int = DECISION_STEP) -> pd.DataFrame:
    """Rows on the ET wall-clock :29/:59 grid, excluding the first and last block.

    Pinned to the ET wall clock rather than to minutes-from-anchor so the decision
    ROWS are identical across anchors and cannot land in the `:00-:14` archive
    holes (`core/session.py::decision_mfos`).
    """
    on_grid = ((df["et_tod"].to_numpy() % 60) + 1) % step == 0
    inside = (df["mfo"].to_numpy() >= step) & (df["mfo"].to_numpy() < length - 1)
    return df.loc[on_grid & inside].reset_index(drop=True)


def band_sigma(dec: pd.DataFrame, ref: pd.DataFrame, lookback: int = LOOKBACK,
               min_frac: float = BAND_MIN_FRAC) -> pd.DataFrame:
    """Trailing same-slot mean |displacement from the anchor|, strictly prior.

        move[d, mfo]  = |close[d, mfo] / anchor_open[d] - 1|
        sigma[d, mfo] = mean of move over the prior `lookback` sessions (shift 1)

    Identical to `core/session.py::noise_bands` apart from taking the anchor price
    from `ref` (which may be any anchor) instead of the session's first bar.
    """
    m = dec.merge(ref[["anchor_open"]], left_on="date", right_index=True, how="left")
    cm = m.pivot_table(index="date", columns="mfo", values="close", aggfunc="last")
    a0 = ref["anchor_open"].reindex(cm.index)
    move = (cm.div(a0, axis=0) - 1.0).abs()

    mp = max(1, int(math.ceil(min_frac * lookback)))
    sigma = move.shift(1).rolling(lookback, min_periods=mp).mean()

    out = sigma.stack().rename("sigma").reset_index()
    out.columns = ["date", "mfo", "sigma"]
    return out
