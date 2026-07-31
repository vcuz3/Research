# Findings — Cross-Asset Macro Exploration (DXY / GC / ES / NQ)

Reviewed evidence, by finding. Every number here comes from an immutable artifact under
`artifacts/runs/EXP-XXXX/` and is reproducible with the command in `experiments/ledger.csv`.

**Headline: all four preregistered hypotheses were REJECTED.** The transferable output of
the project is three method findings (B, E, G) and two descriptive facts about the tape
(A's reversion ordering, F's first-hour asymmetry). Nothing here is an edge, and nothing
here is a candidate for one.

Status key: `confirmed` = supported by an executed control-bearing run; `descriptive` =
measured but not tested against a null; `rejected` = the preregistered kill test fired.

---

## A / EXP-0001 (HYP-0001) — the dollar decomposition separates nothing intraday — REJECTED

The idea was that an intraday move splits into a mechanical dollar repricing (which should
not continue) and idiosyncratic order flow (which should, because parent orders are worked
over time). Tested by replacing the momentum predictor `past_I_30` with
`resid_I_30 = past_I_30 − β_I · past_dxy_30`, where β is fitted on the 20 **strictly prior**
sessions.

**KT3 fired**: the paired within-slot IC delta is +0.0044 [+0.0005,+0.0078] on GC but
−0.0017 (ES) and −0.0027 (NQ) — the sign disagrees between the primary market and both
siblings.

**The preregistered metric was also mis-signed for the effect that exists**, and this is
recorded as a defect rather than glossed. HYP-0001 claimed the residual would *predict
better*, i.e. carry a larger |IC|. The metric was written as a signed delta on the
assumption of momentum. Gold's 30-minute effect is **reversion**, so a positive signed
delta means the residual is *worse*. On the hypothesis' actual claim gold reads
**|IC| 0.0360 → 0.0317 = 87.9% of raw: the decomposition destroys 12% of the signal.**

The degenerate control (KT2) explains why. Both legs carry the *same-signed* reversion —
factor |IC| 0.0155, residual 0.0317 — and their undecomposed sum carries the most. There
is nothing to isolate. A sufficient and simpler explanation for everything observed:
subtracting a noisily-estimated β times a correlated series adds estimation variance, so
it can only degrade a predictor that already works.

**The reversion ordering is the durable descriptive output**, endpoint-corrected (see G):

| series | IC(past_30, fwd_30) | endpoint-corrected |
|---|---|---|
| DXY | −0.0464 [−0.0543,−0.0376] | −0.0311 |
| GC | −0.0360 [−0.0440,−0.0264] | −0.0315 (88% retained) |
| ES | +0.0004 [−0.0074,+0.0083] | +0.0040 |
| NQ | −0.0040 [−0.0119,+0.0052] | −0.0033 |

**The dollar reverts intraday more than gold does; the equity indices do not revert at
all.** Gold behaving like a currency rather than like an index is consistent with
`futures/gc`'s repeated finding that momentum systems do not transfer to it.

One artifact caught and quarantined: the "factor leg predicts the dollar-hedged forward
return" cells (+0.0193 ES / +0.0202 NQ) are mechanical. `fwdresid` contains −β·fwd_dxy and
`factor` contains +β·past_dxy, so their correlation inherits −β²·corr(past_dxy, fwd_dxy),
which is positive because the dollar reverts. Reported, not interpreted.

Status: **rejected** (mechanism); **confirmed** (reversion ordering).
Evidence: `artifacts/runs/EXP-0001/`.

---

## B / EXP-0001 — rank IC and mean spread give OPPOSITE readings, on both asset classes

The most transferable result in the project, and it was a by-product.

| market | within-slot rank IC | q5−q1 **mean** forward move | in ticks |
|---|---|---|---|
| GC | **−0.0360 [−0.0440,−0.0264]** | −0.10 bp [−0.57,+0.38] | −0.15 |
| ES | +0.0004 [−0.0074,+0.0083] | **+0.89 bp [+0.19,+1.63]** | +1.09 |
| NQ | −0.0040 [−0.0119,+0.0052] | **+1.12 bp [+0.22,+1.95]** | +3.34 |

Gold has a strongly significant rank **reversion** whose mean spread is indistinguishable
from zero. ES and NQ have rank ICs indistinguishable from zero whose mean spreads are
significantly **positive** — momentum. The two statistics disagree on all three markets,
and they disagree in *opposite directions* across asset classes.

The reconciliation is distributional. Equity intraday momentum lives in the **tails**:
large moves continue, typical moves do not, so a rank statistic — which weights the median
observation — cannot see it. Gold's reversion is the mirror: a middle-of-the-distribution
effect with no expectancy attached.

