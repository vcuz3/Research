# EXP-0005 Results Discussion

- Hypothesis: `HYP-0003` — Follow-up on EXP-0003's one live cell: is gold's coherence momentum contrast simply the VOLATILITY confound (KT2) in a double-sorted form?
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: within-(slot x volatility-quintile) momentum contrast on cohz at matched 30% rate, 90% session-block CI, plus a 100-draw rule-18 re-pairing null
- Kill test: the contrast collapses toward zero once the top/bottom coherence split is made WITHIN volatility quintiles as well as within slots
- Evidence: `gold_coherence.txt` (this directory)

## Result versus hypothesis

**The kill test fires. Gold's coherence contrast was the volatility confound.**

| market | slot-matched only (EXP-0003) | ALSO volatility-matched | mirror: volatility given coherence |
|---|---|---|---|
| GC | **+0.0496 [+0.0069,+0.0853]** | **−0.0047 [−0.0274,+0.0272]** | +0.0020 [−0.0244,+0.0341] |
| ES | +0.0179 [−0.0318,+0.0676] | −0.0100 [−0.0347,+0.0212] | +0.0058 [−0.0260,+0.0369] |
| NQ | +0.0191 [−0.0323,+0.0632] | −0.0348 [−0.0630,−0.0045] | −0.0104 [−0.0400,+0.0244] |

Adding volatility quintiles to the matching takes gold from a clearly significant +0.0496
to **−0.0047 with a CI centred on zero**. HYP-0003's KT2 was the right control; it simply
needed the double-sorted form rather than a side-by-side comparison of two selectors.

The **mirror** arm closes the alternative reading. If the pair carried anything jointly,
volatility conditioned on coherence should show it; instead it is +0.0020 on gold, also
centred on zero. Neither label carries a momentum contrast once the other is held fixed.

**The matching is verified, not assumed.** The coherence spread between the cells is
essentially untouched by the extra conditioning (ES high/low mean coherence 0.451/0.093 in
EXP-0003 versus 0.439/0.095 here), while the volatility ratio between cells falls from
1.46 to 1.11. The contrast therefore did not disappear because the split was weakened — it
disappeared because the volatility gradient was removed.

## Gross, net, baseline, and null comparison

Re-pairing null, 100 draws, on the vol-neutral arm:

| market | real | null mean | null sd | z | frac ≥ real |
|---|---|---|---|---|---|
| GC | −0.0047 | −0.0012 | 0.0172 | −0.20 | 0.600 |
| ES | −0.0100 | +0.0025 | 0.0212 | −0.59 | 0.700 |
| NQ | −0.0348 | +0.0011 | 0.0194 | −1.86 | 0.940 |

The null centres at zero on all three markets — the well-behaved result, confirming the
re-pairing destroys the contemporaneous pairing without introducing a bias. Every real
value sits inside the band. Gold's EXP-0003 near-miss (frac 0.067) becomes frac 0.600.

Economic dose-response, gross and before costs (side = sign of the trailing 30-minute
move, P&L = side × the next 30-minute move, non-overlapping):

| market | cell | gross bp/bet | ticks | $/contract | session-clustered t |
|---|---|---|---|---|---|
| GC | high coherence | +0.157 | 0.238 | +2.38 | 2.61 |
| GC | low coherence | −0.017 | −0.025 | −0.25 | −0.43 |
| NQ | high coherence | +0.004 | 0.013 | +0.06 | −0.27 |
| NQ | low coherence | +0.452 | 1.353 | +6.76 | 3.59 |
| ES | high / low | +0.211 / +0.204 | 0.258 / 0.250 | +3.22 / +3.12 | −0.65 / 1.59 |

This table is the reason the run ends here rather than continuing. **The three markets
point three different ways**: gold's momentum is concentrated in high coherence, NQ's in
*low* coherence (t = 3.59, the largest single number in the run and the *opposite* of the
hypothesis), and ES is flat between the cells. And gold's surviving cell is worth
+0.238 ticks = **$2.38 per contract against a round trip of roughly $20** — sub-cost by
about eight times even before the sign inconsistency.

## Regimes, sensitivity, and alternative explanations

- **Entanglement, measured.** corr(cohz, rvz) is modest, but the cells built from cohz
  differ in volatility by 1.46x on ES. A low pairwise correlation between two labels does
  not imply the *cells they select* are matched — that is the same "low correlation is
  necessary but not sufficient" lesson as `vei_exploration` finding P, arriving from the
  selection side rather than the feature side.
- **NQ's significant negative.** −0.0348 [−0.0630,−0.0045], with frac ≥ real of 0.940 in
  the null (i.e. in the lower tail). Taken alone it would be "momentum works when the index
  is *decoupled* from the dollar", a coherent inverse story. It is not promoted: gold
  points the other way, ES is flat, and this is one cell of a 3-market × 3-arm table read
  after the primary hypothesis had already failed.
- The vol-neutral arm is a stricter test than EXP-0003's and it uses essentially the same
  rows (38,746 versus 38,766 on gold), so the collapse is not a sample change.

## Artifact and implementation risks

- Volatility quintiles are formed **within each slot** before being crossed with the slot
  key, so the composite key never mixes time-of-day with volatility level.
- The composite key is used for *both* the top/bottom split and the within-cell
  correlation, so the two cells match on slot and volatility for the statistic as well as
  for the selection.
- The 100-draw null rebuilds the whole feature pipeline per draw (β, coherence, z-score,
  quintiles, split), not just the final statistic.
- Residual risk: quintile matching leaves an 11% residual volatility gradient between the
  cells. A finer conditioning would remove more, at the cost of thinner cells. Given the
  contrast is already centred on zero, finer matching could only push it further from the
  hypothesis.

## Builder interpretation

This run does the job the whole project was set up to make possible: it takes the single
attractive number the exploration produced and destroys it with the control that was
written down before the number existed.

The general statement worth keeping is about *selection*, not about gold: **matching a
regime split on time of day is not enough; the split must also be matched on volatility,
because almost every intraday label is correlated with volatility.** EXP-0003 matched slot
composition exactly — the cells had identical sizes and identical time-of-day mixes — and
that was still not sufficient. The workspace's existing discipline (matched selection
rate, same-slot z-score) was necessary and incomplete.

That also settles HYP-0003's larger question. Factor coherence was chosen precisely
because it was *not* a volatility variable, in response to the standing caution that a new
overlay needs a non-volatility mechanism. It turned out to be one anyway, once measured as
a selector rather than as a feature. Sixth volatility overlay, sixth rejection.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: finding E.
- `MEMORY.md`: recorded; the coherence channel is closed at intraday cadence.
- Shared `LEARNINGS.md`: **candidate** — "match a regime split on volatility, not only on
  time of day" is a method claim, it changed the verdict of a run here, and it applies to
  every conditioning study in this workspace. Held pending confirmation on a second
  project, per the entry criteria.
