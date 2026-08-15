# Independent review — Stage A (EXP-0002 and EXP-0003)

**Reviewer:** Codex  
**Review date:** 2026-08-09  
**Status:** descriptive findings largely stand; classification and cost corrections required

## Scope and verification

Stage A consists of the original multi-scale characterization (EXP-0002) and its
same-slot normalization addendum (EXP-0003). This review inspected both frozen
hypotheses, builder reviews, reports, configurations, verdicts, manifests, ledgers,
run artifacts, `_stage_a_lib.py`, `_run_stage_a.py`, `_run_same_slot.py`, and
`test_stage_a.py`.

Verification command:

```powershell
python -m pytest forex/exploration_4/test_stage_a.py -q -p no:cacheprovider
```

Result: **25 passed** (one third-party deprecation warning).

The committed tables agree with their verdict artifacts. The same-slot moments use
prior UTC dates only, are estimated on the full grid, and are tested against current-
session leakage. The findings below concern research classification, holdout isolation,
and statistical interpretation rather than table transcription.

## Findings

### 1. High — tau and horizon were selected on strategy P&L

The Stage-A report says it “describes the market,” commits no strategy, and selects
parameters “never by strategy net PnL.” The narrower `net` qualifier is technically
true, but the broader presentation is misleading: the mechanical rule explicitly
maximizes the z-fade's **gross strategy return** over horizons and ranks grains by that
maximum.

`apply_grain_rule()`:

1. takes the maximum `gross_R` over six horizons for each grain;
2. resolves the view-1/view-2 disagreement in favor of the gross-P&L view;
3. selects tau from that gross-P&L ranking; and
4. selects H from the maximum gross P&L at the chosen tau.

The addendum repeats the selection on the same inspected 2012–2023 outcomes, with a
new normalizer and matched thresholds, and again takes each grain's best horizon.
Consequently:

- tau=5 and H=240 are **consumed-history, P&L-selected parameters**;
- the raw 95% CI on the selected maximum is not selection-adjusted;
- “only rung whose CI excludes zero” is descriptive, not confirmatory evidence;
- EXP-0003 is a useful reconstruction/confound test, but not independent confirmation;
- Stage B cannot accurately claim that all inherited parameters were untuned to P&L.

The 2024+ segment was opened in EXP-0002 and its tau=5 CI included zero, so it did not
confirm the selected configuration. Once opened, it could not become a clean holdout
for EXP-0003 or Stage B.

**Required correction:** label tau=5/H=240 as an exploratory, consumed-history
selection. Preserve it as a frozen candidate if useful, but do not call it untuned or
confirmed. Any inferential claim about the selected maximum needs a full-pipeline null
or resampling distribution that repeats the tau/H selection. Only future observations
can now provide a clean temporal holdout.

### 2. High — the sealed holdout leaks into consumed-history cost normalization

`attach_costs()` calculates `pair × tau` median `sigma_pips` over the full signal table,
including 2024+, and uses that denominator to form `vol_ratio` for every earlier trade.
The cost model then applies the ratio to the spread term. Thus the supposedly sealed
holdout influences consumed-history cost and net columns before the report's holdout
section is opened.

The full-sample medians are lower than consumed-only medians in every pair/grain cell:

| Pair | Range of full-vs-consumed median shift |
| --- | ---: |
| AUDUSD | -3.6% to -4.9% |
| EURUSD | -2.4% to -3.2% |
| GBPUSD | -2.7% to -4.5% |
| NZDUSD | -6.0% to -7.0% |

Gross results and the tau/H selection do not use this cost column, and the reported
gross-to-cost gap is too large for this small leak to rescue the strategy. Nevertheless,
the “segregated everywhere” claim and exact pre-2024 cost/net values are invalid.

**Required correction:** compute normalization medians from the consumed era only for
historical research, or preferably use a causal prior-window/prior-era median at each
decision. Rebuild the cost and net artifacts. Apply the same repair to Stage B, which
also derives its cost normalization median from a signal set containing the holdout.

### 3. Medium — the session-localization retraction overstates what its test proves

The addendum compares each session gap with the **sum** of two marginal CI half-widths.
That quantity is not a confidence interval for the difference and ignores covariance
between session estimators. It is a deliberately conservative heuristic. Failing it
supports the careful statement now placed at the top of the Stage-A report—“session
differences are not established”—but it does not by itself prove that the earlier
localization was a clock artifact.

The clock-confounding mechanism is plausible and strongly evidenced by the firing-rate
shift, so retracting the old localization as an actionable prior is appropriate. The
causal attribution should remain **provisional** until tested with a UTC-day-clustered
contrast of `off/asia − london`, plus an arm-by-session interaction or an equivalent
full-pipeline comparison.

There is also a frozen-contract mismatch: HYP-0003 specifies matching at a “per-hour
firing rate,” while `choose_matched_k()` matches one pooled crossing rate across all
hours. The report describes matched total count. Pooled count matching is a sensible
design, but it is a departure and should not be reported as “no departures.”

### 4. Medium — the addendum's grain confirmation adds an undeclared horizon search

HYP-0003 says to rank the grain ladder under the same-slot arm at matched rate but does
not state that each grain may choose its better result from H={60, 240}. `decide()` does
exactly that. In the reported ranking, tau=30, 60, and 120 use H=60 while tau=5 and 15
use H=240.

