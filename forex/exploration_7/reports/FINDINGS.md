# FINDINGS — FX weekend gap mean reversion

**Verdict: NO-GO as a tradable edge.** The reversion is statistically real and
remarkably consistent, but it is (a) not specific to weekends, (b) concentrated
in the first hour, (c) unstable across eras, and (d) approximately the same
size as the spread you must cross to capture it.

Runs: EXP-0001 (preregistered) and EXP-0002 (discovery follow-up).
Preregistration: `experiments/hypotheses/HYP-0001.md`, frozen before any
outcome was computed. Data gate: `reports/DATA_QUALITY.md`.

---

## A. What was tested

Fade the weekend gap: short after an up-gap, long after a down-gap, where the
gap is `log(first tradable open after the break / Friday close)` and "large" is
`|z| >= k` with `z` scaled by the pair's own **prior** 26 weekend gaps. Nine
pairs, 782 canonical weekends, 2011-07 to 2026-07, ~6,700 pair-weekends with a
usable sigma. Returns are per-event, in sigma units, with SEs clustered on
weekend date because all nine pairs share each weekend.

## B. The preregistered test fails

Primary specification (`k=1.5`, entry 5 min after reopen, exit 1 day):

| Condition | Result | |
| --- | --- | --- |
| P1 pooled clustered t ≥ 2 | mean R **+0.531**, t **+1.85** | **FAIL** |
| P2 ≥ 6/9 pairs positive | 8/9 | PASS |
| P3 AUDJPY positive | +0.692 (t 1.35) | PASS |
| P4 60-min-delay retention ≥ 0.5 | 0.54 | PASS |
| P5 gross > 0 | +9.33 pips | PASS |

**One-day reversion is not confirmed.** The honest reason is power, not
absence: at this horizon the clustered SE is 0.289, so the minimum detectable
effect is ~0.58 sigma and the observed 0.53 sigma sits just under it. The
original AUDJPY claim is *directionally* consistent (+0.69 sigma, +15.8 pips)
but AUDJPY alone has n=88 and t=1.35 — that sample cannot separate this from
zero.

> Correction to EXP-0001: its validity gate reported a minimum detectable
> effect of 0.05 sigma. That was wrong — it injected a synthetic effect *on top
> of* the effect already present and then declared detection when real+injected
> cleared t=2. EXP-0002 recomputes MDE as 2×SE. Nothing else in EXP-0001
> depended on it.

## C. What is actually there: a 1-hour effect

Reading the full term structure (discovery — the 1-hour cell was chosen after
seeing the surface, and is scored accordingly in §D):

Pooled mean fade R, entry 5 min after reopen, hold measured **from entry**:

| \|z\| ≥ | H=60 min | H=240 min | H=1440 min | n |
| --- | --- | --- | --- | --- |
| 0.0 | **+0.086 (t 5.94)** | +0.036 (t 1.36) | +0.024 (t 0.37) | 6,723 |
| 1.0 | **+0.227 (t 4.65)** | +0.183 (t 2.31) | +0.294 (t 1.48) | 1,377 |
| 1.5 | **+0.292 (t 4.22)** | +0.246 (t 2.13) | +0.531 (t 1.84) | 787 |
| 2.0 | **+0.369 (t 4.20)** | +0.318 (t 2.09) | +0.995 (t 2.77) | 534 |
| 2.5 | **+0.404 (t 3.84)** | +0.321 (t 1.65) | +1.129 (t 2.46) | 376 |

The 1-hour column is the real object: monotone in gap size, significant at every
threshold, and **9/9 pairs positive** at both k=1.5 and k=2.0. Hit rate 62.4%.
The 1-day column has larger point estimates but roughly 4× the SE, so it is the
same effect plus a day of noise.

Beyond one hour the effect stops accumulating: the continuation view (EXP-0001
§C2) shows the gap-direction return is −0.237 sigma at 60 min and essentially
flat thereafter. Whatever unwinds, unwinds in the first hour.

## D. Controls

