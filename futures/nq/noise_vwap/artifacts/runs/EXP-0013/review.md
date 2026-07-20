# EXP-0013 Results Discussion

- Hypothesis: `HYP-0006` — A fixed early-flat cutoff before the close improves NQ risk-adjusted returns
- Status: completed — hypothesis rejected
- Builder: Claude (Opus 4.8)
- Reviewer: Claude (Opus 4.8)
- Primary metric: max-cell zero-trade-day daily net-ATR-R Sharpe uplift over the cutoff-0 baseline across the cutoff family
- Kill test: Reject if NQ max-cell Sharpe uplift < +0.10, or (if the real gate passes) Null C family-max p > 0.05; weaken if Sharpe gain only cuts net R or sign does not transfer to ES

## Result versus hypothesis

Rejected. NQ's best cell just clears the Sharpe threshold but fails the net-R
condition, and the sign is opposite on ES, so no Null C was run.

NQ (cutoff minutes before 16:00 ET; baseline = 0):

| cutoff | trades | net R | Sharpe | ΔSharpe | maxDD (R) | p90R | 2023+ Sh |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 4209 | +91.2 | 1.29 | — | 4.7 | +0.35 | 1.10 |
| 15 | 4209 | +88.6 | 1.29 | −0.001 | 4.2 | +0.33 | 1.33 |
| 30 | 3956 | +89.1 | 1.34 | +0.057 | 4.9 | +0.35 | 1.52 |
| 45 | 3956 | +90.4 | 1.39 | **+0.101** | 5.4 | +0.35 | 1.54 |
| 60 | 3717 | +74.0 | 1.18 | −0.106 | 5.4 | +0.34 | 1.24 |

ES: every cutoff is worse — net R falls to +43-44 (from +51.5) and Sharpe drops
(best cell −0.030). The sign does not transfer.

The NQ best cell (cutoff 45) clears +0.10 Sharpe but its net R is −0.8 below
baseline, so the success gate (Sharpe uplift AND net R >= baseline) fails and no
Null C was run per the standing rule.

## Gross, net, baseline, and null comparison

This is not the looser-stop machinery artifact seen in EXP-0010/0012: trade count
barely changes (4209→3956) and the top-decile winner-R is preserved (p90R 0.35 =
baseline), so the Sharpe gain is NOT from truncating the winner tail. It comes from
removing late-session daily-return variance. But net R does not improve (flat to
−0.8 on NQ, clearly negative on ES), so there is no gross edge being captured —
only variance reshaped, and only on NQ.

## Regimes, sensitivity, and alternative explanations

The striking signal is the recent 2023+ Sharpe: NQ jumps from 1.10 to ~1.52-1.54
at cutoffs 30-45, i.e. late-session (15:15-16:00 ET) reversals have hurt NQ more in
recent years. This is a consumed-data, recent-regime observation and belongs in
forward-shadow monitoring, not a historical optimization (same discipline as the
EXP-0008 short-lookback recent-regime note). Contrary to the idea's premise, daily
max drawdown does NOT improve on NQ (4.7→5.4 at cutoff 45); the improvement is in
daily-return dispersion, not tail depth.

## Artifact and implementation risks

The cutoff is implemented default-off in the audited core/engine2.py
(`flat_before_close`); flat_before_close=0 reproduces the baseline bit-for-bit
(engine2-vs-core.engine parity re-verified) and a behaviour check confirms the
forced flat and no-new-entry cutoff move the last exit from mfo 389 to 359 (30m)
and 329 (60m). No Null C was run because the real gate failed; the recent-era
observation is descriptive only.

## Builder interpretation

The paper's early-flat cutoff is the most "alive" of the tested exit ideas on NQ
(Sharpe +0.101, and not a tail-truncation artifact), but it does not clear the
bar: net R does not improve, drawdown does not improve, and the sign is opposite on
ES. Retain ride-to-close. The recent-era late-session-reversal effect on NQ is
worth watching in a forward shadow, not banking historically. Useful NO-GO that
closes IDEA-0002.

## Independent review

