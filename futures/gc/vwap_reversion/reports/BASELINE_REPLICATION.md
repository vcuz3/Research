# BASELINE — GC VWAP-band mean-reversion (fade)

- Baseline experiment ID: EXP-0000
- Frozen config: `baseline_replication/configs/faithful_config.json`
- Command: `python -m futures.gc.vwap_reversion.scripts.run_baseline GC 1s`
  (1-minute comparison: `... GC 1m`)
- Evidence: `artifacts/runs/EXP-0000/`

**Verdict: NO-GO.** The ±2σ VWAP fade with a fixed 2RR bracket has **no gross edge**
on GC once fills are resolved at 1-second precision, and is **net-negative at every
realistic cost**. The bands are efficient: gold does not revert from ±2σ to VWAP
often enough to beat the 2RR geometry.

## Data scope

| Resolution | Sessions | Bars | Range | Trades |
| --- | ---: | ---: | --- | ---: |
| 1-second (baseline) | 3964 | 39,358,546 | 2010-06-07 → 2026-07-17 | 10,673 |
| 1-minute (comparison) | 3647 | 1,420,745 | 2011-08-01 → 2026-07-16 | 10,067 |

Fill feasibility asserted in code (`assert_fills`): every entry/exit fill attainable
within its bar; gap-through fills at the bar open (rule 5). Same-bar (entry==exit)
rate 2.0% at 1s vs 5.2% at 1m.

## Headline (1-second, accurate fills; 1 GC contract, $100/pt)

| Cost/side | n | win% | payoff | expR | net pt/trade | total net $ | Sharpe | day-t | Calmar | maxDD $ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **gross** | 10,673 | 33.4 | 2.01 | −0.021 | **+0.013** | +13,663 | +0.08 | +0.32 | +0.01 | 64,163 |
| 0.25 tick | 10,673 | 33.3 | 1.89 | −0.111 | −0.082 | −87,731 | −0.51 | −2.03 | −0.04 | 144,584 |
| 0.50 tick | 10,673 | 33.2 | 1.83 | −0.158 | −0.132 | −141,096 | −0.82 | −3.27 | −0.05 | 194,844 |
| 1.0 tick | 10,673 | 32.9 | 1.72 | −0.253 | −0.232 | −247,826 | −1.45 | −5.74 | −0.05 | 298,294 |

Long 5367 / short 5306 (balanced). Exit reasons: stop 6886, target 2782, eod 1005.

**Why it fails.** A fixed 2RR bracket (win +2σ, lose −1σ) breaks even gross at a
1/3 = 33.3% win rate. Realized gross win rate is **33.4%** — statistically a fair
coin at the bracket geometry, i.e. **no predictive reversion signal**. Gross
expectancy is ≈0 (t=+0.32); any transaction cost then makes it a reliable loser.

## The 1-second data changes the conclusion (this is why 1s was used)

At 1-minute resolution the fade looked marginally better — gross +0.092 pt/trade,
Sharpe +0.57, t=+2.16, win rate 35.6%:

| | gross pt/trade | gross Sharpe | gross t | win% | same-bar |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1-minute | +0.092 | +0.57 | +2.16 | 35.6 | 5.2% |
| 1-second | +0.013 | +0.08 | +0.32 | 33.4 | 2.0% |

The 1-minute gross was a **coarse-bar fill artifact**: when a single minute both
dips to the target and spikes to the stop, 1-minute OHLC cannot say which came
first, and a bar that "only reached the target" can still contain an earlier
stop-touch invisible at 1m. 1-second bars reveal those stop-first paths → the win
rate falls 35.6% → 33.4% and the gross edge evaporates. **The honest number is the
1-second number.**

## Fill-assumption sensitivities (1-second) — the edge does not hide in optimism

- **Same-bar TARGET allowed** (path-optimistic, rule 3): net @0.5 tick −0.124 vs
  conservative −0.132 — essentially identical (only 31 same-bar target wins at 1s).
  The conservative default is not what is killing it.
- **Strict +1-tick trade-through entry** (queue guard, rule 4): net @0.5 tick
  −0.197 (worse). No queue-friendly version exists.

Every variant at every cost is net-negative with a strongly negative day-clustered
t-stat.

## Claim results

| Claim ID | Claim | Threshold | Result | Status |
| --- | --- | --- | --- | --- |
| CLM-001 | net-profitable @0.5 tick under honest fills | > 0 | −0.132 pt/trade, Sh −0.82 | **FAIL** |
| CLM-002 | edge not dependent on optimistic path | sign stable | gross ≈ 0 both ways | FAIL (no edge to be stable) |
| CLM-003 | survives strict trade-through entry | > 0 | −0.197 pt/trade | **FAIL** |

## Interpretation and consistency

- Consistent with the workspace's prior NQ finding that VWAP σ-bands are **efficient**
  (shared memory `nq-vwap-band-nogo.md`): fading the band is not an edge.
- Clean kill-test pass for a NO-GO. No Null-C warranted — the real pass fails its
  primary metric (gross ≈ 0, net < 0), already a REJECT (gate: don't run Null-C on a
  failing real pass).

## Limitations / not done (edge is already NO-GO)

- RTH equity window 09:30–16:00 inherited from noise_vwap; a gold-native session was
  not tested (sweeping windows on consumed history is discouraged, rule 26).
- kb/ks/window/gap are the prespecified baseline; no parameter search was run.
- All history here is consumed research data, not a sealed holdout.
