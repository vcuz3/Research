# EXP-0011 Results Discussion

- Hypothesis: `HYP-0008` — Frozen multi-horizon volatility state adds stable forward-30m volatility information beyond the causal same-slot median plus range_rv_15m core.
- Status: completed
- Builder: Codex
- Reviewer: unassigned
- Primary metric: Paired OOS delta Spearman IC on forward 30-minute realized volatility normalized by its causal same-slot median.
- Kill test: Both NQ and ES must have positive OOS delta IC with lower 90% session-block-bootstrap bound above zero, lower MAE and QLIKE, and positive yearly delta IC in at least 60% of OOS years.

## Result versus hypothesis

The incremental hypothesis passed every predeclared OOS gate, but the candidate is
not being adopted operationally because the improvement is too small to justify the
additional state and maintenance burden.

- Part A (through 2023-12-29): normalized-target IC rose from 0.8272 to 0.8464
  on NQ (delta +0.0192) and from 0.8248 to 0.8409 on ES (delta +0.0160).
- Part B (2024-01-01 through 2026-07-14): normalized-target IC rose from 0.8237
  to 0.8324 on NQ (delta +0.0088, 90% session-block CI [0.0055, 0.0124]) and
  from 0.8333 to 0.8428 on ES (delta +0.0095, CI [0.0064, 0.0133]).
- OOS yearly delta IC was positive in every measured year on both markets.
- OOS normalized MAE changed by -0.00592 NQ / -0.00841 ES and QLIKE by
  -0.00665 NQ / -0.00517 ES; lower is better for both losses.
- The raw-target sensitivity agreed: delta IC +0.0100 NQ / +0.0113 ES and MAE
  improved by 0.17592 / 0.18908 basis points.

## Gross, net, baseline, and null comparison

This is a forecasting experiment, not a trading backtest, so gross/net returns and
trading-cost nulls do not apply. The relevant baseline is the frozen two-input range
core: the causal 90-session same-slot target median plus `range_rv_15m`. The frozen
range-plus-multi model was evaluated as a paired incremental comparison on identical
observations.

## Regimes, sensitivity, and alternative explanations

The gain replicated on NQ and ES, in normalized and raw target formulations, and in
every OOS calendar-year slice. This makes the incremental information credible. The
OOS effect was nevertheless about half the Part-A effect, and its operational size is
small: roughly +0.009 IC and 0.18 bp lower raw MAE for six additional state variables.
NQ and ES are correlated markets, so their agreement is replication across instruments,
not two fully independent trials.

## Artifact and implementation risks

The notebook passed its causal-alignment, overlap/purge, boundary, and target-definition
audits before model evaluation. The exact evaluated notebook SHA-256 is
`ccb9f5e9243cad48e648e7bfaf5327f33823efe2dde2a50543607e8616e79606`.
The notebook remains mutable, so this review records the frozen result. The entire
2024-01-01 through 2026-07-14 interval is now consumed for this hypothesis; only later
observations are clean forward evidence.

## Builder interpretation

**Scientifically confirmed; operationally not adopted.** Use the causal same-slot
median plus `range_rv_15m` as the production specification. Keep the multi-horizon
candidate as a shadow benchmark only. Reconsider it only if future shadow results show
a materially larger and decision-relevant benefit.

## Independent review

- Reviewer: Claude
- Review date: 2026-07-31
- Review status: reviewed
- Verdict: **QUALIFIED-CONFIRMED** (downgraded from "confirmed"). The operational
  decision — adopt the two-input range core, do not adopt the six multi-horizon state
  variables — is upheld and is the right call. The *incremental* claim is not yet
  established at the strength recorded.

### Objections

