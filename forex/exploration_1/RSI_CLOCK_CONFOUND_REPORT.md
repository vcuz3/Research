# Why "scheduled" beat "first crossing": the two clocks differ in sampling PHASE, not in signal quality

Date: 2026-08-04. Scope: EURUSD + GBPUSD, 2012-01-01 to 2023-12-31, holdout from
2024 never loaded. Reproduces and then reinterprets the clock comparison recorded
in `MEMORY.md` (scheduled 0.637-0.695 pip vs first-crossing 0.220-0.418 pip).

Scripts (all self-contained, re-implementing the fakeout notebook's loader, Wilder
RSI, clock definitions and endpoint accounting):

- `_run_rsi_clock_decomposition.py` -> `rsi_clock_decomposition_results.json`
- `_run_rsi_clock_phase_forensics.py` -> `rsi_clock_phase_forensics_results.json`
- `_run_rsi_clock_boundary_test.py` -> `rsi_clock_boundary_test_results.json`

## Verdict

**The first-crossing signal is not worse. It is better, once the sampling phase is
held fixed.** The published comparison changed two things at once: the signal
definition (state vs event) and the sampling phase (100% on `:29`/`:59` vs spread
over all 30 phases of the half hour). The `:29` phase is the single best phase of
the half hour, by a margin larger than the entire scheduled-vs-crossing gap.

Mean signed gross pips per signal, 30-minute fixed horizon, entry `open(t+1)`:

| cell | scheduled (all on `:29`) | crossing, ALL phases | crossing, ON `:29` | crossing, OFF `:29` |
|---|---|---|---|---|
| EURUSD early | +0.646 | +0.413 | **+1.214** (n=1756, t=+4.81) | +0.380 |
| EURUSD late  | +0.695 | +0.222 | **+0.716** (n=475, t=+2.23)  | +0.206 |
| GBPUSD early | +0.637 | +0.383 | **+1.427** (n=1952, t=+5.42) | +0.336 |
| GBPUSD late  | +0.679 | +0.346 | **+1.377** (n=539, t=+2.94)  | +0.308 |

On-phase crossings beat the scheduled clock in 3 of 4 cells and tie in the fourth,
at matched RSI depth past the threshold (2.2-2.7 points on both arms — the depth
confound the earlier matching exercise correctly ruled out is genuinely absent
here). The published crossing average is just
`(1/30)*on-phase + (29/30)*off-phase`.

## Rule-23 reproduction

Seven of the eight published clock/pair/era means reproduce within 0.0021 pip. The
eighth, GBPUSD early first-crossing, comes out +0.3827 against a published
+0.3974 (-0.0147). Cause is an edge case in crossing detection: the original
requires `previous_rsi > threshold`, which drops crossings where the previous
minute's RSI is NaN (post-gap warm-up); the reproduction admits them. It does not
touch any conclusion below — every arm compares populations built the same way.

## What it is not

**Not depth.** Already rejected in `MEMORY.md`, and confirmed: at the matched
`tau == 0` / phase-`:29` cell the depths are 2.59 vs 2.43 (EURUSD early) and the
gap is still 3.2x.

**Not "state sampling finds a better state".** Within the scheduled clock,
expectancy *decays* with `tau`, the minutes since RSI entered the extreme:

| tau (min in zone) | EURUSD early | GBPUSD early | share of scheduled events |
|---|---|---|---|
| 0 | +0.903 | +1.036 | 33-34% |
| 1-2 | +0.660 | +0.763 | 32-33% |
| 3-5 | +0.654 | +0.417 | 18% |
| 6-10 | +0.082 | -0.210 | 10-11% |
| 11-20 | -0.241 | -0.002 | 4-5% |

A fresh crossing is the *best* state, not the worst. The scheduled clock's
all-`tau` average (+0.646) is a diluted version of its own `tau == 0` cell.

**Not length-biased sampling.** Scheduled sampling over-weights long extreme runs
(mean run length 6.3-7.4 min vs 3.2-3.5 for crossings), and long runs are
disastrous — first crossings into runs lasting 21-45 minutes average -17.4 pips
(EURUSD early). Reweighting the crossing population to the scheduled run-length
mix gives **-1.61 pips** (EURUSD) and **-1.99 pips** (GBPUSD). Length bias works
*against* the scheduled clock; it wins despite it.

## What it is: a first-minute effect at the top and middle of the hour

> **PARTLY SUPERSEDED 2026-08-04.** The phase placebo and the first-minute
> localisation below both replicate on two further sources. The `:00`/`:30`
> raw-return reversal spike offered here as the mechanism does **not** replicate
> on CME futures, so it is a spot-FX statement rather than the general
> explanation. See the cross-vendor section at the end.

**Phase placebo.** Running the scheduled clock at all 30 phases of the half hour,
phase `:29` is rank 30/30 in three cells and 29/30 in the fourth. Cross-phase
median is +0.257 to +0.463 against +0.637 to +0.695 at `:29`, with a cross-phase
sd of 0.11-0.15 — so `:29` sits roughly 3 sd above the rest of the distribution.

