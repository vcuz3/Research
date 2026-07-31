# EXP-0015 Results Discussion

- Hypothesis: `HYP-0012` — the forward-vol core is a TIMING instrument: it correctly
  calls changes away from trailing 30-minute volatility.
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: WITHIN-SLOT Spearman IC between the predicted log-change
  `pc = log(F/P)` and the realised log-change `rc = log(A/P)`, where `P` is the trailing
  30-minute realised vol (the strict backward twin of the target), with a 90%
  session-block-bootstrap CI. The EXPANSION side is gated separately.
- Reproduce: `python -u -m futures.nq.vei_exploration.scripts.hyp_0012_disagreement {NQ|ES}`
- Outputs: `disagreement_NQ.txt`, `disagreement_ES.txt`, `disagreement_{NQ,ES}.csv`

## Result versus hypothesis

**PASS on both markets, including the discriminating expansion-only gate.**

| | NQ | ES |
| --- | --- | --- |
| PRIMARY within-slot IC(pc, rc) | **+0.3766 [+0.3690, +0.3841]** | **+0.3901 [+0.3819, +0.3984]** |
| expansion calls only (`pc > 0`) | **+0.2201 [+0.2050, +0.2351]** | **+0.2380 [+0.2240, +0.2520]** |
| contraction calls (`pc <= 0`) | +0.2854 [+0.2740, +0.2971] | +0.2725 [+0.2598, +0.2840] |
| free same-slot median in place of the model | +0.2403 [+0.2325, +0.2496] | +0.2518 [+0.2441, +0.2600] |
| the model's marginal value on this axis | **+0.1363** | **+0.1383** |

The expansion gate was preregistered precisely because volatility mean-reverts and
calling a contraction after a spike is nearly free. It clears on both markets, so the
pass is not carried by mean-reversion arithmetic. Per-year within-slot IC is between
+0.350 and +0.436 on NQ and +0.367 and +0.436 on ES across all eleven tested years, with
the expansion-only figure between +0.19 and +0.31 — stable, no era dependence. Per-slot
IC is +0.347..+0.407 (NQ) / +0.345..+0.421 (ES), i.e. uniform across the session.

## The result that matters more than the pass: persistence is a far harder benchmark than seasonality

This is the reframing item 16 was designed to produce, and it materially qualifies
EXP-0012's headline.

| within-slot IC vs realised forward RV | NQ | ES |
| --- | --- | --- |
| model `F` | +0.8808 | +0.8740 |
| **persistence `P` (trailing 30m RV)** | **+0.8674** | **+0.8610** |
| seasonality `M` (causal same-slot median) | +0.4186 | +0.3830 |

EXP-0012 credited the core with a within-slot IC delta of about +0.47 over the same-slot
median. Measured against the benchmark a practitioner would actually default to, that
delta is **+0.013 (NQ) / +0.013 (ES)**. Persistence alone already achieves a log-MSE
skill of **+0.686 / +0.710** over seasonality; the model's skill over *persistence* is
**+0.187 / +0.148**.

So EXP-0012's number is not wrong — it was measured against a weak benchmark. The correct
statement is: **almost all of the core's apparent advantage over seasonality is
reproduced by the trivial rule "volatility persists"; what the model adds on top is a
19% / 15% reduction in log-MSE and a genuinely informative call on the CHANGE.** Both
halves need saying. Quoting the +0.47 without the +0.013 overstates the model; quoting
the +0.013 without the +0.19 log-MSE skill and the +0.38 change-IC understates it. The
levels are nearly all persistence; the deltas are where the model lives.

## Regimes, sensitivity, and alternative explanations

**Skill rises monotonically with the size of the disagreement** — the opposite of the
overconfidence failure mode the hypothesis flagged as a distinct, reportable outcome.
By |pc| decile on NQ (ES is the same shape):

| decile | 1 | 4 | 7 | 10 |
| --- | --- | --- | --- | --- |
| mean abs(pc) | 0.012 | 0.083 | 0.173 | 0.414 |
| IC(pc, rc) | +0.033 | +0.145 | +0.367 | **+0.643** |
| log-MSE skill vs P | +0.001 | +0.026 | +0.190 | **+0.426** |

The model is most right exactly where it would actually be used. That is the strongest
single piece of evidence in this run.

