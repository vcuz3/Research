# Project Memory: Anchored TWAP/SMA Z-band ATR strategy

## Scope

- Objective: implement and test the user-clarified 2.5Z re-entry fade with a 2ATR stop.
- Instruments or markets: AUDUSD, EURUSD, GBPUSD, NZDUSD midpoint FX.
- Data coverage: 2011-07/12 through 2026-07-17 at one minute; signals at 15 minutes.
- Current phase: editable Z-band and RSI arm/reset single-pair tooling plus one frozen EURUSD Z-band train/OOS export for regime analysis.

## Current status

- Verdict: tooling ready; **EXP-0001's specific four-pair/global-anchor configuration was a NO-GO at a 1.0-pip round-trip cost**. Other single-pair/parameter hypotheses are untested until separately frozen and registered.
- Last verified: 2026-08-08.
- Lifecycle phase: final review / closeout.
- Baseline replication: clarified logic implemented; exact TradingView parity is not claimed because symbol, timeframe, chart timezone, and broker-emulator details were unspecified.
- Baseline tolerance and result: 8 deterministic engine/feature fixtures pass.
- Engine audit: passed for tested invariants; see `reports/ENGINE_AUDIT.md`.
- Execution profile: completed 15-minute close, next complete-bar open, underlying one-minute bracket replay, adverse one-minute dual-touch, gap at first tradable open, one position per pair.
- Holdout status: 2024-01-01 through 2026-07-17 consumed; future-only thereafter.
- Experiment ledger: `experiments/ledger.csv`.
- Reproduction command: `python run_research.py --output-dir artifacts/runs/EXP-0001`.
- Primary evidence: `artifacts/runs/EXP-0001/`, `artifacts/runs/EXP-0002/`,
  `anchored_twap_sma_zband_atr.ipynb`; editable guarded workflow:
  `single_pair_zband_workbench.ipynb`.

## Authoritative artifacts

- Strategy specification: `paper/PAPER_SPEC.md`.
- Claims register: `paper/CLAIMS.md`.
- Baseline report: `reports/BASELINE_REPLICATION.md`.
- Engine audit: `reports/ENGINE_AUDIT.md`.
- Current findings: `reports/FINDINGS.md`.
- Final review: `reports/FINAL_REVIEW.md`.

## Confirmed findings

- The user clarification supersedes the pasted pivot/2.0Z/1.5ATR defaults: baseline is 2.5Z arming and a 2.0x ATR(14) stop.
- All five pre-2020 anchor candidates were negative net at 1 pip; SMA(80) was merely the least-bad daily-Sharpe candidate and was frozen for later evaluation.
- OOS 2021-2023: 4,756 trades, +0.350 gross pips/trade, -0.650 net, daily net-pip Sharpe -0.929, clustered net-R t -2.48; all four pairs negative net.
- Holdout 2024-2026-07-17: 3,929 trades, +0.357 gross pips/trade, -0.643 net, daily net-pip Sharpe -1.220, clustered net-R t -2.89; all four pairs negative net.
- The later gross effect is smaller than 0.5 pip/trade and flips negative at 0.5-pip cost in both OOS and holdout. This is cost-fragile, not a deployable edge.
- Core files have zero duplicates, out-of-order timestamps, or invalid OHLC. Complete 15-minute-bar share is at least 99.983% per reported pair/sample aggregate; selected-feature readiness exceeds 99.96% after one-time warm-up.
- EXP-0002 confirmed the frozen EURUSD SMA200/Z2/arm30/ATR14x3/R1.5
  exporter produces both isolated segments: 1,894 train trades and 717 OOS
  trades, with no 2024+ rows. `candidate_trades` is training-only; downstream
  analysis must use/export the post-segmentation `trades` variable.
- EXP-0003 confirmed `single_pair_rsi_crossover_workbench.ipynb` executes end
  to end on both shortened and full pre-holdout dates. The full default EURUSD
  run created 3,474 train and 1,347 OOS trades without loading 2024+ rows.
  This is an implementation validation, not evidence of an RSI trading edge.

## Provisional hypotheses

- The small later-period midpoint gross expectancy might reflect genuine mean reversion, but it is not worth further parameter search. Quote-level spread evidence and a full path-preserving null would be required before interpreting it.
- EXP-0002's frozen EURUSD configuration had mean net R of -0.04114 in train
  and +0.01873 in 2021-2023 OOS. This is exploratory after training inspection
  and has not been promoted as an edge; evidence is `artifacts/runs/EXP-0002/`.

## Invalidated or superseded findings

- Invalidated: the clarified strategy has positive net OOS/holdout value at a plausible 1-pip round-trip cost.
- Superseded: the pasted pivot-stop and lower threshold defaults are not the intended baseline.

## Decisions and constraints

- The user clarified that the desired deliverable is a single-pair notebook with editable parameters and training dates, with holdout opened only after development is complete. `single_pair_zband_workbench.ipynb` implements that workflow directly in small sequential cells.
- `single_pair_rsi_crossover_workbench.ipynb` follows the same structure for a
  two-stage RSI strategy: a short arms on a completed-bar cross above its upper
  threshold and enters at the next-bar open after a later cross below its reset;
  the long logic is mirrored. ATR stop and R-multiple target are frozen at entry.
- The RSI defaults are RSI(14), short arm/reset 0.70/0.65, long arm/reset
  0.30/0.35, 30-bar arm expiry, ATR(14) x 2 stop, and 1.5R target. The optional
  candidate grid is off by default and selects only on training data.
- The workbench uses percentage-of-current-equity risk sizing: units equal the cash risk budget divided by the ATR stop distance, with an optional explicit leverage cap. Tuning and account metrics therefore use compounded daily returns rather than fixed-quantity pip Sharpe.
- Calendar 2020 remains an unused embargo and is never used for selection or headline confirmation.
- One global anchor choice is selected across all pairs; later results cannot retune it.
- Midpoint OHLC lacks bid/ask quotes. Cost stress is an assumption, not measured execution.
- Historical data through 2026-07-17 has now been inspected; new holdout evidence must be future data.

## Known risks and open questions

- The 15-minute signal interval is a documented assumption because the user source did not specify chart timeframe.
- One-minute bars still cannot order rare same-minute dual barrier touches; adverse scoring affected 0.13% OOS and 0.20% holdout trades.
- No path-preserving return-shuffle null or quote-level spread replay has been run because the baseline already failed net.

## Next actions

1. Use `single_pair_zband_workbench.ipynb` to choose one pair and freeze a train/OOS protocol before registering any new material run.
2. Keep `OPEN_HOLDOUT=False` throughout tuning; do not use the historical holdout to rescue a failed OOS result.
3. Do not reinterpret already inspected 2024-2026 dates as scientifically clean; a genuine new holdout is future-only.
4. Use `export_frozen_notebook_trades.py` when a regime study needs the selected
   train and OOS trades; do not manually export `candidate_trades`.
5. Use `single_pair_rsi_crossover_workbench.ipynb` for RSI arm/reset research;
   freeze its configuration before interpreting OOS and keep 2024+ locked.

## Promotion candidates

- None. Existing shared cost/fill lessons already cover the conclusion.
