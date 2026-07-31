# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — Dollar-decomposed residual momentum: the idiosyncratic part of an intraday move continues, the dollar-explained part does not
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: paired within-slot Spearman IC delta IC(resid_GC_30,fwd_GC_30)-IC(past_GC_30,fwd_GC_30), 90% session-block bootstrap CI
- Kill test: KT1 paired within-slot IC delta CI includes 0 on GC; KT2 the factor leg predicts at least as well as the residual; KT3 sign of the delta disagrees between GC and both siblings
- Evidence: `residual_momentum.txt` (this directory)

## Result versus hypothesis

**REJECTED.** KT3 fired, and the primary metric turned out to be mis-signed for the
effect that actually exists in the data — which is itself the run's first substantive
finding.

| market | IC(raw past) | IC(residual) | IC(factor leg) | paired delta |
|---|---|---|---|---|
| GC | −0.0360 [−0.0440,−0.0264] | −0.0317 [−0.0401,−0.0230] | −0.0155 [−0.0246,−0.0074] | +0.0044 [+0.0005,+0.0078] |
| ES | +0.0004 [−0.0074,+0.0083] | −0.0014 [−0.0105,+0.0078] | +0.0097 [+0.0009,+0.0177] | −0.0017 [−0.0046,+0.0012] |
| NQ | −0.0040 [−0.0119,+0.0052] | −0.0067 [−0.0151,+0.0019] | +0.0115 [+0.0027,+0.0196] | −0.0027 [−0.0053,−0.0002] |

- **KT1 — does not fire on the letter.** The GC paired delta is +0.0044 [+0.0005,+0.0078],
  a CI excluding zero.
- **The letter is misleading and must not be reported as a pass.** HYP-0001 predicted the
  residual would *predict better*, i.e. carry a **larger |IC|**. The preregistered metric
  was written as a signed delta on the assumption that the effect would be momentum
  (positive IC). Gold's 30-minute effect is **reversion** (IC −0.036), so a *positive*
  signed delta means the residual is a **weaker** predictor. On the hypothesis' actual
  claim, gold reads `|IC| 0.0360 → 0.0317 = 87.9% of raw`: **the decomposition destroys
  12% of the signal.** This is recorded as a preregistration defect, not as a pass.
- **KT2 — does not fire.** The factor leg's |IC| (0.0155) is about half the residual's
  (0.0317), so the dollar-explained leg is not doing all the work. But both legs carry the
  *same-signed* reversion and their sum carries the most: nothing is isolated by splitting.
- **KT3 — FIRES.** The paired delta is +0.0044 on GC and −0.0017 / −0.0027 on ES and NQ.
  The sign disagrees between the primary market and **both** siblings, which is the
  preregistered rejection condition.

## Gross, net, baseline, and null comparison

No null was spent. Standing workspace rule: gate the expensive null on the real pass
first clearing its primary metric. The real pass fails, so no re-pairing null was run.

Economic magnitude, which is where the run's most useful result sits:

| market | predictor | q5−q1 mean forward 30-min move | in ticks | vs round trip |
|---|---|---|---|---|
| GC | past_GC_30 | −0.10 bp [−0.57,+0.38] | −0.15 | ~$20 |
| GC | resid_GC_30 | +0.16 bp [−0.38,+0.71] | +0.24 | ~$20 |
| ES | past_ES_30 | **+0.89 bp [+0.19,+1.63]** | +1.09 | ~$25 |
| NQ | past_NQ_30 | **+1.12 bp [+0.22,+1.95]** | +3.34 | ~$10 |

**The rank statistic and the mean statistic disagree on every market, and they disagree
in opposite directions.** Gold has a strongly significant *rank* reversion whose *mean*
quintile spread is indistinguishable from zero. ES and NQ have *rank* ICs
indistinguishable from zero whose *mean* quintile spreads are significantly **positive**
(momentum). The reconciliation is distributional: equity intraday momentum lives in the
tails — large moves continue, typical moves do not — so a rank statistic, which weights
the median observation, cannot see it. Gold's reversion is the mirror image: it is a
middle-of-the-distribution effect with no expectancy attached.

This directly extends `vei_exploration` EXP-0013's warning ("do not read a rank IC of a
conditioning variable against skewed per-trade P&L; it tracks the median trade"). Here the
same trap appears on *raw returns*, not on trade P&L, and it flips the conclusion on both
asset classes. It also supplies a mechanical explanation for why `futures/nq/noise_vwap`'s
**breakout** momentum works on NQ/ES: a breakout rule trades the tail, which is the only
part of the distribution where the momentum lives.

## Regimes, sensitivity, and alternative explanations

