# EXP-0002 Results Discussion

- Hypothesis: `HYP-0002` — Anchor deviation predicts forward return with a REVERSION sign, strongest in illiquid blocks
- Status: completed
- Builder: Claude (Opus 5)
- Reviewer: Claude (Opus 5), self-review — no second model available this session
- Primary metric: per-signal mean pip of fading |dev_vwap_z|>=1.0 at H=30 pooled, session cluster-robust SE + session block-bootstrap CI, reported jointly with the Spearman rank IC
- Kill test: Rejected if ANY of: (1) spread not negative-reversion on both products; (2) |cluster t| < 2 or bootstrap CI spans zero on either; (3) asia not more reversionary than overlap on both; (4) the degenerate `open` anchor lands inside vwap's CI.

## Result versus hypothesis

**REJECTED.** Two of the four pre-declared arms fail, and a fifth control added
during the run (`past30`) fails harder than either.

| arm | 6E | 6B | verdict |
|---|---|---|---|
| 1. reversion sign | +0.1309 pip | +0.0476 pip | PASS (both positive = fade pays) |
| 2. \|t\|≥2 and CI excludes 0 | t +2.66, CI [+0.031,+0.222] | t **+0.72**, CI [−0.066,+0.165] | **FAIL on 6B** |
| 3. asia more reversionary than overlap | +0.288 vs −0.282 | +0.115 vs −0.300 | PASS (both) |
| 4. degenerate `open` outside vwap's CI | +0.0822, inside | +0.0747, inside | **FAIL on both** |
| 4b. no-anchor `past30` (added) | **+0.1971, t +3.92** | **+0.3836, t +5.96** | beats VWAP on both |

The headline is arm 4b. **A signal that uses no anchor at all — fade the trailing
30-minute return, z-scored by the identical causal same-slot construction — beats
every anchored variant on both products, by 1.5x on 6E and 8x on 6B.** The VWAP,
TWAP, session-open and prior-close anchors are all statistically
indistinguishable from each other and all worse than using no anchor. The partial
correlation confirms the same thing from the other direction: the raw rank IC of
`dev_vwap_z` (−0.0298 / −0.0257) roughly **halves** once `past_30` is partialled
out (−0.0146 / −0.0114), while `past_30`'s own IC (−0.0390 / −0.0365) is the
largest in the table.

So the sign and the shape the hypothesis predicted are both real, and the
attribution is wrong: this is short-horizon price reversal, not anchor
displacement. The anchor is a noisier proxy for the same thing.

## Gross, net, baseline, and null comparison

