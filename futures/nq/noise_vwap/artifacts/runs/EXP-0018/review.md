# EXP-0018 Results Discussion

- Hypothesis: `HYP-0010` — ES cross-market breakout confirmation gates NQ noise-VWAP entries
- Status: completed
- Builder: Claude (Opus 4.8)
- Reviewer: unassigned
- Primary metric: net daily Sharpe uplift of `agree` over the common-set baseline vs a re-pairing null
- Kill test: Reject unless `agree` lifts net daily Sharpe by >= +0.05; if it clears, the uplift must beat the re-pairing null at z>=2 and frac(null>=real)<0.05.
- Evidence: `es_confirm.txt` (this dir). Reproduce: `python -m futures.nq.noise_vwap.scripts.hyp_0010_es_confirm NQ 90 0.50 200`.

## Result versus hypothesis

REJECT the user's thesis as deployable alpha. The PRIMARY `agree` variant (take an NQ
signal only when ES has simultaneously broken out of its own noise area in the same
direction) does NOT improve net daily Sharpe: 1.074 vs the common-set baseline 1.102,
uplift **−0.029**, below the +0.05 gate. Because the primary metric fails, the thesis is
rejected without needing the confirmatory null on `agree` (gate-nullc-on-success-metric).

However the mechanism the user proposed has **real per-trade support** — this is the
honest positive finding, and it is the opposite of what the sibling GC study found:

- `agree` **raises** gross/trade (+5.302 vs +4.945 pt), net/trade (+4.827 vs +4.470),
  and hit-rate (0.407 vs 0.380) while dropping ~30% of trades. So the kept trades are
  genuinely BETTER per trade — ES confirmation carries real per-trade information. On
  gold (GC EXP-0007) the identical filter HALVED gross/trade, i.e. selected the WORSE
  trades (a rarity filter). NQ↔ES's tighter coupling shows up exactly where the user
  predicted: at the per-trade quality level.
- It does not monetize as risk-adjusted alpha because it is a pure turnover/capacity
  trade: total net R falls ~25% (baseline 4.470×2923 ≈ 13066 pt → agree 4.827×2035 ≈
  9823 pt), daily P&L gets lumpier (day-net t 2.68 vs 3.15, day$ 125.1 vs 127.5), so
  daily Sharpe is flat-to-down. Same money is not made on fewer trades; less is.

## Gross, net, baseline, and null comparison

Common NQ∩ES date set = 3628 sessions. ES decision-bar state marginals: breakout
long 0.141 / short 0.119 / flat 0.741; VWAP side above 0.564 / below 0.436.

| variant | Sharpe | uplift | trades | kept% | gross/kept | net/trade | hit | L(net) | S(net) |
|---|---|---|---|---|---|---|---|---|---|
| baseline(common) | 1.102 | — | 2923 | 1.00 | +4.945 | +4.470 | 0.380 | +4.210 | +4.740 |
| **agree** (PRIMARY) | 1.074 | −0.029 | 2035 | 0.70 | +5.302 | +4.827 | 0.407 | +6.682 | +2.985 |
| gate | 1.080 | −0.024 | 2037 | 0.70 | +5.325 | +4.850 | 0.407 | +6.675 | +3.037 |
| vwap | 1.026 | −0.077 | 2843 | 0.97 | +4.702 | +4.227 | 0.380 | +4.466 | +3.979 |
| es_dir | 0.696 | −0.408 | 3544 | 1.21 | +2.662 | +2.187 | 0.433 | +3.143 | +1.138 |
| es_opp | −0.720 | −1.824 | 6540 | 2.24 | −0.512 | −0.987 | 0.460 | −0.745 | −1.196 |
| disagree | 1.209 | +0.105 | 1474 | 0.50 | +4.862 | +4.387 | 0.362 | +1.664 | +7.472 |

Reading the menu:

- **gate ≈ agree.** When ES breaks out at all it is almost always the same direction as
  the NQ signal (opposite-direction ES breakouts during an NQ signal are rare), so
  "ES in any breakout" and "ES agrees" pick nearly the same trades. This directly
  confirms the coupling premise.
