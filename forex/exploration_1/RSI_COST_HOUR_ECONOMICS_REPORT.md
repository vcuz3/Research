# Cost-hour economics (Workstream A, D1 + D2) — REPORT

Spec: `RSI_COST_HOUR_ECONOMICS_SPEC.md`. Run: `python -u _run_cost_hour_economics.py`
→ `cost_hour_economics_results.json`, `cost_hour_economics_cells.csv`,
`cost_hour_economics_per_hour.csv`. Cost model: `_cost_model.py` (tested,
`_test_cost_model.py`, 15/15). Consumed history; 2024+ sealed.

## Verdict: **NO-GO** for a spread/commission-taking version, at every hour, era,
scenario and pair tested. The kill test fires: **0/4 pairs are net-positive in the
liquid London/NY hours** under the base scenario at the mandatory one-minute delay.

## Headline numbers (delay 1, median across pairs)

| arm | gross pips | gross R | mean cost pips | net pips | net R | net cluster t |
|---|---:|---:|---:|---:|---:|---:|
| best cell — base | 0.286 | 0.036 | 1.149 | **−0.852** | **−0.113** | −16.2 |
| best cell — optimistic | 0.286 | 0.036 | 1.014 | −0.718 | −0.099 | −14.1 |
| best cell — pessimistic | 0.286 | 0.036 | 1.373 | −1.077 | −0.137 | −19.7 |
| best cell — **base, NO commission** | 0.286 | 0.036 | 0.449 | **−0.152** | −0.021 | −3.1 |
| ungated base — base | 0.199 | 0.027 | 1.152 | −0.911 | −0.169 | −29.9 |

## What kills it

1. **The commission is the dominant term and it is a hard floor.** FTMO-style
   $3.5/side on a $10/pip pair is **0.70 pip round trip** — on its own **~2.4× the
   0.286 pip gross edge**, before any spread. Stripping commission entirely still
   leaves the strategy net-negative (−0.15 pip, t −3.1): the modelled spread over the
   *traded* hours averages ~0.45 pip round trip, itself above gross.
2. **The edge cannot escape into cheap hours because it has none.** Per-hour, **gross
   is below modelled cost in all 24 UTC hours** (best cell, base, delay 1). The
   cheapest hour is the 15:00 UTC overlap (gross 0.43, cost 1.03, net −0.53); the
   dearest are the 21:00–22:00 rollover (cost 1.9–2.3) — and the project's own edge
   leans into those late hours, so restricting to liquid hours *reduces* net R only
   from −0.11 to −0.06, never above zero. Overlap-only (12–16 UTC): −0.04 to −0.10,
   4/4 negative.
3. **It is worse per unit of exposure on the ungated base** (net R −0.169) than on the
   selective best cell (−0.113): selectivity helps, but nowhere near enough — the gate
   raises gross from 0.199 to 0.286 pip, a 0.087 pip lift against a 1.15 pip cost.

## Interpretation

The strategy is a **~0.29 pip gross edge facing a ~0.7–1.4 pip round-trip cost floor**.
The floor is set primarily by per-lot commission, which is depth-, hour- and
scenario-independent. No time-of-day selection route (D2) closes a gap this size, and
the modelled-cost verdict is not a fragile cost-model artefact: it is negative even in
the optimistic scenario and even with commission zeroed.

**Consequences for the remaining workstreams (before building them):**

- **D5 (passive entry) cannot rescue this alone.** Earning rather than paying the
  half-spread saves at most ~0.45 pip, but the ~0.70 pip commission remains and still
  exceeds gross. Passive entry is only relevant *combined with* a large gross increase.
- **D3 (depth) is the pivotal open question** and is tested next
  (`_run_depth_cost.py`): can selectivity push **gross pips per trade above the
  ~0.7 pip commission floor** at any usable frequency? The `|z|` frontier to date tops
  out near ~0.34 pip gross at z=3.0, so the prior is *no* — but the ceiling must be
  measured, because it decides whether any net-positive per-trade configuration exists.
- **D6/D7 (challenge simulator, portfolio) are moot until B finds a net-positive
  per-trade stream.** A challenge cannot be passed by compounding trades that each lose
  ~0.85 pip net; a portfolio of net-negative legs is net-negative. C is therefore
  gated on a positive B result, not run in parallel.

