# EXP-0007 Results Discussion

- Hypothesis: `HYP-0004` — Opening condition explains the legacy VEI momentum uplift
- Status: completed — mechanism confirmed, predictive-information hypothesis rejected
- Builder: Codex
- Reviewer: unassigned
- Primary metric: session-block-bootstrap controlled past_ret x quiet_open interaction and era-stratified session re-pairing p-value, both markets
- Kill test: quiet-open mechanism corr >0.50 both; controlled interaction positive with 90% CI>0 and era-stratified session re-pairing p<0.05 both; correct-signed dose response and era stability

## Result versus hypothesis

**REJECT as predictive information.** The mechanical premise is confirmed: within
time-of-day slot, `legacy_vei - repaired_vei` correlates +0.551 NQ / +0.532 ES with
`quiet_open = -log(first-minute TR / mean first-50-minute TR)`, clearing the +0.50
mechanism gate on both. The legacy bug really is an undocumented opening-anchor
feature.

The predictive premise fails every important robustness discriminator. The registered
controlled `past_ret × quiet_open` coefficient is +0.0171 NQ with 90% session-block CI
[-0.0304,+0.0210] and +0.0121 ES [-0.0272,+0.0164]: both include zero. The
era-stratified same-feature session re-pairing gives p=0.045 NQ but p=0.137 ES, so the
both-market null gate fails. The quietest-minus-loudest opening quintile continuation
spread is only +0.016 NQ and has the wrong sign, -0.022, on ES; neither market is
monotone by quintile. Era coefficients alternate sign (NQ +/−/+/−; ES −/−/+/−).

## Gross, net, baseline, and null comparison

No trading or fill claim was made; gross/net are not applicable. The estimand is the
controlled standardized forward-return interaction.

| instrument | mechanism corr | primary coef [90% CI] | re-pairing p | q4−q0 spread |
|---|---:|---:|---:|---:|
| NQ | +0.5507 | +0.0171 [−0.0304,+0.0210] | 0.0450 | +0.0160 |
| ES | +0.5317 | +0.0121 [−0.0272,+0.0164] | 0.1369 | −0.0217 |

The null preserves each instrument's complete return paths, repaired VEI, volatility,
slot and era composition, plus the opening-feature marginal distribution, while
re-pairing the session-level opening feature among donor sessions inside the same era.
It destroys only same-session opening-to-later-return information. NQ barely clears in
isolation, but that result is not stable to concentration controls and ES fails.

## Regimes, sensitivity, and alternative explanations

- **The already-viewed boundary decomposition reproduces exactly.** High-set overlap is
  92.1% on both markets. Legacy-only is just 23 NQ / 40 ES observations with corr
  +0.809/+0.451; repaired-only is 203/228 with corr −0.229/−0.154. These are consumed,
  sparse discovery cells, not validation.
- **The common high set retains the core weak effect:** +0.087 NQ / +0.086 ES. Legacy's
  apparent advantage comes from rare boundary reclassification, not a wholesale better
  high-VEI ranking.
- **One shared extreme session is load-bearing.** Both files have a zero-range first bar
  on 2020-03-16. The registered fixed log maps it to the documented `1e-6` floor. It is
  the maximum-influence session in both markets; leaving it out flips the primary
  coefficient to −0.0153 NQ / −0.0071 ES. Dropping all zero-range openings gives −0.0128
  [−0.0321,+0.0067] NQ / −0.0059 [−0.0308,+0.0210] ES. A bounded causal transform
  `-log1p(open_rel50)` gives +0.0045 / +0.0110, both CIs including zero. Thus the NQ
  p=0.045 is an extreme-session artifact, and NQ/ES agreement here is the same date,
  not independent replication.
- **Neighbouring denominators do not rescue it.** First 5/10/30/50-minute definitions
  keep small positive full-sample point coefficients, but none repairs the registered
  inference; the common 2020-03-16 leverage remains because its first bar is zero.
- **Time of day and volatility are not omitted explanations.** The primary regression
  includes repaired VEI, past volatility level, slot and era intercepts, and slot/era
  baseline-momentum interactions; the result still fails.

## Artifact and implementation risks

- History was fully consumed before this run, and the motivating fringe was explicitly
  seen before registration. Only the continuous controlled interaction and null were
  treated as new discriminators.
- `open_rel50` is causal at the first eligible 10:29 decision and is guarded by a test
  that later-bar perturbations cannot change it. Project suite: 12/12 pass.
- Data quality: 3710 sessions; 7 NQ / 4 ES incomplete sessions, 60 / 53 missing RTH bars,
  zero duplicate `(date,mfo)` rows, uniform finite opening-feature coverage at all
  analysed decisions. Each market has one zero-range opening, on the same 2020-03-16
  session; it is reported rather than silently dropped.
- NQ and ES are correlated siblings. Same-date extremes cannot count as independent
  replication.

## Builder interpretation

The legacy recursion demonstrably encoded opening-bar shape, but there is no evidence
that this accidental component is a stable predictor. Its spectacular fringe came from
a very small threshold boundary and the only positive controlled full-sample read is
concentrated in one shared zero-opening session. Do not restore the defective Wilder
seed. If opening-transition research continues, formulate a new feature around expansion
onset/volume participation (backlog item 11) and validate on future data; do not mine
more transforms of this consumed opening-ratio screen.

## Independent review

- Review status: pending
- Objections: independent review unassigned; discovery history is consumed.
- Verdict: **MECHANISM CONFIRMED / PREDICTIVE FEATURE REJECTED**

## Promotion decision

- `reports/FINDINGS.md`: add Study G / EXP-0007 rejection
- `MEMORY.md`: record the mechanism and rejection; close the legacy-seed restoration path
- Shared `LEARNINGS.md`: not eligible without cross-project verification
