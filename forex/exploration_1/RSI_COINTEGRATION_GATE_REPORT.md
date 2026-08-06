# RSI/z fade — cross-pair cointegration / divergence conditioner (REPORT)

Runs 2026-08-05. Frozen spec: `RSI_COINTEGRATION_GATE_SPEC.md`. Screen
(`_run_rsi_cointegration_gate.py`) + step-2 selection-corrected null and redundancy
(`_run_rsi_cointegration_null.py`). Consumed history (2012–2023); 2024+ sealed. Engine
identical to the confirmed regime matrix (event clock, non-overlap, 2R stop, 1-pip
slippage, 30-min horizon). Partners: EUR↔GBP, AUD↔NZD.

## Verdict — NO-GO under the frozen spec (null 2/4), but the most independent conditioner found

The screen found `diverge_hi` SUPPORTED (fade P better when the partner DIVERGES / does not
confirm), delay-0-positive, both blocks agreeing. Step 2 splits it:

- **Independence PASSES cleanly** — this is the ONLY conditioner in the search that is not a
  restatement of the `|z|`, volatility, or directional axes. Built purely from the partner,
  it is orthogonal to (even mildly anti-correlated with) P's own vol/directional state,
  stacks on the vol gate on 3/4 pairs, and out-reverts "confirm" within the vol-gate
  population on 4/4 pairs.
- **Selection-corrected null FAILS the 3/4 bar (2/4)** — the effect is decisively real on
  ONE leg of each cointegrated block and largely selection on the other.

Per rule 26 the preregistered bar (≥3/4) is not met and is not flipped post hoc. **Not
adopted; not a holdout candidate.** Recorded as negative-for-deployment evidence (rule 25).

## Screen — the divergence direction is clean and monotone (delay 1, median excess R)

| keep | diverge_hi | diverge_lo (mirror) | verdict |
|---|---|---|---|
| 40% | −0.0015 | −0.0100 | diverge helps |
| 20% | +0.0083 | −0.0156 | diverge helps |
| 10% | +0.0140 | −0.0227 | diverge helps |

`diverge_hi 10` and `20`, and `partner_calm 10/20`, all cleared the screen's SUPPORTED bar
(median ≥ +0.005 R, ≥3/4 pairs, delay 0 positive: `diverge_hi 10` delay0 +0.0056). Risk
unit 7.18 vs frontier ~9.5 (below → NOT a volatility selector, rule 19). This was the first
survivor of the entire conditioner search to pass the delay-robustness bar.

## Step 2 §1 — redundancy: genuinely orthogonal (Spearman on traded rows)

| pair | xalign~vei_atr_z | ~rv30_pct | ~adx_z | P(diverge\|vol) | marginal |
|---|---|---|---|---|---|
| EURUSD | −0.147 | −0.129 | −0.100 | 0.074 | 0.087 |
| GBPUSD | −0.105 | −0.062 | −0.074 | 0.092 | 0.086 |
| AUDUSD | −0.170 | −0.143 | −0.111 | 0.063 | 0.077 |
| NZDUSD | −0.170 | −0.120 | −0.089 | 0.070 | 0.078 |

Unlike KER/ADX/Hurst (all +0.4–0.6 with each other), the cross-pair divergence is
*negatively* correlated with the own-pair vol/directional axis — a different dimension.

## Step 2 §2–3 — stacks on and is independent of the vol gate

Stack (excess of `vol_gate AND diverge` minus `vol_gate`), delay 1: EUR **+0.0181**, AUD
**+0.0254**, NZD **+0.0141**, GBP −0.0026 → **3/4**. Within-vol split (diverge vs confirm
among vol-gate signals, matched risk unit): EUR +0.0105, GBP +0.0180, AUD +0.0040, NZD
+0.0025 → **4/4**. So divergence adds information *on top of* volatility.

## Step 2 §4 — selection-corrected null (real MAX vs null MAX, within-(slot,era,side) donors)

| pair | real max (argmax) | null max mean ± sd | frac ≥ real | verdict |
|---|---|---|---|---|
| EURUSD | +0.0159 (diverge_hi 10) | +0.0039 ± 0.0029 | 0.000 | **PASS** |
| NZDUSD | +0.0302 (diverge_hi 10) | +0.0030 ± 0.0040 | 0.000 | **PASS** |
| GBPUSD | +0.0121 (diverge_hi 10) | +0.0092 ± 0.0023 | 0.100 | FAIL |
| AUDUSD | +0.0115 (diverge_hi 20) | +0.0075 ± 0.0041 | 0.130 | FAIL |

Block-structured: one leg of each cointegrated block passes decisively (real 4–10× the null
mean, frac 0.000); the other fails because its null-max mean is high (+0.008–0.009), i.e.
random partner re-pairing manufactures most of its apparent excess. The failures sit at the
~87–90th null percentile — real-ish but short of p≤0.05. Invariant checks all PASS
(partner signal-row marginal preserved, z trigger untouched, firing rate preserved).

## Method note (reusable) — a side-folded feature must be permuted WITHIN side

The first null run FAILED its own firing-rate invariant on 4/4 pairs. Cause: `xalign =
side · z_partner`; permuting `z_partner` across all signals in a (slot, era) cell moves a
long-signal partner value onto a short signal, flipping its sign and scrambling the xalign
marginal and firing rate — and distorting the null-max means. The fix is to permute within
(slot, era, **side**). The in-code invariant caught the mis-specification before it was
interpreted (RULES 17). The corrected null did not change the 2/4 verdict, but its null-max
means were the trustworthy ones.

## Economics — unchanged

Best arm `diverge_hi 10` gross ~0.24 pip; even the vol-stacked within-vol diverge cells top
out at ~0.18–0.37 pip (GBP highest), still below the ~0.70 pip commission floor. A real,
orthogonal conditioner, but not enough to cross the floor even stacked.

## Bottom line

The strongest and most independent conditioner of the search: cross-pair divergence carries
real, vol-orthogonal reversion information, decisively on EURUSD and NZDUSD. But it fails the
preregistered 3/4 null bar (GBPUSD, AUDUSD within selection), and the economics stay below
the cost floor. **NO-GO**, negative evidence preserved. The conditioner search is now
exhausted across three axes (directional structure — redundant; cross-pair coherence — dead;
cross-pair divergence — orthogonal but null-fragile); the open question moves to Workstream C
(the account/challenge simulator).

## Files

`RSI_COINTEGRATION_GATE_SPEC.md`, `_run_rsi_cointegration_gate.py`,
`_run_rsi_cointegration_null.py`, `rsi_cointegration_gate_results.json` / `.csv`,
`rsi_cointegration_null_results.json` / `_draws.csv`.