**Gap-sign null (selection-aware).** Randomising the gap sign preserves
selection, paths, volatility and counts, and destroys only the link between gap
direction and subsequent direction — the whole claim. Comparing the real
**maximum** |t| over the reproduced 6×3 search against the null distribution of
that same maximum: real 5.94, null mean 1.83, p95 2.86, max 3.75 over 400 draws,
sd 0.545 (non-degenerate). **frac(null ≥ real) = 0.0000.** The direction
information is real and survives the search correction.

**Entry-delay control (the artifact test that matters).** On this archive
`open[t] == close[t−1]` for ~100% of contiguous minutes, so a noisy reopen print
inflates the measured gap *and* flatters the fade from the next bar. Paired on
identical weekends, with hold duration held constant, k=1.5:

| Entry delay | H=60 | H=240 | H=1440 |
| --- | --- | --- | --- |
| 1 min | +0.322 (t 4.58) | +0.284 (t 2.48) | +0.585 (t 2.04) |
| 5 min | +0.292 (t 4.22) | +0.246 (t 2.13) | +0.531 (t 1.84) |
| 15 min | +0.231 (t 3.17) | +0.203 (t 1.64) | +0.538 (t 1.86) |
| 60 min | +0.181 (t 2.94) | **−0.081 (t −0.40)** | +0.357 (t 1.20) |

The 1-hour effect **survives** delay but loses 44% of its size — a real effect
with a boundary-noise component on top, not one or the other. The 4-hour cell
**inverts** under a 60-minute delay, so it is not a robust effect at all.

> EXP-0001's version of this control anchored the exit at reopen+h, so delaying
> entry silently shortened the hold; at H=60 with a 60-min delay the trade had
> zero duration. EXP-0002 anchors exits at entry+H. This is why the two runs
> report different retention numbers, and EXP-0002's are the valid ones.

**Weeknight placebo — this is the finding that matters most.** The identical
pipeline on ordinary weeknight breaks at the same UTC clock (3,109 breaks,
median 16 min):

| k | Arm | n | H=60 | H=240 | H=1440 |
| --- | --- | --- | --- | --- | --- |
| 1.5 | weekend | 787 | +0.292 (t 4.22) | +0.246 | +0.531 |
| 1.5 | **weeknight** | 3,662 | **+0.181 (t 1.91)** | +0.227 | +0.179 |
| 2.0 | weekend | 534 | +0.369 (t 4.20) | +0.318 | +0.995 |
| 2.0 | **weeknight** | 1,977 | **+0.173 (t 1.15)** | +0.423 | +0.448 |

A weeknight break carries **~62% of the weekend effect** at k=1.5, and at
H=240 it is *larger*. So this is not a weekend-gap phenomenon. It is reversion
after a displacement measured across any thin-liquidity session boundary, and
the weekend is simply the largest instance. That reframes the mechanism away
from "weekend news gets overpriced" and toward "the reopen print is noisy."

**Era stability (k=1.5, H=60).** Not stable:

| | mean R | t | gross pips |
| --- | --- | --- | --- |
| 2011–14 | +0.150 | 1.36 | +1.82 |
| 2015–18 | +0.559 | 4.34 | +8.65 |
| 2019–22 | +0.126 | 1.06 | +0.56 |
| 2023–26 | +0.367 | 2.08 | +5.75 |

Roughly half the sample contributes almost nothing. A four-era split where two
eras are flat is not a foundation for deployment.

## E. Why it is not tradable

The reopen is the widest spread of the week, and we hold **mid-only** data — so
cost is estimated, and the conclusion is explicitly cost-model-dependent. Using
the median 1-minute high-low range at the reopen bar as a spread proxy:

