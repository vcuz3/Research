# Claim-matched null for the volatility-regime gate

Follow-up to `RSI_Z_REGIME_MATRIX_REPORT.md`, which left the combined gate
(ATR expansion top-40% **AND** RV(30) percentile top-40%) as an unverified screen:
one pass out of 13 arms, no null. Script `_run_rsi_gate_null.py`, 100 donor-matched
draws per pair. 2024+ never opened.

## Verdict

**The volatility-regime family is REAL — it clears a claim-matched, selection-corrected
null on 4 of 4 pairs.** But the specific combined gate is **not** the stable winner, and
one of the two reasons the earlier report was cautious turns out to have been the right
one for the wrong reason.

| Question | Answer |
|---|---|
| Does the regime family carry information, correcting for the 5-arm search? | **Yes.** Real maximum excess beats the null maximum on **4/4 pairs** (frac ≥ real = 0.010, 0.000, 0.000, 0.000). |
| Is the *combined* gate the right cell? | **No.** The best arm differs on **every** pair, and the combined gate is the argmax on only 1 of 4. |
| Is combining better than either component at the same rate? | **Yes, 4/4 pairs** — +0.0085 R over ATR alone, +0.0032 R over RV(30) alone. |
| Should it be deployed as specified? | **Promote the family, not the cell.** EURUSD is flat (−0.0002) and fails its own null (0.270). |

---

## The null, and what it is allowed to conclude

Within each **(session minute, era)** cell, the triple
`(vei_atr_z, rv30_pct, rv5_pct)` is permuted **jointly** across dates, on the full
minute grid — so a decision keeps its own price path and trigger but receives another
date's regime state.

**Preserves** — every price path and therefore every trade's P&L given its entry; the
`|z| ≥ 1.5` trigger and its depth; the event clock, the non-overlap rule, the compulsory
stop and its slippage; the exact marginal distribution of each feature within every
slot/era cell, hence the gate's firing rate; the joint dependence between the two gates
(they travel together); the same-slot seasonal structure.

**Destroys** — only the contemporaneous link between the regime state and *this*
decision's forward return. That is exactly the claim.

All four preservation claims are asserted in code before any draw is interpreted
(rule 17), and all pass on all four pairs:

| Check | Result |
|---|---|
| feature marginals preserved exactly (sorted values identical) | PASS ×4 |
| joint dependence between the two gates preserved (Spearman to 1e-9) | PASS ×4 |
| combined gate firing rate preserved to <0.5 pp | PASS ×4 |
| `|z|` trigger count untouched | PASS ×4 |

---

## Result 1 — the family clears the null decisively

Excess over the `|z|` frontier, real against 100 null draws:

| Arm | EURUSD | GBPUSD | AUDUSD | NZDUSD |
|---|---:|---:|---:|---:|
| ATR 40% | +0.0056 / **0.000** | +0.0139 / **0.000** | +0.0008 / **0.000** | +0.0028 / **0.000** |
| RV(30) 40% | −0.0006 / 0.010 | +0.0204 / **0.000** | +0.0033 / **0.000** | +0.0090 / **0.000** |
| RV(5) 40% | +0.0011 / **0.000** | +0.0073 / **0.000** | +0.0026 / **0.000** | +0.0109 / **0.000** |
| RV(30) 20% | −0.0109 / 0.970 | +0.0057 / 0.050 | +0.0018 / **0.000** | +0.0219 / **0.000** |
| **ATR 40% + RV(30) 40%** | −0.0002 / 0.270 | +0.0170 / **0.000** | +0.0130 / **0.000** | +0.0143 / **0.000** |

*(real excess / fraction of null draws ≥ real)*

**Selection-corrected**, comparing each pair's real *maximum* over the five-arm search
against the null distribution of maxima:

| Pair | real max | arm | null max mean | null max sd | null max p95 | frac ≥ real |
|---|---:|---|---:|---:|---:|---:|
| EURUSD | +0.0056 | ATR40 | −0.0012 | 0.0032 | +0.0038 | **0.010** |
| GBPUSD | +0.0204 | rv30_40 | +0.0033 | 0.0024 | +0.0070 | **0.000** |
| AUDUSD | +0.0130 | ATR40+rv30_40 | −0.0046 | 0.0021 | −0.0011 | **0.000** |
| NZDUSD | +0.0219 | rv30_20 | −0.0030 | 0.0022 | +0.0004 | **0.000** |

**4/4 pairs clear p ≤ 0.05 after correcting for the search.** The "1 pass out of 13
arms" concern from the previous report is answered: the effect survives its own
selection.

### The methodological catch, and it must be stated with the pass

