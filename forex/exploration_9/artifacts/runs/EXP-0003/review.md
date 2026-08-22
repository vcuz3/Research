# EXP-0003 Results Discussion

- Hypothesis: `HYP-0001` — Run-length reversion is a grind-vs-lunge concentration effect, not magnitude
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: unconditional fold cl-t + signflip p; joint count/disp cl-t, per era
- Kill test: (a) reversion mean-fold not distinguishable from the signflip null (real ≤ null p > 0.05) ⇒ KILL; (b) displacement subsumes count/max-share in the causal joint regression ⇒ the "persistence, not magnitude" claim is KILLED and it reduces to ordinary magnitude reversion.

## Result versus hypothesis

Direct answer to "what reversion signal is significant in full AND recent era."
Metric: the UNCONDITIONAL fold (fade a same-direction 5m run, unweighted) with a
signflip null, plus the joint count-vs-displacement horse race, split into
FULL (2011-2026) and RECENT (2020-2026). See `era_reversion_table.txt`.

## Gross, net, baseline, and null comparison

- **Unconditional fold — the only survivor.** Significant in BOTH eras on ALL
  four pairs. RECENT: EUR +0.055 pip cl-t=+4.1, GBP +0.059 t=+3.6, AUD +0.073
  t=+4.0, NZD +0.059 t=+3.2 — every one at signflip p=0.005. Recent amplitude is
  ~half the full-sample (~0.10-0.12 pip) but unambiguously alive.
- **Both conditioners die post-2020.** In RECENT the joint horse race is
  insignificant on every pair: count t = −0.4 / +0.1 / −0.3 / +0.2; displacement
  t = −1.6 / −1.4 / −1.2 / −1.4 (right sign, sub-threshold). The full-sample
  conditioner edges — concentration on EUR/GBP (count t=−5.3/−2.6) and magnitude
  on AUD/NZD (disp t=−3.9/−5.7) — are ENTIRELY pre-2020.

## Regimes, sensitivity, and alternative explanations

- Consistent with EXP-0002's per-year decay; this run localises it: it is not
  just EUR/GBP concentration that faded, AUD/NZD magnitude faded too. The pooled
  full-sample conditioner significance is dominated by 2011-2019.
- The base reversion halving (≈0.11→≈0.06 pip) is itself an amplitude-decay
  signal — the phenomenon is weakening but not gone. Still sub-cost (reopen
  spread ~fractions of a pip to a pip), consistent with the stated "signal for
  another strategy, not standalone" framing.

## Artifact and implementation risks

- Same controls as EXP-0001/0002 (causal vol-norm, session clustering, µs-safe
  targets, signflip null shared across eras within a pair). Unconditional-fold
  cl-t computed as the clustered t of the mean (regress fold on a constant).
- RECENT n≈200k per pair, G≈1698 sessions — well powered; the conditioner
  nulls are true nulls, not low-power failures.

## Builder interpretation

The deployable takeaway: **the reversion signal to feed another strategy is the
unconditional fold of a same-direction 5m run in the Frankfurt→NY window** —
robust across all four pairs and still significant post-2020, though at ~half
amplitude. Do NOT weight it by run-length/concentration or by displacement
magnitude for live use: both refinements are dead since 2020 on every pair and
would add parameters with no recent edge. HYP-0001's concentration mechanism is
now firmly a historical (pre-2020, EUR/GBP) feature.

## Independent review

- Review status: builder-complete; independent replication recommended
- Objections: pending
- Verdict: Deployable reversion signal = the UNCONDITIONAL fold (all pairs, full
  + recent, p=0.005). Both conditioners dead post-2020 — do not use them live.

## Promotion decision

- `reports/FINDINGS.md`: pending
- `MEMORY.md`: pending; update only if durable state changes
- Shared `LEARNINGS.md`: not eligible without cross-project verification
