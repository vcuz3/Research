# Trigger redundancy and the regime-filter matrix — event clock, compulsory stop

Frozen specification: `RSI_Z_REGIME_MATRIX_SPEC.md`, written before the run, including
the pre-measured `Spearman(z, RSI14) = 0.9684` prior. Script
`_run_rsi_z_regime_matrix.py` on the `_rsi_stop_engine.py` engine. 2024+ never opened.

## Verdict

| Question | Answer |
|---|---|
| **Is RSI anything more than a deeper `z`?** | **No.** All five RSI thresholds sit on the `|z|` frontier (excess −0.0024 to +0.0018 R). **Requiring both is mildly *worse* than a matched-rate deeper `z`** (−0.0010 to −0.0043 R, 0-1 of 4 pairs). |
| **Were the project's regime survivors all applied?** | **No — one of three.** `RSI_COHERENCE_TIMEEXIT_REPORT.md` used only the ATR expansion gate; the RV-percentile family had never been run on an event clock. |
| **Does any regime filter beat pure selectivity?** | **One arm, weakly: ATR expansion top-40% AND RV(30) percentile top-40% together**, +0.0137 R excess, 3/4 pairs, surviving both a one-minute delay and the late era. **One pass out of 13 declared arms, so it is a candidate, not a result.** |

## The method: everything is scored against the `|z|` frontier

Every arm changes its own signal count, and this project has twice established that
depth alone raises profit per signal. So no arm is read at its own rate. The
`|z| >= k` sweep is the reference curve, and each arm is scored as

`excess = arm mean R − (frontier mean R, interpolated in log signals/year to that arm's own rate)`

An arm sitting **on** the curve added nothing but selectivity. All numbers are under the
compulsory stop (2.0 R, 1-pip slippage), event clock, non-overlapping, 30-minute hold.

### The reference frontier (median across the four pairs)

| `|z| ≥` | signals/yr | mean pips | mean R | risk unit | cluster t | hit |
|---:|---:|---:|---:|---:|---:|---:|
| 1.00 | 7,947 | 0.141 | 0.016 | 9.56 | 5.62 | 0.519 |
| 1.25 | 7,107 | 0.185 | 0.021 | 9.60 | 6.45 | 0.523 |
| **1.50** | 6,152 | 0.206 | 0.023 | 9.21 | 7.30 | 0.527 |
| 1.75 | 5,177 | 0.266 | 0.028 | 8.90 | 7.96 | 0.531 |
| 2.00 | 4,268 | 0.261 | 0.030 | 8.19 | 6.21 | 0.533 |
| 2.25 | 3,446 | 0.291 | 0.033 | 8.60 | 6.08 | 0.536 |
| 2.50 | 2,743 | 0.318 | 0.037 | 8.91 | 5.38 | 0.537 |
| 3.00 | 1,697 | 0.340 | 0.038 | 8.83 | 4.72 | 0.540 |

Monotone in depth, as on the fixed clock. Note the risk unit barely moves (8.2-9.6
pips), so this frontier is a genuine depth effect and not a volatility-selection
artefact.

---

## A. RSI on top of `z`: rejected — they are the same variable

Measured before the run on 4.21M EURUSD minutes:

- **`Spearman(z, RSI14) = 0.9684`**
- `P(z ≤ −1.5 | RSI ≤ 30) = 0.821`, `P(RSI ≤ 30 | z ≤ −1.5) = 0.430`
- **zero** minutes where the two disagree on direction

RSI extremes are close to a *subset* of `z` extremes: a stricter cut on the same
quantity, not a second opinion.

