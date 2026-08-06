# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — Trend-following closed form predicts cross-product realised trend P&L
- Status: completed
- Builder: Claude (Opus 5)
- Reviewer: unassigned
- Primary metric: Spearman(PHI at lag 0, realised gross P&L of the executable
  lag-1 rule) across the 30-product CME panel, daily clock, span 32,
  cluster-bootstrap CI clustered by asset class.
- Kill test: K1 Spearman > +0.50 with a cluster-bootstrap CI excluding zero; K2
  PHI from era *k* must rank era *k+1* AND beat the degenerate
  prior-window-realised screen; K3 the declared `NQ > ES > YM/GC > RTY` ordering,
  decomposed into (a) versus the realised EWMA ladder and (b) versus
  `noise_vwap`'s ladder.
- Artifacts: `screen_daily.txt`, `screen_slot30.txt`, `per_product_*.csv`,
  `k1_*.csv`, `k2_daily.csv`, `k2b_annual_daily.csv`,
  `k2b_persistence_daily.csv`, `sensitivity_*.csv`, `identity_*.csv`.

## Result versus hypothesis

**K1 PASSES, K2 FAILS, K3 is unanswerable as posed — and K1's pass is not
evidence.** The verdict is REJECT as a pre-screen.

| gate | result | verdict |
|---|---|---|
| K1 Spearman(PHI0, realised gross), n=30 | **+0.8656** [+0.6853, +0.9333], re-pairing null frac 0.0000 | passes the +0.50 gate |
| K1 on net | +0.8857 [+0.6966, +0.9533] | passes |
| K1 at cost stress 1.0 increment | +0.8759 [+0.6510, +0.9290] | passes |
| K2 era *k* → *k+1*, pooled (n=79) | **+0.0620**; every transition CI spans zero | fails |
| K2b annual, pooled (n=374) | PHI **+0.0268** [−0.0210, +0.1149] | fails |
| K2b PHI **minus** degenerate screen | **+0.0072** [−0.0083, +0.0492] | **spans zero — fails** |
| K3(a) PHI vs the realised EWMA ordering | 3/3 adjacent pairs (YM ladder) | passes |
| K3(b) realised EWMA vs `noise_vwap` ladder | 0/3 adjacent pairs | fails — see below |

Control 1 (the identity check) passed at **4.16e-17** over 30 products × 2
execution lags, so nothing below is an implementation artifact.

## Gross, net, baseline, and null comparison

**The formula is arithmetically exact, and that is the problem.** Before reading
K1 the run asks how much of it is algebra, and the answer is: nearly all.
`PHI` at the executable lag correlates with realised gross P&L at
**Spearman +0.9804** — it is the same number, by construction, and
`tests/test_core.py` pins the agreement at 1e-10. The published lag-0 form and
the executable lag-1 form share 159 of their 160 weighted lags and correlate at
+0.8990. So K1 measures one thing only: whether the one-lag execution offset and
the cost break the identity. They do not. It is a rule-16 situation — an
algebraic relation presented as validation — and it is labelled as such rather
than scored.

**Turnover is the one part of the article that holds outright.** The claim that
`E|Δp| = (2/√π)·√(1−ν)` depends only on the filter span and never on the market
is confirmed: the risk-unit turnover is **0.257–0.278 against a predicted
0.2778** on 28 of 30 products. The two exceptions are `SR3` (0.211) and `ZQ`
(0.199), and they are explained rather than anomalous — their volume-ranked
continuous front flickers so often that 33% / 38% of their returns are contract
substitutions, which are zeroed inside the filter and damp the signal.

**Costs and deployability (rules 20, 21).** At half a measured price increment
one way: median annualised gross Sharpe **+0.057**, median net **+0.027**, and
**17 of 30 products net-positive** — a coin flip. Best is `RB` at +0.662 gross,
worst `6S` at −0.377. Cost eats a median 17% of gross where gross is positive,
but far more in the rates complex (`ZT` cost 0.0169 against gross 0.0259, 65%).
The matched EWMA trend rule is not a tradable result on this panel at span 32,
which is a side finding but a consistent one.

