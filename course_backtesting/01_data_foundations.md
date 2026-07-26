# 01 — Data foundations, sessions, and the data-quality gate

> Every backtest bug I have found in this workspace that survived more than a
> day was a **data** bug wearing a strategy costume.

---

## 1.1 The bar contract

Fix this once and never deviate:

| Column | Meaning | Rule |
|---|---|---|
| `ts_utc` | **Open** timestamp of the bar, UTC, tz-aware | A bar labelled `09:30:00` covers `[09:30:00, 09:31:00)` |
| `open, high, low, close` | prices | `low <= open,close <= high` must hold |
| `volume` | contracts/shares traded in the interval | |
| `symbol` | the actual tradable contract | needed for rolls |

Two conventions exist for bar timestamps: **open-labelled** and
**close-labelled**. Vendors mix them. Pick open-labelled, and **verify** which
one your vendor uses by checking the first bar of a session against the known
session open time. Getting this wrong is a silent one-bar lookahead or lag on
every single trade.

```python
# Verification: for an equity-index future, RTH opens 09:30 ET.
# Open-labelled data -> first RTH bar is 09:30. Close-labelled -> 09:31.
first = df[df.et.dt.date == some_date].et.min()
print(first)   # if 09:31, your data is CLOSE-labelled: shift it or adjust mfo.
```

**The information rule.** A bar's `close` is known at `ts_utc + bar_duration`,
not at `ts_utc`. Its `high` and `low` are known only at the end too. This
single fact generates most of lesson 06.

---

## 1.2 Timezones: store UTC, reason in exchange-local

Never store local time. Store UTC, convert on load:

```python
ts = pd.to_datetime(df["ts_utc"], utc=True)
et = ts.dt.tz_convert("America/New_York")
df["tod"] = (et.dt.hour * 60 + et.dt.minute).values      # minute of day, ET
df["etdate"] = et.dt.normalize().dt.tz_localize(None).values
```

Why: US DST shifts twice a year. A strategy keyed on UTC time-of-day silently
moves an hour relative to the cash open two days a year, and its "09:30 bar"
becomes the "08:30 bar" for six months. `pytz`/`zoneinfo` via
`tz_convert` handles this correctly; manual `+5h` offsets do not.

---

## 1.3 Session dates and the minutes-from-open coordinate

For anything intraday, the useful coordinate is **not** wall-clock time — it is
**minutes from the session open** (`mfo`). It makes same-time-of-day features
align across sessions and survives overnight sessions that wrap midnight.

From `futures/nq/noise_vwap/core/session.py`:

```python
RTH_START = 9 * 60 + 30      # 09:30 ET
RTH_END   = 16 * 60          # 16:00 ET, exclusive

if session == "RTH":
    df["sdate"] = df["etdate"]
    df["mfo"] = (df["tod"] - RTH_START).astype(int)
else:  # ETH / Globex: session opens 18:00 ET the PRIOR evening
    # trade-date = (ET + 6h).date()  -> 18:00 ET + 6h = 00:00 next day
    df["sdate"] = (et + pd.Timedelta(hours=6)).dt.normalize().dt.tz_localize(None)
    df["mfo"] = ((df["tod"] - 18 * 60) % 1440).astype(int)
```

Three things this gets right that ad-hoc code gets wrong:

1. **`mfo` is anchored to a FIXED clock time, not to the first observed bar.**
   If you use `groupby(date).cumcount()`, then on a day where the 09:30 bar is
   missing, every subsequent bar's index shifts by one and your
   same-time-of-day feature compares 10:00 against 09:59 on other days.
2. **The trade-date is defined for the overnight session.** The Globex session
   for trade-date D starts at 18:00 ET on D−1. The `+6h` trick maps it
   correctly and keeps the whole RTH day with its own date.
3. **`is_rth` is carried separately**, so you can trade the overnight but still
   force a flat at the cash close.

Also drop incomplete sessions explicitly:

```python
nb = df.groupby("sdate")["et"].transform("size")
df = df[nb >= MIN_BARS_RTH].reset_index(drop=True)   # e.g. 350 of ~390
```

