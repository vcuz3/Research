# FX futures VWAP exploration (6E/6B) — Project Guide

## Objective and scope

- Research question: does a session-anchored VWAP carry tradable information on
  CME FX futures, and is its **volume** weighting load-bearing?
- Instruments: **6E** (EUR/USD future, 125,000 EUR, $12.50/pip) and **6B**
  (GBP/USD future, 62,500 GBP, $6.25/pip).
- Source paper: none. This is an open-ended exploration, not a replication, so
  `paper/` is intentionally empty and the baseline-replication gate does not
  apply. Structural grounding is cited per hypothesis (Lyons 2001; Ranaldo 2009;
  Melvin & Prins 2015; Evans 2018; FSB 2014).
- Data source and coverage: Databento `GLBX.MDP3` `ohlcv-1m`, volume-ranked
  continuous front `6E.v.0` / `6B.v.0`, **unadjusted**, 2010-06-07 .. 2026-07-27,
  at `futures/data/databento/`. Shared instrument data — do not copy into the
  project.

## Project map

| Concern | Location |
| --- | --- |
| Paper contract and claims | `paper/` — **not applicable**, no source paper |
| Faithful replication | `baseline_replication/` — **not applicable** |
| Execution/accounting | `backtest_engine/` — **not applicable**, no engine (see below) |
| Features/anchors/statistics | `core/` |
| Hypotheses and run ledger | `experiments/` |
| Nulls/controls/holdout | `validation/` |
| Immutable outputs | `artifacts/runs/` |
| Current reports | `reports/` |
| Durable handoff | `MEMORY.md` |

**Why there is no backtest engine.** Every result is an entry-information
measurement (rule 15): the feature is observed at `close(m)`, the position is
entered at `open(m+1)` (rules 1, 2) and closed at a bar close H minutes later.
There are no stops, targets or barriers, so there is no fill-path ambiguity to
adjudicate and nothing that exit geometry could manufacture. If this project ever
acquires a barrier strategy it will need a real engine and a rule-3 intrabar
policy, and this section must be revisited.

## Data and session conventions

- Timestamp source and timezone: Databento `ts_event` in UTC; every derived clock
  is `America/New_York` wall time, except the London fix which is
  `Europe/London`.
- Trading calendar/session: CME FX Globex, **18:00 ET → 16:59 ET** (the CME trade
  date), 1,380 minutes, 60-minute maintenance halt 17:00-17:59 ET. Verified
  against the archive, not assumed. `sdate = date(t_ET + 6h)`;
  `mfo = (minute_of_day_ET - 1080) mod 1440`.
- Decision clock: 30-minute grid pinned to the **ET wall clock** (`mfo` 29, 59,
  …), 46 decisions per session. Never derived from minutes-from-open.
- Instrument/roll convention: volume-ranked continuous front, unadjusted.
  Sessions spanning more than one `instrument_id` (~1.5%) are **dropped** — a
  session-anchored VWAP across a roll averages two contracts. Since no analysis
  here spans a session boundary, back-adjustment is unnecessary.
- Corporate actions or price adjustments: not applicable.
- Missing data policy: sessions with fewer than 400 bars are dropped (holiday
  half-days, the 2010 partial first session); counts are returned by
  `LoadReport`, not hidden. Windowed features use the rule-9a fractional
  `min_periods`, **`lookback=90, min_periods=45`**, set by measured 6B Asia
  coverage — see `reports/DATA_QUALITY.txt` and finding G.
- Holdout: trade dates in **2024, 2025, 2026 are sealed**. `load_bars` defaults to
  `scope="explore"`; `scope="holdout"` must be passed explicitly.
- Data fingerprint command:
  `.\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.data_quality`

## Contract economics (rule 19)

The reporting unit is **per product**, not a single constant. Two ticks changed
mid-sample:

| | notional | unit | $/unit | early tick | later tick |
|---|---|---|---|---|---|
| 6E | 125,000 EUR | 1e-4 | $12.50 | 0.0001 ($12.50) | **0.00005 ($6.25)** from 2016 |
| 6B | 62,500 GBP | 1e-4 | $6.25 | 0.0001 ($6.25) | unchanged |
| 6J | 12,500,000 JPY | **1e-6** | $12.50 | 1e-6 ($12.50) | **5e-7 ($6.25)** from 2015 |