- Reviewer: Claude (Opus 4.8)
- Review date: 2026-07-19
- Review status: completed
- Verdict: REJECT confirmed — concur with the builder.
- Basis: Re-derived from real_nq/es.txt. NQ cutoff-45 Sharpe +0.101 is real but
  paired with flat/negative net R, worse maxDD, and an opposite ES sign; the gate
  and the ES-transfer weakener both trip. Correctly no Null C per the standing
  rule. The winner-tail retention (p90R unchanged) rules out the truncation
  failure mode and correctly identifies the effect as variance reshaping.
- Objections: none blocking.
  1. The recent-2023+ NQ improvement (1.10→1.54) is the one genuinely interesting
     residue; keep it as a forward-shadow watch item, do not re-optimize the cutoff
     on consumed history.
  2. If ever revisited, target daily/close-proximity DRAWDOWN explicitly rather
     than Sharpe, since drawdown did not improve here.

## Follow-up Null C (2026-07-20)

At the user's request — motivated by a structural late-session-noise thesis (3:45 ET
MOC imbalance reveal, passive-fund close rebalancing, and 0DTE gamma hedging all
concentrating mechanical, non-fundamental flow into the final 15-30 min) — the
family-max Null C was run despite the original net-R gate failing. Under a
variance-avoidance thesis the correct control is net-R PRESERVATION (satisfied:
NQ −0.8R out of 91), not net-R increase, and the drift-preserving return-shuffle
null is the right discriminator: it keeps session drift but shuffles intraday
timing so no minute is special. 30 draws, family-max ΔSharpe over the {15,30,45,60}
cutoff grid. Evidence: `nullc_nq.txt`, `nullc_es.txt`.

| market | real max ΔSharpe | null max mean (sd) | p | verdict |
| --- | ---: | ---: | ---: | --- |
| NQ | +0.101 (cutoff 45) | −0.048 (0.058) | 0.0323 | PASS (0/30 beat real) |
| ES | −0.030 (all cutoffs hurt) | +0.008 (0.072) | 0.7419 | REJECT (noise beats real) |

Interpretation:

1. **NQ is NOT the looser-stop machinery artifact.** Unlike EXP-0010/0012, whose null
   reproduced the Sharpe lift POSITIVELY (+0.08 to +0.25 on noise), here the null
   centers NEGATIVE (−0.048): on drift-preserved, timing-shuffled NQ tape the best of
   four cutoffs typically HURTS Sharpe. The real +0.101 exceeds every one of 30 null
   draws. So the NQ early-flat is a genuine late-session-specific timing feature, not a
   hold-less-time variance amplifier. This is the discriminator that separates it from
   the other rejected exit tweaks.
2. **The stated pan-index structural mechanism is falsified by ES.** MOC imbalances,
   passive rebalancing, and 0DTE gamma all bear at least as heavily on the S&P as on
   the Nasdaq-100 (SPX 0DTE is the largest 0DTE market; S&P passive AUM exceeds NDX).
   A pan-index cause therefore predicts ES benefits as much or more. Instead ES INVERTS
   — early-flat is worse than baseline and worse than its own null (noise beats the real
   tape, p=0.74). What survives on NQ is NQ-tape-specific, not the general structural
   close phenomenon.
3. **The NQ pass buys daily-dispersion Sharpe only.** Net R is preserved not improved
   (−0.8R), maxDD is WORSE (4.7→5.4R), and the effect concentrates in 2023+ (23+Sh
   1.10→1.54) on consumed history. 0DTE's post-2022 growth is a plausible-but-
   unconfirmable story for the recent-era loading.

Revised verdict: the original REJECT for production adoption STANDS (no net-R gain,
worse drawdown, mechanism falsified cross-market). What CHANGES is that the NQ effect
is no longer dismissible as machinery — it is a qualified, NQ-specific, forward-shadow
candidate that cleared the drift-preserving null on consumed data. Watch in shadow; do
not bank historically; do not attribute it to the MOC/rebalancing/0DTE mechanism, which
ES contradicts.

## Promotion decision

- `reports/FINDINGS.md`: not updated (still NO-GO for adoption; forward-shadow watch only)
- `MEMORY.md`: updated with the follow-up Null C result and revised forward-watch note
- Shared `LEARNINGS.md`: eligible — single-market Null C pass does not validate a
  mechanism that predicts cross-market transfer; the sibling market is the mechanism test
