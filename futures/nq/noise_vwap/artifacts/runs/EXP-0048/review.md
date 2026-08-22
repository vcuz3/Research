# EXP-0048 review — HYP-0036 entry confirmation-depth gate

- Builder: Claude (Opus 4.8), 2026-08-16
- Reviewer: unassigned
- Verdict: **NO-GO** (both markets)
- Reproduce: `python -u -m futures.nq.noise_vwap.scripts.hyp_0036_confirm_depth NQ`
  (select+NQ TEST), `... ES 0.1` (transfer). Null C `... null NQ 0.1 40` — NOT spent (gate rule).

## Hypothesis

Shallow breakouts (decision-bar close only barely beyond the noise band) fail to
follow through more often in the recent era (the 2026 NQ hit-rate collapse to
20.8%, below the ~23% geometric break-even). Requiring a deeper break —
`ext_atr >= k` ATR at the decision bar, applied through the audited `entry_gate`
path, `k=0` reproduces the baseline bit-exact — should select higher-follow-through
entries. Preregistered in `experiments/hypotheses/HYP-0036.md`.

Origin is a SEARCHED discovery (rule 26) from two 2026-08-16 diagnostics:
`diag_nonstationarity.py` (fade is a hit-rate/follow-through collapse, not signal
scarcity or winner shrinkage) and `sweep_entry_buffer.py` (per-trade net edge is
monotone in break depth). The standing prior is that this is a turnover lever, so
the decisive control is the matched-count random-drop null, not raw Sharpe.

## Result

### NQ TRAIN selection (first 60% of common sessions)
Baseline: n=2477, Sharpe 1.2676, netR 55.41.

| k | n | retain | gross pt/trd | exp netR/trd | Sharpe | dSharpe |
|---|---|--------|--------------|--------------|--------|---------|
| 0.00 | 2477 | 1.000 | 2.05 | 0.022 | 1.268 | 0.000 |
| 0.05 | 1792 | 0.724 | 2.69 | 0.032 | 1.328 | +0.061 |
| **0.10** | **1391** | **0.562** | **3.29** | **0.043** | **1.454** | **+0.186** |
| 0.15 | 1117 | 0.451 | 3.70 | 0.050 | 1.419 | +0.151 |
| 0.20 | 932 | 0.376 | 3.80 | 0.046 | 1.157 | −0.111 |
| 0.30 | 687 | 0.277 | 3.69 | 0.046 | 0.929 | −0.339 |
| 0.50 | 372 | 0.150 | 3.83 | 0.047 | 0.622 | −0.646 |

Per-trade quality rises monotonically with depth (gross 2.05 → 3.83) — the effect
is real. But Sharpe peaks at k=0.10 and collapses once the exposure floor is
breached; the retain≥0.50 selection floor forbade the degenerate high-per-trade,
tiny-exposure cells. Selected **k* = 0.10** (argmax TRAIN dSharpe with retain≥0.50).

### NQ TEST kill test (last 40%) — FAIL
Baseline: n=1732, Sharpe 1.3224, netR 35.78.
- k*=0.10: Sharpe 1.3224 → **1.3066 (dSharpe −0.016)**, netR 35.78 → 31.94 (**−3.84**),
  retain 0.558. **Real gate FAILS** (needs +0.10 and netR not fall).
- Matched-count random-drop null (keep 9571 of 12811 candidates, 200 draws): real
  dSharpe −0.016 vs null mean −0.097 (sd 0.116), **frac(random≥real) 0.210** — fails
  <0.05. Depth filtering is not distinguishable from randomly thinning the book.

### ES TEST transfer — FAIL
Baseline Sharpe 1.070. k*=0.10: **1.070 → 0.758 (dSharpe −0.312)**, netR 29.19 → 19.15,
retain 0.571; random-drop null **frac 0.905**. Sibling markets disagree in sign — the
project's standing mechanism-failure signal.

### Null C — NOT spent
Primary market fails the real gate and the random-drop null; per the gate rule the
expensive drift-preserving null is not spent (a real pass that misses the primary is
already a REJECT).

## Interpretation

Classic quality-not-alpha turnover lever, the same signature as Hurst (EXP-0026/0027/
0028), VEI (EXP-0035/0036), gap/RVOL (EXP-0016/0024), NQ↔ES confirmation (EXP-0018),
and percentile-momentum (EXP-0030): per-trade quality rises while exposure falls, and
the risk-adjusted uplift either does not survive out of era or does not beat a random
drop of equal size. Here it fails both — the TRAIN Sharpe uplift (+0.186) is in-sample
only (TEST −0.016), and even the residual per-trade gain is indistinguishable from
random thinning (frac 0.21).

**Reconciliation with the earlier anticipatory sweep** (`sweep_entry_buffer.py`, which
showed TEST Sharpe rising with a positive entry buffer): that sweep ran `threshold`
(first-crossing) entry and scored against the `threshold buf=0` arm (Sharpe +0.771), a
book that over-fires (6807 TEST signals vs the clock's 1732). Raising the buffer there
climbed out of the over-firing hole toward — but never reaching — the deployed 30-min
clock book (+1.322). Against the correct deployed baseline (the clock book), and split
TRAIN/TEST, depth filtering adds nothing risk-adjusted. The per-trade "deeper earns
more" gradient is real and era-stable; the "deeper lifts Sharpe recently" reading was
an artifact of the weaker reference and in-sample fitting.

Retain the unconditioned continuous-stop baseline. No core engine change (gate lives in
`entry_gate`; k=0 parity asserted). Artifacts: `train_sweep_NQ.csv`,
`random_null_test_NQ.csv`, `random_null_test_ES.csv`, `verdict_NQ.json`.