**Full-range confirmation, no threshold, ~107k rows per phase.** Spearman
IC(RSI, signed forward 30-min return) by phase, using every row rather than only
the 30/70 extremes: phase `:29` is the most negative (strongest mean reversion) of
30 phases in EURUSD early, GBPUSD early and GBPUSD late, and 2nd in EURUSD late.
So the phase effect is a property of the tape, not a small-sample artifact of the
extremes.

**It lives in the first traded minute.** Splitting the phase-`:29` excess over the
cross-phase median into the first minute and the remaining 29:

| cell | total excess | first minute | remaining 29 min | rank of `:29` on "rest" |
|---|---|---|---|---|
| EURUSD early | +0.363 | +0.184 | +0.171 | 30/30 |
| EURUSD late  | +0.438 | +0.302 | +0.135 | 24/30 |
| GBPUSD early | +0.282 | +0.293 | +0.015 | 17/30 |
| GBPUSD late  | +0.219 | +0.237 | -0.011 | 15/30 |

On GBPUSD it is *entirely* the first minute. Delaying entry and exit by one minute
(same signal phase, traded window moved off the boundary) drops the rank of `:29`
to 28/30, 26/30, 18/30, 22/30.

**Degenerate control: it is present with no RSI at all.** Unconditional lag-1
autocorrelation of one-minute open-to-open returns, by minute of hour, on every
row:

| minute | EURUSD ac1 | GBPUSD ac1 |
|---|---|---|
| median of 60 | -0.016 | -0.024 |
| `:00` | **-0.085** | **-0.082** |
| `:30` | **-0.062** | **-0.074** |
| `:59` | +0.004 | +0.003 |

A signal taken at the `:29` or `:59` close is entered at the `:30` or `:00` open —
the two minutes where one-minute reversal is 3-5x the median, and immediately
after `:59`/`:29`, which are among the *least* reversing minutes. The scheduled
clock is parked on a round-clock microstructure effect; the crossing clock samples
it 1 time in 30.

## Caveats

1. `:00`/`:15`/`:45`/`:59` have ~4% fewer contiguous rows than the median minute,
   so their `ac1` estimates rest on a slightly different sample. Far too small to
   produce -0.085 vs -0.016, but worth noting.
2. ~~Whether the boundary reversal is real market flow or an IBKR spot
   bar-construction artifact is not separated here.~~ **Resolved 2026-08-04 —
   see the cross-vendor section below. The finding replicates; the proposed
   mechanism only half does.**
3. Nothing here is a trade recommendation. The on-phase crossing cells are
   0.7-1.4 pip gross against a 0.5-1.0 pip realistic round trip, they are
   post-hoc within this investigation, n is 475-1952, and `MEMORY.md` already
   records that a one-minute feature lag roughly halves the edge — which is the
   same first-minute fragility this report localises. Any follow-up needs adverse
   execution and a first-minute return decomposition before it means anything.
4. The survival split in `rsi_clock_decomposition_results.json` arm E (crossings
   whose extreme survives to the next checkpoint average -4.6 to -5.7 pips,
   t about -35, versus +1.2 to +1.7 for non-survivors) is **not causal** —
   survival to the checkpoint is not known at the crossing. It is a descriptive
   restatement of "continuation kills this signal", not a filter.

## Consequence for the project

- Retract the framing that the scheduled clock carries information the crossing
  clock lacks. The "residual clock effect remains unexplained" line in `MEMORY.md`
  is now explained: it is the sampling phase.
- Any future clock comparison must be run at **matched sampling phase**, or the
  phase must be swept as a placebo. This is the same family as the workspace
  learning that a fixed threshold on a normalised feature is a time-of-day
  selector — here a fixed *schedule* is a minute-of-hour selector.
- The `:29` phase advantage was inside every scheduled-clock result this project
  has produced, including the range-break condition and the VEI interaction work.
  Those are not invalidated, but their baselines all sit on the best phase of 30.

---

# Cross-vendor / cross-venue check (2026-08-04)

Two independent sources were added to separate "real clock structure" from "IBKR
bar-construction artifact":

- **LSE** tick-derived 1-second bars, EUR/USD + GBP/USD, 2009-09 to 2012-02/04
  (`forex/data/lse/fx/`). Different vendor **and** an almost non-overlapping
  period — the original work started at 2012-01-01.
- **CME** Databento `GLBX.MDP3` `ohlcv-1m`, 6E + 6B continuous front, 2010-06 to
  2026-07 (`futures/data/databento/`). Exchange-reported prints from a central
  limit order book, with real volume. Returns are masked across contract changes.

Scripts: `_run_boundary_crosscheck.py`, `_run_boundary_crosscheck_aligned.py`,
`_run_phase_shape_crosscheck.py` (+ three JSON outputs).

