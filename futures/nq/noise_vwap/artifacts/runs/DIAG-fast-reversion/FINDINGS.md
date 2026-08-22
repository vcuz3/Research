# DIAG — fast-alpha reversion mechanic (NQ, 2026-08-16)

Diagnostic (not a confirmatory experiment). Answers three user questions on the
correct footing (EXP-0047 Addendum 2): the exit-delay uplift is **+117% mean
(post-stop reversion) / −17% variance**; the paper's *sign-timing* cue is the
NO-GO (a blind delay harvests the same reversion). Script:
`scripts/diag_fast_reversion.py`. TRAIN 2011-2020 / TEST 2020-2026.

## Q1 — why delaying helps at EXIT but not ENTRY (it's a sign flip, not clock-vs-continuous)

Entry trailing-return IC (side-signed log return into the decision vs per-trade net R):

| x_min | Spearman IC | p | mean-R top−bottom quintile |
|---|---|---|---|
| 1 | −0.041 | .008 | −0.001 |
| 5 | −0.051 | .001 | +0.002 |
| 10 | −0.081 | .000 | +0.006 |
| 20 | −0.118 | .000 | +0.028 |
| 30 | −0.121 | .000 | +0.028 |

Rank IC and mean-spread **disagree in sign** — the LEARNINGS #1/#4 split. Rank-wise
the bulk of entries mildly *revert* (deeper extension → lower median outcome), but
the **mean** (what equal-risk sizing consumes) *rises* with extension: the top
extension quintile earns +0.028 R more than the bottom at x=30. NQ intraday
momentum lives in the **tails**, so delaying/fading the entry trims the right tail
that IS the edge → entry-delay is harmful.

Exit mirror — mean side-signed forward move AFTER a stop (n_stop=3414):

| x_min | mean fwd R | % positive |
|---|---|---|
| 1 | +0.0005 | 0.496 |
| 5 | +0.0022 | 0.514 |
| 30 | +0.0050 | 0.530 |

A stop-out is an adverse spike, and adverse spikes **partially retrace** — a small,
roughly uniform post-stop reversion (barely >50%). Waiting recovers a sliver = the
+117%-mean effect.

**Answer:** entry and exit sit at *opposite* points of the local move. Entry is a
fresh favorable breakout whose payoff is continuation (momentum in the tails); the
stop fires on an adverse spike that mean-reverts. The **sign of the local edge
differs**, which is why a delay helps at exit and hurts at entry. The
clock-vs-continuous distinction is secondary (a continuous/threshold entry also
enters on extension and would face the same momentum condition).

## Q2 — is the post-stop capture consistent through the day?  No.

Fixed 4-bar delay, per-trade capture (overlay − baseline net R), by decision slot:
total **+7.32 R over both eras, mean +0.0018 R/trade** (EXP-0047's +0.0041 was
TEST-only — the effect is recent-weighted).

- 10 of 12 slots positive, but **afternoon-weighted** (slots 6–11 ≈ +0.004..+0.006 R);
  **negative at lunch** (slot 5, 12:00 ET, −0.0029) and **worst in the final half-hour**
  (slot 12, 15:30, −0.0071) — no time to revert before the EOD flat.
- In **every** slot the delay raises win rate (+0.06..+0.14) while **deepening the
  1st-percentile left tail** (e.g. slot 11 p01 −0.332 → −0.496). The drawdown cost
  is pervasive, not localized — exactly the review's warning.

## Q3 — noise-reduction stop (slower cadence / fixed hold), drawdown-aware.  No TRAIN-stable survivor.

Honor the stop only on a slower cadence (`exit_check=N`) or after a fixed hold
(grace period, then "stay if above stop"). Scored with maxDD & Calmar=sumR/maxDD.

**Clock entry:** holds look great **on TEST** (hold4 dSharpe +0.204, hold6 +0.249,
hold6 even maxDD −0.51 / Calmar +2.80, recent Sharpe 1.095→1.270) — but they are
**flat-to-negative on TRAIN** (hold6 −0.063 Sharpe, maxDD +0.46). The benefit is
**recent-era-only** and would never be selected on TRAIN; the lone maxDD improvement
is non-monotone in hold length (hold4 TEST maxDD is *worse*, +1.03) = era-luck, not
structure.

**Continuous (threshold) entry:** slower cadence hugely helps **TRAIN** (cad30
+0.569 Sharpe, maxDD 22.3→9.1 — it cuts the over-firing re-buy churn) but **flips to
hurting on TEST** (cad30 −0.147, maxDD +4.27), and the whole threshold book sits far
below the clock book anyway (Sharpe ~0.8 vs 1.32). Not a path.

**Verdict:** the noise-reduction stop is the same small, **recent-era, drawdown-gated**
post-stop-reversion effect EXP-0047 flagged — not a TRAIN/TEST-stable, deployable
rule. Under honest TRAIN-selection it is a **NO-GO** (nothing helps on TRAIN). Its
TEST appeal is a watch-item for forward/shadow data (could be a real recent regime
shift toward more post-stop mean-reversion, or era-luck — undecidable on consumed
history). No null spent (fails the TRAIN-selectability precondition).
