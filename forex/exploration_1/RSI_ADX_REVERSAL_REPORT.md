# RSI/z fade — reversed high-ADX conditioner (REPORT)

Run 2026-08-05. Frozen spec: `RSI_ADX_REVERSAL_SPEC.md`. Confirmatory test of the
POST-HOC reversed direction surfaced by `RSI_EFFICIENCY_GATE_REPORT.md` (high recent
directional strength → better reversion). Screen on consumed history (2012–2023);
2024+ sealed and NOT opened. Engine identical to the confirmed regime matrix (event
clock, non-overlap, 2R stop, 1-pip slippage, 30-min horizon). Reproduce:
`python -u _run_rsi_adx_reversal.py`.

## Verdict — a real CONDITIONING RELATIONSHIP, but NOT a robust independent gate, and economics unchanged

The automatic panel-count gate printed "REAL & INDEPENDENT". Read per-pair (rule 26;
correlated pairs ≈ 2–3 effective tests; EURUSD weakest), the honest verdict is narrower:

- **The conditioning relationship is confirmed at the family level.** The cleanest,
  best-controlled test — the within-vol conditional split (§3) — is **4/4 pairs**: among
  volatility-gate signals, the high-ADX half out-reverts the low-ADX half by **+0.0069
  to +0.0096 R**, depth-matched and rate-matched (both halves ≈50%, same |z| depth).
- **It is NOT a deployable independent gate.** As a hard AND conjunction on top of the
  vol gate (§2) it stacks on only **2/4 pairs meaningfully** (EUR +0.0080, NZD +0.0191);
  GBP is ≈0 (+0.0004) and **AUD is negative (−0.0073) — combining HURTS**. The
  selection-corrected null (§4) fails on EURUSD, and the NZD "pass" is carried by a KER
  arm (`low_ker_raw 10`), not the ADX candidate. Best cell differs per pair (keep 10 on
  EUR/GBP, keep 20 on AUD) — the same "family confirmed, cell not identified" pattern as
  the vol-regime family.
- **The economics do not move.** The effect is ~+0.008 R, comparable to (not additive
  with) the confirmed vol gate's +0.0137 R, and at the 30-min horizon that is ~0.2–0.3
  pip gross against the ~0.70 pip commission floor — still ~3× underwater.

## §1 Redundancy — partial, not full (Spearman among traded |z|≥1.5 rows)

| pair | adx_z~vei_atr_z | adx_z~rv30_pct | adx_z~ker_z | P(high-adx\|vol) | marginal |
|---|---|---|---|---|---|
| EURUSD | +0.284 | +0.184 | +0.622 | 0.464 | 0.355 |
| GBPUSD | +0.245 | +0.150 | +0.616 | 0.444 | 0.352 |
| AUDUSD | +0.242 | +0.143 | +0.628 | 0.452 | 0.360 |
| NZDUSD | +0.196 | +0.095 | +0.613 | 0.420 | 0.349 |

ADX carries some volatility (+0.15–0.28 with the vol-gate features) but is far from a
restatement of it (not ~0.9). It is more related to KER (+0.62), and KER is the weaker
carrier — consistent with directional STRUCTURE, not path efficiency, doing the work.

## §2 Stack (frontier-excess, delay 1) — the fragility

| pair | vol_gate | high_adx20 | AND | stack−vol | stack−adx |
|---|---|---|---|---|---|
| EURUSD | +0.0014 | +0.0066 | +0.0093 | **+0.0080** | +0.0027 |
| GBPUSD | +0.0116 | +0.0071 | +0.0120 | +0.0004 | +0.0049 |
| AUDUSD | +0.0136 | +0.0153 | +0.0063 | **−0.0073** | −0.0090 |
| NZDUSD | +0.0181 | +0.0052 | +0.0373 | **+0.0191** | +0.0320 |

