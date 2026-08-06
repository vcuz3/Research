# Final Review — trend-following closed form as an instrument pre-screen

One hypothesis, one experiment, both closed 2026-08-03. Verdict: **REJECT as a
pre-screen**; two of the source article's own claims **confirmed**.

## Research evidence versus deployable evidence

**Research evidence (solid).** The closed form is exact to 4.16e-17; its turnover
claim holds on 28 of 30 products; the autocorrelation term, not the drift term,
carries the cross-product variation; and realised trend P&L has zero
year-to-year rank persistence across the panel. All of these are measurements on
16 years of 30 products with cluster-aware uncertainty, a re-pairing null, and a
degenerate benchmark.

**Deployable evidence (none, and none was sought).** No edge was proposed here.
For completeness the matched EWMA rule was scored honestly and is not tradable:
daily median annualised net Sharpe +0.027 with 17/30 products positive at *every*
span; intraday 0/30 with cost 23x gross. There is nothing to size, shadow, or
allocate to.

## What would have been concluded without the controls

This is the point of the run and it is worth stating plainly.

- **Without the identity diagnostic**, the headline would have been: "Spearman
  +0.87 across 30 products, CI excluding zero, re-pairing null 0.0000, robust to
  leave-one-asset-class-out, de-duplication, cost stress and every span — the
  closed form predicts the transfer ladder, and 'which market next' is now a
  table." Confident, fully controlled by this workspace's normal standards, and
  entirely wrong. The relation was a correct derivation, which is exactly why it
  survived every null: **a re-pairing null cannot detect an identity.**
- **Without the degenerate no-theory benchmark**, the out-of-sample arm would
  have read "+0.027, weak but positive, needs more data" instead of "+0.007
  against just running the backtest, spanning zero".
- **Without bootstrapping the difference** rather than comparing two intervals,
  neither of those two overlapping CIs would have decided anything.
- **Without the term decomposition**, the preregistered worry (that PHI is SR² in
  disguise) would have stood unexamined — and it happens to be wrong, so the
  article would have been under-credited rather than over-credited.

Three controls, none more than a few lines, and they moved the verdict in both
directions.

## Regimes, neighbours, cross-market, cost stress

- **Neighbouring parameters:** spans {8, 16, 32, 64, 128} plus an EWMA crossover.
  Read as a slope, not an argmax; the slope confirmed the algebra explanation.
- **Cross-market:** the panel *is* the cross-market check — five asset classes,
  leave-one-class-out +0.829 to +0.896 in sample, and the OOS failure is uniform
  across classes.
- **Regimes:** four 4-year eras and fourteen annual windows. Per-year OOS scores
  swing +0.365 to −0.364 on a stable ranking, which is the signature of the
  diagnosed failure mode rather than a regime effect.
- **Cost stress:** 0.5 and 1.0 measured price increments one way; conclusions
  unchanged.
- **Panel composition:** de-duplicated (no MGC/MCL) and heavy-roll-removed arms
  both reproduce the in-sample result and both fail out of sample.

## Holdout

None sealed, and none was needed: this measures an externally published formula
against results the workspace already owns. No historical data has been
"consumed" in the sense that matters, because no candidate edge was screened.

## Proceed, watch, or abandon

**Abandon the pre-screen use, keep the tool.** Do not use PHI to choose the next
port target — finding D shows no screen can do that job on this panel. Do use it
for what it is genuinely good at and what nobody claimed: a fast, exact,
analytic **decomposition of a completed backtest**, attributing a trend result to
specific lags and separating drift from autocorrelation.

The one live follow-up is finding G (the equity ladder inverts between clocks),
which is provisional on one panel and one strategy family per clock and is cheap
to settle — the machinery already accepts an arbitrary clock.
