# EXP-0026 — HYP-0017 Hurst-exponent trade filter

- Hypothesis: `experiments/hypotheses/HYP-0017.md`
- Builder: Claude (Opus 4.8), 2026-07-22
- Baseline: continuous-stop NQ/ES baseline (noise_bands lb90, RTH, 30-min clock,
  VWAP gate, every-bar band/VWAP stop, next-open fills, per-instrument costs).
- Code: `scripts/hyp_0017_hurst_filter.py`
- Reproduce:
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0017_hurst_filter real {NQ|ES}`
- Artifacts: `sweep_{NQ,ES}.csv`, `random_null_{NQ,ES}.csv`,
  `hurst_features_{NQ,ES}.parquet`, `verdict_{NQ,ES}.json`.

## What was tested

Causal, session-to-date generalized Hurst exponent (order-1 structure function,
`E|X(t+τ)-X(t)| ∝ τ^H`, log-log slope over lags {1,2,3,4,5,7,10,15,20}∩[≤n/2]) of
the log-close path anchored at the session open, evaluated at every 30-min
decision bar. Estimator validated on synthetics: pure trend → H≈0.99, random walk
→ H≈0.49. Three signals gated the entry (rule-18 engine rerun via `entry_gate`,
numba↔engine2 parity asserted on the ungated baseline):

- **H** — the level (persistence regime),
- **dH** — 1st derivative / ROC along the within-session decision clock,
- **d2H** — 2nd derivative (acceleration).

Each swept over a threshold grid in both directions ("high" = keep S≥T,
"low" = keep S≤T). NQ intraday H distribution: median 0.49, ~45% of decisions
above 0.5 — well-centred on the random-walk boundary, good for a threshold sweep.

## Result versus hypothesis — REJECT as alpha (cross-market NO-GO), real per-trade info

| market | base Sh | base netR | base gross_pt/t | FAMILY-BEST cell | dSharpe | dNetR | gross_pt/t | retain |
|---|---|---|---|---|---|---|---|---|
| NQ | 1.288 | 91.20 | 3.509 | **H ≥ 0.50** | **+0.058** | **−10.4** | 4.592 | 0.617 |
| ES | 0.698 | 51.47 | 0.730 | **H ≥ 0.50** | **+0.084** | **−2.9** | 1.008 | 0.560 |

Both markets independently select the SAME natural threshold, **H ≥ 0.5** (the
random-walk boundary), as the family-best — a non-cherry-picked, mechanism-
consistent optimum. Real gate (dSharpe ≥ +0.10 AND netR ≥ base) **REJECTS on both**
(dSharpe below +0.10 and net R falls). Per the standing rule, no Null-C spent.

## Gross, net, baseline, and null comparison

The mechanism SIGN is real and transfers:

- **The Hurst LEVEL carries genuine per-trade selection information in the
  predicted direction.** As the H≥T threshold rises, gross points/trade and
  expected net-R/trade rise MONOTONICALLY on both markets — persistent-tape
  breakouts are higher quality:
  - NQ gross_pt/t 3.509 → 4.592 (H≥0.5) → ~4.4 (H≥0.6); exp netR/t 0.0217 →
    0.0311 → 0.0463.
  - ES gross_pt/t 0.730 → 1.008 (H≥0.5); exp netR/t 0.0119 → 0.0201.
- **The `low` (chop-regime) direction is worse everywhere on both markets** — a
  clean sign confirmation: keeping only anti-persistent-tape breakouts
  monotonically degrades Sharpe (NQ down to 0.32, ES to 0.37). The breakout
  system genuinely wants a persistent tape.
- **matched-count random-signal-drop null** (keep the same number of candidate
  breakouts at random, 200 draws) — the rarity-filter discriminator:
  - NQ: real dSharpe +0.058 vs random mean −0.148 (sd 0.096); frac(rand≥real)
    Sharpe = **0.030**. The H≥0.5 selection BEATS a random equal-count drop → NOT
    a pure rarity filter; there is real per-trade information.
  - ES: real +0.084 vs random −0.050 (sd 0.106); frac(rand≥real) Sharpe =
    **0.080** — same direction but marginal (does not clear 0.05). The per-trade
    info is real but weaker on ES.

Why it is still a NO-GO as alpha: the H≥0.5 filter is a **turnover/capacity
lever, not risk-adjusted alpha** — the exact [[nq-es-crossmarket-confirm]]
pattern. It raises per-trade quality (gross/t +30% NQ, +38% ES) while cutting
exposure ~40%, so total net R FALLS on both (NQ −10.4R, ES −2.9R), daily Sharpe
rises only +0.058 / +0.084 (below the +0.10 gate), and drawdown does not improve
enough to matter (NQ maxDD 4.70→4.17R). Better selection + less exposure = no
risk-adjusted gain. Persistence is a per-trade-quality tag, not a monetizable
timing signal, on a system that already rides intraday drift to the close.

## Regimes, sensitivity, and alternative explanations

- The Sharpe/expected-R sensitivity to the H threshold is smooth and monotone on
  the "high" side up to H≈0.5, then Sharpe collapses past H≈0.55 as the trade
  count and total net R fall off a cliff (retain < 0.37) — the interior Sharpe
  peak at H≥0.5 is the capacity/quality trade-off turning over, not a stable
  optimum. Expected net-R/trade keeps rising past H≥0.5 (to 0.046 at H≥0.65),
  confirming the per-trade-quality signal is monotone even where Sharpe dies.
- **Derivatives add nothing (the user's dH / d2H hypotheses rejected).** Every dH
  and d2H cell, both directions, both markets, is WORSE than baseline (dSharpe
  negative throughout; NQ best dH ≈ −0.24, d2H ≈ −0.51). Rising or accelerating
  persistence carries no usable edge beyond the level — and even the level does
  not monetize. The ROC/acceleration framing is inert-to-harmful.
- Consistent with the project's volatility-INDEPENDENCE finding
  ([[nq-noise-vwap-prop-challenge]]) and the string of selectivity screens
  (KAMA regime, gap veto EXP-0024, RVOL veto EXP-0016) that all resolved as
  variance/turnover levers rather than alpha.

## Artifact and implementation risks

- Causality: Hurst uses only closes at/before the decision bar; fill is next-open.
- Rule 18: the filter is a stateful `entry_gate` engine rerun, not a post-hoc
  trade drop, so flip/position bookkeeping is correct under filtering.
- numba↔engine2 parity asserted on the ungated baseline (`assert_parity`).
- The matched-count null samples from the candidate breakout pool restricted to
  signals where the tested signal is DEFINED (fair for dH/d2H).
- Estimator quality is time-of-day dependent (session-to-date window grows through
  the day); this is a limitation but does not affect the REJECT — the sign and the
  no-monetization conclusion are robust across the threshold sweep and transfer to
  ES.

## Builder interpretation

The user's core intuition is partly VINDICATED at the descriptive level: a
persistent (high-Hurst) intraday tape genuinely produces higher-quality
breakouts, the effect is monotone in H, peaks at the natural H=0.5 boundary
without tuning, transfers to the ES sibling, and beats a matched-count random
drop on NQ (p=0.03). But it does not become money: like cross-market
confirmation, it is a per-trade-quality/capacity lever that cuts exposure and
total net R and leaves Sharpe below the deployment gate. The requested
derivatives (ROC, 2nd derivative) are inert-to-harmful. Retain the unconditioned
baseline; if ever revisited, only as a default-off per-trade-quality/capacity
dial on a forward holdout, never as a Sharpe claim.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: pending
- `MEMORY.md`: updated (HYP-0017 rejected; per-trade-quality caveat recorded)
- Shared `LEARNINGS.md`: not eligible without cross-project verification