**Re-pairing null (rule 18).** Every K1 arm returns frac ≥ real of 0.0000; the
drift-term and bare-`SR` arms return 0.92 and 0.73. The null discriminates.

## Regimes, sensitivity, and alternative explanations

**Control 3 refutes the preregistered concern, in the direction that favours the
article.** HYP-0001 named the sharpest risk in advance: that `PHI` would be
dominated by `SR²` — "the market went up" wearing an autocorrelation coat. It is
not. The autocorrelation term alone scores **+0.8563** [+0.6278, +0.9219]; the
drift term alone **−0.2632** [−0.6803, +0.2740], null frac 0.92; bare `SR`
**−0.1128**. The cross-product variation in trend P&L is carried by the
autocorrelation term, and the drift term contributes essentially nothing —
its spread across products (0.0000–0.0432) is a quarter of the autocorrelation
term's (−0.151 to +0.179).

And it is not any single lag: **bare ρ(1) scores +0.0024** [−0.3009, +0.3262].
The article's structural claim — that trend P&L is the *whole weighted
autocorrelation function*, not a headline lag — survives.

**Panel composition.** Leave-one-asset-class-out ranges only +0.829 to +0.896
across all five classes; de-duplicated (no `MGC`/`MCL`) +0.9009; heavy-roll
products removed +0.8449. No class carries it and the near-duplicates are not
inflating it.

**Span sensitivity, read as a slope not an argmax.** K1's Spearman rises
monotonically with span — 8: +0.693, 16: +0.747, 32: +0.866, 64: +0.928, 128:
+0.941, crossover 16/64: +0.963. That monotonicity is itself confirmation of the
algebra explanation: the longer the span, the smaller ρ(1)'s share of `PHI0`,
and the closer `PHI0` gets to being literally the realised statistic. Median
gross falls as span rises (0.0108 → 0.0026) and the net-positive count sits at
15–17 of 30 at *every* span.

### Why the screen fails — three one-line diagnostics

This is the substantive content of the run.

1. **`Spearman(PHI, degenerate screen) = +0.9808` within year.** `PHI` computed
   over a window *is* that window's in-sample trend P&L plus a drift term. So
   "use the closed form" and "just run the backtest" are the same predictor.
   The closed form does not add information to a backtest; it **is** the
   backtest, written in closed form. That single number explains why K2b's
   difference statistic is +0.0072.
2. **Rank persistence of `PHI` itself, year to year: +0.7133.** The predictor is
   very stable. (Partly mechanical — consecutive 4-year windows overlap by 3
   years — but stable either way.)
3. **Rank persistence of realised P&L, year to year: −0.0045.** The *target* has
   no persistence at all across this panel.

So the failure is not a noisy predictor. It is a **stable predictor of an
unstable target**, which is the worst combination available: any screen with a
multi-year estimation window will produce a confident, smooth, repeatable ranking
that is uncorrelated with next year. The per-year K2b scores behave exactly as
that diagnosis predicts — +0.365 in 2023, −0.364 in 2025 — a fixed ranking
swinging with whichever way the truth happened to fall.

The consequence generalises past this formula: with year-to-year rank
persistence of realised trend P&L at zero, **no screen of any construction can
rank next year's trend P&L across these 30 products.** The binding constraint is
the stability of the autocorrelation function, not the choice of estimator.

### K3 was not answerable as the source item posed it

The item's kill test asks the ranking to reproduce `NQ > ES > YM/GC > RTY`, which
is `noise_vwap`'s ladder — an intraday *barrier breakout* result — while the same
item's own traps section says to benchmark against a matched EWMA rule and
explicitly not against `noise_vwap`. Decomposed:

- **(a) does `PHI` reproduce the realised EWMA ordering?** Yes — 3/3 adjacent
  pairs on `NQ/ES/YM/RTY`, 2/3 on `NQ/ES/GC/RTY`.
- **(b) does the realised EWMA ladder match `noise_vwap`'s?** No — 0/3. The
  daily EWMA ladder is **`RTY > YM > ES > NQ`**, close to the exact reverse.

