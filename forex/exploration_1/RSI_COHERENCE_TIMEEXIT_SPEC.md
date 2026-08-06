# Frozen specification — cross-pair coherence gate and time-based non-reversion exit

Written before either run. Arms, metrics, controls and kill tests below are fixed;
any post-run addition is labelled a disclosed amendment in the report, never a pass.

Two deployment facts are declared up front, because they change the estimand rather
than decorating it. Both were supplied by the user before any run.

1. These strategies are intended for a **prop-firm challenge in which a
   single-price-barrier stop loss is COMPULSORY on every trade**. The unconstrained
   fixed-horizon return is therefore no longer the relevant target. Every headline
   number in both arms is measured **with a stop already in place**, and the no-stop
   column is carried only as a reference for
   `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md` continuity.
2. Decisions are **not** taken on a fixed `:29`/`:59` clock. That grid was
   exploration scaffolding. Every signal here is an **event**: the first minute at
   which the entry condition becomes true. This also removes a defect this project
   has already documented — `RSI_CLOCK_CONFOUND_REPORT.md` found the `:29` schedule
   is a minute-of-half-hour selector ranking 30/30 among 30 phases — so the change
   is a correction, not only a preference.

## 0. Common construction

- Pairs EURUSD, GBPUSD, AUDUSD, NZDUSD; one-minute midpoint OHLC from
  `forex/data/clean/*_1m_clean.parquet`. 2012-01-01 to 2023-12-29. **2024+ is
  sealed and is not read.** Era split 2021-01-01.
- **Event clock.** A signal fires at minute `i` when the entry condition is true at
  `i` and was **not** true at `i-1`; a non-contiguous minute always starts a new run,
  so a condition is never carried across a weekend, holiday or gap.
- **Non-overlap is enforced (rule 13).** A trade holds 30 minutes, so the next
  accepted signal must be at least 30 minutes after the last accepted entry. Only
  one position is open at a time, which is what a single challenge account runs. The
  overlapping variant is reported once as a statistical-power sensitivity only.
- Entry at `open(i+1)`. Baseline exit at `open(i+31)`, i.e. a 30-minute hold.
- A trade is admitted only if minutes `i .. i+32` are **exactly contiguous**.
- Because every signal is a first crossing, every trade is `age == 0` in the sense
  of `RSI_THRESHOLD_FRESHNESS_REPORT.md`. That report found age 0 is the best state
  **and** that 85% of its advantage is the first traded minute, so the one-minute
  delay arm is a **primary** result here, not a sensitivity.
- The **minute-of-half-hour phase distribution of accepted events is reported** as a
  placebo axis, per this project's standing requirement. Concentration on `:29`/`:59`
  would mean the event clock had reproduced the schedule and must be reported.
- The expansion-gate cutpoint is fitted on the **early era only** and applied
  unchanged to the late era. The audited fixed-clock script took that quantile over
  the whole sample, which is a two-sided statistic; this removes it.
- Two entry signals, both reported at every stage:
  - **`gated`** (primary; the surviving system after
    `RSI_THRESHOLD_FRESHNESS_REPORT.md`): `|z| >= 1.5` with **no volatility scaling**,
    AND the ATR(14)/ATR(50) causal same-slot z-score in its top 40%.
  - **`rsi3070`** (bridge to every earlier report): Wilder RSI(14) <= 30 long,
    >= 70 short.
- `z = (log P - log EMA20) / sd`, `sd` the exact 120-minute rolling std of the
  displacement series.
- **Risk unit `sigma`** = trailing RV(30) in pips at the entry price
  (`rv_30m * 1e4 * entry_px`). Declared primary because it is what a deployed system
  can compute at the entry bar with no slot machinery. The causal expected-slot unit
  (`prior same-slot median forward RV(30)`, 90 sessions) is carried as a sensitivity
  because the published table uses it.
- Every result is reported in **both mean pips and mean R** (`pips / sigma`), and the
  **implied risk unit `mean_pips / mean_R`** is printed beside every rule comparison,
  per `ai_shared_memory/LEARNINGS.md` 2026-08-04. A comparison whose pips ranking and
  R ranking disagree is reported as a risk-unit difference, not an edge difference.
