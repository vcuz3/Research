# EXP-0049 review — HYP-0037 smarter depth entry gate (three arms)

- Builder: Claude (Opus 4.8)
- Date: 2026-08-16
- Hypothesis: `experiments/hypotheses/HYP-0037.md`
- Verdict: **NO-GO on all three arms, both markets.** None clears the NQ TEST
  primary gate, so no arm reaches the matched-count random-drop null or Null C
  (gate rule).

## Baselines (deployed clock book, lb90, next_open, require_vwap, every_bar both-stop)

| inst | TRAIN Sharpe (n) | TEST Sharpe (n) |
| --- | --- | --- |
| NQ | 1.268 (2477) | 1.322 (1699) — netR 35.78 |
| ES | 0.481 (2627) | 1.070 (1699) — netR 29.19 |

TRAIN = first 60% of common sessions (~2011–2020), TEST = last 40% (~2020–2026).
Consumed research data; TEST is a temporal-validation split, not a sealed holdout.

## Arm A — side-asymmetric depth (k_long vs k_short on ext_atr, clock gate)

User thesis: NQ up-drift lets long breakouts follow through on a shallower break,
while counter-drift short "panic" breaks need a deeper break → `k_long < k_short`.

TRAIN grids **mildly support the asymmetry DIRECTION** (best cell wants the short
threshold deeper than the long): NQ argmax k_long=0.10 / k_short=0.15
(TRAIN dSharpe +0.217, retain 0.51); ES argmax k_long=0.05 / k_short=0.20
(TRAIN dSharpe +0.414, retain 0.55). But it does not transfer:

| inst | selected (kl,ks) | TEST dSharpe | TEST dNetR | real_gate |
| --- | --- | --- | --- | --- |
| NQ | (0.10, 0.15) | **−0.011** | −4.03 | FAIL |
| ES | (0.05, 0.20) | **−0.268** | −9.93 | FAIL |

The asymmetry is an in-sample TRAIN artifact; on TEST the deeper-short cut only
removes exposure. Consistent with EXP-0048 (symmetric depth) and every prior
per-signal entry gate on this book.

## Arm B — always-fire deeper threshold (first-crossing entry), era-resolved

Scored against the **deployed clock baseline** (correcting the EXP-0048
reconciliation error — NOT the over-firing buf=0 threshold arm). Threshold mode
has no cooldown and over-fires (~4× trades at buf=0), so Sharpe is
exposure/churn-confounded; the clean reads are per-trade net points and the
d_sharpe_vs_clock column.

- **NQ & ES: every buffer LOSES to the clock book on TEST at every depth.**
  d_sharpe_vs_clock is negative across the whole grid on both TRAIN and TEST.
  Deeper buffers do raise per-trade net points monotonically (e.g. NQ TEST
  buf=0.30 netPt/t up sharply) but only by shedding exposure; the risk-adjusted
  number never reaches the clock book.
- The only cell that "wins" is a cherry-picked NQ RECENT-20% slice
  (buf≈0.15, +0.295, n=775) — an unstable searched last-20% window, and the same
  buffer is negative-vs-clock over full TEST. ES RECENT-20% is negative at every
  buffer. Not a claim.

Verdict: the clock decision gate already captures what the deeper always-fire
threshold does, without the ~4× churn. Descriptive; no null spent.

## Arm C — band-relative per-slot depth (ext_sigma gate, clock gate)

`ext_sigma = ext_atr · ATR / (0.5·(upper−lower))` — break depth in band-halfwidth
units (the per-slot scale the band is built from), the scale-free unit
(LEARNINGS #1). The diagnostic **CONFIRMS the confound the user suspected**: a
fixed `ext_atr` cut IS a mild time-of-day selector, and the band-relative cut is
2–3× flatter across slots at matched overall rate:

| inst | per-slot fire-rate CV, ext_atr≥0.10 | CV, ext_sigma (matched) |
| --- | --- | --- |
| NQ | 0.088 | **0.036** |
| ES | 0.115 | **0.050** |

But **correcting the confound does not change the deployment verdict.** TRAIN
selects k_sigma*=0.20 (retain ~0.55–0.56); TEST:

| inst | TEST dSharpe | TEST dNetR | real_gate |
| --- | --- | --- | --- |
| NQ | **−0.007** | −3.57 | FAIL |
| ES | **−0.405** | −12.24 | FAIL |

So the ATR gate's time-of-day-selector character was real but was NOT what made
the depth gate fail — the depth mechanism itself does not monetize as a
risk-adjusted uplift in either unit. This is the cleaner statement of the
EXP-0048 NO-GO: a depth gate is a turnover/capacity lever whether measured in
session-ATR units or band units.

## Overall

All three refinements of the depth-entry gate reproduce the EXP-0048 signature:
per-trade quality rises with depth (real, era-stable), the TRAIN Sharpe uplift is
in-sample only, and TEST fails the +0.10 gate with netR falling. Two positive
research residuals worth keeping: (A) the long/short asymmetry the user proposed
is directionally present on TRAIN in both markets (short wants a deeper break),
and (C) the band-relative normalization genuinely de-clocks the depth cut. Neither
rescues deployment. The confirmation-depth entry family is now closed
(EXP-0048 + EXP-0049).

## Reviewer

- Reviewer: unassigned
- Decision: NO-GO (turnover lever, no out-of-era transfer, on all three arms)
- Objections: pending