This extends `vei_exploration` EXP-0013's warning ("do not read a rank IC of a conditioning
variable against skewed per-trade P&L; it tracks the median trade") in two ways: the trap
appears on **raw returns**, not only on trade P&L, and it **flips the conclusion in both
directions** rather than merely inflating one. It also supplies a mechanical explanation
for why `futures/nq/noise_vwap`'s **breakout** momentum works on NQ/ES — a breakout rule
trades the tail, which is the only part of the distribution where the momentum is.

Practical rule: report both, every time, and say which one the decision consumes. A book
that sizes equally per bet consumes the mean; a book that is truncated by barriers may
consume something closer to the median.

Status: **confirmed** (within this project; candidate for shared learnings).
Evidence: `artifacts/runs/EXP-0001/residual_momentum.txt`, final section.

---

## C / EXP-0002 (HYP-0002) — the dollar does NOT lead; the "lead" is bidirectional — REJECTED

At a 5-minute non-overlapping clock, the forward partial IC pIC(past_dxy, fwd_I | past_I)
is real and correctly signed on GC (−0.0049 [−0.0078,−0.0020]) and ES. **KT1 does not
fire.** Without a further control this run would have reported a confident lead-lag that
also decays with horizon exactly as a transmission lag should.

**KT2 — the symmetry control — fires and settles it:**

| market | forward | reverse | \|rev\|/\|fwd\| |
|---|---|---|---|
| GC | −0.0049 | **−0.0115** | **2.36** |
| ES | −0.0043 | −0.0059 | 1.37 |
| NQ | −0.0022 (ns) | −0.0059 | 2.72 |

Gold appears to lead the dollar **more than twice as strongly** as the dollar leads gold.
A news-priced-in-FX-first mechanism cannot produce a stronger reverse effect. This is the
signature of shared or imperfectly-synchronised contemporaneous information.

**It is not a staleness artifact** (KT3 does not fire): the EUR-only basket — 0.42%
forward-filled minutes versus 4.70% for the 4-leg — retains the whole effect
(GC −0.0044 versus −0.0049), as does the dollar-fresh subsample. The measurement is sound;
the interpretation is what fails.

**The mechanism's own differential prediction also fails.** HYP-0002 predicted a weaker
lead into ES than into GC, because ES is more liquid than the FX basket. Observed:
−0.0043 versus −0.0049, effectively equal.

Scale: gold's marginal dollar effect, double-sorted, is −0.18 bp = **0.27 ticks** against a
~$20 round trip. The contemporaneous link is −0.31 Pearson / −0.37 within-block rank — the
cross-asset relationship is about **75x larger contemporaneously than at one 5-minute
lag**, which is what efficient transmission looks like.

Status: **rejected**.
Evidence: `artifacts/runs/EXP-0002/`.

---

## D / EXP-0003 (HYP-0003) — factor coherence is not a momentum regime — REJECTED

Coherence = |corr(1-min instrument returns, 1-min dollar returns)| over the trailing 60
minutes, on dollar-fresh minutes only, normalised to the trailing 90-session same-slot
z-score. Split at a matched 30% rate *within each slot*, so the two cells have identical
size and identical time-of-day composition.

**KT1 fired**: ES +0.0179 [−0.0326,+0.0743] and NQ +0.0191 [−0.0337,+0.0637], both CIs
spanning zero on the two preregistered markets.