- Inference: per-signal mean with session-clustered t (rule 12). Never
  session-averaged.
- Costs: reported at 0.2, 0.5 and 1.0 pip round trip. The true spread remains
  unmeasured, so no net tradability claim is permitted from either arm.

## 1. The compulsory stop

Single price barrier, so there is no intrabar stop-versus-target ordering to resolve
(rule 3 is satisfied by construction; there is no second barrier).

- Long stop at `entry - k*sigma`; short at `entry + k*sigma`.
- Triggered on the first minute in `i+1 .. i+30` whose low (long) or high (short)
  reaches the level. **The entry bar `i+1` is included** (rule 3).
- Fill (rule 5): at the stop level, unless the minute **opened beyond** it, in which
  case at that open. A `slippage` variant adds a further fixed adverse amount.
- Grid `k in {1.0, 1.5, 2.0, 3.0}` plus `inf` (no stop, reference only).
  **Primary `k = 2.0`**, chosen before the run from the published sweep as the
  widest level whose stop rate (~9.5%) still caps per-trade risk at a level a
  challenge drawdown limit can carry.
- Slippage `{0.0, 1.0}` pips. **Primary 1.0 pip**, because
  `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md` already established that crediting the
  exact stop level is what makes stops look survivable, and a challenge account does
  not get the optimistic fill.

## 2. Arm 3 — cross-pair coherence as a regime filter

### Mechanism claim

All four pairs are quoted against USD, so a USD repricing moves all four the same
way. The claim is that a displacement **shared with the other three pairs** is a
macro move that continues, while a displacement **specific to one pair** is the
inventory or noise event this strategy is designed to fade. This is the direct test
of the user's "gate the signal if we are entering a new trending regime" question,
using the only genuinely cross-sectional information in the dataset.

### Feature, causal and self-exclusive

At each decision bar, for each pair `p`:

- `u_p = r30_p / rv30_p`, where `r30_p` is the exact 30-minute trailing log return
  and `rv30_p` the exact 30-minute realised volatility. Signed and unit-free.
- `others_p = mean(u_q)` over the **three pairs other than `p`**, on the exact same
  timestamp. Own pair is excluded so the feature cannot mechanically restate `|z|`.
- `coh_p = sign(u_p) * others_p`. Positive when the pair moves with the basket
  (a USD move), negative when it moves against it.
- **`coh_pct`** = causal same-slot percentile of `coh_p` over the prior 90 sessions.

A decision is admitted only if all four pairs have an exact synchronized timestamp
and a defined `u`. Coverage loss is reported per pair and per session block (rule
9a); if it is concentrated in any time block that is reported as a finding.

### Primary metric and kill test

Primary: **mean R per bet under the compulsory stop (`k = 2.0`, 1.0 pip slippage)**,
comparing the bottom `coh_pct` tercile (idiosyncratic) against the top
(broad USD move), at equal selection rate by construction.

- **SUPPORTED** requires all four:
  1. idiosyncratic beats broad in **>= 3/4 pairs**, median gap **>= +0.02 R**;
  2. the gap retains **>= 50%** of its size when the split is run **within
     volatility quintiles as well as within slots** (LEARNINGS 2026-07-31c — matching
     on time of day alone is not sufficient);
  3. it beats a **rate-matched own-pair-only control** (tighten `|z|` to the same
     keep fraction) in **>= 3/4 pairs**, in R units;
  4. a **re-pairing null** (the other three pairs' `u` taken from a different date at
     the same slot and era, 200 draws) centres near zero and the real gap falls
     outside the central 90% of the null distribution.
- **REJECTED** if the sign reverses, if the volatility-matched split removes more
  than half the gap, if the own-pair-only control matches it, or if the null does not
  separate.
- If the sign reverses — i.e. **broad** moves fade better than idiosyncratic ones —
  that is reported as the headline, because it directly contradicts the stated
  mechanism and this project has already had one mechanism invert on a fresh sample.