**6J's unit is 1e-6, not 1e-4**, because it quotes dollars per YEN near 0.0091;
1e-6 is chosen so 12,500,000 × 1e-6 = $12.50, exactly a 6E pip and exactly one
pre-2015 tick. It is **not** the conventional USD/JPY pip of 0.01 yen — the
futures quote is the *reciprocal* of the spot convention, so 0.01 yen maps to a
price-level-dependent ~8.3e-8 and cannot serve as a fixed unit.

Never quote a cost in ticks across the whole sample; build it from
`core.data.tick_size(product, year)`. Never place two products' native units side
by side — compare in dollars, or in the risk-equalised statistic (P&L over the
decision's own same-slot displacement scale), which is the equal-risk estimand of
rule 12.

## Commands

```powershell
# Core invariants (25 checks)
.\.venv\Scripts\python.exe -m futures.forex.vwap_exploration.tests.test_core

# Rule-9a data-quality gate -> reports/DATA_QUALITY.txt
.\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.data_quality

# Registered experiments (append a product to run just one)
.\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0001_anatomy
.\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0002_entry_information
.\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0003_london_fix
.\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0004_vol_stratified_blocks
.\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0005_liquidity_vs_clock
.\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0006_rsi
```

## Acceptance gates

- Baseline tolerance: not applicable (no replication target).
- Engine tests required: `tests/test_core.py` must pass 25/25 before any run is
  registered. It pins, among others, `TWAP == VWAP-at-constant-volume` (and
  `!=` at varying volume), anchor causality under truncation, strict-prior-session
  slot scaling, cluster-SE behaviour under block dependence, the
  rank-IC-vs-mean-spread disagreement, and — for the confounder-matched
  contrast — that `stratified_contrast` kills a pure confound, preserves a real
  within-stratum effect, and collapses `n_eff` to zero under disjoint support.
- Minimum validation suite for any *candidate edge* (none reached this bar):
  degenerate-limit control, session cluster-robust per-signal estimand with the
  session-averaged contrast reported alongside, cross-product agreement, per-era
  stability, era-appropriate costs, and a claim-matched null. **Gate the null on
  the real pass first clearing its primary metric** — none did here, so no null
  was spent.
- Holdout protocol: 2024-2026 sealed. Nothing in this project has earned a
  holdout run.

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.

## Standing cautions specific to this project

1. **Always run the no-anchor control.** `past30` (fade the trailing return,
   z-scored identically) beat every session anchor on both products. Any future
   anchor variant must clear it, not just clear zero.
2. **Never enter at `close(m)`.** The shared-print artifact is worth 68-88% of the
   measured reversal here.
3. **Never session-average a per-signal effect.** It produced t≈+15 from a null on
   6B.
4. **Check your measurement window against institutional windows.** The entire
   London-fix result was the measurement window overlapping the benchmark's
   averaging window by 30 seconds.
5. **A RECURSIVE feature's gap damage is DISPLACED by its memory length.** Under
   a reset-on-gap policy, `asia`'s 5.8% missing bars collapsed **`ldn_am`'s** RSI
   coverage to 0.73 — a block with 0.25% missing — because 14 periods on a
   30-minute grid is ~7 hours. Per-block gap counts do NOT predict per-block
   coverage. Bridge increments across missing bars
   (`core/rsi.py::gap_policy="bridge"`) and report both policies.
6. **A fixed threshold on a trailing-window-normalised feature is a time-of-day
   selector.** RSI's 70/30 cut had a per-slot selection-rate CV 3.5-5.7x the
   project's same-slot z-score, firing 6.4% in `asia` against 16.1% in `overlap`.
   Report the per-slot selection-rate CV for any new threshold, and compare every
   candidate at a MATCHED global selection rate on a COMMON sample.
7. **Any conditioner built from 1-minute changes has coverage equal to roughly
   the SQUARE of the per-minute coverage.** `rv_60` deleted 29.7% of 6B's Asia
   decisions against 0.1% of its overlap decisions — finding G reappearing inside
   the control meant to remove a bias, and selective in the worst direction (it
   removes the quiet tail of the very variable being conditioned on). Report
   per-block coverage of any new feature before reading a contrast built on it,
   and carry a looser-floor sensitivity arm.