- **Shared-endpoint (bid-ask bounce) artifact — controlled, survives.** `past` and `fwd`
  share the close at the decision bar, so pricing error there mechanically induces
  negative correlation. Re-measuring with `pastlag` (ending one bar earlier, sharing no
  price) gives GC −0.0315 versus −0.0359, i.e. **88% retained**. Gold's 30-minute rank
  reversion is a property of the tape, not of the sampling.
- **The dollar's own autocorrelation — a real artifact, caught.** IC(past_dxy_30,
  fwd_dxy_30) = −0.0464 [−0.0543,−0.0376], and −0.0311 with the shared endpoint removed.
  **The dollar itself reverts intraday more strongly than gold or the indices do.** This
  invalidates the tempting reading of the dollar-hedged-target panel: `fwdresid` contains
  −β·fwd_dxy and `factor` contains +β·past_dxy, so their correlation mechanically inherits
  −β²·corr(past_dxy, fwd_dxy), which is **positive** when the dollar reverts. The
  +0.0193 (ES) / +0.0202 (NQ) "factor leg predicts the hedged return" cells are that
  artifact and carry no equity information. Reported, not interpreted.
- **Era split.** GC's paired delta is −0.0009 [−0.0050,+0.0038] in 2011-2018 and +0.0089
  [+0.0028,+0.0155] in 2019-2026. The only cell where the decomposition "helps" is one
  era of one market — a 2-cell split read after the fact.
- **Staleness.** Restricting to dollar-fresh decisions (94.8% of rows) changes nothing
  materially on any market (GC delta +0.0045 versus +0.0044).
- **(W,H) surface.** All nine GC cells are positive (+0.0007..+0.0053) and all but two
  ES/NQ cells are negative. Read as a slope, not an argmax: the sign pattern is
  consistent, small, and market-specific — i.e. it tracks whether the market reverts, not
  whether the decomposition adds information.
- **Alternative explanation for the whole result.** The residual is the raw move minus a
  noisily-estimated β times a correlated series. Subtracting an estimated quantity adds
  estimation variance. On a market where the raw predictor already works (gold), that can
  only degrade it; on markets where the raw predictor is ~0 (ES/NQ), the |IC| "improvement"
  from 0.0004→0.0014 is a ratio of two numbers that are both statistically zero. This
  explanation is sufficient for everything observed and is simpler than the flow mechanism.

## Artifact and implementation risks

- In-run identities asserted: `beta=0` reproduces raw momentum exactly (max|diff| 0.0);
  `resid + factor == past` to 1.7e-18 on all three markets.
- β is fitted on 20 strictly prior sessions and is verified by test to be blind to its own
  session and the future (`tests/test_core.py`).
- Roll bars are excluded from every return; the roll-adjusted level is tested to have no
  splice jump while keeping the real move.
- Residual risk carried: β is estimated through the origin on RTH 1-minute returns and
  applied to 15/30/60-minute windows. A horizon-dependent β would change the split. This
  is checked at the overnight horizon in EXP-0004 (β_on −0.968 versus β_rth −0.902 for
  gold — close) but not at intraday horizons.

## Builder interpretation

The hypothesis is dead and the reason is clean: **at a 30-minute intraday horizon the
dollar decomposition does not separate anything.** Both legs carry the same-signed effect
and the undecomposed move carries the most. The flow story (idiosyncratic moves continue
because parent orders are worked over time) finds no support at this horizon.

The run's value is in three by-products, in descending order of importance:

1. **Rank and mean disagree, oppositely, on both asset classes** (see above). This is the
   most transferable thing the project has produced and it applies to essentially every
   IC reported in this workspace.
2. **A cross-asset reversion ordering at 30 minutes**: DXY (−0.031 endpoint-corrected)
   reverts more than GC (−0.032 raw / −0.0315 corrected), and ES/NQ do not revert at all
   in rank terms. Gold behaving like a currency rather than like an index is consistent
   with `futures/gc`'s repeated finding that momentum systems do not transfer to gold.
3. **A reusable, tested causal dollar factor** (`core/data.py`), built from published ICE
   weights rather than a fitted PCA, with a per-slot staleness report.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending
- Note for the reviewer: the preregistration defect (signed delta versus |IC|) is the
  first thing to check. The builder's position is that KT3 fires regardless of which
  reading is taken, so the rejection does not depend on resolving it — but a reviewer who
  disagreed would still have to explain the 87.9% retention on the primary market.

## Promotion decision

- `reports/FINDINGS.md`: findings A (decomposition rejected) and B (rank versus mean).
- `MEMORY.md`: recorded.
- Shared `LEARNINGS.md`: finding B is a candidate once it has been checked on a second
  project; it is a claim about statistics, not about this tape, so it should transfer —
  but it has been verified in one project only and stays here until it is not.
