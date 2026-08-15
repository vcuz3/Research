# Independent review — EXP-0004 Stage-B reference book

**Reviewer:** Codex  
**Review date:** 2026-08-09  
**Status:** changes required before EXP-0004 is used as the Stage-C ruler

## Scope and verification

Reviewed the frozen report, hypothesis, kill test, configuration, verdict and run
manifest; inspected `_run_stage_b.py`, `_stage_b_lib.py`, and `test_stage_b.py`; and
queried the committed `trades.parquet` artifact. The report copy under `reports/` is
byte-identical to the run artifact. The reported tables agree with `verdict.json`.

Verification command:

```powershell
python -m pytest forex/exploration_4/test_stage_b.py -q -p no:cacheprovider
```

Result: **12 passed** (one third-party deprecation warning).

The numerical transcription is sound. The issues below concern the estimand,
execution semantics, coverage reporting, and interpretation.

## Findings

### 1. High — headline metrics do not represent the stated one-position book

The report states that the book permits one position per pair, enforced with greedy
non-overlap, but applies that policy only to the Sharpe calculation. The primary
gross/net result, confidence intervals, era splits, pair/session tables, cost curve,
and holdout result use every hypothetical signal, including overlapping positions.

- Primary consumed result: 137,807 signal-level observations.
- Consumed one-position book: 66,399 executed trades.
- Code path: `book_surface()` aggregates all trade rows; only `book_sharpes()` calls
  `greedy_non_overlap()`.

The primary estimand therefore does not describe the declared deployable policy. This
is especially consequential for Stage C: an overlay can change exits and holding
periods, which changes which later signals survive the stateful non-overlap rule.
Filtering already-completed overlapping trades at matched count cannot reproduce that
book.

**Required correction:** apply the one-position state transition before every metric
labelled as the book, and rerun the frozen reference plus future overlay comparisons
through identical stateful machinery. Signal-level results may remain as a separately
labelled diagnostic.

### 2. High — already-crossed exit limits use non-deployable order semantics

For 6,355 of 166,395 valid delay-1 signals (3.8%), the entry price had already crossed
the anchor in the favourable direction before entry. `simulate_anchor_retrace()` marks
the anchor as invalid and holds these positions to the time cap. The parity test
explicitly freezes that behavior.

A limit at an already-crossed price is marketable. Under the stated strategy it should
execute immediately at a price supported by the data, or the completed-retrace signal
should be rejected before entry. Holding to the cap is not the behavior of the order
described in the report. On the current artifact these rows average -0.034 pips and
+0.0138 R_slot under the timeout treatment, so the direct pooled mean impact is small;
the effect on non-overlap, occupancy, and overlay eligibility remains unmeasured.

**Required correction:** prespecify either immediate marketable-limit handling or a
causal no-entry rule, add parity fixtures, and rerun the stateful book.

### 3. Medium — time and touch treatments are not payoff bounds

The report calls the time exit a floor, touch a ceiling, and the three treatments a
bracket. Its own pooled table disproves the floor claim: guarded gross is -0.0245
R_slot, below the alleged time floor of +0.1466 R_slot. Trade-level inspection found:

- guarded below time on 35.16% of delay-1 signals;
- time above touch on 35.18%;
- guarded above touch on 0.02%.

Touch maximizes the chance of an anchor fill, not P&L. A missed fill may outperform an
anchor fill if price continues favourably, and a time exit may be above or below either
anchor policy.

**Required correction:** rename these arms to `touch-fill diagnostic` and
`time-exit comparator`; remove all floor, ceiling, bracket, and upper/lower-bound
claims. The comparison remains useful after the interpretation is corrected.

### 4. Medium — material path exclusions and Friday truncations are unreported

The run flow is:

| Stage | Count |
| --- | ---: |
| Signals before news veto | 198,812 |
| News vetoed | 15,471 |
| Signals after news veto | 183,341 |
| Valid delay-1 paths | 166,395 |
| Additional zero-cap/incomplete-path exclusions | 16,946 (9.2%) |
| Retained trades shortened by Friday flat | 5,289 (3.2%) |

The frozen kill test promised separately quantified news removals and Friday-flat
truncations, but the reference report contains neither flow. The post-news path loss is
large enough to require Rule-9a coverage reporting by pair, era, and time-of-day.

**Required correction:** emit and report a rerunnable Stage-B data-quality/exclusion
artifact separating zero-cap, incomplete-path, news-veto, and Friday-shortened rows.

## Minor wording corrections

- A confidence interval containing zero means positive gross reversion is **not
  established**; it does not prove that reversion is absent.
- With negative gross P&L there is no nonnegative breakeven transaction cost. Describe
  `-0.137 pips` as the rebate required to reach zero, rather than a breakeven round trip.

## Review conclusion

The NO-GO direction is likely robust: even the optimistic touch and time comparators
are far below modelled costs. However, EXP-0004 should not yet be treated as the frozen
Stage-C ruler. The one-position estimand and already-crossed-anchor semantics must be
corrected first, followed by a reproducible coverage report. The current report is
numerically faithful to its artifact but does not yet describe a fully deployable book.