Reported alongside, not as criteria: the monotonicity of the quintile profile, the
stop-out rate by `coh_pct` cell (the tail-avoidance channel the filter is supposed
to work through), and the same split on the no-stop return.

## 3. Arm 4 — time-based non-reversion exit

### Mechanism claim

The worst 1% of trades remove 52-79% of gross P&L. A trade that has not begun to
revert some minutes after entry is the observable early state of that tail. Exiting
it early should cut the left tail at a smaller cost than the compulsory stop does,
because it acts before the adverse excursion is complete.

### Rule, causal

At elapsed minute `N`, observe `close(i+N)` and exit at `open(i+1+N)` if the
non-reversion condition holds; otherwise hold to `open(i+31)`. The compulsory stop
remains live throughout and takes precedence if it triggers first.

- Conditions: **(a) position P&L <= 0** (primary), **(b) position P&L <= -0.25 R**.
- `N in {5, 10, 15, 20}`. **Primary `N = 10`, condition (a)**.

### Degenerate controls, declared as decisive

1. **Matched-rate tighter stop.** The time exit closes some fraction `f` of trades
   early; a stop at the `k'` that stops the same fraction `f` is the degenerate
   alternative. **If the matched-rate stop matches the time exit, the finding is
   "this is a stop", not "time carries information", and the arm is REJECTED.**
2. **Matched-rate random-time exit.** Exit a random `f` of trades at minute `N`
   regardless of their state. Separates information from reduced exposure.
3. **Unconditional exit at `N`** for every trade — the horizon-sweep degenerate,
   already known to lower gross.

### Kill test

- **SUPPORTED** requires the conditional time exit to beat hold-to-30 in mean R in
  **>= 3/4 pairs by >= +0.02 R**, **and** to beat both control 1 and control 2 in
  **>= 3/4 pairs**.
- **REJECTED** otherwise, and explicitly rejected if control 1 ties it.

## 4. Reported for both arms regardless of verdict

- Mean pips, mean R, implied risk unit, cluster t, hit rate, stop-out rate,
  signals/year, worst-1% and worst-5% share of gross.
- **Session-level risk (rule 22), because a challenge is judged on drawdown, not on
  per-trade expectancy**: daily P&L in R, worst day, and maximum peak-to-trough
  drawdown of the cumulative per-bet R curve.
- **A one-minute entry delay on every headline cell.** This project has documented
  that 85% of one component and a large share of the base edge is the first traded
  minute; a component that does not survive the delay is not deployable here.
- Era split. A gain carried by the early nine years is not promoted.

## 5. Rule-23 reproduction, declared before the run

The clock change means the published fixed-clock means are **not** the right
reproduction target — a different clock is a different sample, and this project has
already measured that the two clocks differ. Reproduction is therefore declared
against the published **first-crossing** numbers in
`RSI_CLOCK_CONFOUND_REPORT.md` / `MEMORY.md`:

- all-phase first-crossing RSI 30/70 gross: **0.397-0.418 pip in 2012-2020** and
  **0.220-0.341 pip in 2021-2023**, EURUSD and GBPUSD.

Target: the no-stop, no-delay, era-split `rsi3070` event cells for those two pairs
land inside those published ranges. Tolerance is the published range itself, widened
by **0.05 pip**, because the published crossing figures used a 30-minute cooldown
without the exact 32-minute contiguity requirement or the non-overlap rule applied
here. The admitted-sample difference is reported explicitly.

Carried as context, not as a reproduction target because the clock differs: the
fixed-clock published values were RSI 30/70 no-stop per-pair 0.659 / 0.648 / 0.521 /
0.544, and the trailing-RV-unit stop sweep ran 0.605 (no stop) to 0.617 (3.0 R).
An unexplained difference is carried as a limitation, not silently absorbed.

## 6. Out of scope

- No null is run on arm 4 (rule 17 remains outstanding for it); its degenerate
  controls are the substitute and this is declared, not discovered.
- The bid/ask spread is still unmeasured. Neither arm can produce a net tradability
  claim.
- 2024+ is not opened by either script.
