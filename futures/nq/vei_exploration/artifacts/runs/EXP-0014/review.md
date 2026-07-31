# EXP-0014 Results Discussion

- Hypothesis: `HYP-0011` — the frozen two-input core transfers to downside semivariance,
  and the up/down split is itself forecastable.
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: paired WITHIN-SLOT Spearman IC delta of the frozen-recipe model over
  the target's own causal same-slot median, count-weighted across slots, 90%
  session-block-bootstrap CI.
- Reproduce: `python -u -m futures.nq.vei_exploration.scripts.hyp_0011_semivariance {NQ|ES}`
- Outputs: `semivariance_NQ.txt`, `semivariance_ES.txt`, `semivariance_{NQ,ES}.csv`

## Result versus hypothesis

**Claim A CONFIRMED on both markets. Claim B REJECTED on both markets.** The two claims
were preregistered as independent and they separate cleanly.

### Claim A — the recipe transfers to the semivariance legs

| within-slot IC delta over own same-slot median | NQ | ES |
| --- | --- | --- |
| total RV `fwd_rv_bp` (reference) | +0.4622 [+0.4403, +0.4862] | +0.4912 [+0.4688, +0.5146] |
| **downside `fwd_dsv_bp`** | **+0.4267 [+0.4054, +0.4499]** | **+0.4560 [+0.4337, +0.4791]** |
| upside `fwd_usv_bp` | +0.4587 [+0.4377, +0.4824] | +0.4869 [+0.4658, +0.5096] |
| retention vs the total-RV reference | **92.3%** | **92.8%** |

Both CIs exclude zero and both retentions clear the preregistered 75% gate with room to
spare. Log-MSE skill over the same-slot median is +0.626 NQ / +0.648 ES on the downside
leg, and MAE falls 6.85 → 4.25 bp (NQ) / 5.55 → 3.36 bp (ES). Per-year deltas are
positive in all eleven tested years on both markets (NQ +0.404..+0.847, ES
+0.367..+0.853). **The decision-relevant downside quantity is available at no extra
cost:** same recipe, same learner, same walk-forward, only the target changed.

The downside leg is consistently the *hardest* of the three (its delta is ~93% of total
and below the upside leg on both markets), which is the expected ordering — down-minutes
are the sparser, more jump-driven half of the variance — but the shortfall is small.

### Claim B — the up/down split is NOT forecastable

| within-slot IC delta on `fwd_down_share` | NQ | ES |
| --- | --- | --- |
| slot median + `range_rv_15m` | −0.0064 [−0.0192, +0.0087] | +0.0044 [−0.0088, +0.0199] |
| slot median + `past_down_share_30m` | +0.0045 [−0.0093, +0.0186] | −0.0013 [−0.0160, +0.0139] |

All four cells span zero, and the two markets do not even agree on which candidate is
better — the definition of noise. Note the candidate designed to give Claim B its best
chance (swapping the symmetric `range_rv_15m` for its asymmetric counterpart, because a
symmetric feature carries no up/down information at all and would have made the test
rigged) is the *worse* of the two on ES.

**The degenerate control is the decisive evidence, and it is stronger than the CIs.** The
realised down-share has mean 0.4950 (NQ) / 0.4942 (ES) with sd 0.166 / 0.158, and its
per-slot means span only 0.4861–0.4998 (NQ) and 0.4888–0.4979 (ES). Subtracting the causal trailing same-slot
median *increases* the variance — the median removes **−2.1% (NQ) / −2.0% (ES)** of it.
A trailing statistic fitted to a constant-plus-noise quantity is worse than no statistic
at all. The down-share is a constant ≈ ½ plus noise.

## Gross, net, baseline, and null comparison

Forecasting study, not a backtest, so trading costs and P&L nulls do not apply. Each
target is compared against its own free baseline — the causal trailing 90-session
same-slot median — on identical rows, paired and session-block bootstrapped.

## Regimes, sensitivity, and alternative explanations

The **drift control** (the load-bearing one, motivated by `futures/nq/noise_vwap`
EXP-0022, where a real sibling-confirmed up/down band asymmetry turned out to merely
restate drift and was harmful to act on) did not need to do any work, because Claim B
failed outright. Reported anyway, and it confirms there is no drift channel to worry
about: corr(predicted down-share, trailing 30-minute return) is −0.0004 (NQ) / +0.0140
(ES); corr(realised down-share, trailing return) is +0.0081 / +0.0094; and within-slot
deltas inside trailing-return terciles are −0.002/+0.005/+0.006 (NQ) and
+0.006/−0.005/+0.010 (ES). Nothing anywhere.

Alternative explanation considered and rejected for Claim A: that the downside result is
just the total-RV result relabelled. It partly is — that is exactly what Claim B's
failure means — but it is still the useful finding, because it establishes the
*magnitude* of the transfer (93%) rather than assuming it, and because the downside leg
has its own MAE scale that a stop-placement calculation needs.

## Artifact and implementation risks

- Rule 23: `core/forward_vol.py` reproduces the EXP-0011 notebook's pooled ICs to
  |Δ| 1.5e-05 / 6.8e-05 (NQ) and 1.7e-04 / 3.1e-05 (ES) at exact row counts, asserted
  before any new target is evaluated. Declared tolerance 5e-4.
- **The decomposition identity is checked in the run, not assumed**:
  `fwd_rv_bp² == fwd_dsv_bp² + fwd_usv_bp²` to max |error| 2.9e-11 over 41,458 rows
  (NQ), so the two legs provably partition the reference target and nothing is double
  counted. Also pinned as a unit test.
- Tests 29/29 pass, five new for this run (semivariance identity, backward-window
  causality in both directions, the backward twin matching the forward estimator, the
  short-first-slot scaling and gap voiding, and a within-slot-IC helper test that
  demonstrates the pooled/within-slot divergence on a synthetic panel).
- Rule 9a: 29,313 evaluated rows on both markets from 41,710/41,712 decision rows — the
  gap is the pre-2016 walk-forward warm-up plus 252/225 missing targets. Slot coverage is
  uniform.
- Adding the semivariance columns changed `_target_paths_for_session`; the rule-23
  reproduction re-passing at exact row counts is the evidence that `fwd_rv_bp` and the
  evaluation sample were untouched by that edit.

## Builder interpretation

**Downside volatility is total volatility times a constant, and that constant is ½.**
The practical consequence is a clean simplification rather than a new lever: any
stop-placement or barrier calculation that wants downside volatility can take the
existing total-RV forecast, apply the recipe to the downside target directly (93% of the
skill transfers), and must NOT expect any information from the up/down split. The
asymmetry channel is closed on this instrument pair at this horizon.

This is a useful negative in the same family as noise_vwap's band programme, which found
that the per-slot symmetric level is a sufficient statistic for the noise band and that
neither a distributional reshape nor an up/down redistribution added anything. The same
sentence now holds for the volatility *forecast*: the symmetric level is sufficient, and
the sign split carries nothing.

## Independent review

- Review status: pending
- Objections: independent review not yet assigned
- Verdict: builder verdict recorded (Claim A CONFIRMED, Claim B REJECTED); independent
  review pending

## Promotion decision

- `reports/FINDINGS.md`: promote as finding §N
- `MEMORY.md`: promote both claims and the constant-½ down-share result
- `experiments/IDEA_BACKLOG.md`: close item 14
- Shared `LEARNINGS.md`: not yet — candidate once the "symmetric level is a sufficient
  statistic" pattern is confirmed outside the NQ/ES index pair
