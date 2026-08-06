# RSI/z fade — directional-EFFICIENCY conditioner (REPORT)

Run 2026-08-05. Frozen spec: `RSI_EFFICIENCY_GATE_SPEC.md`. Screen on consumed
history (2012–2023); 2024+ sealed. Engine identical to the confirmed regime matrix
(event clock, non-overlap, 2R stop, 1-pip slippage, 30-min horizon); the only moving
part is the conditioning variable. Primary metric: excess mean R over the `|z|`
frontier at matched signals/year, delay 1, median across the four pairs.

## Verdict

**The preregistered hypothesis is REJECTED, and falsified in the opposite
direction.** The thesis was: reversion is better in LOW-efficiency (choppy) states.
It is the reverse — fading a `|z| >= 1.5` extreme reverts BETTER when the recent path
was EFFICIENT / trending, and WORSE when it was choppy — on 6/6 low-vs-high cells.

```
DIRECTIONAL KILL (median excess R over frontier, delay 1)
  ker keep 40/20/10%:  low -0.0118/-0.0144/-0.0059   high +0.0016/+0.0015/+0.0036
  adx keep 40/20/10%:  low -0.0118/-0.0208/-0.0162   high +0.0070/+0.0069/+0.0043
  htf: withtrend -0.0054   countertrend -0.0033        (both negative)
```

Every LOW-efficiency gate is worse than the frontier at matched rate (a real
degradation, not a wash); every HIGH-efficiency gate is at or above it.

## What the screen surfaced (a NEW, post-hoc hypothesis — not adopted)

The **ADX/DI** channel carries a reversed signal that clears the kill-test bar:

| arm | excess R | pairs ≥0.005 | delay-0 | risk unit |
|---|---|---|---|---|
| high_adx_z 20 | **+0.0069** | 4/4 | +0.0021 | 8.01 |
| high_adx_z 40 | +0.0070 | 3/4 | +0.0013 | 8.31 |
| high_ker_z 20 | +0.0015 | 1/4 | −0.0013 | 9.17 |

So it is specifically the directional-movement (ADX/DI) structure — not net/gross
path efficiency (KER, weak, 1/4 pairs) — that reverts better. Mechanistically: a
clean directional over-extension to an extreme snaps back; a choppy grind to the same
displacement is an already-balanced market with less to give back.

**This is not a result.** The spec forbade flipping the preregistered direction post
hoc (rule 26). `high_adx_z` is a screen-generated candidate that would need its own
frozen hypothesis, a claim-matched donor-matched null (rules 16–18), and a redundancy
check against the already-confirmed volatility gate before it could be credited.

## Why it does not change the economics

- Magnitude is ~half the confirmed vol gate (+0.0069 vs +0.0137 R excess).
- At the 30-min horizon the high_adx gross is ~0.20 pip against the ~0.70 pip
  commission floor — still ~3.5× underwater. It is a mechanism finding, not a lever.
- Risk unit (8.0–8.3) sits slightly *below* the frontier's ~9.5, so it is not simply
  re-selecting the highest-σ states — which is what makes it interesting, but also
  means its relationship to the vol gate is unproven (could stack or be redundant).

## Guardrails

- **Coverage (rule 9a):** KER/ADX defined on 1.000 of base signals for EUR/GBP/AUD;
  0.973–0.992 for NZD, the few missing in thin late-session minutes — not distorting.
- **mean R beside pips / risk unit** reported on every arm (table above and CSV).
- **Feature tests:** `_test_efficiency_features.py` 10/10 (KER=1 on a straight line,
  0 on a zigzag, undefined across a gap; ADX high on a trend / low on chop; both
  causal; ADX resets per session).

## Files

`_efficiency_features.py`, `_test_efficiency_features.py`,
`_run_rsi_efficiency_gate.py`, `rsi_efficiency_gate_results.json` / `.csv`.
Reproduce: `python -u _run_rsi_efficiency_gate.py`.
