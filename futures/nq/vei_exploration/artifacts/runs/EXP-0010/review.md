# EXP-0010 Results Discussion

- Hypothesis: `HYP-0007` — Fresh time-of-day-normalised VEI expansion with
  strengthening volume carries short-horizon momentum
- Status: completed
- Builder: Codex
- Reviewer: unassigned
- Primary metric: zero-trade-day daily net-ATR-R t-statistic and Sharpe for the
  volume-confirmed first-onset H=10 strategy, NQ and ES
- Kill test: primary netR > 0, Sharpe > 0, daily t >= 2, and better netR and Sharpe
  than unconfirmed onset on both markets; only then spend matched-count and Null C

## Result versus hypothesis

**The descriptive mechanism is present, but the useful-alpha hypothesis is rejected.**

The test used EXP-0009's canonical regime label: repaired Wilder(10/50) VEI converted
to a strictly causal trailing-90-session same-slot z-score. An onset is the first
five-minute upward crossing of `z >= 1.5` in a session. Volume confirms it only when
trailing five-minute volume is above its own same-slot norm and its z-score is higher
than in the prior block. There were 2,899 NQ / 2,976 ES onsets, of which 2,290 / 2,415
(79% / 81%) were confirmed.

At H=10, momentum-aligned forward return was:

| cell | NQ mean bp [90% CI] | ES mean bp [90% CI] |
| --- | ---: | ---: |
| confirmed onset | +0.639 [+0.023,+1.252] | +0.781 [+0.265,+1.260] |
| unconfirmed onset | -1.317 [-2.472,-0.229] | -0.958 [-1.773,-0.142] |
| confirmed minus unconfirmed | **+1.956 [+0.592,+3.149]** | **+1.740 [+0.752,+2.694]** |

So volume distinguishes the pooled historical onset cells cleanly. It is better read as
identifying a bad low-participation subset than as creating a strong positive signal:
79–81% of onsets pass the volume condition.

The effect is not era-stable. The H=10 confirmed-minus-unconfirmed difference by era was
NQ -1.51 / +1.90 / +4.66 / +5.37 bp and ES +0.81 / +1.27 / +4.53 / +0.97 bp for
2011–15 / 2016–19 / 2020–22 / 2023+. CIs include zero in every pre-2020 cell and in ES
2023+; the primary strategy is negative in both markets in 2011–19 and positive in
2020+. This is a regime-dependent historical observation, not a stable law.

## Gross, net, baseline, and null comparison

| primary H=10 | NQ | ES |
| --- | ---: | ---: |
| trades | 2,281 | 2,391 |
| net points/trade | +0.731 | +0.121 |
| net ATR-R | +1.12 | -4.53 |
| daily Sharpe | +0.050 | -0.199 |
| daily t | +0.19 | -0.76 |

**Kill test 1 fired on both markets.** Both primary cells beat their unconfirmed-onset
controls, but neither approached daily t >= 2 and ES failed even the positive netR /
Sharpe conditions. Matched-count and path-preserving nulls remain unspent by the
predeclared gate.

The declared H=30 sensitivity improves to NQ Sharpe +0.527, t +2.02 and ES Sharpe
+0.364, t +1.40. It is not the frozen primary, fails the both-market threshold, and is
consistent with the project's recurring cost-amortisation pattern. It cannot replace
the rejected H=10 test.

## Regimes, sensitivity, and alternative explanations

- The first mature-high, volume-confirmed observation is net negative on both markets
  (NQ t -1.16; ES t -1.28). This supports the descriptive onset-versus-late distinction.
- Splitting confirmed onsets by the absolute volatility level favours the high-level
  half on both markets, but even that post-control cell reaches only t +1.06 NQ / -0.09
  ES. It is not an edge and suggests that onset information is conditional rather than
  a pure ratio effect.
- The pooled mechanism difference is positive in all three dayparts on both markets,
  but only some CIs exclude zero. It is not confined to a single clock slot.
- NQ and ES are not independent replications here: 2,675 onset dates overlap (Jaccard
  0.836), 1,295 events occur at the same date and five-minute slot, and their aligned
  H=10 returns correlate 0.896. Cross-market agreement therefore carries less evidence
  than two unrelated instruments would.
- The 2023+ strategy Sharpe is +0.866 NQ / +0.581 ES. Those dates were inspected as part
  of the consumed sample; preserve as a forward-watch lead only.

## Artifact and implementation risks

- Tests pass 17/17, including a new invariant that an onset requires an observed
  below-to-above transition and only the first crossing per session is retained.
- Rule 9a outputs report 0 duplicates, 0 missing OHLC, 0 non-positive volume, 7 NQ / 4
  ES sessions with internal gaps, and uniform causal-normalisation coverage (0.9838 at
  every decision slot). Every cell uses one common sample with a contiguous
  `m-30..m+31` window; session-end truncation and gap-affected windows are dropped.
- The source contains 61 contract symbols but no RTH `is_roll` flags; no primary trade
  spans a flagged roll bar.
- The first attempted run timed out during a mechanically inefficient bootstrap that
  concatenated thousands of one-row frames. It produced no statistic. Indexed
  whole-session resampling replaced it without changing the estimand or hypothesis;
  final CIs use 400 seeded draws, matching EXP-0009's runtime convention.
- All experiment outputs are confined to `artifacts/runs/EXP-0010/`.

## Builder interpretation

VEI onset and volume participation are useful descriptive state variables: a fresh
expansion with participation is materially different from an unconfirmed expansion,
and waiting until the regime is mature loses the effect. But the direct H=10 momentum
implementation is weak, era-dependent, highly correlated across NQ/ES, and fails daily
portfolio performance. Treat volume as a possible veto or allocation input for an
independently validated strategy, not as a new standalone VEI trade.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: add Study J as mechanism qualified / alpha rejected.
- `MEMORY.md`: close backlog item 11; preserve the post-2020 result as forward-watch.
- Shared `LEARNINGS.md`: not eligible; this is project-specific and not independently
  reviewed or replicated on unrelated markets.
