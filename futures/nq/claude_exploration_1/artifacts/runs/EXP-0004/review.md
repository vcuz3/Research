# EXP-0004 Results Discussion

- Hypothesis: `HYP-0004` — Gold under-reacts overnight to dollar moves because its overnight book is thin; the shortfall is completed once NY liquidity arrives
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: Spearman IC(short_GC, rth_GC) with 90% session bootstrap CI; sign declared POSITIVE in advance
- Kill test: KT1 primary IC CI includes 0 or the sign is negative; KT2 the unconstrained (on_GC, on_dxy) pair lacks the mechanism sign pattern; KT3 the effect is as strong on ES
- Evidence: `overnight_impulse.txt` (this directory)

## Result versus hypothesis

**REJECTED — all three kill tests fire.** This is the cleanest rejection of the four.

- **KT1 FIRES on both counts.** IC(short_GC, rth_GC) = **−0.0301 [−0.0570,+0.0000]**:
  the CI touches zero, and the **sign is negative**, which was declared in advance as a
  rejection condition. The mechanism predicted the unabsorbed dollar-implied move is
  *completed* during RTH; the data give the opposite sign.
- **KT2 FIRES.** The unconstrained regression `rth ~ a + b1·on_GC + b2·on_dxy` gives
  b1 = +0.0261 [−0.0156,+0.0727] and b2 = −0.0338 [−0.1038,+0.0352], with **R² = 0.0017**.
  The mechanism requires b1 < 0 and b2 > 0. Both coefficients are the wrong sign and both
  CIs span zero. The overnight→RTH channel is empty at this resolution.
- **KT3 FIRES.** IC(short, rth) is −0.0301 on GC, −0.0302 on ES and −0.0239 on NQ. The
  liquidity-mismatch mechanism predicts a materially *weaker* effect on ES, whose
  overnight book is far deeper than gold's. The three are indistinguishable, which points
  at the decomposition arithmetic rather than at gold's overnight illiquidity.

The decisive detail is that **the shortfall is very nearly the negative of the raw
overnight gap**: sd(on_GC) = 81.2 bp versus sd(short_GC) = 75.9 bp, and the dollar explains
only R² = 0.127 of the overnight gold gap. So IC(short, rth) ≈ −IC(on, rth), and the two
print as −0.0301 and +0.0301. **KT2's degenerate control is not merely passed, it is
exact**: the "dollar shortfall" carries nothing the raw overnight gap does not, because it
is essentially the same variable with a sign flip.

## Gross, net, baseline, and null comparison

No re-pairing null was spent — the hypothesis' own gating rule was that the null runs only
if the primary clears KT1 and KT2. Neither cleared. (Standing workspace rule: gate the
expensive null on the success metric.)

Economic size, on the quintile spread of the shortfall against the RTH move:

| market | q5−q1 mean RTH move | ticks | $/contract |
|---|---|---|---|
| GC | −7.75 bp [−14.76,−0.85] | −11.7 | −117 |
| ES | −5.83 bp [−14.72,+2.97] | −7.1 | −89 |
| NQ | −3.39 bp [−15.03,+6.61] | −10.1 | −51 |

Only gold's spread excludes zero and it is **negative** — the reverse of the declared
direction — and the q1..q5 profile is non-monotone (+1.74, +1.54, −1.41, +1.93, −6.02),
driven entirely by the top cell. That is a shape to distrust, not to trade.

## Regimes, sensitivity, and alternative explanations

- **Where the sign becomes significant.** The GC first-hour cell is −0.0526
  [−0.0821,−0.0226]; the rest-of-session cell is +0.0018 [−0.0279,+0.0305]. Whatever this
  is, it happens in the first RTH hour and then stops. Read with the sign reversed, it
  says gold's *idiosyncratic* overnight move **continues** into the first NY hour rather
  than reverting — the mirror of the hypothesis. But per the paragraph above it is
  indistinguishable from plain overnight-gap continuation.
- **Weekend split (post-hoc).** GC `gap_days > 1` gives −0.1347 [−0.1949,−0.0698] on 800
  observations against −0.0017 [−0.0381,+0.0326] for single-day gaps. Recorded and
  explicitly **not promoted**: one cell of a 4-split × 3-market table read after the
  primary failed is a sliced null. It would need its own preregistration and its own null.
- **Era split.** GC 2011-2018 +0.0075 [−0.0357,+0.0510]; 2019-2026 −0.0593
  [−0.1020,−0.0236]. The sign inverts across eras on the primary market.
- **Horizon-matched β — the pre-declared objection, checked and cleared.** HYP-0004
  flagged in advance that β is fitted on RTH 1-minute returns and applied to an overnight
  window. Re-estimating β from *overnight* gaps over the trailing 60 sessions gives
  β_on = −0.968 versus β_rth = −0.902 for gold, and IC(short_on, rth) = −0.0260
  [−0.0553,+0.0014]. The rejection is not a β-misspecification artifact.
- **Alternative explanation, and the one the builder believes.** Gold's overnight gap is
  87% idiosyncratic. Any "shortfall" built on a factor with R² = 0.13 is dominated by the
  raw gap, so the test had far less power to isolate a dollar channel than the design
  assumed. That is a design limitation as much as a result: a decomposition is only
  informative where the factor leg is large enough for the residual to be a genuinely
  different variable, and overnight it is not.

## Artifact and implementation risks

- The overnight change is computed on the roll-adjusted continuous log level, so a
  contract change inside the gap does not appear as a move (rule 11, tested).
- `gap_days` is recorded and split on, so a 65-hour weekend gap is never silently pooled
  with a 17-hour overnight gap.
- 3,672-3,707 of 3,710 sessions are used depending on the arm; the first session has no
  predecessor and the leading edge of the β window costs a few more.
- **Power, declared in advance:** with ~3,700 observations the detectable |IC| floor is
  about 0.03, and the primary estimate sits exactly at that floor. "No effect" here means
  "no effect larger than about 0.03", not a proof of zero.

## Builder interpretation

The mechanism is rejected, and the reason is more instructive than the verdict: **the
decomposition was applied where the factor explains almost nothing.** Intraday (EXP-0001)
the dollar explains ~16% of gold's 30-minute variance and the split still added nothing;
overnight it explains 13% and the "shortfall" degenerates into the raw gap with a sign
flip. Taken with EXP-0001 this is a general lesson about this class of test rather than a
fact about gold.

The one descriptive item worth keeping is the first-hour asymmetry, and only as a note:
gold's overnight idiosyncratic move continues into the first NY hour and is spent by
mid-session. That is consistent with `futures/gc` EXP-0002 (gold's tradable behaviour is
tied to the equity cash session), and it is the only cell where a sign-stable,
mechanism-shaped pattern appears — pointed the opposite way from the hypothesis.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: finding F.
- `MEMORY.md`: recorded; the overnight channel is closed.
- Shared `LEARNINGS.md`: not eligible on its own. The transferable half — "a factor
  decomposition is only informative where the factor's R² is large" — is stated in
  FINDINGS and is carried jointly with EXP-0001.