On AUD, high_adx ALONE (+0.0153) beats both vol_gate and the AND — the conjunction is
destructive there. NZD's AND (+0.0373, only 1311/yr) is suspiciously large on a thin
cell. Not a robust conjunction.

## §3 Within-vol conditional (delay 1) — the decisive, clean test, 4/4

| pair | adx_hi meanR / pips / unit | adx_lo meanR / pips / unit | hi−lo R |
|---|---|---|---|
| EURUSD | +0.0323 / +0.272 / 8.43 | +0.0238 / +0.214 / 8.97 | +0.0084 |
| GBPUSD | +0.0305 / +0.255 / 8.34 | +0.0236 / +0.213 / 9.02 | +0.0069 |
| AUDUSD | +0.0269 / +0.222 / 8.26 | +0.0189 / +0.120 / 6.35 | +0.0080 |
| NZDUSD | +0.0401 / +0.328 / 8.17 | +0.0305 / +0.220 / 7.23 | +0.0096 |

**Risk-unit guardrail (rule 19) splits the panel:** on EUR/GBP the high-ADX half has a
*lower* risk unit than the low-ADX half (8.4 vs 9.0), so its higher mean R is NOT bought
by selecting bigger-σ states — clean, vol-independent evidence. On AUD/NZD the high-ADX
half has a *higher* risk unit (8.3 vs 6.4; 8.2 vs 7.2), so part of that hi−lo gap IS
residual volatility. The relationship is genuine on the majors and partly vol-confounded
on the carry pairs — the opposite split from where the null/stack were strongest.

## §4 Selection-corrected null (real MAX over the whole efficiency search vs null MAX)

| pair | real max (argmax) | null max mean ± sd | p95 | frac ≥ real | verdict |
|---|---|---|---|---|---|
| EURUSD | +0.0084 (high_adx_z 10) | +0.0033 ± 0.0030 | +0.0089 | 0.070 | FAIL |
| GBPUSD | +0.0180 (high_adx_z 10) | +0.0094 ± 0.0025 | +0.0136 | 0.010 | PASS |
| AUDUSD | +0.0153 (high_adx_z 20) | +0.0067 ± 0.0032 | +0.0119 | 0.000 | PASS |
| NZDUSD | +0.0205 (low_ker_raw 10) | +0.0052 ± 0.0027 | +0.0104 | 0.000 | PASS |

The null centres well above zero (frontier baseline is informative), exactly as expected.
High-ADX itself clears it on GBP/AUD; EUR fails; NZD's pass is a KER arm. So the null
supports "the efficiency family carries information beyond selectivity" on 3/4 pairs, and
"high-ADX specifically" on 2/4.

## Guardrails / invariants

- Null invariants (§0) all PASS on 4/4 pairs: feature marginals preserved exactly, joint
  dependence (adx_z,ker_z) preserved, high-ADX firing rate preserved to <0.5pp, z trigger
  untouched.
- Coverage (rule 9a): adx_z defined on 1.000 of base signals for EUR/GBP/AUD; 0.974/0.993
  for NZD (thin late-session minutes).
- mean R beside pips and the implied risk unit reported on every arm.

## Bottom line

The reversed direction is a **genuine conditioning relationship** — directional strength
raises reversion quality, cleanly so on the majors (within-vol 4/4, vol-independent on
EUR/GBP by the risk-unit test). It is **not** a robust independent deployment lever: it
does not stack as a conjunction on 2/4 pairs, fails the null on EURUSD, its best cell is
pair-specific, and its magnitude leaves the economics unchanged (still ~3× below the
commission floor). **Not adopted; not a holdout candidate.** Logged as a confirmed
mechanism result and negative-for-deployment evidence (rule 25).

## Files

`RSI_ADX_REVERSAL_SPEC.md`, `_run_rsi_adx_reversal.py`, `rsi_adx_reversal_results.json` /
`rsi_adx_reversal_draws.csv`. Reuses `_efficiency_features.py` and the confirmed engine.