**The important asymmetry, and the honest caveat.** On the expansion side the *ranking*
is good (IC +0.220 NQ / +0.238 ES) but the log-MSE skill over persistence is only
**+0.008 (NQ) / +0.061 (ES)**, against **+0.300 / +0.211** on the contraction side. So
the model can order which expansions will be larger, but on expansion calls it barely
beats persistence at predicting the *level*. Nearly all of the MSE gain comes from
correctly anticipating decay. Anyone using this to size an anticipated expansion should
read that gap: the direction-of-change call transfers, the magnitude call largely does
not.

**Base rates.** The model calls an expansion only 40.0% (NQ) / 42.2% (ES) of the time,
and realised `rc` has mean -0.068 / -0.044 — volatility decays over the next 30 minutes
relative to the trailing 30 on average, so a bias toward contraction calls is correct
rather than a defect. Mean realised `rc` on expansion calls is nonetheless **+0.054 /
+0.069**, i.e. expansion calls are right in sign on average too.

Alternative explanation considered: that the change-IC is manufactured by a scale
mismatch between `P` and the forward window. Rejected by construction and by test — `P`
is the same estimator on the same price series applied to the immediately preceding
window, and `test_past_window_matches_the_forward_estimator_on_the_same_prices` asserts
`past_rv30_bp[p] == fwd_rv_bp[p-31]` exactly — and by measurement, since every statistic
here is within-slot, so any residual per-slot scale bias is differenced out.

## Artifact and implementation risks

- Rule 23: the reproduction of the EXP-0011 notebook's pooled ICs is asserted before the
  forecast is used (|delta| <= 1.7e-04 at exact row counts, tolerance 5e-4).
- Rule 9a: 29,308 of 29,313 walk-forward rows keep a defined trailing benchmark (99.98%);
  five dropped for a broken or zero trailing window. Per-slot benchmark coverage
  0.9989–1.0000, uniform.
- The trailing benchmark is scaled by `HORIZON_MIN / n` at the 09:59 slot, where only 29
  in-session returns exist, and is never allowed to cross the session open into overnight
  trade (the forward target never does). This is a per-slot scale detail, absorbed by
  within-slot measurement; both facts are pinned by tests.
- Causality of `P` is tested in both directions: perturbing a bar after the decision bar
  cannot change it, perturbing a bar inside the trailing window must.
- One frozen model against two fixed benchmarks; no parameter searched. This is consumed
  history, so the disagreement structure documented here is discovery.

## Builder interpretation

**The core is a timing instrument, not only a calibration instrument — but a much smaller
one than EXP-0012 implied.** Three statements, all needed together:

1. Against the benchmark that matters, the core's advantage in *level* ranking is small
   (+0.013 within-slot IC over trailing 30-minute RV). EXP-0012's +0.47 was measured
   against seasonality, which persistence beats on its own.
2. Its advantage in *change* is real, large, both-market, era-stable, and survives the
   preregistered expansion-only gate (+0.22 / +0.24), with +0.14 of marginal value over
   what the free same-slot median would call.
3. Its skill increases monotonically with the size of the disagreement, so the useful
   content is concentrated exactly in the subset where a forecast could change a decision.

For the research programme this narrows where to look next. The model's weakest cell is
the one worth the most: **expansion calls, where the ranking works but the magnitude does
not.** That is precisely the cell a scheduled-calendar feature (backlog item 13) should
improve, because scheduled events are the anticipatable source of volatility expansion,
and it is the cell that matters for standing aside, widening a stop, or buying
optionality. Item 13 is now not merely the highest-value untouched channel but a targeted
one, with a specific measurable cell to beat: expansion-call log-MSE skill over
persistence of +0.008 (NQ) / +0.061 (ES).

## Independent review

- Review status: pending
- Objections: independent review not yet assigned
- Verdict: builder verdict recorded (PASS on both markets, with EXP-0012's headline
  materially qualified); independent review pending

## Promotion decision

- `reports/FINDINGS.md`: promote as finding §O, and annotate §K–L (EXP-0012) with the
  benchmark qualification
- `MEMORY.md`: promote the pass, the persistence-vs-seasonality reframing, and the
  expansion-magnitude gap as the specific target for item 13
- `experiments/IDEA_BACKLOG.md`: close item 16; sharpen item 13 with the cell to beat
- Shared `LEARNINGS.md`: strong candidate — "measure a forecast against the benchmark a
  practitioner would actually use, not the weakest available one, and split the
  disagreement set by sign" is general. Promote after one cross-project confirmation.