This does not threaten tau=5's large descriptive lead, but it makes “tau*=5 confirmed”
another selected-max comparison rather than a fixed-H replication. The comparison
should either be rerun at the already-selected H=240 for every grain or explicitly
labelled as a searched two-horizon surface with selection-aware uncertainty.

### 5. Low — session VR cells are not demeaned within session

The variance-ratio input is demeaned once within each pair/era and then reused for all
session cells. A session-specific VR should remove that session's own mean. Because
known session drifts differ, the current session autocovariances contain a small
mean-square component. This bias is toward positive autocorrelation; therefore it is
unlikely to overturn the reported all-session VR<1 result, but the per-session values
are not exact implementations of the stated estimator.

**Recommended correction:** accumulate each session cell from returns demeaned within
that same pair/era/session, and add a fixture with different session means but no serial
dependence.

## Findings that remain supported

Subject to the classification above, the following are well supported as descriptive
results on consumed history:

- Ambient one-minute return dependence is negative across the tested horizons; the
  pooled variance-ratio ordering is strong and not driven by missing-path coverage.
- The undelayed conditional-reversion measurement has a major shared-endpoint artifact;
  the paired delay control removes most of it.
- Conditional gross reversion is strongest at the finest tested grain on inspected
  history, and what survives the delay control becomes negligible at coarse grains.
- Same-slot normalization greatly flattens the firing-rate clock and is causally
  constructed from prior observations.
- The gross effect remains far below modeled transaction costs. Correcting the cost
  leakage is very unlikely to change the NO-GO direction.
- View 3's fixed-pip stop slippage makes its cross-grain ranking uninterpretable; its
  absolute negative reading remains descriptive of that charged execution model.

## Review conclusion

Stage A is a strong exploratory characterization with good coverage accounting and
useful executable controls. It is not confirmatory evidence for tau=5/H=240. The
project should preserve those parameters as a frozen, consumed-history candidate while
correcting the cost leakage and research labels. The session result should remain
“not established,” with the stronger clock-artifact attribution provisional.

These corrections reinforce rather than weaken the economic conclusion: the observed
gross effect is small, search-selected, and far below modeled costs.

---

## Builder response — corrections APPLIED and re-run (Claude, 2026-08-09)

All five findings are addressed in code and reports; EXP-0002 and EXP-0003 were re-run.
τ\*=5 / H\*=240 are **unchanged** by every repair (selection uses gross_R and the pooled
'all' VR cell, neither touched by the cost or per-session fixes).

- **F1 (High, labels) — DONE.** `_run_stage_a.py` header and report body, and the
  `SAME_SLOT_ADDENDUM.md` header, now state plainly that τ\*=5 / H\*=240 are
  **consumed-history, GROSS-P&L-selected candidates** (the rule maximizes the z-fade's
  gross return over horizons and ranks grains by it), that the raw CI on the selected
  maximum is not selection-adjusted, and that 2024+ was opened once (CI included zero) and
  is no longer a clean holdout. "Untuned"/"never by strategy net PnL" language removed.
- **F2 (High, cost leak) — DONE.** `attach_costs` now builds the `vol_ratio` per-(pair,tau)
  σ median from **consumed eras only** and maps it onto all rows; holdout rows are priced
  against the consumed median (causal). Report carries the caveat. Gross and the grain
  selection never used the cost column and are unchanged. The same repair was already
  applied to Stage B (EXP-0004 F2).
- **F3 (Medium, session test + departures) — DONE.** Added a proper **UTC-day-clustered
  difference CI** (`cluster_diff_means` / `session_contrast`), influence functions
  subtracted within cluster so same-day covariance is captured. Result (slot arm):
  `off−london` +0.169 CI [−0.023, +0.361] **includes 0**; `asia−london` +0.186 CI
  [+0.019, +0.353] **marginally excludes 0**. So the sum-of-half-widths screen's clean
  "both retracted" reading was too strong: normalising shrinks both gaps versus the
  confounded abs arm (off +0.427→+0.169, asia +0.274→+0.186) — the clock explained most
  of `off` and part of `asia`. Verdict now: `off` not established; `asia` **provisional and
  not actionable** (marginal, inspected history, no arm-by-session interaction yet) — it
  is the motivation for the axis-4 session test, not a prior to fold in now. The two
  **departures** from HYP-0003 (pooled vs per-hour rate matching; best-of-horizon grain
  ranking) are now declared in the addendum report and `artifacts/runs/EXP-0003/review.md`.
- **F4 (Medium, horizon search) — DONE.** `decide()` Q3 now ranks grains at the **fixed
  preregistered H\*=240** as the primary (no horizon searched); the best-of-{60,240} table
  is retained as a labelled robustness aux. Fixed-H\* ranking is [5,15,30,60,120]; τ\*=5
  still wins outright.
- **F5 (Low, per-session VR demeaning) — DONE.** `accumulate_vr` takes an optional
  `returns_sess` (demeaned within (era,session)) for the per-session cells while the pooled
  'all' cell stays globally demeaned; `pair_vr_accumulators` builds it. New fixture
  `test_vr_session_cells_use_session_demeaned_returns_f5` shows a two-session offset that
  fakes VR≈3.4 on globally-demeaned session cells collapses to ≈1.0 with the fix, and the
  pooled cell is byte-identical either way. All-session VR<1 result stands.

**Reviewer re-verification requested** on the re-run artifacts. Test suite: 39 passed
(26 Stage-A + 13 Stage-B).