| k=1.5, H=60 | gross pips | reopen range | net @1× | net @2× |
| --- | --- | --- | --- | --- |
| EURUSD | +2.31 | 4.60 | −2.29 | −6.89 |
| AUDUSD | +5.13 | 4.20 | +0.93 | −3.27 |
| GBPUSD | +4.32 | 5.97 | −1.66 | −7.63 |
| NZDUSD | +3.10 | 3.87 | −0.77 | −4.65 |
| USDJPY | +3.08 | 1.50 | +1.58 | +0.08 |
| NZDJPY | −2.63 | 4.10 | −6.73 | −10.83 |
| EURJPY | +6.45 | 3.65 | +2.80 | −0.85 |
| AUDJPY | +6.70 | 4.17 | +2.52 | −1.65 |
| GBPJPY | +10.36 | 8.75 | +1.61 | −7.14 |
| **pooled** | **+3.97** | — | 5/9 positive | 1/9 positive |

Pooled cost stress, round-trip charge against the pooled book:

| charge | 1 pip | 2 pips | 3 pips | 4 pips | 6 pips |
| --- | --- | --- | --- | --- | --- |
| k=1.5 | +2.97 (t 2.6) | +1.97 (t 1.7) | +0.97 (t 0.8) | −0.03 (t 0.0) | −2.03 |
| k=2.0 | +4.25 (t 2.9) | +3.25 (t 2.3) | +2.25 (t 1.6) | +1.25 (t 0.9) | −0.75 |

**Break-even round-trip cost is ~4 pips at k=1.5 and ~5 pips at k=2.0.** That
is inside the plausible range for a Sunday-reopen round trip on these pairs,
and well inside it for the JPY crosses where the gross is largest — GBPJPY
shows the biggest gross (+10.4 pips) and also the widest reopen range (8.75).
The gross is approximately the modeled cost, which per Rule 20 makes this a
cost-model-dependent conclusion, not a robust edge.

Note also that R and pips disagree in sign for NZDJPY (mean R +0.050, gross
−2.63 pips): the sigma normalisation weights small-gap weekends up, while pips
are dominated by the large ones. Both are reported; the deployable object is
pips.

**Clean-vs-padded archive split.** The canonical calendar fix does not induce
the effect — the six archives with zero Saturday bars carry it *more* strongly
than the three padded ones, which is the opposite of what a data artifact would
do:

| k=1.5, H=60 | mean R | t | n | gross pips |
| --- | --- | --- | --- | --- |
| 6 clean archives | +0.356 | 4.52 | 504 | +5.19 |
| 3 padded archives | +0.177 | 1.87 | 283 | +1.81 |

The tradability conclusion is unchanged: +5.19 pips gross against a ~4 pip
break-even is still inside the plausible reopen spread.

## F. What survives

1. **A real, well-measured statistical fact:** after a session break, a large
   displacement from the pre-break close partially reverts within about an
   hour, monotonically in the size of the displacement, on 9/9 FX pairs, at
   t≈4.2 with a decisive selection-aware null.
2. **It is not a weekend effect** — weeknight breaks carry most of it.
3. **It is not capturable at these sizes** with a market order across the
   reopen spread.

## G. Answering the original question

The AUDJPY claim **does not replicate as stated**. At the one-day horizon that
"reversion toward the gap" implies, AUDJPY is +0.69 sigma with t=1.35 — not
distinguishable from zero on 88 events, and the pooled nine-pair test at that
horizon fails its preregistered t≥2 bar. What is genuinely there on AUDJPY is a
one-hour effect (+0.344 sigma, +6.70 pips, t=2.55) that is real but is roughly
the size of the AUDJPY weekend reopen spread, and that is equally present after
ordinary weeknight breaks.

## H. If this were taken further

The only version worth testing is a **passive** one: the effect is the reopen
print being noisy, so paying the reopen spread to trade it is self-defeating.
A resting limit order placed *before* the close on Friday, at a level the
reopen would have to gap through, earns the spread instead of paying it. That
requires queue evidence proportional to the claim (Rule 4) and a fill model we
do not currently have data for — L1 quotes at the reopen. Without that data
this line is closed.

Do **not** pursue: deeper thresholds (k≥2.5 loses significance as n falls),
longer horizons (noise), or per-pair selection (that is fitting the 9/9 table).