- **vwap (the user's "don't go long if ES is under its VWAP") is inert-to-harmful:**
  barely filters (97% kept), Sharpe falls, gross/kept FELL below baseline. The *full
  noise-area breakout* on ES carries the per-trade information; ES's mere side of its
  own VWAP does not. The noise-area construct is load-bearing, not just VWAP sign.
- **es_dir (does ES LEAD NQ?) is much worse (0.70).** Entering NQ in ES's breakout
  direction is inferior to NQ's own signal — ES does not lead. **es_opp is genuinely
  negative (−0.72, gross −0.512, not merely cost)** so es_dir has real directional
  content and there is no Rule-16 mirror-trap rescue (fading ES is simply bad).
- **agree is strongly asymmetric:** it concentrates NQ **longs** (L net +6.68 vs +4.21)
  but HURTS **shorts** (S +2.99 vs +4.74). ES confirmation helps NQ upside breaks and
  hurts NQ downside breaks — a directional artifact, not a symmetric quality gate.

Re-pairing null (Rule 18) on the only Sharpe-beater, `disagree` (secondary/post-hoc,
family of 6, consumed history), 200 year-stratified draws, seeds 10000..10199:

- real uplift +0.1051; null uplift mean/sd **+0.0001 / 0.0977**; z=+1.08;
  frac(null>=real)=0.140. VERDICT: REJECT (z<2, frac>0.05).
- The null **CENTER at ~0** rules OUT the pure rarity-filter explanation (dropping a
  random 50% of trades via unrelated ES days does NOT reproduce the uplift on average).
  But the real uplift sits well inside the null's noise band (14% of null draws beat it),
  so it is not distinguishable from noise either — underpowered, and WEAKER than GC's
  already-marginal disagree survivor (GC z=+1.53). gross/kept also FELL (+4.86 vs +4.95)
  and the lift is almost entirely a huge short-side skew (S +7.47 on 691 trades). This is
  a consumed-history post-hoc screen, at most a forward-shadow curiosity, not an edge.

## Regimes, sensitivity, and alternative explanations

- Alternative explanation for the `agree` per-trade lift: it is not "ES predicts NQ" so
  much as "requiring two independent same-direction breakouts is a higher evidential bar,
  which mechanically raises hit-rate and per-trade payoff while trading less." That is
  consistent with the total-net-R drop and the flat Sharpe: better selection, less
  exposure, no risk-adjusted gain — a capacity/turnover lever.
- The short-side degradation under `agree` argues against a clean symmetric mechanism;
  a real shared-information confirmer should help both sides. It helps longs only.
- No cost-model dependence drives the verdict: agree already fails on Sharpe at gross
  logic (net/trade rises but total falls); the conclusion is not a cost artifact.

## Artifact and implementation risks

- Fills honest: baseline and all variants use the faithful next-open engine; the overlay
  only zeroes/redirects `want` at decision bars, never changes fill timing (rule 1/2).
  Parity guard: `cond_mode=None` reproduces the frozen faithful baseline exactly
  (2923 trades / 14454.25 gross), asserted at the top of every run.
- ES state is fully causal: built from ES's own bars, ES's own cumulative RTH VWAP, and
  ES's own strictly-prior 90-session noise bands (same audited `core.data` code as NQ),
  read at the same decision tod as the NQ signal — contemporaneous, no lookahead.
- Consumed history: 3628 sessions already inspected. Only future shadow is a clean
  holdout; nothing here is deployable evidence.

## Builder interpretation

The user's core intuition is partially correct and worth stating precisely: on the
tightly-coupled NQ↔ES pair, requiring simultaneous same-direction ES confirmation DOES
retain higher-quality NQ breaks (higher gross/trade, net/trade, and hit-rate) — the
"an NQ break with no ES break is noise" idea has genuine per-trade support, unlike gold
where the same filter selected worse trades. But it produces NO deployable alpha: it is
a selectivity/turnover lever that gives up ~25% of total net R and leaves daily Sharpe
flat-to-down. The softer VWAP-side gate is inert (the noise-area breakout, not VWAP sign,
carries the info). ES does not lead NQ (es_dir worse, es_opp genuinely negative). The
lone Sharpe-beater, disagree, fails its re-pairing null and is weaker than GC's already-
marginal version. Retain the unconditioned baseline. If anything is carried forward it is
a default-off capacity note (agree/gate as a "trade less, per-trade-better" lever for a
capacity-constrained or higher-cost deployment), never as alpha.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending (builder verdict: REJECT as deployable alpha; documented per-trade
  quality concentration as a turnover/capacity lever only)

## Promotion decision

- `reports/FINDINGS.md`: not promoted (no edge)
- `MEMORY.md`: updated — HYP-0010 rejected; cross-market confirm is a capacity lever
- Shared `LEARNINGS.md`: eligible — refines the 2026-07-19 GC cross-market conditioning
  learning with the NQ contrast (tight coupling → per-trade info but still no alpha)
