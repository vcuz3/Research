# EXP-0004 — Momentum-in-high-VEI strategy test (HYP-0001)

- Builder: Claude (Opus 4.8), 2026-07-26
- Verdict: **Mechanism CONFIRMED, edge REJECTED.** The VEI regime is a real,
  cross-market momentum selector (clean, correct-signed gross dose-response), but the
  per-trade tilt is too small to overcome costs and produce a deployable daily edge.
  Preregistered kill-test 1 fails on both markets → nulls skipped (standing rule).

## Design (preregistered, HYP-0001)

Causal momentum simulator (`core/strategy.py`): at each 30-min RTH decision bar, if the
VEI gate holds, take side = sign(trailing 30-min return); fill next-open; hold 30 min;
flat at close; non-overlapping single-position bets; conservative per-interval round-trip
cost (NQ 0.35 pt, ES 0.215 pt); R = net pts / causal daily ATR(14). Canonical VEI =
Wilder(10/50) (Study A). Preregistered primary cell = `high` (VEI>1.10), H=30. Controls:
`all` / `low` dose-response, T sweep, horizon check, ES cross-market.

## Result

### Dose-response (T=1.10) — mechanism confirmed

| cell | NQ gross pt/t | NQ netR | NQ Sharpe (t) | ES gross pt/t | ES Sharpe (t) |
|---|---|---|---|---|---|
| `all` (no gate) | +0.054 | −160.9 | −1.17 (−4.5) | +0.018 | −2.52 (−9.7) |
| `low ≤1.10` | −0.008 | −162.9 | −1.40 (−5.4) | +0.008 | −2.68 (−10.3) |
| **`high >1.10`** | **+0.959** | +0.68 | +0.015 (0.06) | **+0.375** | −0.073 (−0.28) |

Same momentum rule, only the VEI gate differs. Momentum's positive **gross** expectancy
lives almost entirely in the high-VEI regime; in the calm/contracting regime it is
≈0/negative. Sign is correct (high ≫ low) and **transfers to ES**. This confirms Study D
at the strategy level: VEI selects *when* momentum is present. (Because it is a
within-sample same-rule contrast that flips sign as predicted and transfers cross-market,
the mechanism is established without spending a Null C.)

### But not deployable

The `high>1.10` gross tilt is only ~0.96 pt/trade (NQ) / 0.38 (ES); cost eats a third,
and the daily aggregation is near-zero and lumpy (high-VEI bets cluster on volatile
days): daily Sharpe +0.015 (NQ, t=0.06) / −0.073 (ES). **KILL-TEST 1 (netR>0 & Sh>0 &
day_t≥2 & high>low) REJECT** on both. Per the standing rule the matched-count random
null and the path-preserving Null C were not spent.

### Sensitivity (labelled, not the primary)

- T sweep: net pt/trade rises monotonically with T (NQ T=1.15 +1.58, T=1.20 +1.92) and
  the `low` side is monotonically worse — a clean dose-response corroborating the
  mechanism, but Sharpe/day-t never clear the bar (t<1 everywhere).
- Horizon: the effect strengthens with hold — H=60 gives NQ Sharpe +0.449 (t=1.72,
  net/t +1.62) / ES +0.357 (t=1.37). Still below t≥2, and a post-hoc horizon, so a
  forward-watch lead, not a pass. Suggests the high-VEI trend persists beyond 30 min.

## Interpretation

The recurring project pattern, now confirmed for VEI momentum with a preregistered test:
a **real, cross-market per-trade signal that does not monetize**. VEI is a genuine
momentum regime switch (the gross dose-response and Study D both show it), but the edge
is sub-cost and daily-lumpy — not a standalone tradable strategy. Consistent with the
noise_vwap prior that intraday-momentum vol-selectivity screens are turnover/quality
levers, not portfolio alpha.

Notably the recent era (2023+) is positive on the high cell (NQ 23+Sharpe +0.875, ES
+1.50) — but on consumed history that is a forward-watch observation, not evidence
(rule 26). If revisited, the promising axis is horizon (H=60) and using the high-VEI
switch to *gate an existing* momentum book rather than as a standalone.

## Reproduce

```
python -u -m futures.nq.vei_exploration.scripts.hyp_0001_momentum_vei real NQ
python -u -m futures.nq.vei_exploration.scripts.hyp_0001_momentum_vei real ES
```

---

## ERRATUM (added 2026-07-26 by EXP-0005) — two corrections; the verdict stands

The verdict above (mechanism confirmed, edge rejected) is unchanged: the preregistered
primary cell `high>1.10, H=30` is untouched by both corrections (NQ n=2636, Sharpe
+0.015; ES n=3102, Sharpe −0.073), so kill-test 1 still fails and the nulls remain
correctly unspent. Two things written above are wrong and must not be carried forward.

**1. The H=60 row was a 2-unit book (rule 13).** A 60-minute hold on a 30-minute
decision clock fills a second bet before the first exits, while HYP-0001 declares
non-overlapping single-position bets and `score()` sums per-bet R per day as one unit.
`core/strategy.py::simulate` now enforces non-overlap by default (`allow_overlap=True`
opts into concurrency), guarded by `tests/test_strategy.py::test_no_overlap_is_the_default`.

| cell | NQ netR | NQ Sharpe (t) | ES netR | ES Sharpe (t) |
|---|---|---|---|---|
| `H60_overlap2u` (the row published above) | +28.07 | +0.449 (1.72) | +26.43 | +0.357 (1.37) |
| **`H60_1unit`** (the declared estimand) | +22.83 | +0.442 (1.70) | +32.67 | **+0.526 (2.02)** |
| `H60_clock60` (60-min decision clock) | +12.01 | +0.288 (1.10) | +12.85 | +0.249 (0.96) |

H=60 remains a post-hoc horizon on consumed history (rule 26), so the corrected ES
t=2.02 is **not** a pass — and `H60_clock60` shows the apparent horizon benefit also
depends on keeping the 30-minute cadence. The guard additionally removed 2 NQ bets from
the `all`/`low` H=30 cells (netR −160.95 → −161.19): `simulate` works in bar-index
space, so on a session with missing minutes a nominal 30-minute hold spans fewer than 30
index positions and can genuinely overlap the next decision. ES unaffected.

**2. "The effect strengthens with hold" is wrong.** The Interpretation section above
reads the H=60 Sharpe as evidence that the high-VEI trend persists beyond 30 minutes.
EXP-0005's term structure (composition-free constant sample) shows the opposite —
corr(past 30m, fwd H) in the high regime **peaks at H=5–10 min** (NQ +0.177 / ES +0.170)
and decays to ≈0 by H=90–120 and to-close. What improves with a longer hold is the cost
ratio, not the signal: a fixed round trip amortised over a bigger move. There is no
basis for expecting further gains past ~60 minutes, and "H=60 is the promising axis"
should be read as a cost-efficiency observation only.

The audit of the underlying mechanism came out the other way, in EXP-0004's favour:
Study D's regime contrast survives time-of-day matching intact on both markets
(HYP-0002). See `artifacts/runs/F_term_structure/review.md`.

## Independent review

- Reviewer: unassigned
- Status: not-reviewed
- Open items: confirm the next-open/fixed-horizon fill causality in `core/strategy.py`
  (tests in `tests/test_strategy.py`), the conservative per-interval cost, and the
  preregistered gate (kill-test failed at gate 1, so the nulls were correctly not run).
