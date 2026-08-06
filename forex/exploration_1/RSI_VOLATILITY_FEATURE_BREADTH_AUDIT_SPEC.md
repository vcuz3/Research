# RSI volatility-feature breadth audit — frozen exploratory specification

## Question

Does `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md` test enough distinct volatility
constructions and outcome definitions to support its broad claims that kurtosis,
vol-of-vol, term structure, and volatility structure generally do not distinguish
snap-back from continuation?

This audit is written before the breadth run. It does not revisit 2024+ data.
All history through 2023 is already consumed, so any survivor is hypothesis-
generating rather than confirmatory.

## Scope correction established before the run

The programme tested one vol-of-vol construction (the rolling standard deviation
of heavily overlapping RV(5)), two conventional sample-kurtosis windows (30 and
60 observations), and one backward-looking RV ratio (5/30). Those are valid
tests of those exact features. They are not exhaustive tests of volatility
structure, robust tail shape, jump concentration, or a market-implied volatility
term structure. The categorical report wording is therefore too broad regardless
of the results below.

## Frozen data and clock

- EURUSD, GBPUSD, AUDUSD, NZDUSD one-minute midpoint OHLC, 2012-2023.
- Same `build_pair` pipeline, NY 17:00 session boundary, completed `:29`/`:59`
  decisions, next-open entry, and exact 30-minute exit as the programme.
- Signals are RSI(14) <= 30 or >= 70. The 2024+ holdout remains sealed.
- Feature transforms are causal 90-prior-session same-slot percentiles.

## Candidate families

The audit adds deliberately different constructions rather than many cosmetic
parameter variants:

1. RV level at 5, 15, 30, 60, and 120 minutes.
2. Backward realized-volatility slopes/ratios at 5/30, 15/60, and 30/120.
3. Level-normalized vol-of-vol (coefficient of variation of RV(5)) and volatility-
   innovation dispersion (standard deviation of changes in log RV(5)), over 60
   and 120 minutes.
4. Conventional rolling kurtosis over 30, 60, 120, and 240 minutes.
5. Tail/jump concentration: largest squared return share, realized quarticity
   ratio, and bipower-variation jump share over 30, 60, and 120 minutes.
6. Downside semivariance share over 30, 60, and 120 minutes.

This is broader, not exhaustive. It still has no options-implied volatility,
cross-asset state, order book, spread, news, or genuine market term structure.

## Targets

The original `survived` label is retained. Two economic targets are added:

- `loss`: the fixed-horizon trade loses money;
- `tail_loss`: gross P&L is below the pair-specific early-era 10th percentile,
  with that frozen threshold applied to 2021-2023.

This prevents a failure on “RSI remains beyond 30/70 at the next checkpoint” from
being misread as failure to identify economically damaging continuation.

## Validation and controls

- Univariate late-era AUC for every pair × target × feature, with session-block
  bootstrap intervals and BH correction over the full screen.
- Direction must agree on at least three of four pairs to be called stable.
- Compare a baseline logistic model (`rsi_depth`, RV(30) percentile) with an L2-
  regularized expanded model. Choose regularization on 2019-2020 after fitting on
  2012-2018, refit on 2012-2020, and report 2021-2023 AUC.
- Report the change in mean P&L when dropping the half of signals scored riskiest,
  but treat this as a turnover/selectivity diagnostic, not alpha.
- Report feature coverage and complete-case counts. No imputation.

## Kill / interpretation thresholds

The hypothesis that the broader engineered-volatility set adds *material*
information is supported only if, for either `survived` or `tail_loss`:

1. expanded-model late-era AUC beats the baseline by at least 0.015 in at least
   three pairs and the median improvement is at least 0.015; or
2. a volatility feature has direction-consistent AUC in at least three pairs,
   full-screen BH q < 0.10, and median absolute AUC deviation >= 0.03.

Otherwise the breadth run is a NO-GO for this candidate set. Even a NO-GO cannot
justify “volatility structure does not predict continuation”; it just expands the
documented negative search boundary.

## Post-run diagnostic amendment (disclosed)

The first completed run showed that every RV-level horizon predicts the fixed-pip
`tail_loss` target. Because a fixed pip barrier is mechanically crossed more often
when volatility is high, a scale-normalized `tail_loss_scaled` target was added
after seeing that output. It is the bottom decile of gross P&L divided by trailing
RV(30), with the decile fitted in 2012-2020 and frozen in 2021-2023. This diagnostic
does not participate in the frozen gate above.
