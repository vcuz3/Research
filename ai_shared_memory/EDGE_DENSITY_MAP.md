# Edge-Density Map — where to dig next

A living, scored ranking of candidate research terrains. Its job is to stop the
program from uniformly sampling the most-efficient corners of the most-efficient
markets, and to point the (elite) validation stack at ground with a real prior.

**This is a prioritisation doc, not evidence.** A high score is a hypothesis
about where edge *should* be denser, to be tested — never a claim that edge
exists. Re-score when a seam is exhausted or a new dataset lands.

## How terrains are scored (1 = poor, 5 = strong)

- **Prior** — is there a *structural* reason a price is pushed away from fair
  value (a forced trader, a constraint, a mandate)? Mechanism-first beats
  pattern-first, which has a terrible prior in liquid markets and is where nearly
  every trap in `LEARNINGS.md` was born.
- **Breadth** — how many *independent* bets are available? IR ≈ IC·√breadth, so
  breadth is the cheapest multiplier we have. 4 USD majors ≈ 2 effective; NQ↔ES
  ≈ 1.x. Measure it with `effective_breadth` in the kill battery.
- **Data edge** — do we hold something others don't, or are we running a new
  function of the same closes everyone has?
- **Capacity** — can it hold meaningful size before it self-arbitrages? (Higher
  is better for deployment; low capacity can still be fine for a prop challenge.)
- **Uncrowded** — inverse of how many colocated PhD shops are already there.

`Score = Prior + Breadth + Data + Capacity + Uncrowded` (max 25). Ordering is
judgement, not arithmetic — the columns exist to make the trade-offs explicit.

## The map (initial scoring, 2026-08-10)

| Terrain | Prior | Breadth | Data | Cap | Uncrowd | Σ | Verdict |
|---|:-:|:-:|:-:|:-:|:-:|:-:|---|
| **Order-flow / microstructure** (NQ MBP-1, L2/CVD) | 4 | 3 | **5** | 2 | 3 | **17** | **DIG** — differentiated data, your best-instinct queued project |
| **Forced-flow / calendar events** (index rebal, month-end, fixings, roll) | **5** | 4 | 3 | 3 | 3 | **18** | **DIG** — mechanism-first; your one flow survivor (news-blackout) is real |
| **Cross-sectional breadth** (one signal × many instruments) | 3 | **5** | 2 | 4 | 3 | **17** | **DIG** — buys the breadth the whole program lacks |
| **Positioning / carry / funding** (COT, basis, swap points) | 4 | 3 | 4 | 4 | 3 | **18** | **SCOUT** — structural, underused data, slow clock |
| **Prop-challenge payoff geometry** (risk-of-ruin under hard DD) | 3 | 2 | 2 | 2 | 4 | **13** | **SCOPE HONESTLY** — a survival/payoff problem, *not* an alpha hunt |
| **Intraday reversion/continuation on liquid FX/index** | 2 | 1 | 1 | 4 | 1 | **9** | **STARVE** — your NO-GO graveyard; the honest answer here is "no edge" |
| **Threshold/anchor/VWAP transforms of price** | 1 | 1 | 1 | 3 | 1 | **7** | **STOP** — exhausted; every variant rejected across NQ/GC/FX |

### Reading the map
- The three **DIG** rows share a pattern: a *structural* reason (flow, mandate,
  microstructure) and/or *breadth*, and at least one thing others don't have.
- The two bottom rows are where the vast majority of past effort went and where
  the vast majority of NO-GOs came from. That is not bad luck — it is what those
  markets are. **Move the aim, keep the machine.**
- **Prop-challenge** is deliberately called out as mis-scoped when framed as
  alpha: you already found "~half of pass odds are barrier geometry" and
  "vol-targeting is survival-not-alpha." Solve it as a stochastic-payoff /
  risk-of-ruin optimisation with an explicit objective, not as a Sharpe hunt.

## Standing rules for using this map
1. Before building, write the **mechanism statement**: the forced trader, their
   constraint, the compensation, and the *asymmetric* prediction that separates
   your mechanism from a generic pattern (name the cell where it MUST fire first).
2. Run `tools/preflight_kill_battery.py` on the candidate *before* the engine.
3. Prefer the highest-Σ terrain you have data for. Do not add a study to a
   STARVE/STOP row without a genuinely new dataset or mechanism.
4. When a seam is exhausted, **re-score the whole terrain**, don't try the next
   parameter (cf. the NQ noise-band programme, correctly closed as EXHAUSTED).

## Change log
- 2026-08-10 — created; initial scoring from the FX/futures NO-GO history in
  `MEMORY.md` and `LEARNINGS.md`.