| Arm | signals/yr | mean R | frontier at that rate | **excess** | pairs ≥ +0.005 |
|---|---:|---:|---:|---:|---:|
| rsi 15/85 | 429 | 0.0392 | 0.0380 | +0.0012 | 1/4 |
| rsi 20/80 | 1,039 | 0.0335 | 0.0380 | +0.0002 | 2/4 |
| rsi 25/75 | 2,560 | 0.0328 | 0.0364 | +0.0018 | 0/4 |
| rsi 30/70 | 4,813 | 0.0255 | 0.0285 | −0.0018 | 1/4 |
| rsi 35/65 | 7,169 | 0.0191 | 0.0204 | −0.0024 | 0/4 |
| **z 1.5 AND rsi 30/70** | 4,077 | 0.0288 | 0.0309 | **−0.0025** | 0/4 |
| **z 1.5 AND rsi 25/75** | 2,254 | 0.0353 | 0.0358 | **−0.0043** | 1/4 |
| **z 2.0 AND rsi 30/70** | 3,306 | 0.0323 | 0.0338 | −0.0010 | 0/4 |

**All eight are on the frontier, and every conjunction is on the wrong side of it.**
Per pair, `z 1.5 AND rsi 30/70` is −0.0061 (AUDUSD), +0.0021 (EURUSD), +0.0011
(GBPUSD), −0.0080 (NZDUSD).

The reason the conjunction is slightly *negative* rather than merely neutral is worth
stating: since RSI extremes are largely nested inside `z` extremes, "both" mostly
reproduces the RSI cut — but it reaches that selectivity by an indirect route that
discards some deep-`z` signals RSI happened not to flag, and those are not worse than
average. You pay the selectivity cost without getting the full selectivity benefit.

**Conclusion: do not stack RSI on `z`. Pick one and set its depth on the frontier.** If
you want fewer, better signals, move the `z` threshold — it is one parameter, it is
monotone, and it dominates the conjunction at every matched rate tested.

