# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — Frozen standardized-displacement mean reversion baseline
- Status: completed — **NO-GO**
- Builder: Codex
- Reviewer: unassigned
- Review status: pending independent review
- Pre-run code/spec commit: `6658526`
- Primary metric: per-signal base-cost net R, UTC-day clustered
- Kill test: `KILL_TEST.md`

## Result versus hypothesis

Rejected. Consumed-history base-cost net expectancy is −0.3733 R/signal (95%
clustered CI [−0.3880, −0.3585]); gross expectancy is already negative at
−0.0815 R and −0.244 pips. The sealed holdout is −0.5045 R net.

## Gross, net, baseline, and null comparison

Mean base cost is 1.081 pips, far above the negative gross result. Symmetric and
fixed-horizon compulsory-stop diagnostics are both significantly negative. The
reversion exit beats the matched-duration random-exit null by about 0.0103 R,
but both results are negative; the null success is not a viable trading edge.

## Regimes, sensitivity, and alternative explanations

No regime or parameter sweep was run. Early, late, and sealed-holdout results are
all negative. Each of EURUSD, GBPUSD, and AUDUSD is individually negative at base
costs. NZDUSD has material coverage exclusions and is not needed for the verdict.

## Artifact and implementation risks

- Midpoint bars have no bid/ask or volume, so costs are modeled rather than measured.
- The unavailable 17:00 New York bar required attainable liquidation at 16:55.
- The first material attempt stopped before metrics because the original boundary
  requested an unavailable 17:00 price. A second stopped before metrics on unused
  batch padding, and a third was interrupted before metrics to vectorize an
  inefficient data-quality date count. None produced or informed performance
  parameter changes. The final run is deterministic and reproduced exactly.
- NZD late-era 18:00–19:00 UTC holes cause 17,063 conservative path exclusions;
  see the era/hour table in `DATA_QUALITY.md`.

## Builder interpretation

The compulsory stop converts a positive consumed-history unstopped six-bar
forward-return diagnostic into a significantly negative deployable result, and
the raw forward signal does not survive the holdout. The frozen asymmetric exit
has a small timing advantage over random exits, but overall gross expectancy is
negative before costs. The correct project outcome is NO-GO.

## Independent review

- Review status: pending
- Required rerun: invariant tests plus `python -u forex/exploration_4/_run_baseline.py`
- Required inspection: frozen commit, kill test, ledger, price-availability
  boundary, NZD exclusions, trade-level artifacts, and notebook
- Verdict: pending; builder result must not be described as independently reviewed

## Promotion decision

- `reports/FINDINGS.md`: updated with NO-GO
- `MEMORY.md`: updated with confirmed negative evidence
- Shared `LEARNINGS.md`: not changed; no new cross-project reusable finding claimed