So the two strategy families rank the same four equity index products in opposite
orders, and a screen for one is not a screen for the other. `noise_vwap`'s NQ
advantage is intraday continuation monetised through a barrier; the daily EWMA
rule finds NQ the *worst* of the four because NQ's daily returns are the most
mean-reverting at trend-relevant lags (`PHI0_ac` −0.111, the panel's most
negative). K3 conflated two questions; scored properly it is a pass on the part
that tests the formula and a rejection of the premise on the part that does not.

## Artifact and implementation risks

- **Identity check passed at 4.16e-17**, so predicted-vs-realised disagreement is
  attributable to the market rather than the code.
- **Rule-9a defect caught in this project's own first build and fixed.** A strict
  `min_periods == vol_window` on the causal 63-session scale required all 63
  trailing sessions to be roll-free. `CL` drops 4.7% of returns to rolls, so
  essentially every window contained one, and the daily risk unit was defined on
  **0.0% of rows for all six energy products** — invisible as a crash, visible
  only as NaN in the report. The fractional floor (2/3) restores them to 0.92–0.94.
  Pinned by `test_fractional_min_periods_survives_scattered_roll_gaps`.
- **An off-by-one in the filter alignment** initially put `w[0]` on `x_{t-1}`
  instead of `x_t`, which shifts every lag in the closed form. Caught by the
  identity check failing, now pinned by
  `test_apply_kernel_puts_the_most_recent_return_at_weight_one`.
- **Turnover was first reported in contracts**, which carries each product's own
  price scale and is not comparable across the panel (it ranged 0.002 to 6090).
  Split into `turnover_pos` (risk units, the article's quantity) and
  `turnover_contracts` (used only inside cost).
- **Heavy-roll products.** `BZ` 13%, `SR3` 33%, `ZQ` 38% of daily returns are
  contract substitutions. They stay in the panel — excluding them would be a
  selection decision — and every headline is repeated without them.
- **Shared-decision-bar artifact (LEARNINGS 2026-07-31d).** `dp_t` and `dp_{t+1}`
  share the close `C_t`, so pricing error there induces mechanical negative
  ρ(1). This can only inflate `PHI0`; the primary *realised* arm is lag-1 and
  never touches ρ(1), so no realised number here is exposed to it.
- **Measured increments are the effective traded grid**, not the exchange
  minimum. On `PA` from 2021 the two differ (0.5 vs 0.05). For a cost floor the
  effective grid is the more honest input; it is labelled so it is not mistaken
  for the contract specification.
- Not tested: intraday-clock results are the secondary arm (`screen_slot30.txt`);
  no sub-minute data was used and none is needed for a continuously-held linear
  position.

## Builder interpretation

The formula is **correct, confirmed on its turnover claim, structurally right
about autocorrelation over drift — and useless as a pre-screen**, because it is
an exact restatement of the backtest it is meant to replace.

What a normal exploratory pass would have reported: "Spearman +0.87 across 30
products, CI excluding zero, re-pairing null at 0.0000, robust to
leave-one-class-out, de-duplication, cost stress and every span — the closed form
predicts the transfer ladder." That is a clean, confident, entirely wrong
conclusion, and two cheap controls destroyed it: the **identity diagnostic**
(asked before K1 was read, not after) and the **degenerate prior-window screen**.
Neither costs more than a few lines.

The genuinely valuable output is not the verdict on the formula but diagnostic
(3): realised trend P&L has **zero year-to-year rank persistence** across 30 CME
products over 16 years. That closes the "which market next?" question the item
was raised to answer — not by giving a table, but by showing no table can exist
at this horizon.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: promoted — findings A through F.
- `MEMORY.md`: updated; the project's verdict and the persistence result are
  durable state.
- Shared `LEARNINGS.md`: **eligible and promoted as provisional.** The
  "predicted quantity is an algebraic restatement of the realised one" failure
  mode and the "stable predictor of an unstable target" diagnosis are both
  general, and the identity diagnostic is a three-line control that applies to
  any closed-form or analytic-approximation claim. Marked provisional pending a
  second project, with the confirming test named.