1. **BLOCKING — the Part-A placebo does not centre at zero, and it was never rerun on
   Part B.** Cell 13: shuffling the target within (year, slot) still reproduces a
   candidate-minus-baseline delta of **+0.01008 NQ** [p05 +0.00749, p95 +0.01273] and
   **+0.00417 ES** [+0.00142, +0.00683], against observed Part-A deltas of +0.01920 /
   +0.01601. So 53% (NQ) / 26% (ES) of the in-sample improvement is reproduced by noise:
   the richer model aligns better with the year×slot GROUP LEVEL of the target, and
   pooled Spearman rewards that even when within-group alignment is destroyed. Part A
   still clears its own null. **Part B does not have one.** The confirmed OOS delta of
   +0.0088 NQ sits *inside* NQ's Part-A placebo band [+0.0075, +0.0127] and below its
   null mean of +0.0101. The fix is cheap and cannot be re-tuning: `oos_prediction_cache`
   already holds the frozen Part-B predictions, so `shuffled_target_placebo` can be run
   on them with no refit and no specification change. Until then the gate does not
   discriminate. Registered as backlog item 18.
2. Same root cause: the primary metric is a **pooled** Spearman across all slots and
   years (IC ~0.83), which is dominated by getting the volatility LEVEL ordering right.
   A within-(year, slot) IC should be the primary or at least a co-diagnostic.
   *Partly answered since:* EXP-0012 measured within-slot skill of the CORE against the
   same-slot median and found it large (+0.47), but it did not repeat the multi-horizon
   INCREMENT comparison within slot, so objection 1 stands for the increment.
3. **Seed asymmetry, uncontrolled.** `make_model(RANDOM_SEED + year + j)` gives the
   baseline `j=0` and the candidate `j=1`, i.e. different random states, with no
   baseline-vs-baseline-different-seed control showing seed noise is smaller than the
   +0.009 effect.
4. **Loss deltas are unscaled.** Normalized MAE -0.0059 and QLIKE -0.0067 are reported
   without baseline levels, so materiality cannot be judged. Report percentages.
5. **The OOS yearly-stability gate is near-powerless**: "positive in >=60% of years" over
   2024, 2025 and a half-year 2026, with nested expanding training sets. "Positive in
   every year" is three correlated observations, not three trials.
6. **Preregistration is retrospective in the repo and unverifiable.** `declared_utc`
   12:13:55 to `closed_utc` 12:15:58 is a two-minute window, and HYP-0008 states it
   "formalizes that completed confirmation study". The freeze evidence is entirely the
   notebook's internal lock structure, and the notebook is **untracked in git**, so there
   is no verifiable timestamp for when Part B was unlocked. The recorded sha256 is the
   only anchor (it still matches on disk).
7. **`manifest.json` has `"outputs": []`.** The result tables exist only as Styler HTML
   inside a mutable notebook. The run directory should hold a frozen text/CSV dump.
8. Process state at review time: HYP-0008 status was still `proposed` while EXP-0011 was
   `completed`, and reviewer was `unassigned` in the hypothesis, review, manifest and
   ledger row.

### What the review verified rather than objected to

- The causality work is genuine, not asserted: cell 7 reconstructs 160 random decision
  rows straight from the minute parquet (max formula error 3.9e-17 / 0.0 bp; exact-clock,
  non-overlap, roll-guard and prior-only-median all True on both markets), the rule-9a
  coverage table is present, and Part B fits ONLY the two preregistered models.
- Every number in this review.md was checked against the notebook's stored cell outputs
  and matches exactly, and the on-disk notebook sha256 still equals the recorded value.
- **The sealed-read leakage invariant was independently verified** during EXP-0013:
  building the features over full history versus sealing the parquet read at 2024-01-01
  gives **bit-identical** pre-2024 rows (max |diff| 0.000e+00 on the slot median,
  `range_rv_15m` and the target). EXP-0011's Part-A/Part-B split did not leak.
- `core/forward_vol.py` reproduces this notebook's four published pooled ICs to
  |Δ| <= 1.7e-04 at **exact** evaluation row counts (22,274 / 22,277 / 7,039 / 7,038).

## Promotion decision

- `reports/FINDINGS.md`: not updated; this review and the experiment ledger are the
  run-level record
- `MEMORY.md`: promote the durable scientific result, operational non-adoption, and
  consumed-OOS boundary
- Shared `LEARNINGS.md`: not eligible without cross-project verification