**KT3 fired**: the rule-18 re-pairing null (each session's equity path paired with a
*different* session's dollar path from the same calendar year, whole pipeline recomputed)
centres near zero on all three markets — the well-behaved outcome — and the real ES/NQ
values sit comfortably inside it (37% and 30% of draws beat them).

The label's calibration worked exactly as `vei_exploration` finding I predicts: a fixed cut
on RAW coherence selects 33.7% of the 10:29 ES slot and 26.1% of the 13:29 slot, while the
same-slot z-score holds 28.3-30.9% everywhere. Gold has the strongest raw time-of-day
profile of the three (slot-mean spread 0.101 versus 0.036 for ES).

Two cautions the run generated about itself: the selection-rate dial swings ES across
+0.0806 / +0.0179 / −0.0031 at 20/30/40% — the 20% cell is exactly the number that would
have been reported as a finding had the rate not been fixed in advance — and no market is
significant in both eras.

Gold (a **declared third market**) printed +0.0496 [+0.0077,+0.0945] with a null p of
0.067. Carried into EXP-0005 as a screen, and killed there.

Status: **rejected**.
Evidence: `artifacts/runs/EXP-0003/`.

---

## E / EXP-0005 — matching on time of day is NOT enough; match on VOLATILITY too

Gold's coherence contrast, under progressively stricter matching:

| market | slot-matched (EXP-0003) | ALSO volatility-matched | mirror: volatility given coherence |
|---|---|---|---|
| GC | **+0.0496 [+0.0069,+0.0853]** | **−0.0047 [−0.0274,+0.0272]** | +0.0020 [−0.0244,+0.0341] |
| ES | +0.0179 [−0.0318,+0.0676] | −0.0100 [−0.0347,+0.0212] | +0.0058 [−0.0260,+0.0369] |
| NQ | +0.0191 [−0.0323,+0.0632] | −0.0348 [−0.0630,−0.0045] | −0.0104 [−0.0400,+0.0244] |

**Gold's contrast collapses from a clearly significant +0.0496 to −0.0047 centred on zero**
once the top/bottom coherence split is made within volatility quintiles as well as within
slots. The 100-draw re-pairing null on the vol-neutral arm centres at zero on all three
markets and gold's frac≥real goes from 0.067 to 0.600.

**The collapse is not a weakened split.** The coherence spread between the cells is
essentially unchanged by the extra conditioning (ES high/low mean coherence 0.451/0.093
before, 0.439/0.095 after), while the volatility ratio between cells falls from 1.46 to
1.11. The contrast vanished because the volatility gradient was removed, not because the
selection was diluted.

**The general method claim**, which is what this run is for: *matching a regime split on
time of day is not sufficient. Almost every intraday label is correlated with volatility,
so the split must be matched on volatility as well.* EXP-0003 matched slot composition
**exactly** — identical cell sizes, identical time-of-day mixes — and that was still not
enough. The workspace's existing discipline (matched selection rate, same-slot z-score,
`vei_exploration` findings H and I) is necessary and incomplete.

A related sub-lesson, arriving from the selection side rather than the feature side of
`vei_exploration` finding P: **a modest pairwise correlation between two labels does not
imply the cells they select are matched.** cohz and rvz are not strongly correlated, yet
cohz-selected cells differ in volatility by 1.46x.

Economically the run also ends the question: the three markets point three different ways
(gold's momentum concentrates in *high* coherence at t=2.61; NQ's in *low* coherence at
t=3.59, the opposite of the hypothesis; ES is flat), and gold's surviving cell is worth
**+0.238 ticks = $2.38 per contract against a ~$20 round trip** — sub-cost by about eight
times, before the sign inconsistency.

Status: **confirmed** (method claim); **rejected** (the gold screen).
Evidence: `artifacts/runs/EXP-0005/`.

---

## F / EXP-0004 (HYP-0004) — the overnight dollar channel is empty — REJECTED

Mechanism: gold's overnight book is thin, so a dollar move at 03:00 ET is fully priced in
FX but only partly in COMEX gold; the shortfall `β_GC·on_dxy − on_GC` should be completed
when New York liquidity arrives. **All three kill tests fired.**

- **KT1**: IC(short_GC, rth_GC) = −0.0301 [−0.0570,+0.0000] — CI touches zero and the sign
  is **negative**, declared in advance as a rejection condition.
- **KT2**: the unconstrained regression `rth ~ a + b1·on_GC + b2·on_dxy` gives b1 = +0.0261
  and b2 = −0.0338, both wrong-signed, both CIs spanning zero, **R² = 0.0017**.
- **KT3**: −0.0301 (GC) / −0.0302 (ES) / −0.0239 (NQ). The mechanism requires a materially
  weaker effect on ES, whose overnight book is far deeper. They are indistinguishable.

