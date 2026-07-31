# EXP-0002 Results Discussion

- Hypothesis: `HYP-0002` — The dollar LEADS gold and equity indices intraday: lagged DXY returns predict forward returns beyond own momentum
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: within-block partial Spearman IC pIC(past_dxy_5, fwd_GC_5 | past_GC_5), 90% session-block bootstrap CI
- Kill test: KT1 primary partial IC CI includes 0; KT2 the REVERSE partial IC is within a factor of 2 of the forward one; KT3 the effect vanishes on the EUR-only dollar proxy
- Evidence: `lead_lag.txt` (this directory)

## Result versus hypothesis

**REJECTED — KT2, the symmetry control, fires decisively.**

| market | FORWARD (dollar leads) | REVERSE (instrument leads) | \|rev\|/\|fwd\| |
|---|---|---|---|
| GC | −0.0049 [−0.0078,−0.0020] | **−0.0115 [−0.0146,−0.0083]** | **2.36** |
| ES | −0.0043 [−0.0075,−0.0011] | −0.0059 [−0.0097,−0.0023] | 1.37 |
| NQ | −0.0022 [−0.0053,+0.0006] | −0.0059 [−0.0088,−0.0030] | 2.72 |

- **KT1 does not fire on GC or ES.** The forward partial IC excludes zero with the
  declared negative sign on both. Taken alone this would read as "yes, the dollar leads".
- **KT2 FIRES, and worse than the threshold.** The preregistration said KT2 fires if the
  reverse is *within a factor of two* of the forward. On every market the reverse is not
  merely comparable — it is **larger**, by 1.4x to 2.7x. Gold appears to lead the dollar
  more than twice as strongly as the dollar leads gold. That is the textbook signature of
  shared or imperfectly-synchronised contemporaneous information, not of transmission. A
  news-priced-in-FX-first mechanism cannot produce a *stronger* reverse effect.
- **KT3 does not fire.** The EUR-only proxy retains essentially the whole effect
  (GC −0.0044 versus −0.0049; ES −0.0044 versus −0.0043), as does the dollar-fresh
  subsample. So it is **not** a stale-price artifact — the measurement is sound, the
  interpretation is what fails.

## Gross, net, baseline, and null comparison

No null was spent; the real pass fails its own kill test.

Scale, which is what settles it economically. Double-sorted (dollar quintile *within*
quintiles of the instrument's own trailing move, so the number is the dollar's marginal
contribution):

| market | forward 5-min move, top-vs-bottom dollar quintile | ticks | round trip |
|---|---|---|---|
| GC | −0.18 bp [−0.27,−0.12] | **−0.27** | ~$20 |
| ES | −0.08 bp [−0.17,+0.02] | −0.10 | ~$25 |
| NQ | −0.04 bp [−0.16,+0.07] | −0.12 | ~$10 |

Gold's marginal dollar effect is real and about **one quarter of one tick** — roughly a
seventh of a round trip. Even if the mechanism had been confirmed, there is nothing here.

For scale in the other direction: the contemporaneous link is −0.31 (Pearson) / −0.37
(within-block rank) on gold. The claimed *lagged* effect is −0.005. The cross-asset
relationship is ~75x larger contemporaneously than at one 5-minute lag, which is what an
efficiently-transmitted relationship looks like.

## Regimes, sensitivity, and alternative explanations

- **Shared-endpoint control at 5 minutes — a material and honestly-reported hit.** At this
  horizon the shared close at the decision bar is one bar out of five rather than one out
  of thirty, so bid-ask bounce is a much bigger share of any measured reversion:

  | series | IC(past_5, fwd_5) | IC(pastlag_5, fwd_5) | retained |
  |---|---|---|---|
  | GC | −0.0437 | −0.0303 | 0.69 |
  | ES | −0.0353 | −0.0209 | 0.59 |
  | NQ | −0.0202 | −0.0131 | 0.65 |
  | DXY | −0.0472 | −0.0210 | **0.44** |

  So **31-56% of the apparent 5-minute reversion is the sampling artifact**, and it is
  worst on the synthetic dollar index (which is built from four forward-filled legs and
  therefore has the most endpoint noise). The majority survives on every series, so the
  5-minute reversion is real — but any number quoted from this horizon without the lagged
  control is inflated by roughly a third to a half.
- **Horizon term structure.** The forward partial IC decays with H on the 5-minute clock
  (GC −0.0048 → −0.0034 → −0.0017 for H = 5/10/30), which is the shape a transmission lag
  would have. On the 30-minute clock it does not (GC −0.0012 → +0.0027 → −0.0003). The
  decay is consistent with the mechanism but cannot rescue it against KT2.
- **Sibling differential — the mechanism's own prediction, and it fails.** HYP-0002
  predicted a *weaker* lead into ES than into GC because ES is more liquid than the FX
  basket. Observed: GC −0.0049 versus ES −0.0043, effectively equal. The differential the
  mechanism required is absent.
- **Era split.** Only GC 2019-2026 (−0.0069 [−0.0123,−0.0022]) is significant; GC
  2011-2018, ES and NQ in both eras all span zero.
- **The alternative explanation the builder accepts.** Two negatively-correlated series
  that each mean-revert at 5 minutes will show negative *cross*-lag correlations in both
  directions even after linearly partialling out own momentum, because a rank-space linear
  partial does not fully remove a nonlinear or heteroskedastic own-momentum term. The
  symmetric, same-signed, both-directions result is exactly this, and it is simpler than
  a transmission story that would have to explain why gold leads the dollar.

## Artifact and implementation risks

- The 5-minute clock is **non-overlapping**: past (m−5, m] and forward (m, m+5] share no
  bars, so the only overlap risk is the single shared close, which is controlled above.
- Within-slot grouping uses the 30-minute block rather than each of the 78 five-minute
  slots. That is a deliberate choice (documented in the script): the purpose of within-slot
  grouping is to strip time-of-day composition, and 13 blocks do that while keeping ~22k
  observations per cell instead of ~3.7k.
- `nboot=200` rather than 400 for this run, because the 5-minute frame is 289k rows and
  the partial IC is computed per block per draw. CIs are correspondingly a little coarser;
  none of the verdicts turns on a marginal interval.
- Roll bars are excluded from every return; the EUR-only arm re-runs the whole pipeline on
  a differently-constructed dollar rather than reweighting a finished result.

## Builder interpretation

The naive cross-asset story is dead, and it died on the control that was written down for
exactly this purpose. The forward effect *is* statistically real and correctly signed —
which is precisely why the symmetry control was preregistered. Without it, this run would
have produced a confident "the dollar leads gold at 5 minutes, p < 0.05, robust to the
staleness control, decays with horizon as a transmission lag should" — a result that is
wrong, and wrong in a way that no amount of bootstrapping or era-splitting would catch.

The two things worth keeping:

1. **The reverse direction is the cheapest and most decisive control for any lead-lag
   claim**, and it costs one extra line of code. It is more informative here than the
   staleness control, the horizon surface, and the sibling split combined.
2. **The 5-minute shared-endpoint number.** 31-56% of measured short-horizon reversion is
   sampling artifact, worst on a synthetic index. This is a concrete, reusable magnitude
   for any short-horizon reversion study in this workspace.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: finding C, plus the endpoint magnitude in finding G.
- `MEMORY.md`: recorded; the intraday lead-lag channel is closed.
- Shared `LEARNINGS.md`: **candidate** — "test the reverse direction before believing a
  lead-lag" is a method claim that changed this verdict. Held pending a second project.
