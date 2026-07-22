# EXP-0027 — HYP-0018 Hurst-conditioned partial-take-profit

- Hypothesis: `experiments/hypotheses/HYP-0018.md`
- Builder: Claude (Opus 4.8), 2026-07-22
- Baseline: continuous-stop NQ/ES baseline (noise_bands lb90, RTH, 30-min clock,
  VWAP gate, every-bar band/VWAP stop, next-open fills, per-instrument costs).
- Code: `scripts/hyp_0018_hurst_exit.py`; default-off `tp_gate` on `core/engine2.py`.
- Reproduce:
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0018_hurst_exit real {NQ|ES}`
- Artifacts: `conditional_{NQ,ES}.csv`, `mirror_{NQ,ES}.csv`, `verdict_{NQ,ES}.json`.

## What was tested

Follow-on from EXP-0026: the Hurst LEVEL is an established, cross-market, per-trade
CONTINUATION signal that did not monetize as an entry GATE (gating cuts exposure).
This applies the SAME causal session-to-date entry-bar Hurst where it costs no
exposure — the EXIT horizon. Entries and the trade population are UNCHANGED (4209
NQ / 4326 ES trades in every cell). Only the `tp1.0_50` partial take-profit (bank
50% at +1 ATR, runner trails — the project's one Null-C-surviving exit tweak) is
modulated per trade: for threshold T, a trade with entry-H ≤ T banks the partial
(CONDITIONAL, "bank chop"); H > T holds the runner. Sweep T over {0.35..0.65}. The
endpoints recover the two unconditional references (no-tp = continuous-stop
baseline; all-tp = unconditional tp1.0_50). A MIRROR control banks the HIGH-H
trades (H ≥ T) — the mechanism predicts the mirror is worse.

Implemented via a new default-off `tp_gate` on `core.engine2` (parity verified:
`tp_gate=None` and `tp_gate`=all-entry-keys both reproduce unconditional tp1.0_50
bit-exact; empty gate reproduces no-tp bit-exact).

## Result versus hypothesis — REJECT on both, mechanism INVERTED

| market | no-tp Sh | all-tp Sh | best CONDITIONAL (bank chop) | cond uplift vs all-tp | best MIRROR (bank trend) |
|---|---|---|---|---|---|
| NQ | 1.288 | 1.344 | 1.332 (T=0.65) | **−0.012** | 1.354 |
| ES | 0.698 | 0.687 | 0.710 (T=0.40) | +0.023 | 0.723 |

Real gate (dSharpe ≥ +0.10 vs no-tp AND netR ≥ base AND Sharpe > BOTH references)
**REJECTS on both markets**. Per the standing rule, no Null-C spent.

Three decisive reads:

1. **Conditioning adds ~nothing.** The best conditional cell's uplift over
   unconditional tp1.0_50 is −0.012 (NQ) / +0.023 (ES) Sharpe — noise-level and
   below the +0.10 gate. Where does H put its "bank" mass? At the useful (high-T)
   thresholds the conditional banks ~95% of trades anyway (NQ T=0.65 banked_frac
   0.975), i.e. it collapses back to all-tp. The tp partial's mean-reversion
   capture is NOT Hurst-selective — the +1 ATR give-back happens regardless of the
   entry-bar persistence regime. (This is exactly the failure mode flagged as the
   main risk in HYP-0018.)

2. **The intended direction is mildly HARMFUL and the MIRROR is better — on BOTH
   markets.** Banking the LOW-H (chop) trades and holding the HIGH-H runner (the
   mechanism) is worse than banking the HIGH-H trades: NQ mirror-best 1.354 >
   conditional-best 1.332; ES mirror-best 0.723 > conditional-best 0.710. The
   asymmetry the hypothesis predicted appears with the OPPOSITE sign, and it
   transfers to ES — so it is a (tiny) real property of the tape, not NQ noise. The
   persistence at ENTRY does not predict whether THIS trade's post-extension
   give-back is worth banking vs holding; if anything, trending-session trades that
   reach +1 ATR are slightly better to bank (local overshoot before trend resumes).

3. **The tp overlay itself does not even transfer cleanly.** all-tp beats no-tp on
   NQ (+0.056 Sharpe, the known tp1.0_50 result) but HURTS on ES (0.687 < 0.698) —
   consistent with tp1.0_50 being an NQ-validated, ES-weaker overlay. So there is
   no robust exit surface for H to improve.

## Regimes, sensitivity, alternative explanations

- The conditional Sharpe surface is flat and non-monotone in T on both markets
  (NQ 1.276→1.332, ES 0.694→0.710) — no stable interior optimum, no dose-response.
  Expected net-R/trade is essentially constant (~0.021 NQ, ~0.012 ES) across the
  whole sweep, confirming the exit conditioning moves almost no P&L.
- max drawdown is unchanged by conditioning (NQ ~4.34–4.70R, ES ~7.0–7.7R).
- Consistent with the project's finding that the band+VWAP+continuous-stop
  machinery is already efficient, and with EXP-0026: the Hurst signal is real as an
  entry-QUALITY tag but does not translate into either selection alpha (EXP-0026)
  or exit-management value (this run). The exit lever for Hurst is exhausted.

## Artifact and implementation risks

- Causality: entry Hurst uses only closes ≤ the decision bar; partial fills
  next-open; `tp_gate` keys are (date, entry_mfo = decision_mfo+1).
- Trade population identical across all cells (n constant) — this is a pure
  MANAGEMENT test, not selection, so there is no exposure/turnover confound.
- Engine parity asserted in-script (`assert_parity`) and independently smoke-tested
  (tp_gate=None == all-tp; empty gate == no-tp, bit-exact).

## Builder interpretation

The EXP-0026 insight — persistence is a real per-trade continuation signal, apply
it where it costs no exposure — was a sound idea and the cleanest remaining lever,
but it does not pay off: entry-bar persistence does not predict the exit horizon.
The partial-TP's edge (post-+1ATR mean-reversion) is orthogonal to session-to-date
Hurst, so conditioning on H collapses to the unconditional tp and the intended
"bank chop / hold trend" split is marginally counterproductive on both markets.
Combined with EXP-0026, the Hurst exponent is a real but non-monetizable signal in
this system: it improves neither trade selection nor trade management. Retain the
unconditioned baseline; the `tp1.0_50` overlay stays as-is (NQ default-off,
paper-forward). Keep the new `tp_gate` as tested, default-off machinery.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: pending
- `MEMORY.md`: updated (HYP-0018 rejected; Hurst exit lever exhausted)
- Shared `LEARNINGS.md`: not eligible without cross-project verification