**The null does not centre at zero — it centres NEGATIVE**, from −0.0012 to −0.0130
depending on pair and arm. That is not a defect; it is what the statistic means. The
baseline being subtracted (the `|z|` frontier) is itself an *informative* selection —
deepening `z` genuinely improves profit per trade — so a **random** gate at the same
trade count lands *below* the frontier by construction, because it keeps the shallow
`z = 1.5` signal mix while being compared against a deeper cell.

Two different bars follow, and both must be read:

- **"Beats the null" = the gate carries real information** (versus a random gate at the
  same rate). Passed everywhere except EURUSD's combined and RV(30) 20% cells.
- **"Excess > 0" = the gate beats the cheaper alternative of just deepening `z`.** This
  is the bar that matters for deployment, and it is the harder one.

Reporting only the null p-value here would have overstated the result by roughly the
width of the null's offset — around 0.010 R, which is most of the effect. This extends
the standing workspace instruction to read the null's *centre*, not only its tail.

---

## Result 2 — combining beats either component at its own rate, 4/4

The previous report's required control: tighten each single gate until it fires at the
combined gate's own rate (~2,800/yr), so "is it the combination, or just that rate?" is
answered directly.

| Pair | combined | ATR alone @ same rate | RV(30) alone @ same rate |
|---|---:|---:|---:|
| EURUSD | −0.0002 (0.0386 R) | −0.0078 (0.0307) | −0.0034 (0.0354) |
| GBPUSD | +0.0170 (0.0515) | +0.0073 (0.0416) | +0.0137 (0.0481) |
| AUDUSD | +0.0130 (0.0356) | +0.0085 (0.0317) | +0.0029 (0.0257) |
| NZDUSD | +0.0143 (0.0527) | +0.0049 (0.0432) | +0.0118 (0.0502) |

- combined − same-rate ATR: median **+0.0085 R, 4/4 pairs**
- combined − same-rate RV(30): median **+0.0032 R, 4/4 pairs**

**Requiring both volatility acceleration and a high volatility level is genuinely better
than either at matched selectivity**, on every pair including EURUSD (where both single
gates are *more* negative than the combination). This is the strongest single piece of
evidence in the run, and it is consistent with the project's existing finding that
acceleration and level are distinct low-correlation conditioners.

---

## Result 3 — the specific cell is not stable, and that is the binding limitation

**The best arm is different on all four pairs:**

| Pair | argmax | excess |
|---|---|---:|
| EURUSD | ATR 40% | +0.0056 |
| GBPUSD | RV(30) 40% | +0.0204 |
| AUDUSD | ATR 40% + RV(30) 40% | +0.0130 |
| NZDUSD | RV(30) 20% | +0.0219 |

The combined gate is the winner on **one** of four. On EURUSD it is flat against the
frontier (−0.0002) and does not clear its own null (0.270). One arm is actively
wrong-signed (EURUSD RV(30) 20%, −0.0109, frac 0.970 — *worse* than random).

So the honest promotion is: **the volatility-regime family conditions this edge, and a
combined acceleration-plus-level gate is the best default because it wins the matched-rate
comparison on 4/4 — but the exact keep fractions are not identified by this evidence and
should not be tuned per pair.** Picking each pair's argmax would be fitting four
independent parameter choices on consumed history.

---

## What this changes

| Claim | Status |
|---|---|
| Volatility-regime gating carries real information | **Confirmed** against a claim-matched, selection-corrected null, 4/4 pairs. Upgraded from screen. |
| The single gates are "selectivity dials" (previous report) | **Partly retracted.** They are weak *against the frontier* (+0.004 to +0.006, 2/4) but decisively real *against a random gate*. The earlier wording conflated the two bars. |
| ATR expansion + RV(30) percentile as the deployed gate | **Promoted to default, with the parameterisation left loose.** Wins the matched-rate control 4/4; is the argmax on only 1/4. |
| EURUSD | **Weakest member on every regime arm.** Do not read panel medians without it. |

## Limitations

- 100 draws gives a p-floor of 0.01; three of four pairs report 0.000, i.e. below the
  resolution of the test.
- The four pairs are correlated tests, nearer two effective observations.
- The null re-pairs the regime features but cannot break the *mechanical* association
  between a feature and its own trailing window; a feature and its donor share the slot
  and era, which is deliberate (donor matching) but does bound how much is destroyed.
- Still no spread measurement. The combined gate grosses 0.382 pip at ~2,800
  trades/pair/year: about **+510 pips/pair/year at 0.2 pip round trip, −331 at 0.5 pip**.
  The null verifies the *signal*, not the *economics*.
- Late-era cluster t for the combined arm remains 1.46.

## Evidence

`_run_rsi_gate_null.py` → `rsi_gate_null_results.json`, `rsi_gate_null_draws.csv`.
Engine `_rsi_stop_engine.py`, checks `_test_rsi_stop_engine.py` (17 passing).
Reproduce with `python -u _run_rsi_gate_null.py` from `forex/exploration_1`.
