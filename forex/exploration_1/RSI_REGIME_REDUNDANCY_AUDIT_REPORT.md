# RSI volatility-regime features — redundancy and no-RSI audit

> **REVIEW ADDENDUM — 2026-08-04.** The redundancy and mechanism corrections in
> this audit are accepted: use canonical same-slot RV(30) and RV(5) percentiles,
> and withdraw the “surprise” and nonlinear-synergy labels. Two conclusions below
> are narrowed. First, rho near 0.98 means near-redundant for the within-slot rank
> estimand, not literal identity; frozen top-bin Jaccard overlap is about
> 0.60-0.73. Second, reproducing the regime gradient without RSI proves a generic
> short-horizon-reversion channel but does not prove that RSI has no incremental
> regime interaction. In a post-audit clustered rank regression controlling for
> trailing 1m and 30m returns and both return x regime interactions, RSI x regime
> remains negative in all four pairs (beta -0.044 to -0.093; t -2.75 to -5.74).
> Therefore “both features fail” is read as failure of novelty/attribution, not
> failure of the underlying RV-conditioned RSI measurement. Also, RV(30) and
> RV(5) are two distinct canonical levels; they do not all collapse to one
> underlying variable.

## Verdict

Two arms were run against the features carried forward by
`RSI_JOINT_VOLATILITY_REGIME_REPORT.md` and
`RSI_SURPRISE_ACCELERATION_INTERACTION_REPORT.md`. Both features fail.

1. **Redundancy.** At the metric those reports use — within-slot rank correlation —
   each recommended feature is the same variable as a same-slot percentile the
   project already had. `log(RV_30m / E[RV_30m])` correlates **+0.975 to +0.977**
   with `rv_30m_pct_90d`; `log(RV_5m / E[RV_30m])` correlates **+0.982 to +0.983**
   with the same-slot percentile of RV(5). Both hold on all four pairs.
2. **No-RSI degenerate control.** The surprise-quintile gradient in reversion
   strength is reproduced with RSI removed from the pipeline. A median **62%** of
   the Q5−Q1 gradient survives using the raw trailing 30-minute return, and a
   median **74%** survives using the trailing **one-minute** return alone.

The consequence is that neither report's headline is about the feature it names,
and the regime effect both are built on is a property of short-horizon reversion
rather than of RSI. The joint report's §2 and the acceleration report's §1 and §3
verdicts should be marked superseded. Rule 25 applies: the negative evidence is
preserved, and the underlying measurements in those reports remain valid — it is
their attribution that is withdrawn.

This audit adds no new tradable claim. It removes two.

## Frozen setup

Unchanged from `RSI_BROAD_REGIME_SWEEP_SPEC.md` and the two audited specs:
EURUSD, GBPUSD, AUDUSD, NZDUSD one-minute midpoint OHLC, 2012-2023, New York
17:00 session boundary, `:29`/`:59` decisions, next-minute-open entry, exit at
the open exactly 30 minutes later. The 2024+ holdout is untouched by this audit.

Both arms reuse `build_pair` from the broad sweep unmodified, so feature
construction, causality, and coverage are identical to the audited runs. Two
quantities are added:

- `rv_5m_raw = rv_ratio_5_30_raw × rv_30m_raw`, an exact reconstruction of the
  5-minute realized volatility already implicit in the panel;
- `past_ret_30m_bp` and `past_ret_1m_bp`, gap-exact trailing returns at the
  decision bar, computed with the sweep's own `exact_lag`.

Feature causality was re-verified in code before running: `prior_slot_median` and
`causal_slot_percentile` both `shift(1)` before rolling, so the expected-volatility
term uses only prior sessions at the same slot.

## 1. Redundancy — the recommended features are same-slot volatility percentiles

Within-slot Spearman is the decisive statistic here because it is the statistic
the audited reports use to measure RSI information. Pooled correlation is shown
alongside it, and the two differ materially for a reason given below.

### 90-session memory (both reports' preferred default)

| Comparison | EURUSD | GBPUSD | AUDUSD | NZDUSD |
|---|---:|---:|---:|---:|
| 30m surprise vs **RV(30) slot percentile** | **+0.9774** | **+0.9766** | **+0.9765** | **+0.9754** |
| fast surprise vs **RV(5) slot percentile** | **+0.9826** | **+0.9833** | **+0.9834** | **+0.9818** |
| fast surprise vs RV(5)/RV(30) acceleration | +0.6857 | +0.6950 | +0.6993 | +0.7154 |
| fast surprise vs 30m surprise | +0.6302 | +0.6091 | +0.6179 | +0.5919 |

Top-quintile membership overlap is 0.803-0.828 for the first row and 0.830-0.856
for the second. The 30-session sensitivity agrees and is slightly weaker
(+0.947 to +0.950 and +0.958 to +0.962).

