# Project Memory: Bitcoin Noise Area VWAP

Keep this concise. Link to reports and immutable artifacts instead of copying
their contents.

## Scope

- Objective: transparently port the audited NQ Noise-Area + VWAP strategy to
  Bitcoin with explicit session anchoring, date splits, data gates, and fills.
- Instruments or markets: Binance Spot BTCUSDT as a reference series; a
  short-capable deployment venue is not yet specified.
- Data coverage: shared one-minute archive 2017-08-17 through 2026-08-12;
  EXP-0001 loads 2019-01-01 onward.
- Current phase: baseline replication / initial transfer screen.

## Current status

- Verdict: provisional
- Last verified: 2026-08-16
- Lifecycle phase: baseline
- Baseline replication: completed as EXP-0001; independent review pending.
- Baseline tolerance and result: causal invariants passed; IS net Sharpe -0.223,
  temporal-OOS net Sharpe 0.230, OOS gross 11.835 bps/trade against 10 bps cost.
- Engine audit: provisional pass for notebook timing, non-overlap, missing-bar,
  and rolling-causality assertions; venue execution is unaudited.
- Execution profile: completed 30-minute decision bars; exact next-minute open
  market fills; decision-time stops; final session-close proxy; one position.
- Holdout status: consumed/temporal only. Only future observations after a
  specification freeze can be clean holdout evidence.
- Experiment ledger: `experiments/ledger.csv`
- Reproduction command: `python crypto/noise_vwap/backtest_engine/run_notebook.py`
- Primary evidence: `artifacts/runs/EXP-0001/review.md` and
  `baseline_replication/bitcoin_noise_vwap.ipynb`.

## Authoritative artifacts

- Paper specification: `paper/PAPER_SPEC.md`
- Claims register: `paper/CLAIMS.md`
- Baseline report: `reports/BASELINE_REPLICATION.md`
- Engine audit: `reports/ENGINE_AUDIT.md`
- Current findings: `reports/FINDINGS.md`

## Confirmed findings

- The self-contained notebook exposes all strategy calculations and parameters,
  including start/IS/OOS dates, ET anchor, session length, weekends, decision
  interval, lookback, coverage floors, VWAP gate, costs, and notional.
- EXP-0001 loaded 4,000,250 rows, reported 22 gaps / 4,090 missing minutes,
  retained 1,984 of 1,987 candidate sessions, and achieved complete evaluated
  band coverage without filling missing bars.
- All baseline fill and causality assertions passed: exact next-minute entries
  and non-EOD exits, zero overlap, and zero manual band parity error.

## Provisional hypotheses

- Hypothesis: the weekday 09:30 ET transfer contains positive BTC timing value.
  - Kill test: OOS net Sharpe > 0 and OOS gross/trade > 10 bps.
  - Current evidence: literal screen passed narrowly (0.230; 11.835 bps), but IS
    and the two latest annual segments are negative. Status remains provisional.

## Invalidated or superseded findings

- Default anchor is 09:30 ET with a 390-minute weekday session to preserve the
  NQ decision universe and tie the anchor to U.S. cash-market price discovery.
- A 90% minimum observation floor is explicit for the 90-session band; evaluated
  cells happened to have all 90 observations under the frozen baseline.
- Default cost is 5 bps per side as a sensitivity assumption, not a current fee
  claim.

## Decisions and constraints

- BTC has no natural open; anchor results may be clock/session selectors.
- The OOS gross cushion over cost is only 1.835 bps/trade before spread, funding,
  borrow, impact, or basis between spot and the traded vehicle.
- Annual results are unstable and 2025-2026 are negative.
- No path-preserving null, anchor-neighbor test, intended-venue replay, or
  independent review has been completed.

## Known risks and open questions

- None yet.

## Next actions

1. Independently review EXP-0001 and the notebook calculations.
2. Run a path-preserving Null C on the one frozen cell before any anchor search.
3. If it survives, test neighboring anchors with selection-aware inference and
   replay fills/costs on the intended short-capable venue.

## Promotion candidates

- None yet. Promote only findings verified and reusable across projects.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
