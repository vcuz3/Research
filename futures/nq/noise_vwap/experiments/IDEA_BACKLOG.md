# Noise VWAP Idea Backlog

Uncommitted brainstorming belongs here and is not evidence. Add ideas with
`python tools/research_admin.py new-idea --project futures/nq/noise_vwap`.

## Ideas

Priority order after the prerequisite faithful Null C rerun (`EXP-0007`):

1. `IDEA-0001` was rejected by `EXP-0008`; preserve it as negative evidence.
2. VWAP-touch exit (`stop_ref="vwap"`) vs the current `both` stop was REJECTED by
   `EXP-0010` (HYP-0003): NQ ΔSharpe -0.031, ES +0.258 but Null C p=0.29 with a
   positive null-uplift mean on both markets — a variance/selectivity amplifier,
   not exit information. Preserve as negative evidence; the paper's strongest
   exit family (4.2) does not transport.
3. `IDEA-0002` is a small, low-complexity exit ablation.
4. `IDEA-0003` and `IDEA-0004` promoted to active pursuit after the 2026-07-18
   review of paper 5095349: the paper's headline VWAP/ladder/asymmetric-exit
   results are in-sample-optimized (no holdout/WFO), so harvest them only as
   isolated single-variable changes each gated by its own full-pipeline Null C.
5. `IDEA-0005` is a portfolio-risk study, not an alpha improvement.
6. `IDEA-0006` is low priority because it imports a large in-sample search.


## IDEA-0001 — Short causal noise lookbacks

- Created: 2026-07-18
- Observation: The paper's optimized winners all used 2-8 prior sessions rather than its 14/90-session baselines; this claim has not been isolated on NQ/ES.
- Proposed mechanism: A short strictly-prior same-time-of-day window may adapt the noise boundary faster to current intraday volatility and admit meaningful breaks sooner.
- Expected improvement: Higher zero-trade-day net-R Sharpe than the 90-session working baseline without reducing aggregate net R or relying on one lookback.
- Main artifact risk: High selection risk across lookbacks; short windows amplify estimation noise and regime dependence. Rerun the full family under Null C on a common sample.
- Motivating evidence: outputs/5095349_extracted.txt pp.10,16; paper Tables 9-11
- Status: rejected by `EXP-0008`; NQ ΔSharpe -0.065/p=0.8571, ES +0.026/p=0.1905

## IDEA-0002 — Fixed early-flat cutoff

- Created: 2026-07-18
- Observation: The paper exits 11-31 minutes before the equity close; successful ladder variants cluster at 30 minutes before close.
- Proposed mechanism: Avoiding thin or reversal-prone closing minutes may reduce giveback and gap-to-next-open exit risk.
- Expected improvement: Lower daily drawdown and non-negative net-R delta versus the same entries and stop logic.
- Main artifact risk: Likely market-specific to equity margin rules and may simply truncate NQ's winner tail; test a tiny prespecified cutoff family and report tail retention.
- Motivating evidence: outputs/5095349_extracted.txt pp.2,8,16
- Status: REJECTED by `EXP-0013` (HYP-0006). Cutoff family {15,30,45,60} min. NQ
  best cutoff 45 ΔSharpe +0.101 clears Sharpe but net R −0.8 (fails gate) and maxDD
  worse; ES sign opposite (all cutoffs hurt). NOT tail truncation (p90R preserved) —
  variance reshaping only. Forward-watch: recent-2023 NQ Sharpe 1.10→1.54. Preserve
  as negative evidence; retain ride-to-close.

## IDEA-0003 — Causal two-stage ATR ladder

- Created: 2026-07-18
- Observation: The paper reports its strongest in-sample QQQ results for two-stage partial-exit ladders, while this project has only tested a single partial TP plus runner.
- Proposed mechanism: Banking part of a mature move and ratcheting the remaining stop may reduce giveback while retaining the large-winner tail.
- Expected improvement: Sharpe and drawdown improvement beyond the validated tp0.75_67 operating point with at least 90% top-decile winner-R retention.
- Main artifact risk: Paper ladder levels are AUM-dependent, often unreachable, and path-sensitive; translate to entry-frozen ATR units, include the fill bar, and use adverse ambiguous-bar resolution or close-trigger/next-open fills.
- Motivating evidence: outputs/5095349_extracted.txt pp.5-8,13,16; STUDIES.md partial-TP section
- Review note (2026-07-18): the paper's own Table 8 shows the upper ladder TP is
  "not realistically reached" for 3 of 4 strategies, collapsing into a time exit,
  so the tested ladder must be genuinely reachable in ATR units. This project's
  one Null-C survivor so far is the single partial-TP `tp1.0_50` (bank 50% at
  +1 ATR, runner trails; real dSharpe +0.056 vs null -0.032, z+2.57); the
  two-stage ladder must beat that operating point, not just the baseline.
