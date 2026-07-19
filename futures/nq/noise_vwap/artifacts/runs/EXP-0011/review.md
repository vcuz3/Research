# EXP-0011 Results Discussion

- Hypothesis: `HYP-0004` — The paper two-stage RR ladder exit improves NQ risk-adjusted returns over the band stop
- Status: completed — hypothesis rejected
- Builder: Claude (Opus 4.8)
- Reviewer: Claude (Opus 4.8)
- Primary metric: zero-trade-day daily net-ATR-R Sharpe uplift of the paper Table-2 ladder over the both stop, vs corrected Null C
- Kill test: Reject if ladder Sharpe uplift over both < +0.10, ladder net R < both net R, or Null C upper-tail p > 0.05; weaken if ladder Sharpe < tp1.0_50 or sign does not transfer to ES

## Result versus hypothesis

Rejected on the primary NQ test; not salvaged by ES.

| Instrument | arm | trades | net R | Sharpe | ladder Δ vs both | Null uplift mean±sd | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ | both | 4209 | +91.2 | 1.29 | — | — | — |
| NQ | tp1.0_50 | 4209 | +88.5 | 1.34 | | | |
| NQ | ladder | 4092 | +78.3 | 1.21 | **−0.075** | −0.047 ± 0.091 | 0.6129 |
| ES | both | 4326 | +51.5 | 0.70 | — | — | — |
| ES | ladder | 4280 | +47.3 | 0.71 | **+0.014** | −0.039 ± 0.108 | 0.3226 |

NQ ladder loses on both Sharpe (−0.075) and net R (−12.9), fails the +0.10 gate
outright, and also underperforms the `tp1.0_50` survivor by −0.131 Sharpe. ES is a
wash on Sharpe (+0.014) and negative on net R (−4.2). Null C confirms: the tiny ES
uplift is below the null mean's noise, and even NQ's negative uplift is typical of
the null (18/30 draws beat it).

## Gross, net, baseline, and null comparison

The ladder cuts NQ gross R from +111.2 to +97.5. The fixed −1R step-0 stop is
looser than the trailing band on failures (lets some losers run to −1R) while the
breakeven step-1 stop and the +5R cap truncate the winners the trailing band/VWAP
stop was still riding. The net effect is strictly worse risk-adjusted return. The
paper's own Table 8 flagged that its upper take-profit was usually unreachable
(the trade exits on time), consistent with a rigid ladder discarding the trailing
stop's edge without a compensating gain.

## Regimes, sensitivity, and alternative explanations

Recent 2023+ Sharpe is also lower for the ladder on both markets. Fill sensitivity
(signal_close − next_open) is small (NQ +0.032, ES −0.027), so the result is not a
fill artifact. Diffusivity gates matched exactly (NQ 0.25, ES 0.00). The paper's
ladder STRUCTURE does not transport; its headline Sharpe 3.35 was an in-sample QQQ
fit, as the 2026-07-18 paper review predicted.

## Artifact and implementation risks

The ladder is implemented default-off in the audited core/engine2.py with a
mechanics unit test (tests/test_ladder.py: blended +3.5R payoff, −1R stop, and
ladder-off == baseline) and the engine2-vs-core.engine parity re-verified. 1R is
the entry-frozen distance from the fill to the band/VWAP stop reference (rule 14),
so the risk unit is causal and vol-scaled, not ATR or ticks. Cost caveat: the 50%
partial's extra half-turn commission is not separately modeled (matches the
tp1.0_50 convention and slightly favours the ladder), which does not change a
reject. 30 null draws give coarse p-resolution but both p-values are far from 0.05.

## Builder interpretation

The paper's flagship ladder does not beat the current band stop or the existing
tp1.0_50 partial on NQ/ES futures. Retain the `both` stop; keep tp1.0_50 as the
only validated exit tweak. Useful NO-GO that closes the ladder idea (IDEA-0003).

## Independent review

- Reviewer: Claude (Opus 4.8)
- Review date: 2026-07-19
- Review status: completed
- Verdict: REJECT confirmed — concur with the builder.
- Basis: Re-derived from real_nq/es.txt and null_nq/es.txt; verified the ladder
  mechanics test and the s=1/baseline parity. NQ fails the Sharpe gate and the net-R
  gate and loses to tp1.0_50; the null shows neither market's uplift is
  distinguishable from noise. Gross-R compression is the mechanism, matching the
  paper's own unreachable-TP finding.
- Objections: none blocking. 30-draw coarseness is adequate for a reject; the
  unmodeled partial commission only makes the (already failing) ladder look better.

## Promotion decision

- `reports/FINDINGS.md`: not updated (NO-GO; recorded in MEMORY invalidated list)
- `MEMORY.md`: updated with the rejected hypothesis
- Shared `LEARNINGS.md`: not eligible without cross-project verification