**Why the test had less power than the design assumed, and the lesson that generalises.**
The dollar explains only **R² = 0.127** of gold's overnight gap (sd 81.2 bp raw versus
75.9 bp for the shortfall), so the "shortfall" is very nearly the negative of the raw
overnight gap — the two ICs print as −0.0301 and +0.0301. Combined with EXP-0001 (where the
dollar explains ~16% of gold's 30-minute variance and the split still added nothing), the
general statement is: **a factor decomposition is only informative where the factor's R²
is large. Below roughly 20% the residual is not a different variable.**

The pre-declared β objection was checked and cleared: a horizon-matched overnight β
(−0.968 versus −0.902 from RTH minutes) gives IC −0.0260 [−0.0553,+0.0014]. The rejection
is not β misspecification.

Descriptive note, sign-reversed from the hypothesis: gold's *idiosyncratic* overnight move
**continues** into the first RTH hour (−0.0526 [−0.0821,−0.0226] on the shortfall, so
positive on the residual) and is spent by mid-session (+0.0018 in the rest). Consistent
with `futures/gc` EXP-0002 (gold's tradable behaviour is tied to the equity cash session) —
but indistinguishable from ordinary overnight-gap continuation.

Not promoted, recorded as a sliced null: GC `gap_days > 1` gives −0.1347
[−0.1949,−0.0698] on 800 observations. One cell of a 4-split × 3-market table read after
the primary failed.

Power, declared in advance: with ~3,700 sessions the detectable |IC| floor is about 0.03
and the primary estimate sits at that floor. "No effect" means "no effect larger than
about 0.03".

Status: **rejected**.
Evidence: `artifacts/runs/EXP-0004/`.

---

## G / EXP-0001 + EXP-0002 — the shared decision-bar close manufactures reversion

`past` ends and `fwd` starts at the same close, so any pricing error in that one price
(bid-ask bounce, a stale or one-tick print) enters `past` with +1 and `fwd` with −1 and
induces **mechanical negative correlation**. Measured by re-running with `pastlag`, which
ends one bar earlier and shares no price:

| horizon | series | raw | endpoint-corrected | retained |
|---|---|---|---|---|
| 30 min | GC | −0.0359 | −0.0315 | 0.88 |
| 30 min | DXY | −0.0464 | −0.0311 | 0.67 |
| 5 min | GC | −0.0437 | −0.0303 | 0.69 |
| 5 min | ES | −0.0353 | −0.0209 | 0.59 |
| 5 min | NQ | −0.0202 | −0.0131 | 0.65 |
| 5 min | DXY | −0.0472 | −0.0210 | **0.44** |

**At 5 minutes, 31-56% of measured reversion is sampling artifact**, worst on the synthetic
dollar index, which is built from four forward-filled legs and therefore carries the most
endpoint noise. At 30 minutes the cost is 12-33%. In every case the majority of the effect
survives, so the reversions reported above are real — but any short-horizon reversion
number quoted without this control is inflated by a third to a half.

The control costs one extra column. It should be standard for any reversal claim.

Status: **confirmed**.
Evidence: `artifacts/runs/EXP-0001/residual_momentum.txt`, `artifacts/runs/EXP-0002/lead_lag.txt`.

---

## H — data-layer results (rule 9a), from `reports/DATA_QUALITY.md`

- **A synthetic DXY from CME FX futures is a viable causal factor**, built from published
  ICE weights (never a fitted PCA, which would be a two-sided statistic under rule 8).
  Every leg enters `log DXY` with a **negative** coefficient because all CME FX contracts
  are quoted as USD per unit of foreign currency.
- **Drop CHF.** The 5-leg basket is forward-filled on **10.47%** of RTH minutes; the 4-leg
  basket (EUR/JPY/GBP/CAD) on **4.70%**, while the two agree at corr **0.9992** on
  30-minute returns. CHF carries 3.6% of the index and more than doubles the staleness.
- **FX staleness is strongly time-of-day dependent** — 0.5% in the first RTH hour rising to
  10.7% in the last for the 4-leg basket (1.2% → 23.6% for the 5-leg) — because FX volume
  collapses after the London close. Any cross-asset statistic measured late in the US
  session is measured on a thinner dollar. This is a substantive fact about the data, not
  only a defect: it is why every coherence statistic here is computed on dollar-fresh
  minutes and z-scored per slot.
- EUR-only correlates 0.9637 with the full basket at 30-minute returns, which is what makes
  it a usable staleness control rather than a different variable.

Status: **confirmed**.

---

## What would have been concluded without the controls

Worth recording plainly, because it is the argument for the whole apparatus. Taking only
the arms that a normal exploratory pass would have run:

- EXP-0002 would have reported *"the dollar leads gold at 5 minutes, correctly signed, CI
  excludes zero, robust to a staleness control, and decaying with horizon exactly as a
  transmission lag should"*. The reverse direction — one extra line — showed the reverse
  effect is 2.4x larger.
- EXP-0003 would have reported *"gold's intraday momentum is significantly stronger when
  gold is moving with the dollar, +0.0496, CI excludes zero, and it beats the volatility
  selector"*. Matching the split on volatility took it to −0.0047.
- EXP-0001 would have reported gold's 30-minute reversion at −0.036 as a tradable rank
  signal. Its mean quintile spread is −0.15 ticks, indistinguishable from zero.

Three of the five runs were decided by a **degenerate or reversed control** — the factor
leg, the reverse direction, the volatility-matched split — exactly as `vei_exploration`
findings H and P predicted they would be.
