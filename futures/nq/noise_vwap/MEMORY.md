# Project Memory: Noise Area VWAP

This file is the concise handoff for the project. Detailed evidence remains in
the linked reports, code, and run artifacts.

## Scope

- Objective: faithfully reproduce the published Noise Area VWAP strategy, audit
  its implementation, and test whether robust NQ/ES improvements exist.
- Instruments or markets: NQ and ES futures.
- Data coverage: 2011-2026 clean Databento research history.
- Current phase: final validation / future-shadow planning.

## Current status

- Verdict: qualified paper replication; research watchlist, not deployment-ready.
- Last verified: 2026-07-19 from the current forensic and review reports plus
  the corrected faithful Null C run `EXP-0007`, 1-second execution run
  `EXP-0009`, the rejected exit/lookback studies `EXP-0008`/`EXP-0010`, and
  the rejected gap/RVOL veto and sizing studies `EXP-0016`/`EXP-0017`.
- Lifecycle phase: final validation.
- Baseline replication: passed after correcting decision-clock and VWAP-gate
  discrepancies.
- Baseline tolerance and result: clean faithful headline is approximately NQ
  28.3% return / 1.31 Sharpe, ES 15.5% / 0.81, and equal-weight portfolio 23.8%
  / 1.52; compare published NQ 24.3% / 1.67, ES 16.8% / 1.25, portfolio 22.4%
  / 1.57.
- Engine audit: next-open faithful path and parity tooling exist. The Null C
  opening-sentinel defect is fixed and its anchor, net-move, atom, diffusivity,
  and pairing invariants are tested. The clean post-fix faithful run passed:
  NQ z=2.81/p=0.0323/49% capture; ES z=5.63/p=0.0323 with negative null net P&L.
- Execution profile: signal after the decision bar, fill at the next available
  bar open with explicit costs; `signal_close` is an ablation only.
- Holdout status: consumed. Only future shadow data can be clean holdout evidence.
- Experiment ledger: `experiments/ledger.csv` (legacy rows are reconstructed).
- Reproduction command: `python -m futures.nq.noise_vwap.scripts.forensic`.
- Primary evidence: `FORENSIC.md` and `REVIEW.md`.

## Authoritative artifacts

- Paper specification: `paper/PAPER_SPEC.md`
- Claims register: `paper/CLAIMS.md`
- Baseline evidence: `FORENSIC.md`
- Engine and pipeline review: `REVIEW.md`
- Data audit: `DATA_AUDIT.md`
- Kill tests: `KILL_TEST.md`
- Experiment history: `experiments/ledger.csv`

## Confirmed findings

- The original large replication gap was primarily caused by an off-by-one
  decision clock and a missing VWAP gate; the corrected clean run is broadly
  consistent with the paper's headline return claims.
- Faithful execution is next-open. Same-close execution is useful only as a
  labelled diagnostic.
- Performance is regime dependent and 2025 was weak; aggregate Sharpe alone is
  insufficient evidence of a persistent edge.
- The corrected faithful strategy exceeds the session-drift-preserving Null C
  on both NQ and ES in `artifacts/runs/EXP-0007/`; NQ still has material null
  capture (49%), so this supports a qualified timing edge rather than deployment.
- The former Null C implementation could shuffle its artificial zero-link
  sentinel away from index 0 and omit one real inter-bar link. The core and
  legacy study implementations now pin the opening atom and pass multi-seed
  invariant tests in `tests/test_nulls.py`.
- `EXP-0009` confirms that the working continuous-stop edge survives a causal
  first-touch execution model on 68.3 million NQ RTH one-second bars. At 0.5
  tick/side, zero-day daily Sharpe changed from 0.923 (1m close/next-open) to
  0.883 (1s touch), within the predeclared -0.15 tolerance. The touch engine was
  not an improvement: turnover increased and vol-targeted Sharpe/CAGR/maxDD
  changed from 1.184/22.5%/-18.1% to 1.090/19.5%/-24.4%. Evidence:
  `artifacts/runs/EXP-0009/`.

## Provisional hypotheses

- None currently promoted.

## Invalidated or superseded findings

- `HYP-0009` is rejected as validated capital-allocation alpha, although it is
  a default-off future-shadow candidate. The frozen four-level gap/RVOL sizing
  schedule kept all 4,209 trades and improved real zero-day daily Sharpe from
  1.288 to 1.398, net R from 91.20 to 101.97, and max drawdown from 4.70R to
  4.42R at only 0.957x mean trade weight. Net-R uplift was positive pre-2023
  (+8.40R) and 2023+ (+2.38R). However, 30 paired full-pipeline Null C draws
  reproduced mean Sharpe uplift +0.074 (sd 0.045) versus real +0.111: z=0.81,
  with 30% of null draws at least as strong. Do not deploy or use this as an ML
  justification on consumed history; only future shadow can resolve the
  residual real-minus-null uplift. Evidence: `artifacts/runs/EXP-0017/`.
- `HYP-0008` is rejected: vetoing otherwise valid NQ breakouts when the
  overnight gap opposes the signal and signal-minute RVOL(90) is below 1.2
  raised real net R by +3.97R and daily Sharpe by +0.236, with positive deltas
  both pre-2023 and 2023+, but retained only 86.1% of trades and failed the
  paired full-pipeline Null C test. The null produced a larger mean uplift of
  +5.18R (sd 5.18; real-vs-null z=-0.23; 53.3% of draws beat real). The EXP-0015
  conditional bins therefore did not validate as predictive alpha; treat this
  fixed rule as selectivity/turnover and do not use it to justify XGBoost.
  Evidence: `artifacts/runs/EXP-0016/`.