### Why the denominator does nothing at this metric

The initial framing of this audit — that the ratio is "mostly its numerator" — was
wrong and is corrected here. Pooled across slots the expected-volatility
denominator carries real variance: `var(log denominator)` is 0.22 against
`var(log numerator)` 0.38 on EURUSD, and pooled `ρ(surprise, log numerator)` is
only +0.55 to +0.72.

The variance it carries is the **time-of-day seasonal cycle**. That cycle is then
removed three separate times over: once by the denominator, once by
`causal_slot_percentile`'s within-slot ranking, and once again by measuring IC
within slot. Inside a slot the denominator is a slowly-rolling 90-session median
with almost nothing left to contribute, which is why the within-slot correlation
reaches 0.977 while the pooled correlation is 0.912. The correct description is
three redundant de-seasonalisations, not a constant denominator.

This is the reason `RSI_JOINT_VOLATILITY_REGIME_REPORT.md` §3 finds an increment
of only +0.0028 IC and +0.016 pip over current-RV percentile: that increment is
what an 18% reshuffle of top-quintile membership produces on its own. §3 is the
identity diagnostic for §2, and its verdict should have been read back into §2.

### What the acceleration report's "synergy" actually is

`RSI_SURPRISE_ACCELERATION_INTERACTION_REPORT.md` correctly identifies the
algebraic identity `RV(30)/E[RV(30)] × RV(5)/RV(30) = RV(5)/E[RV(30)]` and
declines to stack all three ratios. Taken one step further, the collapsed feature
correlates only ~0.69 with the acceleration axis and ~0.61 with the surprise axis:
it is **neither of its two parents**. What the product measures is the
short-horizon volatility level, which neither axis measures alone.

The high-surprise/high-acceleration corner is therefore high RV(5). The reported
"strengthening three-way sign in 8/8" is not evidence of a nonlinear interaction
between two regime variables; it is an additive statement about a third variable
that both axes partially proxy. This is consistent with that report's own
observation that the sign is stable while coefficient-level inference is weak
(median |t| 1.47, 1/8 with q < 0.10) — the sign of a mislabelled main effect is
stable, its interaction coefficient is not.

## 2. No-RSI control — the regime gradient is not about RSI

Rows are split into frozen quintiles of the joint report's preferred feature
(`surprise_90d`, cutpoints from 2012-2020). `ic_rsi` reproduces the audited
metric. `ic_past_30m` and `ic_past_1m` are the identical within-slot IC computed
against the raw trailing return, with **no RSI anywhere in the arm**. More
negative means stronger mean reversion.

| Pair | Metric | Q1 | Q2 | Q3 | Q4 | Q5 | Q5−Q1 strength |
|---|---|---:|---:|---:|---:|---:|---:|
| EURUSD | ic_rsi | −0.0496 | −0.0564 | −0.0632 | −0.0708 | −0.0686 | 0.0190 |
| | ic_past_30m | −0.0329 | −0.0464 | −0.0543 | −0.0566 | −0.0518 | 0.0189 |
| | ic_past_1m | −0.0250 | −0.0389 | −0.0373 | −0.0487 | −0.0539 | 0.0289 |
| GBPUSD | ic_rsi | −0.0392 | −0.0584 | −0.0684 | −0.0651 | −0.0811 | 0.0418 |
| | ic_past_30m | −0.0331 | −0.0491 | −0.0558 | −0.0537 | −0.0559 | 0.0229 |
| | ic_past_1m | −0.0189 | −0.0324 | −0.0475 | −0.0441 | −0.0551 | 0.0362 |
| AUDUSD | ic_rsi | −0.0394 | −0.0456 | −0.0456 | −0.0604 | −0.0643 | 0.0249 |
| | ic_past_30m | −0.0314 | −0.0378 | −0.0319 | −0.0462 | −0.0428 | 0.0114 |
| | ic_past_1m | −0.0248 | −0.0367 | −0.0339 | −0.0515 | −0.0401 | 0.0153 |
| NZDUSD | ic_rsi | −0.0310 | −0.0379 | −0.0557 | −0.0620 | −0.0928 | 0.0619 |
| | ic_past_30m | −0.0303 | −0.0289 | −0.0426 | −0.0524 | −0.0735 | 0.0432 |
| | ic_past_1m | −0.0138 | −0.0290 | −0.0362 | −0.0392 | −0.0498 | 0.0360 |

Share of the RSI gradient surviving without RSI:

| Pair | via past 30m return | via past 1m return |
|---|---:|---:|
| EURUSD | 1.00 | 1.53 |
| GBPUSD | 0.55 | 0.87 |
| AUDUSD | 0.46 | 0.62 |
| NZDUSD | 0.70 | 0.58 |
| **Median** | **0.62** | **0.74** |

