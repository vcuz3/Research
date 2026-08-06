# RSI/z fade — Hurst-exponent regime conditioner (REPORT)

Run 2026-08-05. Frozen spec: `RSI_HURST_GATE_SPEC.md`. Screen on consumed history
(2012–2023); 2024+ sealed and NOT opened. Engine identical to the confirmed regime
matrix (event clock, non-overlap, 2R stop, 1-pip slippage, 30-min horizon); only the
gate moves. Reproduce: `python -u _run_rsi_hurst_gate.py`.

## Verdict — NO-GO under the frozen spec; direction reproduces the ADX axis but adds nothing

No arm is cleanly SUPPORTED. The Hurst-regime gate is:

1. **Directionally consistent with the ADX result** — HIGH Hurst (persistent/trending)
   reverts better than LOW Hurst, on all three keeps (kill test §4). The reversed
   "directional structure helps reversion" effect reproduces on a third, independent
   estimator (Hurst, vs ADX and KER).
2. **Fragile to the entry clock — fails the preregistered "delay 0 does not contradict"
   clause.** The two positive arms at delay 1 (`high_hurst_z 20` +0.0138, `high_hurst_z
   40` +0.0073, both 3/4 pairs) flip NEGATIVE at delay 0 (−0.0033, −0.0007). The
   preregistered bar was breached, so both are "supported-but-fragile", not SUPPORTED.
   (ADX, by contrast, held +0.0021 at delay 0.)
3. **Redundant with the ADX/KER directional axis, not the volatility axis.** Redundancy
   preview, Spearman on traded |z|≥1.5 rows: `hurst_z ~ adx_z ≈ +0.47`, `~ ker_z ≈ +0.37`,
   but `~ vei_atr_z` only +0.11 and `~ rv30_pct` +0.06–0.09. Hurst is a partial restatement
   of the directional axis already tested (and found non-deployable), not new information.

Because the spec gates a step-2 null + full redundancy run on a CLEAN survivor and there
is none, no null was run. NO-GO logged (rule 25).

## §1 Redundancy preview (Spearman, traded |z|≥1.5 rows)

| pair | adx_z | ker_z | vei_atr_z | rv30_pct |
|---|---|---|---|---|
| EURUSD | +0.476 | +0.368 | +0.129 | +0.090 |
| GBPUSD | +0.475 | +0.373 | +0.116 | +0.066 |
| AUDUSD | +0.474 | +0.374 | +0.111 | +0.059 |
| NZDUSD | +0.470 | +0.372 | +0.105 | +0.010 |

## §3 Gate arms, excess over the |z| frontier at matched rate (delay 1, median)

| arm | signals/yr | gross pips | mean R | excess R | risk unit | cluster t |
|---|---|---|---|---|---|---|
| high_hurst_z 20 | 1340 | 0.242 | 0.0314 | **+0.0138** | 7.38 | 3.41 |
| high_hurst_z 10 | 780 | 0.166 | 0.0281 | +0.0085 | 5.62 | 1.64 |
| high_hurst_z 40 | 2578 | 0.192 | 0.0247 | +0.0073 | 8.32 | 4.22 |
| low_hurst_z 40 | 3331 | 0.074 | 0.0049 | −0.0149 | 9.56 | 1.86 |
| low_hurst_z 20 | 1943 | 0.011 | 0.0001 | −0.0171 | 31.09 | 0.13 |
| low_hurst_z 10 | 1150 | −0.032 | −0.0057 | −0.0252 | 6.67 | −0.44 |

LOW-Hurst gates are all worse than the frontier (the classical "reversion likes
anti-persistence" prior is falsified, same as the KER/ADX low side). Risk units are
at or below the frontier's ~9.5, so the high side is not a volatility selector — but that
only confirms it lives on the directional axis, which §1 shows is ADX.

## §5 Kill test per arm (delay 1 primary; delay 0 shown)

```
high_hurst_z 20   excess +0.0138 R  3/4 | delay0 -0.0033  -> supported-but-fragile
high_hurst_z 40   excess +0.0073 R  3/4 | delay0 -0.0007  -> supported-but-fragile
high_hurst_z 10   excess +0.0085 R  2/4 | delay0 -0.0062  -> REJECTED (selectivity dial)
low_hurst_* (all)                        -> REJECTED (worse than frontier)
```

Per-pair (delay 1) the negative member on the high side is EURUSD (`high_hurst_z 20`:
EUR −0.0028), the usual weakest pair that inverts to momentum long-horizon.

## Guardrails

- **Coverage (rule 9a):** hurst_z defined on 0.974–0.977 of base signals for EUR/GBP/AUD;
  0.925/0.948 for NZD. The 120-bar window nulls the first ~136 min of each session, but
  base `z` already excludes the first 120 min, so the incremental deletion is the thin
  session-open sliver — uniform, not a hidden time-of-day filter.
- **Estimator landmine handled (LEARNINGS 2026-08-03):** Hurst is on a FIXED trailing
  window (constant sampling dispersion) and same-slot z-scored, so a fixed cut on hurst_z
  is not the growing-window time-of-day selector that afflicts `noise_vwap`'s Hurst gate.
- **Feature tests:** `_test_hurst_feature.py` 7/7 (H=1 on a ramp, ~0.5 on a random walk,
  ~0 on an iid level, >0.5 drift-dominated, causal, NaN across a gap and before the window
  fills).

## Bottom line

Hurst is a genuine third confirmation of the *direction* (persistence/trending → better
reversion) but is **not adopted**: it fails the preregistered delay-robustness bar, is
+0.47 correlated with the ADX axis that already failed the deployment test, and its
economics are the same sub-commission-floor size as everything else on this axis. NO-GO,
negative-for-deployment evidence preserved (rule 25).

## Files

`RSI_HURST_GATE_SPEC.md`, `_hurst_feature.py` (+ `_test_hurst_feature.py`),
`_run_rsi_hurst_gate.py`, `rsi_hurst_gate_results.json` / `.csv`.