- Status: REJECTED by `EXP-0011` (HYP-0004). The paper Table-2 ladder (−1R/+2R →
  bank 50% → 0R/+5R, 1R = entry-frozen band distance) cut NQ gross R 111→97, lost
  −0.075 Sharpe vs `both` and −0.131 vs `tp1.0_50`, ES flat; Null C did not save
  it. The fixed levels discard the trailing stop's edge. Preserve as negative
  evidence; `tp1.0_50` remains the only validated partial-exit tweak.

## IDEA-0004 — Entry and exit band horizons separated

- Created: 2026-07-18
- Observation: The paper allows a narrower exit boundary than entry boundary, but its stated inequality and implementation parameterization are internally confusing.
- Proposed mechanism: A stable entry boundary paired with a faster exit boundary may respond sooner when continuation fails.
- Expected improvement: Higher net-R Sharpe with identical entries and no loss of aggregate net R.
- Main artifact risk: Substantial overlap with the project's failed stop-reference/buffer search; high machinery-amplifier and multiple-testing risk. Resolve the paper's sign convention before coding.
- Motivating evidence: outputs/5095349_extracted.txt pp.5,7-8; WFO.md Design B
- Review note (2026-07-18): paper 4.3/4.4 lets the exit boundary be NARROWER
  than the entry boundary (a faster give-up), parameterized as
  volatility_multiplier_exit = enter + exit_diff with exit_diff in [-1, 0]. The
  engine's `stop_ref="band"` + `stop_buf_atr` can approximate a tighter exit
  band; test a tiny prespecified exit-multiplier family, hold entries identical,
  and gate on a full-pipeline Null C (the earlier stop-buffer search failed this
  exact way, so expect a machinery amplifier).
- Status: REJECTED by `EXP-0012` (HYP-0005). Grid s∈{0.5,0.75} × y∈{0.5,1.0} of
  max(narrow noise band, VWAP−y·σ_vw) long / mirror short. Literal negative-y
  (tighter) rejected both markets; user-selected positive-y (looser): NQ best
  +0.090 Sharpe MISSED the +0.10 gate, ES best +0.320 but Null C mean +0.254
  (p=0.29). Same looser-stop/fewer-trades Sharpe artifact as EXP-0010. Preserve as
  negative evidence; the looser exit is a turnover/capacity lever only.

## IDEA-0005 — Futures-native causal sizing comparison

- Created: 2026-07-18
- Observation: The paper's returns rely on direction-specific equity margin and target-vol sizing that usually saturates available margin; those economics do not transfer to futures.
- Proposed mechanism: Causal strategy-vol or underlying-vol targeting with explicit contract floors may improve capital efficiency without changing signal alpha.
- Expected improvement: Lower daily/weekly tail risk and drawdown at matched long-run volatility; no alpha claim.
- Main artifact risk: Sizing can manufacture attractive CAGR or Sharpe through leverage, floors, or retrospective allocation. Preserve one-contract gross/net evidence and enforce causal portfolio accounting.
- Motivating evidence: outputs/5095349_extracted.txt pp.2,13-14; FORENSIC.md faithful sizing
- Status: untriaged

## IDEA-0006 — Paper bundle transport benchmark

- Created: 2026-07-18
- Observation: The paper publishes optimized QQQ parameter bundles but no untouched holdout or walk-forward evidence.
- Proposed mechanism: Treating each published bundle as externally chosen may provide a low-discretion transport test on NQ/ES, after translating equity-only sizing and exits.
- Expected improvement: At least one coherent strategy family transfers in sign across NQ and ES and beats its own full-pipeline Null C distribution.
- Main artifact risk: Not independent of the paper's in-sample search; cross-asset transport is exploratory, definitions differ, and exact ladder translation is ambiguous. Benchmark only, never confirmation.
- Motivating evidence: outputs/5095349_extracted.txt Tables 7,9-11
- Status: untriaged
