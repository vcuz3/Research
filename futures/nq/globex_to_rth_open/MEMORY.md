# Project Memory: NQ Globex to RTH Open

## Scope

- Objective: test long NQ from 18:00 to next-date 09:30 ET, MA/VIX gates, and
  four sizing rules.
- Data coverage: NQ trade dates 2011-08-02 through 2026-07-14; daily VIX overlap.
- Current phase: exploratory study complete; validation not started.

## Current status

- Verdict: provisional WATCH / research only.
- Last verified: 2026-08-25.
- Baseline: 3,761 trades, $60.61 net/trade, Sharpe 0.531, HAC(5) t=2.244,
  maximum drawdown -$97,010 under $15 round-trip cost.
- Engine audit: five builder tests passed; independent review pending.
- Execution: exact 18:00/09:30 bar opens, same contract, no roll inside.
- Holdout: consumed; future-only.
- Authoritative run: `artifacts/runs/EXP-0003/`.
- Reproduction: `python futures\nq\globex_to_rth_open\scripts\run_study.py`.
- Vol-target figure run: `artifacts/runs/EXP-0004/`; reproduce with
  `python futures\nq\globex_to_rth_open\scripts\run_vol_target_figure.py`.
- LSE SMA200 parity run: `artifacts/runs/EXP-0005/`; reproduce with
  `python futures\nq\globex_to_rth_open\scripts\run_lse_sma200_figure.py`.
- LSE/Databento comparison: `artifacts/runs/EXP-0006/`; reproduce with
  `python futures\nq\globex_to_rth_open\scripts\compare_lse_databento.py`.

## Confirmed findings

- Confirmed implementation fact: exact-clock, bounded-date, roll-excluding,
  one-position accounting and cost fixtures pass executable tests.
- Confirmed data fact: 60 of 3,821 matched anchor pairs crossed a roll and were
  excluded; 3,761 valid pairs remain. Evidence: EXP-0003 data quality.
- Confirmed comparison fact: the LSE and Databento SMA200 gates agree on all
  2,357 common dates. Fifteen >=50-bp overnight-return mismatches cluster in
  quarterly roll windows; the LSE constant-symbol series visibly changes
  contract inside the holding window. Evidence: EXP-0006.

## Provisional findings

- The baseline net mean is positive but has a large drawdown and era variation.
- SMA200 is the strongest of six MA cells: $76.28 net/trade, 0.02135 ATR14 units,
  Sharpe 0.731, positive in all four eras.
- VIX >=25 is the strongest adequately populated high-VIX lead: 492 trades,
  $287.56 net/trade, 0.05538 ATR14 units, Sharpe 1.601; selection adjustment is
  missing.
- No inverse-vol sizing rule dominates one contract. ATR14 modestly reduces
  full-sample drawdown; inverse VIX and prior-day ATR worsen it.
- The prespecified 10% vol-target arm compounds to 214.68% net (8.12%
  annualized), with 11.06% realized vol, Sharpe 0.762, and -23.82% drawdown over
  3,701 sized trades. Its mechanics are confirmed; external figure parity is
  provisional because the outside numbers/convention were not supplied.
- LSE plus SMA200 reproduces the expected ~0.99 Sharpe: 1.014 (+0.024), with
  9.79% annualized net return, 9.67% realized vol, and -15.36% drawdown over
  2,417 observations/1,991 trades. Evidence: EXP-0005. LSE roll IDs are absent;
  EXP-0006 shows this estimate is materially aided by continuous-contract roll
  splices and is not a clean same-contract result.
- The old LSE/Databento yearly tables were not like-for-like: EXP-0004 was
  unfiltered and EXP-0005 used SMA200. Matching the rules changes Databento 2022
  from -15.88% to -3.35%, versus LSE -3.40%. On common dates after excluding 15
  obvious roll mismatches diagnostically, Sharpes are 0.851 LSE and 0.819
  Databento. Evidence: EXP-0006.

## Invalidated or superseded findings

- EXP-0001 raw-dollar-only reporting was superseded by EXP-0002 era reporting
  and EXP-0003 ATR-normalized reporting; its arithmetic was reproduced exactly.
- EXP-0002 was superseded by EXP-0003 because high-VIX effects required a
  scale-free diagnostic.

## Decisions and constraints

- Fractional units are research weights normalized by a shifted trailing
  252-session median; use config rounding for whole-contract tests.
- All historical cells are discovery, never a sealed holdout.
- Do not promote the MA or VIX lead before a complete selection-aware null.

## Known risks and next actions

1. Implement full-family feature-date permutation/block nulls and matched-rate
   controls for the searched filters.
2. Stress 18:00 slippage/commission and inspect the worst sparse-window dates.
3. Obtain independent code/artifact review.
4. If the leads survive, preregister a future shadow period.
5. For figure parity, obtain the outside yearly values and confirm whether its
   60-day estimator uses overnight-leg or full-session close-to-close returns.
6. Do not treat LSE parity as deployable until its continuous-contract roll
   construction is documented or reproduced with contract-level data. EXP-0006
   confirms quarterly splices occur inside some holding windows.

## Promotion candidates

- None. Findings are project-specific and not independently validated.
