# Idea Backlog

Uncommitted brainstorming belongs here. An idea is not a finding or approved
experiment. Use `python tools/research_admin.py new-idea` to add entries.

## Ideas

### Done (see reports/FINDINGS.md)

- [x] **Dollar-decomposed residual momentum** — split each intraday move into a
  dollar-explained leg and an idiosyncratic residual and ask which continues.
  REJECTED (EXP-0001, HYP-0001, finding A). Produced the project's most useful
  by-products: the cross-asset reversion ordering, and the rank-versus-mean split
  (finding B).
- [x] **Cross-asset lead-lag** — does the dollar lead gold/equities at 5 minutes?
  REJECTED by the symmetry control (EXP-0002, HYP-0002, finding C). The "lead" is
  bidirectional and *larger* in the direction the mechanism does not predict.
- [x] **Factor coherence as a momentum regime** — REJECTED on both preregistered
  markets (EXP-0003, HYP-0003, finding D). Gold survived as a screen; EXP-0005 showed
  it was the volatility confound (finding E).
- [x] **Overnight dollar impulse** — REJECTED, wrong sign, all three kill tests
  (EXP-0004, HYP-0004, finding F).

### Next dimensions (proposed, unstarted)

1. **Finding B applied backwards — DOWNGRADED after checking, 2026-07-31.** The original
   version of this item claimed `vei_exploration` EXP-0011/0012/0015 were decided on rank
   ICs that may not track expectancy. **That was wrong and is withdrawn**: those runs
   already report magnitude-based losses alongside their ICs (EXP-0011 normalised MAE and
   QLIKE, EXP-0012 log-MSE skill +73.6%/+74.2% and MAE 9.01→4.78 bp, EXP-0015 log-MSE
   skill over persistence). Finding B's trap is specific to **signed, tail-skewed return**
   targets; a volatility target is positive-valued and its magnitude metrics were already
   present. What survives of the item is narrower: finding B is a **forward-looking
   discipline for new return/direction work**, not a re-audit of the volatility
   programme. The one place it may still bite retroactively is any per-trade quality
   claim scored by rank IC — and `vei_exploration` EXP-0013 already caught that itself.
2. **Coherence at a DAILY cadence.** The 60-minute intraday coherence is a noisy
   statistic whose noise is itself volatility-dependent, which is exactly how it became
   a volatility proxy (finding E). A session-level label estimated from the whole prior
   session would be far better conditioned, and a one-label-per-day regime fits gating a
   book better than an intraday tilt — the same argument `vei_exploration` backlog item 4
   makes for a daily VEI. Cheap on the existing panel. **Match on volatility from the
   start**, not as a follow-up.
3. **The dollar's own intraday reversion.** EXP-0001/0002 measured IC(past_dxy_30,
   fwd_dxy_30) = −0.046 raw, −0.031 endpoint-corrected — a *larger* reversion than gold
   or the indices show, and the largest raw number the project produced. It was only ever
   measured as a control for an artifact. The prior should be that the deepest macro
   market on earth is not exploitable at 30 minutes, but that prior has not actually been
   tested against FX futures costs. Note finding B applies: measure the mean, not only
   the rank, before concluding anything.
4. **Gold's 30-minute rank reversion, in a form that is not a mean bet.** Finding A
   established it (−0.036, 88% surviving the endpoint control, present in both eras) and
   simultaneously established that it carries **no mean expectancy** (−0.15 ticks). Do
   NOT open it as a directional entry signal. The only live question is whether being
   right about the *median* is worth something where the tails are truncated anyway — an
   exit rule or a passive-fill improvement on an existing gold book.
5. **A gold-versus-dollar SPREAD book rather than a directional one.** Every test here
   asked whether the dollar predicts an instrument's own return. With β = −0.90 and a
   contemporaneous correlation of −0.40 the natural object is the hedged spread, whose
   own reversion would be a relative-value claim. Honest prior from finding A: the
   residual was a *worse* predictor than the raw move, so the spread's reversion is
   likely weaker, not stronger.
6. **Event-conditioned cross-asset transmission — DATA-BLOCKED.** All four hypotheses
   tested the *unconditional* tape. The one place a cross-asset lead is mechanically
   plausible is the seconds-to-minutes after a scheduled macro release, when FX is the
   deepest place to price a surprise. Same channel `vei_exploration` backlog item 13
   identifies as its highest-value untouched direction, approached from the cross-asset
   side. Needs an economic-calendar source this workspace does not have; record the
   blocking item as data acquisition, and do not simulate it without real release times.

## Standing cautions

- **Read the mean, not only the rank.** Finding B is this project's most transferable
  result and the two statistics disagreed on every market tested. Report both and say
  which one the decision consumes.
- **Run the degenerate or reversed control.** It decided three of the five runs here: the
  factor leg (EXP-0001), the reverse direction (EXP-0002), the volatility-matched split
  (EXP-0003/0005). Inherited from `vei_exploration` findings H and P and confirmed again.
- **Matching on time of day is not enough.** Match the split on volatility too (finding
  E). EXP-0003 matched slot composition exactly and still measured a volatility gradient
  of 1.46x between its cells.
- **The shared endpoint is not a detail.** `past` and `fwd` share the close at the
  decision bar, so any pricing error there manufactures reversion — 12-33% of it at 30
  minutes, 31-56% at 5 minutes (finding G). Never report a reversal without the lagged
  control.
- **A decomposition needs a large factor R².** Below roughly 20% the residual is not a
  different variable from the raw move (finding F). Check the factor's share *before*
  designing a study around its residual.
- **Staleness in a synthetic index manufactures both autocorrelation and lead-lag.** Every
  cross-asset claim here was re-run on the EUR-only proxy for that reason, and should be.

## IDEA-0001 — Cross-asset macro decomposition: DXY as an explicit factor for gold and equity indices

- Created: 2026-07-31
- Observation: the workspace has tested cross-market *filters* repeatedly (GC gated on ES,
  NQ gated on ES) and they consistently behave as turnover levers rather than alpha. It
  has never tested a cross-market **decomposition**: using a macro factor to split an
  instrument's own move into an explained and an unexplained part.
- Proposed mechanism: gold and, more weakly, the equity indices are priced against the
  dollar. The dollar-explained part of a move is a mechanical repricing that arbitrage
  completes immediately; the residual is instrument-specific order flow, which is
  persistent because large orders are worked over time. The two parts should therefore
  have different forward properties, and a filter cannot see the difference because it
  only observes the sum.
- Expected improvement: not a strategy — a decomposition that either concentrates the
  predictive content into one leg or shows the split is empty. Either answer is useful.
- Main artifact risk: a synthetic dollar index built from futures legs of unequal
  liquidity is forward-filled, and staleness manufactures exactly the autocorrelation and
  lead-lag the study measures. Mitigated by the EUR-only control arm and a per-slot
  staleness report.
- Motivating evidence: `futures/gc` EXP-0002 (gold's edge lives in equity RTH), EXP-0007
  (ES direction does not condition GC); `futures/nq/noise_vwap` EXP-0018.
- Status: promoted to HYP-0001..HYP-0004; **all four closed, all four rejected**. The
  answer to the framing question is that the split is empty at every horizon tested,
  and finding F explains why: the factor's R² is too small for the residual to be a
  different variable.