## Result 1 — the FINDING replicates. 5 of 6 cells, three vendors, two venues.

Phase `:29` versus the other 29 phases, mean signed gross pips per RSI 30/70
signal, 30-minute horizon:

| source | phase `:29` | median of other phases | excess | rank of `:29` |
|---|---|---|---|---|
| IBKR EURUSD | +0.660 | +0.282 | +0.377 | **30/30** |
| IBKR GBPUSD | +0.647 | +0.381 | +0.267 | **30/30** |
| LSE EURUSD | +0.098 | -0.022 | +0.120 | 22/30 |
| LSE GBPUSD | +1.286 | +0.569 | +0.717 | **30/30** |
| CME 6E | +0.460 | +0.079 | +0.381 | **30/30** |
| CME 6B | +0.349 | -0.042 | +0.391 | **30/30** |

The full-range version (Spearman IC of RSI against the signed forward 30-minute
return, per phase, no 30/70 threshold, 26k-133k rows per phase) agrees: `:29` is
the most negative of 30 phases on LSE GBPUSD, CME 6E and CME 6B, and 3rd on LSE
EURUSD. The weak cell is LSE EURUSD, which is also the thinnest (2,155 signals
per phase) and has a near-zero base rate.

**So the phase confound behind "scheduled beats first-crossing" is real, is not
an IBKR artifact, and holds on exchange-reported futures and on 2009-2012 data
that no part of this project had seen.**

## Result 2 — the proposed MECHANISM only half replicates.

The claim was a one-minute reversal spike at `:00`/`:30`. Aligned lag-1
autocorrelation of one-minute close-to-close returns, labelled by ending minute
(the first pass compared IBKR open-to-open against LSE close-to-close, which are
offset by one minute because IBKR bars satisfy `open(t) == close(t-1)` exactly
and LSE bars do not; that mislabelling is fixed here):

| source | median ac1 | `:00` (rank/60) | `:30` (rank/60) |
|---|---|---|---|
| IBKR GBPUSD | -0.024 | -0.082 (**3**) | -0.074 (**4**) |
| LSE EURUSD | -0.016 | -0.094 (**1**) | -0.061 (**4**) |
| LSE GBPUSD | -0.022 | -0.177 (**1**) | -0.084 (**3**) |
| CME 6E | -0.378 | -0.385 (26) | -0.263 (**60**) |
| CME 6B | -0.350 | -0.276 (54) | -0.296 (45) |

On spot FX it replicates cleanly on the fresh vendor and survives an activity
control (regressing ac1 on log tick count across the 60 minutes; LSE GBPUSD `:00`
stays rank 1/60 on the residual). **On CME futures it is absent, and on 6E the
`:30` minute is the *least* reverting minute of the hour.** CME trade prints
carry bid-ask bounce an order of magnitude larger than any minute-of-hour
structure (ac1 about -0.35 everywhere), and activity at `:00` is roughly 2x the
median minute, so the raw CME profile is largely a liquidity profile; after the
activity control both CME contracts are unremarkable at `:00` and `:30`.

## Result 3 — the SHAPE is partly shared, and that is the honest reading.

Splitting each phase's result into the first traded minute and the remaining 29:

| source | excess in first minute | excess in remaining 29 | first-minute share |
|---|---|---|---|
| IBKR EURUSD | +0.213 (rank 30/30) | +0.145 (30/30) | 56% |
| IBKR GBPUSD | +0.284 (rank 30/30) | +0.000 (16/30) | 107% |
| LSE GBPUSD | +0.422 (rank 30/30) | +0.269 (26/30) | 59% |
| CME 6E | +0.139 (rank 30/30) | +0.247 (30/30) | 36% |
| CME 6B | +0.198 (rank 30/30) | +0.239 (29/30) | 51% |

The first-minute component is rank 30/30 in every cell including both futures
contracts. But on CME the *remaining 29 minutes* also rank 30/30 and 29/30 and
carry more of the excess than the first minute does — so on futures the phase
advantage is broader than a single-minute microstructure effect, which is
consistent with the raw-return reversal spike being absent there.

## Revised verdict

- **Confirmed:** the scheduled-vs-first-crossing comparison is a sampling-phase
  confound, and phase `:29` is genuinely the best phase of the half hour. This
  now rests on three vendors, two venues, and a fresh 2009-2012 sample.
- **Partly rejected:** "the schedule is parked on a `:00`/`:30` one-minute
  reversal spike" is a spot-FX statement, not a general one. It does not hold on
  CME, and CME shows the phase advantage just as strongly without it. The
  mechanism is therefore **open again** — what is established is that the effect
  is concentrated near the start of the trade everywhere, and extends further
  into the holding period on futures.
- Rule-19 note carried from workspace learnings: 6E's tick halved in 2016, so any
  cost statement on these CME cells must be quoted per era, not in ticks across
  the whole sample. Nothing here is costed; all numbers are gross.