**Non-tradable by roughly an order of magnitude**, which is why no null was spent
(the real pass fails its primary metric on cost grounds — the "gate Null C on the
success metric" rule).

| | gross/bet | optimistic round trip | net/bet |
|---|---|---|---|
| 6E 2010-2015 (tick 1.0 pip) | +0.134 pip | 2.0 pip | −1.87 pip (−$23.32) |
| 6E 2016-2023 (tick 0.5 pip) | +0.129 pip | 1.0 pip | −0.87 pip (−$10.89) |
| 6B 2010-2015 | +0.148 pip | 2.0 pip | −1.85 pip (−$11.57) |
| 6B 2016-2023 | −0.015 pip | 2.0 pip | −2.01 pip (−$12.59) |

The round trip assumes a 1-tick-wide market and a fill at the touch on both
sides — the most optimistic model available. Gross is 8x below it on the best
cell and negative on the worst.

Note the rule-19 point this makes concrete: 6E's tick halved in 2016, so the
*same* gross edge went from 15x below cost to 8x below cost with no change in
predictability. Quoting one cost number across the sample would have been wrong
by 2x on one of the two products.

## Regimes, sensitivity, and alternative explanations

- **The block shape is the most interesting surviving result, and it dissociates
  the two signals.** Anchor deviation reverts in `asia` (+0.288 / +0.115) and
  `ny_pm`, and **continues** in the London/NY `overlap` (−0.282 / −0.300, both
  products, and −0.357 t −2.20 for TWAP on 6B). The no-anchor `past30` arm has the
  *opposite* profile: its reversion is *strongest* in `overlap` (+0.439) and
  `ny_pm` (+0.700, t +5.04) on 6B. The two features are therefore not measuring
  the same thing at every hour even though `past30` dominates pooled — anchor
  displacement and short-horizon reversal have opposite time-of-day profiles.
- **Era stability is weak.** 6E: 12/14 years positive but only one year reaches
  |t|>2. 6B: 9/14 positive, sign flips across a long 2015-2020 run. This is a
  small effect measured over many observations, not a stable one.
- **Shared-decision-bar artifact, sized on this data.** Entering at `close(m)`
  instead of `open(m+1)` inflates the result to +0.404 (6E) / +0.379 (6B); the
  honest estimate retains only **32.4% / 12.5%**. LEARNINGS 2026-07-31d measured
  31-56% retained at a 5-minute horizon on NQ/ES/GC; this is a *worse* case at a
  30-minute horizon on a new asset class. Any FX-futures reversal quoted without
  this control is inflated by 3-8x.
- **The estimand contrast is dramatic and is the run's most transferable
  by-product.** Session-averaging instead of taking the per-signal mean turns
  6B's null (+0.048, t +0.72) into **+1.030, t +15.06**, and 6E's +0.131/t+2.66
  into **+0.777, t +15.92**. `corr(session mean, session count)` is **−0.461 /
  −0.474**. Sessions with FEW signals have HIGH mean P&L — the opposite sign of
  correlation from the FX-spot and NQ/ES cases, and it still manufactures a
  t≈16 result out of nothing.

**Alternative explanation considered.** Could arm 4's failure be a power problem
— `open` merely too noisy to separate from `vwap`? No: the CIs are narrow
(±0.10 pip) and `open`'s point estimate is 63% / 157% of `vwap`'s while `past30`'s
is 151% / 806%. The ordering is clear and consistent across both products; there
is nothing for more data to resolve.

## Artifact and implementation risks

- Entry is `open(m+1)` after a `close(m)` decision (rules 1, 2). No barriers, no
  stops, no targets — nothing here can be manufactured by exit geometry (rule 15).
- The signal threshold is a fixed `|dev_z| >= 1.0` on a **causally** standardised
  feature; no full-sample quantile decides what was tradable (rule 8). Quintiles
  appear only as a descriptive profile.
- The same-slot scale uses `lookback=90, min_periods=45`, chosen from measured 6B
  Asia coverage rather than convention — see `reports/DATA_QUALITY.txt`. The
  default (60, 2/3) would have deleted 35% of 6B's 18:00 ET decisions while
  deleting 1% of its London decisions.

## Builder interpretation

The VWAP framing is withdrawn. There is a real, cross-product, structurally-shaped
short-horizon reversal on FX futures, and displacement from a session VWAP is a
*worse* way to measure it than the trailing return that costs nothing to compute.
Neither version is remotely tradable at 1-contract granularity.

The shape result (reversion in the illiquid blocks, continuation in the overlap)
is worth keeping as a descriptive fact about the FX futures tape and is consistent
with the transitory-inventory account — it is simply not a VWAP fact.

## Independent review

- Review status: self-reviewed; no second model this session.
- Objections: (a) arm 3's "shape" comparison is not itself volatility-matched, and
  LEARNINGS 2026-07-31c showed a time-of-day-matched split can still inherit a
  volatility gradient. Here the split *is* time-of-day, so the objection is that
  the asia/overlap contrast may be a volatility contrast wearing a liquidity
  label. Since the hypothesis is rejected on other arms this is not load-bearing,
  but a volatility-stratified version is logged in the backlog before the shape
  result is used for anything. (b) `past30` was added mid-run, after seeing
  Control C. It is a degenerate control rather than a candidate feature, and it
  made the verdict *more* negative, so it cannot be a search artifact — but it was
  not preregistered and is labelled as such.
- Verdict: **rejected. Sign and shape confirmed, attribution and tradability
  refuted.**

## Promotion decision

- `reports/FINDINGS.md`: promoted as findings B, C, D.
- `MEMORY.md`: promoted (NO-GO verdict).
- Shared `LEARNINGS.md`: promoted — the estimand-contrast reproduction and the
  degenerate no-anchor control are both cross-project and both changed a verdict.