Half-days (Thanksgiving Friday, Christmas Eve) otherwise contaminate
same-slot statistics with sessions that ended at 13:00.

---

## 1.4 Futures rolls — the causal way

Continuous futures series are a **construction**, and most constructions leak.

**Rules:**

- **Never pick the front contract using future volume.** "The contract with
  the most volume over the month" is a two-sided statistic. Use a causal rule:
  roll when yesterday's volume/OI in the deferred exceeded the front, or roll
  on a fixed calendar rule (e.g. 8 business days before expiry).
- **Never let a roll gap occur inside a simulated trade.** Either flatten at
  the roll, or run the strategy on the *individual contract's* prices and stitch
  the P&L, not the prices.
- **Choose your adjustment deliberately.** Back-adjusted (panama) series have
  correct *differences* but wrong *levels* — any percentage-based feature
  (returns, `close/open − 1`, %-bands) computed on a back-adjusted series is
  wrong far from the present. Ratio-adjusted series have correct returns but
  wrong point differences — any point-based feature (ATR in points, tick costs)
  is wrong.

In this workspace the noise band uses `|close/open − 1|` — a **percentage**
feature — computed **within a single session**, so no roll can occur inside the
window and the choice is moot. That is not an accident; it is a design that
sidesteps the problem. Prefer such designs.

**Gotcha found here:** vendor `instrument_id`s get *recycled* across contracts.
Resolving symbols requires a resolve-window and per-day validation; a naive
`instrument_id` join silently splices two different contracts together.

---

## 1.5 The data-quality gate (run this before interpreting anything)

This is Rule 9a in this workspace, and it exists because a verbatim NQ→GC port
silently deleted **~28% of the 15:29 decisions** on gold and nobody noticed for
weeks (`futures/gc/noise_vwap/reports/DATA_QUALITY.md`).

The cause: a `rolling(90, min_periods=90)` same-time-of-day feature. On a thin
instrument, **one** missing minute anywhere in the trailing 90-session window
nulls the feature, and the strategy silently skips that decision. Deletion rate
tracks time-of-day liquidity, so it is a **hidden liquidity filter**.

### The gate, as a committed script

```python
"""data_quality.py — run at every core data-load and feature stage."""
import numpy as np, pandas as pd

def report(df: pd.DataFrame, feature_cols: list[str], slot_col="mfo") -> str:
    out = []
    # --- coverage -----------------------------------------------------------
    out.append(f"rows={len(df)} sessions={df.sdate.nunique()} "
               f"{df.sdate.min().date()} -> {df.sdate.max().date()}")
    per_sess = df.groupby("sdate").size()
    out.append(f"bars/session: med={per_sess.median():.0f} "
               f"min={per_sess.min()} max={per_sess.max()} "
               f"short(<90% med)={int((per_sess < 0.9*per_sess.median()).sum())}")

    # --- missing bars by time of day ---------------------------------------
    n_sess = df.sdate.nunique()
    slot_cov = df.groupby(slot_col).size() / n_sess
    worst = slot_cov.nsmallest(5)
    out.append("worst raw slot coverage:\n" +
               "\n".join(f"  {slot_col}={k}: {v:.3%}" for k, v in worst.items()))

    # --- duplicates / ordering ---------------------------------------------
    dup = int(df.duplicated(["sdate", slot_col]).sum())
    mono = bool(df.sort_values("et").et.is_monotonic_increasing)
    out.append(f"duplicate (sdate,{slot_col}) rows={dup}  ts_monotonic={mono}")

    # --- OHLC sanity --------------------------------------------------------
    bad = int(((df.low > df[["open","close"]].min(axis=1)) |
               (df.high < df[["open","close"]].max(axis=1))).sum())
    nonpos = int((df[["open","high","low","close"]] <= 0).any(axis=1).sum())
    out.append(f"OHLC violations={bad}  nonpositive prices={nonpos}")

    # --- FEATURE coverage: the load-bearing part ---------------------------
    for c in feature_cols:
        cov = df.groupby(slot_col)[c].apply(lambda s: s.notna().mean())
        out.append(f"feature '{c}' coverage by slot: "
                   f"min={cov.min():.3%} max={cov.max():.3%} "
                   f"spread={cov.max()-cov.min():.3%}")
        if cov.max() - cov.min() > 0.05:
            out.append(f"  !! NON-UNIFORM: '{c}' deletes decisions unevenly "
                       f"by time of day. worst slots: "
                       f"{cov.nsmallest(3).to_dict()}")
    return "\n".join(out)
```