*(This is consistent with, and sharpens, the project's existing record that RSI is
largely a renormalised trailing return, and the CME FX finding that RSI(14) "IS the
trailing return re-normalised".)*

---

## B. The regime filters — one of three had been applied

`RSI_COHERENCE_TIMEEXIT_REPORT.md` ran only the **ATR(14)/ATR(50) same-slot expansion
gate**. The two RV-percentile survivors from `RSI_RV_CLOCK_REGIME_REPORT.md`
(`rv_30m_pct_90d`, `rv_5m_pct_90d`) — which had passed their own frozen clock-and-delay
kill test — had never been run on an event clock, and no combination had been tried.

All gate cutpoints fitted on the early era only:

| Arm | signals/yr | mean pips | mean R | **excess** | pairs ≥ +0.005 | delay 1 | late era | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| + ATR expansion 40% | 4,523 | 0.278 | 0.0369 | +0.0042 | 2/4 | +0.0038 | +0.0077 | dial |
| + RV(30) pct 40% | 3,337 | 0.340 | 0.0408 | +0.0061 | 2/4 | +0.0082 | +0.0009 | dial |
| + RV(30) pct 20% | 1,955 | 0.385 | 0.0367 | +0.0037 | 2/4 | +0.0048 | −0.0018 | dial |
| + RV(5) pct 40% | 5,207 | 0.279 | 0.0363 | +0.0050 | 2/4 | +0.0045 | +0.0055 | dial |
| **+ ATR 40% AND RV(30) 40%** | **2,803** | **0.382** | **0.0451** | **+0.0137** | **3/4** | **+0.0126** | **+0.0079** | **SUPPORTED** |

Per-pair excess for the combined gate: AUDUSD **+0.0130**, EURUSD **−0.0002**, GBPUSD
**+0.0170**, NZDUSD **+0.0143**.

### Reading this honestly

**The individually-applied gates are all selectivity dials.** Each lands +0.004 to
+0.006 R above the frontier on 2 of 4 pairs — inside the ±0.005 band the spec declared
as "no effect". That includes the gate currently deployed. On its own, the ATR
expansion gate is not earning its place; it is a way of trading less.

**The combination is 3x either component and is the one arm that passes.** That is not
arithmetic: two dials that each add ~+0.005 do not compose to +0.0137. It is consistent
with this project's own earlier finding that volatility **acceleration** (ATR ratio) and
volatility **level** (RV percentile) are distinct, low-correlation conditioning
variables, so requiring both selects a state neither identifies alone.

Supporting detail:

- **The gain is not a risk-unit artefact.** The combined gate's implied risk unit is
  8.41 pips against 8.6-8.9 at the rate-matched point on the frontier — it selects
  *slightly smaller* typical moves while earning more per unit of risk. Per
  `LEARNINGS.md` 2026-08-04 that is the direction a real conditioner runs, not a fake
  one.
- **It survives the one-minute delay** (+0.0126, i.e. 92% retained) and the **late era**
  (+0.0079), the two checks that killed earlier components here.
- In absolute terms it roughly **doubles mean R against the plain `|z| ≥ 1.5` base**
  (0.045 against 0.023) at 2,803 signals/year instead of 6,152, and lifts mean pips from
  0.206 to 0.382.

### Why it is a candidate and not a result

- **It is one pass out of 13 declared arms.** The criterion is "median ≥ +0.005 R and
  ≥3/4 pairs"; under a null that is not a rare event to hit once in thirteen tries. This
  is a search, and it is labelled as one.
- **EURUSD is flat (−0.0002)** — the most liquid and most-studied pair in the panel is
  the one that does not participate. A 3/4 vote with the largest market abstaining is
  weaker than 3/4 suggests.
- **The four pairs are correlated tests**, closer to two effective observations.
- **No null was run** (rule 17). The frontier interpolation is a degenerate control, not
  a null; it cannot detect machinery bias the way a re-pairing or return-shuffle null
  can.
- The late-era cluster t is **1.46**, i.e. the recent third of the sample supports the
  direction but not significance on its own.

**Required before this is promoted:** a claim-matched null through the full pipeline,
and a demonstration that the combined gate's advantage is not reproduced by any single
same-rate own-pair statistic other than `|z|`.

---

## What this changes

| Claim | Status |
|---|---|
| RSI as an entry trigger | **Interchangeable with `z`**, `Spearman 0.968`. Keep one; the project's reports can continue to use RSI 30/70 as the reference signal, but it carries no information `z` lacks. |
| RSI stacked on top of `z` | **Rejected.** Negative excess at every matched rate tested. |
| ATR expansion gate as a standalone component | **Downgraded to a selectivity dial** (+0.0042 R, 2/4 pairs). It was the last survivor of the five-component system; on its own it no longer earns that status on an event clock. |
| RV-percentile regime family | Individually also dials on this clock (+0.005 to +0.006, 2/4). |
| **ATR expansion AND RV(30) percentile together** | **New leading candidate.** +0.0137 R over a matched-rate deeper `z`, 3/4 pairs, survives delay and era. Needs a null and an independent check. |

## Limitations

- Thirteen arms, one pass; treat as a screen (rule 26).
- No null (rule 17); the frontier is a degenerate control only.
- The spread is still unmeasured. The combined gate grosses 0.382 pip at 2,803
  trades/pair/year — roughly **+510 pips/pair/year at a 0.2 pip round trip and −331 at
  0.5 pip**. Better than the ungated base, still decided entirely by an unmeasured
  number.
- Late-era cluster t is 1.46 for the winning arm.
- Risk unit is trailing RV(30); the causal expected-slot unit was not re-run.

## Evidence

- Spec `RSI_Z_REGIME_MATRIX_SPEC.md` (frozen, including the pre-measured correlation).
- `_run_rsi_z_regime_matrix.py` → `rsi_z_regime_matrix_results.json`,
  `rsi_z_regime_matrix.csv`.
- Engine `_rsi_stop_engine.py`, checks `_test_rsi_stop_engine.py` (17 passing).
- Reproduce with `python -u _run_rsi_z_regime_matrix.py` from `forex/exploration_1`.
