# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — Run-length reversion is a grind-vs-lunge concentration effect, not magnitude
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: folded 15m reversion + count/dsig horse-race t; signflip null p
- Kill test: (a) reversion mean-fold not distinguishable from the signflip null (real ≤ null p > 0.05) ⇒ KILL; (b) displacement subsumes count/max-share in the causal joint regression ⇒ the "persistence, not magnitude" claim is KILLED and it reduces to ordinary magnitude reversion.

## Result versus hypothesis

Both kill-test clauses were survived; the hypothesis is accepted as an
exploratory (not holdout-validated) finding.

- (a) Reversion exists and beats its null. Mean folded 15m reversion is
  +0.097 pip (EUR) / +0.103 pip (GBP), sitting ~10σ above the signflip null,
  p = 0.005 (the 1/201 permutation floor). NOT killed.
- (b) Displacement does NOT subsume count/concentration. In the causal joint
  regression `y ~ dsig + signed_count`, the count coefficient survives
  (EUR b=−0.068, t=−5.3; GBP b=−0.033, t=−2.6) while the causal-vol-normalised
  displacement `dsig` collapses to insignificant-or-wrong-signed (EUR +0.022
  t=+1.7 momentum sign; GBP −0.011 t=−0.9). The magnitude-proxy hypothesis is
  REJECTED, not confirmed. NOT killed.

## Gross, net, baseline, and null comparison

This is a signal study, not a strategy — no costs/sizing modelled by design
(the user asked for a statistically robust sub-cost signal to feed another
strategy, fast-alpha style). Comparison is against the signflip null only.

Signflip null (200 draws, real |returns| fixed, iid signs, full pipeline,
seed 7), from `reversion_core_null.txt`:

- EUR: meanfold real +0.097 vs null +0.001±0.010 (p=0.005); count_t real −8.3
  vs null +0.12±1.46 (p=0.005, i.e. 5.8σ outside); disp_t real +3.0 p=0.97
  (displacement carries NO reversion beyond the null — consistent with (b)).
- GBP: meanfold real +0.103 vs null −0.001±0.010 (p=0.005); count_t real −3.9
  vs null −0.02±1.40 (p=0.005, 2.8σ outside); disp_t real −1.5 p=0.15.

The count coefficient being far outside its own signflip distribution rules out
the "nested/overlapping same-sign events inflate the count t" machinery
explanation — the null preserves the event overlap structure and |return|
magnitudes, and destroys only the directional serial dependence.

## Regimes, sensitivity, and alternative explanations

- Continuous refinement (`persistence_horserace.txt`): max-bar share
  `max|bar|/|disp| ∈ [1/k,1]` is the single best univariate predictor (EUR
  t=−4.6, GBP t=−2.4), the continuous form of integer count (corr(k,share)
  =−0.85), and beats integer count on EUR. Per-bar move size is irrelevant
  (t≈0, EUR −0.013). Monotone quintile on EUR: even grind (share≈0.47) reverts
  +0.17 pip; single-bar lunge (share=1.0) → −0.03 pip momentum. GBP same shape,
  weaker.
- Mechanism read: reversion is about HOW the displacement was accumulated
  (grind = reverts, lunge = continues), not how big it was. Consistent with the
  workspace "sharp = continuation, grind = reversion" theme.
- EUR/GBP character split: GBP's persistence effect is real in sign and
  monotonicity but weaker and more entangled with plain magnitude in the joint
  regression.
- Not yet tested (open): era stability by year; cross-pair transfer
  (USDJPY/AUDUSD); whether the effect is a within-window time-of-day artifact.

## Artifact and implementation risks

- Shared-close artifact (LEARNINGS §6): open==prev_close ≈ 0.9965 here, so a
  next-open entry does NOT separate the windows. Controlled with a paired
  1-minute-grain embargo (a 5m embargo would void most of a ~10min-half-life
  signal). The signflip null is the primary defence — it shares the decision
  path and only destroys direction.
- Unit trap (LEARNINGS): FX archives are `datetime64[us]`; an earlier ns divisor
  broke sub-5min horizons. Fixed by building targets with unit-safe
  `(lbl+Timedelta).asi8`. Two pre-fix tables were invalidated and discarded.
- Standardisation: predictor uses CAUSAL trailing-vol normalisation (78-bar RMS,
  shifted), not full-sample z. Full-sample scaling is scale-invariant for the
  t-stat but is lookahead in a deployed predictor; the causal version is what is
  reported.
- Multiple testing: horizons, run lengths, two pairs, several conditioners were
  swept in discovery. The count-vs-magnitude horse race and signflip null were
  the pre-specified confirmatory tests; absolute t's are discovery-inflated —
  rely on the null and the sign/monotonicity, not the headline t.

## Builder interpretation

A statistically robust (null-validated, ~10σ) short-horizon reversion signal in
the Frankfurt-open→NY-noon window, whose predictive content is PERSISTENCE /
concentration of the run, not its magnitude. Suitable as a conditioning signal
for another strategy, per the stated intent. NOT demonstrated to be cost-viable
standalone (not the goal), and NOT holdout-validated — all history is inspected,
so only future data is a clean holdout. Strongest on EUR; GBP directionally
agrees but is weaker.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: pending
- `MEMORY.md`: pending; update only if durable state changes
- Shared `LEARNINGS.md`: not eligible without cross-project verification
