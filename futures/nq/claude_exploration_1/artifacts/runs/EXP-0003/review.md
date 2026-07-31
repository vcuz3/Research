# EXP-0003 Results Discussion

- Hypothesis: `HYP-0003` — Macro factor coherence selects the intraday momentum regime, on an axis that is not volatility
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: within-slot momentum contrast top-30% minus bottom-30% of cohz at matched rate and identical slot composition, 90% session-block CI
- Kill test: KT1 contrast CI includes 0 on either ES or NQ or signs disagree; KT2 the volatility-level selector gives an equal or larger contrast; KT3 the real contrast falls inside the rule-18 re-pairing null band
- Evidence: `factor_coherence.txt` (this directory); follow-up in `../EXP-0005/`

## Result versus hypothesis

**REJECTED on both preregistered markets.**

| market | selector | contrast | re-pairing null (30 draws) |
|---|---|---|---|
| ES (primary) | cohz | +0.0179 [−0.0326,+0.0743] | mean +0.0044, frac≥real 0.367 |
| NQ (primary) | cohz | +0.0191 [−0.0337,+0.0637] | mean +0.0033, frac≥real 0.300 |
| GC (declared third) | cohz | **+0.0496 [+0.0077,+0.0945]** | mean −0.0029, frac≥real 0.067 |
| ES | rvz (volatility, KT2) | +0.0040 [−0.0347,+0.0400] | — |
| NQ | rvz (volatility, KT2) | −0.0079 [−0.0414,+0.0210] | — |
| GC | rvz (volatility, KT2) | +0.0170 [−0.0144,+0.0506] | — |

- **KT1 FIRES.** Both primary markets have CIs spanning zero. The preregistration was
  explicit that ES and NQ are near-identical tapes and a regime effect must survive on
  both; neither is significant on its own.
- **KT2 does not fire on this run's form.** Coherence beats the volatility selector in
  point estimate on both primaries (+0.018/+0.019 versus +0.004/−0.008). But that is a
  comparison between two statistically-zero numbers, and EXP-0005 shows the volatility
  control needed a stricter (double-sorted) form to bite.
- **KT3 FIRES on the primaries.** The re-pairing null centres near zero on all three
  markets (+0.0044 / +0.0033 / −0.0029) — the well-behaved outcome, confirming the null
  destroys the pairing without introducing bias. The real ES and NQ values sit comfortably
  inside the band (37% and 30% of draws beat them). Only gold's is near the edge (6.7%,
  z = 1.41).

**Gold is a screen, not a pass**: it was a declared *third* market, its p is marginal on
30 draws, and it is era-dependent (2011-2018 +0.0368 with a CI spanning zero; 2019-2026
+0.0649 excluding zero). It was carried into EXP-0005 for the one confound this run left
open, and **EXP-0005 killed it**.

## Gross, net, baseline, and null comparison

- Unconditional within-slot momentum: ES +0.0139, NQ +0.0125, GC +0.0072. The contrast is
  being asked to move a baseline that is already near zero.
- The re-pairing null is a full-pipeline null (rule 17): the donor dollar path is a real
  dollar path from another session in the same calendar year, and β, coherence, the
  same-slot z-score, the split and the contrast are all recomputed on it. Only the
  contemporaneous pairing is destroyed.
- No economic simulation at this stage; EXP-0005 supplies the dose-response in ticks.

## Regimes, sensitivity, and alternative explanations

- **Rule 9a — the label's calibration works.** A fixed cut on RAW coherence selects 33.7%
  of the 10:29 ES slot and 26.1% of the 13:29 slot; the same-slot z-score holds 28.3-30.9%
  everywhere. The `vei_exploration` finding-I construction transferred exactly as
  advertised, and gold has the strongest raw time-of-day profile of the three (slot-mean
  spread 0.101 versus 0.036 for ES). Coverage is 90.1% — the 09:59 decision is undefined
  because the 60-minute window does not fit, which was declared in advance.
- **The confound, visible in this run's own cell table.** High-coherence cells are also
  high-volatility cells: ES mean trailing RV 21.55 bp versus 14.73 bp, mean |past move|
  16.53 bp versus 11.04 bp. Slot-matching does not remove that. This observation is what
  motivated EXP-0005.
- **Selection-rate sensitivity.** ES swings +0.0806 / +0.0179 / −0.0031 across 20/30/40%.
  A contrast that changes sign along the rate dial is not a stable regime effect — and the
  20% cell is exactly the number that would have been reported as a finding had the rate
  not been fixed in advance.
- **Era split.** No market is significant in both eras.

## Artifact and implementation risks

- Coherence is computed on **dollar-fresh minutes only**, which matters because FX
  staleness rises from 0.5% in the first RTH hour to 10.7% in the last for the 4-leg
  basket. Without that restriction late-session coherence would be mechanically depressed.
- The split is thresholded **within each slot**, so the two cells are tested to have
  identical size and identical slot composition (`tests/test_core.py`).
- The re-pairing permutation is tested to be a derangement stratified by calendar year, so
  no session is paired with itself and no draw compares the 2011 dollar with the 2025 one.
- Residual risk: a 60-observation rolling correlation is noisy and its noise is itself
  volatility-dependent — the exact objection recorded in HYP-0003 before the run, and what
  EXP-0005 addresses.

## Builder interpretation

The hypothesis was that the *composition of drivers* is a regime axis this workspace has
never tested, distinct from the volatility axis it has rejected five times. On the two
markets it was preregistered for, it is not: the contrast is indistinguishable from zero
and indistinguishable from a re-paired dollar.

The gold cell looked live enough to justify one follow-up, and that is where the run's real
value lies. EXP-0005 re-ran the split **within volatility quintiles as well as within
slots** and gold's contrast collapsed from +0.0496 to −0.0047 [−0.0274,+0.0272]. So the
answer to "is coherence a different axis from volatility?" is **no** — on this tape at this
horizon the coherence label is volatility in a cross-asset costume, which makes this the
workspace's sixth volatility-overlay rejection rather than a new kind of one.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: finding D (this run) and finding E (EXP-0005).
- `MEMORY.md`: recorded.
- Shared `LEARNINGS.md`: not eligible alone; the transferable claim is carried jointly
  with EXP-0005.