This is a rule-25 outcome: a decisive NO-GO on the spread-taking version, preserved as
evidence. The one remaining live route is "raise gross per trade above the commission
floor" (D3, then possibly D4/D5); if it fails, the honest conclusion is that this edge
is not deployable on retail/prop FX cost structures.

## D3 depth-ceiling confirmation (`_run_depth_cost.py` → `depth_cost_results.json`)

Sweeping ungated `|z|` from 1.5 to 5.0, delay 1, median across pairs:

| z | signals/yr | gross pips | gross R | risk unit | net (base) | net (optimistic) |
|---:|---:|---:|---:|---:|---:|---:|
| 1.5 | 6,152 | 0.199 | 0.027 | 7.5 | −0.911 | −0.775 |
| 2.0 | 4,268 | **0.230** | 0.029 | 7.2 | −0.950 | −0.813 |
| 2.5 | 2,743 | 0.227 | 0.028 | 7.6 | −0.992 | −0.852 |
| 3.0 | 1,697 | 0.196 | 0.026 | 7.7 | −0.985 | −0.841 |
| 3.5 | 1,022 | 0.079 | 0.012 | 5.7 | −1.151 | −1.001 |
| 4.0 | 635 | −0.033 | 0.011 | 10.1 | −1.295 | −1.112 |
| 4.5 | 454 | −0.213 | −0.005 | 37.4 | −1.486 | −1.306 |
| 5.0 | 363 | −0.527 | −0.018 | 16.7 | −1.650 | −1.523 |

**Depth does not raise gross — gross pips PEAK at 0.230 (z=2.0) and fall thereafter**,
turning negative beyond z=3.5. Under the compulsory 3R stop and 30-minute horizon the
deep-`z` signals overshoot and the risk unit grows faster than the pip capture, so the
selectivity lever that works in *R-excess* terms does not translate into pips that clear
a fixed cost. **The gross ceiling (0.230 pip) is a third of the commission floor
(0.700 pip); no depth is net-positive under any scenario, on any pair.**

## Final synthesis — Workstream A + B(D3)

The edge is a **~0.23–0.29 pip gross** phenomenon facing a **~0.70–1.15 pip round-trip
cost floor** whose dominant, depth/hour/gate-independent term is the **per-lot
commission (~0.70 pip)**. The gap is 3–5× and unbridgeable by the signal-side levers
this project controls:

- **D2 time-of-day:** no hour has gross > cost; liquid-hours restriction never reaches
  net-positive.
- **D3 depth:** gross does not even increase with depth; ceiling 0.230 pip << 0.700 pip.
- **D5 passive entry (unbuilt, but bounded):** earns at most the ~0.45 pip spread; the
  ~0.70 pip commission alone still exceeds the 0.23 pip gross, so passive entry cannot
  rescue a taker on a commissioned account.
- **D4 target exit (unbuilt, but bounded):** would need to ~3× the per-trade capture to
  ~0.70 pip; the project's own MFE/exit work already found stops and take-profits do not
  help (winners and losers share the same tail, |win|≈|loss|), so this ceiling is also
  well under the floor.
- **D6/D7 (challenge sim, portfolio):** cannot pass a challenge by compounding trades
  that each lose ~0.85 pip net; a portfolio of net-negative legs is net-negative. **Not
  built — they are moot without a net-positive per-trade stream, and none exists.**

**Deployability conclusion:** on an FTMO-style raw-spread + commission cost structure,
this mean-reversion edge is **not deployable as a cost-taker**. The only routes that
could change the verdict are outside the strategy's reach: a genuinely commission-free
account with a sub-0.2-pip round-trip spread (does not exist in retail/prop FX), or a
fundamentally larger-per-trade-move strategy (a different research programme, not an
enhancement of this one).

**Load-bearing caveat:** the cost is *modelled*, not measured — chiefly the $3.5/side
commission and the spread profile. The verdict is robust to the spread (negative even
commission-free and in the optimistic scenario), so it rests almost entirely on the
**commission assumption**. If a specific target account has a materially lower or zero
commission, re-run with that `CostParams` before accepting the NO-GO. That single number
is now the highest-value input the project can obtain.