### How to read it

- **Uniform** feature coverage across slots → pass.
- Coverage that **tracks time-of-day liquidity** → you have a hidden filter.
  Quantify how many decision points it removes, per era and per slot, and
  confirm the exclusion is causal.

### The fix

```python
# BAD: one gap anywhere in the window nulls the whole slot
sigma = move.shift(1).rolling(lookback, min_periods=lookback).mean()

# GOOD: average over present sessions; still strictly causal
BAND_MIN_FRAC = 0.9
sigma = move.shift(1).rolling(lookback,
                              min_periods=int(np.ceil(BAND_MIN_FRAC * lookback))).mean()
```

This restored uniform ~97.8% coverage on GC and ~98%/96% on YM/RTY.

> Note the defect was *conservative* — it deleted signals, it did not
> manufacture an edge. It still had to be found and fixed, because it corrupted
> every time-of-day interpretation built on top of it. **"It only loses money"
> is not a reason to leave a data bug in place.**

---

## 1.6 Coverage, joins, survivorship

Before interpreting any cross-source feature, record:

- **Coverage** — does each source span the full claim period, for the full
  population? A macro series starting in 2015 cannot support a 2011-onward
  claim.
- **Join keys and timezone alignment** — the #1 cross-source bug is joining a
  UTC-dated series to an ET-dated series. Always join on an explicit,
  tz-normalised session date.
- **Publication latency** — see Rule 10 in
  [06_lookahead_and_traps.md](06_lookahead_and_traps.md). Use the *vintage*
  available at decision time, not today's revised value.
- **Survivorship** — for anything cross-sectional, is your universe
  reconstructed as-of each date, or is it today's index membership?

A real failure from this workspace: a data migration produced **mis-timed ES
bars** that shifted the whole ES session; every ES result computed before the
fix was wrong. The tell was a data-quality report showing an unexpected `mfo`
range. Run the gate after **every** data rebuild.

---

## 1.7 Resolution: when 1-minute is not enough

1-minute OHLC cannot order the intrabar path. For any strategy where a stop and
a target can both be reachable within one bar, this matters enormously.

Measured in this workspace (`futures/gc/vwap_reversion`): a ±2σ VWAP fade with a
2:1 bracket showed gross Sharpe **+0.57, t = 2.16** on 1-minute bars. Re-run
identically on **1-second** bars, the win rate fell 35.6% → 33.4% — exactly the
algebraic break-even `1/(1+RR)` — and the gross edge collapsed to Sharpe
**+0.08**. The entire 1-minute "edge" was coarse-bar over-crediting of paths
that actually hit the stop first.

**Rule:** never trust a 1-minute gross number for a bracket/fade before
re-resolving the intrabar path at a materially finer resolution. Report the
1m-vs-1s win rate side by side. If the win rate sits at `1/(1+RR)`, the barriers
are efficient and there is no edge.

Design your engine keyed on **seconds-from-midnight** (or a raw int64
timestamp), not on a bar index, so the *same engine* runs both resolutions and
the only variable is the path.

---

## 1.8 Checklist before you build a single feature

- [ ] Bar timestamps: open- or close-labelled? **Verified**, not assumed.
- [ ] Stored UTC, converted with a real tz database.
- [ ] Session date defined, including the overnight case.
- [ ] `mfo` anchored to a fixed clock time, not `cumcount()`.
- [ ] Incomplete/half sessions dropped with an explicit threshold.
- [ ] Roll rule is causal; no roll gap inside a trade; adjustment matches the
      feature type (pct vs points).
- [ ] Data-quality report committed as a script, output committed as evidence.
- [ ] Feature coverage uniform across time-of-day, or the non-uniformity
      quantified and justified.

Next: [02 — Indicators, causally and correctly](02_indicators.md)
