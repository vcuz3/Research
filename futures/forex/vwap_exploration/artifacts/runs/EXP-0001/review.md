# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — VWAP separates materially from its constant-volume degenerate limit (TWAP) on CME FX futures
- Status: completed
- Builder: Claude (Opus 5)
- Reviewer: Claude (Opus 5), self-review — no second model available this session
- Primary metric: R_sep = median over decisions of |VWAP-TWAP| / scale_vwap (causal trailing same-slot mean |close-VWAP|)
- Kill test: Volume weighting declared non-load-bearing if, on BOTH 6E and 6B, R_sep < 0.10 pooled OR corr(dev_vwap,dev_twap) > 0.99.

## Result versus hypothesis

**NOT KILLED on either product.** The volume weighting is a real, non-degenerate
operation on CME FX futures.

| | 6E | 6B |
|---|---|---|
| `R_sep` pooled median | **0.2592** | **0.2493** |
| `R_sep` at 16:29 ET | 0.2871 | 0.2888 |
| `corr(dev_vwap, dev_twap)` pearson | 0.9569 | 0.9582 |
| anchors put price on opposite sides | 7.12% | 7.08% |

Both products land essentially on the pre-declared "materially different"
threshold of 0.25 and nowhere near the 0.10 kill line; the correlation is far
below the 0.99 kill line. Median absolute separation is **2.6 pip (6E) / 3.9 pip
(6B)** pooled, rising to 7.7-8.8 pip in the NY afternoon.

The operationally relevant number is the last row: a "price above/below VWAP"
gate and the same gate built on TWAP would **disagree on 7% of decisions**. Small
but not nothing — and it is what makes HYP-0002's information arm a real question
rather than a tautology.

## Gross, net, baseline, and null comparison

Not applicable — descriptive measurement, no P&L, no null required. No baseline
strategy exists in this project by design.

## Regimes, sensitivity, and alternative explanations

- **Shape control passes.** Median |sep| grows monotonically through the session:
  1.0 pip (6E) / 1.2 pip (6B) in the Asia block against 7.9 / 8.7 pip in `ny_pm`,
  a 7.4-8.0x expansion. The construction demands this — the anchors have had more
  session to diverge — and its absence would have indicated a coding error rather
  than a market fact.
- **Era control passes.** `R_sep` is stable at 0.18-0.36 across all 14 years on
  both products, with a mild downward drift (6E 0.30 in 2011 → 0.21 in 2023).
  Correlation stays 0.945-0.969 throughout. Nothing here is a post-crisis
  artifact, and 6E's 2016 tick halving leaves no visible mark.
- **Cross-product control passes**, unusually tightly: `R_sep` 0.2592 vs 0.2493,
  correlation 0.9569 vs 0.9582, sign disagreement 7.12% vs 7.08%. Two different
  currencies with different volume levels give the same three numbers to two
  significant figures — a hint that what is measured is a property of the
  session/volume-profile geometry, not of EUR or GBP.

**Alternative explanation considered and rejected.** The separation could be an
artifact of thin Asian bars: a handful of 1-contract bars would pull TWAP around
while barely moving VWAP. If that were the story, separation would be *largest*
in Asia. It is smallest there (R_sep 0.128 vs 0.372 in the overlap), so the
effect is driven by the liquid session, not by thin-bar noise.

**The volume profile is less concentrated than the framing assumes.** Top slot
6.2% of session volume against 2.17% under a flat profile; top four slots 22.8%;
HHI only 1.60x the flat value. FX futures volume is *tilted* toward the London/NY
overlap, not *concentrated* in it. That is the quantitative reason `R_sep` is
0.25 rather than 1.0, and it should be carried into any later claim that "VWAP is
dominated by the overlap" — it is not.

## Artifact and implementation risks

- Rolls: sessions spanning more than one `instrument_id` (1.54% / 1.52%) are
  dropped, because a session-anchored VWAP across a roll averages two contracts.
- Zero-volume bars would make VWAP undefined; there are none in either archive
  (0.000%). `add_anchors` forward-fills only within a session.
- `TWAP == VWAP-at-constant-volume` and `TWAP != VWAP-at-varying-volume` are both
  pinned in `tests/test_core.py`, so the "degenerate limit" claim is executable
  rather than asserted.

## Builder interpretation

The precondition for a VWAP study on FX holds on futures and provably does not
hold on the spot archives this workspace already has. This does **not** establish
that the volume weighting carries *information* — two anchors can differ by 3 pip
and predict identically — and EXP-0002 tests that. The value of this run is that
it makes EXP-0002's answer interpretable: had TWAP matched VWAP here, any later
"VWAP result" would have been a TWAP result by construction.

## Independent review

- Review status: self-reviewed; no second model this session.
- Objections: the 0.25 "materially different" line was set by judgement, not by a
  calibration exercise. It is not load-bearing — the verdict rests on the 0.10
  kill line, which the observed value clears by 2.5x on both products.
- Verdict: **accepted, hypothesis not killed.**

## Promotion decision

- `reports/FINDINGS.md`: promoted as finding A.
- `MEMORY.md`: promoted (project state).
- Shared `LEARNINGS.md`: promoted only as a sub-point of the EXP-0002 entry —
  separation without an information test is not yet a reusable lesson.