The volatility-surprise feature conditions short-horizon reversion in general. It
is not selecting states in which RSI specifically becomes informative, which is
what both audited reports claim for it.

### Two findings in favour of the audited reports

- **RSI is not decoration.** It beats the raw trailing return by roughly 0.015 to
  0.020 of IC in essentially every quintile of every pair. It adds something over
  "fade the recent move" — just not the thing either report is about.
- **The P&L arm behaves differently from the IC arm.** The no-RSI fade is positive
  in all 20 cells but non-monotone, and it is weakest exactly at Q5 (EURUSD +0.100
  pip, t 0.58; GBPUSD +0.187, t 0.50) where the RSI arm is strongest (+0.83 to
  +1.35). This is the rank-versus-mean divergence recorded in
  `ai_shared_memory/LEARNINGS.md` (2026-07-31, item a), and it means the two arms
  should not be collapsed into one verdict.

The P&L gradient is also substantially a scale effect. `mean_abs_forward_bp` rises
from 3.79 to 6.34 (EURUSD) and 5.58 to 8.75 (NZDUSD) across quintiles, so Q5 earns
more pips partly because Q5 is more volatile — rule 19. The scale-free metric is
the IC one, and that is the metric that reproduces without RSI.

## 3. Limitations and what was not tested

- **This is not a null.** Neither the audited reports nor this audit runs a
  claim-matched null through the pipeline (rule 17). The redundancy result does
  not need one — it is a correlation between two constructed features, not an
  effect estimate. The no-RSI result would benefit from one.
- **The phase confound is untested here.** All decisions sit at `:29`/`:59` with
  entry at the `:00`/`:30` open, which this project's own clock work found to be
  rank 30/30 among 30 phases, with the effect concentrated in the first traded
  minute (`RSI_CLOCK_CONFOUND_REPORT.md`). That `ic_past_1m` also strengthens
  across surprise quintiles is *consistent* with the regime feature modulating a
  first-minute microstructure effect, but it does not establish it. The decisive
  arm is the one-minute-delayed entry and exit already implemented for the clock
  work, rerun within surprise quintiles. It has not been run.
- **Cell independence.** Both audited reports count agreement over eight pair-era
  cells. Four of the eight are the early era, which is where the cutpoints were
  fitted and which holds most of the data; and AUDUSD/NZDUSD and EURUSD/GBPUSD are
  not independent draws. Effective sample is nearer two or three than eight. This
  audit does not repair that counting — it notes that the vote-count evidence in
  both reports is weaker than it appears.
- **Economics unchanged and unpromising.** The audited Q5 cells are 0.97 to 1.22
  gross pips on midpoint bars against a 0.5-1.0 pip round trip, on consumed
  history, with no spread model and no capacity statement. Half-hour boundaries
  are the worst moment to assume a median spread.

## Decision

1. Mark `RSI_JOINT_VOLATILITY_REGIME_REPORT.md` §2 and its Decision items 1 and 3
   **superseded**. The feature to carry, if any, is `rv_30m_pct_90d`, which the
   project already had; the surprise ratio is a reparameterisation of it.
2. Mark `RSI_SURPRISE_ACCELERATION_INTERACTION_REPORT.md` §1 and §3 **superseded**.
   The collapsed fast-surprise feature is the same-slot percentile of RV(5), and
   the reported synergy is a main effect of short-horizon volatility.
3. Do not spend further work on volatility-regime *parameterisation*. Three
   variants have now resolved to the same underlying variable at ρ ≥ 0.975.
4. Before any further RSI regime work, run the one-minute-delayed entry/exit arm
   within surprise quintiles. If the gradient collapses the way phase `:29` did,
   the whole family is a first-minute microstructure effect and the RSI framing
   should be retired rather than refined.
5. Holdout 2024+ remains sealed. Nothing here consumes it.

## Evidence

- Reproduction: `_run_rsi_regime_redundancy_audit.py`
  (`python -u _run_rsi_regime_redundancy_audit.py`)
- Full results: `rsi_regime_redundancy_audit_results.json`
- Redundancy table: `rsi_regime_redundancy_audit_redundancy.csv`
- No-RSI quintiles: `rsi_regime_redundancy_audit_no_rsi_quintiles.csv`
- Audited reports: `RSI_JOINT_VOLATILITY_REGIME_REPORT.md`,
  `RSI_SURPRISE_ACCELERATION_INTERACTION_REPORT.md`
- Related: `RSI_CLOCK_CONFOUND_REPORT.md` (the untested phase arm),
  `ai_shared_memory/LEARNINGS.md` 2026-07-27 (degenerate no-denominator control),
  2026-07-31 item a (rank versus mean)
