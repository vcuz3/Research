# Frozen spec — the z / RSI mean-reversion system on a FIVE-MINUTE bar clock

Written before the run (rule 24). Origin: user asked to try the z-score / RSI
mean-reversion strategy "on the 5 minutes instead of 1, first crossing, with
appropriate volatility regimes (using the conditions we have created so far)".

## 1. Why this is a real question and not a reparameterisation

Everything this project has established about the surviving system is a
one-minute result, and two of its recorded weaknesses are explicitly
one-minute-scale:

- `RSI_CLOCK_CONFOUND_REPORT.md`: the effect concentrates in the **first traded
  minute**, and the fixed `:29`/`:59` grid was a minute-of-half-hour selector.
- `RSI_COHERENCE_TIMEEXIT_REPORT.md`: the event clock keeps 72% of pips under a
  **one-minute** entry delay — better than the scheduled clock's 15%, but the
  fragility is still measured in single minutes.

A five-minute decision bar cannot trade one-minute microstructure at all. So the
question is not "does a slower clock give a bigger number" but **how much of the
established edge is a sub-five-minute effect**. Both possible answers are
informative.

## 2. Construction

**Bars.** 1-minute midpoint OHLC resampled to non-overlapping 5-minute bars,
grouped by `floor((epoch_minutes - phase) / 5)`, default `phase = 0` (bars start
on `:00`, `:05`, ...). A bar is **valid** only if all five constituent minutes are
present; invalid bars break recursion and break contiguity, exactly as a missing
minute does on the 1-minute clock.

**Parameters are preserved in BAR units**, i.e. the strategy is transplanted to a
slower clock rather than re-tuned:

| quantity | 1-minute study | this run |
|---|---|---|
| displacement anchor | EMA(20) of log close | EMA(20) of 5m log close (100 min) |
| `z` scale | rolling sd, 120 bars | rolling sd, 120 bars (600 min) |
| RSI | Wilder(14) | Wilder(14) on 5m closes (70 min) |
| expansion feature | Wilder ATR(14)/ATR(50) | same, on 5m true range |
| same-slot normaliser | 90 prior sessions, 1440 slots | 90 prior sessions, 288 slots |
| horizon `H` | 30 bars = 30 min | 30 bars = 150 min (primary) |
| risk unit `sigma` | trailing RV over 30 bars | trailing RV over `H` bars |

The risk unit is always "trailing realised volatility over one holding period",
which is what the 1-minute study used; that convention is what makes mean R
comparable across clocks. `H = 6` (30 min, **time-matched to the published
1-minute result**) and `H = 12` (60 min) are also run so that any difference
between clocks can be split into "slower features" and "longer hold".

**Signals.** First crossing (rule: the condition is true at this bar and was not
true at the previous *contiguous* bar), non-overlap enforced — one position at a
time, cooldown `H` bars.

**Execution.** Decision at 5m bar close, entry at the **next 5m bar's open**.
Compulsory single-barrier stop at `2.0 R`, 1 pip adverse slippage, rule-3 entry
bar inside the stop scan, rule-5 gap-through fills at the open.

**The stop is resolved on the underlying ONE-MINUTE path, not on 5m bars.** A 5m
bar can open beyond the stop level only if its first minute did, but a *later*
minute inside that bar can open beyond the level with the 5m bar showing no gap;
scanning 5m bars would credit the exact stop level there. Scanning 1-minute bars
is the conservative choice and the data is already loaded.

## 3. Arms

Frontier (the reference): `|z| >= k` for `k` in
{1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0}.

Trigger check: `rsi <= t / >= 100-t` for `t` in {35, 30, 25, 20, 15}, and
`z1.5 AND rsi 30/70`. This project has already shown on the 1-minute clock that
RSI and `z` are the same variable (Spearman 0.9684) and that stacking is
negative; the check is whether that survives the slower clock, where RSI(14) spans
70 minutes and `z` spans 100.

Regime gates, on the fixed `|z| >= 1.5` base, all cutpoints fitted on the
**early era only** (2012-2020) and applied unchanged to the late era:

- `ATR expansion 40` — `vei_atr_z` in the top 40% (volatility ACCELERATION);
- `rv pct 40` — trailing-RV same-slot percentile in the top 40% (LEVEL);
- `rv pct 20` — top 20%;
- `ATR40 + rv40` — the conjunction, which is the family confirmed against a
  claim-matched null in `RSI_GATE_NULL_REPORT.md`.

## 4. Primary metric and kill test

Primary metric, unchanged from `RSI_Z_REGIME_MATRIX_SPEC.md`: **mean R in excess
of the `|z|` frontier**, linearly interpolated in `log(signals per year)` to the
arm's own selection rate. An arm sitting on the frontier bought selectivity, not
information.

Per arm:

- **SUPPORTED** — median excess `>= +0.005 R` and `>= 3` of 4 pairs at `>= +0.005`;
  downgraded to *supported-but-fragile* if either the one-bar-delay or the
  late-era excess is negative.
- **REJECTED (selectivity dial)** — median excess inside `+/-0.005 R`.
- **REJECTED (worse than frontier)** — median excess `<= -0.005 R`.

Separately, for the clock comparison itself:

- **The five-minute clock is preferred** only if, at the time-matched horizon
  `H = 6`, its base `|z| >= 1.5` arm delivers mean R at least as high as the
  published one-minute figure (`0.0230 R` ungated, `0.0451 R` for the combined
  gate) at a comparable or better delay-retention. Slower features that merely
  trade less often for the same R per unit risk are a turnover setting, not an
  improvement.
- **The one-minute effect is sub-five-minute** if the 5m base R is materially
  below the 1m base R at matched horizon. That is a real finding, not a failure.

## 5. Declared controls

1. **Phase placebo (mandatory).** A 5-minute grid has five possible offsets and
   this project has already been burned once by a clock phase
   (`RSI_CLOCK_CONFOUND_REPORT.md`, phase `:29` rank 30/30 of 30). The base and
   combined-gate arms are run at all five offsets. If the default `phase = 0`
   result is an outlier of the five, the result is a phase artifact and is
   reported as such rather than as a clock finding.
2. **Delay.** Entry and exit shifted one full 5-minute bar later, holding period
   unchanged. On the 1-minute clock a one-*minute* delay cost 28% of pips; a
   five-minute clock that loses less to a five-minute delay is genuinely more
   robust, and one that loses more has simply moved the fragility.
3. **Era split.** 2012-2020 fitted / 2021-2023 applied, reported separately.
4. **Horizon sweep.** `H` in {6, 12, 30} bars, risk unit rescaled to each, so a
   clock effect is not read off a horizon change.
5. **Rule 9a data quality**, reported before any result is interpreted: 5-minute
   bar count and the share built from a complete set of five minutes, per pair
   and per era; events dropped for an incomplete holding path; coverage of the
   same-slot normalisers, checked for a time-of-day gradient.

## 6. What is NOT in scope

- No null (rule 17). This is a clock-transfer measurement of an already-nulled
  family; if the 5-minute clock produces a new leading candidate, a claim-matched
  null in the style of `_run_rsi_gate_null.py` is required before promotion.
- No spread model. Midpoint data only; net figures at 0.2 / 0.5 / 1.0 pip round
  trips are cost stress, not tradability.
- The 2024+ holdout stays sealed.

## 7. Reproduce

    python -u _run_rsi_five_minute_clock.py