- `HYP-0007` is rejected for unconditional ES production-default adoption, but
  confirms material execution utility for the frozen EXP-0012 `s0.5_y0.5` cell.
  At 0.25 tick/side, full-sample net R/Sharpe/maxDD improve from
  51.5/0.70/7.45R to 84.3/1.02/6.22R and trades fall 37%. The joint net-R and
  maxDD condition passes only 1 of 4 eras: drawdown worsens in 2020+ and 2023+,
  while both net R and drawdown worsen in 2025+. Full-sample cost resilience is
  strong (at 1 tick/side: +42.4R treatment versus -16.1R baseline), so retain the
  exit default-off as a forward-shadow/execution-cost lever, not alpha or an
  unconditional default. Evidence: `artifacts/runs/EXP-0014/`.
- The original local replication statistics are invalid as faithful-paper
  evidence because the decision clock and VWAP gate differed.
- Pre-fix Null C magnitude estimates are superseded for the current faithful
  configuration; preserve them as historical evidence, not the current verdict.
- `HYP-0001` is rejected: short lookbacks did not improve full-sample NQ
  performance (best nonbaseline ΔSharpe -0.065, p=0.8571) and ES's small uplift
  (+0.026) was not family-wise significant (p=0.1905). Evidence:
  `artifacts/runs/EXP-0008/`.
- `HYP-0006` is rejected: a fixed early-flat cutoff before the close does not
  validate. NQ best cutoff 45 ΔSharpe +0.101 clears the Sharpe threshold but net R
  is −0.8 below baseline (fails the net-R gate) and maxDD is worse; ES all cutoffs
  hurt (net R +51.5→+43-44, best ΔSharpe −0.030) so the sign does not transfer. No
  Null C (gate failed). Unlike the looser-stop artifacts this is NOT tail
  truncation (top-decile winner-R preserved) — it reshapes late-session variance
  only, on NQ only. Forward-watch: recent 2023+ NQ Sharpe jumps 1.10→1.54 at
  cutoffs 30-45 (late-session reversals hurt NQ more recently); monitor in shadow,
  do not re-optimize on consumed history. `flat_before_close` added default-off to
  `engine2` (parity verified). Evidence: `artifacts/runs/EXP-0013/`.
- `HYP-0005` is rejected: a narrower noise exit band + looser (below-price)
  VWAP-sigma band does not validate. NQ best cell ΔSharpe +0.090 / ΔnetR +14.1
  MISSES the +0.10 gate (no null run per the standing rule); ES best +0.320 clears
  the gate but the family-max Null C reproduces +0.254 on noise (p=0.2903). The
  literal negative-y (tighter) grid was rejected on both markets first. This is the
  3rd looser-stop/fewer-trades "higher Sharpe" that Null C exposed as a
  variance/selectivity amplifier (after EXP-0010 VWAP-touch and the KAMA rarity
  filter): treat any "fewer trades → higher Sharpe" exit as machinery until Null C
  clears it. The looser exit is a turnover/capacity lever, not alpha. exit_band
  added default-off to `engine2` (s=1/y=0 parity verified). Evidence:
  `artifacts/runs/EXP-0012/`.
- `HYP-0004` is rejected: the paper's two-stage RR ladder exit (Table-2
  −1R/+2R → bank 50% → 0R/+5R, 1R = entry-frozen band distance) does not beat the
  `both` stop. NQ ΔSharpe −0.075 / ΔnetR −12.9 (fails +0.10 gate), loses to
  `tp1.0_50` by −0.131 Sharpe, Null C p=0.6129; ES ΔSharpe +0.014, Null C
  p=0.3226. The fixed −1R stop and +5R cap cut gross R (111→97), discarding the
  trailing stop's edge. Ladder added default-off to `engine2` (tests + parity
  verified). Retain `both`; keep `tp1.0_50`. Evidence: `artifacts/runs/EXP-0011/`.
- `HYP-0003` is rejected: the paper's flagship every-bar VWAP-touch exit
  (`stop_ref="vwap"`) does not beat the current `both` stop. NQ uplift ΔSharpe
  -0.031 (fails +0.10 gate), Null C p=0.8710; ES uplift +0.258 but Null C
  p=0.2903. The null-uplift mean is positive on both markets (+0.083 NQ, +0.178
  ES), so the looser stop is a variance/selectivity amplifier that lifts Sharpe
  as much on noise as on signal, not exit information. It does raise per-trade
  net R with ~27% fewer trades — a turnover/capacity lever only, never a Sharpe
  claim. Retain the `both` stop. Evidence: `artifacts/runs/EXP-0010/`.

## Decisions and constraints

- Preserve existing import paths and reports during migration to the standard
  project structure.
- No historical period may be relabelled as sealed holdout after inspection.
- New strategy variants must use the audited engine and compare with the frozen
  faithful baseline.
- Routine ideas, hypotheses, experiment records, closeout, and hygiene checks use
  the shared `tools/research_admin.py` workflow.

## Known risks and open questions

- Obtain independent review of `EXP-0007` configuration and interpretation.
- Obtain independent review of the causal stop activation and cost treatment in
  `EXP-0009`; one-second OHLC still cannot resolve within-second path order.
- Quantify robustness to neighbouring parameters, costs, and post-publication
  regimes without treating searched variants as confirmatory evidence.
- Define the forward shadow start date and immutable observation protocol.

## Next actions

1. Review `EXP-0007`, `EXP-0008`, and `EXP-0009` independently.
2. Decide whether the 2023+ short-lookback regime observation belongs only in
   future shadow monitoring; do not optimize it further on consumed history.
3. Decide whether to enter a future-only shadow period or close the project.

## Promotion candidates

The clock and gate failures may become cross-project learnings after confirming
the same failure modes in another project. They remain project-specific here.
